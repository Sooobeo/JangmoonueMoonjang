"""New contracts through actual B/A0 runners and gateway, with no API calls."""
from copy import deepcopy
import json

import pytest

from ipo_eval.runner import ROOT
from ipo_eval.runner_v2 import execute_v2
from ipo_eval.runtime_v2 import RunV2
from ipo_eval.tool_gateway import ToolGateway
from ipo_eval.wire_contract import to_wire_extraction
from ipo_eval.wire_contract_v2 import to_wire_extraction_v2
from test_agent_loop_v2 import v2_root, records, review, message
from test_contracts_v2 import CHUNKS, ctx, fact, rec
from test_gateway_v2 import FakeCorpus, request


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(params=["compact_v1", "compact_v2"])
def remediation_root(v2_root, request):
    for condition in ("B", "A0"):
        path = v2_root / "config" / f"{condition}.json"
        config = read_json(path)
        config.update(wire_contract=request.param, format_repair_contract="patch_v1",
                      dynamic_submission_contract=True)
        path.write_text(json.dumps(config), encoding="utf-8")
    return v2_root


def extraction(extra=()):
    return {"records": records() + list(extra), "document_version_notes": [], "extraction_limits": ["synthetic"]}


class CompactProvider:
    """Choose actions explicitly; the real runner still performs every tool."""
    def __init__(self, condition, repair=None):
        self.condition, self.repair = condition, repair
        self.responses = self
        self.calls, self.raw_outputs = [], []
        self.action = 0
        self.wire = to_wire_extraction(extraction(), CHUNKS)

    def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        def has_groups(node):
            if isinstance(node, dict):
                return {"groups", "contexts"} <= node.get("properties", {}).keys() or any(has_groups(child) for child in node.values())
            return isinstance(node, list) and any(has_groups(child) for child in node)
        if has_groups(kwargs):
            self.wire = to_wire_extraction_v2(extraction(), CHUNKS)
        fmt = kwargs.get("text", {}).get("format", {}).get("name")
        if fmt == "format_patch":
            previous = json.loads(kwargs["input"][0]["content"])["previous_output"]
            if self.repair == "registration_link":
                prefix = "/request/batch" if "request" in previous else ""
                operation = {"op": "RELINK_CLAIM", "path": prefix + "/values/0/ev/0/claim", "claim_id": "C_F"}
            elif self.repair == "semantic_attack":
                prefix = "/review" if "review" in previous else ""
                operation = {"op": "RELINK_CLAIM", "path": prefix + "/calculation_uses/0/stated_value", "claim_id": "C_F"}
            else:
                prefix = "/review" if "review" in previous else ""
                current_review = previous.get("review", previous)
                declaration = current_review["judgments"][0]["facts"][0]["claim_id"]
                operation = {"op": "RELINK_CLAIM", "path": prefix + "/judgments/0/facts/0/evidence/0/claim_id", "claim_id": declaration}
            output = message({"operations": [operation]})
        elif fmt == "extraction_compact":
            batch = deepcopy(self.wire)
            if self.repair == "registration_link":
                batch["values"][0]["ev"][0]["claim"] = "BROKEN_LINK"
            output = message(batch)
        elif self.condition == "B":
            payload = json.loads(kwargs["input"][1]["content"])
            calc = next(c for c in payload["calculations"] if c["status"] == "OK")
            value = self._review(payload["extraction_snapshot"]["input_snapshot_id"], calc, kwargs["text"]["format"]["schema"])
            output = message(value)
        else:
            observations = []
            for item in kwargs["input"]:
                if item.get("type") == "function_call_output":
                    observations.append(json.loads(item["output"]))
                elif item.get("role") == "user" and isinstance(item.get("content"), str):
                    payload = json.loads(item["content"])
                    if "format_repair_tool_result" in payload:
                        observations.append(payload["format_repair_tool_result"])
            snapshot = next((o["state"]["input_snapshot_id"] for o in reversed(observations)), "X_EMPTY")
            if kwargs.get("tool_choice", {}).get("name") == "submit_review":
                calc = next(c for o in observations if o["ok"] for c in o["result"].get("calculations", []) if c["status"] == "OK")
                schema = next(t for t in kwargs["tools"] if t["name"] == "submit_review")["parameters"]["properties"]["review"]
                name, arguments = "submit_review", {"phase": "COMMIT", "input_snapshot_id": snapshot,
                    "review": self._review(snapshot, calc, schema)}
            else:
                batch = deepcopy(self.wire)
                if self.repair == "registration_link":
                    batch["values"][0]["ev"][0]["claim"] = "BROKEN_LINK"
                name, arguments = [
                    ("search_corpus", {"query": "적용 주식수", "top_k": 1, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}}),
                    ("read_source", {"chunk_ids": ["SYN-p1"], "neighbor_pages": 0}),
                    ("calculate", {"request": {"operation": "REGISTER_BATCH", "base_snapshot_id": snapshot, "batch": batch}}),
                    ("calculate", {"request": {"operation": "EVALUATE", "input_snapshot_id": snapshot, "calculation_types": ["SHARE_SUM"]}}),
                    ("submit_review", {"phase": "PREPARE", "input_snapshot_id": snapshot}),
                ][self.action]
                self.action += 1
            output = [{"type": "reasoning", "id": f"reason_{len(self.calls)}", "summary": [],
                "encrypted_content": "UNCHANGED_ENCRYPTED_REASONING"},
                {"type": "function_call", "call_id": f"call_{len(self.calls)}", "name": name,
                 "arguments": json.dumps(arguments, ensure_ascii=False)}]
        self.raw_outputs.append(deepcopy(output))
        return {"id": f"response_{len(self.calls)}", "model": "gpt-6.1-terra", "status": "completed",
                "output": output, "usage": {"input_tokens": 100, "output_tokens": 100}}

    def _review(self, snapshot, calc, schema):
        value = review(snapshot, calc)
        declaration = schema["properties"]["judgments"]["items"]["properties"]["facts"]["items"]["properties"]["claim_id"]
        prefix = declaration["pattern"].removeprefix("^").split("[")[0]
        for judgment in value["judgments"]:
            for item in judgment["facts"]:
                item["claim_id"] = prefix + judgment["judgment_id"]
                for evidence in item["evidence"]:
                    evidence["claim_id"] = item["claim_id"]
        if self.repair == "review_link":
            value["judgments"][0]["facts"][0]["evidence"][0]["claim_id"] = "BROKEN_LINK"
        if self.repair == "semantic_attack":
            value["calculation_uses"][0]["stated_value"] = "999"
        return value


