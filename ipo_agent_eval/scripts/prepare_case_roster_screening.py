"""Archive primary prospectuses for eligibility screening only; no model runs or gold."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re

import fitz
import httpx

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "reports/a0_implementation/case_roster_sources/evaluation_screening"
CANDIDATES = [
    ("GIGAVIS", "기가비스", "20230512000029"),
    ("MANYO", "마녀공장", "20230524000327"),
    ("SLSBIO", "에스엘에스바이오", "20230926000456"),
    ("ECOEYE", "에코아이", "20231109000220"),
    ("HANSSAK", "한싹", "20230918000119"),
    ("INSWAVE", "인스웨이브시스템즈", "20230913000348"),
    ("SYSTEEL", "에스와이스틸텍", "20231031000078"),
    ("COXEM", "코셈", "20240206000494"),
    ("APR", "에이피알", "20240213000795"),
    ("NOBLAND", "노브랜드", "20240510000093"),
    ("SANIL", "산일전기", "20240717000412"),
    ("JEONJIN", "전진건설로봇", "20240807000292"),
    ("TRUEN", "트루엔", "20230503000321"),
    ("PHILENERGY", "필에너지", "20230704000143"),
    ("PURIT", "퓨릿", "20231004000221"),
]


def screen(candidate):
    slug, name, receipt = candidate
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    metadata_path = ARCHIVE / f"{slug}.json"
    if metadata_path.exists():
        return json.loads(metadata_path.read_bytes())
    main = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"
    with httpx.Client(follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as session:
        response = session.get(main, timeout=90)
        response.raise_for_status()
        document = re.findall(r"openPdfDownload\('" + receipt + r"', '([0-9]+)'", response.text)
        if len(document) != 1:
            raise ValueError(f"No unique PDF: {slug}")
        dcm = document[0]
        popup = f"https://dart.fss.or.kr/pdf/download/main.do?rcp_no={receipt}&dcm_no={dcm}"
        session.get(popup, headers={"Referer": main}, timeout=90).raise_for_status()
        url = f"https://dart.fss.or.kr/pdf/download/pdf.do?rcp_no={receipt}&dcm_no={dcm}"
        pdf = session.get(url, headers={"Referer": popup}, timeout=120)
        pdf.raise_for_status()
    if not pdf.content.startswith(b"%PDF-"):
        raise ValueError(f"Not PDF: {slug}")
    target = ARCHIVE / f"{slug}.pdf"
    with target.open("xb") as stream:
        stream.write(pdf.content)
    with (ARCHIVE / f"{slug}_receipt.html").open("xb") as stream:
        stream.write(response.content)
    hits = []
    with fitz.open(target) as document:
        page_count = len(document)
        for i, page in enumerate(document):
            text = page.get_text(sort=True)
            # Keep a few full pages for manual method/period screening, not answer design.
            if (("적용" in text and "PER" in text and ("평가가액" in text or "평가가치" in text))
                    or ("추정 당기" in text and "PER" in text)
                    or ("적용 EV/EBITDA" in text)):
                hits.append({"page": i + 1, "text": text})
    metadata = {"candidate_id": slug, "issuer_name": name, "receipt_no": receipt,
                "dart_url": main, "source_url": url, "page_count": page_count,
                "pdf_sha256": hashlib.sha256(pdf.content).hexdigest(),
                "screening_pages": hits,
                "scope": "Eligibility/source metadata only. No model execution, scoring or private gold."}
    with metadata_path.open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return metadata


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(screen, CANDIDATES):
            print(json.dumps({k: v for k, v in result.items() if k != "screening_pages"}, ensure_ascii=False), flush=True)
