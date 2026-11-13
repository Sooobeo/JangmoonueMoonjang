"""Synthetic provider responses test control flow, never model quality."""
import hashlib
import json

import pytest
import httpx
from openai import OpenAI
from ipo_eval import runner
from ipo_eval.cases import resolve_case
from ipo_eval.corpus import Corpus
from ipo_eval.schemas import VALUE_FIELDS
from ipo_eval.validation import final_status, validate_extraction, validate_review


def evidence(claim):
    return {"doc_id": "TEST-DOC", "chunk_id": "TEST-DOC-p0001", "page": 1, "claim_id": claim, "locator": "synthetic table"}


def extraction():
    def fact(identifier, number):
        unit = "배" if identifier.endswith("per") else "원" if identifier.endswith("price_krw") else "백만원" if "million_krw" in identifier or identifier in ("X_peer_cap", "X_peer_profit") else "주"
        return {"claim_id": identifier, "value": number, "unit": unit, "period": "TEST-YEAR",
                "description": "synthetic test input", "evidence": [evidence(identifier)], "missing_reason": None}
    values = dict(zip(VALUE_FIELDS, ["50", "10", "500", "5000", "100000", "80000", "10000", "10000", "2000"]))
    return {"values": {key: fact("X_" + key, val) for key, val in values.items()},
            "peers": [{"name": "Synthetic Peer", "per": fact("X_peer_per", "10"),
                       "market_cap_million_krw": fact("X_peer_cap", "200"), "earnings_million_krw": fact("X_peer_profit", "20")}],
            "document_version_notes": ["synthetic"], "extraction_limits": ["fixture only"]}


def review():
    return {"scope": {"document_ids": ["TEST-DOC"], "verification_limits": ["SYNTHETIC TEST ONLY"]},
            "judgments": [{"judgment_id": j, "domain": j, "conclusion": "synthetic conclusion", "disposition": "CONDITIONAL",
                           "facts": [{"claim_id": "R_" + j, "text": "synthetic fact", "evidence": [evidence("R_" + j)]}],
                           "evidence": [evidence("R_" + j)], "counter_evidence": [], "unknowns": [], "next_action": "synthetic next action"}
                          for j in ["J1", "J2", "J3", "J4"]],
            "requests": [], "escalations": [], "missing_inputs": [], "memo": ["SYNTHETIC TEST ONLY"], "model_reported_status": "READY"}


def request(identifier="REQ1", blocking=True, resolved=False):
    return {"request_id": identifier, "question": "Which evidence?", "why_needed": "synthetic", "related_judgment_ids": ["J1"],
            "blocking": blocking, "resolution_status": "RESOLVED" if resolved else "OPEN", "resolution_evidence": []}


