"""Compact v2 shares declared context groups without inferring compatibility."""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator
import pytest

from ipo_eval.calculations_v2 import evaluate
from ipo_eval.format_patch import apply_format_patch
from ipo_eval.provenance import ContractError, SnapshotStore
from ipo_eval.wire_contract import EXTRACTION_WIRE
from ipo_eval.wire_contract_v2 import (EXTRACTION_WIRE_V2, REGISTER_WIRE_BATCH_V2,
    WIRE_INSTRUCTIONS_V2, expand_wire_extraction_v2, to_wire_extraction_v2)
from test_contracts_v2 import CHUNKS, ctx, fact
from test_wire_contract import sample, by_id


def test_grouped_transport_preserves_every_record_snapshot_calculation_and_input():
    original = sample()
    untouched = deepcopy(original)
    wire = to_wire_extraction_v2(original, CHUNKS)
    wire_before = deepcopy(wire)
    expanded = expand_wire_extraction_v2(wire, CHUNKS)
    assert by_id(expanded["records"]) == by_id(original["records"])
    assert expanded["document_version_notes"] == original["document_version_notes"]
    assert expanded["extraction_limits"] == original["extraction_limits"]
    assert to_wire_extraction_v2(expanded, CHUNKS) == wire
    before, after = SnapshotStore(CHUNKS), SnapshotStore(CHUNKS)
    before.register("X_EMPTY", original["records"])
    after.register("X_EMPTY", expanded["records"])
    assert before.current_id == after.current_id
    assert before.logical(before.current_id) == after.logical(after.current_id)
    assert evaluate(before, before.current_id) == evaluate(after, after.current_id)
    assert original == untouched and wire == wire_before


@pytest.mark.parametrize("key", ["as_of", "scope", "basis", "source_snapshot_id"])
def test_encoder_deduplicates_only_exact_group_tuple_not_similar_meaning(key):
    a, b, c = ctx("A", "주"), ctx("B", "원"), ctx("C", "배")
    b["payload"]["period"] = "different real flow period"
    c["payload"][key] += " "  # No stripping, semantic normalization or guessing.
    value = {"records": [a, b, c], "document_version_notes": [], "extraction_limits": []}
    wire = to_wire_extraction_v2(value, CHUNKS)
    assert len(wire["groups"]) == 2
    assert wire["contexts"][0]["g"] == wire["contexts"][1]["g"]
    assert wire["contexts"][2]["g"] != wire["contexts"][0]["g"]
    assert by_id(expand_wire_extraction_v2(wire, CHUNKS)["records"]) == by_id(value["records"])


def test_group_changes_expand_exactly_without_rewriting_unit_period_or_other_groups():
    value = sample()
    wire = to_wire_extraction_v2(value, CHUNKS)
    first = wire["groups"][0]
    first["s"] = "model-declared scope, not engine-certified equivalence"
    expanded = by_id(expand_wire_extraction_v2(wire, CHUNKS)["records"])
    for context in wire["contexts"]:
        p = expanded[context["id"]]["payload"]
        assert p["unit"] == context["u"] and p["period"] == context["p"]
        expected = next(g for g in wire["groups"] if g["id"] == context["g"])
        assert (p["as_of"], p["scope"], p["basis"], p["source_snapshot_id"]) == tuple(expected[k] for k in ("t", "s", "b", "src"))


@pytest.mark.parametrize("mutation", [
    lambda w: w.pop("groups"),
    lambda w: w["groups"].append(deepcopy(w["groups"][0])),
    lambda w: w["groups"][0].update(id=" "),
    lambda w: w["contexts"][0].update(g="UNKNOWN_PREVIOUS_BATCH_GROUP"),
    lambda w: w["contexts"][0].update(s="illegal per-context override"),
    lambda w: w["groups"][0].pop("src"),
    lambda w: w["groups"][0].update(extra="silently discard this"),
])
def test_invalid_group_definitions_fail_without_mutating_wire(mutation):
    wire = to_wire_extraction_v2(sample(), CHUNKS)
    mutation(wire)
    before = deepcopy(wire)
    with pytest.raises(ContractError) as exc:
        expand_wire_extraction_v2(wire, CHUNKS)
    assert exc.value.code == "INVALID_WIRE_CONTRACT"
    assert wire == before


