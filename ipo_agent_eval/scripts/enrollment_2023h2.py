"""Inventory the 2023 H2 DART equity filing queue without opening outcomes."""

import argparse
import hashlib
import re
import shutil
import tempfile
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

import fitz
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from scripts import official_enrollment as initial
from scripts import screen_a1_first_filings as filing
from scripts.current_b import OUT, dump
from scripts.current_live import load

DEST = OUT / "official/enrollment_expansion/2023H2"
CACHE = Path(tempfile.gettempdir()) / "ipo_a1_enrollment_2023h2"
WINDOW = ("20230701", "20231231")


def previously_screened():
    names, receipts, codes = initial.prior_roster()
    previous = load(OUT / "official/enrollment/screened_all.json")["rows"]
    if len(previous) != 39:
        raise ValueError("The prior Q4 screening roster does not have 39 issuers")
    q4 = {
        "names": {initial.key(row["issuer"]) for row in previous},
        "receipts": {row["receipt"] for row in previous},
        "codes": {row["corp_code"] for row in previous},
    }
    return (names, receipts, codes), q4


def inventory():
    initial.PARAMS = {**initial.PARAMS, "startDate": WINDOW[0], "endDate": WINDOW[1]}
    first = initial.listing(1)
    total = first["reported_total"]
    pages_needed = (total + initial.PARAMS["maxResults"] - 1) // initial.PARAMS[
        "maxResults"
    ]
    with ThreadPoolExecutor(max_workers=5) as pool:
        pages = [first, *pool.map(initial.listing, range(2, pages_needed + 1))]
    rows = sorted(
        (row for page in pages for row in page["records"]), key=lambda x: x["receipt"]
    )
    if (
        len(rows) != total
        or len({r["receipt"] for r in rows}) != total
        or any(p["reported_total"] != total for p in pages)
    ):
        raise ValueError("DART total and collected unique receipts differ")
    (names, receipts, codes), q4 = previously_screened()
    earliest = {}
    for row in rows:
        receipt, code = row["receipt"], row["corp_code"]
        issuer = initial.key(row["issuer"])
        if row["title"] != filing.TITLE:
            row["status"] = "OTHER_REPORT_TITLE"
        elif receipt in receipts or code in codes or issuer in names:
            row["status"] = "DUPLICATE_18"
        elif receipt in q4["receipts"] or code in q4["codes"] or issuer in q4["names"]:
            row["status"] = "DUPLICATE_2024Q4_39"
        elif any(s in issuer for s in ("스팩", "기업인수목적", "spac")):
            row["status"] = "SPAC"
        elif code in earliest:
            row["first_in_window_receipt"] = earliest[code]["receipt"]
            row["status"] = (
                "REFILING_AFTER_WITHDRAWN_ORIGINAL"
                if earliest[code]["withdrawal_notice"]
                else "LATER_CORPORATE_RECEIPT"
            )
        else:
            earliest[code] = row
            row["status"] = (
                "WITHDRAWN_ORIGINAL" if row["withdrawal_notice"] else "DOCUMENT_QUEUE"
            )
    result = {
        "date_window": list(WINDOW),
        "search_type": "DART C001",
        "known_model_calls": 0,
        "order": "ascending YYYYMMDD receipt number; earliest exact-title original per corporation",
        "pages": [{k: v for k, v in page.items() if k != "records"} for page in pages],
        "total": total,
        "counts": dict(Counter(row["status"] for row in rows)),
        "rows": rows,
    }
    dump(DEST / "inventory.json", result)
    return result


def document_screen(inventory_rows, start, limit):
    CACHE.mkdir(parents=True, exist_ok=True)
    initial.CACHE = filing.CACHE = CACHE
    path = DEST / (
        "document_screen.json" if start == 1 else f"document_screen_from_{start}.json"
    )
    saved = load(path)["rows"] if path.is_file() else []
    by_receipt = {row["receipt"]: row for row in saved}
    queue = [row for row in inventory_rows if row["status"] == "DOCUMENT_QUEUE"][
        start - 1 : limit
    ]
    pending = [row for row in queue if row["receipt"] not in by_receipt]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for row in pool.map(initial.inspect, pending):
            print(
                row["receipt"],
                row["issuer"],
                row["screen_status"],
                [p["physical_page"] for p in row.get("method_tables", [])],
                flush=True,
            )
            by_receipt[row["receipt"]] = row
            dump(
                path,
                {
                    "scope": "original public filing methods and listing purpose only",
                    "cache_name": CACHE.name,
                    "rows": list(by_receipt.values()),
                },
            )
    return list(by_receipt.values())


