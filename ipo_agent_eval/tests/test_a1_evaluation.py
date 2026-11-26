import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from ipo_eval.a1_ranking import rank
from ipo_eval.a1_ranking_contract import example
from scripts.evaluate_a1 import aggregate, evaluate, grade_case


def rubric(grades=("material", "material", "deferred")):
    return {"population": "unmodified_original", "case_id": "SYNTHETIC", "assignment_ref": "synthetic-v1",
            "items": [{"id": key, "grade": grade, "source_ref": "p.1", "reason": "synthetic evidence"}
                      for key, grade in zip(("X", "Y", "W"), grades, strict=True)]}


@pytest.mark.parametrize(("grades", "delta", "lower", "upper"), [
    (("acceptable", "material", "deferred"), 1, 0, 1),
    (("deferred", "deferred", "material"), -1, -1, 0),
    (("material", "deferred", "deferred"), 0, -1, 1),
    (("material", "nonmaterial", "nonmaterial"), 0, 0, 0)])
def test_changed_items_bounds_and_signed_direction(grades, delta, lower, upper):
    result = grade_case("SYNTHETIC", rank(example()), rubric(grades))
    assert (result["delta"], result["lower"], result["upper"]) == (delta, lower, upper)
    assert result["entered"] == ["Y"] and result["displaced"] == ["W"]
    assert result["status"] == "EVALUABLE" and result["original_status"] == "HUMAN_REVIEW"


def test_equal_lists_and_zero_material_denominator_still_count_issuer():
    case = example()
    case["trials"] = case["trials"][:1]
    result = grade_case("SYNTHETIC", rank(case), rubric(("acceptable", "deferred", "nonmaterial")))
    summary = aggregate([result])
    assert result["delta"] == result["lower"] == result["upper"] == 0
    assert summary["tied"] == 1 and summary["material_issues"] == 0
    assert summary["baseline_missed_rate"] is None and summary["canary_missed_rate"] is None
    assert summary["equal_issuer_mean_delta"] == "0"


def test_original_korean_rubric_vocabulary_is_supported():
    a = grade_case("SYNTHETIC", rank(example()), rubric(("수용 가능", "중대 쟁점", "판정 유보")))
    b = grade_case("SYNTHETIC", rank(example()), rubric(("acceptable", "material", "deferred")))
    assert a == b


def test_equal_issuer_mean_not_weighted_by_items():
    first = grade_case("SYNTHETIC", rank(example()), rubric())
    second = grade_case("SYNTHETIC", rank(example()), rubric(("acceptable", "nonmaterial", "material")))
    third = grade_case("SYNTHETIC", rank(example()), rubric(("material", "material", "deferred")))
    summary = aggregate([first, second, third, {"status": "UNEVALUABLE", "reason": "missing"}])
    assert [summary[k] for k in ("selected_issuers", "evaluated_issuers", "unevaluable_issuers")] == [4, 3, 1]
    assert summary["improved"] == 2 and summary["worsened"] == 1 and summary["tied"] == 0
    assert summary["equal_issuer_mean_delta"].startswith("0.333333333333")
    assert summary["mean_lower"].startswith("-0.333333333333")
    assert summary["deferred_bounds_include_zero"] is True


@pytest.mark.parametrize("fault", ["case_id", "human_grade", "missing_grade", "extra_grade",
                                  "duplicate_grade", "wrong_population", "missing_evidence",
                                  "different_assignment", "overlap", "unequal_k"])
def test_invalid_case_identifies_why_it_is_unevaluable(fault):
    ranking = rank(example())
    grade = rubric()
    if fault == "case_id":
        grade["case_id"] = "other"
    elif fault == "human_grade":
        grade["items"][1]["grade"] = "unknown"
    elif fault == "missing_grade":
        grade["items"].pop()
    elif fault == "extra_grade":
        grade["items"].append({**grade["items"][0], "id": "extra"})
    elif fault == "duplicate_grade":
        grade["items"][-1]["id"] = grade["items"][0]["id"]
    elif fault == "wrong_population":
        grade["population"] = "seeded"
    elif fault == "missing_evidence":
        grade["items"][0]["reason"] = ""
    elif fault == "different_assignment":
        grade["assignment_ref"] = "different"
    elif fault == "overlap":
        ranking["B1"]["canary_extra"] = ["X"]
    else:
        ranking["B1"]["baseline_extra"] = []
    with pytest.raises(ValueError):
        grade_case("SYNTHETIC", ranking, grade)


def test_offline_cli_preserves_selected_issuers_and_missing_sources(tmp_path):
    cwd = Path(__file__).resolve().parents[1]
    cli = [sys.executable, "-m", "scripts.evaluate_a1"]
    sample = json.loads(subprocess.check_output([*cli, "--example"], cwd=cwd))
    roster = sample["manifest"]
    roster["issuers"].extend([
        {"case_id": "explicitly-unavailable", "unavailable_reason": "missing original rubric"},
        {"case_id": "missing-archive", "ranking": "missing.json", "rubric": "rubric.json"},
    ])
    manifest = tmp_path / "roster.json"
    manifest.write_text(json.dumps(roster), encoding="utf-8")
    (tmp_path / "ranking.json").write_text(json.dumps(rank(example())), encoding="utf-8")
    (tmp_path / "rubric.json").write_text(json.dumps(sample["rubric"]), encoding="utf-8")
    report = json.loads(subprocess.check_output([*cli, str(manifest)], cwd=cwd))
    assert report["data_kind"] == "synthetic"
    assert report["summary"]["equal_issuer_mean_delta"] == "1"
    assert report["summary"]["selected_issuers"] == 3 and report["summary"]["unevaluable_issuers"] == 2
    assert all(r.get("reason") for r in report["issuers"][1:])
    roster["issuers"][0]["ranking_sha256"] = "wrong"
    manifest.write_text(json.dumps(roster), encoding="utf-8")
    failed = evaluate(manifest)
    assert failed["summary"]["equal_issuer_mean_delta"] is None
    assert failed["summary"]["deferred_bounds_include_zero"] is None
    assert "digest" in failed["issuers"][0]["reason"]
    dup = deepcopy(roster["issuers"][0])
    roster["issuers"].append(dup)
    manifest.write_text(json.dumps(roster), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicated"):
        evaluate(manifest)
