"""Replay explicit referral policies on locked rankings and independent gradebooks."""
import hashlib
import json
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]
V1 = OUT.parent / "a1_main/v1"
MATERIAL = "중대 쟁점"
PENDING = "판정 유보"


def load(path):
    return json.loads(path.read_bytes())


def policies(ranking):
    rule = set(ranking["rule"]["operational"])
    ai = set(ranking["ai"]["operational"])
    yield "rule", rule
    yield "ai", ai
    yield "union", rule | ai
    yield "rule_first_fill", rule or ai
    yield "intersection", rule & ai
    eligible = [i for i in ranking["rule"]["items"] if i["eligible"] and i["item_id"] not in ranking["mandatory"]]
    leading = {i["item_id"] for i in eligible if i["tie_key"] == eligible[0]["tie_key"]}
    chosen = next((i["item_id"] for i in ranking["ai"]["items"]
                   if i["item_id"] in leading and i["action"] == "사람 검토"), None)
    yield "ties_only", set(ranking["mandatory"]) | {chosen} if len(leading) > 1 and chosen else rule
    for k in (1, 2, 3, 4):
        for arm in ("rule", "ai"):
            mandatory = set(ranking["mandatory"])
            order = [i["item_id"] for i in ranking[arm]["items"] if i["item_id"] not in mandatory]
            yield f"{arm}_fixed_{k}", mandatory | set(order[:k])


def replay():
    result_file = V1 / "analysis/results.json"
    register = load(result_file)
    counts = {}
    companies = []
    material_counts = Counter()
    for row in register["issuers"]:
        case = row["case"]
        if row["selection_state"] != "ranked" or row["grade_state"] != "sealed":
            continue
        ranking = load(V1 / "terra" / case / "ranking.json")
        grades = load(V1 / "blind" / case / "sealed.json")["grades"]
        material = {k for k, v in grades.items() if v == MATERIAL}
        assert set(row["material"]) == material
        material_counts[len(material)] += 1
        allocations = dict(policies(ranking))
        details = {}
        for name, ids in allocations.items():
            tally = counts.setdefault(name, Counter())
            details[name] = sorted(ids)
            tally.update({"items": len(ids), "companies_with_referrals": int(bool(ids)),
                          "companies_with_any_material_found": int(bool(material & ids)),
                          "companies_with_two_or_more_referrals": int(len(ids) >= 2)})
            tally.update(grades[i] for i in ids)
        for arm in ("rule", "ai"):
            assert details[arm] == sorted(row[arm]["operating"]["items"])
            for k in (1, 2, 3, 4):
                frozen = row["fixed_curve_by_k"][str(k)][arm]["items"]
                assert details[f"{arm}_fixed_{k}"] == sorted(frozen)
        companies.append({"issuer": row["issuer"], "case": case, "confirmed_material": sorted(material),
                          "referrals": details})
    assert len(companies) == register["overall"]["complete_pairs"]
    assert sum(k*n for k,n in material_counts.items()) == register["overall"]["known_material"]
    return {"input_sha256": hashlib.sha256(result_file.read_bytes()).hexdigest(),
            "issuers_by_material_count": dict(sorted(material_counts.items())),
            "scope": "두 방식의 순위와 독립 기준표가 있는 기업. 유보 항목은 별도 집계.",
            "counts": counts, "issuers": companies}


if __name__ == "__main__":
    out = replay()
    (OUT / "work/policy_replay.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps([out["issuers_by_material_count"], out["counts"]], ensure_ascii=False, indent=1))
