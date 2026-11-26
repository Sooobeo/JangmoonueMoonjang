"""Bind coder annotations to the actual blind-reviewer responses after submission."""

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from .blind_reviewer import PACKET, REVIEW, sha, unique_object, wire_dumps


def read_json(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_object)


def verify_schema(schema, instance, filename):
    error = next(Draft202012Validator(schema).iter_errors(instance), None)
    if error:
        raise ValueError(f"{filename} {error.json_path}: {error.message}")


def load_run(directory, case, role):
    directory = Path(directory)
    info = read_json(directory / "blind_input.json")
    summary = read_json(directory / "summary.json")
    request = read_json(directory / "blind_request.json")
    expected_id = case[role]["id"]
    mode = summary["mode"]
    if (not case[role]["valid"] or mode not in {"LIVE", "MOCK"}
            or info["mode"] != mode or info["variant"] != role.upper()
            or summary["variant"] != role.upper() or info["run_id"] != expected_id
            or summary["run_id"] != expected_id or summary["case_id"] != case["case_id"]
            or info["freeze"]["case_id"] != case["case_id"]
            or sha(wire_dumps(request).encode()) != info["request_sha256"]):
        raise ValueError(f"{role}: run identity, mode, case or request digest mismatch")
    filename, status = (("blind_review.json", "SUBMITTED") if mode == "LIVE"
                        else ("mock_review.json", "MOCK_COMPLETE"))
    if summary["execution_status"] != status:
        raise ValueError(f"{role}: expected {status} for {mode} response linkage")
    packet = json.loads(request["input"], object_pairs_hook=unique_object)
    verify_schema(PACKET, packet, "blind_request.json")
    candidates = [c["candidate_id"] for c in packet["candidates"]]
    if candidates != info["candidate_order"] or len(set(candidates)) != len(candidates):
        raise ValueError(f"{role}: candidate order or identity mismatch")
    source_ids = {e["evidence_id"] for e in packet["issuer_evidence"]}
    for candidate in packet["candidates"]:
        for group in ("business", "financials", "multiples"):
            source_ids.update(e["evidence_id"] for e in candidate[group])
    contents = (directory / filename).read_bytes()
    answer = json.loads(contents, object_pairs_hook=unique_object)
    verify_schema(REVIEW, answer, filename)
    by_candidate = {cid: [] for cid in candidates}
    for row in answer["candidates"]:
        if row["candidate_id"] in by_candidate:
            by_candidate[row["candidate_id"]].append(row)
    common_packet = {**packet, "candidates": sorted(packet["candidates"], key=lambda c: c["candidate_id"])}
    common_request = {**request, "input": wire_dumps(common_packet)}
    return info, {"run_id": expected_id, "mode": mode, "answer_sha256": sha(contents),
                  "request_without_order_sha256": sha(wire_dumps(common_request).encode()),
                  "request_sha256": info["request_sha256"], "freeze": info["freeze"],
                  "candidate_order": candidates, "candidate_responses": by_candidate,
                  "earnings": answer["earnings"], "aggregation": answer["aggregation"]}, source_ids


def check_original(item, responses, evidence):
    judgment = item["b1"]
    candidate = item["candidate_id"]
    if candidate is not None:
        if candidate not in responses["candidate_responses"]:
            if judgment and judgment["stance"] not in {"omitted", "alternative_only", "group_only"}:
                raise ValueError(f"{item['id']}: candidate is outside B1 packet")
            return
        answer_rows = responses["candidate_responses"][candidate]
    elif "b_proposal" in item:
        answer_rows = [responses[item["b_proposal"]]]
    else:
        answer_rows = []
    if not judgment or judgment["stance"] in {
            "omitted", "conditions_open", "group_only", "alternative_only", "unresolved_conflict"}:
        return
    # Without a quote and source the ranking engine already yields unknown.
    if not judgment["quote"] or not judgment["source_ref"]:
        return
    cited = set(re.findall(r"\bE[0-9]+\b", judgment["source_ref"]))
    matching_rows = [
        row for row in answer_rows
        if any(judgment["quote"] in row.get(field, "") for field in ("reason", "proposal"))
        and cited and cited <= set(row["evidence_ids"]) and cited <= evidence
    ]
    if not matching_rows:
        raise ValueError(f"{item['id']}: B1 quote or cited evidence does not match the linked response")
    if candidate is not None:
        accepts = judgment["stance"] in {"explicit_accept", "conditions_resolved"}
        if not any((r["decision"] == "INCLUDE") == accepts for r in matching_rows):
            raise ValueError(f"{item['id']}: annotated B1 stance contradicts the candidate decision")


def check_trial(trial, role, responses, evidence):
    rows = responses["candidate_responses"].get(trial["target_id"])
    outcome = trial[role]["outcome"]
    if rows is None and outcome != "unscorable":
        raise ValueError(f"{trial['id']}: target outside B packet is unscorable")
    if outcome == "detected" and not any(
            r["reason"].strip() and set(r["evidence_ids"]) & evidence for r in rows or []):
        raise ValueError(f"{trial['id']}: detected needs candidate-specific text and a linked evidence ID")
    if outcome == "false_alarm" and not rows:
        raise ValueError(f"{trial['id']}: a false alarm needs a response about the target")


def link_responses(case, b1_dir, b2_dir):
    """Check identities and citations. The supplied rubric coder decides semantic support."""
    if not b1_dir or ("b2" in case) != bool(b2_dir):
        raise ValueError("Supply the B1 directory and, for B2 diagnostics, both B1 and B2 directories")
    primary, b1, source_ids = load_run(b1_dir, case, "b1")
    if primary["baseline_run_id"] is not None:
        raise ValueError("B1 must not refer to another baseline")
    for item in case["items"]:
        check_original(item, b1, source_ids)
    for trial in case["trials"]:
        check_trial(trial, "b1", b1, source_ids)
    result = {"b1": b1}
    if b2_dir:
        diag, b2, diag_sources = load_run(b2_dir, case, "b2")
        if (diag["baseline_run_id"] != primary["run_id"] or diag["freeze"] != primary["freeze"]
                or diag["mode"] != primary["mode"]
                or b2["request_without_order_sha256"] != b1["request_without_order_sha256"]
                or sorted(diag["candidate_order"]) != sorted(primary["candidate_order"])
                or diag["candidate_order"] == primary["candidate_order"]):
            raise ValueError("B2 must be paired to this B1 with the same settings and a changed order")
        for trial in case["trials"]:
            check_trial(trial, "b2", b2, diag_sources)
        result["b2"] = b2
    return result
