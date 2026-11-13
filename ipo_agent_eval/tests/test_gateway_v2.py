"""Shared gateway isolation, actual reads, ledger and finalization invariants."""
from copy import deepcopy

import pytest

from ipo_eval.budget import BudgetError
from ipo_eval.provenance import SnapshotStore
from ipo_eval.tool_gateway import RequestLedger, ToolGateway
from ipo_eval.validation_v2 import final_status, validate_review
from test_contracts_v2 import ctx, fact, rec, ev, component, coverage, market_records


class FakeRun:
    def __init__(self):
        self.config = {"max_tool_calls": 40, "max_format_repairs": 1, "condition": "A0"}
        self.phase = "EXPLORING"
        self.tool_calls = self.repairs = 0
        self.events = []
        self.guard = None
        self.requests = self.escalations = []

    def log(self, event, data):
        self.events.append({"event": event, **deepcopy(data)})

    def tool(self, name, arguments, callback, reserved_calls=0, actor=None, call_id=None):
        if self.tool_calls + 1 + reserved_calls > self.config["max_tool_calls"]:
            raise BudgetError("TOOL_CALL_RESERVATION")
        self.tool_calls += 1
        self.log("attempt", {"name": name, "actor": actor, "call_id": call_id})
        return callback()

    def reserve_observation(self, result):
        if self.guard:
            self.guard(result)


class FakeCorpus:
    def __init__(self):
        self.case = {"case_id": "SYN-DEV", "allowed_doc_ids": ["SYN"]}
        self.chunks = [{"case_id": "SYN-DEV", "chunk_id": f"SYN-p{page}", "doc_id": "SYN", "page": page,
                        "text": "Complete synthetic page " + str(page), "cutoff_status": "BEFORE"} for page in range(1, 13)]
        self.by_id = {item["chunk_id"]: item for item in self.chunks}

    def search_corpus(self, case_id, query, filters, top_k):
        assert case_id == "SYN-DEV" and filters["cutoff_status"] == "BEFORE"
        hits = [] if query == "NO_MATCH" else [{"chunk_id": c["chunk_id"], "doc_id": c["doc_id"],
                    "page": c["page"], "excerpt": "partial"} for c in self.chunks[:top_k]]
        return {"query": query, "hits": hits, "total_matches": len(hits)}

    def read_source(self, chunk_ids, neighbor_pages):
        wanted = {chunk["page"] for selected in chunk_ids for chunk in self.chunks
                  if abs(chunk["page"] - self.by_id[selected]["page"]) <= neighbor_pages}
        return {"chunks": [deepcopy(c) for c in self.chunks if c["page"] in wanted], "truncated": False}


def gateway():
    return ToolGateway(FakeRun(), FakeCorpus())


def read(g, ids=None):
    return g.dispatch("read_source", {"chunk_ids": ids or ["SYN-p1"], "neighbor_pages": 0})


def register(g, records):
    return g.dispatch("calculate", {"request": {"operation": "REGISTER_BATCH", "base_snapshot_id": g.store.current_id,
                                                "records": records}})


def review(snapshot="X_EMPTY"):
    return {"scope": {"document_ids": ["SYN"], "verification_limits": ["Synthetic test"]},
            "judgments": [{"judgment_id": f"J{i}", "domain": f"J{i}", "conclusion": "Evidence remains limited",
                "disposition": "CONDITIONAL", "facts": [], "evidence": [], "counter_evidence": [],
                "unknowns": ["Not all inputs are read"], "next_action": "Request further review"} for i in range(1, 5)],
            "requests": [], "escalations": [], "missing_inputs": [], "memo": [],
            "model_reported_status": "READY", "input_snapshot_id": snapshot,
            "calculation_uses": [], "not_found_reasons": []}


def request(ident="R1", **extra):
    return {"request_id": ident, "question": "What is the missing input?", "why_needed": "Resolve the stated limitation",
            "related_judgment_ids": ["J1"], "blocking": True, "resolution_status": "OPEN", "resolution_evidence": [],
            "version": 1, "change_reason": None, **extra}


