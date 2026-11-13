"""Mock providers exercise the real gateway and loop, without paid requests."""
from copy import deepcopy
import hashlib
import json

import pytest

from ipo_eval.agent_loop import _format_only
from ipo_eval.runner import ROOT
from ipo_eval.runner_v2 import execute_v2
from test_contracts_v2 import ctx, fact, component, coverage, ev


@pytest.fixture
def v2_root(tmp_path):
    for directory in ("config", "prompts", "ipo_eval", "data/public/raw"):
        (tmp_path / directory).mkdir(parents=True)
    for name in ("B.json", "A0.json", "cases.json"):
        (tmp_path / "config" / name).write_bytes((ROOT / "config" / name).read_bytes())
    # Historical full-v2 scripted outputs remain a regression path. Compact
    # transport and patch responses have separate provider integration tests.
    for name in ("B.json", "A0.json"):
        path = tmp_path / "config" / name
        config = json.loads(path.read_text(encoding="utf-8"))
        for key in ("wire_contract", "format_repair_contract", "dynamic_submission_contract"):
            config.pop(key, None)
        path.write_text(json.dumps(config), encoding="utf-8")
    for name in ("common.md", "v2_contract.md", "A0.md"):
        (tmp_path / "prompts" / name).write_bytes((ROOT / "prompts" / name).read_bytes())
    directory = tmp_path / "data/public"
    raw = b"SYNTHETIC PDF fixture bytes"
    (directory / "raw/SYN.pdf").write_bytes(raw)
    config = json.loads((tmp_path / "config/B.json").read_text(encoding="utf-8"))
    records = {
        "case_manifest.jsonl": {"case_id": "HDMS-DEV-01", "issuer_name": "SYNTHETIC", "cutoff_at": "2000-12-31", "allowed_doc_ids": ["SYN"]},
        "documents.jsonl": {"doc_id": "SYN", "sha256": hashlib.sha256(raw).hexdigest(), "pages": 1, "cutoff_status": "BEFORE"},
        "chunks.jsonl": {"case_id": "HDMS-DEV-01", "doc_id": "SYN", "chunk_id": "SYN-p1", "page": 1,
            "printed_page": 1, "text": " ".join(q["query"] for q in config["fixed_queries"]), "cutoff_status": "BEFORE"},
    }
    for name, record in records.items():
        (directory / name).write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    (directory / "manual.md").write_text("SYNTHETIC common method", encoding="utf-8")
    (tmp_path / "PRIVATE_GOLD_DO_NOT_READ.txt").write_text("SECRET_GOLD_745", encoding="utf-8")
    return tmp_path


def records():
    return [ctx(), fact(), component("SC", "F"), coverage()]


def review(snapshot, calc=None, unknown=False):
    return {"input_snapshot_id": snapshot, "scope": {"document_ids": ["SYN"], "verification_limits": ["synthetic"]},
        "judgments": [{"judgment_id": j, "domain": j, "conclusion": "synthetic conclusion", "disposition": "CONDITIONAL",
            "facts": [] if unknown else [{"claim_id": "R_" + j, "text": "synthetic fact", "evidence": [ev("R_" + j)]}],
            "evidence": [], "counter_evidence": [], "unknowns": ["not read"] if unknown else [], "next_action": "synthetic next action"}
            for j in ("J1", "J2", "J3", "J4")],
        "requests": [], "escalations": [], "missing_inputs": [], "not_found_reasons": [],
        "memo": ["SYNTHETIC"], "model_reported_status": "READY",
        "calculation_uses": [] if calc is None else [{"calc_id": calc["calc_id"], "use": "USE", "stated_value": calc["result"],
            "related_judgment_ids": ["J3"], "reason": "synthetic arithmetic", "replacement_id": None, "unresolved": False}]}


def message(value):
    return [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(value)}]}]


