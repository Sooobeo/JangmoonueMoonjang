"""Aggregate every predeclared v0.3.2 attempt, including failed mandatory items."""
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "reports/a0_implementation"
sys.path.insert(0, str(ROOT / "scripts"))
from audit_costs import audit_run


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    report = read(HERE / "D5_v032_comparison.json")
    assert report["complete"] and len(report["runs"]) == 12
    grading = [read(HERE / name) for name in ("D5_original_case_grading.json", "D5_new_case_grading.json")]
    grades = {g["run_id"]: g for source in grading for g in source["runs"]}
    assert len(grades) == 12
    rows = []
    for run in report["runs"]:
        grade = grades[run["run_id"]]
        scores = {name: [item["score"] for item in
            ([grade[name][key] for key in sorted(grade[name])] if isinstance(grade[name], dict) else grade[name])]
            for name in ("facts", "calculations", "judgments")}
        assert [len(scores[n]) for n in scores] == [5, 3, 4]
        assert all(s in (0, 1) for n in ("facts", "calculations") for s in scores[n])
        assert all(s in (0, 1, 2) for s in scores["judgments"])
        if run["summary"]["execution_status"] == "FAILED":
            assert all(s == 0 for values in scores.values() for s in values)
            assert run["summary"]["final_status"] is None
        methodology = scores["judgments"].count(2) / 4
        assert methodology == grade["metrics"]["methodology"]["rate"]
        rows.append({"case_id": run["case_id"], "condition": run["condition"], "run_id": run["run_id"],
            "directory": run["directory"], "execution_status": run["summary"]["execution_status"],
            "final_status": run["summary"]["final_status"], "failure_reason": run["summary"].get("failure_reason"),
            "facts_correct": sum(scores["facts"]), "calculations_correct": sum(scores["calculations"]),
            "judgments": scores["judgments"], "methodology_rate": methodology,
            "source_appropriateness": grade.get("source_appropriateness"),
            "flags": grade.get("flags", {}), "model_calls": run["summary"]["model_calls"],
            "tool_calls": run["summary"]["tool_calls"], "read_pages": len(run["pages"]),
            "elapsed_seconds": run["summary"]["elapsed_seconds"],
            "known_usage_cost_usd": run["cost_audit"]["known_usage_cost_usd"],
            "unknown_usage_requests": run["cost_audit"]["requests_without_usage"]})
    conditions = {}
    for c in ("B", "A0"):
        group = [r for r in rows if r["condition"] == c]
        assert len(group) == 6
        failed = sum(r["execution_status"] == "FAILED" for r in group)
        cost = sum((Decimal(r["known_usage_cost_usd"]) for r in group), Decimal(0))
        unknown = sum(r["unknown_usage_requests"] for r in group)
        elapsed = [r["elapsed_seconds"] for r in group]
        conditions[c] = {"planned": 6, "submitted": 6 - failed, "failed": failed,
            "failure_rate": failed / 6, "ready": sum(r["final_status"] == "READY" for r in group),
            "facts": {"numerator": sum(r["facts_correct"] for r in group), "denominator": 30},
            "calculations": {"numerator": sum(r["calculations_correct"] for r in group), "denominator": 18},
            "methodology": {"numerator": sum(r["judgments"].count(2) for r in group), "denominator": 24,
                "company_mean": statistics.mean(r["methodology_rate"] for r in group)},
            "J_full_credit_counts": [sum(r["judgments"][i] == 2 for r in group) for i in range(4)],
            "J_each_denominator": 6,
            "failure_or_observed_material_error": {"numerator": sum(r["execution_status"] == "FAILED" or
                r["flags"].get("material_error") is True for r in group), "denominator": 6},
            "known_usage_cost_usd": str(cost), "unknown_usage_requests": unknown,
            "total_cost_estimate_usd": None if unknown else str(cost), "invoice_cost_usd": None,
            "elapsed_seconds": {"mean": statistics.mean(elapsed), "median": statistics.median(elapsed),
                "minimum": min(elapsed), "maximum": max(elapsed)},
            "model_calls": sum(r["model_calls"] for r in group), "tool_calls": sum(r["tool_calls"] for r in group)}
        source_rows = [r["source_appropriateness"] for r in group if r["source_appropriateness"]]
        if source_rows:
            denominator = sum(s["submitted_claims"] for s in source_rows)
            numerator = sum(s["fully_supported_count"] for s in source_rows)
            conditions[c]["submitted_fact_source_support"] = {"numerator": numerator, "denominator": denominator,
                "rate": numerator / denominator if denominator else None,
                "scope": "Structured submitted facts only; failed runs have no observed final claims and remain in failure/mandatory-score denominators."}
    result = {"batch": "D5_v032", "conditions": conditions, "runs": rows,
        "scoring": "Frozen case rubrics; FAILED mandatory non-submission is zero under Protocol §11.1; method=count(J==2)/4.",
        "human_review_complete": False, "blind_grading": False, "human_work_minutes": None,
        "limits": ["AI assisted development grading; six companies and one attempt per condition.",
            "Submitted does not mean correct or calculation complete. Unobserved semantic errors are null.",
            "No inference that A0 is superior: B output truncation prevents a full substantive comparison.",
            "Costs use actual cached/write/ordinary usage with recorded assumptions; no invoice obtained.",
            "v0.3.1 failures/interruption and two compatibility diagnostics are retained separately, not hidden or pooled as paired v0.3.2 results."]}
    (HERE / "D5_comparison_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# B/A0 개발 비교 결과", "", "0.3.2-dev · 개발기업 6곳 × B/A0 각 1회. AI 보조 비블라인드 채점이며 사람 확정 채점은 미완료다.", "",
        "FAILED의 미제출 필수 항목은 원 프로토콜 §11.1에 따라 0점이다. 의미적 오류와 잘못된 완료·불필요 보류가 관찰되지 않으면 null로 둔다. 방법론 충족률은 J1~J4 중 2점인 항목 수/4다.", "",
        "| 기업 | 조건 | 제출/내용 상태 | F /5 | K /3 | J1,J2,J3,J4 | 충족률 | 모델/도구 | 쪽 | 초 | 알려진 비용($) |",
        "|---|---|---|---:|---:|---|---:|---|---:|---:|---:|"]
    for r in rows:
        state = r["final_status"] or "FAILED"
        suffix = "+미확인" if r["unknown_usage_requests"] else ""
        lines.append(f"| [{r['case_id']}](../../{r['directory']}/summary.json) | {r['condition']} | {state} | {r['facts_correct']} | {r['calculations_correct']} | {','.join(map(str,r['judgments']))} | {r['methodology_rate']:.0%} | {r['model_calls']}/{r['tool_calls']} | {r['read_pages']} | {r['elapsed_seconds']:.1f} | {r['known_usage_cost_usd']}{suffix} |")
    lines += ["", "실패 사유와 조건별 분모·비용·시간은 [집계 JSON](D5_comparison_summary.json), 실제 호출·페이지·snapshot·계산 ID는 [실행 비교 JSON](D5_v032_comparison.json)에 보존했다.", "",
        "원래 3기업의 [항목별 채점](D5_original_case_grading.md)과 신규 3기업의 [항목별 채점](D5_new_case_grading.md)을 함께 읽는다. 제출 성공을 계산 완료나 정확도 승인으로 해석하지 않는다.", "",
        "B의 단일 추출 출력 절단이 있어 A0 우월성을 추론하지 않는다. [A1 인계](D6_failure_handoff.md)는 실제 관찰된 행동·실패에만 연결한다. 평가 후보 12개에는 모델 답변을 요청하지 않았다.", "",
        "이전 0.3.1 계획의 최종 실패 3회·중단 1회·미착수 8개는 [별도 감사](D5_v031_interrupted_review_2.md)에 남겼다. 두 호환성 진단도 채점 표본과 구분한다. 청구서와 사람 작업시간은 확보하지 않아 실제 청구액·사람 시간으로 보고하지 않는다.", ""]
    (HERE / "D5_comparison_summary.md").write_text("\n".join(lines), encoding="utf-8")
    prior = read(HERE / "D5_v031_runs.json")["runs"]
    auxiliary = [{"purpose": "v0.3.1 terminal failure", "directory": r["directory"]} for r in prior]
    auxiliary.append({"purpose": "v0.3.1 root-stopped in-progress attempt", "directory": str(ROOT / "runs/20261113T101554Z_A0_500c648e")})
    for name in ("D4_api_smoke.json", "D4_wire_compatibility_probe.json"):
        auxiliary.append({"purpose": "Compatibility diagnostic, unscored", "directory": read(HERE / name)["directory"]})
    for item in auxiliary:
        item["audit"] = audit_run(Path(item["directory"]))
        if item["purpose"] == "v0.3.1 root-stopped in-progress attempt":
            item["audit"]["source_summary_present"] = False
            item["audit"]["execution_status"] = "INTERRUPTED_BY_OPERATOR"
            item["audit"]["status_evidence"] = "reports/a0_implementation/D5_v031_interrupted_review_2.json"
    all_audits = [r["cost_audit"] for r in report["runs"]] + [r["audit"] for r in auxiliary]
    total_known = sum((Decimal(r["known_usage_cost_usd"]) for r in all_audits), Decimal(0))
    missing = sum(r["requests_without_usage"] for r in all_audits)
    account = {"v032_paired_attempts": 12, "earlier_started_attempts": 4, "diagnostic_attempts": 2,
        "earlier_planned_but_never_started": 8, "auxiliary_attempts": auxiliary,
        "all_started_known_usage_cost_usd": str(total_known), "unknown_usage_requests": missing,
        "all_started_total_estimate_usd": None if missing else str(total_known), "invoice_cost_usd": None,
        "note": "Do not treat missing usage as free. All costs, including aborted experiments and diagnostics, remain visible; do not pool their quality scores into the v0.3.2 paired comparison."}
    (HERE / "all_attempt_costs.json").write_text(json.dumps(account, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(conditions, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