def company_history(row):
    receipt = row["receipt"]
    params = {
        "maxResults": 100,
        "startDate": "20140101",
        "endDate": receipt[:8],
        "publicType": "C001",
        "sort": "date",
        "series": "asc",
        "textCrpCik": row["corp_code"],
        "currentPage": 1,
    }
    source_url = initial.LIST_ENDPOINT + "?" + urlencode(params)
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        reply = client.get(source_url)
        reply.raise_for_status()
        soup = BeautifulSoup(reply.content, "html.parser")
        match = re.search(r"총\s*([0-9,]+)건", soup.get_text(" ", strip=True))
        if not match:
            raise ValueError(f"Corporate history count unavailable for {receipt}")
        all_rows = []
        for a in soup.select('a[href*="rcpNo="]'):
            firm = a.find_parent("tr").find("a", onclick=re.compile("openCorpInfoNew"))
            num = re.search(r"rcpNo=(\d{14})", a["href"])
            if firm and num:
                if row["corp_code"] not in firm["onclick"]:
                    raise ValueError(
                        f"Corporate history returned other company for {receipt}"
                    )
                all_rows.append(
                    {
                        "receipt": num[1],
                        "title": a.get_text(" ", strip=True),
                        "withdrawal_notice": bool(
                            a.find_parent("tr").select_one(".tagCom_chul_other")
                        ),
                    }
                )
        if len(all_rows) != int(match[1].replace(",", "")) or not any(
            x["receipt"] == receipt for x in all_rows
        ):
            raise ValueError(f"Corporate history missed receipts for {receipt}")
        same_day = row["date_kst"].replace("-", ".")
        daily_url = (
            initial.DART
            + "/dsac001/mainAll.do?"
            + urlencode(
                {
                    "selectDate": same_day,
                    "textCrpCik": row["corp_code"],
                    "currentPage": 1,
                    "maxResults": 100,
                }
            )
        )
        daily = client.get(daily_url)
        daily.raise_for_status()
        daily_soup = BeautifulSoup(daily.content, "html.parser")
        anchor = daily_soup.find("a", href=f"/dsaf001/main.do?rcpNo={receipt}")
        cells = (
            [
                td.get_text(" ", strip=True)
                for td in anchor.find_parent("tr").find_all("td")
            ]
            if anchor
            else []
        )
        published = (
            row["date_kst"] + "T" + cells[0] + "+09:00"
            if cells and same_day in cells and re.fullmatch(r"\d{2}:\d{2}", cells[0])
            else None
        )
    return {
        "history_url": source_url,
        "history_response_sha256": hashlib.sha256(reply.content).hexdigest(),
        "lookback_start": "2014-01-01",
        "earlier_public_case_reports": [v for v in all_rows if v["receipt"] < receipt],
        "daily_url": daily_url,
        "daily_sha256": hashlib.sha256(daily.content).hexdigest(),
        "published_kst": published or row["date_kst"],
        "time_precision": "minute" if published else "date",
    }


def normalize(text):
    return "".join(unicodedata.normalize("NFKC", text).split())


def verify_quotes(pdf, anchors):
    decoder = PdfReader(pdf)
    with fitz.open(pdf) as doc:
        for name, anchor in anchors.items():
            p = anchor["page"] - 1
            exact = normalize(anchor["quote"])
            if (
                not exact
                or exact not in normalize(doc[p].get_text(sort=True))
                or exact not in normalize(decoder.pages[p].extract_text())
            ):
                raise ValueError(
                    f"Anchor did not reproduce in both PDF extractors for {pdf.stem} {name}"
                )


def check_anchors(row, decision):
    pdf = CACHE / (row["receipt"] + ".pdf")
    source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if source_hash != row["pdf_sha256"] or not row["exact_title_and_earliest_family"]:
        raise ValueError(f"Unconfirmed PDF or first family version {row['receipt']}")
    fields = (
        "ipo_status_anchor",
        "issuer_valuation_anchor",
        "adopted_per_anchor",
        "adopted_price_anchor",
    )
    anchors = {field: decision[field] for field in fields}
    if "issuer_name_anchor" in decision:
        anchors["issuer_name_anchor"] = decision["issuer_name_anchor"]
    verify_quotes(pdf, anchors)
    destination = (
        Path(tempfile.gettempdir()) / "ipo_a1_initial_registrations" / pdf.name
    )
    if (
        destination.is_file()
        and hashlib.sha256(destination.read_bytes()).hexdigest() != source_hash
    ):
        raise ValueError(f"Another PDF version is already present for {row['receipt']}")
    if not destination.is_file():
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(pdf, destination)


