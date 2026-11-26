"""Reproduce the two development filings' displayed valuation and share bridges."""

import hashlib
import json
import re
import time
from decimal import Decimal
from pathlib import Path

import fitz

from ipo_eval.calculations import calculate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/a1_current"
D = Decimal
# (physical page, source row label, displayed value, source unit)
FIELDS = {
    "HDMS": {
        "earnings": (269, "적용 순이익", "151,116", "백만원"),
        "per": (269, "적용 PER 거래배수", "31.5", "배"),
        "equity": (270, "평가시가총액", "4,761,293", "백만원"),
        "existing": (270, "공모 전 발행주식수", "40,000,000", "주"),
        "new": (270, "신주모집주식수", "4,450,000", "주"),
        "secondary": (270, "구주매출주식수", "4,450,000", "주"),
        "options": (270, "희석가능주식수", "420,190", "주"),
        "shares": (270, "공모 후 잠재주식수", "44,870,190", "주"),
        "price": (270, "주당 평가가액", "106,113", "원"),
    },
    "MELCON": {
        "earnings": (208, "적용 당기순이익(백만원)", "6,894", "백만원"),
        "per": (208, "적용 PER(배)", "26.18", "배"),
        "equity": (208, "기업가치 평가액(백만원)", "180,497", "백만원"),
        "existing": (208, "기발행보통주식수", "10,000,000", "주"),
        "new": (208, "공모 신주발행주식", "2,500,000", "주"),
        "underwriter": (208, "상장주선인 의무인", "75,000", "주"),
        "options": (208, "주식매수선택권", "160,000", "주"),
        "shares": (208, "적용 주식수(천주)", "12,735", "천주"),
        "price": (208, "주당 평가가액(원)", "14,173", "원"),
    },
}
CONTEXT = {
    "HDMS": (270, ["2023년 온기 지배주주지분 기준 순이익", "비교회사의 평균 PER"]),
    "MELCON": (
        208,
        ["2026년 2분기 지배주주 당기순이익", "3,447백만원을 연환산", "최근 4개분기"],
    ),
}


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def filing(case):
    folder = ROOT / "data/a1_pilot" / case / "filing"
    meta = json.loads((folder / "provenance.json").read_bytes())
    path = folder / (meta["receipt_no"] + ".pdf")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != (meta.get("sha256") or meta["pdf_sha256"]):
        raise ValueError("Unexpected filing hash")
    return path, meta, digest


def number(value):
    return D(value.replace(",", ""))


def source_match(lines, label, value):
    # The MELCON new-issue row wraps its amount on the next physical line.
    for i, line in enumerate(lines):
        if label not in line:
            continue
        segment = line
        if label in {"공모 신주발행주식", "상장주선인 의무인"}:
            segment += " " + " ".join(lines[i + 1 : i + 3])
        if re.search(r"(?<![\d,.])" + re.escape(value) + r"(?![\d,.])", segment):
            return segment.strip()
    return None


def audit(case, facts):
    values = {
        key: number(f["display"]) * (1000 if f["unit"] == "천주" else 1)
        for key, f in facts.items()
        if f["source_status"] == "통과"
    }

    def check(name, required, rule):
        missing = sorted(set(required) - values.keys())
        if missing:
            return {"rule": name, "status": "미확인", "missing": missing}
        actual, expected, tolerance = rule(values)
        delta = actual - expected
        return {
            "rule": name,
            "status": "통과" if abs(delta) <= tolerance else "불일치",
            "calculated": str(actual),
            "reported": str(expected),
            "delta": str(delta),
            "tolerance": str(tolerance),
            "input_ids": required,
        }

    def price(v):
        calc = calculate(
            {
                "reported_equity_million_krw": str(v["equity"]),
                "share_count": str(v["shares"]),
            }
        )
        row = next(
            r for r in calc["calculations"] if r["id"] == "price_from_reported_equity"
        )
        return D(row["result"]), v["price"], D(".5")

    def cap(v):
        # Half of the displayed final digit on each factor; equity is in millions.
        eps = D(".05") if case == "HDMS" else D(".005")
        return (
            v["earnings"] * v["per"],
            v["equity"],
            v["earnings"] * eps + D(".5") * (v["per"] + eps + 1),
        )

    components = ["existing", "new", "options"] + (
        ["underwriter"] if case == "MELCON" else []
    )
    return [
        check(
            "share_bridge",
            components + ["shares"],
            lambda v: (sum(v[k] for k in components), v["shares"], D(0)),
        ),
        check("equity_at_display_precision", ["earnings", "per", "equity"], cap),
        check("price_from_equity", ["equity", "shares", "price"], price),
    ]


