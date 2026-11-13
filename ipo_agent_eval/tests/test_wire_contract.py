"""Lossless compact transport and unchanged v2 semantic rejection paths."""
from copy import deepcopy
import json

import pytest
import tiktoken
from jsonschema import Draft202012Validator

from ipo_eval.calculations_v2 import evaluate
from ipo_eval.provenance import ContractError, SnapshotStore
from ipo_eval.schemas_v2 import PAYLOADS
from ipo_eval.wire_contract import (EXTRACTION_WIRE, REGISTER_WIRE_BATCH, WIRE_INSTRUCTIONS,
                                   WIRE_LAYOUT, expand_wire_extraction, to_wire_extraction)
from test_contracts_v2 import CHUNKS, component, coverage, ctx, ev, fact, market_records, rec


def sample():
    records = market_records() + [
        rec("PEER", "PEER", name="Synthetic peer", per_fact_id="F_PER", market_cap_fact_id="F_CAP",
            earnings_fact_id="E", reference_price_fact_id="P", reference_shares_fact_id="S"),
        ctx(), fact(value="+0010.000"), component("SC", "F"), coverage(),
        fact("ZERO", "0"),
        fact("MISSING", None, origin="UNAVAILABLE", missing_reason="not read, not zero", evidence=[]),
        fact("NA", None, origin="NOT_APPLICABLE", missing_reason="not applicable", evidence=[]),
        fact("DIRECT", "90000.000", "market_cap_million_krw", "CM", "PEER"),
        rec("SEL", "SELECTION", field="market_cap_million_krw", entity_id="PEER",
            disclosed_fact_id="DIRECT", selected_fact_id="F_CAP", disclosure_status="PRESENT",
            usability="DERIVABLE", selection_reason="Keep disclosed 90000 and select recomputed 100000"),
    ]
    return {"records": records, "document_version_notes": ["Synthetic corrected filing; not a real case"],
            "extraction_limits": ["No economic conclusions supplied by the adapter"]}


def by_id(records):
    return {r["record_id"]: r for r in records}


def test_roundtrip_preserves_all_payload_fields_and_snapshot_identity_and_calculations():
    value = sample()
    original, read_original = deepcopy(value), deepcopy(CHUNKS)
    wire = to_wire_extraction(value, CHUNKS)
    wire_original = deepcopy(wire)
    expanded = expand_wire_extraction(wire, CHUNKS)
    assert by_id(expanded["records"]) == by_id(value["records"])
    assert expanded["document_version_notes"] == value["document_version_notes"]
    assert expanded["extraction_limits"] == value["extraction_limits"]
    assert to_wire_extraction(expanded, CHUNKS) == wire
    old, new = SnapshotStore(CHUNKS), SnapshotStore(CHUNKS)
    old.register("X_EMPTY", value["records"])
    new.register("X_EMPTY", expanded["records"])
    assert old.current_id == new.current_id
    assert old.get(old.current_id) == new.get(new.current_id)
    assert old.logical(old.current_id) == new.logical(new.current_id)
    assert evaluate(old, old.current_id) == evaluate(new, new.current_id)
    assert value == original and wire == wire_original and CHUNKS == read_original


def test_output_is_detached_and_does_not_normalize_decimal_text_or_evidence():
    value = sample()
    value["records"][4]["payload"]["evidence"] *= 2
    wire = to_wire_extraction(value, CHUNKS)
    expanded = expand_wire_extraction(wire, CHUNKS)
    assert by_id(expanded["records"])["F"]["payload"]["value"] == "+0010.000"
    assert by_id(expanded["records"])["P"]["payload"]["evidence"] == [ev("C_P")] * 2
    expanded["records"][0]["payload"]["period"] = "changed"
    expanded["document_version_notes"].append("changed")
    assert value["records"][0]["payload"]["period"] == "FY-SYN"
    assert "changed" not in wire["notes"]


def test_schema_has_no_union_and_aliases_cover_every_original_payload_field():
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
    walk(EXTRACTION_WIRE)
    assert EXTRACTION_WIRE["type"] == "object"
    for group, (kind, aliases) in WIRE_LAYOUT.items():
        assert len(aliases) == len(set(aliases.values()))
        assert set(aliases.values()) == set(PAYLOADS[kind]["properties"])
        assert list(EXTRACTION_WIRE["properties"][group]["items"]["properties"])[0] == "id"
        assert all(full in WIRE_INSTRUCTIONS for full in aliases.values())
    fields = list(EXTRACTION_WIRE["properties"]["values"]["items"]["properties"])
    assert fields.index("m") < fields.index("ev") and fields.index("d") < fields.index("ev")
    request = {"operation": "REGISTER_BATCH", "base_snapshot_id": "X_EMPTY",
               "batch": to_wire_extraction(sample(), CHUNKS)}
    assert not list(Draft202012Validator(REGISTER_WIRE_BATCH).iter_errors(request))


