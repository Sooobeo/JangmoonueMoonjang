"""Synthetic arithmetic tests. No case answer or grading criteria are imported."""

from copy import deepcopy
from decimal import Decimal, getcontext, ROUND_DOWN
import json

import pytest

from ipo_eval.calculations import calculate, sensitivity


@pytest.fixture
def sample():
    return {
        "earnings_million_krw": "50", "applied_per": "12",
        "reported_equity_million_krw": "600", "reported_price_krw": "600",
        "share_count": "1000000", "existing_shares": "800000",
        "new_shares": "150000", "dilutive_shares": "50000",
        "secondary_sale_shares": "100000",
        "peers": [
            {"name": "North", "per": "10", "market_cap_million_krw": "200", "earnings_million_krw": "20"},
            {"name": "East", "per": "12", "market_cap_million_krw": "240", "earnings_million_krw": "20"},
            {"name": "South", "per": "14", "market_cap_million_krw": "280", "earnings_million_krw": "20"},
            {"name": "West", "per": "20", "market_cap_million_krw": "400", "earnings_million_krw": "20"},
        ],
    }


def rows(inputs):
    return {row["id"]: row for row in calculate(inputs)["calculations"]}


def test_unit_conversion_and_secondary_sale_exclusion(sample):
    result = rows(sample)
    assert result["share_sum"]["result"] == "1000000"
    assert result["share_count_difference"]["result"] == "0"
    assert result["price_from_reported_equity"]["result"] == "600"
    assert result["price_from_displayed_per"]["result"] == "600"
    assert result["reported_price_difference"]["result"] == "0"
    sample["secondary_sale_shares"] = "999999999"
    assert rows(sample)["share_sum"]["result"] == "1000000"


def test_two_independent_peer_mean_routes(sample):
    result = rows(sample)
    assert result["peer_displayed_mean"]["result"] == "14"
    assert result["peer_displayed_median"]["result"] == "13"
    assert result["peer_recomputed_mean"]["result"] == "14"
    assert result["price_from_recomputed_peer_mean"]["result"] == "700"
    sample["peers"][0]["market_cap_million_krw"] = "210"
    result = rows(sample)
    assert result["peer_displayed_mean"]["result"] == "14"
    assert result["peer_recomputed_mean"]["result"] == "14.125"


