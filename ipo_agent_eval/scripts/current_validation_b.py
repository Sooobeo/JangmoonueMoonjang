"""Validate physical source rows and price arithmetic in the four validation originals."""

from decimal import Decimal as D

from scripts.current_b import OUT, dump, source_match
from scripts.current_validation import cases, prepare

# Primary filing row labels, printed amounts in original units. The price in the
# discount table is a separate observation, not an input correction.
VALUES = {
    "GIGAVIS": (
        ("적용 당기순이익", "37,848"),
        ("적용 PER(배)", "21.80"),
        ("적용 주식수(주)", "12,675,758"),
        ("주당 평가가액(원)", "65,082"),
        ("평가 시가총액", "824,968"),
        "백만원",
    ),
    "TRUEN": (
        ("2022년 당기순이익", "7,633"),
        ("적용 PER 배수", "22.59"),
        ("적용 주식수", "10,999,650"),
        ("주당 평가가액", "15,680"),
        ("평가 시가총액", "172,471"),
        "백만원",
    ),
    "MANYO": (
        ("적용 당기순이익", "17,297,237,363"),
        ("적용 주식수", "16,378,260"),
        ("적용 PER", "21.15"),
        ("비교가치 주당 평가가액", "22,337"),
        None,
        "원",
    ),
    "PHILENERGY": (
        ("적용 당기순이익", "15,745,462,646"),
        ("적용 PER 배수", "27.9"),
        ("적용 주식수", "10,611,793"),
        ("주당 평가가액", "41,404"),
        None,
        "원",
    ),
}


def build(spec):
    pack = prepare(spec)
    case = pack["case"]
    page = spec["price_table_pdf_page"]
    lines = pack["pages"][str(page)].splitlines()
    earnings, per, shares, price, equity, unit = VALUES[case]
    if case == "MANYO":
        per, shares = shares, per
    rows = {}
    for key, field in [
        ("earnings", earnings),
        ("per", per),
        ("shares", shares),
        ("price", price),
        ("equity", equity),
    ]:
        if field:
            evidence = source_match(lines, *field)
            if not evidence:
                raise ValueError((case, field))
            rows[key] = {
                "page": page,
                "row": field[0],
                "value": field[1],
                "excerpt": evidence,
            }

    def num(field):
        return D(rows[field]["value"].replace(",", ""))

    scale = 10**6 if unit == "백만원" else 1
    predicted = (
        num("equity") * scale if equity else num("earnings") * scale * num("per")
    ) / num("shares")
    # Displayed numerator/multiple carry half their last place of uncertainty.
    error = D(".5") + (
        (
            D(".5") * scale
            if equity
            else num("earnings")
            * scale
            * D(1).scaleb(num("per").as_tuple().exponent)
            / 2
        )
        / num("shares")
    )
    delta = predicted - num("price")
    status = "통과" if abs(delta) <= error else "불일치"
    checks = [
        {
            "rule": "price_at_print_precision",
            "status": status,
            "delta": str(delta),
            "tolerance": str(error),
            "recalculated": str(predicted),
        }
    ]
    if case == "TRUEN":
        loc = source_match(lines, "상대가치 주당 평가가액", "15,578")
        assert loc
        checks.append(
            {
                "rule": "discount_table_price_consistency",
                "status": "불일치",
                "page": page,
                "excerpt": loc,
                "price_difference_krw": 102,
                "fraction_of_calculated": str(D(102) / num("price")),
                "materiality": "price discrepancy below 5%; qualitative impact assessed separately",
            }
        )
    if case == "MANYO":
        assert source_match(lines, "주당 평가가액", "22.337")
        checks.append(
            {
                "rule": "punctuation",
                "status": "표기 상이",
                "page": page,
                "note": "22.337 printed in valuation table; separate discount table gives 22,337원.",
            }
        )
    return {
        "mandatory": [],
        "sha256": pack["pdf_sha256"],
        "receipt": pack["receipt"],
        "earnings_unit": unit,
        "facts": rows,
        "rules": checks,
        "price_impact_fraction": {},
        "alternative_coverage": "독립 적격성이 미확정인 대안은 미산출로 고정. 규칙과 AI가 공유.",
        "scope": "주당가액과 표 간 일관성에 대한 원문 대조. 그 외 정성 중대 쟁점은 독립 판정에서 평가.",
    }


if __name__ == "__main__":
    result = {s["case_id"].split("-")[0]: build(s) for s in cases()}
    dump(OUT / "validation/b.json", result)
