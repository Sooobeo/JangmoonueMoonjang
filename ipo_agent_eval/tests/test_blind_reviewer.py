"""Synthetic checks for the A1 B role. No external call or historical case is used."""
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError

from ipo_eval import blind_reviewer as b


def excerpt(number):
    return {"evidence_id": f"E{number:03}", "text": f"합성 근거 {number}"}


@pytest.fixture
def packet():
    return {"issuer_evidence": [excerpt(1)], "candidates": [
        {"candidate_id": "C003", "business": [excerpt(2)], "financials": [], "multiples": []},
        {"candidate_id": "C002", "business": [excerpt(3)], "financials": [], "multiples": []},
        {"candidate_id": "C001", "business": [excerpt(4)], "financials": [], "multiples": []}]}


def save(path, packet):
    data = json.dumps(packet, ensure_ascii=False).encode()
    path.write_bytes(data)
    return path, b.sha(data)


class TestPacket:
    def test_hash_and_ids(self, tmp_path, packet):
        path, digest = save(tmp_path / "packet.json", packet)
        assert b.load_packet(path, digest) == (packet, {"E001", "E002", "E003", "E004"})
        path.write_bytes(path.read_bytes() + b" ")
        with pytest.raises(ValueError, match="SHA-256"):
            b.load_packet(path, digest)

    @pytest.mark.parametrize("mutation", ["target", "url", "duplicate_candidate", "duplicate_evidence", "blank"])
    def test_invalid_fields(self, tmp_path, packet, mutation):
        candidate = packet["candidates"][0]
        if mutation == "target":
            candidate["selected"] = True
        elif mutation == "url":
            candidate["business"][0]["text"] = "https://example.invalid/key"
        elif mutation == "duplicate_candidate":
            candidate["candidate_id"] = "C002"
        elif mutation == "duplicate_evidence":
            candidate["business"][0]["evidence_id"] = "E001"
        else:
            candidate["business"][0]["text"] = "  "
        with pytest.raises((ValueError, ValidationError)):
            b.load_packet(*save(tmp_path / "packet", packet))

    def test_duplicate_json_key(self, tmp_path):
        path = tmp_path / "packet"
        path.write_bytes(b'{"candidates": [], "candidates": []}')
        with pytest.raises(ValueError, match="Duplicate JSON"):
            b.load_packet(path, b.sha(path.read_bytes()))


class TestOrderingAndAudit:
    def test_only_order_changes(self, packet):
        original = deepcopy(packet)
        first = b.ordered_packet(packet, "B1", 3)
        assert [c["candidate_id"] for c in first["candidates"]] == ["C001", "C002", "C003"]
        for seed in range(128):
            second = b.ordered_packet(packet, "B2", seed)
            assert first != second == b.ordered_packet(packet, "B2", seed)
            assert first == b.ordered_packet(second, "B1", seed)
        assert original == packet
        packet["candidates"] = packet["candidates"][:1]
        with pytest.raises(ValueError, match="at least two"):
            b.ordered_packet(packet, "B2", 1)

    def test_scope_excludes_other_material(self, packet):
        config = b.read_config(b.ROOT / "config/B.json")
        request = b.make_request(config, packet, "static instructions")
        assert json.loads(request["input"]) == packet
        assert not {"tools", "previous_response_id", "conversation", "attachments"} & request.keys()
        assert request["store"] is False

    def test_scoring_preserves_omissions_and_bad_citations(self):
        answer = b.mock_answer(["C001", "C001", "C099"])
        answer["candidates"][0]["evidence_ids"] = ["E001", "E999"]
        audit = b.audit_answer(answer, {"C001", "C002"}, {"E001"})
        assert audit["missing_candidates"] == ["C002"]
        assert audit["unknown_candidates"] == ["C099"]
        assert audit["duplicate_candidates"] == ["C001"]
        assert audit["unknown_evidence_ids"] == ["E999"]
        assert audit["candidates_without_citations"] == ["C001", "C099"]
        with pytest.raises(ValidationError):
            b.audit_answer({"status": "READY"}, {"C001"}, {"E001"})


def fake_client(texts, calls):
    replies = iter(texts)

    def create(**kwargs):
        calls.append(kwargs)
        return {"id": f"mock-{len(calls)}", "model": "mock-model", "status": "completed",
                "usage": {"input_tokens": 12, "output_tokens": 10},
                "output": [{"type": "message", "content": [{"type": "output_text", "text": next(replies)}]}]}

    return SimpleNamespace(responses=SimpleNamespace(create=create))