def commit(g, value=None):
    g.run.phase = "FINALIZING"
    return g.dispatch("submit_review", {"phase": "COMMIT", "input_snapshot_id": g.store.current_id,
                                         "review": value or review(g.store.current_id)})


def test_seven_tools_are_strict_and_final_phase_only_exposes_commit():
    g = gateway()
    tools = g.tools("EXPLORING")
    assert len(tools) == 7
    assert all(tool["strict"] and tool["parameters"]["type"] == "object" for tool in tools)
    assert [tool["name"] for tool in g.tools("FINALIZING")] == ["submit_review"]
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for item in node.values():
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)
    visit(tools)


def test_search_hit_is_not_read_evidence_and_failed_registration_is_atomic():
    g = gateway()
    found = g.dispatch("search_corpus", {"query": "synthetic", "top_k": 1, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}})
    assert found["ok"] and found["result"]["hits"]
    assert not g.read_chunks
    blocked = register(g, [ctx(), fact()])
    assert not blocked["ok"] and blocked["error_code"] == "UNREAD_EVIDENCE"
    assert g.store.current_id == "X_EMPTY" and blocked["result"]["partial_execution"] is False
    assert read(g)["ok"]
    assert register(g, [ctx(), fact()])["ok"]


@pytest.mark.parametrize("field,bad", [("top_k", True), ("top_k", -1), ("top_k", 1.0), ("top_k", 1.5),
                                       ("neighbor_pages", False), ("neighbor_pages", -1), ("neighbor_pages", 1.0)])
def test_noninteger_negative_or_boolean_range_inputs_rejected_and_counted(field, bad):
    g = gateway()
    args = ({"query": "terms", "top_k": bad, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}} if field == "top_k"
            else {"chunk_ids": ["SYN-p1"], "neighbor_pages": bad})
    result = g.dispatch("search_corpus" if field == "top_k" else "read_source", args)
    assert not result["ok"] and result["error_code"] == "INVALID_ARGUMENT"
    assert result["usage_delta"]["tool_calls"] == 1 and not g.read_chunks


@pytest.mark.parametrize("args", [
    {"query": "terms", "top_k": 1, "filters": {"doc_id": "OTHER", "cutoff_status": "BEFORE"}},
    {"query": "terms", "top_k": 1, "filters": {"doc_id": None, "cutoff_status": "AFTER"}},
    {"query": "terms", "top_k": 1, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}, "case_id": "OTHER"},
    {"query": "https://example.test", "top_k": 1, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}},
    {"query": "../private/gold.json", "top_k": 1, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}},
])
def test_isolation_violations_are_fatal_and_return_no_material(args):
    g = gateway()
    result = g.dispatch("search_corpus", args)
    assert result["error_code"] == "ISOLATION_VIOLATION" and g.fatal_error
    assert not g.read_chunks and not g.search_hits
    assert read(g)["error_code"] == "ISOLATION_VIOLATION"


def test_other_case_chunk_and_malformed_doc_id_are_handled_before_access():
    g = gateway()
    assert read(g, ["OTHER-p1"])["error_code"] == "ISOLATION_VIOLATION"
    g = gateway()
    result = g.dispatch("search_corpus", {"query": "q", "top_k": 1, "filters": {"doc_id": [], "cutoff_status": "BEFORE"}})
    assert result["error_code"] == "INVALID_ARGUMENT"


def test_full_pages_are_deduplicated_and_repeat_reads_are_counted():
    g = gateway()
    result = g.dispatch("read_source", {"chunk_ids": ["SYN-p2", "SYN-p3", "SYN-p2"], "neighbor_pages": 1})
    assert result["ok"] and not result["result"]["truncated"]
    assert [c["page"] for c in result["result"]["chunks"]] == [1, 2, 3, 4]
    assert result["usage_delta"]["pages"] == result["usage_delta"]["new_read_pages"] == 4
    again = read(g, ["SYN-p2"])
    assert again["usage_delta"]["pages"] == 1 and again["usage_delta"]["new_read_pages"] == 0


