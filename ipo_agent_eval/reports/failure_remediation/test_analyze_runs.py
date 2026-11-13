"""Small read-only reporting checks, separate from the frozen application."""
import importlib.util
import json
from pathlib import Path


spec = importlib.util.spec_from_file_location("remediation_analysis", Path(__file__).with_name("analyze_runs.py"))
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_unknown_usage_does_not_become_zero_cost_and_actor_choices_stay_separate(tmp_path):
    write(tmp_path / "01_explore_request.json", {})
    write(tmp_path / "02_explore_request.json", {})
    write(tmp_path / "01_explore_response.json", {"id": "SYN_RESPONSE", "model": "gpt-6.1-terra", "status": "completed",
        "output": [{"type": "function_call", "name": "calculate", "arguments": json.dumps({"request": {"operation": "REGISTER_BATCH"}})}],
        "usage": {"input_tokens": 100, "output_tokens": 10, "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 30}}})
    events = [{"event": "model_call_started"}, {"event": "model_call_started"}, {"event": "model_call_failed"}]
    report = analysis.audit_usage(tmp_path, events, {"model_calls": 2}, True, [])
    assert report["known_usage_cost_usd"] == "0.0001385"
    assert report["requests_without_usage"] == 1 and report["total_cost_estimate_usd"] is None
    assert report["real_model_tool_choices"] == {"REGISTER_BATCH": 1}
    assert report["token_totals"]["ordinary_input_tokens"] == 50
    assert analysis.operation("calculate", {"request": []}) == "INVALID_ARGUMENT"


def test_explicit_unstarted_and_unobserved_are_not_failed_attempts(tmp_path, monkeypatch):
    here = tmp_path / "reports/failure_remediation"
    here.mkdir(parents=True)
    (tmp_path / "runs").mkdir()
    monkeypatch.setattr(analysis, "ROOT", tmp_path)
    monkeypatch.setattr(analysis, "HERE", here)
    planned = [{"case_id": f"SYN{i}", "condition": "B", "repeat": 1} for i in (1, 2)]
    write(here / "SYN_plan.json", {"batch": "SYN", "version": "synthetic", "live": True, "planned_runs": planned,
        "source_hashes": {}, "source_snapshot": "reports/failure_remediation/SYN_source"})
    write(here / "SYN_runs.json", {"complete": False, "runs": [{**planned[0], "directory": None,
        "summary": {"execution_status": "NOT_STARTED_STOP_REQUESTED", "failure_reason": "STOP"}}]})
    result = analysis.analyze("SYN")
    assert result["counts"]["actual_started"] == 0
    assert result["counts"]["explicit_not_started"] == 1 and result["counts"]["not_yet_observed"] == 1
    assert "FAILED" not in result["counts"]["by_status"]
    assert result["costs"]["batch_total_estimate_usd"] is None
    assert all(r["usage_cost"] is None for r in result["runs"])


def test_running_registration_and_calculations_are_recovered_from_events(tmp_path):
    events = [
        {"event": "run_created", "mode": "LIVE"},
        {"event": "tool_call", "tool": "calculate", "actor": "model", "arguments": {"request": {
            "operation": "REGISTER_BATCH", "batch": {"values": [{"id": "F"}], "contexts": [{"id": "C"}]}}},
            "result": {"registered_ids": ["C", "F"]}},
        {"event": "tool_call", "tool": "calculate", "actor": "model", "arguments": {"request": {"operation": "EVALUATE"}},
            "result": {"calculations": [{"calc_id": "K", "kind": "SHARE_SUM", "status": "OK", "result": "10"}]}},
        {"event": "tool_envelope", "ok": True, "state": {"input_snapshot_id": "X_SYN", "registered_fact_ids": ["F"]}},
    ]
    (tmp_path / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    before = (tmp_path / "events.jsonl").read_bytes()
    row = analysis.analyze_directory(tmp_path, {"case_id": "SYN", "condition": "A0", "repeat": 1})
    assert row["execution_status"] == "RUNNING" and row["registration"]["record_count"] == 2
    assert row["registration"]["fact_count"] == 1
    assert row["calculations"]["by_kind_status"] == {"SHARE_SUM": {"OK": 1}}
    assert row["submitted_calculation_uses"] is None
    assert row["tool_operations_by_actor"] == {"model": {"REGISTER_BATCH": 1, "EVALUATE": 1}}
    assert row["real_model_tool_choices"] == {}
    assert (tmp_path / "events.jsonl").read_bytes() == before


def test_saved_schema_contamination_is_attributed_to_executor_not_model():
    schema = {"type": "object", "properties": {
        "missing_inputs": {"items": {"properties": {"field": {"type": "string", "enum": ["peer.reference_shares"]}}}},
        "scope": {"properties": {"document_ids": {"items": {"type": "string", "enum": ["peer.reference_shares"]}}}},
        "conclusion": {"type": "string", "enum": ["peer.reference_shares"]}}}
    request = {"text": {"format": {"schema": schema}}}
    issues = analysis.schema_alias_findings(request)
    assert len(issues) == 1 and len(issues[0]["unrelated_string_paths"]) == 2
    assert issues[0]["issue"] == "DYNAMIC_SCHEMA_SHARED_STRING_ENUM_CONTAMINATION"
    del schema["properties"]["scope"]["properties"]["document_ids"]["items"]["enum"]
    del schema["properties"]["conclusion"]["enum"]
    assert analysis.schema_alias_findings(request) == []
