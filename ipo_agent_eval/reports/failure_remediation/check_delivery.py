"""Read-only checks of the final remediation batch and review evidence."""
import argparse
import hashlib
import importlib.util
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_checks(row, plan, directory, require):
    """Audit saved identities, actual tool outputs, usage and read evidence."""
    name = row["case_id"] + "/" + row["condition"]
    def need(condition, message):
        require(condition, name + ": " + message)
    summary = row["summary"]
    need(read(directory / "summary.json") == summary, "result index differs from saved summary")
    need(summary.get("run_id") == directory.name, "run ID differs from directory")
    need(all(summary.get(key) == row[key] for key in ("case_id", "condition", "repeat")), "row and summary identity differ")
    need(summary.get("mode") == "LIVE" and summary.get("model_calls", 0) > 0, "not a real API attempt")
    need(summary.get("config_version") == plan["version"], "version differs")
    hashes = read(directory / "input_hashes.json")
    for relative, digest in plan["source_hashes"].items():
        if relative.startswith(("ipo_eval/", "config/", "prompts/")):
            need(hashes.get(relative) == digest, "actual source hash differs: " + relative)
    need(not any("private" in Path(p.replace("\\", "/")).parts for p in hashes), "private file used as runtime input")
    state = read(directory / "snapshots.json")
    current = state["current_id"]
    records = state["snapshots"][current]["records"]
    need(bool(records) and current != "X_EMPTY", "no registered input")
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    all_calls = [e for e in events if e["event"] == "tool_call"]
    need(len(all_calls) == summary["tool_calls"], "tool attempt count differs from summary")
    need(len([e for e in events if e["event"] == "model_call_started"]) == summary["model_calls"], "model attempt count differs from summary")
    actor = "model" if row["condition"] == "A0" else "program_fixed"
    calls = [e for e in all_calls if e.get("actor") == actor and "error" not in e]
    registered = [e for e in calls if e["tool"] == "calculate" and e["arguments"]["request"]["operation"] == "REGISTER_BATCH"]
    need(any(e.get("result", {}).get("input_snapshot_id") == current for e in registered), "final snapshot was not registered by the required actor")
    evaluate = [e for e in calls if e["tool"] == "calculate" and e["arguments"]["request"]["operation"] == "EVALUATE"
                and e["arguments"]["request"].get("input_snapshot_id") == current]
    sensitivity = [e for e in calls if e["tool"] == "sensitivity" and e["arguments"].get("input_snapshot_id") == current]
    calculations = read(directory / "calculations.json")
    registry = {c["calc_id"]: c for c in calculations}
    need(len(registry) == len(calculations), "duplicate calculation IDs")
    def successful_ids(group):
        ids = set()
        for event in group:
            result = event.get("result", {})
            if result.get("input_snapshot_id") != current:
                continue
            for calc in result.get("calculations", []):
                need(registry.get(calc["calc_id"]) == calc, "saved calculation differs from actual tool result")
                if calc.get("status") == "OK" and calc.get("input_snapshot_id") == current:
                    ids.add(calc["calc_id"])
        return ids
    evaluated_ok, sensitivity_ok = successful_ids(evaluate), successful_ids(sensitivity)
    need(bool(evaluated_ok), "no current successful EVALUATE result by the required actor")
    need(bool(sensitivity_ok), "no current successful sensitivity result by the required actor")
    current_ok = {c["calc_id"] for c in calculations if c["status"] == "OK" and c["input_snapshot_id"] == current}
    review = read(directory / "review.json")
    need(review["input_snapshot_id"] == current, "stale final snapshot")
    commit_actors = {actor, "program_commit"}
    commits = [e for e in all_calls if e["tool"] == "submit_review" and "error" not in e
               and e.get("actor") in commit_actors and e.get("phase") in {"FINALIZING", "REPAIR"}
               and e["arguments"].get("phase") == "COMMIT" and e["arguments"].get("input_snapshot_id") == current
               and e.get("result", {}).get("input_snapshot_id") == current
               and e["result"].get("execution_status") == "SUBMITTED" and e["result"].get("submission_id")]
    need(len(commits) == 1, "exactly one accepted final COMMIT event required")
    need(any(e["event"] == "state_transition" and e.get("to") == "SUBMITTED" for e in events), "SUBMITTED transition missing")
    if commits:
        need(commits[0]["result"].get("content_status") == summary.get("final_status"), "accepted content status differs from summary")
    used = {c["calc_id"] for c in review["calculation_uses"] if c["use"] == "USE"}
    need(bool(used) and used <= current_ok, "missing or invalid calculation use")
    need(bool(used & evaluated_ok) and bool(used & sensitivity_ok), "final review does not use current evaluation and sensitivity results")
    for use in review["calculation_uses"]:
        if use["use"] == "USE" and use["calc_id"] in registry:
            try:
                value, actual = Decimal(str(use["stated_value"])), Decimal(str(registry[use["calc_id"]]["result"]))
                need(value.is_finite() and actual.is_finite() and value == actual, "stated calculation value differs")
            except InvalidOperation:
                need(False, "invalid stated calculation Decimal")
    packet = read(directory / "source_packet.json")
    case = packet["metadata"]["case"]
    need(case["case_id"] == row["case_id"], "read packet case identity differs")
    case_selection = read(directory / "case_selection.json")
    need(case_selection["registration"]["case_id"] == row["case_id"], "case registration identity differs")
    actual_reads = {chunk["chunk_id"]: chunk for e in all_calls if e["tool"] == "read_source" and "error" not in e
                    for chunk in e["result"]["chunks"]}
    packet_reads = {chunk["chunk_id"]: chunk for chunk in packet["sources"]}
    need(actual_reads == packet_reads and bool(actual_reads), "saved read packet differs from actual successful reads")
    need(set(read(directory / "retrieval_history.json")["read_chunks"]) == set(actual_reads), "read history identity differs")
    for chunk in actual_reads.values():
        need(chunk["doc_id"] in case["allowed_doc_ids"] and chunk.get("case_id") == row["case_id"] and chunk.get("cutoff_status") == "BEFORE", "read page outside registered public case")
    def evidence_check(value):
        if isinstance(value, dict):
            if {"doc_id", "chunk_id", "page", "claim_id", "locator"} <= value.keys():
                chunk = actual_reads.get(value["chunk_id"], {})
                need(chunk.get("doc_id") == value["doc_id"] and type(value["page"]) is int and chunk.get("page") == value["page"], "citation was not actually read at the stated coordinates")
            for child in value.values():
                evidence_check(child)
        elif isinstance(value, list):
            for child in value:
                evidence_check(child)
    evidence_check([records, calculations, review])
    ledger = read(directory / "request_ledger.json")
    for group, key in (("requests", "request_id"), ("escalations", "escalation_id")):
        saved = {item[key]: item for item in ledger[group]}
        final = {item[key]: item for item in review[group]}
        need(len(final) == len(review[group]), "duplicate final ledger IDs")
        need(all(saved.get(ident) == item for ident, item in final.items()), "final ledger records differ from saved versions")
        need(all(final.get(ident) == item for ident, item in saved.items() if item["resolution_status"] == "OPEN"), "OPEN ledger item forgotten")
        sync_tool = "request_information" if group == "requests" else "escalate"
        sync = [e for e in all_calls if e["tool"] == sync_tool and e.get("actor") == "program_commit"
                and "error" not in e and e.get("phase") in {"FINALIZING", "REPAIR"}]
        need(len(sync) == 1, "final ledger synchronization missing or repeated: " + group)
        if commits:
            need(commits[0]["result"].get(group) == ledger[group], "accepted COMMIT ledger differs: " + group)
    requests = list(directory.glob("[0-9][0-9]_*_request.json"))
    need(len(requests) == summary["model_calls"], "raw request count differs from attempted model calls")
    known_input = known_output = unknown = 0
    for path in requests:
        response, error = path.with_name(path.name.replace("_request.json", "_response.json")), path.with_name(path.name.replace("_request.json", "_error.json"))
        need(response.exists() != error.exists(), "attempt lacks exactly one response or error artifact")
        usage = read(response).get("usage") if response.exists() else None
        if isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens", "output_tokens")):
            known_input += usage["input_tokens"]
            known_output += usage["output_tokens"]
        else:
            unknown += 1
    need((known_input, known_output) == (summary["input_tokens"], summary["output_tokens"]), "known raw usage differs from summary")
    need(bool(unknown) == summary["usage_unknown"], "unknown-usage flag differs from raw attempts")
    hold = summary["unknown_usage_reservation"]
    need(len(hold["attempts"]) == unknown, "unknown attempts not fully reserved")
    if unknown:
        need(summary["estimated_cost_usd_standard_uncached"] is None, "unknown usage treated as a known total")
        need(hold["input_tokens_estimated"] > 0 and hold["output_tokens_max"] > 0 and hold["cost_ceiling_usd"] > 0, "unknown usage reserved as zero")
    config = read(ROOT / plan["source_snapshot"] / "config" / (row["condition"] + ".json"))
    standard = (known_input * config["price_input_per_million_usd"] + known_output * config["price_output_per_million_usd"]) / 1e6
    known_ceiling = (known_input * config["price_input_per_million_usd"] * 1.25 + known_output * config["price_output_per_million_usd"]) / 1e6
    need(summary["known_usage_cost_usd_standard_uncached"] == round(standard, 6), "known cost differs from raw usage and frozen rates")
    need(summary["cost_ceiling_usd"] == round(known_ceiling, 6), "known cost ceiling differs from frozen rates")
    need(abs(summary["accounted_cost_ceiling_usd"] - round(known_ceiling + hold["cost_ceiling_usd"], 6)) <= 0.0000011,
         "accounted cost omits known or unknown reserved usage")
    if not unknown:
        need(summary["estimated_cost_usd_standard_uncached"] == round(standard, 6), "known total cost differs from usage")
    limits = [(summary["model_calls"], config["max_model_calls"]), (summary["tool_calls"], config["max_tool_calls"]),
        (known_input + hold["input_tokens_estimated"], config["input_tokens_target_max"]),
        (known_output + hold["output_tokens_max"], config["output_tokens_max"]),
        (summary["accounted_cost_ceiling_usd"], config["max_run_usd"]), (summary["elapsed_seconds"], config["wall_seconds_max"])]
    need(all(0 <= used <= maximum for used, maximum in limits), "actual plus unknown-reserved usage exceeds a common cap")
    return {"case_id": row["case_id"], "condition": row["condition"], "status": summary["execution_status"],
            "run_id": directory.name, "registered_records": len(records), "evaluations": len(evaluate),
            "sensitivity": len(sensitivity), "evaluation_ok": len(evaluated_ok), "sensitivity_ok": len(sensitivity_ok),
            "read_pages": len(actual_reads), "current_ok_calculations": len(current_ok), "unknown_attempts": unknown}


