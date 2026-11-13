from copy import deepcopy
import json

import httpx
from openai import APIStatusError
import pytest

from ipo_eval.budget import BudgetError, check_request, exploration_output_limit
from ipo_eval.runtime_v2 import dumps, wire_dumps
from test_runtime_v2 import runtime, response


def error(status=500, code="server_error"):
    return APIStatusError("SECRET_SENTINEL_MUST_NOT_BE_LOGGED",
        response=httpx.Response(status, request=httpx.Request("POST", "https://example.test/responses")),
        body={"code": code, "param": None, "type": "server_error"})


class SequenceClient:
    def __init__(self, values, after_first=None):
        self.responses = self
        self.values = list(values)
        self.calls = []
        self.after_first = after_first

    def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if len(self.calls) == 1 and self.after_first:
            self.after_first()
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def configured(tmp_path, values, after_first=None):
    run = runtime(tmp_path, response())
    run.config["max_transient_api_retries"] = 1
    run.client = SequenceClient(values, after_first)
    return run


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_transient_server_error_retries_identical_request_once_and_keeps_unknown_usage(tmp_path, status):
    run = configured(tmp_path, [error(status), response()])
    request = run.base_request([{"role": "user", "content": "unchanged request"}], 1000)
    original = deepcopy(request)
    result = run.request("explore", request, "EXPLORING", 4000)
    assert result == response() and request == original
    assert run.model_calls == 2 and run.transient_retries == 1
    assert [{k: v for k, v in call.items() if k != "timeout"} for call in run.client.calls] == [request, request]
    assert (run.directory / "01_explore_error.json").exists()
    assert not (run.directory / "01_explore_response.json").exists()
    assert (run.directory / "02_explore_response.json").exists()
    assert run.input_tokens == 100 and run.output_tokens == 50
    assert run.unknown_input_tokens_reserved == run.estimate(request)
    assert run.unknown_output_tokens_reserved == 1000
    assert run.unknown_cost_ceiling_usd == pytest.approx(run.estimate(request) * 1.25 / 1e6 + .005)
    summary = run.finish("SUBMITTED", final_status="HUMAN_REVIEW")
    assert summary["usage_unknown"] and summary["estimated_cost_usd_standard_uncached"] is None
    assert summary["known_usage_cost_usd_standard_uncached"] == .00035
    assert summary["accounted_cost_ceiling_usd"] > summary["cost_ceiling_usd"]
    assert len(summary["unknown_usage_reservation"]["attempts"]) == 1
    assert "SECRET_SENTINEL" not in "".join(p.read_text(encoding="utf-8") for p in run.directory.glob("*.json*"))


@pytest.mark.parametrize("status,code", [(400, "unknown_parameter"), (401, "authentication_error"),
    (403, "permission_error"), (429, "rate_limit_exceeded"), (429, "insufficient_quota"),
    (500, "insufficient_quota"), (501, "not_implemented")])
def test_noneligible_api_errors_are_never_retried(tmp_path, status, code):
    run = configured(tmp_path, [error(status, code), response()])
    with pytest.raises(RuntimeError, match="API_ERROR"):
        run.request("explore", run.base_request([], 1000), "EXPLORING", 4000)
    assert run.model_calls == len(run.client.calls) == 1 and run.transient_retries == 0
    assert run.usage_unknown and run.unknown_output_tokens_reserved == 1000


def test_second_server_failure_stops_without_third_attempt_and_reserves_both(tmp_path):
    run = configured(tmp_path, [error(), error(), response()])
    request = run.base_request([], 1000)
    with pytest.raises(RuntimeError, match="API_ERROR"):
        run.request("explore", request, "EXPLORING", 4000)
    assert run.model_calls == 2 and len(run.client.calls) == 2
    assert run.unknown_input_tokens_reserved == 2 * run.estimate(request)
    assert run.unknown_output_tokens_reserved == 2000
    assert len(run.unknown_usage_attempts) == 2