class Scripted:
    def __init__(self, mode="A0", bad_reference=False, no_tool=False):
        self.mode = mode
        self.calls = []
        self.responses = self
        self.bad_reference = bad_reference
        self.no_tool = no_tool

    def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        n = len(self.calls)
        fmt = kwargs.get("text", {}).get("format", {}).get("name")
        if fmt == "format_repair":
            payload = json.loads(kwargs["input"][0]["content"])
            value = payload["previous_output"]
            r = value.get("review", value)
            r["judgments"][0]["facts"][0]["evidence"][0]["claim_id"] = "R_J1"
            output = message(value)
        elif self.mode == "B":
            if fmt == "extraction_v2":
                output = message({"records": records(), "document_version_notes": [], "extraction_limits": ["synthetic"]})
            else:
                payload = json.loads(kwargs["input"][1]["content"])
                calc = next(c for c in payload["calculations"] if c["status"] == "OK")
                output = message(review(payload["extraction_snapshot"]["input_snapshot_id"], calc))
        elif self.no_tool:
            output = message({"note": "no function call"})
        else:
            observations = [json.loads(x["output"]) for x in kwargs["input"] if x.get("type") == "function_call_output"]
            snapshot = next((r["result"]["input_snapshot_id"] for r in reversed(observations)
                if r["ok"] and "input_snapshot_id" in r["result"]), "X_EMPTY")
            finalizing = kwargs.get("tool_choice", {}).get("name") == "submit_review"
            if finalizing:
                calcs = [c for r in observations if r["ok"] for c in r["result"].get("calculations", []) if c["status"] == "OK"]
                r = review(snapshot, calcs[0] if calcs else None, unknown=not calcs)
                if self.bad_reference and calcs:
                    r["judgments"][0]["facts"][0]["evidence"][0]["claim_id"] = "INVALID_LINK"
                name, args = "submit_review", {"phase": "COMMIT", "input_snapshot_id": snapshot, "review": r}
            else:
                name, args = [
                    ("search_corpus", {"query": "적용 주식수", "top_k": 1, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}}),
                    ("read_source", {"chunk_ids": ["SYN-p1"], "neighbor_pages": 0}),
                    ("calculate", {"request": {"operation": "REGISTER_BATCH", "base_snapshot_id": snapshot, "records": records()}}),
                    ("calculate", {"request": {"operation": "EVALUATE", "input_snapshot_id": snapshot, "calculation_types": ["SHARE_SUM"]}}),
                    ("search_corpus", {"query": "없는단어", "top_k": 1, "filters": {"doc_id": None, "cutoff_status": "BEFORE"}}),
                    ("submit_review", {"phase": "PREPARE", "input_snapshot_id": snapshot}),
                ][n - 1]
            output = [{"type": "reasoning", "id": "rs_" + str(n), "summary": [], "encrypted_content": "SYNTHETIC_REASONING_" + str(n)},
                      {"type": "function_call", "call_id": "call_" + str(n), "name": name, "arguments": json.dumps(args)}]
        return {"id": "response_" + str(n), "model": "gpt-6.1-terra", "status": "completed", "output": output,
                "usage": {"input_tokens": 100, "output_tokens": 100}}


def test_T15_full_autonomous_path_preserves_reasoning_and_call_ids(v2_root):
    client = Scripted()
    directory, summary = execute_v2(True, v2_root, condition="A0", client=client)
    assert summary["execution_status"] == "SUBMITTED", summary
    assert summary["model_calls"] == 7 and summary["tool_calls"] == 9
    assert all(c["parallel_tool_calls"] is False for c in client.calls)
    assert client.calls[1]["input"][2]["type"] == "reasoning"
    assert client.calls[1]["input"][-1]["call_id"] == "call_1"
    assert [t["name"] for t in client.calls[-1]["tools"]] == ["submit_review"]
    saved = "".join(p.read_text(encoding="utf-8") for p in directory.glob("*.json*"))
    assert "SECRET_GOLD_745" not in saved
    assert json.loads((directory / "summary.json").read_text(encoding="utf-8"))["condition"] == "A0"


def test_B_uses_same_contract_and_22_actual_tools(v2_root):
    client = Scripted("B")
    directory, summary = execute_v2(True, v2_root, condition="B", client=client)
    assert summary["execution_status"] == "SUBMITTED", summary
    assert summary["tool_calls"] == 22 and summary["model_calls"] == 2
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(e["actor"] in {"program_fixed", "program_commit"} for e in events if e["event"] == "tool_call")
    assert " B " in (directory / "review.md").read_text(encoding="utf-8")


