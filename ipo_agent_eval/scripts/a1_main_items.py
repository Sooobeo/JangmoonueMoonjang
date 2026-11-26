"""Prepare source-bound main-evaluation packets. No reviewer or grader calls."""

import argparse
import hashlib
import json
import re
from decimal import Decimal as D
from pathlib import Path

import fitz

from scripts.current_validation import COMMON

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/a1_current/official/enrollment_expansion"
DATA = ROOT / "data/a1_main"
MAIN = ROOT / "reports/a1_main/v1"
EXPECTED = "438e093bf95505b2e00fd8a42b76c6b3c553eaeff5bfeb572c6eac5cfc35ab9f"
SCALE = {"원": 1, "천원": 1000, "백만원": 1000000, "주": 1, "천주": 1000, "배": 1}
VALUE_ROWS = {
    "earnings": "이익",
    "per": "PER",
    "shares": "주식수",
    "price": "주당평가가[액격]|주당평가액",
    "equity": "시가총액|기업가치|기업가액",
}


def load(path):
    return json.loads(path.read_bytes())


def dump(path, value):
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf8")
    if path.exists() and path.read_bytes() == content:
        return
    if (MAIN / "freeze.json").exists() or (MAIN / "freeze_manifest.json").exists():
        raise RuntimeError("Cannot replace a frozen input")
    path.parent.mkdir(parents=True, exist_ok=True)
    draft = path.with_suffix(".tmp")
    draft.write_bytes(content)
    draft.replace(path)


def compact(s):
    return "".join(s.split())


def quoted(page, text):
    return {"page": page, "quote": text.strip()}


def value_row(factspec, field, pages, p):
    # Select the reviewed printed cell together with its row label. The adjacent
    # page can carry the first or last part of the issuer table.
    val = factspec["value"]
    v = re.escape(f"{D(val):,f}")
    number = re.compile(r"(?<![\d,.])" + v + r"(?![\d,]|\.\d)")
    matches = []
    for n in [p, p - 1, p + 1]:
        for line in pages[n].splitlines():
            if number.search(line) and re.search(
                VALUE_ROWS[field], compact(line), re.IGNORECASE
            ):
                # A peer aggregate and the issuer input often have the same
                # printed number. Prefer the row entered into the issuer formula.
                label = line.strip().split("  ")[0]
                rank = (
                    0
                    if field != "per" or ("적용" in label and "평균" not in label)
                    else 1,
                    0 if re.search(r"\s{2,}", line.strip()) else 1,
                )
                matches.append((rank, dict(factspec, **quoted(n, line))))
    if matches:
        return min(matches, key=lambda entry: entry[0])[1]
    raise ValueError(f"Unresolved {field} {val} at {p}")


def interval(f):
    # Printed share counts in single shares are integers. Other displayed
    # cells preserve the precision shown, including trailing decimal zeros.
    v = D(f["value"])
    factor = D(SCALE[f["unit"]])
    e = D(0) if f["unit"] == "주" else D(1).scaleb(v.as_tuple().exponent) / 2
    return v * factor, (v - e) * factor, (v + e) * factor


def consistency(kind, calc, low, high, observed, formula, refs):
    value, lo, hi = interval(observed)
    return {
        "check": kind,
        "formula": formula,
        "estimate": str(calc),
        "possible_at_print_precision": [str(low), str(high)],
        "reported": str(value),
        "difference": str(calc - value),
        "status": "통과" if low <= hi and lo <= high else "불일치",
        "pages": sorted(set(refs)),
    }


def per_rows(pages, p, count):
    for n in (p, p + 1, p - 1):
        lines = [s.strip() for s in pages[n].splitlines() if s.strip()]
        for j, line in enumerate(lines):
            cells = re.split(r"\s{2,}", line.strip())
            if "PER" not in cells[0].upper() or "평균" in cells[0]:
                continue
            tokens = [
                m.group(1)
                for cell in cells[1:]
                if (m := re.fullmatch(r"(\d+(?:\.\d+)?)\s*배?", cell))
            ]
            if len(tokens) == count:
                return quoted(n, line), tokens
            if len(cells) == 1 and j + 1 < len(lines):
                next_values = re.split(r"\s{2,}", lines[j + 1])
                if len(next_values) == count and all(
                    re.fullmatch(r"\d+\.\d+", v) for v in next_values
                ):
                    return quoted(n, line + "\n" + lines[j + 1]), next_values
    return None, []


