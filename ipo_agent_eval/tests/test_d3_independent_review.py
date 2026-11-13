"""Independent D3 adversarial checks, separate from gateway implementation."""
from copy import deepcopy

import pytest

from ipo_eval.budget import BudgetError, check_request
from ipo_eval.tool_gateway import ToolGateway
from test_budget_v2 import state
from test_runtime_v2 import runtime, response


class SyntheticCorpus:
    def __init__(self):
        self.case = {"case_id": "SYN", "allowed_doc_ids": ["DOC"]}
        self.by_id = {"DOC-p1": {"chunk_id": "DOC-p1", "doc_id": "DOC", "page": 1, "text": "synthetic entire page"}}

    def read_source(self, chunk_ids, neighbor_pages):
        return {"chunks": [deepcopy(self.by_id[k]) for k in chunk_ids], "truncated": False}

    def search_corpus(self, case_id, query, filters, top_k):
        return {"query": query, "hits": [{"doc_id": "DOC", "chunk_id": "DOC-p1", "page": 1, "excerpt": "synthetic"}]}


def make_gateway(tmp_path):
    run = runtime(tmp_path, response())
    run.phase = "EXPLORING"
    return ToolGateway(run, SyntheticCorpus())


def review(snapshot):
    return {"scope": {"document_ids": ["DOC"], "verification_limits": ["synthetic"]},
        "judgments": [{"judgment_id": j, "domain": j, "conclusion": "Synthetic uncertainty", "disposition": "CONDITIONAL",
                       "facts": [], "evidence": [], "counter_evidence": [], "unknowns": ["Synthetic gap"], "next_action": "Synthetic follow-up"}
                      for j in ["J1", "J2", "J3", "J4"]],
        "requests": [], "escalations": [], "missing_inputs": [], "memo": [], "model_reported_status": "READY",
        "input_snapshot_id": snapshot, "calculation_uses": [], "not_found_reasons": []}


@pytest.mark.parametrize("phase,tool_calls", [("FINALIZING", 38), ("REPAIR", 40)])
def test_final_model_call_is_blocked_when_actual_submission_tools_do_not_fit(phase, tool_calls):
    run = state(tool_calls=tool_calls, repairs=1 if phase == "REPAIR" else 0)
    with pytest.raises(BudgetError, match="TOOL_CALL"):
        check_request(run, 1000, 1000, phase)


def test_observation_reservation_failure_never_marks_full_page_read(tmp_path):
    gateway = make_gateway(tmp_path)
    def reject(result):
        raise BudgetError("SYNTHETIC_RESERVATION_FAILURE")
    gateway.run.observation_guard = reject
    envelope = gateway.dispatch("read_source", {"chunk_ids": ["DOC-p1"], "neighbor_pages": 0}, "read1")
    assert not envelope["ok"] and envelope["error_code"] == "BUDGET_LIMIT"
    assert envelope["usage_delta"]["tool_calls"] == 1
    assert not gateway.read_chunks and not envelope["result"]["partial_execution"]


def test_search_excerpt_is_not_read_evidence_and_reread_is_counted(tmp_path):
    gateway = make_gateway(tmp_path)
    assert gateway.dispatch("search_corpus", {"query": "synthetic", "top_k": 1, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}}, "s1")["ok"]
    assert not gateway.read_chunks
    first = gateway.dispatch("read_source", {"chunk_ids": ["DOC-p1"], "neighbor_pages": 0}, "r1")
    second = gateway.dispatch("read_source", {"chunk_ids": ["DOC-p1"], "neighbor_pages": 0}, "r2")
    assert first["usage_delta"]["new_read_pages"] == 1
    assert second["usage_delta"]["new_read_pages"] == 0
    assert second["usage_delta"]["pages"] == 1


def test_omitting_prior_open_request_does_not_erase_blocking_state(tmp_path):
    gateway = make_gateway(tmp_path)
    request = {"request_id": "R1", "question": "Synthetic question", "why_needed": "Synthetic need",
               "related_judgment_ids": ["J1"], "blocking": True, "resolution_status": "OPEN",
               "resolution_evidence": [], "version": 1, "change_reason": None}
    assert gateway.dispatch("request_information", {"requests": [request]}, "q1")["ok"]
    gateway.run.phase = "FINALIZING"
    result = gateway.dispatch("submit_review", {"phase": "COMMIT", "input_snapshot_id": "X_EMPTY", "review": review("X_EMPTY")}, "c1")
    assert result["ok"] and result["result"]["content_status"] == "PENDING_INFO"
    assert gateway.submitted_review["requests"] == [request]
    assert result["usage_delta"]["tool_calls"] == 3


def test_isolation_violation_prevents_every_later_tool(tmp_path):
    gateway = make_gateway(tmp_path)
    first = gateway.dispatch("read_source", {"chunk_ids": ["OTHER-CASE-p1"], "neighbor_pages": 0}, "x1")
    assert first["error_code"] == "ISOLATION_VIOLATION"
    second = gateway.dispatch("read_source", {"chunk_ids": ["DOC-p1"], "neighbor_pages": 0}, "x2")
    assert second["error_code"] == "ISOLATION_VIOLATION" and not gateway.read_chunks
