from copy import deepcopy
import json

from jsonschema import Draft202012Validator
import pytest

from ipo_eval.format_patch import PATCH_SCHEMA, FormatPatchError, apply_format_patch
from ipo_eval.schemas import obj
from ipo_eval.schemas_v2 import EXTRACTION_V2, REVIEW_V2
from test_contracts_v2 import ctx, fact, ev
from test_gateway_v2 import review, request


def patch(*operations):
    return {"operations": list(operations)}


def evidence_review():
    value = review()
    value["judgments"][0]["facts"] = [{"claim_id": "F1", "text": "Exact original factual assertion 001.00", "evidence": [ev("F1")]}]
    value["requests"] = [request()]
    return value


def test_patch_repairs_only_allowed_fields_and_preserves_original_atomically():
    value = evidence_review()
    value["judgments"][0]["facts"][0]["evidence"][0].update(page="01", claim_id="bad")
    value["requests"][0]["version"] = "1"
    value["extension"] = {"untrusted": "extra content"}
    del value["memo"]
    before = deepcopy(value)
    operations = patch(
        {"op": "NORMALIZE_INTEGER", "path": "/judgments/0/facts/0/evidence/0/page"},
        {"op": "RELINK_CLAIM", "path": "/judgments/0/facts/0/evidence/0/claim_id", "claim_id": "F1"},
        {"op": "NORMALIZE_INTEGER", "path": "/requests/0/version"},
        {"op": "REMOVE_EXTRA", "path": "/extension"},
        {"op": "ADD_EMPTY", "path": "/memo", "empty_kind": "ARRAY"})
    repaired = apply_format_patch(value, operations, REVIEW_V2)
    assert value == before
    assert repaired == evidence_review()
    repaired["judgments"][0]["facts"][0]["text"] = "mutated detached copy"
    assert value == before


@pytest.mark.parametrize("path", ["/judgments/0/conclusion", "/judgments/0/facts/0/text", "/judgments/0/facts/0/claim_id",
    "/judgments/0/facts/0/evidence/0/doc_id", "/judgments/0/facts/0/evidence/0/chunk_id",
    "/judgments/0/facts/0/evidence/0/locator", "/requests/0/resolution_status", "/requests/0/blocking",
    "/missing_inputs", "/judgments/0"])
def test_schema_members_claims_decisions_sources_and_lists_cannot_be_removed(path):
    value = evidence_review()
    before = deepcopy(value)
    with pytest.raises(FormatPatchError):
        apply_format_patch(value, patch({"op": "REMOVE_EXTRA", "path": path}), REVIEW_V2)
    assert value == before


@pytest.mark.parametrize("path", ["", "/", "/judgments/-/memo", "/judgments/00/memo", "/judgments/9/memo", "/judgments/~2/memo"])
def test_root_append_invalid_indices_and_pointer_escapes_are_rejected(path):
    with pytest.raises(FormatPatchError):
        apply_format_patch(review(), patch({"op": "ADD_EMPTY", "path": path, "empty_kind": "ARRAY"}), REVIEW_V2)


def test_populated_missing_inputs_cannot_be_cleared_as_a_format_repair():
    value = review()
    value["missing_inputs"] = [{"field": "earnings_million_krw", "missing_reason": "Not registered", "request_id": "R1"}]
    for operation in ({"op": "REMOVE_EXTRA", "path": "/missing_inputs/0"},
                      {"op": "ADD_EMPTY", "path": "/missing_inputs", "empty_kind": "ARRAY"},
                      {"op": "replace", "path": "/missing_inputs", "value": []}):
        with pytest.raises(FormatPatchError):
            apply_format_patch(value, patch(operation), REVIEW_V2)


@pytest.mark.parametrize("number", [1.0, True, "-1", "1.0", " 1 "])
def test_integer_normalization_does_not_accept_floats_booleans_or_changed_numbers(number):
    value = evidence_review()
    value["requests"][0]["version"] = number
    with pytest.raises(FormatPatchError):
        apply_format_patch(value, patch({"op": "NORMALIZE_INTEGER", "path": "/requests/0/version"}), REVIEW_V2)


def test_claim_link_must_target_existing_definition_not_a_reference_or_extra_field():
    value = evidence_review()
    value["extension"] = {"claim_id": "invented"}
    value["judgments"][0]["facts"][0]["evidence"][0]["claim_id"] = "reference_only"
    for claim in ("invented", "reference_only", "new"):
        with pytest.raises(FormatPatchError, match="UNKNOWN_CLAIM"):
            apply_format_patch(value, patch({"op": "REMOVE_EXTRA", "path": "/extension"},
                {"op": "RELINK_CLAIM", "path": "/judgments/0/facts/0/evidence/0/claim_id", "claim_id": claim}), REVIEW_V2)


def test_union_discriminator_prevents_removing_a_valid_payload_field():
    value = {"records": [ctx(), fact()], "document_version_notes": [], "extraction_limits": []}
    value["records"][1]["payload"]["extra/key"] = "ignored"
    del value["records"][1]["payload"]["derivation_id"]
    repaired = apply_format_patch(value, patch(
        {"op": "REMOVE_EXTRA", "path": "/records/1/payload/extra~1key"},
        {"op": "ADD_EMPTY", "path": "/records/1/payload/derivation_id", "empty_kind": "NULL"}), EXTRACTION_V2)
    assert repaired["records"][1]["payload"]["value"] == "10"
    with pytest.raises(FormatPatchError, match="REMOVE_EXTRA"):
        apply_format_patch(value, patch({"op": "REMOVE_EXTRA", "path": "/records/1/payload/value"}), EXTRACTION_V2)


