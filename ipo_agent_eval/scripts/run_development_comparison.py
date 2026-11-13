"""Predeclare one B/A0 pair per registered development case; never retry answers."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ipo_eval.runner_v2 import execute_v2
from ipo_eval.runtime_v2 import write_json


def source_violations(root, expected):
    """Check the declared source again immediately before each live run."""
    changed = []
    for relative, digest in expected.items():
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            changed.append(relative)
    return sorted(changed)


def not_started(item, status, reason, changed=None):
    """A planned but unexecuted item is not a failed model answer."""
    summary = {"execution_status": status, "final_status": None, "actual_model_answer": False,
               "failure_reason": reason, "model_calls": 0, "tool_calls": 0,
               "input_tokens": 0, "output_tokens": 0, "usage_unknown": False,
               "estimated_cost_usd_standard_uncached": 0.0}
    if changed:
        summary["source_violations"] = changed
    return {**item, "directory": None, "summary": summary}


def launch_precondition(root, stop_path, expected, item):
    if stop_path.exists():
        return not_started(item, "NOT_STARTED_STOP_REQUESTED", "STOP_REQUESTED_BEFORE_API")
    changed = source_violations(root, expected)
    if changed:
        return not_started(item, "NOT_STARTED_SOURCE_CHANGED", "FROZEN_SOURCE_HASH_MISMATCH", changed)
    # Hash verification can take time; honor a stop created during that check.
    if stop_path.exists():
        return not_started(item, "NOT_STARTED_STOP_REQUESTED", "STOP_REQUESTED_BEFORE_API")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--label", default="D5_v031")
    parser.add_argument("--report-dir", choices=["a0_implementation", "failure_remediation"], default="a0_implementation")
    parser.add_argument("--case", action="append", dest="case_ids", help="Declared diagnostic subset; never select after observing its answers")
    parser.add_argument("--workers", type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    if not args.label.replace("_", "").isalnum():
        parser.error("label must contain only letters, digits and underscores")
    report_dir = ROOT / "reports" / args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    plan_path = report_dir / (args.label + "_plan.json")
    results_path = report_dir / (args.label + "_runs.json")
    if plan_path.exists() or results_path.exists():
        raise SystemExit("Batch already exists; do not silently repeat model answers")
    configs = {c: json.loads((ROOT / f"config/{c}.json").read_text(encoding="utf-8")) for c in ("B", "A0")}
    assert {k: v for k, v in configs["B"].items() if k != "condition"} == {k: v for k, v in configs["A0"].items() if k != "condition"}
    roster_path = ROOT / "reports/a0_implementation/case_roster.json"
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "config/cases.json").read_text(encoding="utf-8"))
    entries = registry["cases"]
    assert len(entries) == 6, "This declared first development batch expects six prepared companies"
    if any(entry.get("cohort", "DEVELOPMENT") != "DEVELOPMENT" for entry in entries):
        raise ValueError("Only development cases may enter this batch")
    if args.case_ids:
        if not set(args.case_ids) <= {e["case_id"] for e in entries}:
            raise ValueError("Unknown development case")
        entries = [e for e in entries if e["case_id"] in args.case_ids]
    planned = [{"case_id": e["case_id"], "condition": c, "repeat": 1} for e in entries for c in ("B", "A0")]
    preflights = []
    for item in planned:
        directory, summary = execute_v2(root=ROOT, **item)
        preflights.append({"directory": str(directory), "summary": summary})
    if any(r["summary"]["execution_status"] != "PREFLIGHT_COMPLETE" for r in preflights):
        write_json(report_dir / (args.label + "_blocked_preflights.json"), preflights)
        raise SystemExit("Paired preflight did not pass for every planned case; no live calls made")
    files = [p for folder in ("ipo_eval", "config", "prompts") for p in (ROOT / folder).iterdir()
             if p.is_file() and p.suffix in {".py", ".json", ".md"}]
    files += [Path(__file__), ROOT / "pyproject.toml"]
    frozen = report_dir / (args.label + "_source")
    frozen.mkdir(exist_ok=False)
    hashes = {}
    for p in files:
        relative = p.relative_to(ROOT)
        target = frozen / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        hashes[relative.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != hashes[relative.as_posix()]:
            raise SystemExit("Source changed during capture; no live calls made")
    gold_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (ROOT / "data/cases").glob("*/private/gold.json")}
    plan = {"batch": args.label, "version": configs["B"]["version"], "planned_runs": planned,
        "live": args.live, "protocol": "One paired development attempt per condition; all failures retained; no outcome-based retries",
        "model": configs["B"]["model"], "reasoning_effort": configs["B"]["reasoning_effort"],
        "maximum_planned_run_cost_usd": len(planned) * configs["B"]["max_run_usd"],
        "source_snapshot": str(frozen.relative_to(ROOT)), "source_hashes": hashes,
        "new_gold_hashes_before_answers": gold_hashes, "roster_sha256": hashlib.sha256(roster_path.read_bytes()).hexdigest(),
        "diagnostic_subset": bool(args.case_ids),
        "execution_workers": args.workers,
        "launch_policy": "Verify frozen source hashes and STOP before every live run; record unexecuted items separately. Active API calls finish and remain recorded.",
        "preflights": preflights, "final_evaluation_requested": False}
    write_json(plan_path, plan)
    rows = []
    write_json(results_path, {"batch": args.label, "complete": False, "runs": rows})
    if not args.live:
        print("All preflights passed; --live was not supplied.")
        return 0
    stop_path = report_dir / (args.label + "_STOP")
    completed = {}

    def save_progress():
        rows = [completed[i] for i in sorted(completed)]
        unexecuted = [row for row in rows if row["summary"]["execution_status"].startswith("NOT_STARTED_")]
        write_json(results_path, {"batch": args.label,
            "complete": len(rows) == len(planned) and not unexecuted, "runs": rows,
            "stopped_between_runs": bool(unexecuted),
            "unexecuted_planned_runs": [{k: row[k] for k in ("case_id", "condition", "repeat")} for row in unexecuted],
            "remaining_planned_runs": [item for i, item in enumerate(planned) if i not in completed]})

    def execute_item(index, item):
        blocked = launch_precondition(ROOT, stop_path, hashes, item)
        if blocked is not None:
            return index, blocked
        print("START " + item["case_id"] + " " + item["condition"], flush=True)
        directory, summary = execute_v2(live=True, root=ROOT, **item)
        return index, {**item, "directory": str(directory), "summary": summary}

    initial_block = launch_precondition(ROOT, stop_path, hashes, planned[0])
    if initial_block is not None:
        for i, item in enumerate(planned):
            completed[i] = not_started(item, initial_block["summary"]["execution_status"],
                initial_block["summary"]["failure_reason"], initial_block["summary"].get("source_violations"))
        save_progress()
        print("Batch stopped before live launch; every planned item recorded as unexecuted", flush=True)
        return 0
    if args.workers > 1:
        # Every worker uses a fresh client/run/gateway. Save each completed result
        # immediately and retain declared roster order independently of timing.
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            pending = {executor.submit(execute_item, i, item): i for i, item in enumerate(planned)}
            for future in as_completed(pending):
                if future.cancelled():
                    continue
                index, row = future.result()
                completed[index] = row
                print("END " + row["case_id"] + " " + row["condition"] + " " + row["summary"]["execution_status"] +
                      " " + str(row["summary"].get("failure_reason", "")), flush=True)
                block = launch_precondition(ROOT, stop_path, hashes, row)
                if block is not None:
                    for task, waiting_index in pending.items():
                        if task.cancel():  # Active API attempts finish and remain recorded.
                            completed[waiting_index] = not_started(planned[waiting_index],
                                block["summary"]["execution_status"], block["summary"]["failure_reason"],
                                block["summary"].get("source_violations"))
                save_progress()
        return 0
    for index, item in enumerate(planned):
        _, row = execute_item(index, item)
        completed[index] = row
        save_progress()
        print("END " + item["case_id"] + " " + item["condition"] + " " + row["summary"]["execution_status"] +
              " " + str(row["summary"].get("failure_reason", "")), flush=True)
        if row["summary"]["execution_status"].startswith("NOT_STARTED_"):
            for remaining_index in range(index + 1, len(planned)):
                completed[remaining_index] = not_started(planned[remaining_index],
                    row["summary"]["execution_status"], row["summary"]["failure_reason"],
                    row["summary"].get("source_violations"))
            save_progress()
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