def band_rows(pages, p):
    for n in range(p, p + 5):
        for line in pages[n].splitlines():
            if "할인율" not in line or "~" not in line:
                continue
            rates = re.findall(r"(\d+(?:\.\d+)?)\s*%", line)
            if len(rates) != 2 or len(line.strip()) > 110:
                continue
            for k in (n, n + 1):
                for other in pages[k].splitlines():
                    if not re.search(
                        "희망.*공모|공모.*희망|공모가액", compact(other)
                    ) or not re.search("[~∼]", other):
                        continue
                    values = re.findall(
                        r"(?<![\d,.])\d{1,3}(?:[,.]\d{3})+(?![\d,.])", other
                    )
                    if (
                        len(values) == 2
                        and len(other.strip()) < 105
                        and "%" not in other
                    ):
                        return (
                            quoted(n, line),
                            sorted(rates, key=D, reverse=True),
                            quoted(k, other),
                            [v.replace(",", "").replace(".", "") for v in values],
                        )
    return None, [], None, []


def band_endpoints(price, rates, band):
    endpoints = []
    for rate, offer in zip(rates, band):
        discount = D(rate)
        implied = (1 - D(offer) / price) * 100
        endpoints.append(
            {
                "printed_discount_pct": rate,
                "offer_krw": offer,
                "calculated_offer": str(price * (1 - discount / 100)),
                "implied_discount_pct": str(implied),
                "matches_printed_precision": abs(implied - discount)
                <= D(1).scaleb(discount.as_tuple().exponent) / 2,
            }
        )
    return endpoints


def calculate(
    facts, peer_evidence, multiples, rate_evidence, rates, band_evidence, band
):
    earnings, elo, ehi = interval(facts["earnings"])
    per, plo, phi = interval(facts["per"])
    shares, slo, shi = interval(facts["shares"])
    equity, low, high = earnings * per, elo * plo, ehi * phi
    source_pages = [f["page"] for f in facts.values()]
    checks = []
    if multiples:
        vals = [D(v) for v in multiples]
        mid = sum(vals) / len(vals)
        radius = sum(D(1).scaleb(v.as_tuple().exponent) / 2 for v in vals) / len(vals)
        checks.append(
            consistency(
                "비교 PER 산술평균",
                mid,
                mid - radius,
                mid + radius,
                facts["per"],
                "sum(peer PER) / n",
                [peer_evidence["page"], facts["per"]["page"]],
            )
        )
    else:
        checks.append(
            {
                "check": "비교 PER 산술평균",
                "status": "미확인",
                "reason": "개별 PER 행의 모든 수치를 단일 행에서 대조할 수 없음",
            }
        )
    original = equity / shares
    if "equity" in facts:
        checks.append(
            consistency(
                "이익과 평가시가총액",
                equity,
                low,
                high,
                facts["equity"],
                "earnings × PER",
                source_pages,
            )
        )
        equity, low, high = interval(facts["equity"])
    check = consistency(
        "주당 평가가액",
        equity / shares,
        low / shi,
        high / slo,
        facts["price"],
        "평가시가총액 ÷ 주식수" if "equity" in facts else "이익 × PER ÷ 주식수",
        source_pages,
    )
    check["earnings_per_share_route"] = str(original)
    checks.append(check)
    if band:
        price = D(facts["price"]["value"])
        endpoints = band_endpoints(price, rates, band)
        checks.append(
            {
                "check": "할인율과 밴드",
                "formula": "1 − 공모가 / 공시 주당 평가가액",
                "endpoints": endpoints,
                "status": "통과"
                if all(x["matches_printed_precision"] for x in endpoints)
                else "불일치",
                "pages": [
                    facts["price"]["page"],
                    rate_evidence["page"],
                    band_evidence["page"],
                ],
            }
        )
    else:
        checks.append(
            {
                "check": "할인율과 밴드",
                "status": "미확인",
                "reason": "동일 표 내 할인율·밴드의 양 끝값 형식을 확인해야 함",
            }
        )
    return checks


def ordered(*seqs):
    return list(dict.fromkeys(v for seq in seqs for v in seq if v is not None))