@pytest.mark.parametrize("mutation", [
    lambda w: w.pop("limits"),
    lambda w: w.update(extra="silently ignore this"),
    lambda w: w["values"][0].pop("m"),
    lambda w: w["values"][0].update(v=20000),
    lambda w: w["values"][0]["ev"][0].update(page=1),
    lambda w: w["values"][0].update(o="GUESSED"),
])
def test_invalid_transport_is_rejected_without_defaults_or_silent_key_loss(mutation):
    wire = to_wire_extraction(sample(), CHUNKS)
    mutation(wire)
    with pytest.raises(ContractError) as exc:
        expand_wire_extraction(wire, CHUNKS)
    assert exc.value.code == "INVALID_WIRE_CONTRACT"


@pytest.mark.parametrize("chunks", [{}, {"SYN-p1": {"doc_id": "SYN", "page": 1.0}},
    {"SYN-p1": {"doc_id": "SYN", "page": True}}, {"SYN-p1": {"doc_id": "SYN", "page": 0}},
    {"SYN-p1": {"doc_id": "", "page": 1}},
    {"SYN-p1": {"doc_id": "SYN", "page": 1, "chunk_id": "OTHER"}}])
def test_only_actual_valid_read_coordinates_can_be_expanded(chunks):
    wire = to_wire_extraction(sample(), CHUNKS)
    with pytest.raises(ContractError) as exc:
        expand_wire_extraction(wire, chunks)
    assert exc.value.code == "UNREAD_EVIDENCE"


@pytest.mark.parametrize("changed", [{"page": 2}, {"page": 1.0}, {"doc_id": "OTHER"}, {"chunk_id": "UNREAD"}])
def test_encoder_rejects_bad_coordinates_instead_of_repairing_them(changed):
    value = sample()
    value["records"][4]["payload"]["evidence"][0].update(changed)
    with pytest.raises(ContractError) as exc:
        to_wire_extraction(value, CHUNKS)
    assert exc.value.code == "UNREAD_EVIDENCE"


def test_cross_kind_duplicate_ids_do_not_overwrite_records():
    wire = to_wire_extraction(sample(), CHUNKS)
    wire["peers"][0]["id"] = wire["contexts"][0]["id"]
    with pytest.raises(ContractError, match="unique"):
        expand_wire_extraction(wire, CHUNKS)
    value = sample()
    value["records"].append(deepcopy(value["records"][0]))
    with pytest.raises(ContractError, match="unique"):
        to_wire_extraction(value, CHUNKS)


def test_transport_does_not_supply_missing_records_or_make_semantic_decisions():
    wire = to_wire_extraction(sample(), CHUNKS)
    wire["values"][0]["x"] = "NOT_REGISTERED"
    expanded = expand_wire_extraction(wire, CHUNKS)
    assert by_id(expanded["records"])["P"]["payload"]["context_id"] == "NOT_REGISTERED"
    store = SnapshotStore(CHUNKS)
    with pytest.raises(ContractError, match="Unknown context"):
        store.register("X_EMPTY", expanded["records"])
    assert store.current_id == "X_EMPTY"


def test_incorrect_derived_claim_is_not_recalculated_into_acceptability():
    value = sample()
    value["records"].append(fact("F_CAP", "999", "market_cap_million_krw", "CM", "PEER",
        origin="DERIVED", derivation_id="D_CAP", evidence=[]))
    expanded = expand_wire_extraction(to_wire_extraction(value, CHUNKS), CHUNKS)
    assert by_id(expanded["records"])["F_CAP"]["payload"]["value"] == "999"
    with pytest.raises(ContractError, match="differs from deterministic"):
        SnapshotStore(CHUNKS).register("X_EMPTY", expanded["records"])


def test_compact_output_reduces_measured_tokens_for_same_registered_payload():
    value = sample()
    wire = to_wire_extraction(value, CHUNKS)
    encoding = tiktoken.get_encoding("o200k_base")
    tokens = lambda obj: len(encoding.encode(json.dumps(obj, ensure_ascii=False, separators=(",", ":"))))
    # Same literal values/IDs/claims, both JSONs minified: measures the transport,
    # not prettier-printing, omission of records or an easier financial case.
    assert tokens(wire) < tokens(value) * 0.80
    assert len(by_id(expand_wire_extraction(wire, CHUNKS)["records"])) == len(value["records"])