def test_oversized_read_is_explicit_and_does_not_mark_pages_read():
    g = gateway()
    result = read(g, ["SYN-p1", "SYN-p2", "SYN-p3", "SYN-p4"])
    assert result["error_code"] == "TOO_LARGE" and not g.read_chunks
    g.corpus.read_source = lambda *args: {"chunks": deepcopy(g.corpus.chunks), "truncated": False}
    assert read(g)["error_code"] == "TOO_LARGE" and not g.read_chunks


def test_observation_reservation_prevents_read_and_registration_side_effects():
    g = gateway()
    def fail(_result):
        raise BudgetError("INPUT_RESERVATION")
    g.run.guard = fail
    result = read(g)
    assert result["error_code"] == "BUDGET_LIMIT" and not g.read_chunks
    g.run.guard = None
    assert read(g)["ok"]
    g.run.guard = fail
    result = register(g, [ctx(), fact()])
    assert result["error_code"] == "BUDGET_LIMIT" and g.store.current_id == "X_EMPTY"
    assert result["result"]["partial_execution"] is False


def test_no_hits_are_valid_observations():
    g = gateway()
    result = g.dispatch("search_corpus", {"query": "NO_MATCH", "top_k": 3, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}})
    assert result["ok"] and result["result"]["hits"] == []


def test_common_configured_search_limit_applies_to_b_and_a0():
    for condition in ("B", "A0"):
        g = gateway()
        g.run.config.update(condition=condition, search_top_k_max=2)
        schema = next(tool for tool in g.tools() if tool["name"] == "search_corpus")["parameters"]
        assert schema["properties"]["top_k"]["maximum"] == 2
        result = g.dispatch("search_corpus", {"query": "terms", "top_k": 3,
                            "filters": {"doc_id": None, "cutoff_status": "BEFORE"}})
        assert result["error_code"] == "INVALID_ARGUMENT"


def test_requests_are_versioned_idempotent_and_cannot_disappear_at_commit():
    g = gateway()
    first = g.dispatch("request_information", {"requests": [request()]})
    assert first["ok"]
    assert g.dispatch("request_information", {"requests": [request()]})["ok"]
    assert len(g.ledger.history) == 1
    result = commit(g)
    assert result["ok"] and result["result"]["content_status"] == "PENDING_INFO"
    assert g.submitted_review["requests"] == [request()]
    assert result["usage_delta"]["tool_calls"] == 3
    assert [e["actor"] for e in g.run.events if e["event"] == "attempt"][-2:] == ["program_commit", "program_commit"]


@pytest.mark.parametrize("bad_version", [True, 1.0, 0, -1])
def test_ledger_version_requires_actual_positive_integer(bad_version):
    g = gateway()
    result = g.dispatch("request_information", {"requests": [request(version=bad_version)]})
    assert result["error_code"] == "INVALID_ARGUMENT" and not g.ledger.history


def test_cancellation_and_nonblocking_changes_require_a_new_version_and_reason():
    g = gateway()
    assert g.dispatch("request_information", {"requests": [request()]})["ok"]
    assert not g.dispatch("request_information", {"requests": [request(blocking=False)]})["ok"]
    assert not g.dispatch("request_information", {"requests": [request(version=2, resolution_status="CANCELLED")]})["ok"]
    changed = request(version=2, resolution_status="CANCELLED", change_reason="The question is no longer needed")
    assert g.dispatch("request_information", {"requests": [changed]})["ok"]
    result = commit(g)
    assert result["ok"] and result["result"]["content_status"] == "READY"
    assert len(g.ledger.history) == 2 and g.ledger.history[0]["current"]["resolution_status"] == "OPEN"


def test_resolved_request_requires_read_evidence_and_known_claim():
    g = gateway()
    assert g.dispatch("request_information", {"requests": [request()]})["ok"]
    resolved = request(version=2, resolution_status="RESOLVED", change_reason="Found the input", resolution_evidence=[ev("C_F")])
    assert not g.dispatch("request_information", {"requests": [resolved]})["ok"]
    assert read(g)["ok"] and register(g, [ctx(), fact()])["ok"]
    assert g.dispatch("request_information", {"requests": [resolved]})["ok"]


