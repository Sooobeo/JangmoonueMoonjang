"""Outcome-blind 2024 H1 DART registration inventory and primary PDF screening."""

import argparse
import hashlib
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import fitz
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from scripts import official_enrollment as common
from scripts.current_b import OUT, dump
from scripts.current_live import load
from scripts.screen_a1_first_filings import CACHE, TITLE

HERE = OUT / "official/enrollment_expansion/2024H1"
SPAN = {"startDate": "20240101", "endDate": "20240630"}
ELIGIBLE = {
    "20240305000170": (
        297,
        "적용순이익은 동사의 2023년 3분기 연환산 기준의 적용 순이익",
        "적용 PER 11.33배",
        "2023년 3분기 지배순이익 4,820백만원에 세무조사 법인세 3,511백만원을 더한 조정이익 8,331백만원을 연환산, 11,107,927,455원에 PER 11.33배 적용.",
    ),
    "20240520000263": (
        279,
        "적용순이익은 2024년 1분기 기준 최근 4개분기의 당기순이익의 합계",
        "적용 PER (D) 39.25 배",
        "2024년 1분기말 LTM 순이익 106,595백만원에 PER 39.25배 적용.",
    ),
    "20240621000344": (
        250,
        "적용 순이익은 2024년 1분기 기준 최근 4개분기의 당기순이익의 합계",
        "적용 PER (D) 17.27",
        "2024년 1분기말 LTM 순이익 4,392,286천원에 PER 17.27배 적용.",
    ),
}


def inventory():
    f = HERE / "inventory.json"
    if f.exists():
        return load(f)
    with patch.dict(common.PARAMS, SPAN):
        first = common.listing(1)
        size = (first["reported_total"] + 99) // 100
        with ThreadPoolExecutor(max_workers=5) as pool:
            pages = [first, *pool.map(common.listing, range(2, size + 1))]
    allrows = sorted(
        (r for p in pages for r in p["records"]), key=lambda r: r["receipt"]
    )
    assert (
        len(allrows) == len({r["receipt"] for r in allrows}) == first["reported_total"]
    )
    assert all(p["reported_total"] == len(allrows) for p in pages)
    nm, ids, codes = common.prior_roster()
    q4 = load(OUT / "official/enrollment/screened_all.json")["rows"]
    codes.update(r["corp_code"] for r in q4)
    nm.update(common.key(r["issuer"]) for r in q4)
    seen = set()
    for r in allrows:
        name = common.key(r["issuer"])
        if r["title"] != TITLE:
            flag = "other_title"
        elif r["corp_code"] in codes or name in nm or r["receipt"] in ids:
            flag = "previous18_or_q4_39"
        elif any(w in name for w in ["spac", "스팩", "기업인수목적"]):
            flag = "SPAC"
        elif r["withdrawal_notice"]:
            flag = "withdrawn_title"
        elif r["corp_code"] in seen:
            flag = "later_same_corporate"
        else:
            flag = "primary_pdf_queue"
            seen.add(r["corp_code"])
        r["disposition"] = flag
    info = {
        "window": SPAN,
        "listing_scope": "Official DART C001, all pages, asc date. Original unamended equity filings only. Exclude identity overlap with earlier 18 and 39 by corporate code or issuer name and SPAC/withdrawn/same issuer duplicates.",
        "listing_pages": [
            {k: v for k, v in p.items() if k != "records"} for p in pages
        ],
        "counts": dict(Counter(r["disposition"] for r in allrows)),
        "rows": allrows,
    }
    dump(f, info)
    return info


def download(row):
    f = HERE / "document_screen" / (row["receipt"] + ".json")
    if f.exists() and load(f).get("pdf_sha256"):
        return
    result = common.inspect(row)
    pending = f.with_suffix(f".{os.getpid()}.pending")
    dump(pending, result)
    pending.replace(f)
    print(row["receipt"], row["issuer"], result["screen_status"], flush=True)


def docs(begin, limit):
    rows = [r for r in inventory()["rows"] if r["disposition"] == "primary_pdf_queue"]
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(download, rows[begin : begin + limit]))