@pytest.mark.parametrize("condition", ["B", "A0"])
def test_compact_both_runners_register_calculate_and_submit_with_raw_wire_preserved(remediation_root, condition, monkeypatch):
    prospective = []
    original_estimate = RunV2.estimate
    def capture_estimate(run, payload):
        for item in payload.get("input", []):
            if item.get("type") == "function_call_output" and item.get("call_id") == "budget_estimate":
                prospective.append(json.loads(item["output"]))
        return original_estimate(run, payload)
    monkeypatch.setattr(RunV2, "estimate", capture_estimate)
    client = CompactProvider(condition)
    directory, summary = execute_v2(True, remediation_root, condition=condition, client=client)
    assert summary["execution_status"] == "SUBMITTED", summary
    assert summary["format_repairs"] == 0 and summary["final_status"] == "READY"
    stored = read_json(directory / "snapshots.json")
    assert stored["current_id"] != "X_EMPTY"
    snap = stored["snapshots"][stored["current_id"]]
    assert snap["records"]["F"]["payload"]["value"] == "10"
    assert snap["records"]["F"]["payload"]["evidence"][0]["doc_id"] == "SYN"
    calculations = read_json(directory / "calculations.json")
    assert any(c["status"] == "OK" and c["result"] == "10" for c in calculations)
    assert read_json(directory / "review.json")["calculation_uses"][0]["stated_value"] == "10"
    events = [json.loads(x) for x in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    registration = next(e for e in events if e["event"] == "tool_call" and e["tool"] == "calculate"
        and e["arguments"]["request"]["operation"] == "REGISTER_BATCH")
    assert registration["arguments"]["request"]["batch"] == client.wire
    assert "records" not in registration["arguments"]["request"]
    assert registration["actor"] == ("program_fixed" if condition == "B" else "model")
    assert "SECRET_GOLD_745" not in json.dumps(client.calls)
    if condition == "A0":
        history = read_json(directory / "context.json")
        for output in client.raw_outputs:
            for raw_item in output:
                assert raw_item in history
        observations = [json.loads(i["output"]) for i in history if i.get("type") == "function_call_output"]
        assert all("state" in o and "budget" in o["state"] for o in observations)
        reservations = [e for e in events if e["event"] == "observation_state_reservation"]
        assert reservations and all(e["envelope_and_current_state_included"] for e in reservations)
        assert all(e["prospective_state_growth_tokens_reserved"] >= 1024 for e in reservations)
        assert any(e["prospective_state_growth_tokens_reserved"] >= 2 * 3500 + 1024 for e in reservations)
        assert prospective and all("state" in item and "result" in item for item in prospective)
        pages = [chunk for item in prospective for chunk in item["result"].get("chunks", [])]
        assert pages and all(chunk["text"] for chunk in pages)
    else:
        assert read_json(directory / "extraction_model_output.json") == client.wire
        assert client.calls[0]["text"]["format"]["name"] == "extraction_compact"
        assert client.calls[1]["text"]["format"]["schema"]["properties"]["missing_inputs"]["maxItems"] == 0


@pytest.mark.parametrize("condition", ["B", "A0"])
@pytest.mark.parametrize("repair", ["registration_link", "review_link"])
def test_patch_repairs_compact_registration_or_final_review_without_full_rewrite(remediation_root, condition, repair):
    client = CompactProvider(condition, repair)
    directory, summary = execute_v2(True, remediation_root, condition=condition, client=client)
    assert summary["execution_status"] == "SUBMITTED", summary
    assert summary["format_repairs"] == 1
    assert read_json(directory / "format_patch.json")["operations"][0]["op"] == "RELINK_CLAIM"
    patch_call = next(c for c in client.calls if c.get("text", {}).get("format", {}).get("name") == "format_patch")
    assert "tools" not in patch_call
    assert "previous_output" in json.loads(patch_call["input"][0]["content"])
    facts = read_json(directory / "extraction.json")["facts"]
    assert facts["F"]["value"] == "10" and facts["F"]["evidence"][0]["claim_id"] == "C_F"
    assert read_json(directory / "review.json")["judgments"][0]["facts"][0]["text"] == "synthetic fact"


@pytest.mark.parametrize("condition", ["B", "A0"])
def test_patch_cannot_replace_a_wrong_calculation_value(remediation_root, condition):
    directory, summary = execute_v2(True, remediation_root, condition=condition, client=CompactProvider(condition, "semantic_attack"))
    assert summary["execution_status"] == "FAILED" and summary["final_status"] is None
    assert summary["failure_reason"] == "PATCH_CLAIM_LINK_OUTSIDE_EVIDENCE"
    assert not (directory / "review.json").exists()
    assert any(c["result"] == "10" for c in read_json(directory / "calculations.json"))


def real_gateway(tmp_path, wire_contract="compact_v1"):
    config = read_json(ROOT / "config/A0.json")
    config.update(wire_contract=wire_contract, format_repair_contract="patch_v1", dynamic_submission_contract=True)
    run = RunV2(config, base_directory=tmp_path)
    run.transition("EXPLORING")
    return ToolGateway(run, FakeCorpus())


def register_wire(gateway, value):
    encode = to_wire_extraction_v2 if gateway.run.config["wire_contract"] == "compact_v2" else to_wire_extraction
    return gateway.dispatch("calculate", {"request": {"operation": "REGISTER_BATCH",
        "base_snapshot_id": gateway.store.current_id, "batch": encode(value, CHUNKS)}})


@pytest.mark.parametrize("wire_contract", ["compact_v1", "compact_v2"])
def test_compact_evidence_requires_read_and_invalid_batch_remains_atomic(tmp_path, wire_contract):
    g = real_gateway(tmp_path, wire_contract)
    g.dispatch("search_corpus", {"query": "synthetic", "top_k": 1, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}})
    result = register_wire(g, extraction())
    assert not result["ok"] and result["error_code"] == "UNREAD_EVIDENCE"
    assert g.store.current_id == "X_EMPTY"
    g.dispatch("read_source", {"chunk_ids": ["SYN-p1"], "neighbor_pages": 0})
    encode = to_wire_extraction_v2 if wire_contract == "compact_v2" else to_wire_extraction
    batch = encode(extraction(), CHUNKS)
    batch["values"][0]["ev"][0]["chunk"] = "OTHER-PRIVATE-p1"
    result = g.dispatch("calculate", {"request": {"operation": "REGISTER_BATCH", "base_snapshot_id": "X_EMPTY", "batch": batch}})
    assert not result["ok"] and result["error_code"] == "ISOLATION_VIOLATION"
    assert g.fatal_error == "ISOLATION_VIOLATION"
    assert result["result"]["partial_execution"] is False and g.store.current_id == "X_EMPTY"


