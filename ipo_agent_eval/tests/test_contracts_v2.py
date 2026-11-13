"""Synthetic v2 contracts, atomicity and source-provenance checks."""
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from ipo_eval.provenance import ContractError, SnapshotStore
from ipo_eval.schemas_v2 import RECORD, FACT_V2, REVIEW_V2


CHUNKS = {"SYN-p1": {"doc_id": "SYN", "page": 1}}


def ev(claim):
    return {"doc_id": "SYN", "chunk_id": "SYN-p1", "page": 1, "claim_id": claim, "locator": "synthetic table"}


def rec(rid, record_kind, **payload):
    return {"record_id": rid, "kind": record_kind, "payload": payload}


def ctx(rid="CTX", unit="주", **extra):
    return rec(rid, "CONTEXT", **{"unit": unit, "period": "FY-SYN", "as_of": "2000-12-31",
                                 "scope": "SYN-CONSOLIDATED", "basis": "SYN-VALUATION",
                                 "source_snapshot_id": "SYN-FINAL", **extra})


def fact(rid="F", value="10", field="share_quantity", context="CTX", entity_id=None, **extra):
    return rec(rid, "VALUE", **{"field": field, "entity_id": entity_id, "claim_id": "C_" + rid,
                               "value": value, "context_id": context, "origin": "DISCLOSED",
                               "evidence": [ev("C_" + rid)], "missing_reason": None, "derivation_id": None, **extra})


def derivation(rid, output, operation, inputs, field, context, entity_id=None):
    return rec(rid, "DERIVATION", operation=operation, input_fact_ids=inputs, output_fact_id=output,
               field=field, entity_id=entity_id, context_id=context, claim_id="C_" + output)


def component(rid, fid, kind="EXISTING", treatment="INCLUDE", basis="PRE_OFFER_BASE"):
    return rec(rid, "SHARE_COMPONENT", fact_id=fid, kind=kind, denominator_treatment=treatment,
               treatment_reason="synthetic disclosed denominator", treatment_evidence=[ev("C_" + fid)],
               source_snapshot_id="SYN-FINAL", basis=basis)


def coverage(status="COMPLETE"):
    return rec("COV", "COVERAGE", coverage_status=status, reason="synthetic coverage", evidence=[ev("C_F")],
               source_snapshot_id="SYN-FINAL")


def market_records():
    return [ctx("CP", "원"), ctx("CS", "주"), ctx("CM", "백만원"), ctx("CR", "배"),
            fact("P", "20000", "reference_price_krw", "CP", "PEER"),
            fact("S", "5000000", "reference_shares", "CS", "PEER"),
            fact("E", "10000", "earnings_million_krw", "CM", "PEER"),
            derivation("D_CAP", "F_CAP", "MARKET_CAP", ["P", "S"], "market_cap_million_krw", "CM", "PEER"),
            derivation("D_PER", "F_PER", "PER", ["F_CAP", "E"], "per", "CR", "PEER")]


def test_v2_reading_does_not_modify_v1_contract():
    from ipo_eval.schemas import EXTRACTION, REVIEW
    from ipo_eval.validation import validate_extraction
    from test_workflow import extraction
    assert "records" not in EXTRACTION["properties"]
    assert "input_snapshot_id" not in REVIEW["properties"]
    chunks = {"TEST-DOC-p0001": {"doc_id": "TEST-DOC", "page": 1}}
    assert validate_extraction(extraction(), chunks) == []


def test_atomic_rejection_publishes_no_state_and_versions_are_immutable():
    store = SnapshotStore(CHUNKS)
    original = store.register("X_EMPTY", [ctx(), fact()])["input_snapshot_id"]
    old = store.get(original)
    with pytest.raises(ContractError):
        store.register(original, [fact("F", "20"), fact("BAD", "9", context="UNKNOWN")])
    assert store.current_id == original
    assert store.get(original) == old
    new = store.register(original, [fact("F", "20")])["input_snapshot_id"]
    assert new != original and store.get(new)["versions"]["F"] == 2
    assert store.facts(original)["F"]["value"] == "10"
    assert store.facts(new)["F"]["value"] == "20"
    tamper = store.get(new)
    tamper["records"].clear()
    assert store.get(new)["records"]
    with pytest.raises(ContractError, match="current immutable"):
        store.register(original, [fact("F", "30")])