def test_request_batch_failure_is_atomic_and_cross_group_ids_are_unique():
    g = gateway()
    assert not g.dispatch("request_information", {"requests": [request(), request("R2", version=2)]})["ok"]
    assert not g.ledger.history
    assert g.dispatch("request_information", {"requests": [request()]})["ok"]
    escalation = {"escalation_id": "R1", "review_focus": "Inspect the issue", **{k: v for k, v in request().items() if k != "request_id"}}
    assert not g.dispatch("escalate", {"escalations": [escalation]})["ok"]
    assert not g.ledger.export()["escalations"]


def test_prepare_freezes_snapshot_and_finalization_disallows_exploration():
    g = gateway()
    assert g.dispatch("submit_review", {"phase": "PREPARE", "input_snapshot_id": "X_EMPTY"})["ok"]
    g.run.phase = "FINALIZING"
    assert read(g)["error_code"] == "INVALID_ARGUMENT"
    assert commit(g)["ok"]


def test_finalization_four_reserved_calls_cover_sync_submit_and_one_repair():
    g = gateway()
    read(g)
    g.run.tool_calls = 36
    value = review()
    value["judgments"][0]["facts"] = [{"claim_id": "REPORT_F", "text": "Synthetic observed fact", "evidence": [ev("BAD_ID")]}]
    result = commit(g, value)
    assert result["error_code"] == "INVALID_REVIEW" and result["usage_delta"]["tool_calls"] == 3
    assert g.run.tool_calls == 39
    value["judgments"][0]["facts"][0]["evidence"][0]["claim_id"] = "REPORT_F"
    g.run.repairs = 1
    result = commit(g, value)
    assert result["ok"] and result["usage_delta"]["tool_calls"] == 1 and g.run.tool_calls == 40


def test_too_few_final_tool_calls_block_before_any_sync_or_submit():
    g = gateway()
    g.run.tool_calls = 37
    result = commit(g)
    assert result["error_code"] == "BUDGET_LIMIT" and result["usage_delta"]["tool_calls"] == 0
    assert not g.ledger.history and g.submitted_review is None


def test_schema_error_before_sync_and_integer_repair_still_fit_four_calls():
    g = gateway()
    g.run.tool_calls = 36
    value = review()
    value["requests"] = [request(version="1")]
    result = commit(g, value)
    assert result["error_code"] == "INVALID_ARGUMENT" and g.run.tool_calls == 37
    assert not g.ledger.history
    value["requests"][0]["version"] = 1
    g.run.repairs = 1
    result = commit(g, value)
    assert result["ok"] and result["usage_delta"]["tool_calls"] == 3
    assert g.run.tool_calls == 40 and len(g.ledger.history) == 1


def test_ledger_link_error_before_sync_and_claim_repair_fit_four_calls():
    g = gateway()
    assert read(g)["ok"]
    assert register(g, [ctx(), fact()])["ok"]
    value = review(g.store.current_id)
    value["requests"] = [request(resolution_status="RESOLVED", resolution_evidence=[ev("UNKNOWN")])]
    g.run.tool_calls = 36
    result = commit(g, value)
    assert result["error_code"] == "INVALID_ARGUMENT" and g.run.tool_calls == 37
    assert not g.ledger.history
    value["requests"][0]["resolution_evidence"][0]["claim_id"] = "C_F"
    g.run.repairs = 1
    result = commit(g, value)
    assert result["ok"] and g.run.tool_calls == 40


def test_invalid_both_ledger_groups_do_not_partially_sync():
    g = gateway()
    value = review()
    value["requests"] = [request()]
    value["escalations"] = [{"escalation_id": "R1", "review_focus": "Inspect", **{k: v for k, v in request().items() if k != "request_id"}}]
    result = commit(g, value)
    assert not result["ok"] and result["usage_delta"]["tool_calls"] == 1
    assert result["result"]["partial_execution"] is False and not g.ledger.history


