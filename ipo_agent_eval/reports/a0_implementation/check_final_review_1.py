"""Read-only final cross-check; capture derived-report writes in memory."""
import ast
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
from io import StringIO
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
from audit_d5_runs_review_2 import audit, load, sha


def module(name):
    spec = importlib.util.spec_from_file_location("final_review_1_" + name, ROOT / "scripts" / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    checks = {}
    findings = []
    mapped = load(HERE / "requirements_test_mapping.json")
    assert set(mapped["scenarios"]) == {f"T{i:02d}" for i in range(1, 21)}
    cases = sorted({test for tests in mapped["scenarios"].values() for test in tests})
    for test in cases:
        filename, name = test.split("::")
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        assert any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name for node in ast.walk(tree)), test
    checks["T01_T20"] = {"scenario_count": 20, "unique_ast_verified_test_functions": len(cases),
                          "recorded_full_regression": mapped["latest_full_regression"],
                          "runtime_or_model_execution_in_this_review": False}

    batch = audit("D5_v032")
    assert batch["passed"]
    previous = load(HERE / "D5_review_2.json")
    assert all(sha(ROOT / path) == expected for path, expected in previous["batch_artifact_hashes"].items())
    plan = load(HERE / "D5_v032_plan.json")
    assert all(sha(ROOT / filename) == expected for filename, expected in plan["source_hashes"].items())
    checks["frozen_execution"] = {"audit_passed": batch["passed"], "planned": 12, "observed": len(batch["runs"]),
                                   "outcomes": batch["outcome_counts"], "preserved_current_batch_artifacts": len(previous["batch_artifact_hashes"]),
                                   "current_runtime_source_matches_frozen_batch": True,
                                   "original_preservation": batch["original_preservation"]}

    captured = {}
    def capture(path, text, *args, **kwargs):
        captured[Path(path).resolve()] = text
        return len(text)
    with patch.object(Path, "write_text", capture), redirect_stdout(StringIO()):
        module("summarize_development_comparison").summarize("D5_v032")
        module("finalize_development_report").main()
        module("build_a0_handoff").main()
    for path, text in captured.items():
        actual = path.read_text(encoding="utf-8")
        assert actual == text, "Derived report is not reproducible: " + str(path)
    checks["derived_reports"] = {"reproduced_in_memory_without_writes": [path.relative_to(ROOT).as_posix() for path in sorted(captured)],
                                 "all_content_equal": True}

    summary = load(HERE / "D5_comparison_summary.json")
    assert summary["conditions"]["B"]["facts"] == {"numerator": 0, "denominator": 30}
    assert summary["conditions"]["A0"]["facts"] == {"numerator": 7, "denominator": 30}
    assert summary["conditions"]["A0"]["calculations"] == {"numerator": 0, "denominator": 18}
    assert summary["conditions"]["A0"]["methodology"]["numerator"] == 3
    assert summary["conditions"]["A0"]["methodology"]["denominator"] == 24
    assert summary["conditions"]["A0"]["methodology"]["company_mean"] == 0.125
    assert not summary["human_review_complete"] and not summary["blind_grading"] and summary["human_work_minutes"] is None
    checks["grading"] = {"failed_mandatory_items_zero_under_protocol_11_1": True,
                          "methodology_uses_J_equal_2_not_score_sum": True,
                          "human_and_blind_status_honest": True, "all_planned_pairs_retained": True}

    accounts = load(HERE / "all_attempt_costs.json")
    directories = [ROOT / row["directory"] for row in load(HERE / "D5_v032_comparison.json")["runs"]]
    directories += [Path(row["directory"]) for row in accounts["auxiliary_attempts"]]
    cost_by_run = {}
    unknown_calls = 0
    for directory in directories:
        raw_cost = Decimal(0)
        responses = list(directory.glob("*_response.json"))
        config = load(directory / "config.json")
        for path in responses:
            response = load(path)
            usage = response["usage"]
            details = usage.get("input_tokens_details") or {}
            cached = details.get("cached_tokens", 0)
            writes = details.get("cache_write_tokens", 0)
            request = load(path.with_name(path.name.replace("_response.json", "_request.json")))
            ttl = (request.get("prompt_cache_options") or {}).get("ttl", "30m")
            breakdown = details.get("cache_write_tokens_details")
            short = breakdown.get("ttl_30m_tokens", 0) if breakdown is not None else writes if ttl == "30m" else 0
            long = breakdown.get("ttl_12h_tokens", 0) if breakdown is not None else writes if ttl == "12h" else 0
            assert short + long == writes
            ordinary = usage["input_tokens"] - cached - writes
            assert ordinary >= 0 and usage["input_tokens"] <= 272000
            raw_cost += (Decimal(ordinary) + Decimal(cached) * Decimal("0.05") + Decimal(short) * Decimal("1.25") + Decimal(long) * Decimal("2.5") + Decimal(usage["output_tokens"]) * Decimal("5")) / Decimal(1000000)
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        calls = sum(event["event"] == "model_call_started" for event in events)
        unknown_calls += calls - len(responses)
        cost_by_run[directory.name] = str(raw_cost)
    total = sum(map(Decimal, cost_by_run.values()), Decimal(0))
    assert str(total) == accounts["all_started_known_usage_cost_usd"]
    assert total == Decimal("1.09106735") and unknown_calls == accounts["unknown_usage_requests"] == 3
    assert accounts["all_started_total_estimate_usd"] is None and accounts["invoice_cost_usd"] is None
    stopped = next(row for row in accounts["auxiliary_attempts"] if "root-stopped" in row["purpose"])
    assert stopped["audit"]["execution_status"] == "INTERRUPTED_BY_OPERATOR"
    assert stopped["audit"]["source_summary_present"] is False
    checks["costs"] = {"recorded_cache_rates_independently_applied": True, "started_attempts": len(directories),
                       "all_started_known_cache_usage_usd": str(total), "unknown_usage_calls": unknown_calls,
                       "all_started_total_usd": None, "invoice_usd": None,
                       "per_run_known_cache_usage_usd": cost_by_run, "stopped_status_corrected": True}

    handoff = load(HERE / "D6_failure_handoff.json")
    assert handoff["A1_implemented"] is False and len(handoff["failure_records"]) == 25
    index = {row["failure_id"]: row for row in handoff["failure_records"]}
    for candidate in handoff["A1_candidates"]:
        assert candidate["observed_A0_failure_ids"]
        for identifier in candidate["observed_A0_failure_ids"]:
            assert index[identifier]["condition"] == "A0"
        assert candidate["additional_cost"]["measured"] is False
        assert candidate["additional_cost"]["actual_usd"] is None
        assert Decimal(str(candidate["additional_cost"]["estimated_standard_usd_per_added_call"])) == (Decimal(16000) + Decimal(1000) * 5) / 1000000
    c3 = next(row for row in handoff["A1_candidates"] if row["candidate_id"] == "A1-C3")
    assert "EXPLORING" in c3["signal"] and "FINALIZING/COMMIT" in c3["action"]
    checks["D6"] = {"records": 25, "candidate_count": len(handoff["A1_candidates"]),
                    "candidate_observations": {row["candidate_id"]: row["observed_A0_failure_ids"] for row in handoff["A1_candidates"]},
                    "A1_implemented": False, "cost_and_effect_measured": False}

    documents = [ROOT / "README.md", HERE / "implementation_report.md", HERE / "D5_comparison_summary.md", HERE / "D6_failure_handoff.md", ROOT.parent / "whole plan/IPO_파일럿보완_A0_상세설계.md"]
    missing = []
    expected_future_reviews = []
    for path in documents:
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if link.startswith(("http:", "https:", "#")):
                continue
            target = (path.parent / unquote(link.split("#", 1)[0])).resolve()
            if not target.exists():
                row = {"document": str(path.relative_to(ROOT.parent)), "target": str(target)}
                if target.name in {"final_review_1.md", "final_review_2.md", "final_review_3.md"}:
                    expected_future_reviews.append(row)
                else:
                    missing.append(row)
    assert not missing, missing
    text = (HERE / "implementation_report.md").read_text(encoding="utf-8")
    assert "별도 감사의 표준 비캐시 요율 추정" in text
    assert "예산 상한 검사와 다른 계산" in text
    checks["documents"] = {"broken_existing_artifact_links": missing,
                           "future_final_review_links_pending": expected_future_reviews,
                           "status_explicitly_pending_final_three_reviews": True,
                           "reviewed_file_hashes": {str(path.relative_to(ROOT.parent)): sha(path) for path in documents}}
    findings.extend([
        {"id": "FINAL1-01", "severity": "documentation", "status": "RESOLVED", "finding": "Standard uncached totals were conflated with the cache-write budget ceiling.", "resolution": "Implementation report and D5 third review now distinguish the two; amounts and original usage were unchanged."},
        {"id": "FINAL1-02", "severity": "derived_metadata", "status": "RESOLVED", "finding": "The stopped v0.3.1 run inherited RUNNING in auxiliary cost metadata because no summary exists.", "resolution": "Derived metadata and generator now mark INTERRUPTED_BY_OPERATOR, preserve source_summary_present=false, and link the interruption evidence; no original summary was created."},
    ])
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "review": "Overall final review 1", "reviewer": "preservation_review", "status": "PASS_AFTER_REPAIR", "unresolved_findings": [], "findings": findings, "checks": checks,
              "boundary": "Read-only review and in-memory report regeneration. No runtime/API experiment or source change. This is the first overall review, not a claim that all three overall reviews are complete."}
    destination = HERE / "final_review_1.json"
    assert not destination.exists()
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "resolved_findings": len(findings), "scenarios": 20, "mapped_tests": len(cases), "reproduced_reports": len(captured), "known_cache_usage_usd": str(total), "unknown_usage_calls": unknown_calls}, indent=2))


if __name__ == "__main__":
    main()
