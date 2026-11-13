"""Versioned B/A0 entry point. Historical v1 execution remains readable."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from openai import OpenAI

from .agent_loop import output_json, repair_structure, run_agent
from .budget import BudgetError, check_request
from .cases import DEFAULT_CASE_ID, resolve_case
from .corpus import Corpus
from .runtime_v2 import RunV2, dumps, wire_dumps, write_json
from .schemas_v2 import EXTRACTION_V2, REVIEW_V2
from .wire_contract import EXTRACTION_WIRE, WIRE_INSTRUCTIONS
from .wire_contract_v2 import EXTRACTION_WIRE_V2, WIRE_INSTRUCTIONS_V2


def _required(result):
    if not result["ok"]:
        raise RuntimeError(str(result["error_code"]) + ":" + str(result["message"]))
    return result["result"]


def retrieve_fixed(run, gateway):
    for index, step in enumerate(run.config["fixed_queries"]):
        hits = _required(gateway.dispatch("search_corpus", {"query": step["query"],
            "top_k": run.config["search_top_k"], "filters": {"doc_id": None, "cutoff_status": "BEFORE"}}, f"B_search_{index}", actor="program_fixed"))
        ids = [item["chunk_id"] for item in hits["hits"]]
        if ids:
            _required(gateway.dispatch("read_source", {"chunk_ids": ids,
                "neighbor_pages": run.config["read_neighbor_pages"]}, f"B_read_{index}", actor="program_fixed"))
        else:
            run.log("fixed_search_empty", {"stage": step["stage"], "query": step["query"]})
    return {"metadata": gateway.corpus.public_metadata(), "manual": gateway.corpus.manual,
            "sources": sorted(gateway.read_chunks.values(), key=lambda c: (c["doc_id"], c["page"])), "truncated": False}


def extraction_schema(run):
    return {"compact_v1": EXTRACTION_WIRE, "compact_v2": EXTRACTION_WIRE_V2}.get(
        run.config.get("wire_contract"), EXTRACTION_V2)


def extraction_request(run, system, packet):
    payload = {**packet, "task": "원문에서 발행기업 이익·적용 PER·공시 평가가치/주당평가액/적용주식수, 주식수 구성과 포함근거, 비교기업 PER·시총·이익·기준주가·기준주식수를 v2 records로 추출하라. CONTEXT를 공유하고 반복 문장을 줄여 출력 한도 내 등록하라. 직접값·파생값·미확인을 구별하고 SELECTION과 COVERAGE를 명시하라. 없는 원입력을 만들어 채우지 않는다. 기존주식/신주/의무인수/추가인수/옵션/구주를 원문 기준으로 구별한다. 실제 적용된 비교기업만 PEER로 등록한다. 기업별 정답은 제공되지 않는다."}
    compact = run.config.get("wire_contract") in {"compact_v1", "compact_v2"}
    req = run.base_request([{"role": "system", "content": system}, {"role": "user", "content": wire_dumps(payload)}], run.config["extraction_output_max"])
    req["text"] = {"format": {"type": "json_schema", "name": "extraction_compact" if compact else "extraction_v2", "strict": True, "schema": extraction_schema(run)}}
    return req


def calculation_view(gateway):
    # Full inputs/evidence live in the saved calculation registry; prompts use
    # ID references rather than duplicating every page and input recursively.
    keys = {"calc_id", "input_snapshot_id", "input_fact_ids", "formula", "result", "unit", "status", "reason",
            "kind", "label", "entity_id", "partial_sum", "difference_krw", "difference_percent", "excluded_peer", "assumption"}
    return [{k: v for k, v in row.items() if k in keys} for row in gateway.calculations.values()]


def review_request(run, system, packet, snapshot, calculations, ledger, gateway=None):
    payload = {**packet, "extraction_snapshot": snapshot, "calculations": calculations, "request_ledger": ledger,
               "task": "현재 input_snapshot_id를 사용해 한국어로 J1~J4 검토를 제출하라. 실제 계산 사용/배제는 calculation_uses로 연결한다. 새 조회나 새 숫자 추출은 불가하다. 미확인 사항과 관련 요청/이관을 남기고, 원장 OPEN 항목은 보존한다. 근거 없는 공시 적합성 승인을 만들지 않는다."}
    if gateway is not None and run.config.get("dynamic_submission_contract"):
        payload["state"] = gateway.state_view()
    req = run.base_request([{"role": "system", "content": system}, {"role": "user", "content": wire_dumps(payload)}], run.config["review_output_max"])
    req["text"] = {"format": {"type": "json_schema", "name": "review_v2", "strict": True, "schema": gateway.review_schema() if gateway is not None else REVIEW_V2}}
    return req


def run_fixed(run, gateway, system, packet, final_estimate):
    run.transition("EXPLORING")
    req = extraction_request(run, system, packet)
    value = output_json(run.request("extract", req, "EXPLORING", final_estimate))
    compact = run.config.get("wire_contract") in {"compact_v1", "compact_v2"}
    schema = extraction_schema(run)
    errors = [e.message for e in Draft202012Validator(schema).iter_errors(value)]
    if errors:
        value = repair_structure(run, value, schema, errors)
    arguments = {"request": {"operation": "REGISTER_BATCH", "base_snapshot_id": gateway.store.current_id,
        **({"batch": value} if compact else {"records": value["records"]})}}
    result = gateway.dispatch("calculate", arguments, "B_register", actor="program_fixed")
    if gateway.fatal_error:
        _required(result)
    if not result["ok"]:
        value = repair_structure(run, value, schema, [result["message"]])
        arguments["request"]["batch" if compact else "records"] = value if compact else value["records"]
        result = gateway.dispatch("calculate", arguments, "B_register_repaired", actor="program_fixed")
    _required(result)
    write_json(run.directory / "extraction_model_output.json", value)
    sid = gateway.store.current_id
    _required(gateway.dispatch("calculate", {"request": {"operation": "EVALUATE", "input_snapshot_id": sid,
        "calculation_types": ["ALL"]}}, "B_calculate", actor="program_fixed"))
    _required(gateway.dispatch("sensitivity", {"input_snapshot_id": sid,
        "alternatives": ["MEAN", "MEDIAN", "LEAVE_ONE_OUT"]}, "B_sensitivity", actor="program_fixed"))
    gateway.prepared_snapshot = sid
    run.transition("FINALIZING", actor="program_fixed")
    req = review_request(run, system, packet, gateway.store.get(sid), calculation_view(gateway), gateway.ledger.export(), gateway)
    review = output_json(run.request("review", req, "FINALIZING"))
    result = gateway.dispatch("submit_review", {"phase": "COMMIT", "input_snapshot_id": sid, "review": review}, "B_commit", actor="program_fixed")
    if gateway.fatal_error:
        _required(result)
    if not result["ok"]:
        claims = [f["claim_id"] for f in gateway.store.facts(sid).values()]
        review = repair_structure(run, review, gateway.review_schema(), [result["message"]], claims)
        result = gateway.dispatch("submit_review", {"phase": "COMMIT", "input_snapshot_id": sid, "review": review}, "B_commit_repaired", actor="program_commit")
    _required(result)
    return gateway.submitted_review


def save_state(run, gateway):
    write_json(run.directory / "snapshots.json", gateway.store.export())
    write_json(run.directory / "extraction.json", gateway.store.logical(gateway.store.current_id))
    write_json(run.directory / "calculations.json", list(gateway.calculations.values()))
    write_json(run.directory / "request_ledger.json", gateway.ledger.export())
    write_json(run.directory / "retrieval_history.json", {"search_hits": gateway.search_hits, "read_chunks": list(gateway.read_chunks)})
    write_json(run.directory / "source_packet.json", {"metadata": gateway.corpus.public_metadata(),
        "manual": gateway.corpus.manual, "sources": list(gateway.read_chunks.values()), "truncated": False})


def render_report(report):
    lines = [f"# {report['issuer_name']} {report['condition']} 개발 검토", "",
             "실제 API 답변과 공통 계산 기록이다. 내용의 정답 여부는 별도 채점한다.", "",
             f"- 실행: {report['run_id']}", f"- 내용 상태: {report['final_status']}", f"- 데이터 버전: {report['input_snapshot_id']}", ""]
    lines += ["- " + note for note in report["memo"]]
    for j in report["judgments"]:
        lines += ["", f"## {j['domain']} · {j['disposition']}", "", j["conclusion"], ""]
        for fact in j["facts"]:
            refs = "; ".join(f"{e['doc_id']} PDF {e['page']}쪽 · {e['locator']}" for e in fact["evidence"])
            lines.append(f"- {fact['text']} ({refs})")
        lines += ["", "미확인: " + "; ".join(j["unknowns"]), "", "다음 행동: " + j["next_action"]]
    lines += ["", "## 계산 사용과 배제", "", "```json", dumps(report["calculation_uses"]), "```",
              "", "## 요청과 이관", "", "```json", dumps({"requests": report["requests"], "escalations": report["escalations"]}), "```",
              "", "전체 계산·원입력·근거·사용량은 같은 실행 폴더의 JSON 기록에 보존했다.", ""]
    return "\n".join(lines)


def execute_v2(live=False, root=None, case_id=DEFAULT_CASE_ID, condition="B", repeat=1, client=None, key_provider=None):
    from .runner import ROOT, api_key
    from .tool_gateway import ToolGateway
    from .validation_v2 import final_status as final_status_v2

    root = Path(root or ROOT).resolve()
    if condition not in {"B", "A0"} or type(repeat) is not int or repeat < 1:
        raise ValueError("Invalid condition or repetition")
    config = json.loads((root / "config" / f"{condition}.json").read_text(encoding="utf-8"))
    config.update(case_id=case_id, condition=condition, repeat=repeat)
    run = RunV2(config, live, root / "runs", client)
    gateway = None
    try:
        directory, registration = resolve_case(root, case_id)
        corpus = Corpus(directory, case_id)
        verified = corpus.verify()
        run.transition("INPUT_VERIFIED", documents=verified)
        write_json(run.directory / "case_selection.json", {"registration": registration, "metadata": corpus.public_metadata()})
        hashes = {}
        for folder in (root / "ipo_eval", root / "config", root / "prompts"):
            for path in sorted(folder.iterdir()):
                if path.is_file() and path.suffix in {".py", ".json", ".md"}:
                    hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [directory / n for n in ("chunks.jsonl", "documents.jsonl", "case_manifest.jsonl", "manual.md")] + [directory / "raw" / (d["doc_id"] + ".pdf") for d in corpus.documents]:
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        write_json(run.directory / "input_hashes.json", hashes)
        gateway = ToolGateway(run, corpus)
        common = (root / "prompts/common.md").read_text(encoding="utf-8") + "\n" + (root / "prompts/v2_contract.md").read_text(encoding="utf-8")
        if config.get("wire_contract") == "compact_v1":
            common += "\n" + WIRE_INSTRUCTIONS
        elif config.get("wire_contract") == "compact_v2":
            common += "\n" + WIRE_INSTRUCTIONS_V2
        if condition == "B":
            packet = retrieve_fixed(run, gateway)
            final_template = review_request(run, common, packet, gateway.store.get(gateway.store.current_id), [], gateway.ledger.export(), gateway)
            # Planning allowance for the bounded extraction plus expanded IDs,
            # derived results and sensitivity rows. Actual final request is
            # checked again immediately before transmission.
            final_estimate = run.estimate(final_template) + 3 * config["extraction_output_max"]
            req = extraction_request(run, common, packet)
            try:
                audit = check_request(run, run.estimate(req), config["extraction_output_max"], "EXPLORING", final_estimate)
            except BudgetError as exc:
                save_state(run, gateway)
                return run.directory, run.finish("PREFLIGHT_BLOCKED_BUDGET", final_status=None,
                    actual_model_answer=False, failure_reason=str(exc), source_pages=len(gateway.read_chunks))
            write_json(run.directory / "preflight_budget.json", audit)
        else:
            final_estimate = 0
            packet = None
        run.transition("PREFLIGHT_COMPLETE")
        key = None if client is not None else (key_provider or api_key)()
        if not live:
            save_state(run, gateway)
            return run.directory, run.finish("PREFLIGHT_COMPLETE", final_status=None, source_pages=len(gateway.read_chunks),
                                            api_key_configured=bool(key), actual_model_answer=False)
        if client is None and not key:
            save_state(run, gateway)
            return run.directory, run.finish("NOT_STARTED_MISSING_API_KEY", final_status=None, actual_model_answer=False)
        if client is None:
            run.client = OpenAI(api_key=key, base_url="https://api.openai.com/v1", max_retries=0)
        if condition == "B":
            review = run_fixed(run, gateway, common, packet, final_estimate)
        else:
            system = common + "\n" + (root / "prompts/A0.md").read_text(encoding="utf-8")
            review = run_agent(run, gateway, system, corpus.public_metadata(), corpus.manual)
        save_state(run, gateway)
        status = final_status_v2(review)
        report = {**deepcopy(review), "run_id": run.run_id, "condition": condition, "case_id": case_id,
            "issuer_name": corpus.case["issuer_name"], "cutoff_at": corpus.case["cutoff_at"],
            "config_version": config["version"], "final_status": status, "calculations": list(gateway.calculations.values())}
        write_json(run.directory / "review.json", report)
        (run.directory / "review.md").write_text(render_report(report), encoding="utf-8")
        return run.directory, run.finish("SUBMITTED", final_status=status, actual_model_answer=True,
            model_reported_status=review["model_reported_status"], status_mismatch=status != review["model_reported_status"])
    except Exception as exc:
        if gateway is not None:
            save_state(run, gateway)
        run.log("run_stopped", {"error_type": type(exc).__name__, "reason": str(exc)})
        return run.directory, run.finish("FAILED", final_status=None, actual_model_answer=False, failure_reason=str(exc))