def test_sensitivity_baseline_and_leave_one_out(sample):
    result = sensitivity(sample)
    assert result["baseline"]["result"] == "600"
    scenarios = {row["id"]: row for row in result["scenarios"]}
    assert scenarios["displayed_mean"]["result"] == "700"
    assert scenarios["displayed_mean"]["difference_krw"] == "100"
    assert scenarios["displayed_median"]["result"] == "650"
    assert scenarios["exclude_peer_4"]["result"] == "600"
    assert scenarios["exclude_peer_4"]["difference_percent"] == "0"
    assert all(row["assumption"] for row in scenarios.values())


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "1.5", "1e6", "1,00", True, 1000000])
def test_invalid_share_counts_do_not_produce_prices(sample, value):
    sample["share_count"] = value
    result = rows(sample)
    assert result["price_from_reported_equity"]["status"] == "INVALID"
    assert result["price_from_reported_equity"]["result"] is None
    assert sensitivity(sample)["baseline"]["status"] == "INVALID"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_shares_remain_missing(sample, value):
    sample["share_count"] = value
    assert rows(sample)["price_from_displayed_per"]["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("value", ["-1", "0", "NaN", "Infinity"])
def test_invalid_multiple_is_rejected(sample, value):
    sample["applied_per"] = value
    assert rows(sample)["price_from_displayed_per"]["status"] == "INVALID"
    sensitivity_result = sensitivity(sample)
    assert sensitivity_result["baseline"]["status"] == "INVALID"
    assert sensitivity_result["scenarios"][0]["status"] == "OK"
    assert sensitivity_result["scenarios"][0]["difference_percent"] is None


def test_missing_peer_not_silently_dropped(sample):
    sample["peers"][0]["per"] = None
    result = rows(sample)
    assert result["peer_displayed_mean"]["status"] == "UNAVAILABLE"
    assert result["peer_recomputed_mean"]["status"] == "OK"
    assert all(row["status"] == "UNAVAILABLE" for row in sensitivity(sample)["scenarios"])


def test_invalid_peer_not_silently_dropped(sample):
    sample["peers"][0]["per"] = "-10"
    sample["peers"][1]["per"] = None
    assert rows(sample)["peer_displayed_mean"]["status"] == "INVALID"
    assert all(row["status"] == "INVALID" for row in sensitivity(sample)["scenarios"])


def test_zero_peer_earnings_does_not_divide_by_zero(sample):
    sample["peers"][0]["earnings_million_krw"] = "0"
    result = rows(sample)
    assert result["peer_recomputed_per_1"]["status"] == "INVALID"
    assert result["peer_recomputed_mean"]["status"] == "INVALID"


@pytest.mark.parametrize("peers,status", [([], "UNAVAILABLE"), (None, "UNAVAILABLE"), ({}, "INVALID"), ([None], "INVALID")])
def test_bad_peer_list_is_explicit(sample, peers, status):
    sample["peers"] = peers
    assert rows(sample)["peer_displayed_mean"]["status"] == status
    assert sensitivity(sample)["scenarios"][0]["status"] == status


def test_duplicated_peer_cannot_count_twice(sample):
    sample["peers"][1]["name"] = " north "
    assert rows(sample)["peer_displayed_mean"]["status"] == "INVALID"


def test_single_peer_can_have_mean_but_no_leave_one_out(sample):
    sample["peers"] = sample["peers"][:1]
    result = sensitivity(sample)
    assert result["scenarios"][0]["status"] == "OK"
    assert result["scenarios"][2]["status"] == "UNAVAILABLE"


def test_odd_median_and_zero_components(sample):
    sample["peers"] = sample["peers"][:3]
    sample["existing_shares"] = "1000000"
    sample["new_shares"] = "0"
    sample["dilutive_shares"] = "0"
    result = rows(sample)
    assert result["peer_displayed_median"]["result"] == "12"
    assert result["share_sum"]["result"] == "1000000"


def test_negative_component_is_invalid(sample):
    sample["new_shares"] = "-1"
    assert rows(sample)["share_sum"]["status"] == "INVALID"


def test_invalid_secondary_sale_is_reported_but_missing_sale_is_not_needed(sample):
    sample["secondary_sale_shares"] = "-1"
    assert rows(sample)["share_sum"]["status"] == "INVALID"
    sample["secondary_sale_shares"] = None
    assert rows(sample)["share_sum"]["result"] == "1000000"


def test_missing_component_is_not_filled_with_zero(sample):
    del sample["dilutive_shares"]
    assert rows(sample)["share_sum"]["status"] == "UNAVAILABLE"


def test_comma_grouping_is_accepted_without_float_rounding(sample):
    sample["share_count"] = "1,000,000"
    sample["earnings_million_krw"] = "50.125"
    assert rows(sample)["price_from_displayed_per"]["result"] == "601.5"


def test_reported_rounding_gap_is_a_number_not_error_verdict(sample):
    sample["reported_equity_million_krw"] = "600.3"
    sample["reported_price_krw"] = "600"
    result = rows(sample)
    assert result["reported_price_difference"]["result"] == "0.3"
    assert result["reported_price_difference"]["status"] == "OK"
    assert result["implied_per"]["result"] == "12.006"


def test_empty_inputs_return_explanations():
    result = calculate({})
    assert all(row["status"] == "UNAVAILABLE" and row["reason"] for row in result["calculations"])


def test_no_input_mutation_and_json_serializable(sample):
    original = deepcopy(sample)
    json.dumps(calculate(sample), allow_nan=False)
    json.dumps(sensitivity(sample), allow_nan=False)
    assert sample == original


def test_reproducible_under_external_decimal_context(sample):
    sample["share_count"] = "3"
    original_precision = getcontext().prec
    original_rounding = getcontext().rounding
    try:
        reference = calculate(sample), sensitivity(sample)
        getcontext().prec = 6
        getcontext().rounding = ROUND_DOWN
        assert (calculate(sample), sensitivity(sample)) == reference
    finally:
        getcontext().prec = original_precision
        getcontext().rounding = original_rounding


def test_more_than_80_character_number_is_rejected(sample):
    sample["share_count"] = "1" * 81
    assert rows(sample)["price_from_displayed_per"]["status"] == "INVALID"


def test_non_dictionary_input_reports_programming_error():
    with pytest.raises(TypeError):
        calculate([])
    with pytest.raises(TypeError):
        sensitivity(None)
