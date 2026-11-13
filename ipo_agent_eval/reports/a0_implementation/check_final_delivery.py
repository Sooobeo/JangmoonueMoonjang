"""Check final evidence links and frozen inputs without running the model."""
import ast
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(require_all_reviews=True):
    issues = []
    stage_files = [
        "D0_review_1.md", "D0_review_2.json", "d0_review_3.json",
        "D1_review_1.json", "D1_review_2.md", "D1_review_3.json",
        "D2_review_1.json", "D2_review_2.md", "D2_review_3.json",
        "D3_review_1.md", "D3_review_2.json", "D3_review_3.md",
        "D4_review_1.json", "D4_review_2.md", "D4_review_3.md",
        "D5_review_1.md", "D5_review_2.md", "D5_review_3.md",
        "D6_review_1.md", "D6_review_2.md", "D6_review_3.md"]
    final_files = [f"final_review_{n}.md" for n in (1, 2, 3)]
    required = stage_files + (final_files if require_all_reviews else [])
    for name in required:
        if not (HERE / name).is_file() or (HERE / name).stat().st_size == 0:
            issues.append("Missing review: " + name)
    plan = read(HERE / "D5_v032_plan.json")
    for name, expected in plan["source_hashes"].items():
        if sha(ROOT / name) != expected:
            issues.append("Runtime source changed after batch freeze: " + name)
        if sha(ROOT / plan["source_snapshot"] / name) != expected:
            issues.append("Frozen runtime copy changed: " + name)
    for name, expected in plan["new_gold_hashes_before_answers"].items():
        if sha(ROOT / name) != expected:
            issues.append("New gold changed: " + name)
    if sha(HERE / "case_roster.json") != plan["roster_sha256"]:
        issues.append("Case roster changed")
    mapping = read(HERE / "requirements_test_mapping.json")
    assert set(mapping["scenarios"]) == {f"T{n:02d}" for n in range(1, 21)}
    for references in mapping["scenarios"].values():
        for reference in references:
            name, function = reference.split("::")
            functions = {node.name for node in ast.walk(ast.parse((ROOT / name).read_text(encoding="utf-8")))
                         if isinstance(node, ast.FunctionDef)}
            if function not in functions:
                issues.append("Missing mapped test: " + reference)
    summary = read(HERE / "D5_comparison_summary.json")
    rows = summary["runs"]
    assert len(rows) == len({(r["case_id"], r["condition"]) for r in rows}) == 12
    assert sum(r["execution_status"] == "SUBMITTED" for r in rows) == 2
    assert sum(r["execution_status"] == "FAILED" for r in rows) == 10
    assert sum(r["model_calls"] for r in rows) == 61
    assert sum(r["tool_calls"] for r in rows) == 159
    assert all(r["calculations_correct"] == 0 for r in rows)
    assert summary["conditions"]["A0"]["methodology"]["company_mean"] == 0.125
    costs = read(HERE / "all_attempt_costs.json")
    assert costs["unknown_usage_requests"] == 3 and costs["all_started_total_estimate_usd"] is None
    assert costs["all_started_known_usage_cost_usd"] == "1.09106735"
    assert any(x["audit"]["execution_status"] == "INTERRUPTED_BY_OPERATOR" for x in costs["auxiliary_attempts"])
    handoff = read(HERE / "D6_failure_handoff.json")
    failures = {r["failure_id"]: r for r in handoff["failure_records"]}
    assert len(failures) == 25 and len(handoff["A1_candidates"]) == 3
    for candidate in handoff["A1_candidates"]:
        assert candidate["observed_A0_failure_ids"]
        assert all(failures[name]["condition"] == "A0" for name in candidate["observed_A0_failure_ids"])
        assert candidate["additional_cost"]["measured"] is False
    links = 0
    for path in (HERE / "implementation_report.md", ROOT / "README.md", ROOT.parent / "whole plan/IPO_파일럿보완_A0_상세설계.md"):
        # The archived design body retains historical links; audit the added status block only.
        text = path.read_text(encoding="utf-8")
        if path.name.startswith("IPO_"):
            text = text.split("작성:", 1)[0]
        for raw in re.findall(r"\]\(([^)]+)\)", text):
            target = raw.strip("<>").split("#", 1)[0]
            if not target or "://" in target:
                continue
            target = unquote(target)
            if not require_all_reviews and Path(target).name in final_files:
                continue
            links += 1
            if not (path.parent / target).resolve().exists():
                issues.append("Broken local link: " + str(path.relative_to(ROOT.parent)) + " -> " + target)
    return {"passed": not issues, "issues": issues, "stage_review_records": len(stage_files),
        "overall_review_records": len(final_files) if require_all_reviews else "pending",
        "frozen_runtime_files_checked": len(plan["source_hashes"]), "test_scenarios": 20,
        "regression_passed": mapping["latest_full_regression"]["passed"], "local_links_checked": links,
        "paid_requests_made_by_this_check": 0,
        "notes": ["Assertions additionally verify all 12 paired outcomes, grading denominators, costs and candidate links.",
            "This closes delivery evidence; it does not make the failed experimental runs successful."]}


if __name__ == "__main__":
    result = check()
    (HERE / "final_delivery_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
