"""Independently check the publication CSV and the retrospective one-slot policy."""

import csv
import hashlib
import json
from collections import Counter
from fractions import Fraction
from itertools import product
from pathlib import Path
from statistics import mean


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
BASE = ROOT / "reports/a1_main/v1"
POS = "중대 쟁점"
NEG = ("수용 가능", "비중대 쟁점")


def read(path):
    return json.loads(path.read_bytes())


def main():
    hashes = read(OUT / "sources_sha256.json")
    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in hashes.items())
    cfile = OUT / "기업별_37곳_결과.csv"
    assert cfile.read_bytes().startswith(b"\xef\xbb\xbf")
    with cfile.open(encoding="utf-8-sig", newline="") as file:
        csv_rows = list(csv.DictReader(file))
    by_case = {row["DART 접수번호"]: row for row in csv_rows}
    registry = read(ROOT / "reports/a1_current/official/enrollment_expansion/roster.json")["rows"]
    assert len(csv_rows) == len(by_case) == len(registry) == 37
    assert set(by_case) == {row["receipt"] for row in registry}
    assert sum(int(r["등록 문항 수"]) for r in csv_rows) == 406
    for row in registry:
        observed = by_case[row["receipt"]]
        assert observed["기업명"] == row["issuer"]
        assert row["dart_url"] == observed["최초 신고서 원문"]
    assert Counter(r["완료 쌍"] for r in csv_rows) == {"완료": 27, "미완료": 10}
    assert Counter(r["순위 비교 판정"] for r in csv_rows) == {
        "동률": 1, "AI 상승": 2, "AI 하락": 3, "공통 필수 밖에 확정 중대 없음": 21, "미완료": 10}
    assert all(r["순위 차이(AI − 규칙)"] == "미산출" for r in csv_rows if r["순위 비교 판정"] in
               ("공통 필수 밖에 확정 중대 없음", "미완료"))
    summary = read(OUT / "summary.json")
    csv_by_issuer = {row["기업명"]: row for row in csv_rows}
    slot_count = hit_count = changed = 0
    material = read(OUT / "material_issues.json")
    labels = Counter()
    scores = {}
    for company in registry:
        c = company["receipt"]
        issuer = company["issuer"]
        csv_row = csv_by_issuer[issuer]
        if csv_row["완료 쌍"] != "완료":
            continue
        ranks = read(BASE / "terra" / c / "ranking.json")
        gradebook = read(BASE / "blind" / c / "sealed.json")["grades"]
        # Use indexed sets and integer priorities, never the main program's selection helper.
        middle = {}
        for arm in ("rule", "ai"):
            rows = ranks[arm]["items"]
            grouped = {}
            for index, item in enumerate(rows):
                grouped.setdefault(item["tie_key"], []).append(index)
            midrank = {r["item_id"]: mean(grouped[r["tie_key"]]) for r in rows}
            m = [k for k in midrank if gradebook[k] == POS]
            n = [k for k in midrank if gradebook[k] in NEG]
            if m and n:
                doubles = sum(2 if midrank[x] < midrank[y] else int(midrank[x] == midrank[y])
                              for x, y in product(m, n))
                middle[arm] = Fraction(doubles, 2 * len(m) * len(n))
        if middle:
            scores[issuer] = middle["ai"] - middle["rule"]
            assert abs(float(csv_row["순위 차이(AI − 규칙)"]) - float(scores[issuer])) <= 0.0000005
        baseline = set(ranks["rule"]["operational"])
        protected = set(ranks["mandatory"])
        discretionary = baseline - protected
        if discretionary:
            assert len(discretionary) == 1
            original = next(iter(discretionary))
            rule_by_id = {r["item_id"]: r for r in ranks["rule"]["items"]}
            at_front = {i for i, r in rule_by_id.items() if r["eligible"] and
                        r["tie_key"] == rule_by_id[original]["tie_key"]}
            ai_by_id = {r["item_id"]: int(r["tie_key"]) for r in ranks["ai"]["items"] if r["eligible"]}
            intersection = at_front.intersection(ai_by_id)
            best = min(intersection, key=lambda i: (-ai_by_id[i], i)) if intersection else original
            protected.add(best)
        expected = "없음" if not protected else ", ".join("문항 " + k[-2:] for k in sorted(protected))
        assert csv_row["동률 중 AI 선택 사후 재생 이관"] == expected
        slot_count += len(protected)
        hit_count += sum(gradebook[id_] == POS for id_ in protected)
        changed += protected != baseline
        labels.update(gradebook[k] for k in protected)
        for doc in (m for m in material if m["receipt"] == c):
            assert doc["tie_policy_sent"] == (doc["id"] in protected)
    assert (slot_count, hit_count, changed) == (23, 5, 9)
    assert labels == summary["grade_of_routed_items_in_27"]["tie_policy"]
    assert Fraction(summary["equal_company_weight_mean_delta"]) == mean(scores.values())
    for row in summary["leave_one_out"]:
        assert mean(v for issuer, v in scores.items() if issuer != row["excluded"]) == Fraction(
            row["mean_of_remaining_five_exact"])
    print(f"Verified {len(hashes)} source fingerprints, all 37 CSV companies, 27 policy choices and 6 exact rank differences.")


if __name__ == "__main__":
    main()
