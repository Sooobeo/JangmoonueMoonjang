"""Audit actual Responses evidence and score frozen rankings against two reference panels."""

import json

from scripts.current_b import OUT, ROOT, dump
from scripts.current_evaluate import (
    ARMS,
    CASES,
    DEV,
    VALIDATION,
    compare_formats,
    group_stats,
    original_grades,
    reads,
    sample_plan,
    summarize_case,
)
from scripts.current_label_formats import restricted_fields
from scripts.current_live import load
from scripts.current_selector import read_cases, state
from scripts.evaluate_a1 import KOREAN_GRADES

RESULTS = OUT / "official"


def audit_calls(rank):
    calls = []
    packets = []
    for stage, key in (("A1_LOOK", "lookup_run"), ("A1_SELECT", "decision_run")):
        folder = ROOT / rank[key]
        summary = load(folder / "summary.json")
        requests = sorted(folder.glob("*_request.json"))
        responses = sorted(folder.glob("*_response.json"))
        first = load(requests[0])
        raw = load(responses[-1])
        if (first["model"] != "gpt-6.1-terra" or first["reasoning"] != {"effort": "medium"} or
                summary["execution_status"] != "SUBMITTED" or raw["status"] != "completed" or
                raw["model"] != first["model"] or not raw["id"] or summary["condition"] != stage):
            raise ValueError(f"Official {stage} provenance mismatch for {rank['case']}")
        packet = json.loads(first["input"])
        # A1 receives additional_read in its second stage and a page catalog in its first.
        if restricted_fields(packet) - {"available_pages", "additional_read"}:
            raise ValueError("Reference fields found in selector input")
        packets.append(packet)
        calls.append({k: summary[k] for k in ("run_id", "model_calls", "elapsed_seconds", "input_tokens",
                                               "output_tokens", "format_repairs", "known_usage_cost_usd_standard_uncached")})
    lookup, selection = packets
    if rank.get("lookup_method") == "compact_catalog_recovery_v1":
        expected = [(row["item_id"], row["question"], state(row["a0"]), state(row["c"]),
                     row["a0"].get("reason", "")[:180], row["c"].get("reason", "")[:180],
                     selection["physical_page_index"][row["item_id"]]) for row in selection["original_items"]]
        observed = [(row["id"], row["question"], row["a0"], row["c"], row["a0_reason"], row["c_reason"],
                     row["pages"]) for row in lookup["item_catalog"]]
        if expected != observed or lookup["triz"] != selection["triz"]:
            raise ValueError("Compact lookup drifted from full original inputs")
    elif {k: v for k, v in lookup.items() if k != "available_pages"} != {
            k: v for k, v in selection.items() if k != "additional_read"}:
        raise ValueError("Initial and final selector packets disagree")
    raw_text = {"".join(value.split()) for value in selection["original_sources"].values()}
    additional = selection["additional_read"]
    if set(rank["lookup_pages"]) != set(additional) or len(additional) > 4:
        raise ValueError("Lookup evidence differs from the record")
    return {"calls": calls, "lookup_pages": list(additional),
            "new_text_pages": [k for k, v in additional.items() if "".join(v.split()) not in raw_text]}


def cohorts(rows):
    # group_stats separately supports the original proxy stopwatch. The persona
    # joins the measured operating lists by their exact hashes in its own report.
    for row in rows:
        for arm in ARMS:
            row[arm]["operating"]["proxy_seconds"] = None
    return {group: group_stats([row for row in rows if row["case"] in cases])
            for group, cases in (("development", DEV), ("validation", VALIDATION))
            if any(row["case"] in cases for row in rows)}


def verified_labels():
    return {**read_cases(RESULTS / "dev_labels.json"),
            **read_cases(OUT / "validation_roles/official/labels_triz.json")}


