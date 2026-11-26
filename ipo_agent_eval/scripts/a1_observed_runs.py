"""Validate archived original, trial A0, and blind B runs before real-case evaluation."""
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from ipo_eval.a1_ranking import rank
from ipo_eval.a1_ranking_blind import link_responses
from ipo_eval.agent_loop import _format_only, output_json
from ipo_eval.blind_reviewer import wire_dumps
from ipo_eval.format_patch import apply_format_patch

FAILURES = {"FAILED", "NOT_STARTED_MISSING_API_KEY"}
OBSERVED_RUNS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["ranking_input", "a0_batch", "b1_dir"],
    "properties": {key: {"type": "string", "pattern": r"\S", "description": description}
                   for key, description in {
                       "ranking_input": "Original annotation JSON used as input to ipo_eval.a1_ranking.",
                       "a0_batch": "A0 preparation directory with plan, operator manifest and live ledger.",
                       "b1_dir": "Original blind B1 LIVE run directory including failed or missing-key records.",
                       "b2_dir": "Required when the ranking uses a valid B2 diagnostic.",
                   }.items()},
}
TEXT = {"type": "string", "pattern": r"\S"}
OBSERVED_RUNS_SCHEMA["properties"]["a0_trials"] = {
    "type": "array", "description": "One entry per trial in the ranking input, including repeats.",
    "items": {"type": "object", "additionalProperties": False, "required": ["trial_id", "role", "quote"],
              "properties": {
                  "trial_id": TEXT, "role": {"enum": ["canary", "canary_1", "canary_2", "control"]},
                  "quote": {"anyOf": [TEXT, {"type": "null"}],
                            "description": "Passage from the submitted review. Null for an omission or unscorable answer."},
                  "a0_batch": {**TEXT, "description": "Separate prepared batch for a repeat of the same form."},
              }},
}


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    def unique(pairs):
        obj = dict(pairs)
        if len(obj) != len(pairs):
            raise ValueError("duplicate provenance JSON key")
        return obj
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def only(rows, label):
    if len(rows) != 1:
        raise ValueError("expected exactly one " + label)
    return rows[0]


def narrative_fields(obj):
    if isinstance(obj, str):
        yield " ".join(obj.split())
    elif isinstance(obj, list):
        for value in obj:
            yield from narrative_fields(value)
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from narrative_fields(value)