def test_submission_schema_tracks_exact_current_snapshot_unresolved_fields(tmp_path):
    g = real_gateway(tmp_path)
    empty_schema = g.review_schema()
    assert empty_schema["properties"]["missing_inputs"]["maxItems"] == 0
    g.dispatch("read_source", {"chunk_ids": ["SYN-p1"], "neighbor_pages": 0})
    extra = [ctx("CR", "배"), fact("U", None, "applied_per", "CR", origin="UNAVAILABLE", evidence=[], missing_reason="not read"),
        rec("SU", "SELECTION", field="applied_per", entity_id=None, disclosed_fact_id="U", selected_fact_id=None,
            disclosure_status="NOT_FOUND", usability="UNRESOLVED", selection_reason="source unconfirmed")]
    registered = register_wire(g, extraction(extra))
    assert registered["ok"]
    missing = g.review_schema()["properties"]["missing_inputs"]
    assert missing["minItems"] == missing["maxItems"] == 1
    assert missing["items"]["properties"]["field"]["enum"] == ["applied_per"]
    assert registered["state"]["required_missing_input_fields"] == ["applied_per"]
    replacement = rec("SU", "SELECTION", field="applied_per", entity_id=None, disclosed_fact_id=None, selected_fact_id=None,
        disclosure_status="NOT_APPLICABLE", usability="NOT_APPLICABLE", selection_reason="model explicitly revises applicability")
    assert register_wire(g, {"records": [replacement], "document_version_notes": [], "extraction_limits": []})["ok"]
    assert g.review_schema()["properties"]["missing_inputs"]["maxItems"] == 0
    assert empty_schema["properties"]["missing_inputs"]["maxItems"] == 0


