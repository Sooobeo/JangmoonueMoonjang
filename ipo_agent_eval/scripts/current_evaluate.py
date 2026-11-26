"""Incremental paired evaluation of six disclosed development and validation cases."""

import argparse
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from hashlib import sha256
from statistics import mean, stdev
from subprocess import SubprocessError

from jsonschema import ValidationError
from scipy.optimize import brentq
from scipy.stats import beta, binom, nct, t

from scripts.current_b import OUT, ROOT, dump
from scripts.evaluate_a1 import GRADES, KOREAN_GRADES

DEV = ("HDMS", "MELCON")
VALIDATION = ("GIGAVIS", "TRUEN", "MANYO", "PHILENERGY")
CASES = DEV + VALIDATION
ARMS = ("rule", "ai")
COMPARISON = OUT / "comparison"


def reads(path):
    data = path.read_bytes()
    return json.loads(data), sha256(data).hexdigest()


def limits(values):
    return [min(values), max(values)] if values else None


def original_grades(case):
    if case in DEV:
        data, digest = reads(OUT / "grading/rubrics.json")
        rows = data["cases"][case]["items"]
        pairs = [(row["id"], row["grade"]) for row in rows]
    else:
        data, digest = reads(OUT / "validation/codex" / f"{case}.json")
        if data["case"] != case or data["grader"] != "CODEX_PROXY":
            raise ValueError(f"Unexpected validation reference for {case}")
        pairs = [(row["item_id"], KOREAN_GRADES.get(row["grade"], row["grade"])) for row in data["items"]]
    grades = dict(pairs)
    if not grades or len(grades) != len(pairs) or not set(grades.values()) <= GRADES:
        raise ValueError(f"Invalid reference grades for {case}")
    return grades, digest


def grade_groups(grades):
    return [{key for key, grade in grades.items() if grade in selected} for selected in
            ({"material"}, {"acceptable", "nonmaterial"}, {"deferred"})]


def priority_key(arm, row):
    if arm == "ai":
        score = row["priority"]
        if type(score) is not int or not 1 <= score <= 100 or str(score) != row["tie_key"]:
            raise ValueError(f"Invalid AI priority for {row['item_id']}")
        return -score
    match = re.fullmatch(r"\(([012]), (True|False), Decimal\('([^']+)'\)\)", row["tie_key"])
    if not match:
        raise ValueError(f"Invalid rule priority for {row['item_id']}")
    return int(match[1]), match[2] == "True", Decimal(match[3])


def concordance(order, material, other):
    pair_count = len(material) * len(other)
    if not pair_count:
        return None
    correct = sum((1 if order[a] < order[b] else 0.5 if order[a] == order[b] else 0)
                  for a in material for b in other)
    return {"score": correct / pair_count, "pairs": pair_count, "weighted_correct": correct}


def outcome(listed, material, pending):
    return {"count": len(listed), "material_found": sorted(listed & material),
            "material_missed": sorted(material - listed), "pending_outside": sorted(pending - listed),
            "recall": len(listed & material) / len(material) if material else None,
            "miss_count_bounds": [len(material - listed), len((material | pending) - listed)]}


def missed_delta(listed, material, pending):
    rule, ai = (listed[arm] for arm in ARMS)
    delta = len(material - rule) - len(material - ai)
    return {"rule_minus_ai": delta,
            "pending_bounds": [delta - len((rule - ai) & pending), delta + len((ai - rule) & pending)],
            "newly_missed_by_ai": sorted((rule - ai) & material),
            "newly_found_by_ai": sorted((ai - rule) & material)}


def pending_rank_bounds(orders, material, pending):
    """Exact tied-rank bounds for a shared assignment of every unresolved item."""
    from itertools import accumulate, groupby

    n = len(orders["rule"])
    weights = {}
    for arm, order in orders.items():
        # Each positive earns one point per item behind it and half for a tie.
        weights[arm] = {}
        ahead = 0
        for _, group in groupby(sorted(order, key=order.get), key=order.get):
            keys = list(group)
            score = n - ahead - (len(keys) + 1) / 2
            weights[arm].update(dict.fromkeys(keys, score))
            ahead += len(keys)
    weights["delta"] = {k: weights["ai"][k] - weights["rule"][k] for k in orders["rule"]}
    result = {}
    assignments = 0
    for name, weight in weights.items():
        base = sum(weight[k] for k in material)
        free = sorted(weight[k] for k in pending)
        extrema = []
        for count, (lo, hi) in enumerate(zip(accumulate(free, initial=0),
                                              accumulate(reversed(free), initial=0))):
            m = len(material) + count
            if not 0 < m < n:
                continue
            if name == "delta":
                assignments += math.comb(len(free), count)
            # Within-positive comparisons contribute one point per unordered pair.
            offset = 0 if name == "delta" else m * (m - 1) / 2
            extrema.extend((base + value - offset) / (m * (n - m)) for value in (lo, hi))
        result[name] = limits(extrema)
    return result, assignments


