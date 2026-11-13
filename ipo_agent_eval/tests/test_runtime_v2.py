import json

import pytest

from ipo_eval.runtime_v2 import RunV2
from test_budget_v2 import state


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.responses = self
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def runtime(tmp_path, result):
    config = {**state().config, "wall_seconds_max": 600, "condition": "A0", "version": "0.3.0-dev",
              "model": "gpt-6.1-terra", "reasoning_effort": "medium", "budget_fx_krw_per_usd": 1400}
    return RunV2(config, True, tmp_path, FakeClient(result))


def response(**updates):
    return {**{"id": "SYNTHETIC", "model": "gpt-6.1-terra", "status": "completed",
               "usage": {"input_tokens": 100, "output_tokens": 50}, "output": []}, **updates}


@pytest.mark.parametrize("raw,code", [
    (response(usage=None), "USAGE_MISSING"),
    (response(usage={"input_tokens": 1}), "USAGE_MISSING"),
    (response(usage={"input_tokens": True, "output_tokens": 0}), "USAGE_MISSING"),
    (response(status="incomplete", incomplete_details={"reason": "max_output_tokens"}), "MODEL_INCOMPLETE"),
    (response(output=[{"type": "message", "content": [{"type": "refusal", "refusal": "synthetic"}]}]), "MODEL_REFUSAL"),
])
def test_t16_distinct_api_failure_states(tmp_path, raw, code):
    run = runtime(tmp_path, raw)
    with pytest.raises(RuntimeError, match=code):
        run.request("probe", run.base_request([], 1000), "EXPLORING", 4000)
    assert len(run.client.calls) == 1
    assert (run.directory / "01_probe_response.json").exists()


def test_unknown_usage_is_never_reported_as_zero_total_cost(tmp_path):
    run = runtime(tmp_path, RuntimeError("SECRET_SENTINEL_MUST_NOT_BE_LOGGED"))
    with pytest.raises(RuntimeError, match="API_ERROR"):
        run.request("probe", run.base_request([], 1000), "EXPLORING", 4000)
    summary = run.finish("FAILED", final_status=None)
    assert summary["usage_unknown"]
    assert summary["estimated_cost_usd_standard_uncached"] is None
    assert len(run.client.calls) == 1
    assert "SECRET_SENTINEL" not in "".join(p.read_text(encoding="utf-8") for p in run.directory.glob("*"))


def test_original_usage_and_reasoning_items_are_retained(tmp_path):
    raw = response(output=[{"type": "reasoning", "id": "rs_test", "summary": [], "encrypted_content": "synthetic"},
                           {"type": "function_call", "call_id": "c1", "name": "read_source", "arguments": "{}"}])
    run = runtime(tmp_path, raw)
    result = run.request("explore", run.base_request([], 1000), "EXPLORING", 4000)
    assert result["output"] == raw["output"]
    assert run.input_tokens == 100 and run.output_tokens == 50
    saved = json.loads((run.directory / "01_explore_response.json").read_text(encoding="utf-8"))
    assert saved == raw


def test_rejected_tool_attempt_still_consumes_a_call(tmp_path):
    run = runtime(tmp_path, response())
    def reject():
        raise ValueError("INVALID_ARGUMENT")
    with pytest.raises(ValueError):
        run.tool("read_source", {}, reject, actor="model", call_id="c1")
    assert run.tool_calls == 1
    event = json.loads((run.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert event["actor"] == "model" and event["call_id"] == "c1"
