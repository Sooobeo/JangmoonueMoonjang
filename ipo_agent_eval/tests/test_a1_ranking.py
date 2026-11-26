import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ipo_eval.a1_ranking import alternative_price, decision, rank
from ipo_eval.a1_ranking_contract import SCHEMA, example


def test_paired_ranking_and_independent_b2():
    case = example()
    unchanged = deepcopy(case)
    result = rank(case)
    assert case == unchanged
    assert result["candidate_counts"] == {
        "original": 2, "a0_explicit": 2, "both_accept": 1, "both_accept_mapped": 1}
    assert result["B1"]["signals"]["business-model"] == {"M": 2, "J": 1, "signal": "promote"}
    assert result["B1"]["mandatory"] == result["B2"]["mandatory"] == ["X"]
    assert result["B1"]["baseline_extra"] == result["B2"]["baseline_extra"] == ["W"]
    assert result["B1"]["canary_extra"] == ["Y"]
    assert result["B2"]["canary_extra"] == ["W"]
    assert result["B1"]["controls"] == {
        "valid": 1, "any_false_alarm": 0, "a0_false_alarm": 0, "b_false_alarm": 0}
    assert result["B2"]["controls"]["any_false_alarm"] == 1
    assert result["b_order_diagnostic"]["changed_detection_trials"] == ["T1"]
    assert result["b_order_diagnostic"]["list_changed"] is True


@pytest.mark.parametrize(("stance", "expected"), [
    ("explicit_accept", "accept"), ("conditions_resolved", "accept"),
    ("review", "challenge"), ("exclude", "challenge"), ("refuting_alternative", "challenge"),
    ("group_only", "unknown"), ("alternative_only", "unknown"), ("conditions_open", "unknown"),
    ("unresolved_conflict", "unknown"), ("omitted", "unknown"),
])
def test_evidence_linked_stances(stance, expected):
    annotation = {"stance": stance, "quote": "test quote", "source_ref": "p.1", "reason": "test"}
    assert decision(annotation, True)[0] == expected
    assert decision({**annotation, "source_ref": None}, True)[0] == "unknown"
    assert decision(annotation, False)[0] == "unknown"
    assert decision(None, True)[0] == "unknown"


def test_multi_trial_caps_and_opposite_detectors():
    case = example()
    # One observer on each trial gives J = 0, even if their misses differ.
    case["trials"][0]["b1"]["outcome"] = "detected"
    case["trials"][1]["b1"]["outcome"] = "missed"
    signals = rank(case)["B1"]["signals"]
    assert signals["business-model"] == {"M": 2, "J": 0, "signal": "baseline"}
    case["trials"][1]["a0"]["outcome"] = "unscorable"
    group = rank(case)["B1"]
    assert group["signals"]["business-model"] == {"M": 1, "J": 0, "signal": "unconfirmed"}
    assert group["trials"][1]["valid_pair"] is False
    assert group["trials"][1]["a0"]["reason"]
    # The original input remains scoreable even if the target is omitted.
    case["items"][1]["a0"] = None
    assert rank(case)["items"][1]["pair"] == "unknown"


def test_controls_obvious_and_repeats_do_not_contribute_to_m():
    case = example()
    t1, _, control = case["trials"]
    repeat = {**t1, "id": "repeat", "repeat_of": "T1", "a0_run_id": "A0-repeat"}
    obvious = {**t1, "id": "obvious", "kind": "obvious", "target_id": "o", "a0_run_id": "A0-o"}
    case["trials"] = [repeat, t1, control, obvious]
    result = rank(case)["B1"]
    assert result["signals"]["business-model"] == {"M": 1, "J": 1, "signal": "unconfirmed"}
    assert result["baseline_extra"] == result["canary_extra"]
    assert len(result["trials"]) == 4
    control["b1"]["outcome"] = "unscorable"
    assert rank(case)["B1"]["controls"]["valid"] == 0


def test_disclosed_price_and_actual_aggregation():
    case = example()
    valuation = {"eps_krw": "2", "aggregation": "median",
                 "basis": "synthetic source p.1",
                 "peers": {"Y": "10", "A": "1", "B": "2", "C": "4", "D": "60"}}
    item = case["items"][1]
    assert alternative_price(item, valuation) == (6, None)
    assert alternative_price(item, {**valuation, "aggregation": "mean"}) == (Fraction(67, 2), None)
    assert alternative_price(item, {**valuation, "aggregation": "other"})[0] is None
    assert alternative_price(item, {**valuation, "peers": {"Y": "10"}})[0] is None
    assert alternative_price(item, {**valuation, "peers": {"Y": "10", "A": None}})[0] is None
    case["valuation"] = valuation
    case["items"] = [item]
    case["disclosed_price_krw"] = "10"
    assert rank(case)["items"][0]["impact_fraction"] == "0.4"
    for p0 in ("0", None):
        case["disclosed_price_krw"] = p0
        assert rank(case)["items"][0]["impact_fraction"] is None


