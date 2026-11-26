"""Reconcile post-top-up Terra calls from unique runtime sessions and transport events."""

import json
from collections import Counter

from scripts.current_b import OUT, ROOT, dump
from scripts.current_live import load


def run():
    first = load(OUT / "official/dev_audit.json")["cases"]["HDMS"]["roles"]["c_run"]["run_id"][:16]
    rows = []
    run_ids = set()
    for path in sorted(OUT.rglob("summary.json")):
        record = load(path)
        if not isinstance(record, dict) or record.get("model") != "gpt-6.1-terra" or record.get("mode") != "LIVE":
            continue
        rid = record["run_id"]
        if rid[:16] < first or rid in run_ids:
            continue
        run_ids.add(rid)
        events = [json.loads(line) for line in (path.parent / "events.jsonl").read_bytes().splitlines()]
        types = Counter(e["event"] for e in events)
        starts = types["model_call_started"]
        finished = types["model_call_completed"]
        if finished > starts:
            raise ValueError(f"More recorded responses than sends in {rid}")
        rows.append({"run_id": rid, "case": record["case_id"], "stage": record["condition"],
                     "status": record["execution_status"], "sent": starts, "with_recorded_usage": finished,
                     "sent_without_recorded_usage": starts - finished,
                     "pre_send_failures": max(0, record["model_calls"] - starts),
                     "input_tokens": record["input_tokens"], "output_tokens": record["output_tokens"],
                     "estimated_usd": record["known_usage_cost_usd_standard_uncached"],
                     "elapsed_seconds": record["elapsed_seconds"], "evidence": path.parent.relative_to(ROOT).as_posix()})
    fields = ("sent", "with_recorded_usage", "sent_without_recorded_usage", "pre_send_failures",
              "input_tokens", "output_tokens", "estimated_usd")
    totals = {key: round(sum(r[key] for r in rows), 6) for key in fields}
    result = {"window_start_first_resumed_utc": first, "source": "reports/a1_current/**/events.jsonl + summary.json",
              "unit": "unique submitted HTTP calls. Standard uncached estimate for replies with known usage.",
              "included": "paid Terra in this resumed study including technical failures, secondary grading, "
                          "comparators and conditional experiments. Historical cached calls are excluded.",
              "excluded": "signed-in Codex persona subscription usage; invoice and missing response usage unavailable",
              "sessions": len(rows), "totals": totals, "rows": sorted(rows, key=lambda r: r["run_id"])}
    dump(OUT / "official/resume_costs.json", result)
    print(totals)
    return result


if __name__ == "__main__":
    run()
