"""Independent compact boundary review; all execution uses synthetic corpus."""
from copy import deepcopy
import json
import re

import pytest

from ipo_eval.wire_contract import to_wire_extraction, expand_wire_extraction
from ipo_eval.wire_contract_v2 import expand_wire_extraction_v2
from ipo_eval.provenance import SnapshotStore
from ipo_eval.runner import ROOT
from test_contracts_v2 import CHUNKS
from test_remediation_integration import real_gateway, extraction, remediation_root, CompactProvider, read_json
from test_agent_loop_v2 import v2_root
from ipo_eval.runner_v2 import execute_v2


def register(gateway, batch):
    return gateway.dispatch("calculate", {"request": {"operation": "REGISTER_BATCH",
        "base_snapshot_id": gateway.store.current_id, "batch": batch}})


@pytest.mark.parametrize("foreign", ["OTHER-PRIVATE-p1", "UNKNOWN-p999"])
def test_compact_foreign_chunk_is_fatal_counted_atomic_and_not_repaired(tmp_path, foreign):
    gateway = real_gateway(tmp_path)
    gateway.dispatch("read_source", {"chunk_ids": ["SYN-p1"], "neighbor_pages": 0})
    batch = to_wire_extraction(extraction(), CHUNKS)
    original = deepcopy(batch)
    batch["values"][0]["ev"][0]["chunk"] = foreign
    before = gateway.run.tool_calls
    blocked = register(gateway, batch)
    assert blocked["error_code"] == gateway.fatal_error == "ISOLATION_VIOLATION"
    assert gateway.run.tool_calls == before + 1
    assert blocked["result"]["partial_execution"] is False
    assert gateway.store.current_id == "X_EMPTY"
    assert set(gateway.read_chunks) == {"SYN-p1"}
    assert register(gateway, original)["error_code"] == "ISOLATION_VIOLATION"
    assert gateway.store.current_id == "X_EMPTY"


def test_compact_current_corpus_unread_page_is_recoverable_without_auto_read(tmp_path):
    gateway = real_gateway(tmp_path)
    gateway.dispatch("read_source", {"chunk_ids": ["SYN-p1"], "neighbor_pages": 0})
    batch = to_wire_extraction(extraction(), CHUNKS)
    batch["values"][0]["ev"][0]["chunk"] = "SYN-p2"
    blocked = register(gateway, batch)
    assert blocked["error_code"] == "UNREAD_EVIDENCE" and gateway.fatal_error is None
    assert blocked["result"]["partial_execution"] is False
    assert gateway.store.current_id == "X_EMPTY"
    assert set(gateway.read_chunks) == {"SYN-p1"}
    gateway.dispatch("read_source", {"chunk_ids": ["SYN-p2"], "neighbor_pages": 0})
    assert register(gateway, batch)["ok"]
    stored = gateway.store.facts(gateway.store.current_id)["F"]["evidence"][0]
    assert stored["chunk_id"] == "SYN-p2" and stored["page"] == 2


@pytest.mark.parametrize("stage,expected_calls", [("register", 1), ("commit", 2)])
def test_b_fatal_isolation_stops_before_any_format_repair_api(remediation_root, stage, expected_calls):
    class ForeignEvidenceProvider(CompactProvider):
        def __init__(self):
            super().__init__("B")

        def create(self, **kwargs):
            raw = super().create(**kwargs)
            if stage == "register" and kwargs.get("text", {}).get("format", {}).get("name") == "extraction_compact":
                content = next(c for item in raw["output"] for c in item.get("content", []) if c.get("type") == "output_text")
                wire = json.loads(content["text"])
                wire["values"][0]["ev"][0]["chunk"] = "OTHER-PRIVATE-p1"
                content["text"] = json.dumps(wire)
                self.raw_outputs[-1] = deepcopy(raw["output"])
            return raw

        def _review(self, snapshot, calc, schema):
            value = super()._review(snapshot, calc, schema)
            if stage == "commit":
                value["judgments"][0]["facts"][0]["evidence"][0]["doc_id"] = "OTHER-PRIVATE"
            return value

    client = ForeignEvidenceProvider()
    directory, summary = execute_v2(True, remediation_root, condition="B", client=client)
    assert summary["execution_status"] == "FAILED" and summary["final_status"] is None
    assert not (directory / "review.json").exists()
    assert summary["model_calls"] == expected_calls
    assert len(client.calls) == expected_calls and summary["format_repairs"] == 0
    assert "ISOLATION_VIOLATION" in summary["failure_reason"]


def test_shared_synthetic_prompt_example_registers_only_input_values():
    prompt = (ROOT / "prompts/v2_contract.md").read_text(encoding="utf-8")
    examples = re.findall(r"```json\s*(.*?)\s*```", prompt, re.DOTALL)
    assert len(examples) == 1
    wire = json.loads(examples[0])
    assert {row["id"] for row in wire["values"]} == {"P", "S"}
    assert wire["notes"] == ["SYNTHETIC ONLY"]
    contract = json.loads((ROOT / "config/B.json").read_text(encoding="utf-8"))["wire_contract"]
    expand = expand_wire_extraction_v2 if contract == "compact_v2" else expand_wire_extraction
    expanded = expand(wire, CHUNKS)
    store = SnapshotStore(CHUNKS)
    registered = store.register(store.current_id, expanded["records"])
    facts = store.facts(registered["input_snapshot_id"])
    assert facts["M"]["origin"] == "DERIVED" and facts["M"]["value"] == "100"
    selected = store.logical(registered["input_snapshot_id"])["selections"]
    assert selected[0]["selected_fact_id"] == "M" and selected[0]["usability"] == "DERIVABLE"
