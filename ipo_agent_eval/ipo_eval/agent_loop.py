"""A0 chooses one real tool at a time; B uses the same gateway and budgets."""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator

from .budget import BudgetError, check_request, exploration_output_limit
from .runtime_v2 import wire_dumps as dumps, write_json
from .format_patch import PATCH_SCHEMA, apply_format_patch


def output_json(raw):
    text = "".join(c.get("text", "") for item in raw.get("output", [])
                   if item.get("type") == "message" for c in item.get("content", [])
                   if c.get("type") == "output_text")
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        raise RuntimeError("INVALID_JSON") from None


def _format_only(before, after, path=()):
    """An allowed repair cannot replace numbers, claims, source locations or states.

    Extra keys may be removed, missing empty/null fields inserted, and evidence
    claim links repaired. A shape that needs new factual content fails closed.
    """
    if isinstance(before, dict) and isinstance(after, dict):
        for key in before.keys() & after.keys():
            _format_only(before[key], after[key], (*path, key))
        for key in after.keys() - before.keys():
            if after[key] not in (None, [], {}):
                raise RuntimeError("REPAIR_ADDED_CONTENT")
        return
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            raise RuntimeError("REPAIR_CHANGED_LIST")
        for index, (left, right) in enumerate(zip(before, after)):
            _format_only(left, right, (*path, index))
        return
    if before == after and type(before) is type(after):
        return
    if path and path[-1] == "claim_id" and any(p in {"evidence", "counter_evidence", "resolution_evidence", "treatment_evidence"} for p in path if isinstance(p, str)):
        if isinstance(after, str) and after.strip():
            return
    if path and path[-1] in {"page", "version"} and isinstance(before, str) and before.isdecimal() and type(after) is int and int(before) == after:
        return
    raise RuntimeError("REPAIR_CHANGED_FACT_OR_DECISION:" + "/".join(map(str, path)))


def repair_structure(run, value, schema, errors, known_claims=(), final_input_estimate=None):
    if run.repairs >= run.config["max_format_repairs"]:
        raise RuntimeError("FORMAT_REPAIR_EXHAUSTED")
    run.repairs += 1
    payload = {"previous_output": value, "structural_errors": errors, "known_claim_ids": list(known_claims),
               "instruction": "형식만 고쳐 동일한 JSON을 반환하라. 기존 수치·주장·판단·요청 상태·출처 문서/쪽/위치는 바꾸지 말라. evidence.claim_id의 기존 주장 연결과 정수 형식만 고칠 수 있다. 누락된 빈 배열/null 추가, 허용하지 않은 여분 키 삭제는 가능하다. 새 사실을 쓰거나 추가 검색하지 말라."}
    patch_mode = run.config.get("format_repair_contract") == "patch_v1"
    if patch_mode:
        payload["instruction"] = "원문 전체를 재작성하지 말고 허용된 형식 수정 operations만 반환하라. JSON Pointer path를 사용한다. 누락된 빈필드 ADD_EMPTY, 스키마상 여분 키 REMOVE_EXTRA, page/version의 같은 정수값 NORMALIZE_INTEGER, evidence의 기존 주장 ID 연결 RELINK_CLAIM만 허용된다. 배열 길이, 수치, 사실, 판단, 요청 상태, 출처는 바꿀 수 없다. 의미 오류를 수정하지 않는다."
        payload["target_schema"] = schema
    req = run.base_request([{"role": "user", "content": dumps(payload)}], run.config["format_repair_output_max"])
    req["text"] = {"format": {"type": "json_schema", "name": "format_patch" if patch_mode else "format_repair", "strict": True, "schema": PATCH_SCHEMA if patch_mode else schema}}
    phase = "EXPLORATION_REPAIR" if run.phase == "EXPLORING" else "REPAIR"
    final_estimate = (final_input_estimate if final_input_estimate is not None else run.final_input_estimate + run.config["format_repair_output_max"]) if phase == "EXPLORATION_REPAIR" else 0
    candidate = output_json(run.request("format_repair", req, phase, final_estimate))
    if patch_mode:
        write_json(run.directory / "format_patch.json", candidate)
        candidate = apply_format_patch(value, candidate, schema, known_claim_ids=known_claims)
    else:
        _format_only(value, candidate)
    problems = [e.message for e in Draft202012Validator(schema).iter_errors(candidate)]
    if problems:
        raise RuntimeError("INVALID_STRUCTURE_AFTER_REPAIR")
    run.log("format_repair_result", {"allowed": "format_and_evidence_claim_links_only", "facts_and_decisions_preserved": True})
    return candidate


