"""Archive outcome-blind initial filings and freeze the stratified 37-issuer roster."""

import hashlib
import json
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import fitz
import httpx

from scripts.current_b import OUT, dump
from scripts.current_live import load
from scripts.screen_a1_first_filings import (
    CACHE,
    ROOT,
    TITLE,
    get,
    main_html,
    registration_options,
)

BASE = OUT / "official/enrollment_expansion"
ARCHIVE = BASE / "filings_source"
WINDOWS = ("2023H2", "2024H1", "2025H1", "2025H2")
LEGACY = {
    "SLSBIO": "적용 당기순이익은 2023년 2분기 LTM 기준",
    "ECOEYE": "적용 당기순이익은 발행회사 ㈜에코아이의 최근 4개분기",
    "HANSSAK": "적용 당기순이익은 발행회사 (주)한싹의 최근 4개분기",
    "INSWAVE": "적용 당기순이익은 발행회사 (주)인스웨이브시스템즈의 최근 4개분기",
    "SYSTEEL": "적용 당기순이익은 발행회사 에스와이스틸텍(주)의 최근 4개분기",
    "APR": "적용 순이익은 2023년 3분기 연환산 당기순이익",
    "SANIL": "적용 당기순이익은 동사의 2024년도 1분기 기준 과거 12개월",
    "JEONJIN": "실적치 (2024년도 1분기 기준 과거 12개월(LTM) 당기순이익",
}


def compact(value):
    return "".join(unicodedata.normalize("NFKC", value).split()).casefold()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def offer_anchor(doc):
    for idx in range(min(100, len(doc))):
        match = re.search(r"(?:코스닥|유가증권)시장(?:에|의)?(?:신규|이전)?상장을(?:위한공모|목적으로(?:모집|공모))",
                          compact(doc[idx].get_text(sort=True)))
        if match:
            return {"page": idx + 1, "quote": match[0]}
    raise ValueError("Could not locate an explicit listing-offer purpose")


def original_14():
    legacy = load(ROOT / "reports/a1_development/filing_screening.json")["cases"]
    rows = []
    for item in legacy:
        case = item["case_id"].split("-")[0]
        if case not in LEGACY:
            continue
        receipt = item["receipt_no"]
        source = ARCHIVE / (receipt + ".pdf")
        if not source.exists():
            source = CACHE / (receipt + ".pdf")
            if not source.exists():
                with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
                    get(client, item["pdf_url"], source, item["pdf_url"].replace("pdf.do", "main.do"))
        if sha(source) != item["pdf_sha256"]:
            raise ValueError(f"{receipt}: legacy source checksum mismatch")
        with fitz.open(source) as doc:
            ipo = offer_anchor(doc)
        rows.append({"issuer": item["issuer"], "corp_code": parse_qs(urlparse(item["daily_url"]).query)["textCrpCik"][0],
                     "receipt": receipt, "pdf_url": item["pdf_url"], "pdf_sha256": item["pdf_sha256"],
                     "period_or_method": item["earnings_basis"],
                     "ipo_status_anchor": ipo,
                     "issuer_valuation_anchor": {"page": item["method_period_pdf_page"], "quote": LEGACY[case]},
                     "price_table_page": item["price_table_pdf_page"], "cohort": "기존 미사용 8곳"})
    q4 = load(OUT / "official/enrollment/screened_all.json")
    ids = set(q4["new_historical_PER_without_known_prior_withdrawal_in_window"])
    rows.extend({**row, "cohort": "2024년 4분기 기확보"} for row in q4["rows"] if row["receipt"] in ids)
    if len(rows) != 14 or len(ids) != 6:
        raise ValueError("Previous roster differs from the frozen eight plus six")
    return rows


def selection(rows):
    pools = {w: sorted(load(BASE / w / "eligible.json")["rows"], key=lambda r: r["receipt"]) for w in WINDOWS}
    known = {r["corp_code"] for r in rows}
    previous = load(ROOT / "reports/a1_development/filing_screening.json")["cases"]
    excluded = {code for row in previous if row["case_id"].split("-")[0] not in LEGACY
                for code in parse_qs(urlparse(row.get("daily_url", "")).query).get("textCrpCik", [])}
    excluded.add("01194689")  # HD현대마린솔루션, original DART receipt 20240325000947.
    excluded_receipts = {row["receipt_no"] for row in previous} | {"20240325000947"}
    extra = []
    for i in range(max(map(len, pools.values()))):
        for w, pool in pools.items():
            if i >= len(pool):
                continue
            row = pool[i]
            if row["corp_code"] in known or row["corp_code"] in excluded or row["receipt"] in excluded_receipts:
                raise ValueError(f"Overlapping issuer or exposed receipt {row['issuer']}")
            known.add(row["corp_code"])
            extra.append({**row, "cohort": w})
    return rows + extra[:23], extra[23:]


