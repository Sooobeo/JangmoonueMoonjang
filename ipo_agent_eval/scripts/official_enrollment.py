"""Discover independent initial IPO filings using an outcome-blind DART screen."""

import argparse
import hashlib
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlencode, urlparse

import fitz
import httpx
from bs4 import BeautifulSoup

from scripts.current_b import OUT, ROOT, dump
from scripts.current_live import load
from scripts.screen_a1_first_filings import (
    CACHE,
    DART,
    TITLE,
    get,
    main_html,
    main_url,
    registration_options,
)

DEST = OUT / "official" / "enrollment"
LIST_ENDPOINT = DART + "/dsab001/search.ax"
PARAMS = {"maxResults": 100, "startDate": "20241001", "endDate": "20241231",
          "publicType": "C001", "sort": "date", "series": "asc"}
FUTURE = re.compile(r"(?:추정|예상|예측|전망)(?:연평균)?(?:지배주주)?(?:당기)?(?:순이익|EPS)|(?:순이익|EPS)(?:추정|예상|전망)")
HISTORIC = re.compile(r"최근(?:12개월|4개분기|네분기)|LTM|TTM|연환산|실적치|온기|(?:202[0-4])년(?:[1-4]분기|상반기|반기|당기순이익|연간)")
LISTING_PURPOSE = re.compile(
    r"(?:본주식은|당사는|당사의주권은|금번공모는|본공모는).{0,140}"
    r"(?:코스닥시장|유가증권시장)(?:의)?(?:에)?(?:신규|이전)?상장.{0,35}(?:목적|공모|모집|예심|신청|승인|예정)"
    r"|(?:상장을목적으로모집|상장을목적으로공모|상장예비심사신청서를제출|상장예비심사승인)"
)


def key(value):
    value = re.sub(r"\(주\)|㈜|주식회사|\s+", "", value)
    return value.casefold()


def prior_roster():
    path = ROOT / "reports/a1_development/filing_screening.json"
    metadata = load(path)["cases"]
    names = {key(row["issuer"]) for row in metadata} | {key("HD현대마린솔루션")}
    receipts = {row["receipt_no"] for row in metadata} | {"20240325000947"}
    codes = {code for row in metadata for code in parse_qs(urlparse(row.get("daily_url", "")).query).get("textCrpCik", [])}
    return names, receipts, codes


def listing(page):
    url = LIST_ENDPOINT + "?" + urlencode({**PARAMS, "currentPage": page})
    reply = httpx.get(url, timeout=20, follow_redirects=True)
    reply.raise_for_status()
    body = BeautifulSoup(reply.content.decode("utf-8"), "html.parser")
    records = []
    for a in body.select('a[href*="rcpNo="]'):
        row = a.find_parent("tr")
        if row is None:
            continue
        corp = row.find("a", onclick=re.compile("openCorpInfoNew"))
        code = re.search(r"'([0-9]{8})'", corp["onclick"]) if corp else None
        receipt = re.search(r"rcpNo=(\d{14})", a["href"])
        if not code or not receipt:
            continue
        records.append({"receipt": receipt[1], "corp_code": code[1], "issuer": corp.get_text(" ", strip=True),
                        "title": a.get_text(" ", strip=True), "withdrawal_notice": bool(row.select_one(".tagCom_chul_other")),
                        "listing_page": page, "url": main_url(receipt[1])})
    total = re.search(r"총\s*([0-9,]+)건", body.get_text(" ", strip=True))
    if not total:
        raise ValueError(f"DART listing count missing on search page {page}")
    return {"url": url, "response_sha256": hashlib.sha256(reply.content).hexdigest(),
            "reported_total": int(total[1].replace(",", "")), "records": records}


def inventory(limit):
    first = listing(1)
    total = first["reported_total"]
    pages_needed = (total + PARAMS["maxResults"] - 1) // PARAMS["maxResults"]
    with ThreadPoolExecutor(max_workers=5) as pool:
        pages = [first, *pool.map(listing, range(2, pages_needed + 1))]
    rows = sorted((row for page in pages for row in page["records"]), key=lambda x: x["receipt"])
    if len(rows) != total or len({r["receipt"] for r in rows}) != total or any(p["reported_total"] != total for p in pages):
        raise ValueError("Historical DART listing pages are incomplete or overlap")
    names, receipts, codes = prior_roster()
    by_issuer = set()
    inspect_rows = []
    for row in rows:
        if row["title"] != TITLE:
            row["inventory_status"] = "보고서명 범위 밖"
        elif row["receipt"] in receipts or key(row["issuer"]) in names or row["corp_code"] in codes:
            row["inventory_status"] = "기존 18곳과 중복"
        elif any(word in key(row["issuer"]) for word in ("스팩", "기업인수목적", "spac")):
            row["inventory_status"] = "SPAC"
        elif row["withdrawal_notice"]:
            row["inventory_status"] = "철회 표시·별도 보류"
        elif row["corp_code"] in by_issuer:
            row["inventory_status"] = "같은 회사의 추가 접수"
        else:
            by_issuer.add(row["corp_code"])
            row["inventory_status"] = "이번 원문 확인" if len(inspect_rows) < limit else "원문 확인 대기"
            if len(inspect_rows) < limit:
                inspect_rows.append(row)
    result = {"window": [PARAMS["startDate"], PARAMS["endDate"]], "search_type": "DART public C001",
              "order": "original receipt ascending, exact equity title, one non-withdrawn receipt per new company ID",
              "limits": {"document_inspection": limit, "old_cohort_outcomes_opened": 0, "model_calls": 0},
              "pages": [{k: v for k, v in p.items() if k != "records"} for p in pages],
              "counts": dict(Counter(r["inventory_status"] for r in rows)), "rows": rows}
    dump(DEST / "inventory.json", result)
    return inspect_rows, result