def finalize(inventory_rows, limit):
    selected_specs = load(DEST / "determinations.json")
    documents = {
        row["receipt"]: row
        for p in DEST.glob("document_screen*.json")
        for row in load(p)["rows"]
    }
    chronology = []
    admitted = []
    for row in inventory_rows:
        receipt = row["receipt"]
        disposition = row["status"]
        if disposition == "DOCUMENT_QUEUE":
            doc = documents.get(receipt)
            if doc is None:
                raise ValueError(
                    f"Cannot pass unresolved chronological candidate {receipt}"
                )
            spec = selected_specs.get(receipt)
            if spec:
                disposition = spec["status"]
                if disposition == "ELIGIBLE":
                    admitted.append((doc, spec))
            elif (
                doc["download_status"] == "공식 PDF 확인"
                and not doc["method_tables"]
                and not doc["ipo_purpose_locators"]
            ):
                disposition = "NO_IPO_PURPOSE_OR_APPLIED_PER_TABLE"
            else:
                raise ValueError(f"Need an explicit checked disposition for {receipt}")
            evidence = {
                "pdf_sha256": doc.get("pdf_sha256"),
                "pdf_url": doc.get("pdf_url"),
                "reason": spec["reason"]
                if spec
                else "초기 모집·매출 목적과 인수 의견에서 신규상장 및 발행사 PER 산정표를 확인할 근거가 없다.",
            }
            if spec and "reason_anchor" in spec:
                verify_quotes(
                    CACHE / (receipt + ".pdf"), {"reason_anchor": spec["reason_anchor"]}
                )
                evidence["anchor"] = spec["reason_anchor"]
        else:
            evidence = {"reason": disposition}
        chronology.append({**row, "disposition": disposition, **evidence})
        if len(admitted) == limit:
            break
    if len(admitted) != limit:
        raise ValueError("Not enough supported chronological eligible filings")
    with ThreadPoolExecutor(max_workers=5) as pool:
        histories = list(pool.map(company_history, [row for row, _ in admitted]))
    output = []
    for (row, spec), history in zip(admitted, histories):
        if any(
            v["title"] == filing.TITLE or v["withdrawal_notice"]
            for v in history["earlier_public_case_reports"]
        ):
            raise ValueError(
                f"Earlier equity original or withdrawal requires reconciliation for {row['receipt']}"
            )
        check_anchors(row, spec)
        output.append(
            {
                **{
                    k: row[k]
                    for k in (
                        "receipt",
                        "corp_code",
                        "issuer",
                        "pdf_url",
                        "pdf_sha256",
                        "pdf_pages",
                        "family_metadata",
                        "date_kst",
                        "official_title",
                    )
                },
                **spec,
                **history,
                "source_url": row["url"],
                "shared_cache": "%TEMP%/ipo_a1_initial_registrations/"
                + row["receipt"]
                + ".pdf",
            }
        )
    stop = chronology[-1]["receipt"]
    dump(
        DEST / "eligible.json",
        {"rows": output, "stop_receipt": stop, "known_model_calls": 0},
    )
    dump(
        DEST / "chronology.json",
        {
            "stop_receipt": stop,
            "examined_through_stop": len(chronology),
            "counts": dict(Counter(row["disposition"] for row in chronology)),
            "rows": chronology,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=int, default=0)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--finalize", type=int, default=0)
    parser.add_argument("--refresh-inventory", action="store_true")
    args = parser.parse_args()
    source = DEST / "inventory.json"
    result = (
        load(source) if source.is_file() and not args.refresh_inventory else inventory()
    )
    print(result["total"], result["counts"], flush=True)
    if args.documents:
        processed = document_screen(result["rows"], args.start, args.documents)
        print("screened", len(processed), flush=True)
    if args.finalize:
        finalize(result["rows"], args.finalize)


if __name__ == "__main__":
    main()
