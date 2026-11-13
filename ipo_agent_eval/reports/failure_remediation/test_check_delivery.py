"""Acceptance-checker boundaries using synthetic artifacts only, never API."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("delivery_under_test", HERE / "check_delivery.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def batch(tmp_path, monkeypatch):
    root = tmp_path / "project"
    here = root / "reports/failure_remediation"
    here.mkdir(parents=True)
    (here / "preserve_baseline.py").write_text("def verify():\n    return {'passed': True, 'violations': []}\n", encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", root)
    monkeypatch.setattr(checker, "HERE", here)
    hashes = {}
    for condition in ("B", "A0"):
        cfg = {"condition": condition, "version": "synthetic", "max_model_calls": 24, "max_tool_calls": 40,
               "input_tokens_target_max": 800000, "output_tokens_max": 24000, "max_run_usd": 1.25, "wall_seconds_max": 900,
               "price_input_per_million_usd": 1.0, "price_output_per_million_usd": 5.0}
        relative = "config/" + condition + ".json"
        write(root / relative, cfg)
        write(here / "frozen" / relative, cfg)
        hashes[relative] = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    for filename in ("intermediate_attempts_manifest.json", "compatibility_probe_preservation.json", "FIX_v042_interrupted_preservation.json"):
        write(here / filename, {"entries": [{"path": path, "sha256": digest} for path, digest in hashes.items()]})
    rows, planned = [], []
    for company in range(6):
        for condition in ("B", "A0"):
            case_id = "SYN-" + str(company)
            run_id = case_id + "_" + condition
            directory = root / "runs" / run_id
            actor = "model" if condition == "A0" else "program_fixed"
            evidence = {"doc_id": "SYN_DOC", "chunk_id": "SYN-p1", "page": 1, "claim_id": "F1", "locator": "synthetic"}
            chunk = {"doc_id": "SYN_DOC", "chunk_id": "SYN-p1", "page": 1, "case_id": case_id,
                     "cutoff_status": "BEFORE", "text": "synthetic complete page"}
            calc1 = {"calc_id": "C1", "id": "price", "input_snapshot_id": "X_SYN", "status": "OK", "result": "1", "evidence": [evidence]}
            calc2 = {"calc_id": "C2", "id": "sensitivity_mean", "input_snapshot_id": "X_SYN", "status": "OK", "result": "2", "evidence": [evidence]}
            events = [{"event": "model_call_started"}]
            for index, (tool, args, result) in enumerate([
                ("read_source", {"chunk_ids": ["SYN-p1"], "neighbor_pages": 0}, {"chunks": [chunk]}),
                ("calculate", {"request": {"operation": "REGISTER_BATCH", "base_snapshot_id": "X_EMPTY"}}, {"input_snapshot_id": "X_SYN"}),
                ("calculate", {"request": {"operation": "EVALUATE", "input_snapshot_id": "X_SYN"}}, {"input_snapshot_id": "X_SYN", "calculations": [calc1]}),
                ("sensitivity", {"input_snapshot_id": "X_SYN"}, {"input_snapshot_id": "X_SYN", "calculations": [calc2]}),
                ("request_information", {"requests": []}, {"active_records": []}),
                ("escalate", {"escalations": []}, {"active_records": []}),
                ("submit_review", {"phase": "COMMIT", "input_snapshot_id": "X_SYN"},
                 {"submission_id": "SUB_SYN", "execution_status": "SUBMITTED", "input_snapshot_id": "X_SYN",
                  "content_status": "READY", "requests": [], "escalations": []}),
            ]):
                events.append({"event": "tool_call", "actor": "program_commit" if tool in {"request_information", "escalate"} else actor,
                               "phase": "FINALIZING" if index >= 4 else "EXPLORING", "tool": tool, "arguments": args,
                               "result": result, "call_id": "call_" + str(index), "tool_calls": index + 1})
            events.append({"event": "state_transition", "to": "SUBMITTED"})
            summary = {"run_id": run_id, "case_id": case_id, "condition": condition, "repeat": 1,
                       "config_version": "synthetic", "execution_status": "SUBMITTED", "mode": "LIVE",
                       "model_calls": 1, "tool_calls": 7, "input_tokens": 100, "output_tokens": 10, "final_status": "READY",
                       "usage_unknown": False, "estimated_cost_usd_standard_uncached": 0.00015,
                       "known_usage_cost_usd_standard_uncached": 0.00015, "cost_ceiling_usd": 0.000175,
                       "accounted_cost_ceiling_usd": 0.000175, "elapsed_seconds": 1,
                       "unknown_usage_reservation": {"attempts": [], "input_tokens_estimated": 0, "output_tokens_max": 0, "cost_ceiling_usd": 0}}
            write(directory / "summary.json", summary)
            write(directory / "input_hashes.json", hashes)
            write(directory / "snapshots.json", {"current_id": "X_SYN", "snapshots": {"X_SYN": {"records": {"F1": {"payload": {"evidence": [evidence]}}}}}})
            write(directory / "calculations.json", [calc1, calc2])
            write(directory / "review.json", {"input_snapshot_id": "X_SYN", "calculation_uses": [
                {"calc_id": "C1", "use": "USE", "stated_value": "1"}, {"calc_id": "C2", "use": "USE", "stated_value": "2"}],
                "requests": [], "escalations": [], "evidence": [evidence]})
            write(directory / "source_packet.json", {"metadata": {"case": {"case_id": case_id, "allowed_doc_ids": ["SYN_DOC"]}}, "sources": [chunk]})
            write(directory / "case_selection.json", {"registration": {"case_id": case_id}})
            write(directory / "retrieval_history.json", {"read_chunks": ["SYN-p1"]})
            write(directory / "request_ledger.json", {"requests": [], "escalations": []})
            write(directory / "01_finalize_request.json", {"max_output_tokens": 100})
            write(directory / "01_finalize_response.json", {"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 10}})
            (directory / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            identity = {"case_id": case_id, "condition": condition, "repeat": 1}
            planned.append(identity)
            rows.append({**identity, "directory": str(directory), "summary": summary})
    write(here / "SYN_plan.json", {"version": "synthetic", "planned_runs": planned, "source_snapshot": "reports/failure_remediation/frozen", "source_hashes": hashes})
    write(here / "SYN_runs.json", {"complete": True, "runs": rows})
    return root, here, rows


def audit():
    return checker.check("SYN", require_reviews=False)


def mutate_run(batch, filename, callback):
    path = Path(batch[2][0]["directory"]) / filename
    value = read(path)
    callback(value)
    write(path, value)


def mutate_events(batch, callback):
    path = Path(batch[2][0]["directory"]) / "events.jsonl"
    value = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    callback(value)
    path.write_text("\n".join(json.dumps(e) for e in value) + "\n", encoding="utf-8")


def test_complete_synthetic_artifacts_pass_and_checker_writes_nothing(batch):
    before = {p: p.read_bytes() for p in batch[0].rglob("*") if p.is_file()}
    result = audit()
    assert result["passed"], result["failures"]
    assert len(result["runs"]) == 12
    assert all(p.read_bytes() == content for p, content in before.items())
    assert set(before) == {p for p in batch[0].rglob("*") if p.is_file()}


@pytest.mark.parametrize("mutation,fragment", [
    ("directory", "directory missing"), ("duplicate", "directory reused"),
    ("identity", "identity differ"), ("incomplete", "incomplete"), ("missing_review", "required artifact"),
    ("stale_sensitivity", "successful sensitivity"), ("unavailable_sensitivity", "successful sensitivity"),
    ("wrong_actor", "required actor"), ("unread_citation", "not actually read"),
    ("read_identity", "packet case identity"), ("usage", "known raw usage"), ("forgotten_open", "OPEN ledger"),
    ("unaccepted_commit", "accepted final COMMIT"), ("sync_phase", "ledger synchronization"),
])
def test_incomplete_or_misattributed_delivery_is_rejected(batch, mutation, fragment):
    root, here, rows = batch
    results = read(here / "SYN_runs.json")
    if mutation == "directory":
        results["runs"][0]["directory"] = None
    elif mutation == "duplicate":
        results["runs"][2]["directory"] = results["runs"][0]["directory"]
    elif mutation == "identity":
        results["runs"][0]["case_id"] = "WRONG"
    elif mutation == "incomplete":
        results["complete"] = False
        results["runs"].pop()
    elif mutation == "missing_review":
        (Path(rows[0]["directory"]) / "review.json").unlink()
    elif mutation == "stale_sensitivity":
        mutate_events(batch, lambda events: events[4]["arguments"].update(input_snapshot_id="X_OLD"))
    elif mutation == "unavailable_sensitivity":
        mutate_events(batch, lambda events: events[4]["result"]["calculations"][0].update(status="UNAVAILABLE", result=None))
    elif mutation == "wrong_actor":
        mutate_events(batch, lambda events: events[2].update(actor="program_commit"))
    elif mutation == "unread_citation":
        mutate_run(batch, "review.json", lambda value: value["evidence"][0].update(chunk_id="UNREAD"))
    elif mutation == "read_identity":
        mutate_run(batch, "source_packet.json", lambda value: value["metadata"]["case"].update(case_id="OTHER"))
    elif mutation == "usage":
        mutate_run(batch, "01_finalize_response.json", lambda value: value["usage"].update(input_tokens=101))
    elif mutation == "forgotten_open":
        mutate_run(batch, "request_ledger.json", lambda value: value["requests"].append({"request_id": "R1", "resolution_status": "OPEN"}))
    elif mutation == "unaccepted_commit":
        mutate_events(batch, lambda events: events[7]["result"].update(execution_status="FAILED"))
    elif mutation == "sync_phase":
        mutate_events(batch, lambda events: events[5].update(phase="EXPLORING"))
    write(here / "SYN_runs.json", results)
    result = audit()
    assert not result["passed"]
    assert any(fragment in failure for failure in result["failures"]), result["failures"]


def test_empty_review_stages_do_not_prove_twelve_reviews(batch):
    write(batch[1] / "review_manifest.json", {"acceptance_complete": True, "stages": {}, "open_required_findings": []})
    result = checker.check("SYN", require_reviews=True)
    assert not result["passed"] and "Four exact review stages required" in result["failures"]


def test_review_completion_flags_without_report_artifacts_are_rejected(batch):
    stages = {stage: {"reviews": [{"ordinal": i, "review_complete": True, "artifacts": []} for i in (1, 2, 3)]}
              for stage in ("diagnosis", "implementation", "execution", "overall")}
    write(batch[1] / "review_manifest.json", {"acceptance_complete": True, "stages": stages, "open_required_findings": []})
    result = checker.check("SYN", require_reviews=True)
    assert not result["passed"]
    assert sum("hashed reports" in failure for failure in result["failures"]) == 4


def test_unknown_usage_cannot_be_zeroed_after_an_error_artifact(batch):
    root, here, rows = batch
    directory = Path(rows[0]["directory"])
    (directory / "01_finalize_response.json").unlink()
    write(directory / "01_finalize_error.json", {"http_status": 500, "usage_unknown": True})
    result = audit()
    assert not result["passed"]
    assert any("unknown-usage flag" in failure for failure in result["failures"])


def test_common_model_cap_is_not_waived_by_completed_status(batch):
    root, here, rows = batch
    config_path = here / "frozen/config/B.json"
    config = read(config_path)
    config["max_model_calls"] = 0
    write(config_path, config)
    result = audit()
    assert not result["passed"]
    assert any("usage exceeds a common cap" in failure for failure in result["failures"])


@pytest.mark.parametrize("filename", ["intermediate_attempts_manifest.json", "compatibility_probe_preservation.json", "FIX_v042_interrupted_preservation.json"])
def test_diagnostic_and_stopped_attempt_manifest_cannot_disappear(batch, filename):
    (batch[1] / filename).unlink()
    result = audit()
    assert not result["passed"]
    assert any("stopped-attempt manifest missing" in failure for failure in result["failures"])
