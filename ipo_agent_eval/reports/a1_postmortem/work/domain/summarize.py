"""Rebuild post-hoc counts from frozen baseline records. Never changes a baseline input."""

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path


OUT = Path(__file__).resolve().parent
REPORTS = OUT.parents[2]
SOURCE = REPORTS / "a1_main" / "v1"
ENROLLMENT = REPORTS / "a1_current" / "official" / "enrollment_expansion"
GRADES = {"수용 가능": "acceptable", "비중대 쟁점": "minor",
          "중대 쟁점": "material", "판정 유보": "deferred"}
CORE = ["이익 기간", "이익 귀속", "기준주가", "PER 집계", "적용 주식 수", "주당 평가액", "할인율과 밴드"]
CORE_FULL = ["발행사 적용 이익의 기간", "이익의 회계상 귀속 범위", "비교기업 기준주가의 관측기간·선택",
             "비교기업 PER의 집계 방식", "발행사 적용 주식 수", "주당 평가가액 계산", "공모가 할인율과 밴드"]


def read(path):
    return json.loads(path.read_bytes())


def sample_needed(yield_rate, probability):
    """Minimum n with P(Binomial(n, yield_rate) >= 15) >= probability, for planning only."""
    for n in range(15, 1001):
        failure = sum(math.comb(n, i) * yield_rate**i * (1 - yield_rate)**(n - i) for i in range(15))
        if 1 - failure >= probability:
            return n
    raise ValueError("search range exhausted")


result_file = SOURCE / "analysis" / "results.json"
results = read(result_file)
roster = read(ENROLLMENT / "roster.json")["rows"]
by_case = {r["case"]: r for r in results["issuers"]}
assert set(by_case) == {r["receipt"] for r in roster}
by_type = defaultdict(Counter)
by_sector = defaultdict(Counter)
by_phase = defaultdict(Counter)
raw_rows = []
issuer_rows = []
for enrolled in roster:
    case = enrolled["receipt"]
    r = by_case[case]
    directory = SOURCE / "issuers" / case
    items = read(directory / "items.json")
    grades_file = SOURCE / "blind" / case / "sealed.json"
    grades = read(grades_file)["grades"] if grades_file.exists() else {}
    assert (r["grade_state"] == "sealed") == bool(grades)
    assert not grades or set(grades) == {i["id"] for i in items}
    assert len(items) == r["original_count"] and len(items) >= 7
    sc = read(directory / "c_private.json")["sector"]
    sector = sc["industry"].strip()
    delta = r.get("concordance_delta_ai_minus_rule")
    complete = r["status"] == "COMPARED"
    signs = {"registered": 1, "sealed": int(bool(grades)), "paired": int(complete),
             "eligible": int(delta is not None), "higher": int(delta is not None and delta > 0),
             "lower": int(delta is not None and delta < 0), "equal": int(delta == 0)}
    by_sector[sector].update(signs)
    by_phase[enrolled["cohort"]].update(signs)
    issuer_rows.append(dict(case=case, issuer=r["issuer"], sector=sector, ksic=sc.get("ksic"),
                            enrollment_cohort=enrolled["cohort"], rank_delta=delta, **signs))
    for n, item in enumerate(items):
        if n < len(CORE):
            assert CORE_FULL[n] == item["question"]
            category = CORE[n]
        else:
            assert item["family"] in ("J1", "J2")
            category = "개별 손익 조정" if item["family"] == "J1" else "비교기업 적합성"
        item_id = item["id"]
        grade = GRADES[grades[item_id]] if grades else None
        row = dict(item=item_id, issuer=r["issuer"], category=category, grade=grade,
                   paired=complete, rule=None, ai=None)
        c = by_type[category]
        c["registered"] += 1
        if grade:
            c["graded"] += 1
            c["all_" + grade] += 1
        if complete:
            c["paired"] += 1
            c["paired_" + grade] += 1
            for arm in ("rule", "ai"):
                row[arm] = item_id in r[arm]["operating"]["items"]
                if row[arm]:
                    c[arm + "_routed"] += 1
                    c[arm + "_routed_" + grade] += 1
        raw_rows.append(row)

totals = sum(by_type.values(), Counter())
assert [totals[k] for k in ["registered", "graded", "paired", "all_material", "paired_material",
                            "all_deferred", "rule_routed", "ai_routed", "rule_routed_material",
                            "ai_routed_material"]] == [406, 340, 291, 8, 8, 79, 23, 26, 2, 3]
assert [sum(v[k] for v in by_sector.values()) for k in ["registered", "paired", "eligible"]] == [37, 27, 6]
assert max(v["eligible"] for v in by_sector.values()) == 1
for key, value in by_type.items():
    assert sum(value["paired_" + g] for g in GRADES.values()) == value["paired"]
    assert sum(value["all_" + g] for g in GRADES.values()) == value["graded"]
    for arm in ("rule", "ai"):
        assert sum(value[arm + "_routed_" + g] for g in GRADES.values()) == value[arm + "_routed"]
family_names = {"공통 7종": CORE, "개별 손익 조정": ["개별 손익 조정"], "비교기업 적합성": ["비교기업 적합성"]}
families = {f: sum((by_type[t] for t in types), Counter()) for f, types in family_names.items()}
planning = [{"eligible_probability": p, "confidence": prob, "minimum_registrations": sample_needed(p, prob)}
            for p in (0.10, 6/37, 0.25, 0.5) for prob in (0.80, 0.90)]
out = {"frozen_results_sha256": hashlib.sha256(result_file.read_bytes()).hexdigest(),
       "counts_explanation": "paired includes all items from the 27 companies with both orders and a sealed gradebook. "
                             "All routing columns describe the two actual lists only within these 27. "
                             "All_missing grades and routing are null in item_rows. Absent count keys are zero.",
       "totals": totals, "families": families, "categories": dict(by_type), "sectors": dict(by_sector),
       "enrollment_cohorts": dict(by_phase), "cases": issuer_rows, "item_rows": raw_rows,
       "planning_sensitivity_15_eligible": planning}
(OUT / "domain_counts.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("totals", totals)
for name, v in list(families.items()) + list(by_type.items()):
    print(name, [v[k] for k in ("registered", "graded", "all_deferred", "paired", "paired_deferred",
                                "paired_material", "rule_routed", "ai_routed", "rule_routed_material", "ai_routed_material")])
print("sectors", len(by_sector), "\ncohorts", dict(by_phase), "\nplanning", planning)
