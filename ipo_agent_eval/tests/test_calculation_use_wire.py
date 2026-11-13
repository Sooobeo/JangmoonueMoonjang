"""Wire constraints prevent contradictory calculation-use declarations.

Synthetic values only: no grading answers or recorded model responses.
"""
import json

from jsonschema import Draft202012Validator
import pytest

from ipo_eval.format_patch import FormatPatchError, apply_format_patch
from ipo_eval.schemas import arr, obj
from ipo_eval.schemas_v2 import REVIEW_V2
from test_remediation_integration import real_gateway


def item(**updates):
    return {"calc_id": "CALC_SYNTHETIC", "use": "USE", "stated_value": "12.5",
            "related_judgment_ids": ["J1"], "reason": "Synthetic current result",
            "replacement_id": None, "unresolved": False, **updates}


@pytest.mark.parametrize("value", [
    item(), item(stated_value="-0.25"),
    item(use="REJECT", stated_value=None, replacement_id="OTHER_CALC", unresolved=False),
    item(use="REJECT", stated_value=None, replacement_id=None, unresolved=True),
    item(use="REJECT", stated_value="12.5", replacement_id=None, unresolved=True),
])
def test_wire_allows_each_existing_valid_use_or_rejection_mode(tmp_path, value):
    schema = real_gateway(tmp_path).review_schema()["properties"]["calculation_uses"]["items"]
    Draft202012Validator(schema).validate(value)


@pytest.mark.parametrize("changes", [
    {"unresolved": True}, {"replacement_id": "OTHER_CALC"}, {"stated_value": None},
    {"stated_value": "NaN"}, {"stated_value": 12.5},
    {"use": "REJECT", "replacement_id": None, "unresolved": False},
    {"use": "REJECT", "replacement_id": "OTHER_CALC", "unresolved": True},
])
def test_wire_rejects_semantically_contradictory_modes_before_generation(tmp_path, changes):
    schema = real_gateway(tmp_path).review_schema()["properties"]["calculation_uses"]["items"]
    assert list(Draft202012Validator(schema).iter_errors(item(**changes)))


def test_wire_replaces_items_without_mutating_aliases_or_original_contract(tmp_path):
    original = json.dumps(REVIEW_V2, sort_keys=True)
    gateway = real_gateway(tmp_path)
    schema = gateway.review_schema()
    use_items = schema["properties"]["calculation_uses"]["items"]
    assert len(use_items["anyOf"]) == 3
    for branch in use_items["anyOf"]:
        assert branch["type"] == "object" and branch["additionalProperties"] is False
        assert set(branch["required"]) == set(branch["properties"])
    # The original validator still accepts structure and separately checks meaning.
    assert list(Draft202012Validator(REVIEW_V2["properties"]["calculation_uses"]["items"]).iter_errors(item(unresolved=True))) == []
    use_items["anyOf"][0]["properties"]["stated_value"]["enum"] = ["INDEPENDENT_COPY"]
    second = gateway.review_schema()
    assert "enum" not in second["properties"]["calculation_uses"]["items"]["anyOf"][0]["properties"]["stated_value"]
    assert json.dumps(REVIEW_V2, sort_keys=True) == original
    assert "enum" not in schema["properties"]["judgments"]["items"]["properties"]["conclusion"]
    for group in ("requests", "escalations"):
        blocking = schema["properties"][group]["items"]["properties"]["blocking"]
        assert "enum" not in blocking
        assert Draft202012Validator(blocking).is_valid(True)
        assert Draft202012Validator(blocking).is_valid(False)


def test_final_tool_and_text_review_share_constraint_and_legacy_flag_is_preserved(tmp_path):
    gateway = real_gateway(tmp_path)
    expected = gateway.review_schema()["properties"]["calculation_uses"]["items"]
    gateway.run.phase = "FINALIZING"
    tool_schema = gateway._schemas("FINALIZING")["submit_review"]
    assert tool_schema["properties"]["review"]["properties"]["calculation_uses"]["items"] == expected
    gateway.run.config["dynamic_submission_contract"] = False
    assert gateway.review_schema() == REVIEW_V2


def test_format_patch_repairs_shape_inside_selected_use_branch_only(tmp_path):
    use_schema = real_gateway(tmp_path).review_schema()["properties"]["calculation_uses"]["items"]
    schema = obj({"calculation_uses": arr(use_schema)})
    original = {"calculation_uses": [item()]}
    del original["calculation_uses"][0]["replacement_id"]
    original["calculation_uses"][0]["extra_format_key"] = None
    candidate = apply_format_patch(original, {"operations": [
        {"op": "ADD_EMPTY", "path": "/calculation_uses/0/replacement_id", "empty_kind": "NULL"},
        {"op": "REMOVE_EXTRA", "path": "/calculation_uses/0/extra_format_key"},
    ]}, schema)
    assert candidate == {"calculation_uses": [item()]}
    assert "replacement_id" not in original["calculation_uses"][0]


@pytest.mark.parametrize("value", [item(unresolved=True), item(replacement_id="OTHER_CALC"),
                                   item(use="REJECT", replacement_id=None, unresolved=False)])
def test_format_patch_never_repairs_calculation_selection_semantics(tmp_path, value):
    use_schema = real_gateway(tmp_path).review_schema()["properties"]["calculation_uses"]["items"]
    schema = obj({"calculation_uses": arr(use_schema)})
    original = {"calculation_uses": [value]}
    before = json.dumps(original, sort_keys=True)
    with pytest.raises(FormatPatchError):
        apply_format_patch(original, {"operations": []}, schema)
    assert json.dumps(original, sort_keys=True) == before