def test_unknown_usage_reservation_is_visible_in_state(tmp_path):
    g = real_gateway(tmp_path)
    g.run.unknown_input_tokens_reserved = 123
    g.run.unknown_output_tokens_reserved = 456
    g.run.unknown_cost_ceiling_usd = 0.004
    used = g.state_view()["budget"]["used"]
    assert used["uncertain_input_reserve"] == 123
    assert used["uncertain_output_reserve"] == 456
    assert used["uncertain_cost_reserve"] == 0.004


def test_dynamic_missing_field_enum_does_not_restrict_unrelated_review_strings(tmp_path):
    g = real_gateway(tmp_path)
    g.dispatch("read_source", {"chunk_ids": ["SYN-p1"], "neighbor_pages": 0})
    unresolved = rec("UNRESOLVED_PER", "SELECTION", field="applied_per", entity_id=None,
        disclosed_fact_id=None, selected_fact_id=None, disclosure_status="NOT_FOUND",
        usability="UNRESOLVED", selection_reason="not read")
    assert register_wire(g, extraction([unresolved]))["ok"]
    schema = g.review_schema()
    properties = schema["properties"]
    missing_properties = properties["missing_inputs"]["items"]["properties"]
    field = missing_properties["field"]
    assert field["enum"] == ["applied_per"]
    judgment = properties["judgments"]["items"]["properties"]
    evidence = judgment["evidence"]["items"]["properties"]
    unrelated = [properties["scope"]["properties"]["document_ids"]["items"],
        properties["scope"]["properties"]["verification_limits"]["items"],
        judgment["conclusion"], judgment["next_action"], judgment["judgment_id"],
        judgment["facts"]["items"]["properties"]["text"],
        judgment["facts"]["items"]["properties"]["claim_id"],
        evidence["doc_id"], evidence["chunk_id"], evidence["claim_id"], evidence["locator"],
        missing_properties["missing_reason"], missing_properties["request_id"],
        properties["requests"]["items"]["properties"]["question"]]
    for rule in unrelated:
        assert rule is not field
        assert "enum" not in rule
    # A later independently generated schema must not inherit other edits.
    field["enum"].append("MUTATED_COPY_ONLY")
    assert g.review_schema()["properties"]["missing_inputs"]["items"]["properties"]["field"]["enum"] == ["applied_per"]
