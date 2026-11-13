import json
from decimal import Decimal

import pytest
from scripts.audit_costs import audit_all, audit_run, price_usage


def usage(total=1000, cached=100, writes=200, output=300, reasoning=50):
    return {"input_tokens": total, "input_tokens_details": {"cached_tokens": cached, "cache_write_tokens": writes},
            "output_tokens": output, "output_tokens_details": {"reasoning_tokens": reasoning}}


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_cache_write_replaces_ordinary_input_and_reasoning_is_not_added_twice():
    result = price_usage(usage())
    assert result["ordinary_input_tokens"] == 700
    assert Decimal(result["estimated_cost_usd"]) == Decimal("0.002455")
    assert Decimal(result["cost_components_usd"]["output"]) == Decimal("0.0015")


def test_mixed_ttl_breakdown_takes_precedence_over_default():
    u = usage()
    u["input_tokens_details"]["cache_write_tokens_details"] = {"ttl_30m_tokens": 120, "ttl_12h_tokens": 80}
    result = price_usage(u)
    assert result["cache_write_30m_tokens"] == 120
    assert result["cache_write_12h_tokens"] == 80
    assert Decimal(result["estimated_cost_usd"]) == Decimal("0.002555")


def test_request_12h_when_response_has_no_ttl_split():
    result = price_usage(usage(), "12h")
    assert result["cache_write_12h_tokens"] == 200
    assert result["cache_write_30m_tokens"] == 0


@pytest.mark.parametrize("field,value", [("input_tokens", -1), ("input_tokens", True), ("output_tokens", "3"), ("input_tokens", 272001)])
def test_reject_invalid_top_level_counts_and_unsupported_long_context(field, value):
    u = usage()
    u[field] = value
    with pytest.raises(ValueError):
        price_usage(u)


def test_reject_overlapping_cache_counts():
    with pytest.raises(ValueError):
        price_usage(usage(total=100, cached=80, writes=40))


def test_reject_bad_ttl_split():
    u = usage()
    u["input_tokens_details"]["cache_write_tokens_details"] = {"ttl_30m_tokens": 1, "ttl_12h_tokens": 2}
    with pytest.raises(ValueError):
        price_usage(u)


def test_reject_reasoning_larger_than_output():
    with pytest.raises(ValueError):
        price_usage(usage(output=5, reasoning=6))


def test_missing_usage_is_unknown_not_zero_bill(tmp_path):
    write(tmp_path / "summary.json", {"model_calls": 1, "execution_status": "FAILED"})
    result = audit_run(tmp_path)
    assert result["requests_without_usage"] == 1
    assert result["known_usage_cost_usd"] is None
    assert not result["all_model_requests_have_usage"]


def test_preflight_has_no_model_requests(tmp_path):
    write(tmp_path / "summary.json", {"model_calls": 0, "execution_status": "PREFLIGHT_COMPLETE"})
    result = audit_run(tmp_path)
    assert result["known_usage_cost_usd"] == "0"
    assert result["requests_without_usage"] == 0


def test_incomplete_response_is_billed_in_known_usage_and_original_files_unchanged(tmp_path):
    run = tmp_path / "test_run"
    run.mkdir()
    response = run / "01_review_response.json"
    summary = run / "summary.json"
    write(response, {"id": "r_test", "model": "gpt-6.1-terra", "status": "incomplete", "usage": usage()})
    write(summary, {"model_calls": 1, "execution_status": "FAILED"})
    before = {p.name: p.read_bytes() for p in run.iterdir()}
    audit = audit_all(tmp_path)
    assert Decimal(audit["known_usage_cost_usd"]) == Decimal("0.002455")
    assert audit["known_usage_cost_krw"] == "3.44"
    assert audit["groups"]["failed_with_usage"]["run_count"] == 1
    assert Decimal(audit["groups"]["failed_with_usage"]["known_usage_cost_usd"]) == Decimal("0.002455")
    assert audit["groups"]["submitted"]["run_count"] == 0
    assert not audit["is_invoice"]
    assert before == {p.name: p.read_bytes() for p in run.iterdir()}


def test_unknown_model_never_uses_terra_price(tmp_path):
    write(tmp_path / "summary.json", {"model_calls": 1, "execution_status": "FAILED"})
    write(tmp_path / "01_review_response.json", {"id": "r_test", "model": "another-model", "usage": usage()})
    with pytest.raises(ValueError):
        audit_run(tmp_path)


def test_no_usage_response_is_unconfirmed(tmp_path):
    write(tmp_path / "summary.json", {"model_calls": 1, "execution_status": "FAILED"})
    write(tmp_path / "01_review_response.json", {"id": "r_test", "model": "gpt-6.1-terra", "usage": None})
    assert audit_run(tmp_path)["known_usage_cost_usd"] is None


def test_actual_failed_run_usage_arithmetic_synthetic_copy():
    u = usage(total=97369, cached=0, writes=97363, output=9939, reasoning=563)
    result = price_usage(u)
    assert result["ordinary_input_tokens"] == 6
    assert Decimal(result["estimated_cost_usd"]) == Decimal("0.17140475")