def run():
    labels = verified_labels()
    baseline = load(OUT / "protocol.json")
    rows, secondary, panels, routed = [], [], {}, []
    for case in CASES:
        rank, digest = reads(OUT / "ranking/terra" / (case + ".json"))
        raw = audit_calls(rank)
        if rank["triz"] != labels[case].get("triz", []):
            raise ValueError(f"{case} rank used a different TRIZ condition")
        grades, ref = original_grades(case)
        row = summarize_case(case, rank, grades, baseline["k"], "TERRA")
        row.update(rank_sha256=digest, reference_sha256=ref, evidence=raw)
        rows.append(row)
        decisions = {v["item_id"]: v for v in rank["ai"]["items"]}
        for item in labels[case]["items"]:
            key = item["item_id"]
            if key in rank["ai"]["operational"]:
                a, c = item["a0"], item["c"]
                routed.append({"case": case, "item": key, "type": item["question_type"], "a0": state(a),
                               "c": state(c), "comparable": a.get("comparable", True) and c.get("comparable", True),
                               "reason": decisions[key]["reason"] if key in decisions else "mandatory"})
        if case in VALIDATION:
            plain = load(OUT / "ranking/terra_without_triz" / (case + ".json"))
            if plain["triz"] or plain["rule"] != rank["rule"] or plain["mandatory"] != rank["mandatory"]:
                raise ValueError(f"{case} unmatched no-signal condition")
            plain_result = summarize_case(case, plain, grades, baseline["k"], "TERRA")
            row["without_triz"] = {"same_decision_run": plain["decision_run"] == rank["decision_run"],
                                   "fixed_k": plain_result["fixed_k"]["ai"],
                                   "operational": plain_result["ai"]["operating"]["items"]}
            terra, terra_ref = reads(OUT / "validation/terra" / (case + ".json"))
            if terra["grader"] != "TERRA_PROXY" or set(grades) != {i["item_id"] for i in terra["items"]}:
                raise ValueError("Terra secondary reference is incomplete")
            tg = {i["item_id"]: KOREAN_GRADES[i["grade"]] for i in terra["items"]}
            alt = summarize_case(case, rank, tg, baseline["k"], "TERRA")
            alt.update(reference_sha256=terra_ref, rank_sha256=digest)
            secondary.append(alt)
            panels[case] = {"n": len(tg), "exact_matches": sum(tg[k] == grades[k] for k in tg),
                            "terra_repeat": terra["repeat_n"], "terra_repeat_disagreements": terra["initial_disagreements"],
                            "terra_material": sorted(k for k in tg if tg[k] == "material"),
                            "frozen_material": sorted(k for k in tg if grades[k] == "material")}
    result = {"model": "gpt-6.1-terra", "effort": "medium", "additional_k": baseline["k"],
              "primary_reference": "Frozen Codex adjudication, independent from the official selectors",
              "secondary_reference": "Separately blinded Terra re-rating. Grader and selector share a model.",
              "primary": cohorts(rows), "rows": rows, "secondary": cohorts(secondary), "secondary_rows": secondary,
              "reference_agreement": panels, "ai_operating_roles": routed}
    dump(RESULTS / "metrics.json", result)
    sample = {}
    for panel in ("primary", "secondary"):
        score = result[panel]["validation"]
        valid = score["valid_concordance_pairs"]
        observed = score["expected_cases"]
        analysis = sample_plan(valid, observed)
        effect = next(row for row in analysis["assumptions"] if row["assumed_standardized_paired_effect"] == .8)
        sample[panel] = {"validation_valid": valid, "validation_observed": observed,
                         "eligibility_exact_95_interval": analysis["validation_exact_95_percent_eligibility_interval"],
                         **effect}
    dump(RESULTS / "enrollment/planning.json", {"target_alpha_two_sided": .05, "power": .8,
         "enrollment_probability_of_attaining_target": .9, "effect_assumption": .8, "panels": sample,
         "unopened_legacy_issuers": 8, "final_outcomes_opened": 0,
         "scope": "Planning. Filed-company eligibility precedes outcome-class eligibility. Four validation issuers "
                  "are retired. The six exposed development and validation issuers are excluded from confirmation."})
    formats = RESULTS / "formats/rankings.json"
    if formats.is_file():
        compare_formats(baseline["k"], formats, RESULTS)
    return result


if __name__ == "__main__":
    run()
