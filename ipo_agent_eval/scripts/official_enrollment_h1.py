"""Reproduce the outcome-blind original-filing search for 2025 H1."""

import argparse
import hashlib
import re
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

import fitz
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from scripts import official_enrollment as earlier
from scripts.current_b import OUT, dump
from scripts.current_live import load
from scripts.screen_a1_first_filings import DART, TITLE, get, registration_options

DEST = OUT / "official" / "enrollment_expansion" / "2025H1"
CACHE = Path(tempfile.gettempdir()) / "ipo_a1_enrollment_2025H1"
QUARTERS = (("20250101", "20250331"), ("20250401", "20250630"))
IPO = re.compile(
    r"상장(?:을목적으로|할목적으로|에앞서).{0,30}(?:공모|모집|매출)"
    r"|상장예비심사신청서를제출|상장예비심사결과.{0,16}상장승인"
    r"|(?:코스닥시장|유가증권시장)(?:에|의)?(?:신규|이전)?상장(?:을위해|목적)"
)
RIGHTS = re.compile(r"주주배정.{0,24}(?:유상증자|일반공모)|제3자배정.{0,15}유상증자|주주우선공모")
METHOD_KEYS = (
    "적용재무수치", "적용순이익", "적용당기순이익", "적용PER", "평균PER", "적용산식",
    "주당평가가액", "주당평가액", "주당평가가치", "주당상대가치", "적용이익", "추정당기순이익",
    "적용배수", "평가방법", "평가가치산출", "주당희망공모가액", "기업가치평가결과",
)
PRIMARY_OFFER = re.compile(r"(?:본주식은|금번공모는|금번모집은|이번공모는).{0,80}상장(?:을목적으로|하기위한|예비심사)")


def compact(text):
    return "".join(text.split())


def normalized(text):
    return " ".join(text.split())


def evidence_preview(receipts):
    for receipt in receipts:
        pdf = CACHE / f"{receipt}.pdf"
        if not pdf.exists():
            continue
        with fitz.open(pdf) as doc:
            front = []
            for p in range(1, min(48, len(doc)) + 1):
                page = doc[p - 1].get_text(sort=True)
                for line in page.splitlines():
                    c = compact(line)
                    if PRIMARY_OFFER.search(c) or IPO.search(c) or RIGHTS.search(c):
                        front.append([p, normalized(line)])
            start, stop = earlier.underwriter_pages(doc)
            methods = []
            for p in range(start, min(start + 9, stop)):
                page = doc[p - 1].get_text(sort=True)
                source = compact(page)
                if "적용재무수치" in source or "적용산식" in source:
                    summary_start = page.find("평가모형")
                    if summary_start < 0:
                        summary_start = max(0, page.find("적용산식") - 250)
                    relevant = tuple(x for x in page[summary_start:].splitlines()
                                     if any(key in compact(x) for key in (
                                         "평가모형", "적용재무수치", "적용산식", "평가가액", "희망공모가액밴드",
                                         "순이익", "EBITDA", "EPS", "PER", "PBR", "PSR", "외환효과", "매출액")))
                    methods.append([p, [normalized(x) for x in relevant[:15]]])
            print(receipt, "IPO/RIGHTS", front[:6], "METHOD_START", start, "PRIMARY_METHOD", methods, flush=True)


