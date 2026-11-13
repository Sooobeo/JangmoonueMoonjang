"""Independent read-only audit of a completed D5 development batch.

No API calls, credentials, experiment mutation or scoring decisions are made.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT))
from ipo_eval.cases import resolve_case
from ipo_eval.corpus import Corpus
from ipo_eval.agent_loop import _format_only, output_json
from ipo_eval.provenance import SnapshotStore
from ipo_eval.schemas_v2 import REVIEW_V2
from ipo_eval.validation_v2 import final_status, validate_review
from verify_preservation import verify as preservation_check


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence_locations(value):
    if isinstance(value, dict):
        if {"doc_id", "chunk_id", "page", "claim_id", "locator"}.issubset(value):
            yield value
        for child in value.values():
            yield from evidence_locations(child)
    elif isinstance(value, list):
        for child in value:
            yield from evidence_locations(child)


def audit_run(row, plan):
    directory = Path(row["directory"])
    if not directory.is_absolute():
        directory = PROJECT / directory
    summary = load(directory / "summary.json")
    config = load(directory / "config.json")
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    issues = []
    if summary != row["summary"] or summary.get("mode") != "LIVE":
        issues.append("Batch terminal outcome differs from the original live-run summary")
    frozen_config = load(PROJECT / plan["source_snapshot"] / "config" / (summary["condition"] + ".json"))
    if any(config.get(key) != value for key, value in frozen_config.items()) or set(config) - set(frozen_config) - {"case_id"}:
        issues.append("Run configuration differs from its frozen condition template")
    public_directory, _ = resolve_case(PROJECT, summary["case_id"])
    corpus = Corpus(public_directory, summary["case_id"])
    corpus.verify()
    recorded_hashes = load(directory / "input_hashes.json")
    expected_run_hash_keys = {filename for filename in plan["source_hashes"] if filename.startswith(("ipo_eval/", "config/", "prompts/"))}
    if not expected_run_hash_keys.issubset(recorded_hashes):
        issues.append("Run input-hash manifest omits frozen source/config/prompt files")
    for filename, expected in plan["source_hashes"].items():
        if filename in recorded_hashes and recorded_hashes[filename] != expected:
            issues.append("Run source hash differs from frozen batch: " + filename)
    for filename, expected in recorded_hashes.items():
        if filename.startswith("data/") and sha(PROJECT / filename) != expected:
            issues.append("Public input changed after run: " + filename)
    raw_requests = sorted(directory.glob("[0-9][0-9]_*_request.json"))
    raw_responses = sorted(directory.glob("[0-9][0-9]_*_response.json"))
    input_total = output_total = 0
    missing_usage_responses = 0
    model_function_calls = {}
    repair_candidates = []
    response_models = []
    for path in raw_requests:
        request = load(path)
        if request["model"] != config["model"] or request["reasoning"]["effort"] != config["reasoning_effort"]:
            issues.append("Request model/effort differs from frozen configuration: " + path.name)
        if request.get("store") is not False:
            issues.append("Unexpected server-side storage mode: " + path.name)
        if "tools" in request and request.get("parallel_tool_calls") is not False:
            issues.append("Parallel tool calls enabled: " + path.name)
    for path in raw_responses:
        response = load(path)
        if "_format_repair_response.json" in path.name and response.get("status") == "completed":
            try:
                repair_candidates.append(output_json(response))
            except RuntimeError:
                pass
        response_models.append(response.get("model"))
        usage = response.get("usage")
        if not isinstance(usage, dict) or any(type(usage.get(key)) is not int for key in ("input_tokens", "output_tokens")):
            missing_usage_responses += 1
        else:
            input_total += usage["input_tokens"]
            output_total += usage["output_tokens"]
        for item in response.get("output", []):
            if item.get("type") == "function_call":
                model_function_calls[item.get("call_id")] = item
    if input_total != summary["input_tokens"] or output_total != summary["output_tokens"]:
        issues.append("Summary token totals differ from original response usage")
    if response_models != summary["returned_models"]:
        issues.append("Returned-model inventory differs from original responses")
    if len(raw_responses) > summary["model_calls"] or len(raw_requests) < summary["model_calls"]:
        issues.append("Model request/response file count is incompatible with summary")
    unknown_expected = missing_usage_responses > 0 or len(raw_responses) < summary["model_calls"]
    if unknown_expected and not summary["usage_unknown"]:
        issues.append("Missing request usage is not flagged unknown")
    cost = round((input_total * config["price_input_per_million_usd"] + output_total * config["price_output_per_million_usd"]) / 1000000, 6)
    if summary["known_usage_cost_usd_standard_uncached"] != cost:
        issues.append("Known-usage cost does not reconcile to raw usage")
    if summary["usage_unknown"]:
        if summary["estimated_cost_usd_standard_uncached"] is not None:
            issues.append("Unknown total cost is reported as a numeric total")
    elif summary["estimated_cost_usd_standard_uncached"] != cost:
        issues.append("Known total cost differs from calculated usage")
    tool_events = [event for event in events if event["event"] == "tool_call"]
    if len(tool_events) != summary["tool_calls"]:
        issues.append("Actual tool event count differs from summary")
    allowed_actors = {"program_fixed", "program_commit"} if summary["condition"] == "B" else {"model", "program_commit"}
    if any(event.get("actor") not in allowed_actors for event in tool_events):
        issues.append("Tool actor mislabels policy-selected actions")
    if any(event.get("result", {}).get("external_messages_sent") != 0 for event in tool_events
           if event["tool"] in {"request_information", "escalate"} and "result" in event):
        issues.append("Information-request ledger indicates an external message")
    for event in tool_events:
        if event.get("actor") == "model":
            original_call = model_function_calls.get(event["call_id"])
            is_repair = event["call_id"].endswith("_format_repair")
            if original_call is None and is_repair:
                original_call = model_function_calls.get(event["call_id"].removesuffix("_format_repair"))
                try:
                    if original_call is None or event["arguments"] not in repair_candidates:
                        raise RuntimeError("Unlinked repair candidate")
                    _format_only(json.loads(original_call["arguments"]), event["arguments"])
                except RuntimeError:
                    issues.append("Model actor repair does not match a preserved format-only model response")
            if original_call is None or original_call["name"] != event["tool"] or (not is_repair and json.loads(original_call["arguments"]) != event["arguments"]):
                issues.append("Model actor tool call does not match a saved model-selected function call")
    envelope_count = sum(event["usage_delta"]["tool_calls"] for event in events if event["event"] == "tool_envelope")
    if envelope_count != len(tool_events):
        issues.append("Tool envelope usage deltas do not reconcile to counted tool attempts")
    if summary["model_calls"] > config["max_model_calls"] or summary["tool_calls"] > config["max_tool_calls"] or summary["format_repairs"] > config["max_format_repairs"]:
        issues.append("Actual attempt count exceeds the frozen call/repair cap")
    successful_reads = [event for event in tool_events if event["tool"] == "read_source" and "result" in event]
    read_chunks = {}
    for event in successful_reads:
        result = event["result"]
        if result.get("truncated") is not False:
            issues.append("Source read was truncated or missing its full-page marker")
        if len(result["chunks"]) > config["max_read_pages"]:
            issues.append("Source read exceeds page limit")
        for chunk in result["chunks"]:
            original = corpus.by_id.get(chunk["chunk_id"])
            if original is None or any(chunk[key] != original[key] for key in ("doc_id", "page", "text")):
                issues.append("Returned source is outside the corpus or differs from the full page")
            read_chunks[chunk["chunk_id"]] = chunk
    retrieval = load(directory / "retrieval_history.json")
    packet = load(directory / "source_packet.json")
    if set(read_chunks) != set(retrieval["read_chunks"]) or set(read_chunks) != {chunk["chunk_id"] for chunk in packet["sources"]}:
        issues.append("Read history and saved source packet disagree")
    referenced_locations = 0
    for filename in ("extraction.json", "calculations.json", "request_ledger.json", "review.json"):
        path = directory / filename
        if not path.exists():
            continue
        for evidence in evidence_locations(load(path)):
            referenced_locations += 1
            chunk = read_chunks.get(evidence["chunk_id"])
            if type(evidence["page"]) is not int or chunk is None or (chunk["doc_id"], chunk["page"]) != (evidence["doc_id"], evidence["page"]):
                issues.append("Saved evidence was not actually read: " + filename)
    snapshots = load(directory / "snapshots.json")
    store = SnapshotStore(read_chunks)
    store.current_id = snapshots["current_id"]
    store._snapshots = snapshots["snapshots"]
    if store.logical(store.current_id) != load(directory / "extraction.json"):
        issues.append("Saved logical extraction cannot be reproduced from immutable snapshots")
    calculations = load(directory / "calculations.json")
    registry = {calc["calc_id"]: calc for calc in calculations}
    if len(registry) != len(calculations):
        issues.append("Duplicate saved calculation IDs")
    for calc in calculations:
        if calc["input_snapshot_id"] not in snapshots["snapshots"]:
            issues.append("Calculation references an unknown snapshot")
    ledger = load(directory / "request_ledger.json")
    replay = {"requests": {}, "escalations": {}}
    for change in ledger["history"]:
        prior = replay[change["group"]].get(change["id"])
        if prior != change["previous"]:
            issues.append("Ledger history does not connect to its prior version")
        replay[change["group"]][change["id"]] = change["current"]
    if any(list(replay[group].values()) != ledger[group] for group in replay):
        issues.append("Ledger final state differs from replayed immutable history")
    if summary["execution_status"] == "SUBMITTED":
        report = load(directory / "review.json")
        review = {key: report[key] for key in REVIEW_V2["properties"]}
        issues.extend(validate_review(review, store, read_chunks, corpus.case["allowed_doc_ids"], registry))
        if final_status(review) != summary["final_status"]:
            issues.append("Submitted content status differs from complete request ledger")
        if any(review[group] != ledger[group] for group in replay):
            issues.append("Submitted review omits ledger state")
        if summary["cost_ceiling_usd"] > config["max_run_usd"] or summary["elapsed_seconds"] > config["wall_seconds_max"]:
            issues.append("Over-budget run was presented as submitted")
    else:
        if summary.get("final_status") is not None or (directory / "review.json").exists():
            issues.append("Failed/unsubmitted run has a final review or non-null content status")
        if not summary.get("failure_reason"):
            issues.append("Unsubmitted live run lacks a failure reason")
    return {"run_id": summary["run_id"], "case_id": summary["case_id"], "condition": summary["condition"],
            "execution_status": summary["execution_status"], "failure_reason": summary.get("failure_reason"),
            "model_calls": summary["model_calls"], "tool_calls": summary["tool_calls"],
            "input_tokens": input_total, "output_tokens": output_total, "known_cost_usd": cost,
            "usage_unknown": summary["usage_unknown"], "actual_read_pages": len(read_chunks),
            "evidence_locations_checked": referenced_locations, "snapshot_count": len(snapshots["snapshots"]),
            "calculation_count": len(calculations), "ledger_versions": len(ledger["history"]),
            "actor_counts": dict(Counter(event["actor"] for event in tool_events)),
            "source_hashes_match_frozen_batch": not any("hash" in issue for issue in issues),
            "passed": not issues, "issues": issues}


def audit(batch="D5_v031", partial=False):
    plan = load(HERE / f"{batch}_plan.json")
    results = load(HERE / f"{batch}_runs.json")
    rows = results if isinstance(results, list) else results["runs"]
    planned = {(item["case_id"], item["condition"], item["repeat"]) for item in plan["planned_runs"]}
    observed = {(item["summary"]["case_id"], item["summary"]["condition"], item["summary"].get("repeat", 1)) for item in rows}
    issues = []
    if not partial and isinstance(results, dict) and results.get("complete") is not True:
        issues.append("Batch record does not declare completion")
    if len(rows) != len(observed) or not observed.issubset(planned) or (not partial and observed != planned):
        issues.append("Batch outcomes do not cover planned pairs exactly once")
    frozen = PROJECT / plan["source_snapshot"]
    for name, expected in plan["source_hashes"].items():
        if sha(frozen / name) != expected:
            issues.append("Frozen source snapshot changed: " + name)
    for name, expected in plan["new_gold_hashes_before_answers"].items():
        if sha(PROJECT / name) != expected:
            issues.append("Pre-answer gold changed: " + name)
    if sha(HERE / "case_roster.json") != plan["roster_sha256"]:
        issues.append("Pre-answer case assignment changed")
    stopped_audit = HERE / "D5_v031_interrupted_review_2.json"
    if batch != "D5_v031" and stopped_audit.exists():
        for filename, expected in load(stopped_audit)["artifact_hashes"].items():
            if sha(PROJECT / filename) != expected:
                issues.append("Earlier stopped-batch artifact changed: " + filename)
    preservation = preservation_check()
    if not preservation["passed"]:
        issues.append("Original evidence preservation failed")
    audited = [audit_run(row, plan) for row in rows]
    artifacts = [HERE / f"{batch}_plan.json", HERE / f"{batch}_runs.json"]
    for row in rows:
        directory = Path(row["directory"])
        if not directory.is_absolute():
            directory = PROJECT / directory
        artifacts.extend(path for path in directory.rglob("*") if path.is_file())
    artifact_hashes = {path.relative_to(PROJECT).as_posix(): sha(path) for path in sorted(artifacts)} if not partial else {}
    return {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "batch": batch, "review": "D5 independent review 2",
            "partial": partial, "planned_count": len(planned), "observed_count": len(rows),
            "passed": not issues and all(row["passed"] for row in audited), "issues": issues,
            "outcome_counts": dict(Counter(row["execution_status"] for row in audited)),
            "raw_usage_known_cost_usd": round(sum(row["known_cost_usd"] for row in audited), 6),
            "unknown_usage_run_count": sum(row["usage_unknown"] for row in audited),
            "runs": audited, "original_preservation": preservation,
            "frozen_batch_artifact_count": len(artifact_hashes), "batch_artifact_hashes": artifact_hashes,
            "limits": ["Checks records, source isolation, arithmetic references and accounting; does not grade financial judgment.",
                       "Known-usage costs are the configured uncached estimate, not an invoice.",
                       "Connectivity smoke is separate from the planned development batch."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", default="D5_v031")
    parser.add_argument("--partial", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.batch, args.partial)
    if args.output:
        destination = args.output.resolve()
        if not destination.is_relative_to(HERE) or destination.exists():
            parser.error("Choose a new output path within this report directory")
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"runs", "original_preservation", "batch_artifact_hashes"}}, ensure_ascii=True, indent=2))
    if not report["passed"]:
        print(json.dumps([{"run_id": row["run_id"], "issues": row["issues"]} for row in report["runs"] if row["issues"]], ensure_ascii=True))
    raise SystemExit(0 if report["passed"] else 1)
