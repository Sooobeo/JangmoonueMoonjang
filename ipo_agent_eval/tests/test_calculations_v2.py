"""Design T01-T10 arithmetic and common sensitivity behavior."""
from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from ipo_eval.calculations_v2 import evaluate, sensitivity
from ipo_eval.provenance import ContractError, SnapshotStore
from test_contracts_v2 import CHUNKS, ctx, fact, rec, ev, component, coverage, market_records


def rows(result):
    return {r["id"]: r for r in result["calculations"]}


def share_store(quantities, kinds=None, treatments=None):
    kinds = kinds or ["EXISTING"] + ["PRIMARY_NEW"] * (len(quantities) - 1)
    treatments = treatments or ["INCLUDE"] * len(quantities)
    records = [ctx()]
    for i, (q, k, t) in enumerate(zip(quantities, kinds, treatments)):
        fid = "F" if i == 0 else "F" + str(i)
        records += [fact(fid, q, **({"origin": "UNAVAILABLE", "missing_reason": "not found", "evidence": []} if q is None else {})),
                    component("SC" + str(i), fid, k, t, "PRE_OFFER_BASE" if k == "EXISTING" else "INCREMENT")]
    records.append(coverage())
    store = SnapshotStore(CHUNKS)
    store.register("X_EMPTY", records)
    return store


@pytest.mark.parametrize("quantities,kinds,treatments,expected", [
    (["10000000", "2500000", "75000", "160000"], ["EXISTING", "PRIMARY_NEW", "MANDATORY_UNDERWRITER", "OPTION"],
     ["INCLUDE"] * 4, "12735000"),
    (["12630528", "2228917", "22290", "400000"], ["EXISTING", "PRIMARY_NEW", "ADDITIONAL_UNDERWRITER", "OPTION"],
     ["INCLUDE", "INCLUDE", "INCLUDE", "EXCLUDE"], "14881735"),
])
def test_T01_T02_pilot_arithmetic(quantities, kinds, treatments, expected):
    store = share_store(quantities, kinds, treatments)
    row = rows(evaluate(store, store.current_id))["share_sum"]
    assert row["result"] == expected and row["status"] == "OK"
    assert row["input_snapshot_id"] == store.current_id and row["evidence"]


def test_T03_option_inclusion_follows_caller_declaration():
    store = share_store(["100", "20"], ["EXISTING", "OPTION"], ["INCLUDE", "EXCLUDE"])
    assert rows(evaluate(store, store.current_id))["share_sum"]["result"] == "100"
    store.register(store.current_id, [component("SC1", "F1", "OPTION", "INCLUDE", "INCREMENT")])
    assert rows(evaluate(store, store.current_id))["share_sum"]["result"] == "120"


@pytest.mark.parametrize("condition,expected", [("excluded", "10"), ("incomplete", None), ("unresolved", None), ("missing", None)])
def test_T04_null_exclusion_and_incomplete_denominators(condition, expected):
    store = share_store(["10", None], ["EXISTING", "SECONDARY_SALE" if condition == "excluded" else "OPTION"],
                        ["INCLUDE", "EXCLUDE" if condition == "excluded" else "UNRESOLVED" if condition == "unresolved" else "INCLUDE"])
    if condition == "incomplete":
        store.register(store.current_id, [coverage("INCOMPLETE")])
    row = rows(evaluate(store, store.current_id))["share_sum"]
    assert row["result"] == expected
    assert row["partial_sum"] == "10"


def peer_record(per="F_PER", cap=None):
    return rec("PEER", "PEER", name="Synthetic peer", per_fact_id=per, market_cap_fact_id=cap,
               earnings_fact_id="E", reference_price_fact_id="P", reference_shares_fact_id="S")


def test_T06_T09_cap_and_per_derive_from_raw_inputs_without_missing_direct_value_block():
    store = SnapshotStore(CHUNKS)
    store.register("X_EMPTY", market_records()[:7] + [peer_record(per=None)])
    result = rows(evaluate(store, store.current_id))
    assert result["peer_market_cap"]["result"] == "100000"
    assert result["peer_recomputed_per"]["result"] == "10"
    assert set(result["peer_recomputed_per"]["input_fact_ids"]) == {"P", "S", "E"}
    assert set(e["claim_id"] for e in result["peer_recomputed_per"]["evidence"]) == {"C_P", "C_S", "C_E"}


def test_T07_mismatching_reference_dates_do_not_produce_cap_or_per():
    store = SnapshotStore(CHUNKS)
    records = market_records()[:7] + [peer_record(per=None)]
    records[1]["payload"]["as_of"] = "2001-01-01"
    store.register("X_EMPTY", records)
    result = rows(evaluate(store, store.current_id))
    assert result["peer_market_cap"]["status"] == "INVALID"
    assert result["peer_market_cap"]["result"] is None
    assert result["peer_recomputed_per"]["result"] is None