def test_unknown_record_fields_and_wrong_discriminator_are_rejected():
    record = fact()
    record["payload"]["unexpected"] = "not allowed"
    assert list(Draft202012Validator(RECORD).iter_errors(record))
    record = fact()
    record["kind"] = "PEER"
    assert list(Draft202012Validator(RECORD).iter_errors(record))


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e3", "1,000", "", 10, True, "-1", "1.2"])
def test_bad_share_quantities_are_not_registered(value):
    store = SnapshotStore(CHUNKS)
    with pytest.raises(ContractError):
        store.register("X_EMPTY", [ctx(), fact(value=value)])
    assert store.current_id == "X_EMPTY"


def test_zero_unavailable_and_not_applicable_remain_distinct():
    store = SnapshotStore(CHUNKS)
    records = [ctx(), fact(value="0"), fact("U", None, origin="UNAVAILABLE", missing_reason="not read", evidence=[]),
               fact("NA", None, origin="NOT_APPLICABLE", missing_reason="not applicable", evidence=[])]
    sid = store.register("X_EMPTY", records)["input_snapshot_id"]
    facts = store.facts(sid)
    assert (facts["F"]["origin"], facts["F"]["value"]) == ("DISCLOSED", "0")
    assert facts["U"]["value"] is None and facts["NA"]["value"] is None
    for f in facts.values():
        assert list(Draft202012Validator(FACT_V2).iter_errors(f)) == []


def test_only_actually_read_pages_can_supply_evidence():
    store = SnapshotStore({})
    with pytest.raises(ContractError, match="actually read"):
        store.register("X_EMPTY", [ctx(), fact()])
    store.read_chunks.update(CHUNKS)
    assert store.register("X_EMPTY", [ctx(), fact()])["registered_ids"] == ["CTX", "F"]


def test_evidence_page_rejects_integral_float_as_well_as_boolean():
    for page in (1.0, True):
        record = fact()
        record["payload"]["evidence"][0]["page"] = page
        with pytest.raises(ContractError):
            SnapshotStore(CHUNKS).register("X_EMPTY", [ctx(), record])


def test_derived_value_chain_recomputes_and_retains_all_original_evidence():
    store = SnapshotStore(CHUNKS)
    sid = store.register("X_EMPTY", market_records())["input_snapshot_id"]
    logical = store.logical(sid)
    assert logical["facts"]["F_CAP"]["value"] == "100000"
    assert logical["facts"]["F_PER"]["value"] == "10"
    assert {x["claim_id"] for x in logical["facts"]["F_PER"]["evidence"]} == {"C_P", "C_S", "C_E"}
    assert all(row["input_snapshot_id"] == sid for row in logical["derivations"])
    for f in logical["facts"].values():
        assert list(Draft202012Validator(FACT_V2).iter_errors(f)) == []


def test_claimed_derived_result_cannot_override_arithmetic():
    store = SnapshotStore(CHUNKS)
    records = market_records() + [fact("F_CAP", "999", "market_cap_million_krw", "CM", "PEER", origin="DERIVED", derivation_id="D_CAP")]
    with pytest.raises(ContractError, match="differs from deterministic"):
        store.register("X_EMPTY", records)


def test_derived_origin_without_derivation_is_rejected():
    with pytest.raises(ContractError, match="matching derivation"):
        SnapshotStore(CHUNKS).register("X_EMPTY", [ctx(), fact(origin="DERIVED", evidence=[])])


def test_per_formula_cannot_reverse_same_unit_inputs():
    records = market_records()
    records[-1]["payload"]["input_fact_ids"] = ["E", "F_CAP"]
    with pytest.raises(ContractError, match="formula roles"):
        SnapshotStore(CHUNKS).register("X_EMPTY", records)


def test_derivations_do_not_mix_peer_entities_even_with_identical_contexts():
    store = SnapshotStore(CHUNKS)
    records = market_records()
    records[5]["payload"]["entity_id"] = "OTHER_PEER"
    sid = store.register("X_EMPTY", records)["input_snapshot_id"]
    assert store.facts(sid)["F_CAP"]["value"] is None
    assert store.logical(sid)["derivations"][0]["status"] == "INVALID"


def test_issuer_components_cannot_reuse_peer_share_facts():
    with pytest.raises(ContractError, match="peer quantity"):
        SnapshotStore(CHUNKS).register("X_EMPTY", [ctx(), fact(entity_id="PEER"), component("SC", "F")])


def test_preview_registration_is_exact_but_does_not_publish_state():
    store = SnapshotStore(CHUNKS)
    result = store.preview_register("X_EMPTY", [ctx(), fact()])
    assert store.current_id == "X_EMPTY" and len(store.export()["snapshots"]) == 1
    assert result == store.register("X_EMPTY", [ctx(), fact()])


