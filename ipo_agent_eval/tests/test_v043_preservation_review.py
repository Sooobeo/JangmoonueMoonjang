"""Independent preservation boundaries for model-declared context groups."""
from copy import deepcopy
import json

import pytest

from ipo_eval.format_patch import FormatPatchError, apply_format_patch
from ipo_eval.provenance import SnapshotStore
from ipo_eval.wire_contract_v2 import EXTRACTION_WIRE_V2, expand_wire_extraction_v2, to_wire_extraction_v2
from test_contracts_v2 import CHUNKS, ctx, fact, ev
from test_wire_contract import sample
from test_agent_loop_v2 import v2_root
from test_remediation_integration import remediation_root, CompactProvider, extraction, read_json, real_gateway
from ipo_eval.runner_v2 import execute_v2
from ipo_eval.schemas_v2 import REVIEW_V2
from test_gateway_v2 import review


@pytest.mark.parametrize("path", ["/groups/0/id", "/groups/0/t", "/groups/0/s", "/groups/0/b", "/groups/0/src",
                                 "/contexts/0/g", "/contexts/0/u", "/contexts/0/p", "/values/0/c"])
def test_patch_cannot_remove_or_relink_declared_group_context_or_claim(path):
    wire = to_wire_extraction_v2(sample(), CHUNKS)
    original = deepcopy(wire)
    for operation in ({"op": "REMOVE_EXTRA", "path": path},
                      {"op": "RELINK_CLAIM", "path": path, "claim_id": wire["values"][0]["c"]}):
        with pytest.raises(FormatPatchError):
            apply_format_patch(wire, {"operations": [operation]}, EXTRACTION_WIRE_V2)
        assert wire == original


def test_date_group_reference_and_missing_basis_are_not_format_fillable():
    wire = to_wire_extraction_v2(sample(), CHUNKS)
    with pytest.raises(FormatPatchError):
        apply_format_patch(wire, {"operations": [{"op": "NORMALIZE_INTEGER", "path": "/groups/0/t"}]}, EXTRACTION_WIRE_V2)
    for group, key in (("groups", "b"), ("contexts", "g")):
        invalid = deepcopy(wire)
        del invalid[group][0][key]
        for kind in ("NULL", "ARRAY", "OBJECT"):
            with pytest.raises(FormatPatchError):
                apply_format_patch(invalid, {"operations": [{"op": "ADD_EMPTY", "path": f"/{group}/0/{key}", "empty_kind": kind}]}, EXTRACTION_WIRE_V2)


def test_shared_group_reference_preserves_values_and_raw_names_without_rewriting():
    wire = to_wire_extraction_v2(sample(), CHUNKS)
    # Distinct names for exactly equal group tuples remain distinct raw choices.
    group = deepcopy(wire["groups"][0])
    group["id"] = "MODEL_DECLARED_SECOND_NAME"
    wire["groups"].append(group)
    wire["contexts"][0]["g"] = group["id"]
    before = deepcopy(wire)
    expanded = expand_wire_extraction_v2(wire, CHUNKS)
    store = SnapshotStore(CHUNKS)
    store.register("X_EMPTY", expanded["records"])
    original = SnapshotStore(CHUNKS)
    original.register("X_EMPTY", sample()["records"])
    assert store.current_id == original.current_id
    assert wire == before
    encoded_again = to_wire_extraction_v2(expanded, CHUNKS)
    assert encoded_again != wire  # Logical losslessness is not arbitrary-name identity.
    assert len(encoded_again["groups"]) == len(wire["groups"]) - 1


