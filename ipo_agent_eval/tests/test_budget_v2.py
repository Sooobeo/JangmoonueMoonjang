"""Reservation boundary tests are independent of model response quality."""
from types import SimpleNamespace

import pytest

from ipo_eval.budget import BudgetError, check_request, exploration_output_limit


def state(**overrides):
    config = {"max_format_repairs": 1, "format_repair_input_reserve": 16000,
              "format_repair_output_max": 2500, "review_output_max": 8500,
              "finalization_seconds_reserve": 120, "repair_seconds_reserve": 60,
              "max_model_calls": 16, "max_tool_calls": 40, "input_tokens_target_max": 160000,
              "output_tokens_max": 16000, "price_input_per_million_usd": 1,
              "price_output_per_million_usd": 5, "max_run_usd": .3, "exploration_output_max": 1000}
    return SimpleNamespace(**{**dict(config=config, repairs=0, model_calls=0, tool_calls=0,
        input_tokens=0, output_tokens=0, cost_ceiling_usd=0, remaining_time=lambda: 600), **overrides})


@pytest.mark.parametrize("overrides,code", [
    ({"output_tokens": 5000}, "OUTPUT_RESERVATION"),
    ({"model_calls": 14}, "MODEL_CALL_RESERVATION"),
    ({"tool_calls": 36}, "TOOL_CALL_RESERVATION"),
    ({"remaining_time": lambda: 180}, "TIME_RESERVATION"),
    ({"input_tokens": 140000}, "INPUT_RESERVATION"),
    ({"cost_ceiling_usd": .25}, "COST_RESERVATION"),
])
def test_t13_t14_exploration_never_spends_finalization_reserve(overrides, code):
    with pytest.raises(BudgetError, match=code):
        check_request(state(**overrides), 1000, 1000, "EXPLORING", 4000)


def test_current_history_and_future_observation_are_reserved_for_final_input():
    run = state(input_tokens=90000)
    assert check_request(run, 20000, 1000, "EXPLORING", 30000)
    with pytest.raises(BudgetError, match="INPUT_RESERVATION"):
        check_request(run, 20000, 1000, "EXPLORING", 40000)


def test_t13_finalization_can_use_the_reserved_budget():
    run = state(output_tokens=5000, model_calls=14, tool_calls=36)
    assert exploration_output_limit(run) == 0
    result = check_request(run, 10000, 8500, "FINALIZING")
    assert result["reserved"]["output_tokens"] == 2500
    assert result["reserved"]["model_calls"] == 1


def test_repair_does_not_reserve_a_second_repair():
    run = state(repairs=1, model_calls=15, tool_calls=39, output_tokens=13500)
    assert check_request(run, 16000, 2500, "REPAIR")["reserved"]["model_calls"] == 0
    with pytest.raises(BudgetError, match="REPAIR_INPUT_LIMIT"):
        check_request(run, 16001, 2500, "REPAIR")


def test_cache_write_cost_is_included_in_the_ceiling():
    result = check_request(state(), 10000, 1000, "EXPLORING", 10000)
    assert result["request_and_reserved_cost_ceiling_usd"] == pytest.approx(.105)


def test_final_model_request_requires_room_for_actual_sync_and_submission_tools():
    with pytest.raises(BudgetError, match="TOOL_CALL_RESERVATION"):
        check_request(state(tool_calls=38), 1000, 8500, "FINALIZING")
    with pytest.raises(BudgetError, match="TOOL_CALL_RESERVATION"):
        check_request(state(tool_calls=40, repairs=1), 1000, 2500, "REPAIR")