def mandatory_items(case, rows):
    """Map a confirmed numeric discrepancy to the affected frozen review item."""
    ids = {"HDMS": ("H09", "H10"), "MELCON": ("M09", "M10")}[case]
    mandatory = set()
    for row in rows:
        if row["status"] != "불일치":
            continue
        if row["rule"] == "share_bridge":
            # Correcting only the denominator changes price by reported / actual.
            base = abs(D(row["calculated"]))
            item_id = ids[0]
        else:
            base = abs(D(row["reported"]))
            item_id = ids[1]
        lower_bound = max(D(0), abs(D(row["delta"])) - D(row["tolerance"]))
        if base and lower_bound / base >= D(".05"):
            mandatory.add(item_id)
    return sorted(mandatory)


def run(case):
    start = time.perf_counter()
    path, meta, digest = filing(case)
    facts = {}
    with fitz.open(path) as doc:
        for k, (page, label, value, unit) in FIELDS[case].items():
            line = source_match(
                doc[page - 1].get_text(sort=True).splitlines(), label, value
            )
            if not line:
                raise ValueError(f"Cannot locate {case} {k} {page}")
            facts[k] = {
                "page": page,
                "row": label,
                "display": value,
                "unit": unit,
                "excerpt": line,
                "source_status": "통과",
            }
        page, phrases = CONTEXT[case]
        compact = "".join(doc[page - 1].get_text(sort=True).split())
        if not all("".join(s.split()) in compact for s in phrases):
            raise ValueError("Period/scope source locator is missing")
    rows = audit(case, facts)
    return {
        "version": "B-dev-1",
        "case_id": case,
        "receipt": meta["receipt_no"],
        "sha256": digest,
        "published": meta.get("published_kst") or meta["published_local_date"],
        "facts": facts,
        "period_scope": {"page": page, "source_phrases": phrases},
        "rules": rows,
        "mandatory": mandatory_items(case, rows),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
    }


def main():
    result = [run(case) for case in FIELDS]
    tests = []
    for case in result:
        for mode, expected in [
            ("original", "통과"),
            ("price_plus_1000", "불일치"),
            ("missing_price", "미확인"),
        ]:
            facts = {k: dict(f) for k, f in case["facts"].items()}
            if mode == "price_plus_1000":
                facts["price"]["display"] = str(
                    number(facts["price"]["display"]) + 1000
                )
            elif mode == "missing_price":
                facts["price"]["source_status"] = "미확인"
            row = audit(case["case_id"], facts)[-1]
            assert row["status"] == expected
            tests.append({"case": case["case_id"], "fixture": mode, **row})
        assert all(r["status"] == "통과" for r in case["rules"])
    thresholds = [
        (["55"], 50, True),
        (["50"], 50, True),
        (["42"], 50, False),
        (["31", "20"], 30, True),
        (["29", "20"], 30, False),
        (["29", "31"], 30, True),
        (["30", "20"], 30, True),
    ]
    for values, cutoff, expected in thresholds:
        assert any(D(v) >= cutoff for v in values) == expected
    dump(
        OUT / "b.json",
        {
            "cases": result,
            "injected_checks": tests,
            "threshold_fixtures": thresholds,
            "review": [
                "pinned receipt, hash, period and physical row locators",
                "recalculated share components, units and displayed-precision intervals",
                "two sets of normal, wrong and missing price inputs; seven inclusive threshold/OR cases",
            ],
        },
    )


if __name__ == "__main__":
    main()
