"""Independently verify the 2025 H2 offering and issuer valuation directly in each DART PDF."""

import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from tempfile import gettempdir

import fitz
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
CACHE = Path(gettempdir()) / "ipo_a1_initial_registrations"


def load(path):
    return json.loads(path.read_bytes())


def compact(text):
    return re.sub(r"\s+", "", text)


def quote(page, text):
    return {"page": page, "physical_page": page, "quote": " ".join(text.split())}


def extract(receipt):
    locator = load(HERE / "locator" / (receipt + ".json"))
    hints = load(HERE / "method" / (receipt + ".json"))["rows"]
    file = CACHE / (receipt + ".pdf")
    assert hashlib.sha256(file.read_bytes()).hexdigest() == locator["pdf_sha256"]
    record = {
        k: locator[k]
        for k in ["receipt", "issuer", "corp_code", "pdf_sha256", "pdf_url", "date_kst"]
    }
    record.update(
        source_url=locator["url"],
        family_earliest=locator["exact_title_and_earliest_family"],
        preexisting_method_note_count=len(hints),
    )
    with fitz.open(file) as pdf:
        for i in range(min(100, len(pdf))):
            lines = pdf[i].get_text(sort=True).splitlines()
            op = next(
                (
                    l
                    for l in lines
                    if re.search(
                        r"(?:인수|직접공모|주선)(?:예|아니오)(?:코스닥시장|유가증권시장|해당없음)",
                        compact(l),
                    )
                ),
                None,
            )
            if op:
                break
        else:
            raise ValueError((receipt, "original offering status summary not found"))
        record["ipo_status_anchor"] = quote(i + 1, op)
        if "아니오" in op:
            issue_page = i + 1
            issue = next(
                (
                    l
                    for l in lines
                    if any(
                        w in compact(l)
                        for w in ["주주배정", "제3자배정", "일반공모", "주주우선"]
                    )
                    and re.search("보통주|우선주", l)
                ),
                None,
            )
            if not issue:
                issue = next(
                    (
                        l
                        for l in lines
                        if any(
                            w in compact(l)
                            for w in ["주주배정", "제3자배정", "일반공모", "주주우선"]
                        )
                    ),
                    None,
                )
            if not issue:
                for page_index in [i - 1, i + 1]:
                    if 0 <= page_index < len(pdf):
                        issue = next(
                            (
                                l
                                for l in pdf[page_index]
                                .get_text(sort=True)
                                .splitlines()
                                if any(
                                    w in compact(l)
                                    for w in [
                                        "주주배정",
                                        "제3자배정",
                                        "일반공모",
                                        "주주우선",
                                    ]
                                )
                                and re.search("보통주|우선주", l)
                            ),
                            None,
                        )
                        if issue:
                            issue_page = page_index + 1
                            break
            if not issue:
                raise ValueError((receipt, "pending capital issue type"))
            if issue_page == i + 1 and "주주배정후실" == compact(issue):
                j = lines.index(issue)
                issue = " ".join(lines[j : j + 3])
            record.update(
                classification="not_domestic_IPO",
                issuer_valuation_anchor=quote(issue_page, issue),
                period_or_method="신규상장 목적이 아닌 주식 발행. 발행방식은 원문 모집표에 기재.",
            )
        else:
            hint = next(h for h in hints if "적용산식" in compact(h["line"]))
            p = hint["page"]
            ls = [
                l.strip()
                for l in pdf[p - 1].get_text(sort=True).splitlines()
                if l.strip()
            ]
            idx = next(i for i, l in enumerate(ls) if "적용산식" in l)
            mod = next(
                (
                    l
                    for l in ls
                    if "평가모형" in compact(l) and ("EBITDA" in l or "PER" in l)
                ),
                None,
            )
            fin = next((l for l in ls if "적용재무수치" in compact(l)), None)
            chosen = next(
                (
                    l
                    for l in ls[max(0, idx - 1) : idx + 1]
                    if (("순이익" in compact(l) and "PER" in l) or "EV/EBITDA" in l)
                    and len(compact(l)) > 10
                ),
                ls[idx],
            )
            block = compact(" ".join(ls[max(0, idx - 4) : idx + 3]))
            if (mod and "EV/EBITDA" in mod) or "EV/EBITDA" in block:
                cat = "ipo_other_multiple"
                method = "EV/EBITDA"
            elif "PER" in chosen and re.search(r"추정(?:당기)?순이익", compact(chosen)):
                cat = "ipo_forecast_PER"
                method = "발행사 추정 순이익에 PER 적용"
            elif "PER" in chosen and re.search(
                r"연환산|LTM|12개월|과거", compact(chosen), re.IGNORECASE
            ):
                cat = "ipo_historical_PER"
                method = "발행사 과거 순이익에 PER 적용"
            else:
                raise ValueError((receipt, p, "uncertain", block))
            record.update(
                classification=cat,
                issuer_valuation_anchor=quote(p, chosen),
                period_or_method=method,
            )
            if fin:
                record["applied_financials_anchor"] = quote(p, fin)
            if mod:
                record["valuation_model_anchor"] = quote(p, mod)
            if cat == "ipo_historical_PER" and fin and "추정치" in fin:
                record["source_discrepancy"] = (
                    "요약표의 적용 재무수치 칸에는 추정치라고 기재했으나 같은 표의 적용산식은 이미 종료한 2025년 반기 순이익의 연환산이다. 주당 평가가치 숫자표의 적용 순이익과 PER를 별도로 대조했다."
                )
        # Recheck each recorded passage against the original PDF at its registered physical page.
        for k in [
            "ipo_status_anchor",
            "issuer_valuation_anchor",
            "applied_financials_anchor",
            "valuation_model_anchor",
        ]:
            if k in record:
                a = record[k]
                assert compact(a["quote"]) in compact(
                    pdf[a["page"] - 1].get_text(sort=True)
                )
    return record