def summarize_case(case, ranking, grades, k, expected_condition="CODEX_PROXY"):
    if ranking["case"] != case or ranking["selector_condition"] != expected_condition:
        raise ValueError(f"Unexpected selector record for {case}")
    common = ranking["mandatory"]
    mandatory = set(common)
    population = set(grades)
    optional = population - mandatory
    if ranking["common_item_count"] != len(population) or not mandatory <= population or len(common) != len(mandatory):
        raise ValueError(f"Frozen item population or mandatory IDs differ for {case}")
    material, other, pending = grade_groups(grades)
    orders = {}
    ranks = {}
    op_lists = {}
    arm_out = {}
    for arm in ARMS:
        data = ranking[arm]
        rows = data["items"]
        ids = [row["item_id"] for row in rows]
        if set(ids) != optional or len(ids) != len(optional):
            raise ValueError(f"{case} {arm} is not a complete unique rank")
        priorities = {row["item_id"]: priority_key(arm, row) for row in rows}
        if ids != sorted(ids, key=lambda key: (priorities[key], key)):
            raise ValueError(f"{case} {arm} priority or ID tie break is inconsistent")
        eligible = [row["item_id"] for row in rows if row["eligible"]]
        if (data["fixed_k"] != common + ids[:k] or data["operational"] != common + eligible[:k]
                or data["waiting"] != eligible[k:]):
            raise ValueError(f"{case} {arm} allocation does not match registered K")
        if arm == "ai" and any(row["eligible"] != (row["action"] == "사람 검토") for row in rows):
            raise ValueError(f"{case} AI eligibility does not match proposal")
        ranks[arm] = ids
        orders[arm] = priorities
        op_lists[arm] = set(data["operational"])
        status = {key: "transferred" for key in op_lists[arm]}
        status.update({key: "waiting" for key in data["waiting"]})
        for row in rows:
            disposition = ("not_routed" if arm == "rule" else
                           "request" if row["action"] == "자료 요청" else "archived")
            status.setdefault(row["item_id"], disposition)
        arm_out[arm] = {"concordance": concordance(priorities, material & optional, other & optional),
                        "operating": {**outcome(op_lists[arm], material, pending),
                                      "items": data["operational"], "rate": len(op_lists[arm]) / len(grades),
                                      "mandatory": len(mandatory), "additional": len(op_lists[arm] - mandatory),
                                      "waiting": data["waiting"],
                                      "requests": sorted(key for key, value in status.items() if value == "request"),
                                      "archived": sorted(key for key, value in status.items() if value == "archived"),
                                      "not_routed": sorted(key for key, value in status.items() if value == "not_routed"),
                                      "missed_status": {key: status[key] for key in sorted(material - op_lists[arm])}}}

    pending_optional = sorted(pending & optional)
    bounds, assignments = pending_rank_bounds(orders, material & optional, pending_optional)
    for arm in ARMS:
        arm_out[arm]["concordance_pending_bounds"] = bounds[arm]
    primary = [arm_out[arm]["concordance"] for arm in ARMS]
    concordance_delta = primary[1]["score"] - primary[0]["score"] if all(primary) else None

    fixed_by_k = {}
    for budget in range(min(1, len(optional)), len(optional) + 1):
        lists = {arm: mandatory | set(ranks[arm][:budget]) for arm in ARMS}
        fixed_by_k[str(budget)] = {
            **{arm: {**outcome(lists[arm], material, pending), "items": common + ranks[arm][:budget]} for arm in ARMS},
            "difference": missed_delta(lists, material, pending),
        }
    return {"case": case, "status": "COMPARED", "cohort": "development" if case in DEV else "validation",
            "total_items": len(population), "mandatory": common, "material": sorted(material), "pending": sorted(pending),
            "known_nonmaterial": sorted(other), "optional_material": sorted(material & optional),
            "optional_nonmaterial": sorted(other & optional), "optional_pending": pending_optional,
            "primary_exclusion_reason": None if concordance_delta is not None else
            ("no_known_material_outside_mandatory" if not material & optional else "no_known_nonmaterial_outside_mandatory"),
            **arm_out, "concordance_delta_ai_minus_rule": concordance_delta,
            "concordance_delta_pending_bounds": bounds["delta"], "valid_pending_assignments": assignments,
            "fixed_k": fixed_by_k[str(min(k, len(optional)))], "fixed_curve_by_k": fixed_by_k,
            "operating_difference": {**missed_delta(op_lists, material, pending),
                                     "transfer_change_ai_minus_rule": len(op_lists["ai"]) - len(op_lists["rule"])},
            "triz": ranking["triz"], "selector_seconds": ranking["selector_seconds"],
            "selector_runs": [ranking["lookup_run"], ranking["decision_run"]],
            "human_minutes": None}