def archive(row, client):
    receipt, expected = row["receipt"], row["pdf_sha256"]
    if not re.fullmatch(r"\d{14}", receipt) or not re.fullmatch(r"\d{8}", row["corp_code"]):
        raise ValueError("Invalid receipt or corporation ID")
    url = urlparse(row["pdf_url"])
    query = parse_qs(url.query)
    if url.hostname != "dart.fss.or.kr" or query.get("rcp_no") != [receipt]:
        raise ValueError(f"{receipt}: wrong official PDF URL")
    path = ARCHIVE / (receipt + ".pdf")
    if not path.exists():
        caches = [CACHE, Path(tempfile.gettempdir()) / f"ipo_a1_enrollment_{row['cohort'].lower()}",
                  Path(tempfile.gettempdir()) / f"ipo_a1_enrollment_{row['cohort']}"]
        source = next((p / path.name for p in caches if (p / path.name).is_file() and sha(p / path.name) == expected), None)
        temp = path.with_suffix(".pdf.part")
        if source:
            shutil.copyfile(source, temp)
        else:
            response = client.get(row["pdf_url"], headers={"Referer": row["pdf_url"].replace("pdf.do", "main.do")})
            response.raise_for_status()
            temp.write_bytes(response.content)
        if sha(temp) != expected:
            raise ValueError(f"{receipt}: downloaded document hash differs")
        temp.replace(path)
    if sha(path) != expected:
        raise ValueError(f"{receipt}: archived file checksum mismatch")
    html = main_html(client, receipt)
    family = registration_options(html, "family")
    title = html.title.get_text(strip=True).split("/")[1].strip()
    if title != TITLE or not family or min(v["receipt"] for v in family) != receipt:
        raise ValueError(f"{receipt}: DART does not confirm the original")
    keys = ("receipt", "corp_code", "issuer", "pdf_url", "pdf_sha256", "period_or_method", "cohort")
    saved = {k: row[k] for k in keys}
    with fitz.open(path) as doc:
        for key in ("ipo_status_anchor", "issuer_valuation_anchor", "per_table_anchor", "applied_multiple_anchor",
                    "offer_band_anchor"):
            if key not in row:
                continue
            anchor = row[key]
            page, quote = int(anchor["page"]), anchor["quote"]
            if not 1 <= page <= len(doc) or not compact(quote) or compact(quote) not in compact(doc[page-1].get_text(sort=True)):
                raise ValueError(f"{receipt}: cannot reproduce {key} on p{page}: {quote}")
            saved[key] = {"page": page, "quote": quote}
        saved.update(pdf_pages=len(doc), bytes=path.stat().st_size, pdf_file=path.relative_to(BASE).as_posix(),
                     family_earliest_receipt=receipt, date_kst=f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}",
                     dart_url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}")
        table = row.get("price_table_page") or next((saved[k]["page"] for k in ("per_table_anchor", "applied_multiple_anchor")
                                                    if k in saved), None)
        if table:
            saved["price_table_page"] = table
    return saved


def run(baseline_only=False):
    ARCHIVE.mkdir(exist_ok=True, parents=True)
    CACHE.mkdir(exist_ok=True, parents=True)
    rows, extras = (original_14(), []) if baseline_only else selection(original_14())
    if not baseline_only and len(rows) != 37:
        raise ValueError(f"Only {len(rows)} fully qualified issuers")
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        verified = [archive(row, client) for row in rows]
    if baseline_only:
        return
    if len({r["corp_code"] for r in verified}) != 37 or len({r["pdf_sha256"] for r in verified}) != 37:
        raise ValueError("Duplicate corporation or document")
    roster = {"version": "accrual-1", "planned_issuers": 37, "target_valid_pairs": 15, "outcomes_opened": 0,
              "valid_pairs_observed": None, "selection_contract_sha256": sha(BASE / "모집규칙.md"),
              "rows": verified, "reserve": [{k: r[k] for k in ("receipt", "issuer", "corp_code", "cohort")}
                                            for r in extras], "pdf_bytes": sum(r["bytes"] for r in verified)}
    output = BASE / "roster.json"
    if output.exists() and load(output) != roster:
        raise ValueError("Frozen roster would change. Preserve the prior version.")
    dump(output, roster)
    print(json.dumps({"included": len(rows), "reserve": len(extras), "file_sha256": sha(output)}))


if __name__ == "__main__":
    import sys

    run("--baseline-only" in sys.argv)