def test_fixed_budget_ties_missing_and_unmapped_candidates():
    case = example()
    case["items"][1]["subtype"] = None
    for item in case["items"]:
        item["alternative"] = {"kind": "fixed", "price": "3300", "basis": "test"}
    case["items"].append({**case["items"][1], "id": "A", "candidate_id": None,
                          "alternative": {"kind": "fixed", "price": None, "basis": "test"}})
    case["k"] = 10
    group = rank(case)["B1"]
    assert group["baseline_extra"] == group["canary_extra"] == ["W", "Y", "A"]
    case["k"] = 0
    assert rank(case)["B1"]["canary_extra"] == []


def test_precise_price_comparison_without_display_rounding():
    case = example()
    case["disclosed_price_krw"] = "1"
    original = case["items"][1]
    case["items"] = [
        {**original, "id": key, "candidate_id": key,
         "alternative": {"kind": "fixed", "price": "1.1" + "0"*45 + v,
                                                "basis": "test"}}
        for key, v in [("a", "1"), ("b", "2")]
    ]
    assert rank(case)["B1"]["baseline_extra"] == ["b"]


def test_materiality_and_status_without_promoting_a_major_acceptance():
    case = example()
    case["qualitative_rules"] = ["independent accounting review"]
    x, y, w = case["items"]
    x["alternative"] = {"kind": "fixed", "price": "3150", "basis": "test"}
    assert rank(case)["status"] == "HUMAN_REVIEW"  # Exactly 5%.
    x["alternative"]["price"] = "3149.999"
    assert rank(case)["status"] == "READY"
    w["blocking_info"] = True
    assert rank(case)["status"] == "PENDING_INFO"
    y["verified_fact_error_ref"] = "independent original p.4, row 1"
    y["qualitative_rule"] = case["qualitative_rules"][0]
    y["alternative"] = {"kind": "fixed", "price": None, "basis": "test"}
    result = rank(case)
    assert result["status"] == "HUMAN_REVIEW"
    assert result["B1"]["mandatory"] == ["Y"]
    assert result["B1"]["promoted"] == []
    y["resolved"] = True
    assert rank(case)["status"] == "PENDING_INFO"
    case["a0_original"]["valid"] = False
    assert rank(case)["status"] == "FAILED"
    assert rank(case)["B1"]["mandatory"] == ["Y"]
    assert rank(case)["B1"]["canary_extra"] == rank(case)["B1"]["baseline_extra"]


def test_b_submission_failure_not_mistaken_for_detection_or_list_instability():
    case = example()
    case["b2"]["valid"] = False
    result = rank(case)
    assert result["B2"]["signals"]["business-model"]["M"] == 0
    assert result["b_order_diagnostic"]["list_changed"] is None
    case["b1"]["valid"] = False
    assert all(i["pair"] == "unknown" for i in rank(case)["items"])


@pytest.mark.parametrize("mistake", ["duplicate_target", "duplicate_trial", "duplicate_item",
    "wrong_repeat", "reused_run", "bad_control", "wrong_peer", "extra_human_grade",
    "unknown_rule", "missing_b2_annotation", "negative_threshold", "negative_k"])
def test_inconsistent_inputs_rejected(mistake):
    case = example()
    x, y, _ = case["items"]
    t1, t2, control = case["trials"]
    if mistake == "duplicate_target":
        t2["target_id"] = t1["target_id"]
    elif mistake == "duplicate_trial":
        t2["id"] = t1["id"]
    elif mistake == "duplicate_item":
        y["id"] = x["id"]
    elif mistake == "wrong_repeat":
        t2["repeat_of"] = t1["id"]
    elif mistake == "reused_run":
        t1["a0_run_id"] = case["a0_original"]["id"]
    elif mistake == "bad_control":
        control["b1"]["outcome"] = "detected"
    elif mistake == "wrong_peer":
        y["alternative"]["peer_id"] = "X"
    elif mistake == "extra_human_grade":
        y["original_human_grade"] = "material"
    elif mistake == "unknown_rule":
        x["qualitative_rule"] = "post-hoc"
    elif mistake == "missing_b2_annotation":
        del t1["b2"]
    elif mistake == "negative_k":
        case["k"] = -1
    else:
        case["materiality_fraction"] = "-0.01"
    with pytest.raises(ValueError):
        rank(case)


