"""Apply the pilot's conditional deferral gate and compare whole-company queues."""

from concurrent.futures import ThreadPoolExecutor

from scripts.current_b import OUT, ROOT, dump
from scripts.current_evaluate import (
    VALIDATION,
    concordance,
    grade_groups,
    original_grades,
    outcome,
    priority_key,
)
from scripts.current_live import load
from scripts.current_official_report import RESULTS, audit_calls, verified_labels
from scripts.current_selector import grade_free_case


def run():
    metrics = load(RESULTS / "metrics.json")
    h1 = metrics["primary"]["validation"]
    eligible = {}
    labels = verified_labels()
    for case in VALIDATION:
        full = load(OUT / "ranking/terra" / (case + ".json"))
        candidates = [s["item_id"] for s in full["triz"] if s["item_id"] not in full["mandatory"] and
                      set(s["role_checks"]) == {"A0", "C"} and all(
                          set(checks) == {"original_reproduced", "format_preserved", "direction_responsive"}
                          and all(checks.values()) for checks in s["role_checks"].values())]
        if candidates:
            eligible[case] = sorted(candidates)
    run_h2 = h1["known_operating_additional_miss_ceiling_satisfied"] and h1["complete_pairs"] == len(VALIDATION)
    plan = {"eligible": eligible, "h1_safety_gate": run_h2, "mandatory_excluded": True,
            "population": list(VALIDATION), "source": "official/recovery_protocol.md"}
    plan_file = RESULTS / "deferral/eligibility.json"
    if plan_file.exists() and load(plan_file) != plan:
        raise ValueError("Frozen hold roster differs")
    dump(plan_file, plan)

    def compare(case):
        held = set(eligible[case])
        full = load(OUT / "ranking/terra" / (case + ".json"))
        plain = load(OUT / "ranking/terra_without_triz" / (case + ".json"))
        reduced = grade_free_case(case, labels[case], held_items=held, compact_lookup=True)
        hold_evidence = audit_calls(reduced)
        reference, _ = original_grades(case)
        material, known, pending = grade_groups(reference)
        assessed = {}
        trials = load(OUT / "validation_roles/official/triz/audit.json")
        directories = []
        for key in sorted(held):
            directories.append(trials["eligibility"][key]["screen_run"])
            directories.extend(trials["results"][key][role][form]["evidence_dir"]
                               for role in ("A0", "C") for form in ("original", "format", "directional"))
        trigger = [load(ROOT / path / "summary.json") for path in directories]
        trigger_cost = sum(r["known_usage_cost_usd_standard_uncached"] for r in trigger)
        trigger_seconds = sum(r["elapsed_seconds"] for r in trigger)
        for name, rank in (("full_without_signal", plain), ("full_with_signal", full), ("hold_with_signal", reduced)):
            ai = rank["ai"]
            order = {r["item_id"]: (0, priority_key("ai", r)) for r in ai["items"]}
            if name == "hold_with_signal":
                order.update({r["item_id"]: (1, priority_key("rule", r)) for r in full["rule"]["items"]
                              if r["item_id"] in held})
            optional = set(reference) - set(full["mandatory"])
            if set(order) != optional or full["mandatory"] != rank["mandatory"]:
                raise ValueError(f"{case}/{name}: missing original item or mandatory")
            queue = sorted(order, key=lambda k: (order[k], k))
            if full["mandatory"] + queue[:1] != ai["fixed_k"]:
                raise ValueError("Top-K not reproducible")
            summaries = [load(ROOT / rank[field] / "summary.json") for field in ("decision_run", "lookup_run")]
            selector_cost = sum(r["known_usage_cost_usd_standard_uncached"] for r in summaries)
            assessed[name] = {"rank_order": queue, "concordance": concordance(order, material & optional, known & optional),
                              "fixed_k": {"items": ai["fixed_k"], **outcome(set(ai["fixed_k"]), material, pending)},
                              "operating": {"items": ai["operational"], **outcome(set(ai["operational"]), material, pending)},
                              "selector_seconds": rank["selector_seconds"],
                              "selector_estimated_usd": selector_cost,
                              "selector_plus_eligible_trigger_estimated_usd": selector_cost + (
                                  trigger_cost if name != "full_without_signal" else 0),
                              "selector_plus_eligible_trigger_summed_seconds": rank["selector_seconds"] + (
                                  trigger_seconds if name != "full_without_signal" else 0),
                              "decision_run": rank["decision_run"], "lookup_run": rank["lookup_run"]}
        return {"case": case, "held": sorted(held), "held_grades": {k: reference[k] for k in sorted(held)},
                "trigger": {"evidence_dirs": directories, "model_calls": sum(r["model_calls"] for r in trigger),
                            "estimated_usd": trigger_cost, "summed_seconds": trigger_seconds,
                            "scope": "matched eligible-item alignment and perturbations. Setup time unavailable."},
                "additional_held_material": sorted(material & held), "evidence": hold_evidence, "arms": assessed}

    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(compare, eligible if run_h2 else []))
    report = {**plan, "comparisons": rows}
    dump(RESULTS / "deferral/comparison.json", report)
    return report


if __name__ == "__main__":
    run()