def check(label, require_reviews=True):
    failures, details = [], []
    def require(condition, description):
        if not condition:
            failures.append(description)
    plan = read(HERE / f"{label}_plan.json")
    results = read(HERE / f"{label}_runs.json")
    require(results["complete"], "Final batch is incomplete")
    expected = {(r["case_id"], r["condition"], r["repeat"]) for r in plan["planned_runs"]}
    observed = [(r["case_id"], r["condition"], r["repeat"]) for r in results["runs"]]
    cases = {row[0] for row in expected}
    require(len(cases) == 6 and expected == {(case, condition, 1) for case in cases for condition in ("B", "A0")}
            and len(plan["planned_runs"]) == len(observed) == 12 and set(observed) == expected, "Expected exactly six fresh B/A0 pairs")
    require(bool(plan["source_hashes"]), "Frozen source manifest is empty")
    frozen = ROOT / plan["source_snapshot"]
    for relative, digest in plan["source_hashes"].items():
        require((frozen / relative).is_file() and sha(frozen / relative) == digest, f"Frozen source changed: {relative}")
        require((ROOT / relative).is_file() and sha(ROOT / relative) == digest, f"Working source differs from final batch: {relative}")
    directories, run_ids = set(), set()
    for row in results["runs"]:
        name = row["case_id"] + "/" + row["condition"]
        summary = row["summary"]
        require(summary["execution_status"] == "SUBMITTED", name + ": no accepted submission")
        require(bool(row.get("directory")), name + ": run directory missing")
        if not row.get("directory"):
            continue
        directory = Path(row["directory"]).resolve()
        require(directory not in directories, name + ": run directory reused")
        require(summary.get("run_id") not in run_ids, name + ": run ID reused")
        directories.add(directory)
        run_ids.add(summary.get("run_id"))
        require(directory.is_relative_to((ROOT / "runs").resolve()), name + ": run outside audit directory")
        if not directory.is_relative_to((ROOT / "runs").resolve()):
            continue
        try:
            details.append(run_checks(row, plan, directory, require))
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            failures.append(name + ": missing or malformed required artifact: " + type(exc).__name__ + ": " + str(exc))
    spec = importlib.util.spec_from_file_location("preserve_baseline", HERE / "preserve_baseline.py")
    preservation = importlib.util.module_from_spec(spec)
    previous_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(preservation)
    finally:
        sys.dont_write_bytecode = previous_bytecode
    preserved = preservation.verify()
    require(preserved["passed"], "Baseline evidence preservation failed")
    intermediate = {"passed": False, "entry_count": 0, "violations": []}
    missing_manifest = False
    for manifest_name in ("intermediate_attempts_manifest.json", "compatibility_probe_preservation.json",
                          "FIX_v042_interrupted_preservation.json"):
        try:
            prior_attempts = read(HERE / manifest_name)
            intermediate["entry_count"] += len(prior_attempts["entries"])
            require(bool(prior_attempts["entries"]), "Prior diagnostic/stopped-attempt manifest is empty: " + manifest_name)
            if not prior_attempts["entries"]:
                missing_manifest = True
            for entry in prior_attempts["entries"]:
                path = (ROOT / entry["path"]).resolve()
                if not path.is_relative_to(ROOT.resolve()) or not path.is_file() or sha(path) != entry["sha256"]:
                    intermediate["violations"].append(entry["path"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            missing_manifest = True
            failures.append("Prior diagnostic/stopped-attempt manifest missing or malformed: " + manifest_name + ": " + type(exc).__name__)
    intermediate["passed"] = intermediate["entry_count"] > 0 and not missing_manifest and not intermediate["violations"]
    require(intermediate["passed"], "Diagnostic/stopped-attempt evidence preservation failed")
    if require_reviews:
        manifest = read(HERE / "review_manifest.json")
        require(manifest["acceptance_complete"], "Review acceptance is incomplete")
        require(set(manifest["stages"]) == {"diagnosis", "implementation", "execution", "overall"}, "Four exact review stages required")
        require(not manifest.get("open_required_findings"), "Required review findings remain open")
        for stage, value in manifest["stages"].items():
            reviews = value["reviews"]
            require(len(reviews) == 3 and {r.get("ordinal") for r in reviews} == {1, 2, 3}
                    and all(r.get("review_complete") for r in reviews), stage + ": three completed reviews required")
            require(all(r.get("artifacts") and any(a.get("file") and a.get("sha256") for a in r["artifacts"])
                        for r in reviews), stage + ": completed reviews require actual hashed reports")
        def verify_links(value):
            if isinstance(value, dict):
                if "file" in value and "sha256" in value:
                    path = ROOT / value["file"]
                    require(path.is_file() and sha(path) == value["sha256"], "Review evidence hash differs: " + value["file"])
                for child in value.values():
                    verify_links(child)
            elif isinstance(value, list):
                for child in value:
                    verify_links(child)
        verify_links(manifest)
    return {"label": label, "passed": not failures, "review_checks_required": require_reviews,
            "failures": failures, "runs": details, "preservation": preserved, "intermediate_preservation": intermediate,
            "scope": "Execution/contract/preservation acceptance only; semantic correctness is separately reviewed."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="FIX_v043")
    parser.add_argument("--skip-review-checks", action="store_true")
    args = parser.parse_args()
    result = check(args.label, not args.skip_review_checks)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
