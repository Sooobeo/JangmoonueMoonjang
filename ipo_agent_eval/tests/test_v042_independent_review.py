"""Independent output-budget checks for the larger exploration response cap."""
import json

import pytest

from ipo_eval.budget import BudgetError, check_request, exploration_output_limit
from ipo_eval.runner import ROOT
from test_remediation_integration import real_gateway


def test_v042_both_conditions_share_caps_and_larger_response_is_reserved(tmp_path):
    a = json.loads((ROOT / "config/A0.json").read_text(encoding="utf-8"))
    b = json.loads((ROOT / "config/B.json").read_text(encoding="utf-8"))
    assert {k: v for k, v in a.items() if k != "condition"} == {k: v for k, v in b.items() if k != "condition"}
    assert a["exploration_output_max"] == a["extraction_output_max"] == 9000
    assert (a["output_tokens_max"], a["input_tokens_target_max"], a["max_run_usd"]) == (24000, 800000, 1.25)
    run = real_gateway(tmp_path).run
    assert exploration_output_limit(run) == 9000
    checked = check_request(run, 1000, 9000, "EXPLORING", 1000)
    assert checked["reserved"]["output_tokens"] == 11500
    assert checked["reserved"]["model_calls"] == 2 and checked["reserved"]["tool_calls"] == 4


def test_v042_cap_is_dynamic_and_unknown_output_cannot_be_spent_again(tmp_path):
    run = real_gateway(tmp_path).run
    run.output_tokens = 8000
    run.cost_ceiling_usd = 8000 * run.config["price_output_per_million_usd"] / 1e6
    assert exploration_output_limit(run) == 4500
    with pytest.raises(BudgetError, match="OUTPUT_RESERVATION"):
        check_request(run, 1000, 9000, "EXPLORING", 1000)
    check_request(run, 1000, 4500, "EXPLORING", 1000)
    run.unknown_output_tokens_reserved = 1500
    run.unknown_cost_ceiling_usd = 1500 * run.config["price_output_per_million_usd"] / 1e6
    assert exploration_output_limit(run) == 3000
    with pytest.raises(BudgetError, match="OUTPUT_RESERVATION"):
        check_request(run, 1000, 4500, "EXPLORING", 1000)
    check_request(run, 1000, 3000, "EXPLORING", 1000)
