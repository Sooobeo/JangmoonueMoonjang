"""Three offline reviews of source eligibility, role isolation and session behavior."""
import json
import socket

import fitz
import pytest

from ipo_eval.corpus import Corpus
from scripts import prepare_a1_a0 as a0


def pdf(root, name, content):
    path = root / name
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((60, 60), content)
        doc.save(path)
    return {"path": name, "sha256": a0.sha(path.read_bytes())}


@pytest.fixture
def example(tmp_path):
    form = {role: pdf(tmp_path, f"operator_{role}.pdf", f"P/E selected issuer {n}.")
            for n, role in enumerate(a0.ROLES)}
    evidence = pdf(tmp_path, "private_path_with_target_candidate_name.pdf", "Annual report of publicly traded peer.")
    spec = {"case_id": "RESEARCH-PRIVATE", "issuer_name": "Issuer", "cutoff_at": "2024-03-25",
            "seed": 77, "forms": form, "evidence": [{**evidence, "source_url": "https://example.invalid/source",
                                                      "available_at": "2024-03-24"}]}
    path = tmp_path / "operator.json"
    a0.dump(path, spec)
    return spec, path, tmp_path / "work"


@pytest.fixture
def calibration(example):
    spec, path, work = example
    forms = spec["forms"]
    forms["canary_1"] = {**forms.pop("canary"), "target_id": "C01", "subtype": "business"}
    forms["canary_2"] = {**pdf(path.parent, "operator_canary_2.pdf", "P/E selected issuer 3."),
                         "target_id": "C02", "subtype": "business"}
    a0.dump(path, spec)
    return spec, path, work


FROZEN_ORDER = {"example": ["control", "canary", "original"],
                "calibration": ["canary_2", "control", "original", "canary_1"]}


class TestProvenance:
    @pytest.mark.parametrize("source,cutoff,allowed", [
        ("2024-03-24", "2024-03-25", True), ("2024-03-25", "2024-03-25", False),
        ("2024-03-25T12:01+09:00", "2024-03-25T12:00+09:00", False),
        ("2024-03-25T12:00+09:00", "2024-03-25T12:00:12+09:00", False),
        ("2024-03-25T11:59+09:00", "2024-03-25T12:00+09:00", True),
        ("2024-03-25T11:59:59+09:00", "2024-03-25T03:00Z", True)])
    def test_cutoff(self, tmp_path, source, cutoff, allowed):
        if allowed:
            a0.confirm_time({"available_at": source}, cutoff, tmp_path)
        else:
            with pytest.raises(ValueError):
                a0.confirm_time({"available_at": source}, cutoff, tmp_path)

    def test_same_day_proof(self, tmp_path):
        path = tmp_path / "external-proof"
        path.write_text("Synthetic evidence of sequence", encoding="utf-8")
        evidence = {"available_at": "2024-03-25", "precedence_evidence": {
            "path": path.name, "sha256": a0.sha(path.read_bytes())}}
        a0.confirm_time(evidence, "2024-03-25", tmp_path)
        with pytest.raises(ValueError, match="after"):
            a0.confirm_time(evidence, "2024-03-24", tmp_path)

    def test_wrong_hash_fails_before_publishing(self, example):
        spec, path, work = example
        spec["forms"]["control"]["sha256"] = "0" * 64
        a0.dump(path, spec)
        with pytest.raises(ValueError, match="Source hash"):
            a0.prepare(path, work)
        assert not work.exists()

    @pytest.mark.parametrize("duplicate,reason", [("path", "distinct PDF paths"), ("bytes", "distinct PDF snapshots"),
                                                 ("text", "identical A0 source text")])
    def test_distinct_calibration_documents(self, calibration, duplicate, reason):
        spec, path, work = calibration
        first, second = (spec["forms"][key] for key in ("canary_1", "canary_2"))
        blob = (path.parent / first["path"]).read_bytes()
        if duplicate == "path":
            second["path"] = first["path"]
        elif duplicate == "text":
            blob += b"\n"
        (path.parent / second["path"]).write_bytes(blob)
        second["sha256"] = a0.sha(blob)
        a0.dump(path, spec)
        with pytest.raises(ValueError, match=reason):
            a0.prepare(path, work)
        assert not work.exists()

    @pytest.mark.parametrize("field,value", [("target_id", "C01"), ("subtype", "valuation"), ("target_id", None)])
    def test_inconsistent_assignments(self, calibration, field, value):
        spec, path, work = calibration
        spec["forms"]["canary_2"][field] = value
        a0.dump(path, spec)
        with pytest.raises(ValueError, match="calibration canaries|distinct target IDs"):
            a0.prepare(path, work)
        assert not work.exists()

    @pytest.mark.parametrize("roles", [("original", "canary_1", "control"),
                                      (*a0.CALIBRATION_ROLES, "canary")])
    def test_incomplete_or_extra_roles(self, roles):
        with pytest.raises(ValueError, match="Expected original"):
            a0.form_roles(dict.fromkeys(roles))