def test_whitespace_derivation_claim_and_selection_reason_are_rejected():
    records = market_records()
    records[-1]["payload"]["claim_id"] = " "
    with pytest.raises(ContractError, match="claim ID"):
        SnapshotStore(CHUNKS).register("X_EMPTY", records)
    selection = rec("SEL", "SELECTION", field="share_count", entity_id=None, disclosed_fact_id=None,
                    selected_fact_id=None, disclosure_status="NOT_FOUND", usability="UNRESOLVED", selection_reason=" ")
    with pytest.raises(ContractError, match="reason"):
        SnapshotStore(CHUNKS).register("X_EMPTY", [selection])


def test_unknown_and_cyclic_derivation_inputs_are_rejected_atomically():
    store = SnapshotStore(CHUNKS)
    records = market_records()
    records[-1]["payload"]["input_fact_ids"] = ["UNKNOWN", "E"]
    with pytest.raises(ContractError, match="Unknown derivation"):
        store.register("X_EMPTY", records)
    records = market_records()
    records[-2]["payload"]["input_fact_ids"] = ["F_PER", "S"]
    with pytest.raises(ContractError, match="cycle"):
        store.register("X_EMPTY", records)
    assert store.current_id == "X_EMPTY"


def test_missing_inputs_and_incompatible_dates_preserve_unavailable_or_invalid():
    for missing, expected in [(True, "UNAVAILABLE"), (False, "INVALID")]:
        store = SnapshotStore(CHUNKS)
        records = market_records()
        if missing:
            records[5] = fact("S", None, "reference_shares", "CS", "PEER", origin="UNAVAILABLE", evidence=[], missing_reason="not found")
        else:
            records[1]["payload"]["as_of"] = "1999-12-31"
        sid = store.register("X_EMPTY", records)["input_snapshot_id"]
        row = next(d for d in store.logical(sid)["derivations"] if d["derivation_id"] == "D_CAP")
        assert row["status"] == expected and row["result"] is None


def test_share_components_reject_duplicate_facts_and_mixed_basis():
    records = [ctx(), fact(), component("SC", "F"), component("SC2", "F")]
    with pytest.raises(ContractError, match="two components"):
        SnapshotStore(CHUNKS).register("X_EMPTY", records)
    records = [ctx(), fact(), component("SC", "F", basis="POST_OFFER_TOTAL")]
    with pytest.raises(ContractError, match="basis"):
        SnapshotStore(CHUNKS).register("X_EMPTY", records)


def test_derived_share_count_requires_coverage_and_inclusion_not_null_exclusion():
    records = [ctx(), fact(), component("SC", "F"), coverage(),
               fact("UNKNOWN_SECONDARY", None, origin="UNAVAILABLE", missing_reason="not found", evidence=[]),
               component("SC_SECONDARY", "UNKNOWN_SECONDARY", "SECONDARY_SALE", "EXCLUDE", "INCREMENT"),
               derivation("D_SHARES", "DS", "SHARE_SUM", ["F"], "derived_share_count", "CTX")]
    store = SnapshotStore(CHUNKS)
    sid = store.register("X_EMPTY", records)["input_snapshot_id"]
    assert store.facts(sid)["DS"]["value"] == "10"
    sid = store.register(sid, [coverage("INCOMPLETE")])["input_snapshot_id"]
    assert store.facts(sid)["DS"]["value"] is None


def test_not_found_original_can_select_a_valid_derivation_without_external_request():
    store = SnapshotStore(CHUNKS)
    records = market_records() + [fact("CAP_MISSING", None, "market_cap_million_krw", "CM", "PEER",
                                      origin="UNAVAILABLE", evidence=[], missing_reason="no direct cap found"),
        rec("SEL", "SELECTION", field="market_cap_million_krw", entity_id="PEER", disclosed_fact_id="CAP_MISSING",
            selected_fact_id="F_CAP", disclosure_status="NOT_FOUND", usability="DERIVABLE", selection_reason="same basis price times shares")]
    sid = store.register("X_EMPTY", records)["input_snapshot_id"]
    assert store.logical(sid)["selections"][0]["usability"] == "DERIVABLE"
    assert store.facts(sid)["CAP_MISSING"]["value"] is None


def test_malformed_peer_and_duplicate_entity_selections_rejected():
    store = SnapshotStore(CHUNKS)
    peer = rec("PEER", "PEER", name="Synthetic", per_fact_id="P", market_cap_fact_id=None,
               earnings_fact_id=None, reference_price_fact_id=None, reference_shares_fact_id=None)
    with pytest.raises(ContractError, match="mismatched"):
        store.register("X_EMPTY", market_records() + [peer])


def test_all_objects_in_transmission_schemas_are_strict_and_all_keys_required():
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)
    check(RECORD)
    check(REVIEW_V2)
