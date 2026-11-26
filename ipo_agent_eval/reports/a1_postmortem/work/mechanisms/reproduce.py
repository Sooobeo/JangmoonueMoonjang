"""Read the frozen main evaluation and trace eight material issues through both routes."""
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path


HERE = Path(__file__).resolve().parent
V1 = HERE.parents[2] / "a1_main" / "v1"
MATERIAL = "중대 쟁점"
source_hashes = {}


def read(relative):
    raw = (V1 / relative).read_bytes()
    source_hashes[str(relative)] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def indexed(items):
    mapping = {item["item_id"]: item for item in items}
    assert len(mapping) == len(items)
    return mapping


def compact(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def grade_citations(case, material_ids):
    packet = read(f"issuers/{case}/grading.json")
    pages = packet["pages"]
    question_pages = {row["item_id"]: row["pages"] for row in packet["items"]}
    result = defaultdict(list)
    for reviewer in ("first", "second", "reconcile"):
        source = f"blind/{case}/{reviewer}/accepted.json"
        if not (V1 / source).is_file():
            continue
        answer = read(source)["answer"]["items"]
        for row in answer:
            item = row["item_id"]
            if item not in material_ids or row["grade"] != MATERIAL:
                continue
            page, quote = row["physical_page"], row["quote"]
            assert page in question_pages[item] and quote.strip()
            assert compact(quote) in compact(pages[str(page)])
            result[item].append({"source": source, "page": page, "quote": quote})
    assert set(result) == set(material_ids)
    return result


def snapshot(row, grade, merged, by_id, order, results, materials):
    item = row["item_id"]
    source = merged[item]
    entry = {"item": item, "question": source["question"], "family": source["question_type"], "grade": grade}
    for role in ("a0", "c"):
        record = source[role]
        entry[role] = {
            key: record[key] for key in ("state", "reason", "comparable", "physical_page", "evidence_ids") if key in record
        }
    for route in ("rule", "ai"):
        ranked = by_id[route][item]
        entry[route] = {
            "rank_after_tie_break": order[route].index(item) + 1,
            "all_items_with_same_priority": [key for key in order[route] if by_id[route][key]["tie_key"] == ranked["tie_key"]],
            "eligible": ranked["eligible"],
            "selected": item in results[route]["operating"]["items"],
        }
        if route == "ai":
            entry[route].update({key: ranked[key] for key in ("action", "priority", "reason", "evidence_ids")})
    if item in materials:
        assert grade == MATERIAL
    return entry


def build():
    result = read("analysis/results.json")
    independent = read("analysis/publication_pair_crosscheck.json")["complete_case_detail"]
    counts = defaultdict(lambda: defaultdict(Counter))
    cases = []
    k_hits = defaultdict(Counter)
    routed = Counter()
    signal_counts = Counter()
    material_total = 0
    top_ties = {}
    for z in result["issuers"]:
        if z["status"] != "COMPARED":
            continue
        case = z["case"]
        rank = read(f"terra/{case}/ranking.json")
        grades = read(f"blind/{case}/sealed.json")["grades"]
        merged = indexed(read(f"terra/{case}/merged.json")["items"])
        by_id = {route: indexed(rank[route]["items"]) for route in ("rule", "ai")}
        assert set(grades) == set(merged) == set(by_id["rule"]) == set(by_id["ai"])
        assert not z["mandatory"]
        order = {route: list(rows) for route, rows in by_id.items()}
        materials = {item for item, grade in grades.items() if grade == MATERIAL}
        assert materials == set(z["material"])
        for route in by_id:
            raw_eligible = [item for item in order[route] if by_id[route][item]["eligible"]]
            assert raw_eligible[:1] == z[route]["operating"]["items"]
            if route == "rule" and raw_eligible:
                top_priority = by_id[route][raw_eligible[0]]["tie_key"]
                group = [item for item in raw_eligible if by_id[route][item]["tie_key"] == top_priority]
                assert group == sorted(group)
                top_ties[case] = {"issuer": z["issuer"], "top_eligible_tie_group": group,
                                  "known_material": sorted(materials.intersection(group))}
            for item in raw_eligible:
                counts["eligible"][route][grades[item]] += 1
            for item in raw_eligible[:1]:
                counts["actually_selected"][route][grades[item]] += 1
            for k in range(1, 5):
                k_hits[str(k)][route] += len(set(order[route][:k]) & materials)
        for item, grade in grades.items():
            counts["family"][merged[item]["question_type"]][grade] += 1
            counts["ai_action"][by_id["ai"][item]["action"]][grade] += 1
        if not materials:
            continue
        material_total += len(materials)
        assert z["concordance_delta_ai_minus_rule"] is not None
        checked_quotes = grade_citations(case, materials)
        audit = read(f"blind/{case}/source_audit.json")
        affected = set(materials) | set(z["rule"]["operating"]["items"]) | set(z["ai"]["operating"]["items"])
        entries = []
        for item in sorted(affected):
            entry = snapshot(by_id["ai"][item], grades[item], merged, by_id, order, z, materials)
            if item in materials:
                assert audit[item]["supported"]
                entry["frozen_source_audit_basis"] = audit[item]["basis"]
                entry["direct_citations_verified"] = checked_quotes[item]
                key = ("both" if entry["ai"]["selected"] and entry["rule"]["selected"] else
                       "ai_only" if entry["ai"]["selected"] else
                       "rule_only" if entry["rule"]["selected"] else "neither")
                routed[key] += 1
                for role in ("a0", "c"):
                    state = "역할상 비교 불가" if entry[role]["reason"] == "역할상 비교 불가" else entry[role]["state"]
                    signal_counts[(role, state)] += 1
            entries.append(entry)
        score = independent[case]
        cases.append({"issuer": z["issuer"], "case": case,
                      "rule_concordance": score["rule"], "ai_concordance": score["ai"], "difference": score["delta"],
                      "issue_count": len(grades), "lookup_pages": rank["lookup_pages"],
                      "new_page_ids_added_by_lookup": sorted(set(rank["lookup_refs"]) - set(rank["initial_refs"])),
                      "entries": entries})
    assert len(cases) == 6 and material_total == 8
    assert sum(sum(grades.values()) for grades in counts["family"].values()) == 291
    for route in ("rule", "ai"):
        assert counts["eligible"][route][MATERIAL] == material_total
        assert counts["actually_selected"][route][MATERIAL] == result["overall"]["operating"][route]["material_recall"] * material_total
        for k, values in k_hits.items():
            assert values[route] == result["overall"]["same_k_curve"][k][route]["found"]
    tie_totals = Counter()
    equal_weight_recall_count = Fraction(0)
    for tie in top_ties.values():
        group, confirmed = tie["top_eligible_tie_group"], tie["known_material"]
        tie_totals["with_tie"] += len(group) > 1
        tie_totals["all_options_material"] += len(confirmed) == len(group)
        tie_totals["at_least_one_option_material"] += bool(confirmed)
        tie_totals["registered_ascending_id"] += group[0] in confirmed
        tie_totals["reverse_id_example"] += group[-1] in confirmed
        equal_weight_recall_count += Fraction(len(confirmed), len(group))
    assert tie_totals["registered_ascending_id"] == counts["actually_selected"]["rule"][MATERIAL]
    output = {
        "scope": "동결 평가 완료 기업 27곳·291문항. 기초 자료는 그대로 두고 사후에 교차 집계했다.",
        "cases_with_confirmed_material": cases,
        "counts_on_complete_issuers": counts,
        "operating_confirmed_material": routed,
        "frozen_rule_and_ai_full_ranking_hits_for_equal_seats": k_hits,
        "posthoc_rule_top_tie_sensitivity": {
            "scope": "실제 이관 자격과 점수는 고정하고 같은 최상위 안의 순서만 바꿀 때 확인된 중대 회수 건수.",
            "firms_with_at_least_one_eligible": len(top_ties),
            "totals": tie_totals,
            "equal_probability_expected_count": str(equal_weight_recall_count),
            "case_detail": top_ties,
        },
        "upstream_states_on_known_material": {role: {state: n for (key, state), n in signal_counts.items() if key == role}
                                             for role in ("a0", "c")},
        "checks": [
            "완료 기업마다 두 순위와 합친 역할 기록의 문항 집합을 독립 등급표와 대조했다.",
            "원순위에서 이관 자격이 있는 첫 문항을 골라 동결한 실제 이관 목록과 대조했다. 고정 1~4자리에서의 중대 건수도 공개 민감도 표와 일치했다.",
            "8건마다 중대 등급을 부여한 채점자의 실제 인용을 해당 문항에 허용된 물리 쪽의 원문 문자열과 대조했다. 공백 및 유니코드 정규화 후 모두 일치했다.",
        ],
        "frozen_source_sha256_relative_to_v1": source_hashes,
    }
    return output


if __name__ == "__main__":
    data = build()
    (HERE / "mechanisms.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(data['cases_with_confirmed_material'])} issuers, 8 material items, 291 complete observations.")