class TestIsolation:
    @pytest.mark.parametrize("fixture", FROZEN_ORDER)
    def test_neutral_metadata_and_reproducible_order(self, fixture, request):
        spec, path, work = request.getfixturevalue(fixture)
        plan = a0.prepare(path, work)
        assert [x["role"] for x in plan["order"]] == FROZEN_ORDER[fixture]
        assert plan["version"] == {"example": "A1-A0-pilot-1", "calibration": "A1-A0-calibration-1"}[fixture]
        hashes = [x["input_hashes"] for x in plan["order"]]
        assert all(h.keys() == hashes[0].keys() for h in hashes)
        varied = {name for name in hashes[0] if len({h[name] for h in hashes}) > 1}
        assert varied == {(a0.PUBLIC / rel).as_posix()
                          for rel in ("raw/DOC-01.pdf", "documents.jsonl", "chunks.jsonl")}
        visible_docs, body_hashes = [], []
        for entry in plan["order"]:
            root = work / entry["workspace"]
            corpus = Corpus(root / a0.PUBLIC, a0.CASE)
            corpus.verify()
            meta = corpus.public_metadata()
            assert meta["case"]["case_id"] == "PILOT-01"
            assert meta["case"]["allowed_doc_ids"] == ["DOC-01", "DOC-02"]
            assert corpus.read_source(["DOC-02-p0001"])["chunks"][0]["source_url"] == "urn:ipo:source:DOC-02"
            visible = json.dumps([meta, corpus.chunks])
            for secret in ("operator_", "private_path", "RESEARCH-PRIVATE", "example.invalid", "canary", "control",
                           "C01", "C02", "business"):
                assert secret not in visible
            body_hashes.append(meta["documents"][0].pop("sha256"))
            assert body_hashes[-1] == spec["forms"][entry["role"]]["sha256"]
            visible_docs.append(meta)
        assert len(set(body_hashes)) == len(spec["forms"]) and all(v == visible_docs[0] for v in visible_docs)
        assert a0.prepare(path, work) == plan
        assert a0.prepare(path, work.parent / "other") == plan

    def test_tampered_workspace_and_order(self, example):
        _, path, work = example
        plan = a0.prepare(path, work)
        raw = work / "plan.json"
        saved = raw.read_bytes()
        a0.dump(raw, {**plan, "order": plan["order"][::-1]})
        with pytest.raises(ValueError, match="order"):
            a0.prepare(path, work)
        raw.write_bytes(saved)
        target = work / plan["order"][0]["workspace"] / a0.PUBLIC / "manual.md"
        target.write_text("changed")
        with pytest.raises(ValueError, match="workspace"):
            a0.prepare(path, work)

    @pytest.mark.parametrize("label", ["[CANARY]", "[CANARY_1]", "[Canary 2]"])
    def test_visible_label_is_rejected(self, example, label):
        spec, path, work = example
        spec["forms"]["canary"] = pdf(path.parent, "labelled.pdf", f"{label} operator-only marker")
        a0.dump(path, spec)
        with pytest.raises(ValueError, match="explicit test labels"):
            a0.prepare(path, work)


class TestExecution:
    @pytest.mark.parametrize("fixture", FROZEN_ORDER)
    def test_real_preflight_fresh_sessions_and_resume(self, fixture, request, monkeypatch):
        _, path, work = request.getfixturevalue(fixture)
        def no_network(*args, **kwargs):
            raise AssertionError("Network attempted during offline review.")
        monkeypatch.setattr(socket.socket, "connect", no_network)
        from ipo_eval import runtime_v2
        # execute_v2's A0 preflight does not need a tokenizer; on a fresh
        # machine the backend would attempt to download the tokenizer asset.
        monkeypatch.setattr(runtime_v2.tiktoken, "get_encoding", lambda _: None)
        result = a0.run_batch(path, work)
        assert [x["role"] for x in result["sessions"]] == FROZEN_ORDER[fixture]
        size = len(FROZEN_ORDER[fixture])
        assert len({x["selected_run"] for x in result["sessions"]}) == size
        assert all(x["attempts"][0]["model_calls"] == 0 for x in result["sessions"])
        assert a0.run_batch(path, work) == result
        summaries = list(work.glob("session-*/runs/*/summary.json"))
        assert len(summaries) == size
        for summary in summaries:
            assert not json.loads(summary.read_bytes())["actual_model_answer"]

    def test_technical_retry_same_snapshot_and_missing_key(self, example):
        _, path, work = example
        calls = []
        def simulate(live, root, case_id, condition, key_provider):
            assert live and condition == "A0" and case_id == a0.CASE
            calls.append((root, a0.snapshot(root)))
            index = len(calls)
            status = ["FAILED", "SUBMITTED", "NOT_STARTED_MISSING_API_KEY"][index-1]
            result = {"run_id": f"mock-{index}", "mode": "LIVE", "execution_status": status, "model_calls": 0,
                      "failure_reason": "NO_VALID_SUBMISSION" if status == "FAILED" else None}
            return root, result
        result = a0.run_batch(path, work, live=True, execute=simulate)
        assert calls[0] == calls[1] and calls[0][0] != calls[2][0]
        assert result["sessions"][0]["selected_run"] == "mock-2"
        assert result["sessions"][1]["selected_run"] is None

    @pytest.mark.parametrize("fixture", FROZEN_ORDER)
    def test_repeated_invalid_submissions_stop_at_two(self, fixture, request):
        _, path, work = request.getfixturevalue(fixture)
        calls = []
        def invalid(**kwargs):
            calls.append(kwargs["root"])
            return kwargs["root"], {"run_id": f"mock-{len(calls)}", "execution_status": "FAILED",
                                   "model_calls": 0, "failure_reason": "INVALID_JSON"}
        ledger = a0.run_batch(path, work, live=True, execute=invalid)
        assert all(len(x["attempts"]) == 2 and x["selected_run"] is None for x in ledger["sessions"])
        assert len(calls) == len(FROZEN_ORDER[fixture]) * 2