def history(row, destination=None):
    f = (
        (destination if destination is not None else HERE)
        / "corporate_history"
        / (row["receipt"] + ".json")
    )
    if f.is_file():
        return load(f)
    results = []
    links = []
    with httpx.Client(timeout=35, follow_redirects=True) as client:
        # DART's search accepts up to ten years at once; require the positive-control original too.
        for start, end in [
            ("19990101", "20081231"),
            ("20090101", "20181231"),
            ("20190101", row["receipt"][:8]),
        ]:
            expected = None
            page = 1
            seen_period = []
            while True:
                params = {
                    "currentPage": page,
                    "maxResults": 100,
                    "publicType": "C001",
                    "sort": "date",
                    "series": "asc",
                    "startDate": start,
                    "endDate": end,
                    "textCrpCik": row["corp_code"],
                }
                res = client.get(common.LIST_ENDPOINT, params=params)
                res.raise_for_status()
                soup = BeautifulSoup(res.content, "html.parser", from_encoding="utf8")
                text = soup.get_text(" ", strip=True)
                count = re.search(r"총\s*([0-9,]+)건", text)
                if not count and "조회 결과가 없습니다" not in text:
                    raise ValueError("Unverified DART corporate history")
                total = int(count[1].replace(",", "")) if count else 0
                assert expected is None or total == expected
                expected = total
                links.append(
                    {
                        "url": str(res.url),
                        "response_sha256": hashlib.sha256(res.content).hexdigest(),
                        "total_in_interval": total,
                    }
                )
                for a in soup.select('a[href*="rcpNo="]'):
                    tr = a.find_parent("tr")
                    corp = tr.find("a", onclick=re.compile("openCorpInfoNew"))
                    assert "'" + row["corp_code"] + "'" in corp["onclick"]
                    receipt = re.search(r"rcpNo=(\d{14})", a["href"])[1]
                    seen_period.append(receipt)
                    results.append(
                        {
                            "receipt": receipt,
                            "title": a.get_text(" ", strip=True),
                            "withdrawn_flag": bool(tr.select_one(".tagCom_chul_other")),
                        }
                    )
                if page * 100 >= total:
                    break
                page += 1
            assert len(set(seen_period)) == len(seen_period) == total
    assert (
        sum(r["receipt"] == row["receipt"] and r["title"] == TITLE for r in results)
        == 1
    )
    preceding = [
        r
        for r in results
        if r["receipt"] < row["receipt"]
        and ("철회" in r["title"] or r["title"] == TITLE or r["withdrawn_flag"])
    ]
    result = {
        "corp_code": row["corp_code"],
        "receipt": row["receipt"],
        "window_start": "19990101",
        "window_end": row["receipt"][:8],
        "validated_target_in_final_window": True,
        "queries": links,
        "prior_relevant_title_records": preceding,
        "row_count": len(results),
    }
    dump(f, result)
    return result


def positive_report():
    rows = []
    for receipt, (n, meaning, table, period) in sorted(ELIGIBLE.items()):
        doc = load(HERE / "document_screen" / (receipt + ".json"))
        prior = history(doc)
        assert (
            not prior["prior_relevant_title_records"]
            and doc["exact_title_and_earliest_family"]
        )
        file = CACHE / (receipt + ".pdf")
        assert hashlib.sha256(file.read_bytes()).hexdigest() == doc["pdf_sha256"]
        with fitz.open(file) as pdf:
            compact = lambda v: re.sub(r"\s+", "", v)
            text = compact(pdf[n - 1].get_text(sort=True))
            assert compact(meaning) in text and compact(table) in text, (receipt, n)
            proof = None
            for p, pg in enumerate(pdf, 1):
                if p > 80:
                    break
                t = compact(pg.get_text(sort=True))
                m = re.search(
                    r"본주식은(?:한국거래소내)?(?:코스닥시장|유가증권시장)상장을목적으로(?:모집|공모)|당사는금번(?:유가증권시장|코스닥시장)상장을위한공모|신규상장예비심사승인을받았습니다",
                    t,
                )
                if m:
                    proof = {"page": p, "physical_page": p, "quote": m[0]}
                    break
            assert proof is not None
        item = {
            k: doc[k]
            for k in [
                "receipt",
                "issuer",
                "corp_code",
                "date_kst",
                "pdf_sha256",
                "pdf_url",
                "pdf_pages",
            ]
        }
        item.update(
            dart_url=doc["url"],
            source_url=doc["url"],
            original_pdf_cache=str(file),
            family_earliest_confirmed=True,
            ipo_status_anchor=proof,
            issuer_valuation_anchor={"page": n, "physical_page": n, "quote": meaning},
            per_table_anchor={"page": n, "physical_page": n, "quote": table},
            period_or_method=period,
            classification="ipo_historical_PER",
            historical_issuer_earnings_PER=True,
            is_original_ipo_filing_in_this_family=True,
            corporate_history_file=(HERE / "corporate_history" / (receipt + ".json"))
            .relative_to(common.ROOT)
            .as_posix(),
            prior_withdrawals_or_earlier_originals=[],
        )
        rows.append(item)
    target = HERE / "eligible.json"
    tmp = target.with_suffix(".tmp")
    dump(
        tmp,
        {
            "period": SPAN,
            "rows": rows,
            "three_checks": [
                "DART exact-title earliest family and separately corporate C001 history queried 1999 to receipt inclusive, with original as positive control.",
                "Confirmed listing purpose and issuer's actual historical earnings plus applied PER multiple on the priced offering, reviewed alternate/reference tables and compared issuer against peer periods.",
                "Rechecked exact physical-page anchors and SHA256 and excluded original 18 and prior Q4 39 corporations before dispatch.",
            ],
        },
    )
    tmp.replace(target)
    print(len(rows), "verified", flush=True)


