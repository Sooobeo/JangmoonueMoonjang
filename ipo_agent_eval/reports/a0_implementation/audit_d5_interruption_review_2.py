"""Read-only accounting for the deliberately stopped first D5 batch."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from audit_d5_runs_review_2 import PROJECT, HERE, audit, load, sha, evidence_locations
from ipo_eval.cases import resolve_case
from ipo_eval.corpus import Corpus


def main():
    plan_path = HERE / "D5_v031_plan.json"
    rows_path = HERE / "D5_v031_runs.json"
    plan = load(plan_path)
    completed = audit("D5_v031", partial=True)
    directory = PROJECT / "runs/20261113T101554Z_A0_500c648e"
    config = load(directory / "config.json")
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    requests = sorted(directory.glob("[0-9][0-9]_*_request.json"))
    responses = sorted(directory.glob("[0-9][0-9]_*_response.json"))
    model_started = [event for event in events if event["event"] == "model_call_started"]
    model_completed = [event for event in events if event["event"] == "model_call_completed"]
    tools = [event for event in events if event["event"] == "tool_call"]
    issues = []
    if (directory / "summary.json").exists() or (directory / "review.json").exists():
        issues.append("Interrupted run unexpectedly has a final summary or review")
    if len(requests) != len(model_started) or len(responses) != len(model_completed):
        issues.append("Started/completed event counts do not reconcile to original artifacts")
    tokens = {"input_tokens": 0, "output_tokens": 0}
    for path in responses:
        raw = load(path)
        for key in tokens:
            tokens[key] += raw["usage"][key]
    known_cost = round((tokens["input_tokens"] * config["price_input_per_million_usd"] + tokens["output_tokens"] * config["price_output_per_million_usd"]) / 1e6, 6)
    unmatched_requests = [path.name for path in requests if not path.with_name(path.name.replace("_request.json", "_response.json")).exists()]
    recorded = load(directory / "input_hashes.json")
    for filename, expected in recorded.items():
        if filename in plan["source_hashes"] and expected != plan["source_hashes"][filename]:
            issues.append("Interrupted source differs from frozen batch: " + filename)
        if filename.startswith("data/") and sha(PROJECT / filename) != expected:
            issues.append("Interrupted public input changed: " + filename)
    corpus = Corpus(resolve_case(PROJECT, config["case_id"])[0], config["case_id"])
    corpus.verify()
    read_chunks = {}
    for event in tools:
        if event.get("actor") not in {"model", "program_commit"}:
            issues.append("Unexpected interrupted-run tool actor")
        if event["tool"] == "read_source" and "result" in event:
            result = event["result"]
            if result.get("truncated") is not False or len(result["chunks"]) > config["max_read_pages"]:
                issues.append("Interrupted run did not return bounded full pages")
            for chunk in result["chunks"]:
                original = corpus.by_id.get(chunk["chunk_id"])
                if original is None or any(chunk[key] != original[key] for key in ("doc_id", "page", "text")):
                    issues.append("Interrupted run source differs from allowed full page")
                read_chunks[chunk["chunk_id"]] = chunk
    evidence_count = 0
    for event in tools:
        for evidence in evidence_locations(event["arguments"]):
            evidence_count += 1
            chunk = read_chunks.get(evidence["chunk_id"])
            if chunk is None or (chunk["doc_id"], chunk["page"]) != (evidence["doc_id"], evidence["page"]):
                issues.append("Interrupted attempted submission cites an unread source")
    synchronized = {}
    for event in tools:
        if event["tool"] in {"request_information", "escalate"} and "result" in event:
            synchronized[event["tool"]] = event["result"]
            if event["result"].get("external_messages_sent") != 0:
                issues.append("Unexpected external message indication")
    attempted = {(run["case_id"], run["condition"], 1) for run in completed["runs"]}
    attempted.add((config["case_id"], config["condition"], config.get("repeat", 1)))
    not_started = [row for row in plan["planned_runs"] if (row["case_id"], row["condition"], row["repeat"]) not in attempted]
    if len(completed["runs"]) != 3 or len(not_started) != 8:
        issues.append("Stopped-batch inventory differs from 3 terminal / 1 interrupted / 8 not started")
    protected = [plan_path, rows_path]
    protected += [path for run in load(rows_path)["runs"] for path in Path(run["directory"]).rglob("*") if path.is_file()]
    protected += [path for path in directory.rglob("*") if path.is_file()]
    hashes = {path.relative_to(PROJECT).as_posix(): sha(path) for path in sorted(protected)}
    interrupted = {
        "run_id": directory.name, "case_id": config["case_id"], "condition": config["condition"],
        "execution_status": "INTERRUPTED_BY_OPERATOR", "status_source": "separate audit; original run has no summary",
        "reason": "Parent investigator reported stopping verified batch process PID 31608 after a common API-history serialization defect was observed; no terminal outcome was written for this run.",
        "model_calls_started": len(model_started), "responses_saved": len(responses),
        "unanswered_request_files": unmatched_requests, **tokens,
        "known_usage_cost_usd_standard_uncached": known_cost,
        "estimated_total_cost_usd_standard_uncached": None, "usage_unknown": bool(unmatched_requests),
        "tool_calls": len(tools), "actor_counts": dict(Counter(event["actor"] for event in tools)),
        "actual_read_pages": len(read_chunks), "evidence_locations_checked": evidence_count,
        "synchronized_ledger_from_events": synchronized,
        "last_saved_event": events[-1], "last_attempted_submission_errors": [event["error"] for event in tools if event["tool"] == "submit_review" and "error" in event],
        "final_status": None, "review_present": False,
        "snapshot_state_note": "No calculate/REGISTER_BATCH call is recorded; saved final snapshots/extraction/ledger files are absent because process termination bypassed final persistence. Source reads and synchronized requests are retained in events/context.",
        "issues": issues,
    }
    result = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(), "batch": "D5_v031",
        "audit": "Independent review 2: stopped batch accounting and preservation",
        "passed_accounting_and_preservation": completed["passed"] and not issues,
        "development_comparison_complete": False,
        "planned_runs": 12, "terminal_failed_runs": 3, "interrupted_runs": 1, "not_started_runs": 8,
        "completed_run_audit": completed, "interrupted_run": interrupted, "not_started": not_started,
        "all_attempts_known_usage_cost_usd_standard_uncached": round(completed["raw_usage_known_cost_usd"] + known_cost, 6),
        "all_attempts_total_cost_usd_standard_uncached": None,
        "unknown_usage_attempt_count": completed["unknown_usage_run_count"] + bool(unmatched_requests),
        "artifact_hashes": hashes,
        "interpretation": "These attempts remain part of development history. Interrupted and unstarted runs are neither successful outcomes nor zero-cost attempts. A corrected version requires its own predeclared paired batch and cannot replace this history.",
    }
    output = HERE / "D5_v031_interrupted_review_2.json"
    if output.exists():
        raise SystemExit("Refusing to overwrite prior audit")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in {"completed_run_audit", "interrupted_run", "artifact_hashes", "not_started"}}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