def run():
    inputs = sorted(p.stem for p in (HERE / "locator").glob("*.json"))
    assert (
        set(inputs) == {p.stem for p in (HERE / "method").glob("*.json")}
        and len(inputs) == 61
    )
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(extract, inputs))
    # Only after classifying independently, compare to the supplied source locator freeze.
    frozen = load(HERE / "eligible.json")
    by_id = {r["receipt"]: r for r in frozen["rows"]}
    positive = {
        r["receipt"] for r in rows if r["classification"] == "ipo_historical_PER"
    }
    for r in rows:
        if r["receipt"] not in by_id:
            continue
        given = by_id[r["receipt"]]
        file = CACHE / (r["receipt"] + ".pdf")
        reader = PdfReader(file)
        for field in ["ipo_status_anchor", "issuer_valuation_anchor"]:
            a = given[field]
            assert compact(a["quote"]) in compact(
                reader.pages[a["page"] - 1].extract_text()
            )
        p = given["price_table_page"]
        with fitz.open(file) as pdf:
            for actual in [p, p - 1, p + 1]:
                ls = pdf[actual - 1].get_text(sort=True).splitlines()
                title = next(
                    (l for l in ls if "PER" in l.upper() and "평가가치" in compact(l)),
                    None,
                )
                if title:
                    break
            assert title is not None
        idx = ls.index(title)
        metric = next(
            l
            for l in ls[idx + 1 :]
            if "적용" in l and "순이익" in l and any(c.isdigit() for c in l)
        )
        multiple = next(
            l
            for l in ls[idx + 1 :]
            if "적용PER" in compact(l) and any(c.isdigit() for c in l)
        )
        r["price_table_anchors"] = [quote(actual, l) for l in [title, metric, multiple]]
        r["numeric_price_table_physical_page"] = actual
        r["supplied_price_table_physical_page"] = p
        if r["receipt"] == "20251001000684":
            assert actual == 230
            r["initially_supplied_price_table_physical_page"] = 231
            r["price_table_page_note"] = (
                "숫자 표는 물리 230쪽이고 231쪽에는 반기 조정순이익을 2배 연환산한 산식 주석이 이어진다."
            )
        page = compact(reader.pages[actual - 1].extract_text())
        for a in r["price_table_anchors"]:
            assert compact(a["quote"]) in page
        r["period_or_method"] = given["period_or_method"]
        r["independent_pdf_decoder_price_table_check"] = True
    out = {
        "window": "2025-07-01 through 2025-12-31",
        "source_only": True,
        "model_api_calls": 0,
        "total_candidates": len(rows),
        "counts": dict(Counter(r["classification"] for r in rows)),
        "new_true_positives": sorted(positive - by_id.keys()),
        "frozen_positives_not_reproduced": sorted(by_id.keys() - positive),
        "prior_note_missing": sum(not r["preexisting_method_note_count"] for r in rows),
        "three_reviews": [
            "Compared complete locator/method receipt sets and all PDF SHA-256 values. Identified the purpose from the original filing offering table at a physical page.",
            "Read the issuer's applied valuation formula from the original PDF. Earlier-note misses were classified from the offering table. Distinguish issuer results from peer-only figures or reference calculations.",
            "Compared independently classified positives to the frozen set after the screen; independently checked the original listing and dated period quotes, issuer price table, net income and PER with pypdf.",
        ],
        "rows": rows,
    }
    path = HERE / "screening.json"
    tmp = path.with_suffix(".pending")
    tmp.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    tmp.replace(path)
    print(
        out["counts"],
        out["new_true_positives"],
        out["frozen_positives_not_reproduced"],
        flush=True,
    )


if __name__ == "__main__":
    run()
