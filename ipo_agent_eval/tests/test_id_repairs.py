from copy import deepcopy

import pytest

from ipo_eval.id_repairs import apply_id_repairs, build_id_repair_targets


def evidence(claim):
    return {"claim_id": claim, "doc_id": "PUBLIC", "chunk_id": "PUBLIC-p1", "page": 1,
            "locator": "Table 1", "text_for_immutability_test": "Price 123.45"}


@pytest.fixture
def sample():
    review = {
        "judgments": [{"judgment_id": "J1", "facts": [
            {"claim_id": "R_1", "text": "A public number is 123.45", "evidence": [evidence("X_1"), evidence("R_1")]}
        ], "evidence": [evidence("UNKNOWN"), evidence("X_1")], "counter_evidence": [evidence("BAD")]}],
        "requests": [{"request_id": "Q1", "resolution_evidence": [evidence("WRONG")]}],
        "escalations": [{"escalation_id": "E1", "resolution_evidence": [evidence("WRONG")]}],
        "memo": ["Keep all original words"],
    }
    extraction = {"values": {"test": {"claim_id": "X_1"}}, "peers": []}
    return review, extraction


def valid_repairs(targets):
    return [{"path": t["path"], "replacement": t["allowed_ids"][0]} for t in targets]


def test_targets_match_validator_scopes_and_skip_valid_references(sample):
    review, extraction = sample
    original = deepcopy((review, extraction))
    targets = build_id_repair_targets(review, extraction)
    assert len(targets) == 5
    assert targets[0] == {"path": "/judgments/0/facts/0/evidence/0/claim_id", "allowed_ids": ["R_1"]}
    assert targets[1]["allowed_ids"] == ["J1", "R_1", "X_1"]
    assert {t["path"] for t in targets} == {
        "/judgments/0/facts/0/evidence/0/claim_id", "/judgments/0/evidence/0/claim_id",
        "/judgments/0/counter_evidence/0/claim_id", "/requests/0/resolution_evidence/0/claim_id",
        "/escalations/0/resolution_evidence/0/claim_id",
    }
    assert (review, extraction) == original


def test_apply_changes_only_requested_ids_and_keeps_original_immutable(sample):
    review, extraction = sample
    original = deepcopy(review)
    targets = build_id_repair_targets(review, extraction)
    repairs = valid_repairs(targets)
    result = apply_id_repairs(review, targets, list(reversed(repairs)))
    assert review == original
    assert build_id_repair_targets(result, extraction) == []
    result["memo"].append("new")
    assert review["memo"] == original["memo"]
    restored = deepcopy(result)
    restored["memo"] = deepcopy(original["memo"])
    for target in targets:
        old = original
        new = restored
        parts = target["path"].split("/")[1:]
        for part in parts[:-1]:
            old = old[int(part)] if isinstance(old, list) else old[part]
            new = new[int(part)] if isinstance(new, list) else new[part]
        new["claim_id"] = old["claim_id"]
    assert restored == original


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "bad_id", "bad_type", "extra_field"])
def test_invalid_repairs_are_atomic(sample, change):
    review, extraction = sample
    original = deepcopy(review)
    targets = build_id_repair_targets(review, extraction)
    repairs = valid_repairs(targets)
    if change == "missing":
        repairs.pop()
    elif change == "duplicate":
        repairs.append(deepcopy(repairs[0]))
    elif change == "extra":
        repairs.append({"path": "/judgments/0/facts/0/text", "replacement": "replace fact"})
    elif change == "bad_id":
        repairs[0]["replacement"] = "X_1"
    elif change == "bad_type":
        repairs[0]["replacement"] = ["R_1"]
    else:
        repairs[0]["page"] = 999
    with pytest.raises(ValueError):
        apply_id_repairs(review, targets, repairs)
    assert review == original


@pytest.mark.parametrize("path", [
    "/judgments/0/facts/0/text", "/judgments/0/facts/0/evidence/0/page",
    "/judgments/0/facts/0/evidence/0/doc_id", "/judgments/0/facts/0/claim_id",
    "/memo/0", "/judgments/-1/evidence/0/claim_id", "/judgments/00/evidence/0/claim_id",
    "/judgments/0/evidence/99/claim_id", "/judgments/0/evidence/0/claim_id/extra",
])
def test_tampered_target_cannot_expand_patch_scope(sample, path):
    review, _ = sample
    targets = [{"path": path, "allowed_ids": ["R_1"]}]
    with pytest.raises(ValueError):
        apply_id_repairs(review, targets, [{"path": path, "replacement": "R_1"}])


def test_fact_target_cannot_reassign_parent_ownership(sample):
    review, _ = sample
    path = "/judgments/0/facts/0/evidence/0/claim_id"
    with pytest.raises(ValueError):
        apply_id_repairs(review, [{"path": path, "allowed_ids": ["J1"]}], [{"path": path, "replacement": "J1"}])


def test_duplicate_and_stale_targets_are_rejected(sample):
    review, extraction = sample
    targets = build_id_repair_targets(review, extraction)
    with pytest.raises(ValueError):
        apply_id_repairs(review, targets + targets[:1], valid_repairs(targets))
    result = apply_id_repairs(review, targets, valid_repairs(targets))
    with pytest.raises(ValueError):
        apply_id_repairs(result, targets, valid_repairs(targets))


def test_no_targets_returns_independent_unchanged_copy(sample):
    review, _ = sample
    result = apply_id_repairs(review, [], [])
    assert result == review and result is not review


def test_peer_claims_are_included_in_global_allowlist(sample):
    review, extraction = sample
    extraction["peers"] = [{key: {"claim_id": f"XP_{i}"} for i, key in enumerate(("per", "market_cap_million_krw", "earnings_million_krw"))}]
    targets = build_id_repair_targets(review, extraction)
    assert targets[1]["allowed_ids"] == ["J1", "R_1", "XP_0", "XP_1", "XP_2", "X_1"]


def test_bad_structure_and_duplicate_definitions_raise_value_error(sample):
    review, extraction = sample
    with pytest.raises(ValueError):
        build_id_repair_targets({}, extraction)
    extraction["values"]["test"]["claim_id"] = "R_1"
    with pytest.raises(ValueError):
        build_id_repair_targets(review, extraction)
