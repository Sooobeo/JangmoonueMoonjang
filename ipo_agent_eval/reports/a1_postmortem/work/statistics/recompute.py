"""Reproduce the post hoc tables without model calls or changes to the frozen experiment."""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from fractions import Fraction
from itertools import product
from pathlib import Path
from statistics import mean


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
BASE = ROOT / "reports/a1_main/v1"
ROSTER = ROOT / "reports/a1_current/official/enrollment_expansion/roster.json"
MATERIAL, ACCEPT, MINOR, UNKNOWN = "중대 쟁점", "수용 가능", "비중대 쟁점", "판정 유보"
ARMS = ("rule", "ai")
SIGN = {"up": "AI 상승", "down": "AI 하락", "tie": "동률"}


def read(path):
    return json.loads(path.read_bytes())


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def concordance(ranked, grades):
    position = {row["item_id"]: i for i, row in enumerate(ranked)}
    ties = {row["item_id"]: row["tie_key"] for row in ranked}
    material = [k for k in position if grades[k] == MATERIAL]
    comparator = [k for k in position if grades[k] in (ACCEPT, MINOR)]
    if not (material and comparator):
        return None
    pair_points = [
        Fraction(1, 2) if ties[m] == ties[n] else int(position[m] < position[n])
        for m, n in product(material, comparator)
    ]
    return sum(pair_points, Fraction(0)) / len(pair_points)


def replay_tiebreak(ranking):
    """Preserve baseline budget and eligibility. AI may choose only among equal top rule scores."""
    rule = ranking["rule"]
    rule_eligible = [r for r in rule["items"] if r["eligible"]]
    if not rule_eligible:
        return "이관 적격 후보 없음", [], list(rule["operational"])
    top = [r["item_id"] for r in rule_eligible if r["tie_key"] == rule_eligible[0]["tie_key"]]
    preferred = [
        row["item_id"] for row in ranking["ai"]["items"]
        if row["item_id"] in top and row["eligible"]
    ]
    selection = preferred[0] if preferred else top[0]
    return ("공동 선두" if len(top) > 1 else "단독 선두"), top, ranking["mandatory"] + [selection]


def failure_reasons(flow):
    problems = []
    selection = flow["selection"]
    if isinstance(selection, dict):
        if flow["role_errors"]:
            problems.append("A0 문항별 쪽·사유 응답 검증 실패")
        elif selection["fallback"] == "rule":
            assert "max_output_tokens" in selection["reason"]
            problems.append("A1 출력 한도 초과")
        else:
            assert "supplemental candidate" in str(selection["reasons"])
            problems.append("시점에 맞는 보충 후보 자료 미확보")
    if flow["grade"] != "sealed":
        problems.extend("독립 채점 " + key for key in flow["grade_failure_kinds"])
    return problems