def collect_inventory():
    names, receipts, codes = earlier.prior_roster()
    prior = load(earlier.DEST / "screened_all.json")["rows"]
    names.update(earlier.key(x["issuer"]) for x in prior)
    receipts.update(x["receipt"] for x in prior)
    codes.update(x["corp_code"] for x in prior)
    quarters = []
    rows = []
    for start, end in QUARTERS:
        earlier.PARAMS = {**earlier.PARAMS, "startDate": start, "endDate": end}
        first = earlier.listing(1)
        total = first["reported_total"]
        needed = (total + earlier.PARAMS["maxResults"] - 1) // earlier.PARAMS["maxResults"]
        with ThreadPoolExecutor(max_workers=5) as pool:
            pages = [first, *pool.map(earlier.listing, range(2, needed + 1))]
        quarter_rows = [row for page in pages for row in page["records"]]
        if len(quarter_rows) != total or len({r["receipt"] for r in quarter_rows}) != total or any(
                p["reported_total"] != total for p in pages):
            raise ValueError(f"Incomplete DART search window {start}–{end}")
        for position, row in enumerate(quarter_rows, 1):
            row["quarter_position"] = position
            row["quarter"] = f"2025Q{'1' if start.endswith('0101') else '2'}"
        quarters.append({"start_date": start, "end_date": end, "reported_total": total,
                         "pages": [{k: v for k, v in p.items() if k != "records"} for p in pages]})
        rows.extend(quarter_rows)
    if len({r["receipt"] for r in rows}) != len(rows):
        raise ValueError("Overlapping DART search windows")
    seen = set()
    withdrawals = {}
    for position, row in enumerate(rows, 1):
        row["position"] = position
        receipt = row["receipt"]
        row["date_kst"] = f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}"
        code = row["corp_code"]
        name = earlier.key(row["issuer"])
        if row["withdrawal_notice"] or "철회" in row["title"]:
            withdrawals.setdefault(code, []).append({k: row[k] for k in ("receipt", "title", "url")})
        if row["title"] != TITLE:
            status = "title_outside_scope"
        elif receipt in receipts or code in codes or name in names:
            status = "overlap_previous_18_or_39"
        elif any(word in name for word in ("스팩", "기업인수목적", "spac")):
            status = "spac"
        elif row["withdrawal_notice"]:
            status = "withdrawn_or_marked_review_separately"
        elif code in seen:
            status = "later_exact_title_same_issuer"
        else:
            status = "source_check"
            seen.add(code)
        row["inventory_status"] = status
    for row in rows:
        if row["inventory_status"] == "source_check":
            row["same_issuer_prior_withdrawal_titles_in_window"] = [
                x for x in withdrawals.get(row["corp_code"], []) if x["receipt"] < row["receipt"]
            ]
    return {"window_kst": ["2025-01-01", "2025-06-30"], "search_type": "DART public C001",
            "order": "DART date ascending, HTTP pagination order per quarter; all public result positions retained",
            "quarters": quarters, "counts": dict(Counter(row["inventory_status"] for row in rows)), "rows": rows,
            "model_calls": 0, "outcomes_opened": 0}


def fetch_original(client, row):
    receipt = row["receipt"]
    raw = get(client, row["url"], CACHE / f"{receipt}.html").decode("utf-8")
    document = BeautifulSoup(raw, "html.parser")
    title = document.title.get_text(strip=True)
    if title.split("/")[1].strip() != TITLE:
        raise ValueError(f"Exact original title missing for {receipt}")
    family = registration_options(document, "family")
    if family and (receipt != min(x["receipt"] for x in family) or not any(
            x["receipt"] == receipt and re.fullmatch(r"\d{4}\.\d{2}\.\d{2} " + re.escape(TITLE), x["caption"])
            for x in family)):
        raise ValueError(f"First family receipt differs from {receipt}")
    numbers = set(re.findall(r"openPdfDownload\('" + receipt + r"',\s*'(\d+)'", raw))
    if len(numbers) != 1:
        raise ValueError(f"DART main PDF not uniquely identified for {receipt}")
    params = urlencode({"rcp_no": receipt, "dcm_no": numbers.pop()})
    menu = f"{DART}/pdf/download/main.do?{params}"
    url = f"{DART}/pdf/download/pdf.do?{params}"
    pdf = CACHE / f"{receipt}.pdf"
    if not pdf.exists():
        client.get(menu, headers={"Referer": row["url"]}).raise_for_status()
    blob = get(client, url, pdf, menu)
    return pdf, {"official_title": title, "family_metadata": family, "family_earliest_confirmed": bool(family),
                 "pdf_url": url, "pdf_sha256": hashlib.sha256(blob).hexdigest()}


