"""Read-only artifact inspection; manual semantic judgments supplied separately.

Writes reports only. Never imports a model client or modifies source/run/gold files.
"""
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def inspect_run(row):
    r = Path(row["directory"])
    summary = row["summary"]
    events = [json.loads(x) for x in (r / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    tools = []
    read_locations = set()
    for line, event in enumerate(events, 1):
        if event["event"] != "tool_call":
            continue
        args = event.get("arguments", {})
        tools.append({"line": line, "actor": event.get("actor"), "tool": event["tool"],
                      "operation": args.get("request", {}).get("operation"),
                      "phase": event.get("phase")})
        if event["tool"] == "read_source":
            for chunk in event.get("result", {}).get("chunks", []):
                read_locations.add((chunk["doc_id"], chunk["chunk_id"], chunk["page"]))
    submitted = summary["execution_status"] == "SUBMITTED"
    result = {"case_id": row["case_id"], "condition": row["condition"],
              "run_id": summary["run_id"], "run_directory": str(r.relative_to(ROOT)).replace("\\", "/"),
              "execution_status": summary["execution_status"], "final_status": summary.get("final_status"),
              "summary": summary, "actual_model_tools": [t for t in tools if t["actor"] == "model"],
              "program_commit_tools": [t for t in tools if t["actor"] == "program_commit"],
              "model_operation_counts": dict(Counter(t["operation"] or t["tool"] for t in tools if t["actor"] == "model")),
              "tool_errors": [{"line": i, **e} for i, e in enumerate(events, 1) if e["event"] in {"tool_error", "tool_validation_error"}],
              "finalization_transitions": [{"line": i, **e} for i, e in enumerate(events, 1) if e["event"] == "state_transition" and e.get("to") == "FINALIZING"],
              "read_pages": sorted({x[2] for x in read_locations}),
              "source_appropriateness": {"scope": "Valid final judgments[].facts only; not all natural-language conclusions, and not a truth-accuracy score.",
                                         "observed": submitted, "submitted_claims": 0, "read_location_valid_count": 0,
                                         "fully_supported_count": 0, "qualified_count": 0, "unsupported_count": 0,
                                         "support_rate": None, "claims": []}}
    saved_snapshots = read(r / "snapshots.json") if (r / "snapshots.json").exists() else {}
    saved_calculations = read(r / "calculations.json") if (r / "calculations.json").exists() else []
    current_id = saved_snapshots.get("current_id", "X_EMPTY")
    records = saved_snapshots.get("snapshots", {}).get(current_id, {}).get("records", {})
    result["runtime_activity"] = {
        "current_snapshot_id": current_id, "registered_record_count": len(records),
        "registered": bool(records),
        "evaluate_model_calls": sum(t["operation"] == "EVALUATE" for t in result["actual_model_tools"]),
        "sensitivity_model_calls": sum(t["tool"] == "sensitivity" for t in result["actual_model_tools"]),
        "calculation_count": len(saved_calculations),
        "calculation_status_counts": dict(Counter(c["status"] for c in saved_calculations)),
        "valid_final": submitted,
    }
    final_calcs = [c for c in saved_calculations if c["input_snapshot_id"] == current_id]
    result["core_numeric_availability"] = {
        "scope": "Mechanical availability in the last registered snapshot; semantic correctness is graded separately.",
        "share_sum": [{"calc_id": c["calc_id"], "status": c["status"], "result": c.get("result"), "partial_sum": c.get("partial_sum")} for c in final_calcs if c["id"] == "share_sum"],
        "price_results": [{"calc_id": c["calc_id"], "status": c["status"], "result": c.get("result")} for c in final_calcs if c["id"] in {"price_from_reported_equity", "price_from_displayed_per", "price_from_recomputed_peer_mean"}],
        "sensitivity_status_counts": dict(Counter(c["status"] for c in final_calcs if c["id"].startswith("sensitivity_"))),
        "price_any_ok": any(c["status"] == "OK" for c in final_calcs if c["id"] in {"price_from_reported_equity", "price_from_displayed_per", "price_from_recomputed_peer_mean"}),
        "sensitivity_baseline_ok": any(c["id"] == "sensitivity_baseline" and c["status"] == "OK" for c in final_calcs),
        "sensitivity_alternative_ok": any(c["id"].startswith("sensitivity_") and c["id"] != "sensitivity_baseline" and c["status"] == "OK" for c in final_calcs),
    }
    if not submitted:
        result["failure_observations"] = [{"line": i, **e} for i, e in enumerate(events, 1) if e["event"] in {"run_stopped", "model_call_completed"}][-2:]
        result["facts"] = {f"F{i}": {"score": 0, "reason": "Attempted execution failed without a valid mandatory submission (protocol 11.1)."} for i in range(1, 6)}
        result["calculations"] = {f"K{i}": {"score": 0, "reason": "No valid final mandatory submission; partial response is failure evidence only."} for i in range(1, 4)}
        result["judgments"] = {f"J{i}": {"score": 0, "reason": "No valid final mandatory submission."} for i in range(1, 5)}
        result["flags"] = {"material_error": None, "false_completion": None, "unnecessary_hold": None}
        return result
    review = read(r / "review.json")
    extraction = read(r / "extraction.json")
    calculations = read(r / "calculations.json")
    snap = review["input_snapshot_id"]
    by_id = {c["calc_id"]: c for c in calculations}
    checks = []
    for use in review["calculation_uses"]:
        calc = by_id.get(use["calc_id"])
        exact = None
        if use["use"] == "USE" and calc and calc.get("result") is not None:
            exact = Decimal(use["stated_value"]) == Decimal(calc["result"])
        checks.append({**use, "calculation_exists": calc is not None,
                       "same_final_snapshot": bool(calc and calc["input_snapshot_id"] == snap),
                       "calculation_status": calc.get("status") if calc else None,
                       "exact_stated_value": exact})
    result.update({"input_snapshot_id": snap,
                   "registered_record_count": len(read(r / "snapshots.json")["snapshots"][snap]["records"]),
                   "calculation_status_counts_all_snapshots": dict(Counter(c["status"] for c in calculations)),
                   "current_calculations": [{k: c.get(k) for k in ["calc_id", "id", "entity_id", "status", "result", "partial_sum", "missing_inputs", "input_fact_ids"]} for c in calculations if c["input_snapshot_id"] == snap],
                   "calculation_use_checks": checks,
                   "requests": review.get("requests", []), "escalations": review.get("escalations", []),
                   "missing_inputs": review.get("missing_inputs", [])})
    for judgment in review["judgments"]:
        for claim in judgment["facts"]:
            valid = all((ev["doc_id"], ev["chunk_id"], ev["page"]) in read_locations for ev in claim["evidence"])
            result["source_appropriateness"]["claims"].append({"claim_id": claim["claim_id"], "text": claim["text"], "status": "PENDING_SEMANTIC_REVIEW", "read_location_valid": valid, "evidence": claim["evidence"]})
    source = result["source_appropriateness"]
    source["submitted_claims"] = len(source["claims"])
    source["read_location_valid_count"] = sum(c["read_location_valid"] for c in source["claims"])
    return result


def mark_sources(result, qualified=None, unsupported=None):
    qualified, unsupported = qualified or {}, unsupported or {}
    s = result["source_appropriateness"]
    for c in s["claims"]:
        cid = c["claim_id"]
        c["status"] = "UNSUPPORTED" if cid in unsupported else "QUALIFIED" if cid in qualified else "FULL"
        c["reason"] = unsupported.get(cid) or qualified.get(cid) or "Cited corpus text supports the stated claim; location independently matches an actual read_source result."
    counts = Counter(c["status"] for c in s["claims"])
    s.update(fully_supported_count=counts["FULL"], qualified_count=counts["QUALIFIED"], unsupported_count=counts["UNSUPPORTED"],
             support_rate=counts["FULL"] / s["submitted_claims"] if s["submitted_claims"] else None)


def metrics(run):
    run["metrics"] = {
        "facts": {"correct": sum(x["score"] for x in run["facts"].values()), "scorable": 5},
        "calculations": {"correct": sum(x["score"] for x in run["calculations"].values()), "scorable": 3},
        "methodology": {"full_credit_domains": sum(x["score"] == 2 for x in run["judgments"].values()), "domains": 4},
    }


def write_report(name, data, narrative):
    (ROOT / "reports/failure_remediation" / (name + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "reports/failure_remediation" / (name + ".md")).write_text(narrative, encoding="utf-8")