class TestExecution:
    def test_cli_offline_b1_b2(self, tmp_path, packet):
        path, digest = save(tmp_path / "hidden-case-filename.json", packet)
        cmd = [sys.executable, "-m", "ipo_eval.blind_reviewer", "--packet", str(path),
               "--packet-sha256", digest, "--case-id", "SYNTHETIC-PRIVATE-CASE", "--seed", "23",
               "--output-root", str(tmp_path), "--mock"]
        first = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=b.ROOT)
        baseline = Path(first.stdout.strip().split(" ", 1)[1])
        second = subprocess.run([*cmd, "--variant", "B2", "--baseline", str(baseline)],
                                capture_output=True, text=True, check=True, cwd=b.ROOT)
        diagnostic = Path(second.stdout.strip().split(" ", 1)[1])
        left, right = [json.loads((d / "blind_input.json").read_text("utf-8")) for d in (baseline, diagnostic)]
        assert left["freeze"] == right["freeze"]
        assert left["candidate_order"] != right["candidate_order"]
        assert right["baseline_run_id"] == left["run_id"]
        assert (diagnostic / "mock_review.json").is_file()
        assert not (diagnostic / "blind_review.json").exists()
        assert path.name not in (diagnostic / "blind_request.json").read_text("utf-8")
        assert "SYNTHETIC-PRIVATE-CASE" not in (diagnostic / "blind_request.json").read_text("utf-8")
        assert json.loads((diagnostic / "summary.json").read_text("utf-8"))["model_calls"] == 0
        for mode, seed in [("mock", 24), ("live", 23)]:
            with pytest.raises(ValueError, match="matching mode"):
                b.execute(path, digest, "SYNTHETIC-PRIVATE-CASE", seed, variant="B2",
                          baseline=baseline, mode=mode, output=tmp_path)
        (baseline / "blind_request.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="matching mode"):
            b.execute(path, digest, "SYNTHETIC-PRIVATE-CASE", 23, variant="B2",
                      baseline=baseline, mode="mock", output=tmp_path)

    def test_default_preflight_offline(self, tmp_path, packet):
        path, summary = b.execute(*save(tmp_path / "packet", packet), "SYNTHETIC", 1, output=tmp_path)
        assert summary["execution_status"] == "PREFLIGHT_COMPLETE"
        assert summary["model_calls"] == 0
        assert not (path / "blind_review.json").exists()

    @pytest.mark.parametrize("valid_reply", [True, False])
    def test_responses_path_offline(self, tmp_path, monkeypatch, packet, valid_reply):
        from ipo_eval import runtime_v2
        monkeypatch.setattr(runtime_v2.tiktoken, "get_encoding",
                            lambda _: SimpleNamespace(encode=lambda text: list(text)))
        path, digest = save(tmp_path / "packet", packet)
        calls = []
        reply = json.dumps(b.mock_answer(["C001"])) if valid_reply else "{}"
        client = fake_client(["broken", reply], calls)
        folder, summary = b.execute(path, digest, "SYNTHETIC", 1, output=tmp_path, mode="live", client=client)
        assert summary["execution_status"] == ("SUBMITTED" if valid_reply else "FAILED")
        assert summary["model_calls"] == 2
        assert json.loads((folder / "01_blind_review_request.json").read_text("utf-8")) == json.loads(
            (folder / "02_blind_review_request.json").read_text("utf-8"))
        assert len(calls) == 2 and all("tools" not in call for call in calls)
        assert summary["input_tokens"] == 24 and summary["output_tokens"] == 20
        if valid_reply:
            assert summary["citation_and_coverage_audit"]["missing_candidates"] == ["C002", "C003"]
            assert summary["response_id"] == "mock-2"
        else:
            assert not (folder / "blind_review.json").exists()

    def test_missing_key(self, tmp_path, monkeypatch, packet):
        from ipo_eval import runner, runtime_v2
        monkeypatch.setattr(runner, "api_key", lambda: None)
        monkeypatch.setattr(runtime_v2.tiktoken, "get_encoding", lambda _: None)
        _, summary = b.execute(*save(tmp_path / "packet", packet), "SYNTHETIC", 1,
                               output=tmp_path, mode="live")
        assert summary["execution_status"] == "NOT_STARTED_MISSING_API_KEY"
        assert summary["model_calls"] == 0

    def test_budget_is_checked_before_request(self, tmp_path, monkeypatch, packet):
        from ipo_eval import runtime_v2

        monkeypatch.setattr(runtime_v2.tiktoken, "get_encoding",
                            lambda _: SimpleNamespace(encode=lambda text: list(text)))
        config = json.loads((b.ROOT / "config/B.json").read_text("utf-8"))
        config["max_run_usd"] = 0.000001
        settings, _ = save(tmp_path / "config.json", config)
        calls = []
        _, summary = b.execute(*save(tmp_path / "packet", packet), "SYNTHETIC", 1, output=tmp_path,
                               config_path=settings, mode="live", client=fake_client([], calls))
        assert calls == [] and summary["execution_status"] == "FAILED" and summary["error_type"] == "BudgetError"
