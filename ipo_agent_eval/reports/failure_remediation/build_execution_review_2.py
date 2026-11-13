"""Read-only B-run checks plus explicitly authored semantic review notes.

This reporting utility does not call a model or import the execution runtime.
Only execution_review_2.json/.md are written. Source/gold/run artifacts are read.
"""
from collections import Counter
from decimal import Decimal
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="FIX_v041")
    parser.add_argument("--output-stem", default="execution_review_2")
    args = parser.parse_args()
    plan = read(OUT / f"{args.label}_plan.json")
    batch = read(OUT / f"{args.label}_runs.json")
    note_path = OUT / f"{args.output_stem}_notes.json"
    notes = read(note_path) if note_path.exists() else {}
    complete = {x["case_id"]: x for x in batch["runs"] if x["condition"] == "B"}
    rows = []
    for wanted in plan["planned_runs"]:
        if wanted["condition"] != "B":
            continue
        case = wanted["case_id"]
        if case not in complete:
            not_started = any(x.get("case_id") == case and x.get("condition") == "B" for x in batch.get("unexecuted_planned_runs", []))
            rows.append({"case_id": case, "condition": "B", "review_status": "REVIEWED_NOT_STARTED" if not_started else "PENDING_RUN", "execution_status": "NOT_STARTED" if not_started else None, "scores": None})
            continue
        item = complete[case]
        if item.get("directory") is None and item.get("summary", {}).get("execution_status", "").startswith("NOT_STARTED"):
            rows.append({"case_id": case, "condition": "B", "review_status": "REVIEWED_NOT_STARTED",
                         "execution_status": item["summary"]["execution_status"], "final_status": None,
                         "scores": None, "reason": item["summary"].get("failure_reason", "Operator stopped before this run started")})
            continue
        p = Path(item["directory"])
        summary = read(p / "summary.json")
        row = {"case_id": case, "condition": "B", "run_id": summary["run_id"], "execution_status": summary["execution_status"], "final_status": summary.get("final_status"), "review_status": "PENDING_SEMANTIC_REVIEW"}
        events = [json.loads(s) for s in (p / "events.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
        calls = [e for e in events if e.get("event") == "tool_call"]
        row["execution_checks"] = {"model_calls": summary["model_calls"], "format_repairs": summary["format_repairs"], "transient_retries": summary.get("transient_retries"), "usage_unknown": summary["usage_unknown"], "gateway_tools_by_actor": dict(Counter(f'{e.get("actor")}:{e.get("tool")}' for e in calls)), "register_calls": sum(e.get("tool") == "calculate" and e.get("arguments", {}).get("request", e.get("arguments", {})).get("operation") == "REGISTER_BATCH" for e in calls), "evaluate_calls": sum(e.get("tool") == "calculate" and e.get("arguments", {}).get("request", e.get("arguments", {})).get("operation") == "EVALUATE" for e in calls), "sensitivity_calls": sum(e.get("tool") == "sensitivity" for e in calls)}
        if summary["execution_status"] == "FAILED":
            row.update({"review_status": "REVIEWED_FAILURE", "scores": {"F": [0] * 5, "K": [0] * 3, "J": [0] * 4, "methodology_rate": 0}, "flags": {"material_error": None, "false_completion": None, "unnecessary_hold": None}, "failure_policy": "Protocol 11.1: unsubmitted required items score zero; final content flags remain unobserved/null."})
        elif (p / "review.json").exists():
            review = read(p / "review.json")
            calcs = read(p / "calculations.json")
            packet = read(p / "source_packet.json")
            byid = {c["calc_id"]: c for c in calcs}
            locs = {(s["doc_id"], s["chunk_id"], s["page"]) for s in packet["sources"]}
            checks = []
            for u in review["calculation_uses"]:
                c = byid.get(u["calc_id"])
                valid = c is not None and c["input_snapshot_id"] == review["input_snapshot_id"]
                if u["use"] == "USE":
                    valid = valid and c["status"] == "OK" and Decimal(u["stated_value"]) == Decimal(c["result"])
                checks.append({"calc_id": u["calc_id"], "use": u["use"], "valid": valid, "status": c["status"] if c else None})
            facts = [f for j in review["judgments"] for f in j["facts"]]
            row["calculation_use_checks"] = checks
            row["calculation_status_counts"] = dict(Counter(c["status"] for c in calcs))
            row["structured_claim_location_checks"] = [{"claim_id": f["claim_id"], "valid": all((e["doc_id"], e["chunk_id"], e["page"]) in locs and e["claim_id"] == f["claim_id"] for e in f["evidence"]), "evidence": f["evidence"]} for f in facts]
            row["scores"] = {"F": None, "K": None, "J": None, "reason": "F/J full rubric grading is outside this focused review; K authored after semantic review."}
        if case in notes:
            row.update(notes[case])
        row["artifact_sha256"] = {name: hashlib.sha256((p / name).read_bytes()).hexdigest() for name in ("summary.json", "review.json", "calculations.json", "source_packet.json", "extraction_model_output.json") if (p / name).exists()}
        rows.append(row)
    result = {"batch": args.label, "review_number": 2, "condition": "B", "status": "COMPLETE" if all(r["review_status"].startswith("REVIEWED") for r in rows) else "IN_PROGRESS", "reviewer": "AI non-blind independent assistance; human review pending", "scope": "Execution, current-snapshot calculation uses, case-specific K1-K3, submitted structured factual claim source support and remaining semantic limitations. Full F/J grading not performed for submitted runs.", "failure_policy": "FAILED unsubmitted required F/K/J=0; not executed scores null. K1 correct labelled disclosed component sum may receive credit while complete current denominator remains unresolved.", "source_mutations": False, "comparison_limit": "Budgets, prompts and executor changed since v032; no pure causal or held-out generalization claim.", "runs": rows}
    (OUT / f"{args.output_stem}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = [f"# {args.label} B 실행 독립 2차 검토", "", result["status"], "", "AI 비블라인드 보조 검토이며 인간 검토는 미완료다. 실행 원본·동결 코드·gold는 변경하지 않았다. 실행·계산 사용·회사별 K1~K3와 구조화 사실 근거를 확인하며, 제출 성공을 전체 방법론 정답으로 간주하지 않는다.", ""]
    for row in rows:
        md += [f'## {row["case_id"]}', "", row["review_status"], ""]
        if "run_id" not in row:
            continue
        md += [f'{row["run_id"]}: {row["execution_status"]} / {row.get("final_status")}', ""]
        if "calculation_use_checks" in row:
            checks = row["calculation_use_checks"]
            md += [f'최종 계산 사용 {dict(Counter(c["use"] for c in checks))}; 현재 snapshot/결과 일치 {sum(c["valid"] for c in checks)}/{len(checks)}. 계산 상태 {row["calculation_status_counts"]}.', ""]
        for finding in row.get("failure_observations", []):
            md += [finding["classification"] + ": " + finding["reason"], ""]
        if "K" in row:
            for key, val in row["K"].items():
                md.append(f'- {key}: {val["score"]}점. {val["reason"]}')
            md.append("")
        if "source_appropriateness" in row:
            s = row["source_appropriateness"]
            md += [f'구조화 사실 {s["submitted_claims"]}개: FULL {s["fully_supported_count"]}, QUALIFIED {s["qualified_count"]}, UNSUPPORTED {s["unsupported_count"]}; FULL/제출 사실 지지율 {s["support_rate"]}. 전체 결론 정확도를 뜻하지 않는다.', "", "| 주장 | 판정 | 근거 |", "|---|---|---|"]
            md += [f'| {f["claim_id"]} | {f["status"]} | {f["reason"]} |' for f in s["claims"]]
            md.append("")
        md += [f'- {x}' for x in row.get("remaining_limitations", [])] + [""]
        md += [f'[원본 답변](../../runs/{row["run_id"]}/review.json), [계산](../../runs/{row["run_id"]}/calculations.json), [열람 원문](../../runs/{row["run_id"]}/source_packet.json). 상세 검증과 SHA-256은 동명 JSON에 보존했다.', ""]
    md += ["F/J 전항목은 제출 실행에서 미채점이며 null이다. 실패 미제출이면 protocol 11.1에 따라 필수 F/K/J는 0이다. K1의 산술합계와 최신 전체분모 완전성은 별도로 판단한다. 버전 간 실행 조건 변경 때문에 순수 효과나 최종평가 성과로 해석하지 않는다.", ""]
    (OUT / f"{args.output_stem}.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"status": result["status"], "runs": [(r["case_id"], r["review_status"]) for r in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