def main():
    result_path = BASE / "analysis/results.json"
    result = read(result_path)
    source_paths = {result_path, ROSTER}
    flow_path = BASE / "analysis/terminal_flow.json"
    sensitivity_path = BASE / "analysis/identity_sensitivity.json"
    crosscheck_path = BASE / "analysis/publication_pair_crosscheck.json"
    source_paths.update([flow_path, sensitivity_path, crosscheck_path])
    flows = {row["case"]: row for row in read(flow_path)["issuers"]}
    sensitivity = read(sensitivity_path)
    published = read(crosscheck_path)
    roster = {row["receipt"]: row for row in read(ROSTER)["rows"]}
    company_rows, material_rows, replay_rows, raw_scores = [], [], [], {}
    family = defaultdict(Counter)
    tie_groups = defaultdict(Counter)
    operating = defaultdict(Counter)
    routed_grade = defaultdict(Counter)
    shape = Counter()
    eligibility = Counter()
    observed_family_issuers = defaultdict(set)
    positive_family_issuers = defaultdict(set)
    n_k = defaultdict(Counter)
    grade_totals = Counter()
    all_grades = Counter()
    for src in result["issuers"]:
        c = src["case"]
        flow = flows[c]
        assert roster[c]["issuer"] == flow["issuer"] == src["issuer"]
        paths = {n: BASE / part / c / file for n, part, file in [
            ("registry", "issuers", "items.json"), ("ranking", "terra", "ranking.json"),
            ("grades", "blind", "sealed.json"), ("arithmetic", "issuers", "b.json")]}
        source_paths.update(p for p in paths.values() if p.is_file())
        reg = {v["id"]: v for v in read(paths["registry"])}
        rank = read(paths["ranking"]) if paths["ranking"].is_file() else None
        grades = read(paths["grades"])["grades"] if paths["grades"].is_file() else None
        assert (rank is not None) == (flow["selection"] == "ranked")
        assert (grades is not None) == (flow["grade"] == "sealed")
        assert len(reg) == src["original_count"]
        if grades is not None:
            assert set(reg) == set(grades)
            all_grades.update(grades.values())
        complete = rank is not None and grades is not None
        assert complete == (src["status"] == "COMPARED")
        counts = Counter(grades.values()) if grades is not None else {}
        row = {
            "receipt": c, "issuer": src["issuer"], "registered_items": len(reg),
            "gradebook_complete": grades is not None, "ranking_complete": rank is not None,
            "pair_complete": complete, "selection_or_grading_failure": failure_reasons(flow),
            "A0_complete": src["role_a0"], "C_complete": src["role_c"],
            "reference_grade_counts": dict(counts) if grades is not None else None,
            "self_exposed_in_C": (c in sensitivity["self_exposed_cases"]) if src["role_c"] else None,
            "any_direct_exposed_in_C": (c in sensitivity["any_direct_exposed_cases"]) if src["role_c"] else None,
            "n_optional_material": None, "n_optional_known_other": None, "pairwise_comparisons": None,
            "rank_status": "미완료", "concordance_rule": None, "concordance_ai": None,
            "delta_fraction": None, "delta": None, "rule_top_eligible_tie_count": None,
            "rule_top_eligible_tie_group": None, "operating_rule": None, "operating_ai": None,
            "operating_material_rule": None, "operating_material_ai": None,
            "tie_policy_operating": None, "tie_policy_material": None,
            "pending_excluded": None, "dart_filing": roster[c]["dart_url"],
            "fallback": flow["selection"].get("fallback") if isinstance(flow["selection"], dict) else None,
            "fallback_items": flow["selection"].get("operational") if isinstance(flow["selection"], dict) else None,
        }
        if rank is not None:
            mandatory = rank["mandatory"]
            assert mandatory == read(paths["arithmetic"])["mandatory"]
            strata, tied, tie_selection = replay_tiebreak(rank)
            row.update(rule_top_eligible_tie_count=len(tied), rule_top_eligible_tie_group=strata,
                       operating_rule=rank["rule"]["operational"], operating_ai=rank["ai"]["operational"])
        if not complete:
            company_rows.append(row)
            continue
        for arm in ARMS:
            assert row["operating_" + arm] == src[arm]["operating"]["items"]
        m = {k for k, grade in grades.items() if grade == MATERIAL}
        known_other = {k for k, grade in grades.items() if grade in (ACCEPT, MINOR)}
        optional = set(reg) - set(mandatory)
        both_classes = bool(m & optional) and bool(known_other & optional)
        t = tie_groups[strata]
        t["완료 기업"] += 1
        t["순위 유효 기업"] += both_classes
        values = {}
        for arm in ARMS:
            value = concordance(rank[arm]["items"], grades)
            assert (value is not None) == both_classes
            assert value is None or abs(float(value) - src[arm]["concordance"]["score"]) < 1e-12
            values[arm] = value
            row["concordance_" + arm] = None if value is None else str(value)
        if both_classes:
            delta = values["ai"] - values["rule"]
            raw_scores[c] = delta
            row.update(delta_fraction=str(delta), delta=float(delta),
                       rank_status=SIGN["up" if delta > 0 else "down" if delta < 0 else "tie"])
            assert str(delta) == published["complete_case_detail"][c]["delta"]
        else:
            assert not (m & optional) and (known_other & optional)
            row["rank_status"] = "공통 필수 밖에 확정 중대 없음"
        row.update(n_optional_material=len(m & optional), n_optional_known_other=len(known_other & optional),
                   pairwise_comparisons=len(m & optional) * len(known_other & optional),
                   pending_excluded=counts[UNKNOWN])
        eligibility[row["rank_status"]] += 1
        sets = {a: set(row["operating_" + a]) for a in ARMS}
        sets.update(union=sets["rule"] | sets["ai"], intersection=sets["rule"] & sets["ai"],
                    tie_policy=set(tie_selection))
        for name, items in sets.items():
            operating[name]["sent"] += len(items)
            operating[name]["confirmed_material_sent"] += len(m & items)
            routed_grade[name].update(grades[k] for k in items)
        for arm in ARMS:
            hits = sorted(m & sets[arm])
            row["operating_material_" + arm] = hits
            t[arm + " 중대 이관"] += len(hits)
            assert hits == sorted(src[arm]["operating"]["material_found"])
        row.update(tie_policy_operating=sorted(sets["tie_policy"]), tie_policy_material=sorted(m & sets["tie_policy"]))
        shape["operating_lists_differ"] += sets["rule"] != sets["ai"]
        shape["two_distinct_in_union"] += len(sets["union"]) == 2
        shape["tie_policy_rule_changed"] += sets["rule"] != sets["tie_policy"]
        shape["nothing_in_union"] += not sets["union"]
        if sets["rule"] != sets["tie_policy"]:
            replay_rows.append({"receipt": c, "issuer": row["issuer"], "rule_top_eligible": tied,
                                "rule": {k: grades[k] for k in sets["rule"]},
                                "tie_policy": {k: grades[k] for k in sets["tie_policy"]}})
        grade_totals.update(grades.values())
        for k, info in reg.items():
            f = info["family"]
            observed_family_issuers[f].add(c)
            family[f]["items"] += 1
            family[f][grades[k]] += 1
            for arm in ARMS:
                family[f][arm + "_sent"] += k in sets[arm]
                family[f][arm + "_material_sent"] += (k in m) and (k in sets[arm])
            if k not in m:
                continue
            positive_family_issuers[f].add(c)
            mr = {"receipt": c, "issuer": row["issuer"], "id": k, "family": f,
                  "question": info["question"], "pages": info["pages"],
                  "rank_rule": None, "rank_ai": None, "rule_top_eligible": k in tied,
                  "rule_sent": k in sets["rule"], "ai_sent": k in sets["ai"],
                  "tie_policy_sent": k in sets["tie_policy"]}
            for arm in ARMS:
                indexed = {rr["item_id"]: i for i, rr in enumerate(rank[arm]["items"], 1)}
                mr["rank_" + arm] = indexed.get(k)
            material_rows.append(mr)
        for k in range(1, 5):
            for arm in ARMS:
                ids = mandatory + [i["item_id"] for i in rank[arm]["items"][:k]]
                assert set(ids) == set(src["fixed_curve_by_k"][str(k)][arm]["items"])
                n_k[k][arm + "_sent"] += len(ids)
                n_k[k][arm + "_material_sent"] += len(set(ids) & m)
        company_rows.append(row)
    assert len(company_rows) == len(set(roster)) == len({v["receipt"] for v in company_rows})
    assert sum(r["registered_items"] for r in company_rows) == 406
    assert sum(eligibility.values()) == result["overall"]["complete_pairs"]
    assert len(material_rows) == result["overall"]["known_material"]
    assert len(raw_scores) == result["overall"]["valid_concordance_pairs"]
    observed_mean = mean(raw_scores.values())
    assert abs(float(observed_mean) - result["overall"]["primary_equal_issuer_ai_minus_rule"]) < 1e-12
    for a in ARMS:
        assert operating[a]["sent"] == result["overall"]["operating"][a]["transfers"]
        for k, data in n_k.items():
            assert data[a + "_material_sent"] == result["overall"]["same_k_curve"][str(k)][a]["found"]
    for f in family:
        family[f]["issuers"] = len(observed_family_issuers[f])
        family[f]["issuers_confirmed_material"] = len(positive_family_issuers[f])
    leave_one_out = []
    for c, v in raw_scores.items():
        remaining = mean(other for other_case, other in raw_scores.items() if other_case != c)
        leave_one_out.append({"excluded": roster[c]["issuer"], "excluded_delta": str(v),
                              "mean_of_remaining_five_exact": str(remaining),
                              "mean_of_remaining_five": float(remaining)})
    tallies = Counter({"등록 기업": len(company_rows),
                       "본평가 문항": sum(row["registered_items"] for row in company_rows),
                       "독립 기준표 완성": sum(row["gradebook_complete"] for row in company_rows),
                       "순위 완성": sum(row["ranking_complete"] for row in company_rows),
                       "짝 완성": sum(row["pair_complete"] for row in company_rows),
                       "순위 평가 가능": len(raw_scores)})
    summary = {
        "cohort": dict(tallies), "rank_outcomes_in_27": dict(eligibility),
        "all_gradebooks_label_counts": dict(all_grades), "complete_27_label_counts": dict(grade_totals),
        "equal_company_weight_mean_delta": str(observed_mean),
        "leave_one_out": leave_one_out, "frozen_sensitivities": published["cohorts"],
        "missing_grade_sensitivity_frozen": {
            k: result["overall"][k] for k in ("additional_valid_if_deferred_classified",
                "pending_bounds_on_primary_matched_cohort", "operating_miss_delta_pending_bounds")},
        "issue_family_in_27": dict(family), "rule_top_score_subgroups_in_27": dict(tie_groups),
        "operating_and_post_hoc_replay_in_27": dict(operating),
        "grade_of_routed_items_in_27": dict(routed_grade), "shape_in_27": dict(shape),
        "fixed_k_curves_in_27": dict(n_k), "changed_by_tie_policy": replay_rows,
        "case_state_definition": "독립 기준표와 선별 결과의 완성을 따로 기록했다. 순위 유효 조건은 공통 필수 밖에 확정 중대와 확정 비중대 또는 수용 가능이 각각 하나 이상인 경우다.",
        "tie_policy_definition": "사후에 규칙 이관의 단독 선두와 빈 목록은 보존했다. 최상위 적격 후보가 동률이면 그 안에서 AI가 사람 검토로 요청한 문항 중 AI 순위가 가장 높은 문항을 고른다. 그런 문항이 없으면 규칙의 원래 순서를 쓴다. 모든 공통 필수는 유지한다.",
        "interpretation": "기업 27곳의 1차 동결 기록을 재생했다. 동률 분기는 이미 결과를 읽은 뒤 만들었다. 순위표와 기준표가 있는 기존 기업의 기술적 관측이며 독립 외부 검증과 인과 추정은 확보하지 않았다.",
    }
    save_json("summary.json", summary)
    save_json("companies.json", company_rows)
    save_json("material_issues.json", material_rows)
    save_json("sources_sha256.json", {p.relative_to(ROOT).as_posix(): fingerprint(p) for p in sorted(source_paths)})
    save_company_csv(company_rows)
    print("Recomputed", dict(tallies), "from", len(source_paths), "source files.")