def followup_source(case):
    from scripts.current_selector import original_inputs

    index, pages, _, _ = original_inputs(case)
    if case in DEV:
        frozen, _ = reads(ROOT / "data/a1_pilot" / case / "operator/original_items.json")
        labels = {row["id"]: row["label"] for row in frozen["items"]}
        pdf_sha = frozen["source_sha256"]
    else:
        freeze, _ = reads(OUT / "validation/freeze.json")
        labels = {row["item_id"]: row["question"] for row in freeze[case]["items"]}
        pdf_sha = freeze[case]["sha256"]
    if set(index) != set(labels):
        raise ValueError(f"Review question roster differs for {case}")
    return index, pages, labels, pdf_sha


def timed_reviews(compared):
    from scripts.current_live import S, arr, obj
    from scripts.current_proxy import ask_proxy

    citation = obj({"physical_page": {"type": "integer"}, "quote": S})
    schema = obj({"status": {"type": "string", "enum": ["verified_issue", "adequately_supported", "unresolved"]},
                  "finding": S, "citations": {**arr(citation), "minItems": 1}, "open_question": S})
    jobs = {}
    failed = []
    for result in compared:
        if result["status"] != "COMPARED":
            continue
        case = result["case"]
        queue = {item for arm in ARMS for item in result[arm]["operating"]["items"]}
        if not queue:
            continue
        try:
            index, pages, labels, pdf_sha = followup_source(case)
        except (KeyError, ValueError, RuntimeError, OSError) as exc:
            failed.extend({"case": case, "item_id": item, "status": "SOURCE_UNAVAILABLE", "error": str(exc),
                           "human_minutes": None} for item in sorted(queue))
            continue
        for item in queue:
            authorized = {p: pages[p] for p in index[item] if p in pages}
            if not authorized:
                failed.append({"case": case, "item_id": item, "status": "SOURCE_UNAVAILABLE",
                               "error": "No authorized original pages", "human_minutes": None})
            else:
                jobs[case, item] = (labels[item], authorized, pdf_sha)

    def review_one(job):
        case, item = job
        question, pages, pdf_sha = jobs[job]

        def verify(answer):
            def normalized(text):
                return "".join(text.split())

            for c in answer["citations"]:
                page = c["physical_page"]
                quote = normalized(c["quote"])
                if page not in pages or not quote or quote not in normalized(pages[page]):
                    raise ValueError("Use an exact text quotation from a supplied original physical page.")

        payload = {"question": question, "authorized_original_pages": {str(k): v for k, v in pages.items()}}
        prompt = ("IPO 최초 신고서의 한 검토 항목을 확인한다. 제공된 페이지로만 답한다. 확인된 사실과 남은 한계를 한국어로 적고, "
                  "목록의 출처를 추정하지 않는다. 표·본문에서 확인된 원문 한 줄 이상을 그대로 인용한다. "
                  "중요한 근거가 없으면 미해결을 선택하고 필요한 자료를 쓴다.")
        try:
            res = ask_proxy(case, f"OP_{item}", prompt, payload, schema, 1000, verify)
            return {"case": case, "item_id": item, "status": "CODEX_PROXY_REVIEWED",
                    "original_pdf_sha256": pdf_sha, "physical_pages": list(pages),
                    "answer": res["answer"], "proxy_seconds": res["summary"]["elapsed_seconds"],
                    "evidence_dir": res["evidence_dir"], "human_minutes": None}
        except (ValueError, RuntimeError, OSError, SubprocessError, ValidationError) as exc:
            return {"case": case, "item_id": item, "status": "FAILED", "error": str(exc), "human_minutes": None}

    ordered = sorted(jobs, key=lambda key: sha256(f"arm-masked-v1:{key[0]}:{key[1]}".encode()).digest())
    with ThreadPoolExecutor(max_workers=4) as pool:
        return failed + list(pool.map(review_one, ordered))