def tool_request(run, history, gateway, phase):
    maximum = exploration_output_limit(run) if phase == "EXPLORING" else run.config["review_output_max"]
    req = run.base_request(history, maximum)
    req.update(tools=gateway.tools(phase), parallel_tool_calls=False, include=["reasoning.encrypted_content"])
    if phase == "FINALIZING":
        req["tool_choice"] = {"type": "function", "name": "submit_review"}
    return req


def run_agent(run, gateway, system, metadata, manual):
    initial = {"metadata": metadata, "manual": manual, "input_snapshot_id": gateway.store.current_id,
               "budget": {k: run.config[k] for k in ("max_model_calls", "max_tool_calls", "input_tokens_target_max", "output_tokens_max", "exploration_output_max", "max_run_usd", "wall_seconds_max")}}
    if run.config.get("dynamic_submission_contract"):
        initial["state"] = gateway.state_view()
    history = [{"role": "system", "content": system},
               {"role": "user", "content": dumps(initial)}]
    run.transition("EXPLORING")
    seen_call_ids = set()

    def final_request(extra=None):
        prospective = history + ([{"type": "function_call_output", "call_id": "budget_estimate", "output": dumps(extra)}] if extra is not None else [])
        return tool_request(run, prospective, gateway, "FINALIZING")

    def guard(result):
        # Full result is measured before it is returned/read/registered. It is
        # never silently truncated to make a reservation pass.
        if run.phase != "EXPLORING":
            return
        observation = result
        growth_allowance = 0
        if run.config.get("dynamic_submission_contract"):
            observation = {"call_id": "prospective_observation", "tool": "prospective_tool", "ok": True,
                "result": result, "error_code": None, "message": None,
                "usage_delta": {"tool_calls": 1, "pages": 9, "new_read_pages": 9, "seconds": 0},
                "state": gateway.state_view()}
            # State is observed before mutation. Reserve for IDs introduced by
            # this model call and ledger/calculation growth in its full result.
            # Full source pages themselves are already measured in observation.
            growth_allowance = 1024
            if any(key in result for key in ("registered_ids", "calculations", "active_records")):
                growth_allowance += 2 * run.config["exploration_output_max"] + 2 * len(run.encoder.encode(dumps(result)))
        req = final_request(observation)
        check_request(run, run.estimate(req) + growth_allowance, run.config["review_output_max"], "FINALIZING")
        if growth_allowance:
            run.log("observation_state_reservation", {"envelope_and_current_state_included": True,
                "prospective_state_growth_tokens_reserved": growth_allowance})
        if run.tool_calls + 3 + int(run.repairs < run.config["max_format_repairs"]) > run.config["max_tool_calls"]:
            raise BudgetError("TOOL_CALL_RESERVATION")

    gateway.run.observation_guard = guard
    while gateway.submitted_review is None:
        phase = run.phase
        if phase == "EXPLORING":
            req = tool_request(run, history, gateway, phase)
            final_estimate = run.estimate(final_request()) + max(0, req["max_output_tokens"])
            try:
                check_request(run, run.estimate(req), req["max_output_tokens"], phase, final_estimate)
            except BudgetError as exc:
                gateway.prepared_snapshot = gateway.store.current_id
                run.transition("FINALIZING", reason=str(exc), actor="program_commit")
                history.append({"role": "user", "content": dumps({"phase": "FINALIZING", "input_snapshot_id": gateway.prepared_snapshot,
                     "reason": str(exc), "state": gateway.state_view() if run.config.get("dynamic_submission_contract") else None,
                     "instruction": "예약된 최종 제출만 작성하라. 추가 검색/계산은 불가하다. 미확인 사항과 남은 요청을 명시하라."})})
                continue
        else:
            req = tool_request(run, history, gateway, "FINALIZING")
            final_estimate = 0
        raw = run.request("explore" if phase == "EXPLORING" else "finalize", req, phase, final_estimate)
        history.extend(deepcopy(raw.get("output", [])))
        write_json(run.directory / "context.json", history)
        calls = [item for item in raw.get("output", []) if item.get("type") == "function_call"]
        if not calls:
            raise RuntimeError("NO_VALID_SUBMISSION")
        if len(calls) != 1:
            raise RuntimeError("MULTIPLE_TOOL_CALLS_WITH_PARALLEL_DISABLED")
        call = calls[0]
        if not call.get("call_id") or call["call_id"] in seen_call_ids:
            raise RuntimeError("DUPLICATE_OR_MISSING_CALL_ID")
        seen_call_ids.add(call["call_id"])
        try:
            arguments = json.loads(call["arguments"])
        except (TypeError, ValueError):
            raise RuntimeError("INVALID_TOOL_ARGUMENT_JSON") from None
        result = gateway.dispatch(call["name"], arguments, call["call_id"], actor="model")
        history.append({"type": "function_call_output", "call_id": call["call_id"], "output": dumps(result)})
        write_json(run.directory / "context.json", history)
        if gateway.fatal_error:
            raise RuntimeError(gateway.fatal_error)
        if not result["ok"] and result["error_code"] == "BUDGET_LIMIT":
            if phase != "EXPLORING":
                raise RuntimeError("FINALIZATION_BUDGET_LIMIT:" + str(result["message"]))
            gateway.prepared_snapshot = gateway.store.current_id
            run.transition("FINALIZING", reason=result["message"], actor="program_commit")
            history.append({"role": "user", "content": dumps({"phase": "FINALIZING", "input_snapshot_id": gateway.prepared_snapshot,
                "state": gateway.state_view() if run.config.get("dynamic_submission_contract") else None,
                "instruction": "예산 한도로 최종 제출 단계다. 현재까지 받은 근거와 미확인 사항만 사용하라."})})
            continue
        if not result["ok"] and result["error_code"] not in {"TOO_LARGE", "BUDGET_LIMIT", "UNAVAILABLE", "INVALID_CALCULATION"}:
            schemas = {tool["name"]: tool["parameters"] for tool in gateway.tools(phase)}
            if call["name"] not in schemas:
                raise RuntimeError("UNKNOWN_TOOL")
            claims = [f["claim_id"] for f in gateway.store.facts(gateway.store.current_id).values()]
            repaired = repair_structure(run, arguments, schemas[call["name"]], [result["message"]], claims,
                final_input_estimate=run.estimate(final_request()) + run.config["format_repair_output_max"])
            retry_id = call["call_id"] + "_format_repair"
            result = gateway.dispatch(call["name"], repaired, retry_id, actor="program_commit" if phase == "FINALIZING" else "model")
            history.append({"role": "user", "content": dumps({"format_repair_arguments": repaired, "format_repair_tool_result": result})})
            write_json(run.directory / "context.json", history)
            if not result["ok"]:
                raise RuntimeError("INVALID_TOOL_AFTER_SHARED_REPAIR:" + str(result["error_code"]))
        if gateway.prepared_snapshot is not None and gateway.submitted_review is None:
            run.transition("FINALIZING", reason="model_PREPARE", actor="model")
    run.observation_guard = None
    write_json(run.directory / "context.json", history)
    return gateway.submitted_review