def child(directory, name):
    if not isinstance(name, str) or name in {"", ".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("invalid archived run or workspace name")
    return directory / name


def verify_live(summary, run, condition, case_id):
    if (summary["mode"] != "LIVE" or summary["case_id"] != case_id or summary["condition"] != condition
            or summary["run_id"] != run["id"]):
        raise ValueError("observed run identity, case, role or LIVE mode mismatch")
    status = summary["execution_status"]
    if run["valid"]:
        if status != "SUBMITTED" or summary["actual_model_answer"] is not True or summary["model_calls"] < 1:
            raise ValueError("valid original judgment requires a submitted LIVE model answer")
    elif status not in FAILURES:
        raise ValueError("invalid original judgment needs a recorded LIVE failure or non-submission")


def a0_batch(batch, case_id):
    plan_file = batch / "plan.json"
    plan = load(plan_file)
    source = batch / "operator_manifest.json"
    original = load(source)
    ledger = load(batch / "live.json")
    if (file_digest(plan_file) != (batch / "plan.sha256").read_text().strip()
            or plan["manifest_sha256"] != file_digest(source) or ledger["manifest_sha256"] != plan["manifest_sha256"]
            or plan["case_id"] != case_id or original["case_id"] != case_id or ledger["mode"] != "live"):
        raise ValueError("A0 input manifest, frozen plan or live batch does not match")
    slots = plan["order"]
    forms = original["forms"]
    if (set(forms) not in ({"original"}, {"original", "canary", "control"},
                          {"original", "canary_1", "canary_2", "control"})
            or set(forms) != {r["role"] for r in slots} or len(slots) != len(forms)
            or any(len({r[k] for r in slots}) != len(slots) for k in ("position", "workspace"))
            or len({f["sha256"] for f in forms.values()}) != len(forms)):
        raise ValueError("A0 plan needs distinct roles, forms, positions and workspaces")
    return forms, {r["role"]: r for r in slots}, ledger["sessions"]


def committed_review(directory, review):
    events = [json.loads(line) for line in (directory / "events.jsonl").read_bytes().splitlines() if line.strip()]
    commit = only([e for e in events if e["event"] == "tool_call" and e.get("tool") == "submit_review"
                   and e.get("result", {}).get("execution_status") == "SUBMITTED"], "successful A0 commit")
    args = commit["arguments"]
    actor = commit["actor"]
    repaired = actor == "program_commit" and commit["call_id"].endswith("_format_repair")
    if (actor != "model" and not repaired) or args["phase"] != "COMMIT":
        raise ValueError("A0 submission has no corresponding model commit")
    call_id = commit["call_id"].removesuffix("_format_repair") if repaired else commit["call_id"]
    matches = []
    for path in directory.glob("*_response.json"):
        raw = load(path)
        if raw.get("id") and raw.get("status") == "completed":
            matches.extend((path, json.loads(c["arguments"])) for c in raw.get("output", [])
                           if c.get("type") == "function_call" and c.get("name") == "submit_review"
                           and c.get("call_id") == call_id)
    path, actual = only(matches, "archived A0 model commit response")
    evidence = {"response_sha256": file_digest(path)}
    if repaired:
        repair = only(list(directory.glob("*_format_repair_response.json")), "archived A0 format repair")
        request = load(repair.with_name(repair.name.replace("_response.json", "_request.json")))
        payload = json.loads(request["input"][-1]["content"])
        repair_raw = load(repair)
        if payload["previous_output"] != actual or not repair_raw.get("id") or repair_raw.get("status") != "completed":
            raise ValueError("A0 format repair is not linked to the model's commit")
        fixed = output_json(repair_raw)
        if request["text"]["format"]["name"] == "format_patch":
            actual = apply_format_patch(actual, fixed, payload["target_schema"], payload["known_claim_ids"])
        else:
            _format_only(actual, fixed)
            actual = fixed
        evidence["repair_response_sha256"] = file_digest(repair)
    if actual != args:
        raise ValueError("A0 accepted commit differs from the archived model response")
    body = dict(args["review"])
    for key in ("requests", "escalations"):
        body[key] = commit["result"][key]
    if any(review.get(key) != value for key, value in body.items()) or set(review) - body.keys() - {
            "run_id", "case_id", "condition", "config_version", "issuer_name", "cutoff_at", "final_status", "calculations"}:
        raise ValueError("A0 saved review differs from the committed model answer")
    return list(narrative_fields(body)), evidence


def verify_a0_slot(batch, prepared, role, run_id, expected_valid=None):
    forms, slots, sessions = prepared
    slot = slots[role]
    receipt = only([r for r in sessions if r["role"] == role], f"{role} A0 session")
    valid = receipt["selected_run"] is not None
    submitted = next((r["run_id"] for r in receipt["attempts"] if r["status"] == "SUBMITTED"), None)
    if (receipt["selected_run"] != submitted or receipt["position"] != slot["position"]
            or (expected_valid is not None and valid != expected_valid)
            or (valid and run_id != receipt["selected_run"])):
        raise ValueError("A0 run selection mismatch")
    attempt = only([r for r in receipt["attempts"] if r["run_id"] == run_id], "matching A0 attempt")
    if not valid and receipt["attempts"][-1]["run_id"] != run_id:
        raise ValueError("use the final unresolved A0 attempt for fallback")
    work = child(batch, slot["workspace"])
    directory = child(work / "runs", run_id)
    summary = load(directory / "summary.json")
    verify_live(summary, {"id": run_id, "valid": valid}, "A0", "PILOT-01")
    if summary["execution_status"] != attempt["status"]:
        raise ValueError("A0 run and batch ledger disagree on submission")
    raw_rel = "data/cases/PILOT-01/public/raw/DOC-01.pdf"
    raw_hash = file_digest(work / raw_rel)
    if raw_hash != forms[role]["sha256"] or slot["input_hashes"][raw_rel] != raw_hash:
        raise ValueError("A0 primary input differs from the registered form")
    for name, digest in slot["input_hashes"].items():
        path = (work / name).resolve()
        if not path.is_relative_to(work.resolve()) or file_digest(path) != digest:
            raise ValueError("A0 workspace differs from a frozen input")
    hashes_file = directory / "input_hashes.json"
    if (valid or hashes_file.exists()) and load(hashes_file) != slot["input_hashes"]:
        raise ValueError("A0 frozen inputs do not match recorded execution")
    result = {"run_id": run_id, "execution_status": summary["execution_status"],
              "summary_sha256": file_digest(directory / "summary.json"), "pdf_sha256": raw_hash}
    passages = []
    if valid:
        review_file = directory / "review.json"
        review = load(review_file)
        if (review["run_id"], review["condition"], review["case_id"]) != (run_id, "A0", "PILOT-01"):
            raise ValueError("A0 saved review identity mismatch")
        passages, evidence = committed_review(directory, review)
        result.update(evidence)
        result["review_sha256"] = file_digest(review_file)
    elif summary["actual_model_answer"] is not False:
        raise ValueError("failed A0 attempt cannot declare a submitted answer")
    return result, passages


def verify_blind(directory, case, role):
    summary = load(directory / "summary.json")
    run = case[role]
    verify_live(summary, run, "A1_BLIND_B", case["case_id"])
    info = load(directory / "blind_input.json")
    request = load(directory / "blind_request.json")
    if (info["variant"] != role.upper() or summary["variant"] != role.upper()
            or info["freeze"]["case_id"] != case["case_id"] or info["run_id"] != run["id"]
            or info["mode"] != "LIVE" or info["request_sha256"] != hashlib.sha256(wire_dumps(request).encode()).hexdigest()):
        raise ValueError("blind run does not match frozen role, input or case")
    result = {"run_id": run["id"], "execution_status": summary["execution_status"],
              "summary_sha256": file_digest(directory / "summary.json"), "request_sha256": info["request_sha256"]}
    if run["valid"]:
        actual = [load(p) for p in directory.glob("*_blind_review_response.json")]
        raw = only([r for r in actual if r.get("id") and r["id"] == summary["response_id"]], "matching B response")
        if raw["status"] != "completed" or output_json(raw) != load(directory / "blind_review.json"):
            raise ValueError("B submission differs from its archived model response")
        result["answer_sha256"] = file_digest(directory / "blind_review.json")
    return result


def verify_quote(trial_id, quote, passages):
    normalized = " ".join(quote.split())
    if not any(normalized in field for field in passages):
        raise ValueError(f"{trial_id}: A0 annotation quote differs from its archived answer")


def verify_a0(base, files, case):
    batch = (base / files["a0_batch"]).resolve()
    prepared = a0_batch(batch, case["case_id"])
    forms, slots, _ = prepared
    run = case["a0_original"]
    original, passages = verify_a0_slot(batch, prepared, "original", run["id"], run["valid"])
    original["original_pdf_sha256"] = original.pop("pdf_sha256")
    if run["valid"]:
        for item in case["items"]:
            judgment = item.get("a0")
            if judgment and judgment.get("quote"):
                verify_quote(item["id"], judgment["quote"], passages)

    links = files.get("a0_trials", [])
    by_id = {row["trial_id"]: row for row in links}
    trials = case["trials"]
    if len(by_id) != len(links) or set(by_id) != {t["id"] for t in trials}:
        raise ValueError("register exactly one observed A0 role and quotation record per trial")
    primary_roles = [by_id[t["id"]]["role"] for t in trials if "repeat_of" not in t]
    if len(set(primary_roles)) != len(primary_roles) or set(primary_roles) != set(forms) - {"original"}:
        raise ValueError("primary trials must account for each prepared A0 trial role exactly once")
    calibrated = "canary_2" in forms
    canaries = [t for t in trials if "repeat_of" not in t and by_id[t["id"]]["role"] in {"canary_1", "canary_2"}]
    if calibrated and (len({t["subtype"] for t in canaries}) != 1 or len({t["target_id"] for t in canaries}) != 2):
        raise ValueError("calibration requires distinct targets within a common subtype")
    audited = {}
    for trial in trials:
        tid = trial["id"]
        link = by_id[tid]
        role = link["role"]
        repeat = trial.get("repeat_of")
        if (role == "control") != (trial["kind"] == "control") or (calibrated and role != "control" and trial["kind"] != "realistic"):
            raise ValueError(f"{tid}: A0 material role and trial kind disagree")
        if role not in forms:
            raise ValueError(f"{tid}: A0 role is outside the frozen plan")
        form = forms[role]
        if any(key in form and form[key] != trial[key] for key in ("target_id", "subtype")):
            raise ValueError(f"{tid}: A0 annotation disagrees with its frozen target or subtype")
        if calibrated and role != "control" and "target_id" not in form:
            raise ValueError(f"{tid}: calibration must identify both frozen target-to-form mappings")
        current, proof = batch, prepared
        if repeat:
            if by_id[repeat]["role"] != role or "a0_batch" not in link:
                raise ValueError(f"{tid}: repeat requires the original role in a separate batch")
            current = (base / link["a0_batch"]).resolve()
            proof = a0_batch(current, case["case_id"])
            if (current == batch or proof[0].get(role) != form
                    or proof[1][role]["input_hashes"] != slots[role]["input_hashes"]):
                raise ValueError(f"{tid}: repeated A0 inputs differ from the primary trial")
        elif "a0_batch" in link:
            raise ValueError(f"{tid}: use the primary A0 batch for independent forms")
        record, answer = verify_a0_slot(current, proof, role, trial["a0_run_id"])
        quote = link["quote"]
        outcome = trial["a0"]["outcome"]
        if record["execution_status"] != "SUBMITTED" and (outcome != "unscorable" or quote is not None):
            raise ValueError(f"{tid}: an unresolved A0 run can only support unscorable without a quote")
        if quote is not None:
            verify_quote(tid, quote, answer)
        elif outcome in {"detected", "false_alarm"}:
            raise ValueError(f"{tid}: positive A0 annotation requires an archived answer quotation")
        audited[tid] = {**record, "role": role, "repeat_of": repeat, "quote": quote}
    return {"a0_original": original, "a0_trials": audited}


def verify_observed(base, entry, ranking):
    files = entry.get("observed_runs")
    error = next(Draft202012Validator(OBSERVED_RUNS_SCHEMA).iter_errors(files), None)
    if error:
        raise ValueError(f"observed_runs requires archived execution paths: {error.message}")
    case_path = base / files["ranking_input"]
    case = load(case_path)
    if case["case_id"] != entry["case_id"] or file_digest(case_path) != ranking.get("input_sha256"):
        raise ValueError("ranking is not tied to this case's archived annotation input")
    recomputed = rank(case)
    if {k: v for k, v in ranking.items() if k not in {"input_sha256", "blind_response_links"}} != recomputed:
        raise ValueError("archived ranking is inconsistent with recomputation from its source")
    provenance = verify_a0(base, files, case)
    b1_dir = base / files["b1_dir"]
    provenance["b1"] = verify_blind(b1_dir, case, "b1")
    linked = ranking.get("blind_response_links", {})
    if not isinstance(linked, dict) or any(not isinstance(x, dict) or x.get("mode") != "LIVE" for x in linked.values()):
        raise ValueError("observed ranking contains non-LIVE B evidence")
    if "b2" in case and case["b2"]["valid"]:
        if not case["b1"]["valid"] or not files.get("b2_dir"):
            raise ValueError("valid B2 requires its paired LIVE B1 and B2 archives")
        b2_dir = base / files["b2_dir"]
        provenance["b2"] = verify_blind(b2_dir, case, "b2")
        rebuilt = link_responses(case, b1_dir, b2_dir)
    elif case["b1"]["valid"]:
        primary = {k: v for k, v in case.items() if k != "b2"}
        primary["trials"] = [{k: v for k, v in trial.items() if k != "b2"} for trial in case["trials"]]
        rebuilt = link_responses(primary, b1_dir, None)
    else:
        rebuilt = {}
    if any(key not in rebuilt or rebuilt[key] != data for key, data in linked.items()):
        raise ValueError("B response link is inconsistent with the archived submission")
    if (not (case["a0_original"]["valid"] and case["b1"]["valid"])
            and ranking["B1"]["canary_extra"] != ranking["B1"]["baseline_extra"]):
        raise ValueError("invalid original submission requires equal fallback lists")
    return provenance
