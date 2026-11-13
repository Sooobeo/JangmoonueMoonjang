"""Read-only analysis of a declared remediation batch, including partial runs.

Only this report directory receives output. No runner, API client, private gold,
source modification, or repair of an execution artifact is performed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
_cost_spec = importlib.util.spec_from_file_location("saved_usage_pricing", ROOT / "scripts/audit_costs.py")
_cost = importlib.util.module_from_spec(_cost_spec)
_cost_spec.loader.exec_module(_cost)
GROUP_KINDS = {"contexts": "CONTEXT", "values": "VALUE", "shares": "SHARE_COMPONENT",
               "peers": "PEER", "derivations": "DERIVATION", "selections": "SELECTION", "coverage": "COVERAGE"}
TERMINAL = {"FAILED", "SUBMITTED", "INTERRUPTED_BY_OPERATOR"}


def load(path, default=None, issues=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        if issues is not None:
            issues.append({"file": str(path), "issue": "unreadable_or_currently_incomplete", "error_type": type(exc).__name__})
        return default


def events_at(directory, issues):
    path = directory / "events.jsonl"
    if not path.exists():
        return []
    result = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            result.append(json.loads(line))
        except ValueError:
            issues.append({"file": str(path), "line": index, "issue": "invalid_or_incomplete_event_line"})
    return result


def relative(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def key(item):
    summary = item.get("summary", {})
    return tuple(item.get(k, summary.get(k, 1 if k == "repeat" else None)) for k in ("case_id", "condition", "repeat"))


def operation(name, arguments):
    if name == "calculate":
        request = arguments.get("request") if isinstance(arguments, dict) else None
        return request.get("operation", "INVALID_ARGUMENT") if isinstance(request, dict) else "INVALID_ARGUMENT"
    return name


def schema_alias_findings(request):
    """Detect saved review schemas that restrict unrelated prose to gap IDs."""
    candidates = [("text.format.schema", (request.get("text") or {}).get("format", {}).get("schema"))]
    candidates += [("tools." + str(tool.get("name")) + ".parameters", tool.get("parameters"))
                   for tool in request.get("tools", [])]
    for item in request.get("input", []):
        if item.get("role") == "user" and isinstance(item.get("content"), str):
            try:
                content = json.loads(item["content"])
            except ValueError:
                continue
            if isinstance(content, dict) and isinstance(content.get("target_schema"), dict):
                candidates.append(("format_patch.target_schema", content["target_schema"]))
    findings = []
    for name, schema in candidates:
        if not isinstance(schema, dict):
            continue
        if "review" in schema.get("properties", {}):
            schema = schema["properties"]["review"]
            name += ".properties.review"
        properties = schema.get("properties", {})
        field = properties.get("missing_inputs", {}).get("items", {}).get("properties", {}).get("field", {})
        restricted = field.get("enum")
        if not restricted:
            continue
        contaminated = []
        def walk(node, path=()):
            if isinstance(node, dict):
                if node.get("type") == "string" and node.get("enum") == restricted and path != ("properties", "missing_inputs", "items", "properties", "field"):
                    contaminated.append("/" + "/".join(path))
                for key_, child in node.items():
                    walk(child, (*path, key_))
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    walk(child, (*path, str(index)))
        walk(schema)
        if contaminated:
            findings.append({"issue": "DYNAMIC_SCHEMA_SHARED_STRING_ENUM_CONTAMINATION", "schema_location": name,
                "missing_input_field_enum": restricted, "unrelated_string_paths": contaminated,
                "interpretation": "Executor-generated schema forces unrelated source IDs/prose to missing-input names. Preserve the failure, but do not attribute these forced values to independent model source fabrication."})
    return findings


def discover_unlisted(plan, plan_path, listed_directories, issues):
    """Find active LIVE directories by time, plan membership and frozen hashes.

    The registry is authoritative. Discovered candidates are explicitly labelled;
    multiple candidates are retained as ambiguous, never selected by outcome.
    """
    planned = {key(x) for x in plan["planned_runs"]}
    lower = plan_path.stat().st_mtime
    later = [p.stat().st_mtime for p in HERE.glob("*_plan.json") if p != plan_path and p.stat().st_mtime > lower]
    upper = min(later, default=float("inf"))
    expected = {k: v for k, v in plan.get("source_hashes", {}).items() if k.startswith(("ipo_eval/", "config/", "prompts/"))}
    candidates = defaultdict(list)
    for directory in sorted((ROOT / "runs").iterdir()):
        if not directory.is_dir() or directory.resolve() in listed_directories:
            continue
        config_path = directory / "config.json"
        if not config_path.exists() or not lower <= config_path.stat().st_mtime < upper:
            continue
        config = load(config_path, {}, issues)
        if key(config) not in planned or config.get("version") != plan.get("version"):
            continue
        event_path = directory / "events.jsonl"
        if not event_path.exists():
            continue
        try:
            with event_path.open(encoding="utf-8") as stream:
                first = json.loads(stream.readline())
        except (ValueError, OSError):
            continue
        if first.get("event") != "run_created" or first.get("mode") != "LIVE":
            continue
        hashes = load(directory / "input_hashes.json", {}, issues)
        if not expected or any(hashes.get(k) != v for k, v in expected.items()):
            continue
        candidates[key(config)].append(directory)
    return candidates


def audit_usage(directory, events, summary, terminal, issues):
    request_paths = sorted(directory.glob("[0-9]*_request.json"))
    response_paths = sorted(directory.glob("[0-9]*_response.json"))
    calls = max(len(request_paths), sum(e.get("event") == "model_call_started" for e in events), summary.get("model_calls", 0))
    rows, model_choices, response_ids = [], Counter(), set()
    raw_usage_count = 0
    tokens = Counter()
    total = Decimal(0)
    request_schema_issues = []
    for path in request_paths:
        request = load(path, {}, issues)
        for finding in schema_alias_findings(request):
            request_schema_issues.append({"request_file": relative(path), **finding})
    for path in response_paths:
        raw = load(path, None, issues)
        if not isinstance(raw, dict):
            continue
        rid = raw.get("id")
        if rid and rid in response_ids:
            issues.append({"file": str(path), "issue": "duplicate_response_id_not_double_counted", "response_id": rid})
            continue
        response_ids.add(rid)
        request_path = path.with_name(path.name.replace("_response.json", "_request.json"))
        request = load(request_path, {}, issues)
        entry = {"response_file": relative(path), "response_id": rid, "returned_model": raw.get("model"),
                 "response_status": raw.get("status"), "incomplete_details": raw.get("incomplete_details"),
                 "usage": raw.get("usage"), "estimated_cost_usd": None}
        for item in raw.get("output") or []:
            if item.get("type") == "function_call":
                try:
                    arguments = json.loads(item.get("arguments", ""))
                except (ValueError, TypeError):
                    arguments = None
                model_choices[operation(item.get("name"), arguments)] += 1
        if isinstance(raw.get("usage"), dict):
            raw_usage_count += 1
            try:
                if raw.get("model") != "gpt-6.1-terra" or request.get("service_tier", "default") != "default":
                    raise ValueError("Pricing requires returned Terra and Standard service tier")
                priced = _cost.price_usage(raw["usage"], (request.get("prompt_cache_options") or {}).get("ttl", "30m"))
                entry.update(priced)
                tokens.update({k: priced[k] for k in _cost.COUNTS})
                total += Decimal(priced["estimated_cost_usd"])
            except ValueError as exc:
                entry["pricing_error"] = str(exc)
                issues.append({"file": str(path), "issue": "unpriced_saved_usage", "reason": str(exc)})
        rows.append(entry)
    unknown = max(0, calls - raw_usage_count)
    unpriced = sum(r.get("usage") is not None and r["estimated_cost_usd"] is None for r in rows)
    priced_count = sum(r["estimated_cost_usd"] is not None for r in rows)
    known = str(total) if priced_count or calls == 0 else None
    failed_unknown = sum(e.get("event") == "model_call_failed" for e in events)
    return {"model_calls": calls, "responses_with_usage": raw_usage_count, "priced_responses": priced_count,
        "requests_without_usage": unknown, "unpriced_usage_requests": unpriced,
        "inflight_or_unrecorded_response_requests": 0 if terminal else max(0, unknown - failed_unknown),
        "known_usage_cost_usd": known,
        "total_cost_estimate_usd": known if terminal and unknown == 0 and unpriced == 0 else None,
        "invoice_cost_usd": None, "token_totals": dict(tokens), "responses": rows,
        "real_model_tool_choices": dict(model_choices),
        "request_schema_issues": request_schema_issues,
        "pricing_basis": {"source": "scripts/audit_costs.py::price_usage", "rates_per_million_usd": {k: str(v) for k, v in _cost.RATES.items()},
                          "scope": "Terra Standard, per-request input <=272000 tokens; missing TTL uses request/default 30m; not an invoice"}}


def analyze_directory(directory, planned, discovery="result_registry", registry_summary=None):
    issues = []
    summary = load(directory / "summary.json", {}, issues) or registry_summary or {}
    events = events_at(directory, issues)
    status = summary.get("execution_status", "RUNNING")
    terminal = status in TERMINAL or status.startswith("NOT_STARTED_")
    usage = audit_usage(directory, events, summary, terminal, issues)
    snapshots = load(directory / "snapshots.json", {}, issues)
    extraction = load(directory / "extraction.json", {}, issues)
    review = load(directory / "review.json", None, issues)
    calculations = load(directory / "calculations.json", None, issues)
    tools = [e for e in events if e.get("event") == "tool_call"]
    actor_operations = defaultdict(Counter)
    reconstructed_records, reconstructed_calculations = {}, {}
    for event in tools:
        arguments = event.get("arguments", {})
        op = operation(event.get("tool"), arguments)
        actor_operations[event.get("actor", "UNKNOWN")][op] += 1
        if event.get("error") or not isinstance(event.get("result"), dict):
            continue
        if op == "REGISTER_BATCH":
            request = arguments["request"]
            if "batch" in request:
                for group, kind in GROUP_KINDS.items():
                    for item in request["batch"].get(group, []):
                        reconstructed_records[item["id"]] = kind
            else:
                for record in request.get("records", []):
                    reconstructed_records[record["record_id"]] = record["kind"]
        for calc in event["result"].get("calculations", []):
            reconstructed_calculations[calc["calc_id"]] = calc
    state = next((e["state"] for e in reversed(events) if e.get("event") == "tool_envelope" and "state" in e), {})
    sid = state.get("input_snapshot_id", snapshots.get("current_id", extraction.get("input_snapshot_id")))
    saved_records = snapshots.get("snapshots", {}).get(sid, {}).get("records")
    kinds = Counter(r["kind"] for r in saved_records.values()) if saved_records is not None else Counter(reconstructed_records.values())
    fact_ids = state.get("registered_fact_ids")
    if fact_ids is None and "facts" in extraction:
        fact_ids = list(extraction["facts"])
    if calculations is None:
        calculations = list(reconstructed_calculations.values())
    kind_status = defaultdict(Counter)
    for calc in calculations:
        kind_status[calc.get("kind", calc.get("id", "UNKNOWN"))][calc.get("status", "UNKNOWN")] += 1
    used = review.get("calculation_uses", []) if review else []
    errors = [{"call_id": e.get("call_id"), "tool": e.get("tool"), "error_code": e.get("error_code"), "message": e.get("message")}
              for e in events if e.get("event") == "tool_envelope" and e.get("ok") is False]
    config = load(directory / "config.json", {}, issues)
    return {**planned, "run_id": directory.name, "directory": relative(directory), "discovery": discovery,
        "execution_started": not status.startswith(("NOT_STARTED", "PREFLIGHT")),
        "attempt_directory_created": True, "api_started": usage["model_calls"] > 0, "execution_status": status,
        "final_status": summary.get("final_status"), "failure_reason": summary.get("failure_reason"),
        "terminal": terminal, "elapsed_seconds": summary.get("elapsed_seconds"),
        "registration": {"input_snapshot_id": sid, "record_count": sum(kinds.values()), "records_by_kind": dict(kinds),
            "fact_count": len(fact_ids) if fact_ids is not None else None,
            "source": "saved_snapshot" if saved_records is not None else "successful_tool_events_and_latest_state"},
        "tool_operations_by_actor": {k: dict(v) for k, v in actor_operations.items()},
        "real_model_tool_choices": usage["real_model_tool_choices"],
        "calculations": {"count": len(calculations), "by_kind_status": {k: dict(v) for k, v in kind_status.items()},
            "by_status": dict(Counter(c.get("status", "UNKNOWN") for c in calculations)),
            "rows": [{k: c.get(k) for k in ("calc_id", "kind", "entity_id", "status", "result", "reason")} for c in calculations]},
        "submitted_calculation_uses": used if review else None,
        "submitted_use_counts": dict(Counter(c.get("use", "UNKNOWN") for c in used)) if review else None,
        "tool_errors": errors, "usage_cost": usage,
        "infrastructure_findings": usage["request_schema_issues"],
        "run_config": {k: config.get(k) for k in ("version", "model", "reasoning_effort", "wire_contract", "format_repair_contract",
            "max_model_calls", "max_tool_calls", "input_tokens_target_max", "output_tokens_max", "max_run_usd", "wall_seconds_max")},
        "read_issues": issues, "evidence_files": [relative(directory / name) for name in ("summary.json", "events.jsonl", "snapshots.json", "extraction.json", "calculations.json", "review.json") if (directory / name).exists()]}


def empty_row(planned, status, reason=None):
    return {**planned, "run_id": None, "directory": None, "discovery": None,
        "execution_started": False, "attempt_directory_created": False, "api_started": False, "execution_status": status,
        "final_status": None, "failure_reason": reason, "terminal": status.startswith("NOT_STARTED_"),
        "registration": None, "calculations": None, "submitted_calculation_uses": None,
        "usage_cost": None, "read_issues": []}


def analyze(label):
    plan_path, runs_path = HERE / f"{label}_plan.json", HERE / f"{label}_runs.json"
    issues = []
    plan = load(plan_path, None, issues)
    if plan is None:
        raise ValueError("Readable declared plan required: " + str(plan_path))
    registry = load(runs_path, {"complete": False, "runs": []}, issues)
    listed = {key(x): x for x in registry.get("runs", [])}
    if len(listed) != len(registry.get("runs", [])):
        raise ValueError("Duplicate planned identity in result registry; refusing outcome selection")
    directories = {resolve(r["directory"]).resolve() for r in listed.values() if r.get("directory")}
    discovered = discover_unlisted(plan, plan_path, directories, issues)
    rows, ambiguous = [], []
    for item in plan["planned_runs"]:
        row = listed.get(key(item))
        if row is not None and row.get("directory"):
            rows.append(analyze_directory(resolve(row["directory"]), item, registry_summary=row.get("summary")))
        elif row is not None:
            summary = row.get("summary", {})
            rows.append(empty_row(item, summary.get("execution_status", "NOT_STARTED"), summary.get("failure_reason")))
        elif len(discovered[key(item)]) == 1:
            rows.append(analyze_directory(discovered[key(item)][0], item, "unlisted_matching_live_directory"))
        else:
            status = "NOT_STARTED_PLAN_NOT_LIVE" if not plan.get("live") else "NOT_YET_OBSERVED"
            if discovered[key(item)]:
                status = "AMBIGUOUS_UNLISTED_RUNS"
                ambiguous.extend({**item, "directory": relative(p)} for p in discovered[key(item)])
            rows.append(empty_row(item, status))
    started = [r for r in rows if r["execution_started"]]
    known = sum((Decimal(r["usage_cost"]["known_usage_cost_usd"]) for r in started if r["usage_cost"]["known_usage_cost_usd"] is not None), Decimal(0))
    unknown = sum(r["usage_cost"]["requests_without_usage"] for r in started)
    unpriced = sum(r["usage_cost"]["unpriced_usage_requests"] for r in started)
    all_terminal = all(r["terminal"] for r in rows)
    old = load(ROOT / "reports/a0_implementation/D5_v032_comparison.json", {"runs": []}, issues)
    old_config = load(ROOT / "reports/a0_implementation/D5_v032_source/config/B.json", {}, issues)
    new_config = load(resolve(plan.get("source_snapshot", "")) / "config/B.json", {}, issues)
    config_changes = {k: {"v032": old_config.get(k), "current": new_config.get(k)}
                      for k in sorted(set(old_config) | set(new_config))
                      if old_config.get(k) != new_config.get(k) and k not in {"change_note"}}
    reference = []
    identities = {key(i) for i in plan["planned_runs"]}
    for row in old["runs"]:
        if key(row) in identities:
            reference.append({"case_id": row["case_id"], "condition": row["condition"], "run_id": row["run_id"],
                "execution_status": row["summary"]["execution_status"], "final_status": row["summary"].get("final_status"),
                "failure_reason": row["summary"].get("failure_reason"), "calculation_count": len(row.get("calculation_ids", [])),
                "snapshot_ids": row.get("snapshot_ids"), "known_usage_cost_usd": row.get("cost_audit", {}).get("known_usage_cost_usd")})
    conditions = {}
    for condition in sorted({r["condition"] for r in rows}):
        group = [r for r in rows if r["condition"] == condition]
        observed = [r for r in group if r["execution_started"]]
        choices, statuses, calc_states, uses, token_totals = Counter(), Counter(), Counter(), Counter(), Counter()
        for r in observed:
            choices.update(r["real_model_tool_choices"])
            statuses[r["execution_status"]] += 1
            calc_states.update(r["calculations"]["by_status"])
            uses.update(r.get("submitted_use_counts") or {})
            token_totals.update(r["usage_cost"]["token_totals"])
        conditions[condition] = {"planned": len(group), "actual_started": len(observed),
            "api_started": sum(r["api_started"] for r in group), "observed_statuses": dict(statuses),
            "registered_records": sum(r["registration"]["record_count"] for r in observed),
            "registered_facts": sum(r["registration"]["fact_count"] or 0 for r in observed),
            "fact_count_unobserved_runs": sum(r["registration"]["fact_count"] is None for r in observed),
            "real_model_tool_choices": dict(choices), "calculation_status_counts": dict(calc_states),
            "submitted_calculation_use_counts": dict(uses), "token_totals": dict(token_totals),
            "known_usage_cost_usd": str(sum((Decimal(r["usage_cost"]["known_usage_cost_usd"]) for r in observed
                if r["usage_cost"]["known_usage_cost_usd"] is not None), Decimal(0))),
            "requests_without_usage": sum(r["usage_cost"]["requests_without_usage"] for r in observed)}
    return {"label": label, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "registry_complete": registry.get("complete", False), "all_planned_terminal_observed": all_terminal,
        "counts": {"planned": len(rows), "actual_started": len(started), "api_started": sum(r["api_started"] for r in rows),
            "explicit_not_started": sum(r["execution_status"].startswith("NOT_STARTED_") for r in rows),
            "not_yet_observed": sum(r["execution_status"] == "NOT_YET_OBSERVED" for r in rows),
            "ambiguous_unlisted": len(ambiguous), "by_status": dict(Counter(r["execution_status"] for r in rows))},
        "conditions": conditions,
        "costs": {"known_usage_cost_usd": str(known), "requests_without_usage": unknown, "unpriced_usage_requests": unpriced,
            "batch_total_estimate_usd": str(known) if all_terminal and not unknown and not unpriced and not ambiguous else None,
            "invoice_cost_usd": None}, "runs": rows, "ambiguous_unlisted_runs": ambiguous,
        "v032_matched_reference": reference, "configuration_changes_vs_v032": config_changes,
        "quality_grading_performed": False, "read_issues": issues,
        "inputs": {"plan": relative(plan_path), "runs": relative(runs_path), "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest()},
        "limits": ["Read-only artifact analysis; no correctness grading or model/API request.",
            "actual_started counts observed LIVE execution attempts, excluding NOT_STARTED/PREFLIGHT statuses; api_started separately requires an actual saved model-call attempt.",
            "NOT_YET_OBSERVED is not proof that a run was never started; active discovery requires matching LIVE/time/frozen input hashes.",
            "Saved model function calls are counted separately from program-fixed and repaired tool invocations.",
            "Partial analysis is a point-in-time view; missing usage and in-flight responses are not free.",
            "v032 and this batch differ in common token/call/cost/time budgets, transport, repair, observations and retry policy. This is not an isolated intervention effect.",
            "Submitted status and registered/calculated counts do not establish source correctness or A0 superiority."]}


def markdown(report):
    c = report["counts"]
    lines = [f"# {report['label']} 저장 실행 분석", "", f"관찰 시각: {report['generated_at_utc']}", "",
        f"계획{c['planned']}건 · 실제 시작{c['actual_started']}건 · API 시작{c['api_started']}건 · 명시적 미시작{c['explicit_not_started']}건 · 아직 확인되지 않음{c['not_yet_observed']}건.", "",
        "| 사례 | 조건 | 상태 | 레코드/사실 | 계산 수·상태 | 모델 선택 등록/계산/민감도 | 알려진 추정 USD | 불명 usage 요청 |",
        "|---|---|---|---:|---|---|---:|---:|"]
    for r in report["runs"]:
        reg, calc, cost = r.get("registration"), r.get("calculations"), r.get("usage_cost")
        counts = r.get("real_model_tool_choices", {})
        lines.append(f"| {r['case_id']} | {r['condition']} | {r['execution_status']} | " +
            (f"{reg['record_count']}/{reg['fact_count']}" if reg else "—") + " | " +
            (f"{calc['count']} {json.dumps(calc['by_status'], ensure_ascii=False)}" if calc else "—") + " | " +
            ("/".join(str(counts.get(k, 0)) for k in ("REGISTER_BATCH", "EVALUATE", "sensitivity")) if cost else "—") + " | " +
            (str(cost['known_usage_cost_usd']) if cost else "—") + " | " + (str(cost['requests_without_usage']) if cost else "—") + " |")
    lines += ["", f"알려진 사용량의 비용 추정 합계는 **${report['costs']['known_usage_cost_usd']}**다. "
        f"누락 usage 요청{report['costs']['requests_without_usage']}건, 가격을 계산하지 못한 usage{report['costs']['unpriced_usage_requests']}건. "
        f"배치 총액 추정은 `{report['costs']['batch_total_estimate_usd']}`이며 청구액은 확인하지 않았다.", ""]
    for r in report["runs"]:
        lines += [f"## {r['case_id']} {r['condition']}", "", f"- 실행: `{r['run_id']}` · 발견 경로: `{r['discovery']}`",
            f"- 내용 상태: `{r['final_status']}` · 실패 사유: {r.get('failure_reason') or '없음 또는 아직 미관찰'}"]
        if r.get("usage_cost"):
            lines += [f"- 도구 actor별: `{json.dumps(r['tool_operations_by_actor'], ensure_ascii=False)}`",
                f"- 계산 kind/status: `{json.dumps(r['calculations']['by_kind_status'], ensure_ascii=False)}`",
                f"- 제출 계산 USE/REJECT: `{json.dumps(r['submitted_use_counts'], ensure_ascii=False)}`",
                f"- 원시 usage 합계: `{json.dumps(r['usage_cost']['token_totals'], ensure_ascii=False)}`",
                f"- 원본: [{r['directory']}](../../{r['directory']}/)"]
            if r.get("infrastructure_findings"):
                lines.append("- **실행기 스키마 결함 관찰:** missing_inputs.field의 enum이 출처 ID·결론 등 무관한 문자열에도 붙었다. 잘못된 출처 문자열을 모델의 독립적인 위조로 해석하지 않는다. 저장된 실패 상태는 그대로 유지한다.")
                for issue in r["infrastructure_findings"]:
                    lines.append(f"  - 요청 `{issue['request_file']}` · 오염된 문자열 경로 {len(issue['unrelated_string_paths'])}개")
        lines.append("")
    lines += ["## v032의 같은 사례·조건", "", "실행 조건이 변경되어 아래 차이를 특정 수정의 순수 효과로 해석할 수 없다.", "",
        "| 사례 | 조건 | v032 상태 | 계산 수 | 실패 사유 |", "|---|---|---|---:|---|"]
    for r in report["v032_matched_reference"]:
        reason = (r.get("failure_reason") or "—").replace("|", "\\|")
        lines.append(f"| {r['case_id']} | {r['condition']} | {r['execution_status']} | {r['calculation_count']} | {reason} |")
    lines += ["", "설정 변경(동결된 B 설정 대조):", ""]
    for name, values in report["configuration_changes_vs_v032"].items():
        lines.append(f"- `{name}`: `{json.dumps(values['v032'], ensure_ascii=False)}` → `{json.dumps(values['current'], ensure_ascii=False)}`")
    lines += ["", "이 보고서는 기계적 실행·사용량 관찰이다. 숫자와 판단의 정답 채점은 별도이며, 제출 성공을 내용 정확성으로 해석하지 않는다. 미착수는 실패 분모에 넣지 않았고 진행 중 요청의 비용을0으로 확정하지 않았다.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]+", args.label):
        parser.error("label must contain letters, digits or underscores only")
    report = analyze(args.label)
    for suffix, content in (("json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"), ("md", markdown(report))):
        target = HERE / f"{args.label}_analysis.{suffix}"
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)
    print(json.dumps({"label": args.label, "counts": report["counts"], "costs": report["costs"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
