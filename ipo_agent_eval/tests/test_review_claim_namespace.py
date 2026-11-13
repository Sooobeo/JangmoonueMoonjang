"""Dynamic review declarations cannot collide with stored extraction claims."""
from copy import deepcopy

from jsonschema import Draft202012Validator
import pytest

from ipo_eval.format_patch import FormatPatchError, apply_format_patch
from ipo_eval.schemas_v2 import REVIEW_V2
from test_agent_loop_v2 import review
from test_contracts_v2 import ctx, fact
from test_remediation_integration import real_gateway, register_wire


def declaration(schema):
    return schema["properties"]["judgments"]["items"]["properties"]["facts"]["items"]["properties"]["claim_id"]


def extraction_claim(identifier, claim_id):
    record = fact(identifier, "10")
    record["payload"]["claim_id"] = claim_id
    record["payload"]["evidence"][0]["claim_id"] = claim_id
    return record


def test_dynamic_namespace_skips_every_colliding_prefix_and_leaves_registered_claims_unchanged(tmp_path):
    gateway = real_gateway(tmp_path, "compact_v2")
    initial = gateway.review_schema()
    assert declaration(initial)["pattern"] == "^REVIEW_[A-Za-z0-9_-]+$"
    gateway.dispatch("read_source", {"chunk_ids": ["SYN-p1"], "neighbor_pages": 0})
    records = [ctx(), extraction_claim("F1", "REVIEW_ALREADY"), extraction_claim("F2", "REVIEW2_ALREADY")]
    registered = register_wire(gateway, {"records": records, "document_version_notes": [], "extraction_limits": []})
    assert registered["ok"]
    schema = gateway.review_schema()
    assert declaration(schema)["pattern"] == "^REVIEW3_[A-Za-z0-9_-]+$"
    assert declaration(initial)["pattern"] == "^REVIEW_[A-Za-z0-9_-]+$"
    assert {f["claim_id"] for f in gateway.store.facts(gateway.store.current_id).values()} == {"REVIEW_ALREADY", "REVIEW2_ALREADY"}
    # Existing extraction claim references remain legal outside new declarations.
    evidence_claim = schema["properties"]["judgments"]["items"]["properties"]["evidence"]["items"]["properties"]["claim_id"]
    assert Draft202012Validator(evidence_claim).is_valid("REVIEW_ALREADY")


@pytest.mark.parametrize("claim_id,valid", [("REVIEW_F1", True), ("REVIEW_a-2_b", True),
    ("C_F", False), ("REVIEW_", False), ("REVIEW_공시", False), ("REVIEW_" + "x" * 160, False)])
def test_declaration_requires_nonempty_bounded_ascii_suffix(tmp_path, claim_id, valid):
    leaf = declaration(real_gateway(tmp_path).review_schema())
    assert Draft202012Validator(leaf).is_valid(claim_id) is valid


def test_review_namespace_leaf_does_not_mutate_global_schema_or_other_string_and_boolean_leaves(tmp_path):
    before = deepcopy(REVIEW_V2)
    gateway = real_gateway(tmp_path)
    schema = gateway.review_schema()
    leaf = declaration(schema)
    judgment = schema["properties"]["judgments"]["items"]["properties"]
    other = [judgment["judgment_id"], judgment["conclusion"], judgment["facts"]["items"]["properties"]["text"],
             judgment["facts"]["items"]["properties"]["evidence"]["items"]["properties"]["claim_id"],
             judgment["evidence"]["items"]["properties"]["doc_id"],
             schema["properties"]["scope"]["properties"]["document_ids"]["items"]]
    assert all(item is not leaf and "pattern" not in item and "maxLength" not in item for item in other)
    for group in ("requests", "escalations"):
        boolean = schema["properties"][group]["items"]["properties"]["blocking"]
        assert Draft202012Validator(boolean).is_valid(True)
    leaf["pattern"] = "CORRUPT_LOCAL_COPY"
    assert declaration(gateway.review_schema())["pattern"] == "^REVIEW_[A-Za-z0-9_-]+$"
    assert REVIEW_V2 == before
    gateway.run.config["dynamic_submission_contract"] = False
    assert gateway.review_schema() == REVIEW_V2


def test_bad_new_declaration_is_rejected_and_format_patch_cannot_rename_it(tmp_path):
    schema = real_gateway(tmp_path).review_schema()
    value = review("X_EMPTY")
    original = deepcopy(value)
    assert not Draft202012Validator(schema).is_valid(value)
    for op in ({"op": "RELINK_CLAIM", "path": "/judgments/0/facts/0/claim_id", "claim_id": "REVIEW_FIXED"},
               {"op": "REMOVE_EXTRA", "path": "/judgments/0/facts/0/claim_id"}):
        with pytest.raises(FormatPatchError):
            apply_format_patch(value, {"operations": [op]}, schema)
    assert value == original
