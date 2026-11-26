"""Rank one issuer's original items from preassigned trials and post-run annotations.

From ipo_agent_eval: python -m ipo_eval.a1_ranking INPUT.json
Use --example for synthetic input or --schema for the JSON input contract.
The program takes no human original grades and does not request model responses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from statistics import mean, median

from jsonschema import Draft202012Validator

from .a1_ranking_contract import SCHEMA, example
from .calculations import PRECISION


def number(value):
    return Fraction(value) if value is not None else None


def display(value):
    if value is None:
        return None
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def alternative_price(item, valuation):
    alternative = item["alternative"]
    if alternative["kind"] == "fixed":
        price = number(alternative["price"])
        return price, None if price is not None else "alternative_price_unavailable"
    if not valuation:
        return None, "peer_valuation_unavailable"
    peer_id = alternative["peer_id"]
    if peer_id != item["candidate_id"] or peer_id not in valuation["peers"]:
        raise ValueError(f"{item['id']}: excluded peer must match the registered candidate")
    if valuation["aggregation"] == "other":
        return None, "disclosed_aggregation_not_implemented"
    eps = number(valuation["eps_krw"])
    peers = [number(value) for key, value in valuation["peers"].items() if key != peer_id]
    if eps is None or not peers or any(x is None for x in peers):
        return None, "missing_remaining_peers_or_eps"
    aggregate = mean if valuation["aggregation"] == "mean" else median
    return eps * aggregate(peers), None


def decision(judgment, valid):
    if not valid:
        return "unknown", "invalid_original_submission"
    if judgment is None:
        return "unknown", "no_linked_judgment"
    if not judgment["quote"] or not judgment["source_ref"]:
        return "unknown", "missing_quote_or_source"
    stance = judgment["stance"]
    if stance in {"explicit_accept", "conditions_resolved"}:
        return "accept", stance
    if stance in {"review", "exclude", "refuting_alternative"}:
        return "challenge", stance
    return "unknown", stance


def original_rows(case):
    price = number(case["disclosed_price_krw"])
    threshold = number(case["materiality_fraction"])
    if threshold < 0:
        raise ValueError("materiality_fraction must be nonnegative")
    rows = {}
    impacts = {}
    candidate_ids = set()
    for item in case["items"]:
        identifier = item["id"]
        if identifier in rows:
            raise ValueError(f"duplicate original item: {identifier}")
        candidate = item["candidate_id"]
        if candidate is not None:
            if candidate in candidate_ids:
                raise ValueError(f"{identifier}: repeated original candidate {candidate}")
            candidate_ids.add(candidate)
        rule = item.get("qualitative_rule")
        if rule is not None and rule not in case["qualitative_rules"]:
            raise ValueError(f"{identifier}: qualitative rule was not registered")
        alternative, missing = alternative_price(item, case.get("valuation"))
        impact = None
        if not price:
            missing = "disclosed_price_missing_or_zero"
        elif alternative is not None:
            impact = abs(alternative - price) / abs(price)
        impacts[identifier] = impact
        a0, a_reason = decision(item["a0"], case["a0_original"]["valid"])
        b1, b_reason = decision(item["b1"], case["b1"]["valid"])
        if "unknown" in (a0, b1):
            pair = "unknown"
        elif a0 != b1:
            pair = "disagreement"
        elif a0 == "challenge":
            pair = "both_challenge"
        else:
            pair = "both_accept"
        material = rule is not None or (impact is not None and impact >= threshold)
        required = []
        if material and pair in {"both_challenge", "disagreement"}:
            required.append(pair)
        if material and item.get("verified_fact_error_ref"):
            required.append("verified_fact_error")
        rows[identifier] = {
            **item, "a0_decision": a0, "a0_reason": a_reason, "b1_decision": b1,
            "b1_reason": b_reason, "pair": pair, "alternative_price_krw": display(alternative),
            "impact_fraction": display(impact), "impact_unavailable_reason": missing,
            "mandatory_reasons": required,
        }
    # Compare exact rational impacts, including exact equality at a cutoff.
    order = sorted(rows, key=lambda i: (impacts[i] is None, -(impacts[i] or 0), i))
    return rows, order


def check_trials(case):
    originals = {}
    used_targets = set()
    runs = [case[role]["id"] for role in ("a0_original", "b1", "b2") if role in case]
    runs.extend(t["a0_run_id"] for t in case["trials"])
    if len(runs) != len(set(runs)):
        raise ValueError("distinct role and material runs must have distinct run IDs")
    for trial in case["trials"]:
        tid = trial["id"]
        if tid in originals:
            raise ValueError(f"duplicate trial ID: {tid}")
        originals[tid] = trial
        if ("b2" in trial) != ("b2" in case):
            raise ValueError(f"{tid}: B2 diagnostic and B2 annotations must be supplied together")
        permitted = {"no_false_alarm", "false_alarm"} if trial["kind"] == "control" else {"detected", "missed"}
        for role in ("a0", "b1", "b2"):
            if role in trial and trial[role]["outcome"] not in permitted | {"unscorable"}:
                raise ValueError(f"{tid}: incompatible outcome for {trial['kind']} / {role}")
        if "repeat_of" not in trial:
            key = trial["subtype"], trial["target_id"]
            if key in used_targets:
                raise ValueError(f"{tid}: repeated target must reference its original trial")
            used_targets.add(key)
    for trial in case["trials"]:
        if "repeat_of" in trial:
            original = originals.get(trial["repeat_of"])
            if (not original or "repeat_of" in original
                    or any(original[k] != trial[k] for k in ("subtype", "target_id", "kind"))):
                raise ValueError(f"{trial['id']}: invalid repeat reference")
            for role in ("b1", "b2"):
                if role in trial and original[role]["outcome"] != trial[role]["outcome"]:
                    raise ValueError(f"{trial['id']}: repeated trial must use its frozen B judgment")


def trial_results(case, role):
    signals = {i["subtype"]: {"M": 0, "J": 0} for i in case["items"] if i["subtype"]}
    controls = {"valid": 0, "any_false_alarm": 0, "a0_false_alarm": 0, "b_false_alarm": 0}
    records = []
    for trial in case["trials"]:
        a = trial["a0"]
        b = trial[role] if case[role]["valid"] else {
            "outcome": "unscorable", "reason": "invalid B submission"}
        outcomes = (a["outcome"], b["outcome"])
        valid = "unscorable" not in outcomes
        primary = "repeat_of" not in trial
        detectors = None
        if trial["kind"] == "realistic":
            counts = signals.setdefault(trial["subtype"], {"M": 0, "J": 0})
            if valid and primary:
                counts["M"] += 1
                counts["J"] += outcomes == ("missed", "missed")
        if trial["kind"] != "control" and valid:
            detectors = outcomes.count("detected")
        if trial["kind"] == "control" and valid and primary:
            controls["valid"] += 1
            controls["any_false_alarm"] += "false_alarm" in outcomes
            controls["a0_false_alarm"] += outcomes[0] == "false_alarm"
            controls["b_false_alarm"] += outcomes[1] == "false_alarm"
        records.append({"id": trial["id"], "kind": trial["kind"], "subtype": trial["subtype"],
                        "target_id": trial["target_id"], "repeat_of": trial.get("repeat_of"),
                        "a0_run_id": trial["a0_run_id"], "b_run_id": case[role]["id"],
                        "a0": a, "b": b, "valid_pair": valid, "detectors": detectors})
    for counts in signals.values():
        m, j = counts["M"], counts["J"]
        counts["signal"] = "unconfirmed" if m < 2 else ("promote" if 2 * j >= m else "baseline")
    return signals, controls, records


def variant(case, rows, order, role):
    signals, controls, records = trial_results(case, role)
    mandatory = [i for i in order if rows[i]["mandatory_reasons"]]
    others = [i for i in order if not rows[i]["mandatory_reasons"]]
    promoted = [i for i in others if rows[i]["pair"] == "both_accept"
                and signals.get(rows[i]["subtype"], {}).get("signal") == "promote"]
    promoted_set = set(promoted)
    canary_order = promoted + [i for i in others if i not in promoted_set]
    k = int(case["k"])
    return {"signals": signals, "controls": controls, "trials": records, "mandatory": mandatory,
            "baseline_extra": others[:k], "canary_extra": canary_order[:k], "promoted": promoted}


def compare_b_runs(primary, diagnostic, valid):
    new = diagnostic["canary_extra"]
    old = primary["canary_extra"]
    changed_trials = []
    n = 0
    for first, second in zip(primary["trials"], diagnostic["trials"], strict=True):
        a, b = first["b"]["outcome"], second["b"]["outcome"]
        if first["kind"] != "realistic" or first["repeat_of"] or "unscorable" in (a, b):
            continue
        n += 1
        if a != b:
            changed_trials.append(first["id"])
    return {"comparable_b_submissions": valid, "comparable_detection_targets": n,
            "changed_detection_trials": changed_trials, "list_changed": set(old) != set(new) if valid else None,
            "entered": [i for i in new if i not in old] if valid else None,
            "displaced": [i for i in old if i not in new] if valid else None}


def rank(case):
    errors = Draft202012Validator(SCHEMA).iter_errors(case)
    error = next(errors, None)
    if error:
        raise ValueError(f"{error.json_path}: {error.message}")
    check_trials(case)
    rows, order = original_rows(case)
    primary = variant(case, rows, order, "b1")
    if not case["a0_original"]["valid"]:
        status = "FAILED"
    elif any(not rows[i].get("resolved", False) for i in primary["mandatory"]):
        status = "HUMAN_REVIEW"
    elif any(i.get("blocking_info", False) for i in rows.values()):
        status = "PENDING_INFO"
    else:
        status = "READY"
    applicable = [r for r in rows.values() if r["candidate_id"] is not None]
    explicit = [r for r in applicable if r["a0_decision"] != "unknown"]
    both = [r for r in explicit if r["pair"] == "both_accept"]
    result = {"case_id": case["case_id"], "assignment_ref": case["assignment_ref"],
              "k": case["k"], "status": status, "a0_original": case["a0_original"], "b1": case["b1"],
              "items": list(rows.values()), "B1": primary,
              "candidate_counts": {"original": len(applicable), "a0_explicit": len(explicit),
                                   "both_accept": len(both), "both_accept_mapped": sum(
                                       r["subtype"] is not None for r in both)}}
    if "b2" in case:
        diagnostic = variant(case, rows, order, "b2")
        result.update(b2=case["b2"], B2=diagnostic, b_order_diagnostic=compare_b_runs(
            primary, diagnostic, case["b1"]["valid"] and case["b2"]["valid"]))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("input", metavar="INPUT.json", type=Path, nargs="?")
    group.add_argument("--schema", action="store_true")
    group.add_argument("--example", action="store_true")
    parser.add_argument("--blind-b1-dir", type=Path, help="Check B1 links against its saved response")
    parser.add_argument("--blind-b2-dir", type=Path, help="Check diagnostic B2 links with the paired B1")
    args = parser.parse_args(argv)
    if (args.blind_b1_dir or args.blind_b2_dir) and not args.input:
        parser.error("Blind run directories require a scored case JSON input")
    if args.schema:
        output = SCHEMA
    elif args.example:
        output = example()
    else:
        try:
            data = args.input.read_bytes()
            case = json.loads(data)
            output = rank(case)
            if args.blind_b1_dir or args.blind_b2_dir:
                from .a1_ranking_blind import link_responses
                output["blind_response_links"] = link_responses(case, args.blind_b1_dir, args.blind_b2_dir)
            output["input_sha256"] = hashlib.sha256(data).hexdigest()
        except (KeyError, TypeError, OSError, ValueError) as exc:
            parser.exit(2, f"{parser.prog}: {exc}\n")
    print(json.dumps(output, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