def locate(texts, first_page=1):
    selected = []
    for index, text in enumerate(texts):
        compact = "".join(text.split())
        if not any(k in compact.upper() for k in ("PER", "P/E")) or not any(
                k in compact for k in ("주당평가가액", "주당평가액", "주당평가가치", "주당상대가치", "주당가치")):
            continue
        if not any(k in compact for k in ("적용순이익", "당기순이익", "주당순이익", "적용이익")):
            continue
        relevant = []
        for line in text.splitlines():
            clean = "".join(line.split())
            if HISTORIC.search(clean) or FUTURE.search(clean) or any(k in clean for k in ("적용당기순이익", "적용PER", "주당평가가액")):
                relevant.append(re.sub(r"\s+", " ", line.strip())[:150])
        window = "".join("".join(t.split()) for t in texts[max(0, index - 1):index + 2])
        selected.append({"physical_page": index + first_page, "historical_markers": sorted(set(HISTORIC.findall(window))),
                         "forecast_markers": sorted(set(FUTURE.findall(window))), "row_anchors": relevant[:8]})
    return selected


def underwriter_pages(doc):
    toc = doc.get_toc()
    for idx, (depth, title, start) in enumerate(toc):
        if "인수인의의견" in "".join(title.split()):
            stop = next((p for lvl, _, p in toc[idx + 1:] if lvl <= depth and p > start), len(doc) + 1)
            return start, stop
    return 1, len(doc) + 1


def inspect(row):
    receipt = row["receipt"]
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        try:
            original = main_html(client, receipt)
            title = original.title.get_text(strip=True)
            if title.split("/")[1].strip() != TITLE:
                raise ValueError("Official original title mismatch")
            family = registration_options(original, "family")
            if family and (receipt != min(v["receipt"] for v in family) or
                           not any(v["receipt"] == receipt and v["caption"].endswith(TITLE) for v in family)):
                raise ValueError("DART family does not confirm earliest original")
            raw = (CACHE / f"{receipt}.html").read_text(encoding="utf-8")
            numbers = set(re.findall(r"openPdfDownload\('" + receipt + r"',\s*'(\d+)'", raw))
            if len(numbers) != 1:
                raise ValueError("Cannot pin a single DART document number")
            params = {"rcp_no": receipt, "dcm_no": numbers.pop()}
            menu = DART + "/pdf/download/main.do?" + urlencode(params)
            url = DART + "/pdf/download/pdf.do?" + urlencode(params)
            pdf = CACHE / f"{receipt}.pdf"
            if not pdf.exists():
                client.get(menu, headers={"Referer": row["url"]}).raise_for_status()
            blob = get(client, url, pdf, menu)
            with fitz.open(pdf) as doc:
                pages = len(doc)
                first_markers = []
                for p in range(1, min(70, pages) + 1):
                    early = "".join(doc[p - 1].get_text(sort=True).split())
                    evidence = LISTING_PURPOSE.search(early)
                    if evidence:
                        first_markers.append({"page": p, "brief_anchor": evidence[0][:100]})
                start, stop = underwriter_pages(doc)
                possible_tables = locate([doc[p - 1].get_text(sort=True) for p in range(start, stop)], start)
            if not first_markers:
                status = "신규상장 근거 미확인"
            elif possible_tables:
                status = "PER표 발견·적용 기간 검토 대기"
            else:
                status = "PER 산정표 미확인"
            return {**row, "download_status": "공식 PDF 확인", "screen_status": status,
                    "date_kst": f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}", "time_precision": "date",
                    "official_title": title, "family_metadata": family, "exact_title_and_earliest_family": bool(family),
                    "pdf_url": url, "pdf_sha256": hashlib.sha256(blob).hexdigest(), "pdf_pages": pages,
                    "ipo_purpose_locators": first_markers, "underwriter_physical_range": [start, stop - 1],
                    "method_tables": possible_tables}
        except (httpx.HTTPError, OSError, ValueError, RuntimeError, IndexError) as exc:
            return {**row, "download_status": "미확인", "screen_status": "원문 확인 보류", "reason": str(exc)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=24, choices=range(1, 40))
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    chosen, ledger = inventory(args.limit)
    print(ledger["counts"], flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        screened = list(pool.map(inspect, chosen))
    counts = dict(Counter(row["screen_status"] for row in screened))
    dump(DEST / "document_screen.json", {"source_scope": "DART initial documents only, eligibility still needs period review",
                                         "counts": counts, "rows": screened})
    print(counts, flush=True)