def test_calculation_use_checks_decimal_value_and_snapshot_but_allows_explicit_rejection():
    g = gateway()
    assert read(g)["ok"]
    assert register(g, [ctx(), fact(), component("COMP", "F"), coverage()])["ok"]
    result = g.dispatch("calculate", {"request": {"operation": "EVALUATE", "input_snapshot_id": g.store.current_id,
                                                  "calculation_types": ["SHARE_SUM"]}})
    calc = result["result"]["calculations"][0]
    value = review(g.store.current_id)
    value["calculation_uses"] = [{"calc_id": calc["calc_id"], "use": "USE", "stated_value": "10.0", "related_judgment_ids": ["J1"],
                                  "reason": "Use the registered sum", "replacement_id": None, "unresolved": False}]
    assert not validate_review(value, g.store, g.read_chunks, ["SYN"], g.calculations)
    value["calculation_uses"][0]["stated_value"] = "11"
    assert validate_review(value, g.store, g.read_chunks, ["SYN"], g.calculations)
    old = g.store.current_id
    assert register(g, [fact(value="20")])["ok"]
    value["input_snapshot_id"] = g.store.current_id
    value["calculation_uses"][0]["stated_value"] = "10"
    assert validate_review(value, g.store, g.read_chunks, ["SYN"], g.calculations)
    value["calculation_uses"][0].update(use="REJECT", unresolved=True, stated_value=None, reason="Older snapshot")
    assert not validate_review(value, g.store, g.read_chunks, ["SYN"], g.calculations)
    assert g.calculations[calc["calc_id"]]["input_snapshot_id"] == old


def test_missing_direct_value_with_usable_derivation_does_not_force_external_request():
    g = gateway()
    assert read(g)["ok"]
    records = market_records() + [fact("MISSING", None, "market_cap_million_krw", "CM", "PEER", origin="UNAVAILABLE", evidence=[], missing_reason="not disclosed"),
                rec("SEL", "SELECTION", field="market_cap_million_krw", entity_id="PEER", disclosed_fact_id="MISSING",
                    selected_fact_id="F_CAP", disclosure_status="NOT_FOUND", usability="DERIVABLE", selection_reason="Use the raw inputs")]
    assert register(g, records)["ok"]
    assert commit(g)["ok"] and not g.submitted_review["missing_inputs"]


def test_explicit_unresolved_business_field_links_to_open_request_only():
    g = gateway()
    records = [rec("SEL", "SELECTION", field="earnings_million_krw", entity_id=None, disclosed_fact_id=None,
                   selected_fact_id=None, disclosure_status="NOT_FOUND", usability="UNRESOLVED", selection_reason="Missing required profit")]
    assert register(g, records)["ok"]
    value = review(g.store.current_id)
    assert validate_review(value, g.store, g.read_chunks, ["SYN"], {})
    value["requests"] = [request()]
    value["missing_inputs"] = [{"field": "earnings_million_krw", "missing_reason": "Missing required profit", "request_id": "R1"}]
    assert not validate_review(value, g.store, g.read_chunks, ["SYN"], {})


def test_content_status_is_separate_from_execution_and_semantics_are_not_corrected():
    value = review()
    value["judgments"][0]["conclusion"] = "A semantically wrong conclusion is deliberately left for grading"
    assert commit(gateway(), value)["ok"]
    assert final_status(None, valid=False) is None
    value["requests"] = [request()]
    escalation = {"escalation_id": "E1", "review_focus": "Inspect", **{k: v for k, v in request().items() if k != "request_id"}}
    value["escalations"] = [escalation]
    assert final_status(value) == "HUMAN_REVIEW"


def test_new_gateway_has_no_previous_context_or_ledger():
    old = gateway()
    assert read(old)["ok"]
    assert old.dispatch("request_information", {"requests": [request()]})["ok"]
    new = gateway()
    assert not new.read_chunks and not new.search_hits and not new.calculations and not new.ledger.history
    assert new.store.current_id == "X_EMPTY"
