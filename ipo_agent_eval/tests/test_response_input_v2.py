"""Replay production-shaped SDK output using a rejecting mock transport."""
from copy import deepcopy
import json

import httpx
import pytest
from openai import BadRequestError

from ipo_eval.response_input import to_response_input
from ipo_eval.runner_v2 import execute_v2
from test_agent_loop_v2 import Scripted, v2_root
from test_runtime_v2 import response, runtime


class SdkShapedScripted(Scripted):
    def create(self, **kwargs):
        # This transport rejects the actual shape first present in the failed
        # sixth live request. It never invokes an external provider.
        for item in kwargs["input"]:
            if item.get("type") == "reasoning":
                assert "status" not in item
                assert item.get("content") not in (None, []) if "content" in item else True
                assert item["encrypted_content"].startswith("SYNTHETIC_REASONING_")
            if item.get("type") == "function_call":
                assert "status" not in item and "namespace" not in item
        raw = super().create(**kwargs)
        for item in raw["output"]:
            if item["type"] == "reasoning":
                item.update(content=[], status=None)
            elif item["type"] == "function_call":
                item.update(id="fc_" + item["call_id"], namespace=None, status="completed")
        return raw


def test_full_agent_replays_sdk_defaults_without_changing_original_audit(v2_root):
    client = SdkShapedScripted()
    directory, summary = execute_v2(True, v2_root, condition="A0", client=client)
    assert summary["execution_status"] == "SUBMITTED", summary
    assert summary["model_calls"] == 7
    raw = json.loads((directory / "01_explore_response.json").read_text(encoding="utf-8"))
    context = json.loads((directory / "context.json").read_text(encoding="utf-8"))
    assert context[2:4] == raw["output"]
    assert raw["output"][0]["status"] is None and raw["output"][0]["content"] == []
    wire = client.calls[1]["input"]
    assert wire[2]["id"] == raw["output"][0]["id"]
    assert wire[2]["encrypted_content"] == raw["output"][0]["encrypted_content"]
    assert wire[3]["call_id"] == raw["output"][1]["call_id"] == wire[4]["call_id"]
    assert wire[3]["arguments"] == raw["output"][1]["arguments"]
    assert json.loads((directory / "02_explore_request.json").read_text(encoding="utf-8"))["input"] == wire


def test_serializer_preserves_order_phase_and_nonempty_content_without_aliases():
    history = [
        {"role": "system", "content": "instruction"},
        {"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": "summary"}],
         "content": [{"type": "reasoning_text", "text": "synthetic supplied content"}],
         "encrypted_content": "opaque exact bytes", "status": "completed"},
        {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed", "phase": "commentary",
         "content": [{"type": "output_text", "text": "body", "annotations": []}]},
        {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "example", "namespace": "ns",
         "arguments": '{"number":"001.00", "nested":{"value":null}}', "status": "completed"},
        {"type": "function_call_output", "call_id": "call_1", "output": '{"value":null}'},
    ]
    before = deepcopy(history)
    wire = to_response_input(history)
    assert history == before
    for i in (0, 2, 4):
        assert wire[i] == history[i]
    for i in (1, 3):
        assert wire[i] == {k: v for k, v in history[i].items() if k != "status"}
    wire[1]["summary"][0]["text"] = "changed copy"
    assert history == before


@pytest.mark.parametrize("item", [
    {"type": "new_unknown_output", "content": "must not silently disappear"},
    {"type": "reasoning", "id": "rs_1", "summary": [], "future_content": "must not silently disappear"},
])
def test_unrecognized_replay_content_fails_closed(item):
    with pytest.raises(RuntimeError, match="UNSUPPORTED_RESPONSE_INPUT"):
        to_response_input([item])


def test_optional_reasoning_content_null_is_audited_and_can_be_replayed(tmp_path):
    raw = response(output=[{"type": "reasoning", "id": "rs_1", "summary": [],
                            "content": None, "status": None, "encrypted_content": "opaque"}])
    run = runtime(tmp_path, raw)
    returned = run.request("probe", run.base_request([], 1000), "EXPLORING", 4000)
    assert returned == raw
    wire = run.base_request(raw["output"], 1000)["input"]
    assert wire == [{"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "opaque"}]


@pytest.mark.parametrize("param,expected", [
    ("input[10].status", "input[10].status"),
    ("input[10].content", "input[10].content"),
    ("unsafe secret / bearer token", None),
    ("x" * 161, None),
    (None, None),
])
def test_api_failure_records_only_safe_parameter_path(tmp_path, param, expected):
    exc = BadRequestError("SECRET_SENTINEL_MUST_NOT_BE_LOGGED",
        response=httpx.Response(400, request=httpx.Request("POST", "https://example.test/responses")),
        body={"code": "unknown_parameter", "param": param, "type": "invalid_request_error"})
    run = runtime(tmp_path, exc)
    with pytest.raises(RuntimeError, match="API_ERROR:BadRequestError"):
        run.request("probe", run.base_request([], 1000), "EXPLORING", 4000)
    events = (run.directory / "events.jsonl").read_text(encoding="utf-8")
    failure = json.loads(events.splitlines()[-1])
    assert failure["api_error_param"] == expected
    assert failure["api_error_code"] == "unknown_parameter" and failure["http_status"] == 400
    assert failure["usage_unknown"] is True
    assert "SECRET_SENTINEL" not in events and "unsafe secret" not in events