def build(row, spec, source, extra, full):
    receipt = row["receipt"]
    p, t = spec["valuation_page"], spec["peer_table_page"]
    pages = full
    facts = {
        key: value_row(value, key, pages, p) for key, value in source["facts"].items()
    }
    peer_ev, multiples = per_rows(pages, t, len(spec["peers"]))
    rate_ev, rates, band_ev, band = band_rows(pages, p)
    checks = calculate(facts, peer_ev, multiples, rate_ev, rates, band_ev, band)
    earnings_review = extra["earnings_reconciliation"]
    earnings_parts = earnings_review["components"]
    source_scale = D(SCALE[earnings_review["unit"]])
    annualize = D(earnings_review["annualization_numerator"]) / D(
        earnings_review["annualization_denominator"]
    )
    recalculated = (
        sum(D(r["signed_value"]) for r in earnings_parts) * source_scale * annualize
    )
    uncertainty = len(earnings_parts) * source_scale * annualize / 2
    detail = consistency(
        "적용 이익과 동일 기간 원문 손익",
        recalculated,
        recalculated - uncertainty,
        recalculated + uncertainty,
        facts["earnings"],
        "동일 기간 부호 있는 원문 행 합계 × 단위 환산 × 공시 연환산 계수",
        [facts["earnings"]["page"]] + [r["page"] for r in earnings_parts],
    )
    detail["reconciliation"] = earnings_review
    if extra["attribution_category"] is None and detail["status"] == "불일치":
        detail.update(
            status="미확인",
            reason="공시 적용 귀속이 확정되지 않아 대조 차이의 원인을 단정할 수 없음",
        )
    checks.append(detail)
    components = extra["share_components"]
    denominator = sum(D(c["shares"]) for c in components)
    if components:
        checks.append(
            consistency(
                "적용 주식 수 구성",
                denominator,
                denominator,
                denominator,
                facts["shares"],
                "기발행 + 신주 + 적용 희석분, 구주매출 제외",
                [r["page"] for r in components] + [facts["shares"]["page"]],
            )
        )
    if total := extra.get("printed_share_total"):
        checks.append(
            {
                "check": "구성표 합계 행 대조",
                "components_sum": str(denominator),
                "status": "통과" if D(total["value"]) == denominator else "불일치",
                "evidence": total,
            }
        )
    if extra.get("band_reference"):
        price_ref = extra["band_reference"]
        checks.append(
            {
                "check": "할인표 기준가와 주당 평가가액 대조",
                "status": "통과"
                if price_ref["value"] == facts["price"]["value"]
                else "불일치",
                "valuation_price": facts["price"]["value"],
                "discount_table_price": price_ref["value"],
                "discount_table_endpoints": band_endpoints(
                    D(price_ref["value"]), rates, band
                ),
                "evidence": price_ref,
            }
        )
    for key in ("period", "attribution"):
        ref = extra.get(key)
        established = bool(extra.get(key + "_category"))
        checks.append(
            {
                "check": "적용 이익 기간"
                if key == "period"
                else "적용 이익 회계상 귀속",
                "status": "통과" if established else "미확인",
                "fact": extra.get(key + "_category"),
                "evidence": ref,
            }
        )
    items = []
    evidence_index = {}
    raw = lambda e: None if e is None else {k: e[k] for k in ("page", "quote")}

    def add(
        family, question, target, choice, refs, other, category=None, comparable=False
    ):
        refs = [raw(r) for r in refs if r]
        if not refs:
            raise ValueError((receipt, question, "no source"))
        cites = []
        for ref in refs:
            eid = (
                f"D{ref['page']:03}."
                + hashlib.sha256(ref["quote"].encode()).hexdigest()[:10]
            )
            assert compact(ref["quote"]) in compact(pages[ref["page"]]), (receipt, eid)
            record = {"id": eid, **ref}
            evidence_index[eid] = record
            if record not in cites:
                cites.append(record)
        items.append(
            {
                "id": f"{receipt}-{len(items) + 1:02}",
                "family": family,
                "target": target,
                "question": question,
                "original_choice": choice,
                "original_category": category,
                "role_applicability": {
                    "A0": True,
                    "C": comparable,
                    "independent_grading": True,
                },
                "evidence": cites,
                "pages": ordered([r["page"] for r in refs], other),
            }
        )

    anchor = extra["period"]
    att = extra.get("attribution")
    place = extra.get("accounting_pages", [])
    price_rule = extra["price_rule"]
    reg_note = extra["shares_note"]
    inc = facts["earnings"]
    basis_pages = [p - 1, p, p + 1]
    period = extra["period_category"]
    add(
        *COMMON[0],
        row["issuer"],
        anchor["quote"],
        [anchor, inc, *earnings_parts],
        basis_pages + place,
        period,
        True,
    )
    add(
        *COMMON[1],
        row["issuer"],
        (att or anchor)["quote"],
        [att, anchor, inc],
        basis_pages + place,
        extra.get("attribution_category"),
        True,
    )
    add(
        *COMMON[2],
        "최종 비교기업",
        price_rule["quote"],
        [price_rule, peer_ev],
        [t - 1, t, t + 1],
    )
    add(
        *COMMON[3],
        "최종 비교기업",
        facts["per"]["quote"],
        [peer_ev, facts["per"]],
        [t - 1, t, t + 1],
    )
    add(
        *COMMON[4],
        row["issuer"],
        facts["shares"]["quote"],
        [facts["shares"], reg_note, *components, total],
        basis_pages,
    )
    add(
        *COMMON[5],
        row["issuer"],
        facts["price"]["quote"],
        [facts["price"], inc, facts["per"], facts["shares"], facts.get("equity")],
        basis_pages,
    )
    add(
        *COMMON[6],
        row["issuer"],
        (band_ev or facts["price"])["quote"],
        [band_ev, rate_ev, extra.get("band_reference"), facts["price"]],
        range(p, p + 4),
    )
    for adj in extra["adjustments"]:
        add(
            "J1",
            adj["target"] + "의 적용 이익 조정 근거",
            adj["target"],
            adj["evidence"]["quote"],
            [adj["evidence"], inc],
            ordered(basis_pages, adj.get("notes", []), place),
        )
    for peer in spec["peers"]:
        d = extra["peer_evidence"][peer]
        add(
            "J2",
            peer + "의 사업 비교 적합성",
            peer,
            "공시 최종 PER 산정에 포함",
            [d["header"], d["business"], peer_ev],
            ordered([t, t + 1], extra["issuer_business_pages"]),
            comparable=True,
        )

    root = MAIN / "issuers" / receipt
    neutral = [
        {
            "item_id": r["id"],
            "question": r["question"],
            "question_type": r["family"],
            "pages": r["pages"],
        }
        for r in items
    ]
    allowed = sorted({n for item in items for n in item["pages"]})
    passages = {str(n): pages[n] for n in allowed}
    impact = {i["id"]: None for i in items}
    alternatives = []
    best_priorities = {}
    for alt in extra.get("alternatives", []):
        rec = {
            "formula": alt["formula"],
            "original_item": items[alt["index"]]["id"],
            "evidence": alt["evidence"],
            "alternative_per_share": alt["alternative_per_share"],
            "eligibility": alt["eligibility"],
            "priority": alt["priority"],
        }
        rec["absolute_fraction"] = float(
            abs(D(alt["alternative_per_share"]) - D(facts["price"]["value"]))
            / D(facts["price"]["value"])
        )
        alternatives.append(rec)
        if alt["eligibility"] == "적격":
            item_id = rec["original_item"]
            key = (int(rec["priority"] != "오류 입력 수정"), rec["absolute_fraction"])
            if item_id not in best_priorities or key < best_priorities[item_id]:
                best_priorities[item_id] = key
                impact[item_id] = rec["absolute_fraction"]
    b = {
        "receipt": receipt,
        "pdf_sha256": row["pdf_sha256"],
        "facts": facts,
        "peer_multiples": multiples,
        "peer_multiple_row": peer_ev,
        "discount_row": rate_ev,
        "band_row": band_ev,
        "share_components": components,
        "rules": checks,
        "price_impact_fraction": impact,
        "alternatives": alternatives,
        "mandatory": [items[i]["id"] for i in extra.get("mandatory_indexes", [])],
        "qualitative_review": extra.get("b_review", ""),
    }
    dump(root / "items.json", items)
    dump(root / "catalog.json", {"pages": passages, "evidence": evidence_index})
    dump(root / "b.json", b)
    dump(
        root / "a0.json",
        {
            "items": [
                dict(n, original_choice=r["original_choice"])
                for n, r in zip(neutral, items)
            ],
            "original_physical_pages": passages,
        },
    )
    dump(root / "grading.json", {"items": neutral, "pages": passages})
    dump(
        root / "preparation_items.json",
        {
            "receipt": receipt,
            "items": len(items),
            "peer_count": len(spec["peers"]),
            "adjustment_count": len(extra["adjustments"]),
            "verified_source_sha256": row["pdf_sha256"],
            "full_j1_adjustment_review": True,
            "final_per_peer_order_verified": True,
            "b_valuation_cells_verified": True,
            "checks": checks,
            "gaps": extra.get("gaps", []),
        },
    )
    return len(items)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt")
    args = parser.parse_args()
    path = BASE / "roster.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError("Roster digest changed")
    specs = load(DATA / "valuation_sources.json")
    inputs = load(DATA / "valuation_rows.json")
    extras = load(DATA / "evidence_locations.json")
    for row in load(path)["rows"]:
        key = row["receipt"]
        if args.receipt and key != args.receipt:
            continue
        pdf = BASE / row["pdf_file"]
        if hashlib.sha256(pdf.read_bytes()).hexdigest() != row["pdf_sha256"]:
            raise ValueError("Source PDF digest changed: " + key)
        needed = extras[key]["read_pages"]
        with fitz.open(pdf) as doc:
            pages = {n: doc[n - 1].get_text(sort=True) for n in needed}
        count = build(row, specs[key], inputs[key], extras[key], pages)
        print(key, count, flush=True)


if __name__ == "__main__":
    main()