def prior_equity_history(row):
    """Check DART titles and status metadata only for the same corp ID through intake day."""
    params = {"publicType": "C001", "startDate": "20200101", "endDate": row["receipt"][:8],
              "textCrpCik": row["corp_code"], "maxResults": 100, "sort": "date", "series": "asc", "currentPage": 1}
    try:
        r = httpx.get(earlier.LIST_ENDPOINT, params=params, timeout=30, follow_redirects=True)
        r.raise_for_status()
        body = BeautifulSoup(r.content.decode("utf-8"), "html.parser")
        total = re.search(r"총\s*([0-9,]+)건", body.get_text(" ", strip=True))
        report_links = body.select('a[href*="rcpNo="]')
        if not total or len(report_links) != int(total[1].replace(",", "")):
            raise ValueError("Incomplete company history search")
        titles = []
        for a in report_links:
            receipt = re.search(r"rcpNo=(\d{14})", a["href"])[1]
            tr = a.find_parent("tr")
            owner = tr.find("a", onclick=re.compile("openCorpInfoNew"))
            if row["corp_code"] not in owner["onclick"]:
                raise ValueError("Company history ID mismatch")
            title = a.get_text(" ", strip=True)
            if receipt <= row["receipt"]:
                titles.append({"receipt": receipt, "title": title, "withdrawal_notice": bool(tr.select_one(".tagCom_chul_other")),
                               "url": earlier.main_url(receipt)})
        if not any(x["receipt"] == row["receipt"] and x["title"] == TITLE for x in titles):
            raise ValueError("Current original absent from same-ID history")
        prior_titles = [x for x in titles if x["receipt"] < row["receipt"] and (
            x["title"] == TITLE or x["withdrawal_notice"] or "철회" in x["title"])]
        return {"state": "verified", "url": str(r.url), "response_sha256": hashlib.sha256(r.content).hexdigest(),
                "reported_total": len(report_links), "earlier_initial_or_withdrawal_titles": prior_titles}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return {"state": "unverified", "url": earlier.LIST_ENDPOINT + "?" + urlencode(params), "error": str(exc)}


def find_locations(pdf):
    with fitz.open(pdf) as doc:
        toc = doc.get_toc()
        start, stop = earlier.underwriter_pages(doc)
        front = range(1, min(43, len(doc)) + 1)
        primary = []
        rights = []
        for p in front:
            source = compact(doc[p - 1].get_text())
            if match := IPO.search(source):
                primary.append({"page": p, "locator": match[0]})
            if p <= 35 and (match := RIGHTS.search(source)):
                rights.append({"page": p, "locator": match[0]})
        method = []
        method_stop = min(stop, start + 30)
        for p in range(start, method_stop):
            text = doc[p - 1].get_text(sort=True)
            source = compact(text)
            keys = [key for key in METHOD_KEYS if key in source]
            multiple = list(dict.fromkeys(re.findall(r"(?i)P/E|\bPER\b|EV\s*/\s*EBITDA|\bPSR\b|\bPBR\b", text)))
            if keys or multiple:
                method.append({"page": p, "keys": keys, "multiples": multiple})
        return {"pdf_pages": len(doc), "ipo_purpose_locators": primary, "rights_locators": rights,
                "underwriter_physical_range": [start, stop - 1], "method_search_physical_range": [start, method_stop - 1],
                "method_locators": method, "front_search_physical_range": [1, front.stop - 1],
                "front_toc": [x for x in toc if x[2] <= 45]}