def display_list(items):
    if items is None:
        return "미산출"
    return ", ".join("문항 " + item.split("-")[-1] for item in items) if items else "없음"


def save_company_csv(rows):
    rendered = []
    for row in rows:
        grade_counts = row["reference_grade_counts"]
        fields = {
            "기업명": row["issuer"], "DART 접수번호": row["receipt"],
            "등록 문항 수": row["registered_items"],
            "A0 공시 검토": "완료" if row["A0_complete"] else "미완료",
            "C 후보 검토": "완료" if row["C_complete"] else "미완료",
            "두 방식 순위": "완료" if row["ranking_complete"] else "미완료",
            "독립 기준표": "완료" if row["gradebook_complete"] else "미완료",
            "완료 쌍": "완료" if row["pair_complete"] else "미완료",
            "순위 비교 판정": row["rank_status"],
            "미완료 사유": " · ".join(row["selection_or_grading_failure"]),
            "순위 미완료 시 대체 경로": {"rule": "규칙", "mandatory_only": "공통 필수만"}.get(row["fallback"], "해당 없음"),
            "대체 경로 이관 문항": display_list(row["fallback_items"]) if row["fallback"] else "해당 없음",
            "확정 중대 문항 수": grade_counts.get(MATERIAL, 0) if grade_counts is not None else None,
            "판정 유보 문항 수": grade_counts.get(UNKNOWN, 0) if grade_counts is not None else None,
            "공통 필수 밖 확정 중대 수": row["n_optional_material"],
            "공통 필수 밖 수용 또는 비중대 수": row["n_optional_known_other"],
            "기업 내 순위 비교 쌍 수": row["pairwise_comparisons"],
            "규칙 순위 일치도": None if row["concordance_rule"] is None else float(Fraction(row["concordance_rule"])),
            "AI 순위 일치도": None if row["concordance_ai"] is None else float(Fraction(row["concordance_ai"])),
            "순위 차이(AI − 규칙)": row["delta"],
            "규칙 최상위 이관 적격 후보": row["rule_top_eligible_tie_group"],
            "공동 또는 단독 선두 후보 수": row["rule_top_eligible_tie_count"],
            "규칙 실제 이관 문항": display_list(row["operating_rule"]),
            "AI 실제 이관 문항": display_list(row["operating_ai"]),
            "규칙 이관 중 확정 중대": display_list(row["operating_material_rule"]),
            "AI 이관 중 확정 중대": display_list(row["operating_material_ai"]),
            "동률 중 AI 선택 사후 재생 이관": display_list(row["tie_policy_operating"]),
            "사후 재생 이관 중 확정 중대": display_list(row["tie_policy_material"]),
            "최초 신고서 원문": row["dart_filing"],
        }
        rendered.append({k: ("미산출" if v is None else round(v, 6) if type(v) is float else v)
                         for k, v in fields.items()})
    with (OUT / "기업별_37곳_결과.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rendered[0]))
        writer.writeheader()
        writer.writerows(rendered)


if __name__ == "__main__":
    main()