@pytest.mark.parametrize("kind,reason", [("models", "MODEL_CALL"), ("input", "INPUT"),
    ("output", "OUTPUT"), ("cost", "COST"), ("tools", "TOOL_CALL"), ("time", "TIME")])
def test_every_budget_is_rechecked_before_retry(tmp_path, kind, reason):
    run = configured(tmp_path, [error(), response()])
    request = run.base_request([], 1000)
    estimate = run.estimate(request)
    if kind == "models":
        run.config["max_model_calls"] = 3
    elif kind == "input":
        run.config["input_tokens_target_max"] = estimate + 20000
    elif kind == "output":
        run.output_tokens = 4000
    elif kind == "cost":
        ceiling = check_request(run, estimate, 1000, "EXPLORING", 4000)["request_and_reserved_cost_ceiling_usd"]
        run.config["max_run_usd"] = ceiling + .000001
    elif kind == "tools":
        run.client.after_first = lambda: setattr(run, "tool_calls", 37)
    else:
        run.client.after_first = lambda: setattr(run, "remaining_time", lambda: 180)
    with pytest.raises(BudgetError, match=reason + "_RESERVATION"):
        run.request("explore", request, "EXPLORING", 4000)
    assert len(run.client.calls) == run.model_calls == 1
    assert run.transient_retries == 0 and run.usage_unknown
    events = [json.loads(line) for line in (run.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events[-1]["event"] == "transient_retry_blocked"


@pytest.mark.parametrize("raw,reason", [(response(usage=None), "USAGE_MISSING"),
    (response(status="incomplete", incomplete_details={"reason": "max_output_tokens"}), "MODEL_INCOMPLETE"),
    (response(output=[{"type": "refusal"}]), "MODEL_REFUSAL")])
def test_usage_missing_incomplete_and_refusal_do_not_trigger_retry(tmp_path, raw, reason):
    run = configured(tmp_path, [raw, response()])
    with pytest.raises(RuntimeError, match=reason):
        run.request("explore", run.base_request([], 1000), "EXPLORING", 4000)
    assert len(run.client.calls) == 1 and run.model_calls == 1


def test_final_request_cannot_double_spend_unknown_output_on_retry(tmp_path):
    run = configured(tmp_path, [error(), response()])
    with pytest.raises(BudgetError, match="OUTPUT_RESERVATION"):
        run.request("finalize", run.base_request([], 8500), "FINALIZING")
    assert run.model_calls == 1 and run.unknown_output_tokens_reserved == 8500


def test_future_exploration_still_accounts_for_unknown_attempt(tmp_path):
    run = configured(tmp_path, [error(), response()])
    run.request("explore", run.base_request([], 1000), "EXPLORING", 4000)
    run.output_tokens = 4000
    assert exploration_output_limit(run) == 0
    with pytest.raises(BudgetError, match="OUTPUT_RESERVATION"):
        check_request(run, 100, 1, "EXPLORING", 4000)


@pytest.mark.parametrize("limit", [True, -1, 2])
def test_retry_limit_is_explicit_and_bounded(tmp_path, limit):
    run = configured(tmp_path, [response()])
    run.config["max_transient_api_retries"] = limit
    with pytest.raises(RuntimeError, match="INVALID_TRANSIENT_RETRY_LIMIT"):
        run.request("explore", run.base_request([], 1000), "EXPLORING", 4000)
    assert not run.client.calls


def test_wire_estimate_is_compact_without_changing_string_contents_or_pretty_logs(tmp_path):
    run = runtime(tmp_path, response())
    payload = {"long_list": [{"a": "  exact Korean 원문  ", "b": [1, 2, 3]}] * 20}
    assert json.loads(wire_dumps(payload)) == payload
    assert "\n" not in wire_dumps(payload) and "\n" in dumps(payload)
    assert run.estimate(payload) == len(run.encoder.encode(wire_dumps(payload))) + 800
    assert run.estimate(payload) < len(run.encoder.encode(dumps(payload))) + 800
