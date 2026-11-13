"""Read-only empirical accounting; scoring follows the separate frozen rubrics."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_costs import audit_run


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(batch):
    here = ROOT / "reports/a0_implementation"
    data = read(here / (batch + "_runs.json"))
    plan = read(here / (batch + "_plan.json"))
    rows = []
    for item in data["runs"]:
        directory = Path(item["directory"])
        summary = read(directory / "summary.json")
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        sources = read(directory / "source_packet.json")["sources"]
        calculations = read(directory / "calculations.json")
        snapshots = read(directory / "snapshots.json")
        rows.append({"case_id": item["case_id"], "condition": item["condition"],
            "run_id": directory.name, "directory": directory.relative_to(ROOT).as_posix(),
            "summary": summary, "cost_audit": audit_run(directory),
            "pages": sorted({c["page"] for c in sources}),
            "snapshot_ids": list(snapshots["snapshots"]),
            "calculation_ids": [c["calc_id"] for c in calculations],
            "tool_counts": dict(Counter(e["tool"] for e in events if e["event"] == "tool_call")),
            "actor_counts": dict(Counter(e["actor"] for e in events if e["event"] == "tool_call")),
            "tool_errors": [{"call_id": e["call_id"], "tool": e["tool"],
                "error_code": e["error_code"], "message": e["message"]}
                for e in events if e["event"] == "tool_envelope" and not e["ok"]],
            "model_responses": [{"file": p.name, "status": r.get("status"),
                "incomplete_details": r.get("incomplete_details"), "usage": r.get("usage")}
                for p in sorted(directory.glob("*_response.json")) for r in [read(p)]],
            "state_transitions": [e for e in events if e["event"] == "state_transition"]})
    report = {"batch": batch, "complete": data["complete"], "planned_count": len(plan["planned_runs"]),
        "observed_count": len(rows), "runs": rows,
        "limits": ["Development failures and API diagnostics are retained separately from submitted review quality.",
            "Costs are estimates from raw usage, not invoices; unknown usage must not be counted as zero.",
            "No held-out final evaluation or A1 treatment has been run."]}
    destination = here / (batch + "_comparison.json")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"batch": batch, "complete": report["complete"], "observed_count": len(rows),
        "outcomes": dict(Counter(r["summary"]["execution_status"] for r in rows))}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    if not args.batch.replace("_", "").isalnum():
        parser.error("Invalid batch label")
    summarize(args.batch)