def test_invalid_late_operation_does_not_apply_earlier_valid_change():
    value = review()
    value["extra"] = "untrusted"
    before = deepcopy(value)
    with pytest.raises(FormatPatchError):
        apply_format_patch(value, patch({"op": "REMOVE_EXTRA", "path": "/extra"},
            {"op": "REMOVE_EXTRA", "path": "/model_reported_status"}), REVIEW_V2)
    assert value == before


def test_duplicate_paths_and_unresolved_target_schema_are_rejected():
    value = review()
    del value["memo"]
    operation = {"op": "ADD_EMPTY", "path": "/memo", "empty_kind": "ARRAY"}
    with pytest.raises(FormatPatchError, match="DUPLICATE"):
        apply_format_patch(value, patch(operation, operation), REVIEW_V2)
    with pytest.raises(FormatPatchError, match="TARGET_SCHEMA"):
        apply_format_patch(value, patch(), REVIEW_V2)


def test_patch_output_size_does_not_repeat_long_original_claims():
    value = evidence_review()
    value["judgments"][0]["facts"][0]["text"] *= 10000
    value["extra"] = "remove"
    operations = patch({"op": "REMOVE_EXTRA", "path": "/extra"})
    repaired = apply_format_patch(value, operations, REVIEW_V2)
    assert repaired["judgments"][0]["facts"][0]["text"] == value["judgments"][0]["facts"][0]["text"]
    assert len(json.dumps(operations)) < 100


def test_patch_schema_is_strict_and_bounded():
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["properties"]) == set(node["required"])
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(PATCH_SCHEMA)
    assert not Draft202012Validator(PATCH_SCHEMA).is_valid(patch(*([{"op": "REMOVE_EXTRA", "path": "/x"}] * 33)))


def test_compact_claim_link_uses_only_existing_schema_declared_claims():
    from ipo_eval.wire_contract import EXTRACTION_WIRE, to_wire_extraction
    from test_contracts_v2 import CHUNKS
    value = to_wire_extraction({"records": [ctx(), fact()], "document_version_notes": [], "extraction_limits": []}, CHUNKS)
    value["values"][0]["ev"][0]["claim"] = "bad reference"
    before = deepcopy(value)
    fixed = apply_format_patch(value, patch({"op": "RELINK_CLAIM", "path": "/values/0/ev/0/claim", "claim_id": "C_F"}), EXTRACTION_WIRE)
    assert fixed["values"][0]["ev"][0]["claim"] == "C_F"
    assert value == before and fixed["values"][0]["v"] == "10"
    for claim in ("new claim", "bad reference"):
        with pytest.raises(FormatPatchError, match="UNKNOWN_CLAIM"):
            apply_format_patch(value, patch({"op": "RELINK_CLAIM", "path": "/values/0/ev/0/claim", "claim_id": claim}), EXTRACTION_WIRE)
    for path in ("/values/0/c", "/values/0/ev/0/chunk", "/values/0/ev/0/at"):
        with pytest.raises(FormatPatchError, match="OUTSIDE_EVIDENCE"):
            apply_format_patch(value, patch({"op": "RELINK_CLAIM", "path": path, "claim_id": "C_F"}), EXTRACTION_WIRE)


def test_compact_claim_declarations_cannot_be_smuggled_in_extra_fields():
    from ipo_eval.wire_contract import EXTRACTION_WIRE, to_wire_extraction
    from test_contracts_v2 import CHUNKS
    value = to_wire_extraction({"records": [ctx(), fact()], "document_version_notes": [], "extraction_limits": []}, CHUNKS)
    value["contexts"][0]["c"] = "extra context claim"
    value["values"][0]["extra"] = {"c": "extra value claim"}
    for claim in ("extra context claim", "extra value claim"):
        with pytest.raises(FormatPatchError, match="UNKNOWN_CLAIM"):
            apply_format_patch(value, patch({"op": "REMOVE_EXTRA", "path": "/contexts/0/c"},
                {"op": "REMOVE_EXTRA", "path": "/values/0/extra"},
                {"op": "RELINK_CLAIM", "path": "/values/0/ev/0/claim", "claim_id": claim}), EXTRACTION_WIRE)


def test_compact_derivation_claim_can_relink_coverage_but_cannot_be_changed():
    from ipo_eval.wire_contract import EXTRACTION_WIRE, to_wire_extraction
    from test_contracts_v2 import CHUNKS, coverage, market_records
    value = to_wire_extraction({"records": market_records() + [coverage()],
        "document_version_notes": [], "extraction_limits": []}, CHUNKS)
    fixed = apply_format_patch(value, patch({"op": "RELINK_CLAIM", "path": "/coverage/0/ev/0/claim", "claim_id": "C_F_PER"}), EXTRACTION_WIRE)
    assert fixed["coverage"][0]["ev"][0]["claim"] == "C_F_PER"
    with pytest.raises(FormatPatchError, match="OUTSIDE_EVIDENCE"):
        apply_format_patch(value, patch({"op": "RELINK_CLAIM", "path": "/derivations/0/c", "claim_id": "C_F_PER"}), EXTRACTION_WIRE)