def test_T08_direct_and_derived_disagreement_is_retained_and_requires_selection():
    store = SnapshotStore(CHUNKS)
    store.register("X_EMPTY", market_records()[:7] + [fact("DIRECT", "90000", "market_cap_million_krw", "CM", "PEER"), peer_record(per=None, cap="DIRECT")])
    result = rows(evaluate(store, store.current_id))
    assert result["peer_market_cap_difference"]["result"] == "10000"
    assert result["peer_recomputed_per"]["status"] == "UNAVAILABLE"
    store.register(store.current_id, [rec("SEL", "SELECTION", field="market_cap_million_krw", entity_id="PEER",
        disclosed_fact_id="DIRECT", selected_fact_id="DIRECT", disclosure_status="PRESENT", usability="DIRECT", selection_reason="use disclosed basis")])
    result = rows(evaluate(store, store.current_id))
    assert result["peer_recomputed_per"]["result"] == "9"
    assert store.facts(store.current_id)["DIRECT"]["value"] == "90000"
    assert result["peer_market_cap"]["result"] == "100000"


def test_T10_calculation_ids_are_immutable_per_snapshot_and_inputs_do_not_change():
    store = share_store(["10"])
    old = store.current_id
    first = evaluate(store, old)
    before = store.export()
    assert evaluate(store, old) == first
    assert store.export() == before
    store.register(old, [fact("F", "20")])
    assert rows(evaluate(store, store.current_id))["share_sum"]["calc_id"] != rows(first)["share_sum"]["calc_id"]
    assert rows(evaluate(store, old))["share_sum"]["result"] == "10"


def valuation_store():
    store = SnapshotStore(CHUNKS)
    records = [ctx("CM", "백만원"), ctx("CR", "배"), ctx("CS", "주"), ctx("CP", "원"),
               fact("E", "50", "earnings_million_krw", "CM"), fact("AP", "10", "applied_per", "CR"),
               fact("EQ", "500", "reported_equity_million_krw", "CM"), fact("SH", "100000", "reported_share_count", "CS"),
               fact("PR", "5000", "reported_price_krw", "CP")]
    for i, multiple in enumerate(["10", "20", "30"]):
        entity = "P" + str(i)
        fid = "PER" + str(i)
        records += [fact(fid, multiple, "per", "CR", entity),
                    rec(entity, "PEER", name="Synthetic " + entity, per_fact_id=fid, market_cap_fact_id=None,
                        earnings_fact_id=None, reference_price_fact_id=None, reference_shares_fact_id=None)]
    store.register("X_EMPTY", records)
    return store


def competing_denominator_store():
    """Synthetic disclosed/derived denominators intentionally disagree."""
    store = valuation_store()
    store.register(store.current_id, [
        fact("EX", "150000", "existing_shares", "CS"),
        fact("NEW", "50000", "new_shares", "CS"),
        component("SC_EX", "EX", "EXISTING", "INCLUDE", "PRE_OFFER_BASE"),
        component("SC_NEW", "NEW", "PRIMARY_NEW", "INCLUDE", "INCREMENT"),
        rec("COV", "COVERAGE", coverage_status="COMPLETE", reason="synthetic components complete",
            evidence=[ev("C_EX")], source_snapshot_id="SYN-FINAL"),
        rec("D_SH", "DERIVATION", operation="SHARE_SUM", input_fact_ids=["EX", "NEW"],
            output_fact_id="DERIVED_SH", field="derived_share_count", entity_id=None,
            context_id="CS", claim_id="CLAIM_DERIVED_SH"),
        rec("SEL_REPORTED", "SELECTION", field="reported_share_count", entity_id=None,
            disclosed_fact_id="SH", selected_fact_id="SH", disclosure_status="PRESENT",
            usability="DIRECT", selection_reason="preserve reported denominator"),
        rec("SEL_DERIVED", "SELECTION", field="derived_share_count", entity_id=None,
            disclosed_fact_id=None, selected_fact_id="DERIVED_SH", disclosure_status="NOT_FOUND",
            usability="DERIVABLE", selection_reason="preserve component-sum denominator"),
    ])
    return store


@pytest.mark.parametrize("chosen,usability,expected", [
    ("SH", "DIRECT", "5000"), ("DERIVED_SH", "DERIVABLE", "2500")])
def test_exact_share_count_selection_wins_over_individual_alias_selections(chosen, usability, expected):
    store = competing_denominator_store()
    old = store.current_id
    assert rows(evaluate(store, old))["price_from_displayed_per"]["status"] == "UNAVAILABLE"
    store.register(old, [rec("SEL_ROLE", "SELECTION", field="share_count", entity_id=None,
        disclosed_fact_id="SH", selected_fact_id=chosen, disclosure_status="PRESENT",
        usability=usability, selection_reason="model explicitly chooses valuation denominator")])
    current = rows(evaluate(store, store.current_id))
    assert current["price_from_displayed_per"]["result"] == expected
    assert chosen in current["price_from_displayed_per"]["operand_fact_ids"]
    assert rows(sensitivity(store, store.current_id))["sensitivity_baseline"]["result"] == expected
    assert rows(evaluate(store, old))["price_from_displayed_per"]["status"] == "UNAVAILABLE"
    assert store.facts(store.current_id)["SH"]["value"] == "100000"
    assert store.facts(store.current_id)["DERIVED_SH"]["value"] == "200000"