def scan_disposition(row):
    path = HERE / "decisions" / (row["receipt"] + ".json")
    if path.exists() and load(path)["classification"] not in {
        "unresolved",
        "incomplete",
    }:
        return
    candidate = HERE / "document_screen" / (row["receipt"] + ".json")
    if not candidate.exists():
        return
    record = load(candidate)
    result = {**row, "classification": "incomplete", "anchors": []}
    if not record.get("pdf_sha256"):
        result.update(note=record.get("reason"))
        dump(path, result)
        return
    result.update(
        pdf_sha256=record["pdf_sha256"],
        pdf_url=record["pdf_url"],
        exact_title_and_earliest_family=record["exact_title_and_earliest_family"],
        classification="unresolved",
    )
    if row["receipt"] in ELIGIBLE:
        result.update(
            classification="ipo_historical_PER",
            anchors=[
                {
                    "page": ELIGIBLE[row["receipt"]][0],
                    "quote": ELIGIBLE[row["receipt"]][1],
                }
            ],
        )
        dump(path, result)
        return
    with fitz.open(CACHE / (row["receipt"] + ".pdf")) as doc:
        # First determine offering type from the DART offer-summary table (including existing
        # issuers subject to listing rules). Historical past capital increases are not evidence.
        for p in range(min(80, len(doc))):
            text = doc[p].get_text(sort=True)
            flat = "".join(text.split())
            neg = re.search(
                r"(?:인수|직접공모|주선|모집주선)아니오해당없음해당없음", flat
            )
            foreign = re.search(
                r"(?:나스닥|뉴욕증권거래소).{0,18}상장(?:을)?(?:목적|예정)", flat
            )
            if neg or foreign:
                result.update(
                    classification="not_domestic_IPO",
                    anchors=[{"page": p + 1, "quote": (neg or foreign)[0]}],
                )
                break
        if result["classification"] == "unresolved":
            per = []
            forecast = []
            other = []
            for p in range(
                record["underwriter_physical_range"][0],
                record["underwriter_physical_range"][1] + 1,
            ):
                text = doc[p - 1].get_text(sort=True)
                flat = "".join(text.split())
                matched = re.search(
                    r"(?:상기|상기에서)(?:와같이산출한)?(?:PBR|PSR|EV/EBITDA)(?:상대가치)?(?:산출|평가)결과를적용한.{0,65}?(?:주당평가가액|희망공모가액)|(?:PBR|PSR|EV/EBITDA)에의한.{0,24}평가가치",
                    flat,
                    re.IGNORECASE,
                )
                if matched:
                    other.append({"page": p, "quote": matched[0]})
                mt = re.search(
                    r"(?:동사의주당평가가액은동사의|주당평가가액산출을위하여(?:동사의)?|적용당기순이익은)20[2-3]\d년(?:의)?추정(?:주당|당기)?순이익",
                    flat,
                )
                ft = re.search(
                    r"20[2-3]\d년추정(?:당기)?순이익(?:의)?(?:현재가치|현가)", flat
                )
                if mt:
                    forecast.append(
                        {"page": p, "quote": mt[0], "kind": "issuer_valuation"}
                    )
                elif ft and re.search(r"적용PER|주당평가가액", flat):
                    forecast.append(
                        {"page": p, "quote": ft[0], "kind": "issuer_valuation_table"}
                    )
                if re.search(r"적용PER|PER에의한", flat, re.IGNORECASE) and re.search(
                    r"주당평가(?:가액|액)|평가시가총액", flat
                ):
                    per.append(p)
            if other:
                result.update(classification="ipo_other_multiple", anchors=other[:3])
            elif forecast:
                result.update(classification="ipo_forecast_PER", anchors=forecast[:3])
            else:
                result["possible_PER_pages"] = per
    dump(path, result)