def test_b_checks_actual_final_request_after_extraction_before_sending_again(remediation_root):
    config_path = remediation_root / "config/B.json"
    config = read_json(config_path)
    config["wire_contract"] = "compact_v2"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    actual_input = config["input_tokens_target_max"] - config["format_repair_input_reserve"]

    class HeavyUsageProvider(CompactProvider):
        def __init__(self):
            super().__init__("B")
            self.wire = to_wire_extraction_v2(extraction(), CHUNKS)

        def create(self, **kwargs):
            result = super().create(**kwargs)
            result["usage"]["input_tokens"] = actual_input
            return result

    client = HeavyUsageProvider()
    directory, summary = execute_v2(True, remediation_root, condition="B", client=client)
    assert summary["execution_status"] == "FAILED" and summary["failure_reason"] == "INPUT_RESERVATION"
    assert summary["model_calls"] == len(client.calls) == 1
    assert summary["input_tokens"] == actual_input and not summary["usage_unknown"]
    assert read_json(directory / "snapshots.json")["current_id"] != "X_EMPTY"
    assert read_json(directory / "calculations.json")
    assert not (directory / "02_review_request.json").exists()
    assert not (directory / "review.json").exists()


def test_review_claim_namespace_skips_registered_prefixes_without_touching_other_leaves(tmp_path):
    gateway = real_gateway(tmp_path)
    gateway.dispatch("read_source", {"chunk_ids": ["SYN-p1"], "neighbor_pages": 0})
    gateway.store.register("X_EMPTY", [ctx(),
        fact("A", claim_id="REVIEW_OLD", evidence=[ev("REVIEW_OLD")]),
        fact("B", claim_id="REVIEW2_OLD", evidence=[ev("REVIEW2_OLD")])])
    original_contract = json.dumps(REVIEW_V2, sort_keys=True)
    original_facts = deepcopy(gateway.store.facts(gateway.store.current_id))
    schema = gateway.review_schema()
    facts = schema["properties"]["judgments"]["items"]["properties"]["facts"]["items"]["properties"]
    assert facts["claim_id"]["pattern"] == "^REVIEW3_[A-Za-z0-9_-]+$"
    assert "pattern" not in facts["text"]
    assert "pattern" not in facts["evidence"]["items"]["properties"]["claim_id"]
    assert "pattern" not in schema["properties"]["scope"]["properties"]["document_ids"]["items"]
    assert "pattern" not in schema["properties"]["judgments"]["items"]["properties"]["conclusion"]
    facts["claim_id"]["pattern"] = "MUTATED_RETURNED_SCHEMA_ONLY"
    fresh = gateway.review_schema()["properties"]["judgments"]["items"]["properties"]["facts"]["items"]["properties"]
    assert fresh["claim_id"]["pattern"] == "^REVIEW3_[A-Za-z0-9_-]+$"
    assert json.dumps(REVIEW_V2, sort_keys=True) == original_contract
    assert gateway.store.facts(gateway.store.current_id) == original_facts


def test_review_namespace_is_not_posthoc_declaration_renaming(tmp_path):
    gateway = real_gateway(tmp_path)
    schema = gateway.review_schema()
    value = review()
    value["judgments"][0]["facts"] = [{"claim_id": "REVIEW_FACT", "text": "Exact synthetic assertion",
                                       "evidence": [ev("WRONG_REFERENCE")]}]
    repaired = apply_format_patch(value, {"operations": [{"op": "RELINK_CLAIM",
        "path": "/judgments/0/facts/0/evidence/0/claim_id", "claim_id": "REVIEW_FACT"}]}, schema)
    assert repaired["judgments"][0]["facts"][0]["claim_id"] == "REVIEW_FACT"
    for operation in ({"op": "RELINK_CLAIM", "path": "/judgments/0/facts/0/claim_id", "claim_id": "REVIEW_CHANGED"},
                      {"op": "REMOVE_EXTRA", "path": "/judgments/0/facts/0/claim_id"}):
        with pytest.raises(FormatPatchError):
            apply_format_patch(value, {"operations": [operation]}, schema)
    assert value["judgments"][0]["facts"][0]["evidence"][0]["claim_id"] == "WRONG_REFERENCE"
