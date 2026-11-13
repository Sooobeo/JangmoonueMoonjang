"""Independent D4 repair reservation and hostile-response control-flow checks."""
import json

import pytest

from ipo_eval.agent_loop import repair_structure
from ipo_eval.budget import BudgetError
from ipo_eval.runner_v2 import execute_v2
from ipo_eval.schemas import obj
from test_agent_loop_v2 import v2_root, Scripted, message
from test_runtime_v2 import runtime, response


SCHEMA = obj({"page": {"type": "integer"}})


@pytest.mark.parametrize("attribute,value,error", [
    ("remaining_time", lambda: 120, "TIME_RESERVATION"),
    ("model_calls", 15, "MODEL_CALL_RESERVATION"),
    ("tool_calls", 37, "TOOL_CALL_RESERVATION"),
    ("output_tokens", 6000, "OUTPUT_RESERVATION"),
    ("input_tokens", 158000, "INPUT_RESERVATION"),
])
def test_registration_repair_preserves_the_still_pending_finalization(tmp_path, attribute, value, error):
    run = runtime(tmp_path, response(output=message({"page": 1})))
    run.phase = "EXPLORING"
    setattr(run, attribute, value)
    with pytest.raises(BudgetError, match=error):
        repair_structure(run, {"page": "1"}, SCHEMA, ["integer required"], final_input_estimate=4000)
    assert run.client.calls == []


def test_exploration_repair_timeout_excludes_the_finalization_time(tmp_path):
    run = runtime(tmp_path, response(output=message({"page": 1})))
    run.phase = "EXPLORING"
    run.remaining_time = lambda: 160
    assert repair_structure(run, {"page": "1"}, SCHEMA, ["integer required"], final_input_estimate=4000) == {"page": 1}
    assert run.repairs == 1 and len(run.client.calls) == 1
    assert run.client.calls[0]["timeout"] == 40
    assert "tools" not in run.client.calls[0]
    audit = [json.loads(line) for line in (run.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
             if json.loads(line)["event"] == "budget_reservation"][0]
    assert audit["reserved"]["output_tokens"] == 8500
    assert audit["reserved"]["model_calls"] == 1 and audit["reserved"]["tool_calls"] == 3


class InvalidCallProvider(Scripted):
    def __init__(self, invalid):
        super().__init__()
        self.invalid = invalid

    def create(self, **kwargs):
        raw = super().create(**kwargs)
        call = next(item for item in raw["output"] if item["type"] == "function_call")
        if self.invalid == "multiple":
            raw["output"].append({**call, "call_id": "second_call_same_turn"})
        elif self.invalid == "duplicate":
            call["call_id"] = "repeated_call_id"
        return raw


@pytest.mark.parametrize("invalid,expected,count", [("multiple", "MULTIPLE_TOOL_CALLS_WITH_PARALLEL_DISABLED", 1),
                                                    ("duplicate", "DUPLICATE_OR_MISSING_CALL_ID", 2)])
def test_invalid_function_call_sequences_fail_without_extra_model_retries(v2_root, invalid, expected, count):
    client = InvalidCallProvider(invalid)
    directory, summary = execute_v2(True, v2_root, condition="A0", client=client)
    assert summary["execution_status"] == "FAILED" and summary["failure_reason"] == expected
    assert len(client.calls) == count
    assert len(list(directory.glob("*_response.json"))) == count
    assert not (directory / "review.json").exists()


def test_final_repair_is_retained_in_the_saved_full_context(v2_root):
    directory, summary = execute_v2(True, v2_root, condition="A0", client=Scripted(bad_reference=True))
    assert summary["execution_status"] == "SUBMITTED", summary
    history = json.loads((directory / "context.json").read_text(encoding="utf-8"))
    content = json.loads(history[-1]["content"])
    assert content["format_repair_tool_result"]["ok"]
