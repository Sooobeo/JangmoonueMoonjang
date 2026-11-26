"""Archive-shaped test fixtures only. No IPO or model request is evaluated here."""
import hashlib
import json
import shutil
from copy import deepcopy

import pytest

from ipo_eval.a1_ranking import rank
from ipo_eval.a1_ranking_contract import example
from ipo_eval.blind_reviewer import mock_answer, wire_dumps
from scripts.evaluate_a1 import evaluate


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def saved_answer(run, judgments):
    review = {"judgments": judgments, "requests": [], "escalations": []}
    args = {"phase": "COMMIT", "input_snapshot_id": "fixture-snapshot", "review": review}
    dump(run / "review.json", {**review, "condition": "A0", "case_id": "PILOT-01", "run_id": run.name})
    dump(run / "01_agent_response.json", {"id": "response", "status": "completed", "output": [{
        "type": "function_call", "name": "submit_review", "call_id": "commit1", "arguments": json.dumps(args)}]})
    dump(run / "events.jsonl", {"event": "tool_call", "tool": "submit_review", "actor": "model",
         "call_id": "commit1", "arguments": args,
         "result": {"execution_status": "SUBMITTED", "requests": [], "escalations": []}})


def fixture(base, a_valid=True, b_valid=True):
    case = example()
    del case["b2"]
    case["trials"] = []
    for item in case["items"]:
        item["b1"] = None
    case["a0_original"].update(id="original-A0", valid=a_valid)
    case["b1"].update(id="blind-B1", valid=b_valid)
    inp = dump(base / "input", case)
    ranking = {**rank(case), "input_sha256": inp}
    dump(base / "rank", ranking)
    slug = case["case_id"]
    dump(base / "rubric", {"population": "unmodified_original", "case_id": slug,
                           "assignment_ref": case["assignment_ref"], "items": [
                               {"id": i["id"], "grade": "acceptable", "source_ref": "p1", "reason": "fixture"}
                               for i in case["items"]]})
    files = {"ranking_input": "input", "a0_batch": "a0", "b1_dir": "b1"}
    issuer = {"case_id": slug, "ranking": "rank", "rubric": "rubric", "observed_runs": files}
    manifest = {"population": "unmodified_original", "data_kind": "observed", "issuers": [issuer]}
    dump(base / "roster", manifest)

    batch = base / "a0"
    rel = "data/cases/PILOT-01/public/raw/DOC-01.pdf"
    pdf = batch / "session-01" / rel
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"fixture-pinned-raw-pdf")
    raw_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    doc_hash = dump(batch / "operator_manifest.json", {"case_id": slug, "forms": {"original": {"sha256": raw_hash}}})
    slot = {"role": "original", "position": 1, "workspace": "session-01", "input_hashes": {rel: raw_hash}}
    plan_hash = dump(batch / "plan.json", {"case_id": slug, "manifest_sha256": doc_hash, "order": [slot]})
    (batch / "plan.sha256").write_text(plan_hash)
    run = batch / "session-01/runs/original-A0"
    status = "SUBMITTED" if a_valid else "FAILED"
    receipt = {"role": "original", "position": 1, "selected_run": run.name if a_valid else None,
               "attempts": [{"run_id": run.name, "status": status}]}
    dump(batch / "live.json", {"manifest_sha256": doc_hash, "mode": "live", "sessions": [receipt]})
    header = {"mode": "LIVE", "condition": "A0", "case_id": "PILOT-01", "run_id": run.name}
    dump(run / "summary.json", {**header, "execution_status": status,
                                "actual_model_answer": a_valid, "model_calls": 1})
    dump(run / "input_hashes.json", slot["input_hashes"])
    if a_valid:
        saved_answer(run, [i["a0"]["quote"] for i in case["items"]])

    b_dir = base / "b1"
    packet = {"issuer_evidence": [{"evidence_id": "E1", "text": "fixture"}],
              "candidates": [{"candidate_id": "C1", "business": [], "financials": [], "multiples": []}]}
    request = {"input": wire_dumps(packet)}
    dump(b_dir / "blind_request.json", request)
    dump(b_dir / "blind_input.json", {"run_id": "blind-B1", "mode": "LIVE", "freeze": {"case_id": slug},
         "variant": "B1", "request_sha256": hashlib.sha256(wire_dumps(request).encode()).hexdigest(),
         "candidate_order": ["C1"], "baseline_run_id": None})
    dump(b_dir / "summary.json", {"run_id": "blind-B1", "condition": "A1_BLIND_B", "case_id": slug,
         "execution_status": "SUBMITTED" if b_valid else "NOT_STARTED_MISSING_API_KEY", "response_id": "fixture",
         "mode": "LIVE", "variant": "B1", "actual_model_answer": b_valid, "model_calls": int(b_valid)})
    if b_valid:
        answer = mock_answer(["C1"])
        dump(b_dir / "blind_review.json", answer)
        dump(b_dir / "01_blind_review_response.json", {"id": "fixture", "status": "completed",
             "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}]})
    return manifest, ranking


@pytest.mark.parametrize("a,b", [(True, True), (False, True), (True, False), (False, False)])
def test_linked_submissions_and_genuine_failure_fallback(tmp_path, a, b):
    fixture(tmp_path, a, b)
    report = evaluate(tmp_path / "roster")
    assert report["issuers"][0]["status"] == "EVALUABLE", report["issuers"][0]
    assert report["issuers"][0]["observed_runs"]["a0_original"]["run_id"] == "original-A0"
    assert report["summary"]["tied"] == 1


@pytest.mark.parametrize("bad", ["absent", "empty", "mock_b", "mock_link", "preflight_a", "input", "rank_edit",
                                  "wrong_case", "wrong_role", "wrong_a0_quote", "a0_answer_missing",
                                  "b_raw_missing", "b_answer_edited", "pdf_tampered", "fake_fallback"])
def test_observed_rejects_unverified_evidence(tmp_path, bad):
    roster, _ = fixture(tmp_path)
    entry = roster["issuers"][0]
    a_dir = tmp_path / "a0/session-01/runs/original-A0"
    def edit(path, **changes):
        dump(path, {**json.loads(path.read_bytes()), **changes})
    if bad == "absent":
        del entry["observed_runs"]
        dump(tmp_path / "roster", roster)
    elif bad == "empty":
        entry["observed_runs"] = {}
        dump(tmp_path / "roster", roster)
    elif bad == "mock_b":
        edit(tmp_path / "b1/summary.json", mode="MOCK")
    elif bad == "mock_link":
        edit(tmp_path / "rank", blind_response_links={"b1": {"mode": "MOCK"}})
    elif bad == "preflight_a":
        edit(a_dir / "summary.json", mode="PREFLIGHT")
    elif bad == "input":
        edit(tmp_path / "rank", input_sha256="wrong")
    elif bad == "rank_edit":
        edit(tmp_path / "rank", status="FAILED")
    elif bad == "wrong_case":
        edit(tmp_path / "b1/summary.json", case_id="OTHER")
    elif bad == "wrong_role":
        edit(tmp_path / "b1/blind_input.json", variant="B2")
    elif bad == "wrong_a0_quote":
        edit(a_dir / "review.json", judgments=["Other answer"])
    elif bad == "a0_answer_missing":
        (a_dir / "01_agent_response.json").unlink()
    elif bad == "b_raw_missing":
        (tmp_path / "b1/01_blind_review_response.json").unlink()
    elif bad == "b_answer_edited":
        edit(tmp_path / "b1/blind_review.json", status="READY")
    elif bad == "pdf_tampered":
        (tmp_path / "a0/session-01/data/cases/PILOT-01/public/raw/DOC-01.pdf").write_bytes(b"other")
    else:
        case = json.loads((tmp_path / "input").read_bytes())
        case["b1"]["valid"] = False
        digest = dump(tmp_path / "input", case)
        dump(tmp_path / "rank", {**rank(case), "input_sha256": digest})
    report = evaluate(tmp_path / "roster")
    assert report["issuers"][0]["reason"] and report["summary"]["unevaluable_issuers"] == 1
    assert report["summary"]["equal_issuer_mean_delta"] is None


def load_file(path):
    return json.loads(path.read_bytes())


def save_trial_roster(base, manifest, case):
    digest = dump(base / "input", case)
    dump(base / "rank", {**rank(case), "input_sha256": digest})
    dump(base / "roster", manifest)


def trial_archive(base, calibration=False, repeat=False, failed=False):
    roster, _ = fixture(base)
    files = roster["issuers"][0]["observed_runs"]
    case = load_file(base / "input")
    batch = base / "a0"
    forms = load_file(batch / "operator_manifest.json")
    plan = load_file(batch / "plan.json")
    ledger = load_file(batch / "live.json")
    roles = ["canary_1", "canary_2", "control"] if calibration else ["canary", "control"]
    rel = "data/cases/PILOT-01/public/raw/DOC-01.pdf"
    links = []
    for pos, role in enumerate(roles, 2):
        workspace = f"session-{pos:02}"
        run_id = f"trial-{pos}"
        tid = f"T{pos}"
        target = f"C{pos}"
        work = batch / workspace
        path = work / rel
        path.parent.mkdir(parents=True)
        path.write_bytes(role.encode())
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        forms["forms"][role] = {"sha256": sha, "target_id": target, "subtype": "s"}
        # A changed non-PDF input must invalidate the archived workspace as well.
        digests = {rel: sha, "config/settings.json": dump(work / "config/settings.json", {"value": 1})}
        plan["order"].append({"position": pos, "role": role, "workspace": workspace, "input_hashes": digests})
        valid = not (failed and pos == 2)
        status = "SUBMITTED" if valid else "FAILED"
        ledger["sessions"].append({"role": role, "position": pos, "selected_run": run_id if valid else None,
                                   "attempts": [{"run_id": run_id, "status": status}]})
        directory = work / "runs" / run_id
        dump(directory / "summary.json", {"mode": "LIVE", "case_id": "PILOT-01", "condition": "A0",
             "run_id": run_id, "execution_status": status, "actual_model_answer": valid, "model_calls": 1})
        dump(directory / "input_hashes.json", digests)
        quote = f"specific synthetic trial answer {pos}" if valid else None
        if valid:
            saved_answer(directory, [quote])
        outcome = ("no_false_alarm" if role == "control" else "detected") if valid else "unscorable"
        links.append({"trial_id": tid, "role": role, "quote": quote})
        case["trials"].append({"id": tid, "kind": "control" if role == "control" else "realistic",
            "target_id": target, "subtype": "s", "a0_run_id": run_id,
            "a0": {"outcome": outcome, "reason": "fixture rubric"},
            "b1": {"outcome": "unscorable", "reason": "outside synthetic B packet"}})
    digest = dump(batch / "operator_manifest.json", forms)
    plan["manifest_sha256"] = ledger["manifest_sha256"] = digest
    (batch / "plan.sha256").write_text(dump(batch / "plan.json", plan))
    dump(batch / "live.json", ledger)
    if repeat:
        secondary = base / "repeat"
        shutil.copytree(batch, secondary)
        case["trials"].append({**deepcopy(case["trials"][0]), "id": "R", "repeat_of": "T2", "a0_run_id": "repeat-run"})
        links.append({**links[0], "trial_id": "R", "a0_batch": "repeat"})
        old = secondary / "session-02/runs/trial-2"
        new = old.with_name("repeat-run")
        old.rename(new)
        dump(new / "summary.json", {**load_file(new / "summary.json"), "run_id": new.name})
        saved_answer(new, [links[-1]["quote"]])
        ledger["sessions"][1].update(selected_run=new.name, attempts=[{"run_id": new.name, "status": "SUBMITTED"}])
        dump(secondary / "live.json", ledger)
    files["a0_trials"] = links
    save_trial_roster(base, roster, case)
    return roster, case


@pytest.mark.parametrize("calibration,repeat,failed", [(False, False, False), (True, False, False),
    (True, True, False), (False, False, True)])
def test_observed_trial_material_and_outcome_provenance(tmp_path, calibration, repeat, failed):
    _, case = trial_archive(tmp_path, calibration, repeat, failed)
    issuer = evaluate(tmp_path / "roster")["issuers"][0]
    assert issuer["status"] == "EVALUABLE", issuer
    proof = issuer["observed_runs"]["a0_trials"]
    assert set(proof) == {t["id"] for t in case["trials"]}
    assert (proof["T2"]["execution_status"] == "FAILED") == failed
    if not failed:
        assert proof["T2"]["response_sha256"] and proof["T2"]["review_sha256"]
    if repeat:
        assert proof["R"]["repeat_of"] == "T2" and proof["R"]["pdf_sha256"] == proof["T2"]["pdf_sha256"]


@pytest.mark.parametrize("bad", ["missing_all", "missing_role", "missing_link", "duplicate", "swapped_canaries",
    "wrong_run", "wrong_position", "stale_hash", "different_pdf", "other_input", "forged_quote", "missing_quote",
    "unrelated_raw", "edited_review", "foreign_repeat", "repeat_wrong_form", "failure_as_miss", "failure_quote"])
def test_unlinked_trial_is_unevaluable(tmp_path, bad):
    roster, case = trial_archive(tmp_path, calibration=True, repeat=True)
    files = roster["issuers"][0]["observed_runs"]
    links = files["a0_trials"]
    batch = tmp_path / "a0"
    work = batch / "session-02"
    run = work / "runs/trial-2"
    if bad == "missing_all":
        del files["a0_trials"]
    elif bad == "missing_role":
        links.pop(1)
        case["trials"].pop(1)
    elif bad == "missing_link":
        links.pop(2)
    elif bad == "duplicate":
        links.append(links[0])
    elif bad == "swapped_canaries":
        for a, b in ((0, 1), (3, 1)):
            links[a]["role"] = links[b]["role"]
        links[1]["role"] = "canary_1"
    elif bad == "wrong_run":
        case["trials"][0]["a0_run_id"] = "unselected"
    elif bad == "wrong_position":
        ledger = load_file(batch / "live.json")
        ledger["sessions"][1]["position"] = 31
        dump(batch / "live.json", ledger)
    elif bad == "stale_hash":
        dump(run / "input_hashes.json", {})
    elif bad == "different_pdf":
        (work / "data/cases/PILOT-01/public/raw/DOC-01.pdf").write_bytes(b"wrong")
    elif bad == "other_input":
        dump(work / "config/settings.json", {"value": 2})
    elif bad == "forged_quote":
        links[0]["quote"] = "invented passage"
    elif bad == "missing_quote":
        links[0]["quote"] = None
    elif bad == "unrelated_raw":
        dump(run / "01_agent_response.json", {"id": "x", "status": "completed", "output": [{"type": "message"}]})
    elif bad == "edited_review":
        dump(run / "review.json", {**load_file(run / "review.json"), "judgments": [links[0]["quote"], "edited"]})
    elif bad == "foreign_repeat":
        links[-1]["a0_batch"] = "a0"
    elif bad == "repeat_wrong_form":
        links[-1]["role"] = "canary_2"
    else:
        roster, case = trial_archive(tmp_path / "failed", failed=True)
        tmp_path = tmp_path / "failed"
        if bad == "failure_as_miss":
            case["trials"][0]["a0"]["outcome"] = "missed"
        else:
            roster["issuers"][0]["observed_runs"]["a0_trials"][0]["quote"] = "spurious"
    save_trial_roster(tmp_path, roster, case)
    row = evaluate(tmp_path / "roster")["issuers"][0]
    assert row["status"] == "UNEVALUABLE", row


@pytest.mark.parametrize("outcome", ["missed", "no_false_alarm", "unscorable"])
def test_absence_is_gradeable_from_a_real_submission(tmp_path, outcome):
    roster, case = trial_archive(tmp_path)
    n = int(outcome == "no_false_alarm")
    roster["issuers"][0]["observed_runs"]["a0_trials"][n]["quote"] = None
    case["trials"][n]["a0"]["outcome"] = outcome
    save_trial_roster(tmp_path, roster, case)
    row = evaluate(tmp_path / "roster")["issuers"][0]
    assert row["status"] == "EVALUABLE", row


@pytest.mark.parametrize("prior_success", [False, True])
def test_trial_missing_key_only_supports_genuine_nonsubmission(tmp_path, prior_success):
    trial_archive(tmp_path, failed=True)
    batch = tmp_path / "a0"
    ledger = load_file(batch / "live.json")
    receipt = ledger["sessions"][1]
    status = "NOT_STARTED_MISSING_API_KEY"
    receipt["attempts"][0]["status"] = status
    if prior_success:
        receipt["attempts"].insert(0, {"status": "SUBMITTED", "run_id": "already-selected"})
    dump(batch / "live.json", ledger)
    summary = batch / "session-02/runs/trial-2/summary.json"
    dump(summary, {**load_file(summary), "execution_status": status, "model_calls": 0})
    row = evaluate(tmp_path / "roster")["issuers"][0]
    assert row["status"] == ("UNEVALUABLE" if prior_success else "EVALUABLE"), row