def set_timing(result, followups):
    for arm in ARMS:
        branch = result[arm]["operating"]
        ids = branch["items"]
        matched = [followups.get((result["case"], item)) for item in ids]
        done = [row for row in matched if row and row["status"] == "CODEX_PROXY_REVIEWED"]
        branch["proxy_seconds"] = round(sum(row["proxy_seconds"] for row in done), 3) if len(done) == len(ids) else None
        branch["proxy_items_timed"] = len(done)
        branch["human_minutes"] = None


def selector_usage(result):
    runs = []
    for relative in result["selector_runs"]:
        run, _ = reads(ROOT / relative / "result.json")
        if run["summary"]["condition"] != "CODEX_PROXY":
            raise ValueError("Selector evidence is not a proxy run")
        runs.append(run["summary"])
    usages = [usage for run in runs for usage in run["turn_usage"] if usage is not None]
    totals = {key: sum(usage.get(key, 0) for usage in usages) for key in
              ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")}
    decision, _ = reads(ROOT / result["selector_runs"][1] / "request.json")
    sources = decision["input"]["original_sources"]
    reads_requested = decision["input"]["additional_read"]
    if list(reads_requested) != result["lookup_pages"]:
        raise ValueError("Requested pages differ from the selector input evidence")
    originals = {ref: "".join(value.split()) for ref, value in sources.items()}

    def source_page(ref):
        match = re.fullmatch(r"(?:PDF-|[A-Z]+-P)0*([1-9][0-9]*)", ref)
        return int(match[1]) if match else None

    lookup = []
    for ref, value in reads_requested.items():
        text = "".join(value.split())
        exact = sorted(key for key, original in originals.items() if original == text)
        aliases = sorted(key for key in originals if source_page(key) == source_page(ref))
        lookup.append({"requested_ref": ref, "preexisting_same_page_aliases": aliases,
                       "preexisting_exact_text_refs": exact, "net_new_full_normalized_text": not exact})
    return {"logged_proxy_turns": len(usages), "usage": totals, "billed_dollars": None,
            "requested_pdf_pages": result["lookup_pages"], "requested_page_evidence": lookup,
            "net_new_text_pages": [row["requested_ref"] for row in lookup if row["net_new_full_normalized_text"]]}


def group_stats(rows):
    compared = [row for row in rows if row["status"] == "COMPARED"]
    values = [row["concordance_delta_ai_minus_rule"] for row in compared
              if row["concordance_delta_ai_minus_rule"] is not None]
    compared_primary = [row for row in compared if row["concordance_delta_ai_minus_rule"] is not None]
    ci = None
    if len(values) > 1:
        margin = t.ppf(.975, len(values) - 1) * stdev(values) / math.sqrt(len(values))
        ci = [mean(values) - margin, mean(values) + margin]
    bounds = [row["concordance_delta_pending_bounds"] for row in compared_primary]
    fixed = {arm: {"material_missed": sum(len(row["fixed_k"][arm]["material_missed"]) for row in compared),
                   "material_found": sum(len(row["fixed_k"][arm]["material_found"]) for row in compared)} for arm in ARMS}
    fixed_pending_bounds = [row["fixed_k"]["difference"]["pending_bounds"] for row in compared]
    operating_pending_bounds = [row["operating_difference"]["pending_bounds"] for row in compared]
    operating = {}
    for arm in ARMS:
        units = [row[arm]["operating"] for row in compared]
        transfers = sum(row["count"] for row in units)
        denominator = sum(row["total_items"] for row in compared)
        operating[arm] = {"transfers": transfers, "total_items": denominator,
                          "transfer_rate": transfers / denominator if denominator else None,
                          "wait": sum(len(row["waiting"]) for row in units), "requests": sum(len(row["requests"]) for row in units),
                          "material_missed": sum(len(row["material_missed"]) for row in units),
                          "proxy_seconds": round(sum(row["proxy_seconds"] for row in units), 3)
                          if units and all(row["proxy_seconds"] is not None for row in units) else None}
    additional = sum(len(row["operating_difference"]["newly_missed_by_ai"]) for row in compared)
    return {"expected_cases": len(rows), "complete_pairs": len(compared), "valid_concordance_pairs": len(values),
            "primary_equal_issuer_ai_minus_rule": mean(values) if values else None,
            "descriptive_95_t_interval": ci,
            "pending_bounds_on_primary_matched_cohort": [mean(v[0] for v in bounds), mean(v[1] for v in bounds)] if bounds else None,
            "known_material": sum(len(row["material"]) for row in compared), "fixed_same_k": fixed, "operating": operating,
            "fixed_same_k_miss_delta_pending_bounds": [sum(v[0] for v in fixed_pending_bounds), sum(v[1] for v in fixed_pending_bounds)]
            if compared else None,
            "operating_miss_delta_pending_bounds": [sum(v[0] for v in operating_pending_bounds), sum(v[1] for v in operating_pending_bounds)]
            if compared else None,
            "ai_newly_missed_material_items": [key for row in compared for key in row["operating_difference"]["newly_missed_by_ai"]],
            "known_operating_additional_miss_ceiling_satisfied": additional == 0 if compared else None,
            "human_minutes": None}


def paired_power(n, effect):
    critical = t.ppf(.975, n - 1)
    shift = effect * math.sqrt(n)
    return float(nct.sf(critical, n - 1, -shift) + nct.sf(critical, n - 1, shift))


def validation_reference_feasibility():
    b_path = OUT / "validation/b.json"
    b = reads(b_path)[0] if b_path.exists() else {}
    rows = []
    for case in VALIDATION:
        try:
            grades, _ = original_grades(case)
        except OSError:
            continue
        material, other, pending = grade_groups(grades)
        mandatory = set(b[case]["mandatory"]) if case in b else set()
        rows.append({"case": case, "material_outside_mandatory": len(material - mandatory),
                     "known_nonmaterial_outside_mandatory": len(other - mandatory),
                     "pending_outside_mandatory": len(pending - mandatory), "mandatory_table_present": case in b,
                     "primary_classes_present": bool(material - mandatory and other - mandatory)})
    return rows


def sample_plan(valid, observed):
    rate = valid / observed if observed else None
    interval = None if not observed else [float(beta.ppf(.025, valid, observed - valid + 1)) if valid else 0,
                                          float(beta.ppf(.975, valid + 1, observed - valid)) if valid < observed else 1]
    assumptions = [1.0, .8, .7] + ([rate] if rate not in (None, 0, .7, .8, 1.0) else [])
    options = []
    for effect in (.5, .6, .7, .8, 1.0, 1.2):
        minimum = next(n for n in range(3, 501) if paired_power(n, effect) >= .8)
        options.append({"assumed_standardized_paired_effect": effect, "valid_pairs_needed": minimum,
                        "power_if_all_eight_valid": paired_power(8, effect),
                        "total_enrollment_at_90_percent_probability_of_enough_valid": {
                            str(q): next(n for n in range(minimum, 601) if binom.sf(minimum - 1, n, q) >= .9)
                            for q in assumptions}})
    return {"reserved_outcomes_opened": 0, "reserved_count": 8, "alpha_two_sided": .05, "target_power": .8,
            "validation_valid": valid, "validation_examined": observed, "validation_observed_rate": rate,
            "validation_exact_95_percent_eligibility_interval": interval,
            "eight_valid_minimum_detectable_standardized_paired_effect": brentq(lambda d: paired_power(8, d) - .8, .01, 2),
            "assumptions": options, "notes": "Power planning only. Validation selection is fixed and modest. No efficacy inference."}


def compare_formats(k, path=OUT / "formats/rankings.json", destination=COMPARISON):
    if not path.exists():
        return
    source, digest = reads(path)
    conditions = ("L1", "L2", "L3", "L3-rule")
    rows = []
    for case in CASES:
        data = source["cases"].get(case)
        if not data or any(arm not in data for arm in conditions):
            rows.append({"case": case, "status": "UNEVALUABLE", "reason": "Missing one or more format outputs"})
            continue
        grades, reference = original_grades(case)
        material, _, pending = grade_groups(grades)
        mandatory = data["mandatory"]
        optional = set(grades) - set(mandatory)
        if not set(mandatory) <= set(grades) or len(mandatory) != len(set(mandatory)):
            raise ValueError(f"Unexpected mandatory items for {case} format comparison")
        result = {"case": case, "status": "COMPARED", "reference_sha256": reference,
                  "known_material": sorted(material), "pending": sorted(pending), "items": len(grades)}
        for arm in conditions:
            keys = [row["item_id"] for row in data[arm]["items"]]
            if len(keys) != len(optional) or set(keys) != optional or data[arm]["fixed_k"] != mandatory + keys[:k]:
                raise ValueError(f"Unexpected item population or K for {case} {arm}")
            selected = data[arm]["fixed_k"]
            result[arm] = {"items": selected, **outcome(set(selected), material, pending)}
        rows.append(result)
    cohorts = {}
    for name, cases in (("development", DEV), ("validation", VALIDATION)):
        available = [row for row in rows if row["case"] in cases and row["status"] == "COMPARED"]
        total = sum(len(row["known_material"]) for row in available)
        arms = {}
        for arm in conditions:
            found = sum(len(row[arm]["material_found"]) for row in available)
            recall_values = [row[arm]["recall"] for row in available if row[arm]["recall"] is not None]
            arms[arm] = {"known_material_found": found, "known_material_missed": total - found,
                         "known_material_recall_micro": found / total if total else None,
                         "known_material_recall_equal_issuer": mean(recall_values) if recall_values else None,
                         "pending_selected": sum(len(set(row[arm]["items"]) & set(row["pending"])) for row in available),
                         "pending_outside": sum(len(row[arm]["pending_outside"]) for row in available)}
        cohorts[name] = {"paired_cases": len(available), "expected_cases": len(cases), "known_material": total, **arms}
    dump(destination / "format_k1.json", {"scope": "Exploratory separate from H1", "k": k,
         "ranks_sha256": digest, "source_scope": source["assessment_scope"],
         "model_calls_submitted": source["model_calls_submitted"], "rows": rows, "cohorts": cohorts})


def run(measure):
    protocol, _ = reads(OUT / "protocol.json")
    results = []
    output_path = COMPARISON / "operating_proxy_reviews.json"
    previous = reads(output_path)[0] if output_path.exists() else []
    for case in CASES:
        path = OUT / "ranking/proxy" / f"{case}.json"
        if not path.exists():
            results.append({"case": case, "status": "PENDING_RANK", "reason": "No complete ranked pair on disk"})
            continue
        try:
            grades, reference = original_grades(case)
            ranking, rank_sha = reads(path)
            result = summarize_case(case, ranking, grades, protocol["k"])
            result.update(reference_sha256=reference, rank_sha256=rank_sha)
            result["lookup_pages"] = ranking["lookup_pages"]
            result["selector_usage"] = selector_usage(result)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            result = {"case": case, "status": "UNEVALUABLE", "reason": str(exc)}
        results.append(result)
    measured = timed_reviews(results) if measure else []
    followups = {(row["case"], row["item_id"]): row for row in [*previous, *measured]}
    if measure:
        dump(output_path, list(followups.values()))
    for result in results:
        if result["status"] == "COMPARED":
            set_timing(result, followups)
    validation = group_stats([row for row in results if row["case"] in VALIDATION])
    feasibility = validation_reference_feasibility()
    complete = [row for row in feasibility if row["mandatory_table_present"]]
    technical_path = COMPARISON / "technical_attempts.json"
    technical = reads(technical_path)[0] if technical_path.exists() else []
    report = {"protocol": protocol["version"], "scope": "CODEX_PROXY_DEVELOPMENT_AND_VALIDATION", "k": protocol["k"],
              "rows": results, "development": group_stats([row for row in results if row["case"] in DEV]),
              "validation": validation, "validation_reference_feasibility": feasibility,
              "separate_selector_technical_attempts": technical,
              "sample_plan": sample_plan(sum(row["primary_classes_present"] for row in complete), len(complete))}
    dump(COMPARISON / "metrics.json", report)
    compare_formats(protocol["k"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", action="store_true", help="Run isolated Codex original-page follow-up on the operating lists")
    args = parser.parse_args()
    report = run(args.review)
    for row in report["rows"]:
        print(row["case"], row["status"], row.get("reason", ""))