def document_screen(row):
    with httpx.Client(timeout=45, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        try:
            pdf, metadata = fetch_original(client, row)
            return {**row, **metadata, **find_locations(pdf), "download_status": "verified_main_pdf"}
        except (httpx.HTTPError, OSError, ValueError, RuntimeError, IndexError) as exc:
            return {**row, "download_status": "source_error", "error": str(exc)}


def checked_source(row, annotation, history):
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        pdf, meta = fetch_original(client, row)
    if not meta["family_earliest_confirmed"] or history.get("state") != "verified":
        raise ValueError(f"Original family or issuer search unverified for {row['receipt']}")
    reader = PdfReader(pdf)
    validations = []
    anchor_keys = ("ipo_status_anchor", "issuer_valuation_anchor", "applied_multiple_anchor", "offer_band_anchor")
    with fitz.open(pdf) as doc:
        start, stop = earlier.underwriter_pages(doc)
        for field in anchor_keys:
            anchor = annotation[field]
            p = anchor["page"]
            if field != "ipo_status_anchor" and not start <= p < stop:
                raise ValueError(f"Pricing evidence outside underwriter opinion for {row['receipt']}")
            q = compact(anchor["quote"])
            pdf_text = [compact(doc[p - 1].get_text(sort=sort)) for sort in (True, False)]
            in_mupdf = any(q in candidate for candidate in pdf_text)
            in_pypdf = any(q in compact(reader.pages[p - 1].extract_text(extraction_mode=mode))
                           for mode in ("plain", "layout"))
            if not in_mupdf:
                raise ValueError(f"Anchor {field} did not match official page {p} for {row['receipt']}")
            validations.append({"field": field, "page": p, "mupdf": in_mupdf, "pypdf": in_pypdf})
        pages = len(doc)
    previous = history["earlier_initial_or_withdrawal_titles"]
    classification = annotation["classification"]
    if classification == "historical_PER" and previous:
        raise ValueError(f"Earlier equity-registration metadata for {row['receipt']}; adjudicate separately")
    return {**row, **meta, **annotation, "pdf_pages": pages, "cache_file": str(pdf),
            "earlier_same_corp_history": history, "anchor_checks": validations}


def publish_annotations():
    inventory = load(DEST / "inventory.json")
    history = load(DEST / "issuer_history.json")
    annotations = load(DEST / "adjudication.json")
    valid = {r["receipt"]: r for r in inventory["rows"] if r["inventory_status"] == "source_check"}
    if len({r["receipt"] for r in annotations["rows"]}) != len(annotations["rows"]):
        raise ValueError("Duplicate manual annotation")
    annotated = [checked_source(valid[a["receipt"]], a, history[a["receipt"]]) for a in annotations["rows"]]
    eligible = sorted((r for r in annotated if r["classification"] == "historical_PER"), key=lambda r: r["receipt"])
    if len({r["corp_code"] for r in eligible}) != len(eligible):
        raise ValueError("Duplicate eligible issuer")
    dump(DEST / "eligible.json", {"window_kst": inventory["window_kst"], "rows": eligible,
                                  "count": len(eligible), "cache_dir": str(CACHE),
                                  "outcomes_opened": 0, "model_calls": 0})
    special = [x for x in annotated if x["classification"] != "historical_PER"]
    dump(DEST / "method_holdouts.json", {"window_kst": inventory["window_kst"], "rows": special})
    print(f"Eligible: {len(eligible)}. Method or prior-family holdout: {len(special)}.", flush=True)


def _anchor_exists(doc, anchor):
    return any(compact(anchor["quote"]) in compact(doc[anchor["page"] - 1].get_text(sort=sort))
               for sort in (True, False))


def _capital_increase_anchor(doc, row):
    exercise = [p for depth, title, p in doc.get_toc() if depth == 2 and compact(title).endswith("공모개요")]
    pages = range(exercise[0], min(exercise[0] + 4, len(doc)) + 1) if exercise else ()
    for p in pages:
        lines = doc[p - 1].get_text(sort=True).splitlines()
        for line in lines:
            if RIGHTS.search(compact(line)):
                return {"page": p, "quote": normalized(line)}
    if row["rights_locators"]:
        evidence = row["rights_locators"][-1]
        loc = {"page": evidence["page"], "quote": evidence["locator"]}
        if _anchor_exists(doc, loc):
            return loc
    raise ValueError(f"No capital increase evidence for {row['receipt']}")


def source_disposition(row, methods, qualified):
    if row["download_status"] != "verified_main_pdf" or not row["family_earliest_confirmed"]:
        raise ValueError(f"Missing eligible-scope original dossier for {row['receipt']}")
    receipt = row["receipt"]
    if receipt in qualified:
        approved = qualified[receipt]
        return {**row, **approved, "screen_note": approved["period_or_method"]}
    extra = methods["supplementary_anchors"].get(receipt)
    with fitz.open(CACHE / f"{receipt}.pdf") as doc:
        for group in ("forecast_PER", "other_multiple"):
            if receipt in methods[group]:
                p, quote = methods[group][receipt]
                evidence = {"page": p, "quote": quote}
                if not _anchor_exists(doc, evidence):
                    raise ValueError(f"Excluded method anchor mismatch for {receipt} p{p}")
                if not row["ipo_purpose_locators"] and not isinstance(extra, dict):
                    raise ValueError(f"Missing IPO-purpose evidence for {receipt}")
                if isinstance(extra, dict) and not _anchor_exists(doc, extra):
                    raise ValueError(f"Extra IPO status anchor mismatch for {receipt}")
                return {**row, "classification": group, "applied_noneligible_method_anchor": evidence,
                        "supplementary_anchor_or_note": extra}
        if row["ipo_purpose_locators"]:
            raise ValueError(f"Unclassified possible original IPO {receipt}")
        evidence = extra if extra else _capital_increase_anchor(doc, row)
        if not _anchor_exists(doc, evidence):
            raise ValueError(f"Capital increase anchor mismatch for {receipt}")
    return {**row, "classification": "not_ipo_capital_increase", "non_ipo_anchor": evidence}


def publish_screen():
    inventory = load(DEST / "inventory.json")
    scan = load(DEST / "document_screen.json")["rows"]
    qualifying = {}
    for file in ("eligible.json", "method_holdouts.json"):
        qualifying.update({r["receipt"]: r for r in load(DEST / file)["rows"]})
    methods = load(DEST / "excluded_ipo_methods.json")
    checked = {r["receipt"]: source_disposition(r, methods, qualifying) for r in scan}
    if set(checked) != {r["receipt"] for r in inventory["rows"] if r["inventory_status"] == "source_check"}:
        raise ValueError("At least one source gate missing or over scope")
    rows = [checked.get(r["receipt"], {**r, "classification": r["inventory_status"]}) for r in inventory["rows"]]
    counts = dict(Counter(r["classification"] for r in rows))
    dump(DEST / "screened_all.json", {"window_kst": inventory["window_kst"], "rows": rows,
                                      "counts": counts, "full_originals_examined": len(scan),
                                      "model_calls": 0, "outcomes_opened": 0})
    print(counts, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--reuse-inventory", action="store_true")
    parser.add_argument("--preview", nargs="*", metavar="RECEIPT")
    parser.add_argument("--history", nargs="+", metavar="RECEIPT")
    parser.add_argument("--publish-annotations", action="store_true")
    parser.add_argument("--publish-screen", action="store_true")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    if args.publish_annotations:
        publish_annotations()
        return
    if args.publish_screen:
        publish_screen()
        return
    if args.preview is not None:
        evidence_preview(args.preview or [p.stem for p in sorted(CACHE.glob("*.pdf"))])
        return
    inventory_file = DEST / "inventory.json"
    if args.history:
        inventory = load(inventory_file)
        old = DEST / "issuer_history.json"
        history = load(old) if old.exists() else {}
        pending = [r for r in inventory["rows"] if r["receipt"] in args.history and (
            history.get(r["receipt"], {}).get("state") != "verified")]
        with ThreadPoolExecutor(max_workers=7) as pool:
            for row, result in zip(pending, pool.map(prior_equity_history, pending), strict=True):
                history[row["receipt"]] = result
                dump(old, history)
                print(row["receipt"], row["issuer"], result["state"],
                      result.get("earlier_initial_or_withdrawal_titles", []), flush=True)
        return
    inventory = load(inventory_file) if args.reuse_inventory else collect_inventory()
    if not args.reuse_inventory:
        dump(inventory_file, inventory)
    print(inventory["counts"], flush=True)
    rows = [r for r in inventory["rows"] if r["inventory_status"] == "source_check"]
    print([(r["position"], r["issuer"], r["receipt"]) for r in rows], flush=True)
    if args.inventory_only:
        return
    with ThreadPoolExecutor(max_workers=9) as pool:
        examined = list(pool.map(document_screen, rows))
    dump(DEST / "document_screen.json", {"window_kst": inventory["window_kst"], "rows": examined,
                                         "counts": dict(Counter(r["download_status"] for r in examined))})
    print(Counter(r["download_status"] for r in examined), flush=True)


if __name__ == "__main__":
    main()
