import pytest

from scripts import a1_main_blind as blind
from scripts import a1_main_timing as timing


def put(path, value):
    blind.write_once(path, blind.wire(value))


def test_missing_neutral_timing_source_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(blind, "BASE", tmp_path)
    result = blind.timed_review("issuer", "i")
    assert result["attempts"] == 0 and result["whole_seconds"] is None
    assert result["missing_reason"] == "neutral_question_or_source_pages_unavailable"
    assert blind.timed_review("issuer", "i") == result


def test_timing_order_shared_items_fallback_and_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(timing, "BASE", tmp_path)
    for case, common in (("x", ["m"]), ("y", []), ("z", [])):
        put(tmp_path / "issuers" / case / "b.json", {"mandatory": common})
    put(
        tmp_path / "terra/x/ranking.json",
        {
            "mandatory": ["m"],
            "rule": {"operational": ["m", "r"]},
            "ai": {"operational": ["m", "a"]},
        },
    )
    put(tmp_path / "terra/y/failure.json", {"operational": ["f"]})
    put(
        tmp_path / "terra/z/ranking.json",
        {"mandatory": [], "rule": {"operational": []}, "ai": {"operational": []}},
    )
    cohort = ["x", "y", "z"]
    assignment = timing.freeze_assignments(cohort)
    assert assignment["order"] == sorted(
        {("x", "m"), ("x", "r"), ("x", "a"), ("y", "f")},
        key=lambda key: blind.hash_bytes("/".join(key).encode()),
    )
    with pytest.raises(ValueError, match="timing outstanding"):
        timing.summary(cohort)
    for case, key in assignment["order"]:
        value = None if key == "a" else 2.5
        put(
            tmp_path / "timing" / case / key / "timing.json",
            {
                "whole_seconds": value,
                "packet_prep_seconds": 0.3,
                "service_seconds": 2.1,
                "verification_seconds": 0.1,
                "missing_reason": "timeout" if value is None else None,
            },
        )
    report = timing.summary(cohort)
    assert (
        report["unique"]["assigned_items"] == 4 and report["unique"]["timed_items"] == 3
    )
    assert report["per_case"]["x"]["rule"]["whole_seconds"] == 5
    assert report["per_case"]["x"]["ai"]["whole_seconds"] is None
    assert report["per_case"]["y"]["fallback"]["whole_seconds"] == 2.5
    assert report["paired_complete_issuers"] == ["z"]
    assert report["paired_delta_seconds_ai_minus_rule"] == 0


@pytest.mark.parametrize("failure", [True, False])
def test_blind_time_keeps_one_measurement_and_terminal_missing(
    tmp_path, monkeypatch, failure
):
    monkeypatch.setattr(blind, "BASE", tmp_path)
    put(tmp_path / "issuers/x/items.json", [{"id": "i", "pages": [1]}])
    put(
        tmp_path / "issuers/x/grading.json",
        {"items": [{"item_id": "i", "question": "neutral"}], "pages": {"1": "excerpt"}},
    )

    def submit(folder, role, schema, packet, check):
        assert role == blind.ROLE and schema == blind.REVIEW
        assert packet == {
            "check_question": "neutral",
            "original_physical_pages": {"1": "excerpt"},
        }
        for n in (1, 2):
            put(
                folder / f"attempt-{n}" / "closed.json",
                {
                    "elapsed_seconds": 1.2,
                    "session_seconds": 1,
                    "verification_seconds": 0.1,
                    "valid": n == 2 and not failure,
                },
            )
        if failure:
            raise RuntimeError("Two starts exhausted: synthetic")

    monkeypatch.setattr(blind, "submit", submit)
    result = blind.timed_review("x", "i")
    assert blind.timed_review("x", "i") == result
    assert result["observed_attempt_seconds"] == 2.4
    if failure:
        assert (
            result["whole_seconds"] is None
            and result["missing_reason"] == "attempts_exhausted"
        )
    else:
        assert result["whole_seconds"] == result["packet_prep_seconds"] + 2.4
        assert result["service_seconds"] == 2 and result["verification_seconds"] == 0.2
