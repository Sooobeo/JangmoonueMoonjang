"""Recheck first equity registrations; run with PyMuPDF, pypdf, httpx and BeautifulSoup.

DART replies are cached in the system temporary directory. The checked-in
report pins PDF bytes on subsequent runs, including after a fresh download.
"""
import hashlib
import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import fitz
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(tempfile.gettempdir()) / "ipo_a1_initial_registrations"
OUTPUT = ROOT / "reports/a1_development/filing_screening.json"
TITLE = "증권신고서(지분증권)"
DART = "https://dart.fss.or.kr"

# Physical pages in the initial filing. Only method and issuer earnings-period
# anchors are captured. Peer choices, correctness judgments and labels are absent.
REVIEWED = {
    "MELCON": (208, "2026년 상반기 실적, 일회성 이익 조정 후 연환산", "연환산", "유가증권"),
    "DTS": (256, "2026년 반기 순이익 연환산", "반기", "연환산"),
    "SHINSUNGST": (177, "2023년 반기 실적 연환산", "2023년반기", "연환산"),
    "ALT": (193, "2022년 4~12월 법인세차감전이익과 2023년 1~3월 순이익 합산", "2022년4월", "법인세차감전이"),
    "MILLIE": (225, "2023년 반기 순이익 연환산", "2023년도반기", "연환산"),
    "GIGAVIS": (234, "2022년 연간 순이익, 주식보상비용 조정", "2022년온기", "주식보상비용"),
    "MANYO": (185, "2022년 연간 순이익", "2022년당기순이익", "적용순이익"),
    "SLSBIO": (229, "2023년 2분기 기준 최근 12개월(LTM)", "2023년2분기", "LTM"),
    "ECOEYE": (235, "2022년 3분기~2023년 2분기 최근 4개 분기 합산", "최근4개분기", "2023년2분기"),
    "HANSSAK": (233, "2022년 3분기~2023년 2분기 최근 4개 분기 합산", "최근4개분기", "2023년2분기"),
    "INSWAVE": (234, "2022년 2분기~2023년 1분기 최근 4개 분기, 비경상 손실 조정", "최근4개분기", "비경상적손실"),
    "SYSTEEL": (187, "2022년 3분기~2023년 2분기 최근 4개 분기 합산", "최근4개분기", "2023년2분기"),
    "APR": (256, "2023년 3분기 누적 실적 연환산", "2023년3분기", "연환산"),
    "SANIL": (252, "2024년 1분기 기준 최근 12개월(LTM), 주식보상비용 조정", "과거12개월", "주식보상비용"),
    "JEONJIN": (179, "2024년 1분기 기준 최근 12개월(LTM)", "2024년도1분기", "과거12개월"),
    "TRUEN": (195, "2022년 연간 순이익", "2022년당기순이익", "적용PER배수"),
    "PHILENERGY": (185, "2023년 1분기 기준 최근 12개월(LTM), 파생상품평가손실 조정", "2023년1분기", "파생상품평가손실"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def get(client, url, path, referer=None):
    if path.exists():
        return path.read_bytes()
    headers = {"Referer": referer} if referer else {}
    response = client.get(url, headers=headers)
    response.raise_for_status()
    data = response.content
    if path.suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("Non-PDF at " + url)
    if path.suffix == ".html" and b"openPdfDownload(" not in data:
        raise ValueError("Missing DART document menu at " + url)
    path.write_bytes(data)
    return data


def main_url(rcp):
    return f"{DART}/dsaf001/main.do?rcpNo={rcp}"


def main_html(client, rcp):
    data = get(client, main_url(rcp), CACHE / f"{rcp}.html")
    return BeautifulSoup(data.decode("utf-8"), "html.parser")


def registration_options(soup, select):
    results = []
    for opt in soup.select(f"#{select} option"):
        match = re.fullmatch(r"rcpNo=(\d{14})", opt.get("value", ""))
        if match and opt.get("title", "").strip() == TITLE:
            results.append({"receipt": match[1], "caption": " ".join(opt.stripped_strings).split()})
    return [{**row, "caption": " ".join(row["caption"])} for row in results]


def check_pdf(row, path):
    page, basis, *terms = REVIEWED[row["case_id"].split("-")[0]]
    # Where the method summary and detailed calculation are on different pages,
    # retain both so the record can be checked through either source location.
    table = 190 if row["case_id"].startswith("JEONJIN-") else page
    elapsed = date.fromisoformat(row["date_kst"])
    with fitz.open(path) as doc:
        cover = None
        for i in range(min(12, len(doc))):
            text = "".join(doc[i].get_text().split())
            if ("금융위원회귀중" in text and row["issuer"] in text and
                    re.search(rf"{elapsed.year}년0?{elapsed.month}월0?{elapsed.day}일", text)):
                cover = i + 1
                break
        if not cover:
            raise ValueError("Issuer and dated cover not found")
        text = "".join(doc[page - 1].get_text(sort=True).split())
        table_text = "".join(doc[table - 1].get_text(sort=True).split())
        if not all(word in text for word in terms) or not all(word in table_text for word in ("PER", "주당평가가액")):
            raise ValueError("Reviewed issuer earnings or valuation table locator changed")
        row.update(cover_pdf_page=cover, pdf_pages=len(doc), earnings_basis=basis,
                   method_period_pdf_page=page, price_table_pdf_page=table)
    with path.open("rb") as stream:
        reader = PdfReader(stream)
        alternative = "".join(reader.pages[page - 1].extract_text().split())
        alternate_table = "".join(reader.pages[table - 1].extract_text().split())
    if not all(term in alternative for term in terms) or "PER" not in alternate_table:
        raise ValueError("Second PDF text decoder could not confirm the period or PER")


def lookup_minute(client, original_text, row):
    codes = set(re.findall(r"openCorpInfoNew\('(\d{8})'", original_text))
    if len(codes) != 1:
        return {"daily_lookup": "company_code_unconfirmed"}
    day = row["date_kst"].replace("-", ".")
    code = codes.pop()
    url = f"{DART}/dsac001/mainAll.do?selectDate={day}&textCrpCik={code}&currentPage=1&maxResults=100"
    path = CACHE / f"daily_{code}_{day}.html"
    if not path.exists():
        response = client.get(url)
        response.raise_for_status()
        path.write_bytes(response.content)
    soup = BeautifulSoup(path.read_text("utf-8"), "html.parser")
    link = soup.find(id="r_" + row["receipt_no"])
    if link and link.get("href") == "/dsaf001/main.do?rcpNo=" + row["receipt_no"]:
        cells = [cell.get_text(strip=True) for cell in link.find_parent("tr").find_all("td")]
        if re.fullmatch(r"\d{2}:\d{2}", cells[0]) and day in cells:
            return {"daily_url": url, "precision": "minute", "published_kst": row["date_kst"] + "T" + cells[0] + "+09:00"}
    return {"daily_url": url, "daily_lookup": "exact_receipt_minute_unconfirmed"}


def inspect_case(row):
    cid = row["case_id"]
    pros = row.get("receipt_no") or row["source_documents"][0]["receipt_no"]
    result = {"case_id": cid, "issuer": row["issuer_name"], "cohort": row["cohort"],
              "prospectus_url_for_identification_only": main_url(pros)}
    try:
        with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=90, follow_redirects=True) as client:
            origin = main_html(client, pros)
            related = registration_options(origin, "ref")
            if len(related) != 1:
                raise ValueError("Expected one related equity registration family")
            anchor = related[0]["receipt"]
            family = registration_options(main_html(client, anchor), "family")
            first = [rec for rec in family if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\s+증권신고서\(지분증권\)", rec["caption"])]
            if len(first) != 1 or first[0]["receipt"] != min(rec["receipt"] for rec in family):
                raise ValueError("Missing unique initial unamended receipt in the related family")
            rcp = first[0]["receipt"]
            result.update(receipt_no=rcp, registration_url=main_url(rcp), family_url=main_url(anchor),
                          family_versions=family, date_kst=f"{rcp[:4]}-{rcp[4:6]}-{rcp[6:8]}", precision="date")
            original = main_html(client, rcp)
            title = original.title.get_text(strip=True)
            if TITLE not in title or registration_options(original, "family") != family:
                raise ValueError("Initial receipt and related registration disagree on version family")
            original_text = (CACHE / f"{rcp}.html").read_text("utf-8")
            dcms = set(re.findall(r"openPdfDownload\('" + rcp + r"',\s*'(\d+)'", original_text))
            if len(dcms) != 1:
                raise ValueError("PDF document number is ambiguous")
            dcm = dcms.pop()
            params = f"rcp_no={rcp}&dcm_no={dcm}"
            menu = f"{DART}/pdf/download/main.do?{params}"
            url = f"{DART}/pdf/download/pdf.do?{params}"
            path = CACHE / f"{rcp}.pdf"
            if not path.exists():
                client.get(menu, headers={"Referer": main_url(rcp)}).raise_for_status()
            pdf = get(client, url, path, menu)
            result.update(dart_title=title, dcm_no=dcm, pdf_url=url, pdf_sha256=digest(pdf), bytes=len(pdf))
            result.update(lookup_minute(client, original_text, result))
        result["retrieval"] = "pdf_downloaded"
    except (OSError, httpx.HTTPError, ValueError, RuntimeError) as exc:
        result.update(retrieval="incomplete", reason=str(exc))
    print(cid, result["retrieval"], result.get("receipt_no"), result.get("reason",""), flush=True)
    return result


def write_summary(report):
    rows = report["cases"]
    minutes = sum(r.get("precision") == "minute" for r in rows)
    lines = ["# 최초 증권신고서 재심사", "",
             (f"개발 5곳과 평가 후보 12곳 중 **{report['verified']}/{len(rows)}곳**에서 최초 지분증권 신고서와 과거 실적 PER 산정 근거를 확인했다. "
              f"DART에서 분 단위 공개시각을 확인한 기업은 {minutes}곳이다. 쪽 번호는 PDF 첫 장을 1쪽으로 센다."), "",
             "| 기업 | 구분 | 최초 접수일시(KST) | 적용 이익 | 근거 쪽(실적 / 산정표) | DART 최초 접수 |",
             "|---|---|---|---|---|---|"]
    for row in rows:
        cohort = "개발" if row["cohort"] == "DEVELOPMENT" else "평가 후보"
        when = row.get("published_kst", row.get("date_kst", "미확인")).replace("T", " ").replace("+09:00", "")
        if row.get("precision") == "date":
            when += " (시각 미확인)"
        ref = f"[{row['receipt_no']}]({row['registration_url']})" if row.get("receipt_no") else "미확인"
        pages = f"{row.get('method_period_pdf_page','–')} / {row.get('price_table_pdf_page','–')}"
        lines.append(f"| {row['issuer']} | {cohort} | {when} | {row.get('earnings_basis','미확인')} | {pages} | {ref} |")
    lines += ["", "## 세 차례 점검", ""]
    lines += [f"{i}. {check}" for i, check in enumerate(report["checks"], 1)]
    lines += ["", report["time_rule"],
              ("후보 풀과 원본 항목 연결, 독립 채점과 평가 규모 확정은 파일럿·본 평가에서 진행한다. "
               "기업별 원본 해시, PDF 주소, 정정 이력과 일별 목록 주소는 [증빙 기록](filing_screening.json)에 있다."), ""]
    OUTPUT.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    roster = json.loads((ROOT / "reports/a0_implementation/case_roster.json").read_bytes())["cases"]
    active = [r for r in roster if r["cohort"] in {"DEVELOPMENT", "EVALUATION_CANDIDATE"}
              and r["case_id"] != "HDMS-DEV-01"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(inspect_case, active))
    for row in rows:
        if row["retrieval"] == "pdf_downloaded":
            try:
                check_pdf(row, CACHE / (row["receipt_no"] + ".pdf"))
                row["retrieval"] = "verified"
            except (OSError, ValueError, RuntimeError) as exc:
                row.update(retrieval="incomplete", reason=str(exc))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "purpose": "최초 신고서의 버전·시점·과거 실적 PER 적격성 재심사",
        "scope": "평가 후보 12곳과 HD현대마린솔루션 외 개발 5곳. 최종 평가 표본 결정 및 자연 쟁점 채점은 후속 단계.",
        "checks": [
            "DART 투자설명서의 관련 지분증권 신고서와 정정본·원본 양쪽 본문선택 이력에서 가장 이른 유일한 비정정 접수를 확인했다.",
            "공식 PDF의 원본 SHA-256, 표지 회사명·날짜·물리 쪽을 확인했다. DART 일별 목록에서 접수번호·날짜가 정확히 같은 행에만 시·분을 기록했다.",
            "최초본 발행사 적용 이익의 실적 기간과 PER 산정표를 확인했다. 기록한 물리 쪽의 기간 표지어와 PER를 PyMuPDF와 pypdf 두 추출기로 대조했다.",
        ],
        "time_rule": "일자 정밀도면 최초 신고서와 이전 날짜의 검증 자료만 허용. 같은 날 자료에는 별도 선공개 증거가 필요하다. 분 단위 시각도 같은 분 내 자료의 선후를 보증하지 않는다.",
        "verified": sum(r["retrieval"] == "verified" for r in rows), "cases": rows,
    }
    if OUTPUT.exists():
        previous = {r["case_id"]: r for r in json.loads(OUTPUT.read_bytes())["cases"]}
        for row in rows:
            old = previous.get(row["case_id"], {})
            if old.get("pdf_sha256") and old["pdf_sha256"] != row.get("pdf_sha256"):
                raise ValueError("Previously recorded PDF differs or was unavailable: " + row["case_id"])
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_summary(report)
    print(f"Validated {report['verified']}/{len(rows)} first filings.", flush=True)


if __name__ == "__main__":
    main()