def test_cli_example_and_schema_roundtrip(tmp_path):
    cli = [sys.executable, "-m", "ipo_eval.a1_ranking"]
    cwd = Path(__file__).resolve().parents[1]
    payload = subprocess.check_output([*cli, "--example"], cwd=cwd)
    Draft202012Validator.check_schema(SCHEMA)
    assert json.loads(subprocess.check_output([*cli, "--schema"], cwd=cwd)) == SCHEMA
    path = tmp_path / "example.json"
    path.write_bytes(payload)
    result = json.loads(subprocess.check_output([*cli, str(path)], cwd=cwd))
    assert result["input_sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["B1"]["canary_extra"] == ["Y"]
    path.write_text('{"case_id":"INCOMPLETE"}', encoding="utf-8")
    invocation = subprocess.run([*cli, str(path)], cwd=cwd, capture_output=True, check=False)
    assert invocation.returncode == 2 and invocation.stdout == b""


def test_real_mock_run_artifacts_b1_b2_to_ranking_cli(tmp_path, monkeypatch):
    from ipo_eval import blind_reviewer
    from ipo_eval.a1_ranking_blind import link_responses

    # Both directories are produced by the blind reviewer itself. Local stubbed
    # text makes the rubric results observable without a model or real filing.
    packet = {"issuer_evidence": [{"evidence_id": "E0", "text": "synthetic valuation"}],
              "candidates": [{"candidate_id": f"C{i}", "business": [
                  {"evidence_id": f"E{i}", "text": "synthetic candidate business"}],
                  "financials": [], "multiples": []} for i in range(1, 6)]}
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    case = example()

    proposal = {"proposal": "synthetic proposal", "reason": "synthetic rationale", "evidence_ids": ["E0"]}
    def synthetic_answer(ids, *, diagnostic=False):
        rows = []
        for cid in sorted(ids):
            challenge = cid in ({"C1", "C3", "C4", "C5"} if diagnostic else {"C1", "C4"})
            rows.append({"candidate_id": cid, "decision": "REVIEW" if challenge else "INCLUDE",
                         "reason": f"synthetic {cid} reasoning", "evidence_ids": [f"E{cid[1:]}"]})
        return {"status": "READY", "candidates": rows, "earnings": proposal, "aggregation": proposal}

    common = (path, hashlib.sha256(path.read_bytes()).hexdigest(), case["case_id"], 99)
    monkeypatch.setattr(blind_reviewer, "mock_answer", synthetic_answer)
    b1, first = blind_reviewer.execute(*common, mode="mock", output=tmp_path / "runs")
    monkeypatch.setattr(blind_reviewer, "mock_answer", lambda ids: synthetic_answer(ids, diagnostic=True))
    b2, second = blind_reviewer.execute(*common, mode="mock", variant="B2", baseline=b1, output=tmp_path / "runs")
    assert first["execution_status"] == second["execution_status"] == "MOCK_COMPLETE"
    assert first["model_calls"] == second["model_calls"] == 0
    case["b1"]["id"], case["b2"]["id"] = first["run_id"], second["run_id"]
    case["valuation"]["peers"] = {"C1": "18", "C2": "15", "C9": "12"}
    for item, cid in zip(case["items"][:2], ["C1", "C2"], strict=True):
        item["candidate_id"] = item["alternative"]["peer_id"] = cid
        item["b1"].update(quote=f"synthetic {cid} reasoning", source_ref=f"E{cid[1:]}")
    case["items"][2].update(b_proposal="earnings")
    case["items"][2]["b1"].update(quote="synthetic rationale", source_ref="E0")
    for trial, cid in zip(case["trials"], ["C3", "C4", "C5"], strict=True):
        trial["target_id"] = cid
    input_path = tmp_path / "annotations.json"
    input_path.write_text(json.dumps(case), encoding="utf-8")
    command = [sys.executable, "-m", "ipo_eval.a1_ranking", str(input_path),
               "--blind-b1-dir", str(b1), "--blind-b2-dir", str(b2)]
    report = json.loads(subprocess.check_output(command, cwd=Path(__file__).resolve().parents[1]))
    assert report["B1"]["canary_extra"] == ["Y"] and report["B2"]["canary_extra"] == ["W"]
    assert report["b_order_diagnostic"]["list_changed"]
    assert report["blind_response_links"]["b1"]["mode"] == "MOCK"
    assert report["blind_response_links"]["b2"]["answer_sha256"] == hashlib.sha256(
        (b2 / "mock_review.json").read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="identity"):
        link_responses(case, b2, b1)
    case["items"][1]["b1"]["source_ref"] = "E999"
    with pytest.raises(ValueError, match="cited evidence"):
        link_responses(case, b1, b2)