@pytest.fixture
def fixture_root(tmp_path):
    for folder in ["config", "prompts", "data/public/raw", "ipo_eval"]:
        (tmp_path / folder).mkdir(parents=True)
    config = json.loads((runner.ROOT / "config/B_v1.json").read_text(encoding="utf-8"))
    (tmp_path / "config/B.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "config/cases.json").write_bytes((runner.ROOT / "config/cases.json").read_bytes())
    (tmp_path / "prompts/common.md").write_text("Synthetic test system message", encoding="utf-8")
    raw = b"synthetic source bytes, not a real PDF"
    (tmp_path / "data/public/raw/TEST-DOC.pdf").write_bytes(raw)
    corpus = tmp_path / "data/public"
    def one(name, value):
        (corpus / name).write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    one("case_manifest.jsonl", {"case_id": "HDMS-DEV-01", "issuer_name": "TEST-ISSUER", "cutoff_at": "2000-12-31T23:59:59+09:00", "allowed_doc_ids": ["TEST-DOC"]})
    one("documents.jsonl", {"doc_id": "TEST-DOC", "sha256": hashlib.sha256(raw).hexdigest(), "pages": 1, "cutoff_status": "BEFORE"})
    one("chunks.jsonl", {"case_id": "HDMS-DEV-01", "doc_id": "TEST-DOC", "chunk_id": "TEST-DOC-p0001", "page": 1,
                         "printed_page": 1, "text": " ".join(q["query"] for q in config["fixed_queries"]), "cutoff_status": "BEFORE"})
    (corpus / "manual.md").write_text("Synthetic manual", encoding="utf-8")
    # Prove recursive reads never expose this sentinel.
    (tmp_path / "PRIVATE_GOLD_SENTINEL.txt").write_text("DO_NOT_SEND_GOLD_18a7", encoding="utf-8")
    return tmp_path


class FakeResponse:
    def __init__(self, value, status="completed"):
        self.output_text = json.dumps(value)
        self.status = status

    def model_dump(self, mode):
        return {"id": "SYNTHETIC_RESPONSE", "model": "SYNTHETIC_MODEL", "status": self.status,
                "output": self.output_text, "usage": {"input_tokens": 100, "output_tokens": 100}}


class FakeClient:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(next(self.outputs))


def test_complete_fixed_workflow_and_input_isolation(fixture_root, monkeypatch):
    client = FakeClient([extraction(), review()])
    monkeypatch.setattr(runner, "api_key", lambda: "SYNTHETIC_KEY_DO_NOT_LOG")
    monkeypatch.setattr(runner, "OpenAI", lambda **kwargs: client)
    directory, summary = runner.execute(live=True, root=fixture_root)
    assert summary["execution_status"] == "SUBMITTED"
    assert summary["model_calls"] == 2
    assert summary["tool_calls"] == 15
    assert summary["final_status"] == "READY"
    assert (directory / "review.md").exists()
    report = json.loads((directory / "review.json").read_text(encoding="utf-8"))
    assert isinstance(report["calculations"], list)
    assert all(row["inputs"] and row["evidence"] for row in report["calculations"])
    assert all("unit" in source and "period" in source for row in report["calculations"] for source in row["inputs"])
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    tools = [e["tool"] for e in events if e["event"] == "tool_call"]
    assert tools == ["search_corpus", "read_source"] * 5 + ["calculate", "sensitivity", "request_information", "escalate", "submit_review"]
    saved = "".join(p.read_text(encoding="utf-8") for p in directory.iterdir() if p.is_file())
    assert "DO_NOT_SEND_GOLD_18a7" not in saved
    assert "SYNTHETIC_KEY_DO_NOT_LOG" not in saved
    assert all(c["model"] == "gpt-6.1-terra" and not c["store"] for c in client.calls)
    assert all("previous_response_id" not in c and "tools" not in c for c in client.calls)
    review_input = json.loads(client.calls[1]["input"][1]["content"])
    assert review_input["extraction"] == extraction()
    assert "source_inputs" not in review_input["calculations"]
    saved_calculations = json.loads((directory / "calculations.json").read_text(encoding="utf-8"))
    assert saved_calculations["source_inputs"]
    assert all(review_input["calculations"][k] == v for k, v in saved_calculations.items() if k != "source_inputs")


def test_missing_key_never_fabricates_answer(fixture_root, monkeypatch):
    monkeypatch.setattr(runner, "api_key", lambda: None)
    directory, summary = runner.execute(live=True, root=fixture_root)
    assert summary["execution_status"] == "NOT_STARTED_MISSING_API_KEY"
    assert summary["final_status"] is None
    assert summary["model_calls"] == 0
    assert not (directory / "review.json").exists()


def test_free_preflight_never_calls_api(fixture_root, monkeypatch):
    monkeypatch.setattr(runner, "api_key", lambda: "SYNTHETIC")
    monkeypatch.setattr(runner, "OpenAI", lambda **kwargs: pytest.fail("No network permitted in preflight"))
    _, summary = runner.execute(live=False, root=fixture_root)
    assert summary["execution_status"] == "PREFLIGHT_COMPLETE"
    assert not summary["actual_model_answer"]


def test_env_file_key_is_loaded_without_variable_expansion(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(runner, "ROOT", tmp_path / "app")
    (tmp_path / "app").mkdir()
    (tmp_path / ".env").write_text('OPENAI_API_KEY="SYNTHETIC_${DO_NOT_EXPAND}"\n', encoding="utf-8-sig")
    assert runner.api_key() == "SYNTHETIC_${DO_NOT_EXPAND}"


def test_structural_checks_leave_numerically_wrong_answer_for_later_grading(fixture_root):
    corpus = Corpus(fixture_root / "data/public", "HDMS-DEV-01")
    x = extraction()
    x["values"]["share_count"]["value"] = "999999999"
    assert validate_extraction(x, corpus.by_id) == []
    assert validate_review(review(), x, corpus.by_id, ["TEST-DOC"]) == []


def test_reject_bad_source_ids_and_missing_reason(fixture_root):
    corpus = Corpus(fixture_root / "data/public", "HDMS-DEV-01")
    x = extraction()
    x["values"]["share_count"]["evidence"][0]["page"] = 999
    assert validate_extraction(x, corpus.by_id)
    x = extraction()
    x["values"]["share_count"]["value"] = None
    assert validate_extraction(x, corpus.by_id)


def test_resolved_requests_require_evidence_and_correct_status_precedence(fixture_root):
    r = review()
    r["requests"] = [request()]
    assert final_status(r) == "PENDING_INFO"
    e = request("ESC1")
    e["escalation_id"] = e.pop("request_id")
    e["review_focus"] = "synthetic"
    r["escalations"] = [e]
    assert final_status(r) == "HUMAN_REVIEW"
    assert final_status(r, valid=False) == "FAILED"
    r = review()
    r["requests"] = [request(resolved=True)]
    corpus = Corpus(fixture_root / "data/public", "HDMS-DEV-01")
    assert validate_review(r, extraction(), corpus.by_id, ["TEST-DOC"])


def test_missing_input_requires_request_link(fixture_root):
    x = extraction()
    x["values"]["share_count"].update(value=None, missing_reason="No share table")
    corpus = Corpus(fixture_root / "data/public", "HDMS-DEV-01")
    r = review()
    assert validate_review(r, x, corpus.by_id, ["TEST-DOC"])
    r["requests"] = [request()]
    r["missing_inputs"] = [{"field": "share_count", "missing_reason": "No share table", "request_id": "REQ1"}]
    assert validate_review(r, x, corpus.by_id, ["TEST-DOC"]) == []


@pytest.mark.parametrize("value,unit", [("", "백만원"), ("NaN", "백만원"), ("50", "USD"), ("1e3", "백만원")])
def test_invalid_numeric_form_and_units_are_common_format_errors(fixture_root, value, unit):
    corpus = Corpus(fixture_root / "data/public", "HDMS-DEV-01")
    x = extraction()
    x["values"]["earnings_million_krw"].update(value=value, unit=unit)
    assert validate_extraction(x, corpus.by_id)


@pytest.mark.parametrize("disposition", ["REQUEST_INFO", "ESCALATE"])
def test_disposition_requires_actual_request(fixture_root, disposition):
    corpus = Corpus(fixture_root / "data/public", "HDMS-DEV-01")
    r = review()
    r["judgments"][0]["disposition"] = disposition
    assert validate_review(r, extraction(), corpus.by_id, ["TEST-DOC"])


def test_report_retains_counter_evidence():
    r = review()
    r["judgments"][0]["counter_evidence"] = [evidence("R_J1")]
    r.update(run_id="SYNTHETIC", cutoff_at="2000", final_status="READY", calculations={})
    assert "반대 근거로 검토한 원문" in runner.render_report(r)


def test_one_format_repair_no_extra_search(fixture_root, monkeypatch):
    bad = review()
    bad["judgments"] = bad["judgments"][:3]
    client = FakeClient([extraction(), bad, review()])
    monkeypatch.setattr(runner, "api_key", lambda: "SYNTHETIC")
    monkeypatch.setattr(runner, "OpenAI", lambda **kwargs: client)
    _, summary = runner.execute(live=True, root=fixture_root)
    assert summary["execution_status"] == "SUBMITTED"
    assert summary["format_repairs"] == 1
    assert summary["tool_calls"] == 15


def test_second_bad_format_retains_failed_run(fixture_root, monkeypatch):
    client = FakeClient([extraction(), {}, {}])
    monkeypatch.setattr(runner, "api_key", lambda: "SYNTHETIC")
    monkeypatch.setattr(runner, "OpenAI", lambda **kwargs: client)
    directory, summary = runner.execute(live=True, root=fixture_root)
    assert summary["execution_status"] == "FAILED"
    assert summary["format_repairs"] == 1
    assert (directory / "03_review_format_repair_response.json").exists()
    assert not (directory / "review.json").exists()


def test_id_repair_changes_only_evidence_reference_and_preserves_raw_response(fixture_root, monkeypatch):
    bad = review()
    bad["judgments"][0]["facts"][0]["evidence"][0]["claim_id"] = "UNDECLARED"
    patch = {"repairs": [{"path": "/judgments/0/facts/0/evidence/0/claim_id", "replacement": "R_J1"}]}
    client = FakeClient([extraction(), bad, patch])
    monkeypatch.setattr(runner, "api_key", lambda: "SYNTHETIC")
    monkeypatch.setattr(runner, "OpenAI", lambda **kwargs: client)
    directory, summary = runner.execute(live=True, root=fixture_root)
    assert summary["execution_status"] == "SUBMITTED"
    assert summary["format_repairs"] == 1
    assert summary["model_calls"] == 3
    result = json.loads((directory / "review.json").read_text(encoding="utf-8"))
    assert result["judgments"][0]["facts"][0]["evidence"][0]["claim_id"] == "R_J1"
    assert result["judgments"][0]["facts"][0]["text"] == bad["judgments"][0]["facts"][0]["text"]
    assert "UNDECLARED" in (directory / "02_review_response.json").read_text(encoding="utf-8")
    assert client.calls[-1]["max_output_tokens"] == 2500


def test_memo_count_repair_preserves_full_judgments_and_requests(fixture_root, monkeypatch):
    bad = review()
    bad["memo"] = ["Synthetic item " + str(i) for i in range(7)]
    client = FakeClient([extraction(), bad, {"memo": ["Synthetic combined memo"]}])
    monkeypatch.setattr(runner, "api_key", lambda: "SYNTHETIC")
    monkeypatch.setattr(runner, "OpenAI", lambda **kwargs: client)
    directory, summary = runner.execute(live=True, root=fixture_root)
    assert summary["execution_status"] == "SUBMITTED"
    assert summary["format_repairs"] == 1
    result = json.loads((directory / "review.json").read_text(encoding="utf-8"))
    assert result["judgments"] == bad["judgments"]
    assert result["requests"] == bad["requests"]
    assert result["memo"] == ["Synthetic combined memo"]
    assert client.calls[1]["text"]["format"]["schema"]["properties"]["memo"]["maxItems"] == 5


@pytest.mark.parametrize("limit", ["max_model_calls", "input_tokens_target_max", "output_tokens_max", "max_run_usd", "wall_seconds_max"])
def test_budget_stops_before_call(fixture_root, limit):
    config = json.loads((fixture_root / "config/B.json").read_text(encoding="utf-8"))
    config[limit] = 0
    client = FakeClient([extraction()])
    run = runner.Run(config, True, directory=fixture_root / "budget_run", client=client)
    with pytest.raises(runner.BudgetError):
        run.call("test", "synthetic", {}, {}, 10)
    assert client.calls == []


def test_source_hash_and_unavailable_pages_are_enforced(fixture_root):
    corpus = Corpus(fixture_root / "data/public", "HDMS-DEV-01")
    corpus.verify()
    with pytest.raises(ValueError):
        corpus.read_source(["PRIVATE-DOC"])
    with pytest.raises(ValueError):
        corpus.search_corpus("OTHER-CASE", "query")
    (fixture_root / "data/public/raw/TEST-DOC.pdf").write_bytes(b"modified")
    with pytest.raises(ValueError):
        corpus.verify()


def test_real_sdk_serializes_responses_request_without_network(fixture_root):
    config = json.loads((fixture_root / "config/B.json").read_text(encoding="utf-8"))
    seen = []
    def handle(request):
        body = json.loads(request.content)
        seen.append(body)
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert body["model"] == "gpt-6.1-terra"
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["store"] is False
        return httpx.Response(200, json={"id": "resp_SYNTHETIC", "object": "response", "created_at": 1,
            "status": "completed", "model": "gpt-6.1-terra", "error": None, "incomplete_details": None,
            "output": [{"id": "msg_SYNTHETIC", "type": "message", "status": "completed", "role": "assistant",
                        "content": [{"type": "output_text", "text": json.dumps({"synthetic": True}), "annotations": []}]}],
            "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}})
    with OpenAI(api_key="SYNTHETIC_NOT_A_KEY", base_url="https://api.openai.com/v1", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
        run = runner.Run(config, True, directory=fixture_root / "sdk_test", client=client)
        value, _ = run.call("synthetic", "test only", {}, {"type": "object", "properties": {}, "required": [], "additionalProperties": False}, 100)
    assert value == {"synthetic": True}
    assert len(seen) == 1
    assert run.input_tokens == 100 and run.output_tokens == 10


def synthetic_registered_case(root, case_id, doc_id, marker):
    """Make isolated fake public material; no real company's answers are used."""
    directory = root / "data" / "cases" / case_id / "public"
    (directory / "raw").mkdir(parents=True)
    source = root / "data/public"
    for filename in ("case_manifest.jsonl", "documents.jsonl", "chunks.jsonl"):
        text = (source / filename).read_text(encoding="utf-8")
        text = text.replace("HDMS-DEV-01", case_id).replace("TEST-DOC", doc_id).replace("TEST-ISSUER", marker)
        if filename == "chunks.jsonl":
            row = json.loads(text)
            row["text"] += " " + marker
            text = json.dumps(row)
        (directory / filename).write_text(text, encoding="utf-8")
    (directory / "raw" / (doc_id + ".pdf")).write_bytes((source / "raw/TEST-DOC.pdf").read_bytes())
    methods = root / "data/methods"
    methods.mkdir(exist_ok=True)
    (methods / "IPO_PER_B_v0.2.md").write_text("COMMON SYNTHETIC METHOD", encoding="utf-8")
    (directory / "manual.md").write_bytes((methods / "IPO_PER_B_v0.2.md").read_bytes())
    return directory


@pytest.mark.parametrize("case_id,doc_id,marker", [
    ("MELCON-DEV-01", "SYNTHETIC-A", "SELECTED_CASE_A"),
    ("DTS-DEV-01", "SYNTHETIC-B", "SELECTED_CASE_B"),
])
def test_registered_case_runs_are_isolated_and_keep_existing_files(fixture_root, monkeypatch, case_id, doc_id, marker):
    directories = {}
    for identity, document, text in [("MELCON-DEV-01", "SYNTHETIC-A", "SELECTED_CASE_A"),
                                      ("DTS-DEV-01", "SYNTHETIC-B", "SELECTED_CASE_B")]:
        directories[identity] = synthetic_registered_case(fixture_root, identity, document, text)
    private = fixture_root / "data/private"
    private.mkdir()
    (private / "grade.json").write_text("PRIVATE_RUBRIC_SENTINEL_4fc9", encoding="utf-8")
    previous = fixture_root / "runs/EXISTING_SYNTHETIC_RUN"
    previous.mkdir(parents=True)
    (previous / "review.json").write_text("PRIOR_ANSWER_SENTINEL_e3a8", encoding="utf-8")
    preserved = {p: p.read_bytes() for folder in (fixture_root / "data/public", previous)
                 for p in folder.rglob("*") if p.is_file()}
    rewritten = lambda value: json.loads(json.dumps(value).replace("TEST-DOC", doc_id))
    client = FakeClient([rewritten(extraction()), rewritten(review())])
    monkeypatch.setattr(runner, "api_key", lambda: "SYNTHETIC_KEY")
    monkeypatch.setattr(runner, "OpenAI", lambda **kwargs: client)
    directory, summary = runner.execute(live=True, root=fixture_root, case_id=case_id)
    assert summary["execution_status"] == "SUBMITTED"
    assert summary["case_id"] == case_id
    assert summary["model_calls"] == 2 and summary["tool_calls"] == 15
    sent = json.dumps(client.calls)
    assert marker in sent and doc_id in sent
    other_marker = "SELECTED_CASE_B" if marker == "SELECTED_CASE_A" else "SELECTED_CASE_A"
    assert other_marker not in sent
    assert all(secret not in sent for secret in ("PRIVATE_RUBRIC_SENTINEL_4fc9", "PRIOR_ANSWER_SENTINEL_e3a8", "DO_NOT_SEND_GOLD_18a7", "TEST-ISSUER"))
    saved = "".join(p.read_text(encoding="utf-8") for p in directory.iterdir() if p.is_file())
    assert "PRIVATE_RUBRIC_SENTINEL_4fc9" not in saved and "PRIOR_ANSWER_SENTINEL_e3a8" not in saved
    assert (directory / "review.md").read_text(encoding="utf-8").startswith(f"# {marker} B 검토 결과")
    hashes = json.loads((directory / "input_hashes.json").read_text(encoding="utf-8"))
    prefix = f"data/cases/{case_id}/public/"
    assert hashes[prefix + "raw/" + doc_id + ".pdf"] == hashlib.sha256((directories[case_id] / "raw" / (doc_id + ".pdf")).read_bytes()).hexdigest()
    assert "config/cases.json" in {p.replace("\\", "/") for p in hashes}
    assert "data/methods/IPO_PER_B_v0.2.md" in hashes
    assert not any(p.startswith("data/public/") for p in hashes)
    assert all(path.read_bytes() == contents for path, contents in preserved.items())


def test_cross_case_material_in_jsonl_is_never_searchable(fixture_root):
    first = synthetic_registered_case(fixture_root, "MELCON-DEV-01", "SYNTHETIC-A", "SELECTED_CASE_A")
    second = synthetic_registered_case(fixture_root, "DTS-DEV-01", "SYNTHETIC-B", "OTHER_CASE_SENTINEL")
    # An accidental concatenation of input lists must not broaden the selected case.
    for filename in ("case_manifest.jsonl", "documents.jsonl", "chunks.jsonl"):
        with (first / filename).open("a", encoding="utf-8") as stream:
            stream.write("\n" + (second / filename).read_text(encoding="utf-8"))
    corpus = Corpus(first, "MELCON-DEV-01")
    corpus.verify()
    assert corpus.search_corpus("MELCON-DEV-01", "OTHER_CASE_SENTINEL")["hits"] == []
    with pytest.raises(ValueError, match="Case is not allowed"):
        corpus.search_corpus("DTS-DEV-01", "query")
    with pytest.raises(ValueError, match="Unknown or disallowed"):
        corpus.read_source(["SYNTHETIC-B-p0001"], neighbor_pages=100)


@pytest.mark.parametrize("case_id", ["UNKNOWN-DEV-01", "../private", "data/public", "C:/secret", ""])
def test_unregistered_or_invalid_case_stops_without_api(fixture_root, monkeypatch, case_id):
    monkeypatch.setattr(runner, "api_key", lambda: pytest.fail("Invalid selection must stop before key lookup"))
    monkeypatch.setattr(runner, "OpenAI", lambda **kwargs: pytest.fail("No API permitted"))
    directory, summary = runner.execute(live=True, root=fixture_root, case_id=case_id)
    assert summary["execution_status"] == "FAILED"
    assert summary["model_calls"] == 0 and summary["tool_calls"] == 0
    assert not (directory / "source_packet.json").exists()


@pytest.mark.parametrize("redirect", ["data/private", "../private", "data/cases/DTS-DEV-01/public", "C:/secret"])
def test_registry_cannot_redirect_public_inputs(fixture_root, redirect):
    path = fixture_root / "config/cases.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["cases"][1]["public_directory"] = redirect
    path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(ValueError, match="dedicated public directory"):
        resolve_case(fixture_root, "MELCON-DEV-01")


def test_registered_method_version_must_match(fixture_root):
    directory = synthetic_registered_case(fixture_root, "MELCON-DEV-01", "SYNTHETIC-A", "SELECTED_CASE_A")
    resolve_case(fixture_root, "MELCON-DEV-01")
    (directory / "manual.md").write_text("unversioned change", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from its registered method"):
        resolve_case(fixture_root, "MELCON-DEV-01")


@pytest.mark.parametrize("damage", ["missing_page", "duplicate_page", "duplicate_chunk_id", "tampered_pdf"])
def test_new_case_rejects_damaged_source_before_key_lookup(fixture_root, monkeypatch, damage):
    directory = synthetic_registered_case(fixture_root, "MELCON-DEV-01", "SYNTHETIC-A", "SELECTED_CASE_A")
    chunks = directory / "chunks.jsonl"
    row = json.loads(chunks.read_text(encoding="utf-8"))
    if damage == "missing_page":
        chunks.write_text("", encoding="utf-8")
    elif damage in ("duplicate_page", "duplicate_chunk_id"):
        duplicate = dict(row)
        if damage == "duplicate_page":
            duplicate["chunk_id"] += "-duplicate"
        chunks.write_text(json.dumps(row) + "\n" + json.dumps(duplicate), encoding="utf-8")
    else:
        (directory / "raw/SYNTHETIC-A.pdf").write_bytes(b"tampered")
    monkeypatch.setattr(runner, "api_key", lambda: pytest.fail("Invalid sources must stop before key lookup"))
    _, summary = runner.execute(live=True, root=fixture_root, case_id="MELCON-DEV-01")
    assert summary["execution_status"] == "FAILED"
    assert summary["model_calls"] == 0 and summary["tool_calls"] == 0