def all_dispositions():
    data = inventory()
    queue = [r for r in data["rows"] if r["disposition"] == "primary_pdf_queue"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(scan_disposition, queue))
    reports = [load(f) for f in sorted((HERE / "decisions").glob("*.json"))]
    dump(
        HERE / "screening.json",
        {
            "listing_counts": data["counts"],
            "counts": dict(Counter(r["classification"] for r in reports)),
            "primary_pdf_queue": len(queue),
            "pending": [
                r["receipt"]
                for r in queue
                if r["receipt"] not in {v["receipt"] for v in reports}
            ],
            "rows": reports,
        },
    )
    print(dict(Counter(r["classification"] for r in reports)), flush=True)


def final_audit():
    source = inventory()
    screened = load(HERE / "screening.json")
    eligible = load(HERE / "eligible.json")["rows"]
    assert (
        len(source["rows"]) == 673
        and not screened["pending"]
        and len(screened["rows"]) == 62
    )
    assert not any(
        r["classification"] in {"unresolved", "incomplete"} for r in screened["rows"]
    )
    assert {r["receipt"] for r in eligible} == {
        r["receipt"]
        for r in screened["rows"]
        if r["classification"] == "ipo_historical_PER"
    }
    checks = []
    for r in screened["rows"]:
        p = CACHE / (r["receipt"] + ".pdf")
        assert hashlib.sha256(p.read_bytes()).hexdigest() == r["pdf_sha256"]
        with fitz.open(p) as doc:
            for a in r["anchors"]:
                assert "".join(a["quote"].split()) in "".join(
                    doc[a["page"] - 1].get_text(sort=True).split()
                )
        checks.append(
            {
                "receipt": r["receipt"],
                "issuer": r["issuer"],
                "verified_document_sha256": r["pdf_sha256"],
                "verified_primary_anchors": len(r["anchors"]),
            }
        )
    positive_checks = []
    for r in eligible:
        pdf = PdfReader(r["original_pdf_cache"])
        for k in ["ipo_status_anchor", "issuer_valuation_anchor", "per_table_anchor"]:
            a = r[k]
            assert "".join(a["quote"].split()) in "".join(
                (pdf.pages[a["page"] - 1].extract_text() or "").split()
            )
            positive_checks.append(
                {
                    "receipt": r["receipt"],
                    "field": k,
                    "page": a["page"],
                    "matched": "pypdf and PyMuPDF",
                }
            )
    dump(
        HERE / "checks.json",
        {
            "window": SPAN,
            "counts": screened["counts"],
            "three_reviews": [
                {
                    "round": 1,
                    "verification": "Reconcile pagination and corporate identity metadata; earliest DART registration family and prior C001 corporate queries for every inclusion.",
                },
                {
                    "round": 2,
                    "verification": "Tie historical issuer earnings and actual PER price table to initial domestic offering; independent checks of PBR reference-only PER (Oh Sang) and peer historical vs issuer forecast calculations.",
                },
                {
                    "round": 3,
                    "verification": "Re-read every disposition's cited original physical page and hash of every downloaded PDF; separately verify three independent source anchors per inclusion with pypdf.",
                },
            ],
            "disposition_hash_and_quote_checks": checks,
            "independent_positive_rechecks": positive_checks,
            "no_outcome_inputs": True,
            "model_api_calls": 0,
            "eligible_sha256": hashlib.sha256(
                (HERE / "eligible.json").read_bytes()
            ).hexdigest(),
            "screening_sha256": hashlib.sha256(
                (HERE / "screening.json").read_bytes()
            ).hexdigest(),
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "stage", choices=["inventory", "docs", "history", "positive", "screen", "audit"]
    )
    p.add_argument("--begin", type=int, default=0)
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--issuers", nargs="*")
    a = p.parse_args()
    if a.stage == "inventory":
        print(inventory()["counts"])
    elif a.stage == "docs":
        docs(a.begin, a.limit)
    elif a.stage == "positive":
        positive_report()
    elif a.stage == "screen":
        all_dispositions()
    elif a.stage == "audit":
        final_audit()
    else:
        rows = [
            r
            for r in inventory()["rows"]
            if r["disposition"] == "primary_pdf_queue" and r["issuer"] in a.issuers
        ]
        with ThreadPoolExecutor(max_workers=3) as pool:
            for r in pool.map(history, rows):
                print(r["receipt"], r["prior_relevant_title_records"], flush=True)