def test_exact_unresolved_share_count_is_not_replaced_by_usable_alias_choices():
    store = competing_denominator_store()
    store.register(store.current_id, [rec("SEL_ROLE", "SELECTION", field="share_count", entity_id=None,
        disclosed_fact_id="SH", selected_fact_id=None, disclosure_status="PRESENT",
        usability="UNRESOLVED", selection_reason="model has not chosen a comparable denominator")])
    assert rows(evaluate(store, store.current_id))["price_from_displayed_per"]["status"] == "UNAVAILABLE"
    assert rows(sensitivity(store, store.current_id))["sensitivity_baseline"]["result"] is None


def test_absent_exact_share_count_preserves_ambiguous_alias_behavior():
    store = competing_denominator_store()
    price = rows(evaluate(store, store.current_id))["price_from_displayed_per"]
    assert price["status"] == "UNAVAILABLE" and price["selection_required"]
    assert "share_count.selection" in price["required_fields"]


def test_existing_prices_aggregates_and_sensitivities_remain_decimal_reproducible():
    store = valuation_store()
    result = rows(evaluate(store, store.current_id))
    assert result["price_from_reported_equity"]["result"] == "5000"
    assert result["price_from_displayed_per"]["result"] == "5000"
    assert result["reported_price_difference"]["result"] == "0"
    assert result["implied_per"]["result"] == "10"
    assert result["peer_displayed_mean"]["result"] == "20"
    assert result["peer_displayed_median"]["result"] == "20"
    alternatives = rows(sensitivity(store, store.current_id))
    assert alternatives["sensitivity_baseline"]["result"] == "5000"
    assert alternatives["sensitivity_displayed_mean"]["result"] == "10000"
    assert alternatives["sensitivity_displayed_median"]["result"] == "10000"
    assert alternatives["sensitivity_exclude_peer_1"]["result"] == "12500"
    assert alternatives["sensitivity_exclude_peer_3"]["result"] == "7500"
    with localcontext() as context:
        context.prec = 3
        assert rows(sensitivity(store, store.current_id)) == alternatives


def test_missing_peer_is_never_silently_dropped_from_aggregate_or_sensitivity():
    store = valuation_store()
    store.register(store.current_id, [fact("PER1", None, "per", "CR", "P1", origin="UNAVAILABLE", missing_reason="not read", evidence=[])])
    assert rows(evaluate(store, store.current_id))["peer_displayed_mean"]["status"] == "UNAVAILABLE"
    assert all(row["status"] == "UNAVAILABLE" for row in sensitivity(store, store.current_id)["scenarios"])


def test_negative_profit_is_invalid_and_not_an_automatic_method_switch():
    store = valuation_store()
    store.register(store.current_id, [fact("E", "-5", "earnings_million_krw", "CM")])
    assert rows(evaluate(store, store.current_id))["price_from_displayed_per"]["status"] == "INVALID"
    assert rows(sensitivity(store, store.current_id))["sensitivity_baseline"]["status"] == "INVALID"


def test_unknown_formula_and_alternative_rejected():
    store = SnapshotStore()
    with pytest.raises(ContractError):
        evaluate(store, "X_EMPTY", ["eval(user_text)"])
    with pytest.raises(ContractError):
        sensitivity(store, "X_EMPTY", ["arbitrary"])


def test_sensitivity_only_returns_selected_alternatives():
    store = valuation_store()
    result = sensitivity(store, store.current_id, ["MEDIAN"])
    assert [r["id"] for r in result["calculations"]] == ["sensitivity_baseline", "sensitivity_displayed_median"]


def test_unavailable_outputs_identify_missing_registered_ids_and_unregistered_roles():
    store = SnapshotStore(CHUNKS)
    store.register("X_EMPTY", market_records()[:7] + [peer_record(per=None)])
    store.register(store.current_id, [fact("S", None, "reference_shares", "CS", "PEER", origin="UNAVAILABLE", evidence=[], missing_reason="not found")])
    result = rows(evaluate(store, store.current_id))
    assert result["peer_market_cap"]["missing_input_ids"] == ["S"]
    assert result["peer_recomputed_per"]["missing_input_ids"] == ["S"]
    assert "share_count" in result["price_from_reported_equity"]["required_fields"]
    assert "share_components" in result["share_sum"]["required_fields"]


def test_ambiguous_cap_reports_explicit_selection_requirement():
    store = SnapshotStore(CHUNKS)
    store.register("X_EMPTY", market_records()[:7] + [fact("DIRECT", "90000", "market_cap_million_krw", "CM", "PEER"), peer_record(per=None, cap="DIRECT")])
    row = rows(evaluate(store, store.current_id))["peer_recomputed_per"]
    assert row["selection_required"] and "SELECTION required" in row["reason"]
    assert row["required_fields"] == ["PEER.market_cap_million_krw.selection"]