def test_T16_tool_free_finish_is_a_preserved_failure(v2_root):
    directory, summary = execute_v2(True, v2_root, condition="A0", client=Scripted(no_tool=True))
    assert summary["execution_status"] == "FAILED"
    assert summary["failure_reason"] == "NO_VALID_SUBMISSION"
    assert summary["final_status"] is None
    assert (directory / "01_explore_response.json").exists() and not (directory / "review.json").exists()


def test_T13_budget_forces_only_finalization_without_an_exploration_call(v2_root):
    path = v2_root / "config/A0.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["max_model_calls"] = 2
    path.write_text(json.dumps(config), encoding="utf-8")
    client = Scripted()
    _, summary = execute_v2(True, v2_root, condition="A0", client=client)
    assert summary["execution_status"] == "SUBMITTED", summary
    assert len(client.calls) == 1
    assert client.calls[0]["tool_choice"] == {"type": "function", "name": "submit_review"}


def test_shared_format_repair_cannot_reread_or_change_facts(v2_root):
    client = Scripted(bad_reference=True)
    directory, summary = execute_v2(True, v2_root, condition="A0", client=client)
    assert summary["execution_status"] == "SUBMITTED", summary
    assert summary["format_repairs"] == 1 and summary["tool_calls"] == 10
    assert "format_repair_tool_result" in (directory / "context.json").read_text(encoding="utf-8")
    assert "tools" not in client.calls[-1]
    with pytest.raises(RuntimeError, match="REPAIR_CHANGED_FACT"):
        _format_only({"value": "10"}, {"value": "20"})
    with pytest.raises(RuntimeError, match="REPAIR_CHANGED_FACT"):
        _format_only({"blocking": True}, {"blocking": False})


def test_T18_fresh_context_for_every_repetition(v2_root):
    left, right = Scripted(), Scripted()
    d1, s1 = execute_v2(True, v2_root, condition="A0", repeat=1, client=left)
    d2, s2 = execute_v2(True, v2_root, condition="A0", repeat=2, client=right)
    assert s1["execution_status"] == s2["execution_status"] == "SUBMITTED"
    assert d1 != d2
    assert left.calls[0]["input"] == right.calls[0]["input"]
    assert len(right.calls[0]["input"]) == 2


def test_T16_registration_and_final_review_share_one_repair(v2_root):
    class TwoBrokenReferences:
        def __init__(self):
            self.responses = self
            self.script = Scripted(bad_reference=True)
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(deepcopy(kwargs))
            if kwargs.get("text", {}).get("format", {}).get("name") == "format_repair":
                value = json.loads(kwargs["input"][0]["content"])["previous_output"]
                row = next(r for r in value["request"]["records"] if r["kind"] == "VALUE")
                row["payload"]["evidence"][0]["claim_id"] = row["payload"]["claim_id"]
                return {"id": "registration_repair", "model": "gpt-6.1-terra", "status": "completed",
                    "output": message(value), "usage": {"input_tokens": 100, "output_tokens": 100}}
            simulated = deepcopy(kwargs)
            for item in kwargs["input"]:
                if item.get("role") == "user" and isinstance(item.get("content"), str):
                    try:
                        context = json.loads(item["content"])
                    except ValueError:
                        continue
                    if "format_repair_tool_result" in context:
                        simulated["input"].append({"type": "function_call_output", "call_id": "mock_observation",
                            "output": json.dumps(context["format_repair_tool_result"])})
            raw = self.script.create(**simulated)
            if len(self.script.calls) == 3:
                call = next(item for item in raw["output"] if item["type"] == "function_call")
                value = json.loads(call["arguments"])
                row = next(r for r in value["request"]["records"] if r["kind"] == "VALUE")
                row["payload"]["evidence"][0]["claim_id"] = "BROKEN_REGISTRATION_LINK"
                call["arguments"] = json.dumps(value)
            return raw

    client = TwoBrokenReferences()
    directory, summary = execute_v2(True, v2_root, condition="A0", client=client)
    assert summary["failure_reason"] == "FORMAT_REPAIR_EXHAUSTED", summary
    assert summary["execution_status"] == "FAILED" and summary["final_status"] is None
    assert summary["format_repairs"] == 1
    repairs = [c for c in client.calls if c.get("text", {}).get("format", {}).get("name") == "format_repair"]
    assert len(repairs) == 1 and len(client.calls) == 8
    assert (directory / "snapshots.json").exists()
    assert not (directory / "review.json").exists()