def test_unused_valid_groups_are_raw_only_and_do_not_create_context_records():
    wire = to_wire_extraction_v2(sample(), CHUNKS)
    original = expand_wire_extraction_v2(wire, CHUNKS)
    wire["groups"].append({**wire["groups"][0], "id": "UNUSED_GROUP", "s": "unused model declaration"})
    before = deepcopy(wire)
    assert expand_wire_extraction_v2(wire, CHUNKS) == original
    assert wire == before


def test_incremental_batch_uses_existing_context_without_cross_batch_group_state():
    store = SnapshotStore(CHUNKS)
    store.register("X_EMPTY", [ctx()])
    delta = {"records": [fact("FRESH", "10")], "document_version_notes": [], "extraction_limits": []}
    wire = to_wire_extraction_v2(delta, CHUNKS)
    assert wire["groups"] == wire["contexts"] == []
    expanded = expand_wire_extraction_v2(wire, CHUNKS)
    store.register(store.current_id, expanded["records"])
    assert store.facts(store.current_id)["FRESH"]["value"] == "10"


def test_groups_do_not_fabricate_source_locations_or_missing_contexts():
    wire = to_wire_extraction_v2(sample(), CHUNKS)
    with pytest.raises(ContractError) as exc:
        expand_wire_extraction_v2(wire, {})
    assert exc.value.code == "UNREAD_EVIDENCE"
    wire["values"][0]["x"] = "UNKNOWN_CONTEXT"
    expanded = expand_wire_extraction_v2(wire, CHUNKS)
    assert by_id(expanded["records"])["P"]["payload"]["context_id"] == "UNKNOWN_CONTEXT"
    with pytest.raises(ContractError, match="Unknown context"):
        SnapshotStore(CHUNKS).register("X_EMPTY", expanded["records"])


def test_v2_schema_is_closed_without_union_and_does_not_change_v1_schema():
    before = json.dumps(EXTRACTION_WIRE, sort_keys=True)
    def walk(node):
        if isinstance(node, dict):
            assert "anyOf" not in node and "oneOf" not in node
            if node.get("type") == "object":
                assert set(node["required"]) == set(node["properties"])
                assert node["additionalProperties"] is False
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(EXTRACTION_WIRE_V2)
    request = {"operation": "REGISTER_BATCH", "base_snapshot_id": "X_EMPTY", "batch": to_wire_extraction_v2(sample(), CHUNKS)}
    Draft202012Validator(REGISTER_WIRE_BATCH_V2).validate(request)
    assert set(EXTRACTION_WIRE_V2["properties"]["contexts"]["items"]["properties"]) == {"id", "u", "p", "g"}
    assert set(EXTRACTION_WIRE_V2["properties"]["groups"]["items"]["properties"]) == {"id", "t", "s", "b", "src"}
    assert all(name in WIRE_INSTRUCTIONS_V2 for name in ("as_of", "scope", "basis", "source_snapshot_id", "unit", "period", "group_id"))
    assert json.dumps(EXTRACTION_WIRE, sort_keys=True) == before


def test_existing_compact_claim_patch_uses_grouped_schema_without_rewriting_groups():
    wire = to_wire_extraction_v2(sample(), CHUNKS)
    wire["values"][0]["ev"][0]["claim"] = "WRONG_LINK"
    groups = deepcopy(wire["groups"])
    repaired = apply_format_patch(wire, {"operations": [{"op": "RELINK_CLAIM", "path": "/values/0/ev/0/claim", "claim_id": wire["values"][0]["c"]}]}, EXTRACTION_WIRE_V2)
    assert repaired["groups"] == groups
    assert repaired["values"][0]["ev"][0]["claim"] == repaired["values"][0]["c"]
