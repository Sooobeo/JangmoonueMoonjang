"""Download the public HDMS prospectus and build an auditable page corpus.

No gold file, answer key, or model response is read by this script.
Run from any directory: python ipo_agent_eval/scripts/prepare_hdms.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import fitz
import httpx
from bs4 import BeautifulSoup


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parent
PUBLIC = PROJECT / "data" / "public"
PDF_URL = "https://money2.daishin.com/html/Notice/2024/downloads/hdmarine0509_03.pdf"
DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240424000222"
DART_BODY_URL = (
    "https://dart.fss.or.kr/report/viewer.do?rcpNo=20240424000222"
    "&dcmNo=9913887&eleId=1&offset=686&length=302117&dtd=dart4.xsd"
)
EXPECTED_SHA256 = "9f563a7e2af8c39a96567e83268321b0a40cf334abe94e7377b00ca0351f31ab"
CASE_ID = "HDMS-DEV-01"
DOC_ID = "HDMS-PROS-01"
CUTOFF = "2024-04-24T23:59:59+09:00"
VERSION_DATE = "2024-04-24"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def download(url: str) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=90) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def verify_receipt(refresh: bool) -> dict:
    """Keep only historical receipt metadata, not today's related-report links."""
    destination = PUBLIC / "provenance" / "receipt_verification.json"
    if destination.exists() and not refresh:
        return json.loads(destination.read_text(encoding="utf-8"))
    main_bytes = download(DART_URL)
    body_bytes = download(DART_BODY_URL)
    main = BeautifulSoup(main_bytes, "html.parser", from_encoding="utf-8")
    body = BeautifulSoup(body_bytes, "html.parser", from_encoding="utf-8")
    title = main.title.get_text(" ", strip=True) if main.title else ""
    allowed_receipts = {"rcpNo=20240417000055", "rcpNo=20240424000222"}
    history = {}
    for option in main.select("option"):
        receipt = option.get("value", "")
        if receipt in allowed_receipts:
            history[receipt] = " ".join(option.get_text(" ", strip=True).split())
    body_text = " ".join(body.get_text(" ", strip=True).split())
    expected_title = "HD현대마린솔루션/투자설명서/2024.04.24"
    checks = {
        "receipt_title_matches": title == expected_title,
        "corrected_receipt_in_history": "2024.04.24" in history.get("rcpNo=20240424000222", ""),
        "original_receipt_in_history": "2024.04.17" in history.get("rcpNo=20240417000055", ""),
        "correction_date_in_body": "2024년 04월 24일" in body_text[:200],
        "correction_type_in_body": "공모가액 확정에 따른 기재사항 정정" in body_text[:400],
    }
    result = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "receipt_url": DART_URL,
        "correction_body_url": DART_BODY_URL,
        "receipt_response_sha256": hashlib.sha256(main_bytes).hexdigest(),
        "correction_body_response_sha256": hashlib.sha256(body_bytes).hexdigest(),
        "title": title,
        "historical_receipts": history,
        "correction_heading_excerpt": body_text[:260],
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "note": "현재 접수 화면의 다른 관련 공시 링크는 보관한 발췌와 검색 자료에서 제외했다. 공개 시각은 날짜까지만 확인했다.",
    }
    write_json(destination, result)
    return result


def build(refresh: bool = False, render: bool = False) -> dict:
    for subdir in ("raw", "provenance", "inspection"):
        (PUBLIC / subdir).mkdir(parents=True, exist_ok=True)
    pdf_path = PUBLIC / "raw" / f"{DOC_ID}.pdf"
    if refresh or not pdf_path.exists():
        pdf_path.write_bytes(download(PDF_URL))
    actual_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if actual_hash != EXPECTED_SHA256:
        raise ValueError(f"PDF checksum mismatch: {actual_hash}")
    receipt = verify_receipt(refresh)
    with fitz.open(pdf_path) as pdf:
        if len(pdf) != 638:
            raise ValueError(f"Unexpected PDF page count: {len(pdf)}")
        correction_text = pdf[2].get_text(sort=True)
        cover_text = pdf[53].get_text(sort=True)
        version_checks = {
            "sha256_matches": actual_hash == EXPECTED_SHA256,
            "page_count_matches": len(pdf) == 638,
            "pdf_correction_date": bool(re.search(r"2024년\s*04월\s*24일", correction_text)),
            "pdf_correction_reason": "공모가액 확정에 따른 기재사항 정정" in correction_text,
            "pdf_subscription_start": bool(re.search(r"2024년\s*4월\s*25일", cover_text)),
            "dart_receipt_verified": receipt["all_checks_passed"],
        }
        verified = all(version_checks.values())
        cutoff_status = "BEFORE" if verified else "UNKNOWN"
        chunks = []
        for index, page in enumerate(pdf):
            text = page.get_text(sort=True)
            footer_match = re.search(r"Page\s+(\d+)\s*$", text)
            printed_page = int(footer_match.group(1)) if footer_match else None
            chunks.append({
                "case_id": CASE_ID,
                "doc_id": DOC_ID,
                "chunk_id": f"{DOC_ID}-p{index + 1:04d}",
                "page": index + 1,
                "printed_page": printed_page,
                "text": text,
                "source_url": PDF_URL,
                "available_at": VERSION_DATE,
                "available_at_precision": "DATE",
                "cutoff_status": cutoff_status,
                "text_extraction_method": "PyMuPDF Page.get_text(sort=True)",
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "previous_chunk_id": f"{DOC_ID}-p{index:04d}" if index else None,
                "next_chunk_id": f"{DOC_ID}-p{index + 2:04d}" if index + 1 < len(pdf) else None,
                "extraction_warnings": [
                    "글자 색과 굵기는 텍스트에 보존되지 않는다. 정정 전·후 제목과 본문 표를 함께 확인한다.",
                    "표가 다음 페이지로 이어질 수 있다. 단위·기간·열 제목이 없으면 앞뒤 페이지를 함께 읽는다.",
                ],
            })
        if render:
            for page_no in (3, 54, 329, 330, 331, 332, 424, 425):
                pdf[page_no - 1].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(
                    PUBLIC / "inspection" / f"page-{page_no}.png"
                )
    manifest = {
        "case_id": CASE_ID,
        "issuer_name": "HD현대마린솔루션",
        "issuer_legal_name": "에이치디현대마린솔루션 주식회사",
        "market": "KOSPI",
        "cohort": "DEVELOPMENT_PILOT",
        "valuation_method": "HISTORICAL_PER",
        "cutoff_at": CUTOFF,
        "cutoff": CUTOFF,
        "general_subscription_start": "2024-04-25",
        "allowed_doc_ids": [DOC_ID],
        "is_pre_cutoff_verified": verified,
        "cutoff_status": cutoff_status,
        "manual_path": "manual.md",
        "case_facts_source": "허용 공시의 본문. 방법서는 검토 절차만 제공하며 채점표는 모델에 제공하지 않는다.",
    }
    document = {
        "case_id": CASE_ID,
        "doc_id": DOC_ID,
        "title": "HD현대마린솔루션 정정 투자설명서",
        "version": "2024-04-24 정정 투자설명서",
        "receipt_no": "20240424000222",
        "original_receipt_no": "20240417000055",
        "dart_url": DART_URL,
        "source_url": PDF_URL,
        "local_path": "raw/HDMS-PROS-01.pdf",
        "sha256": actual_hash,
        "byte_count": pdf_path.stat().st_size,
        "page_count": len(chunks),
        "pages": len(chunks),
        "available_at": VERSION_DATE,
        "available_at_precision": "DATE",
        "cutoff_at": CUTOFF,
        "cutoff_status": cutoff_status,
        "is_pre_cutoff_verified": verified,
        "version_checks": version_checks,
        "version_evidence": [
            {"source_url": DART_URL, "locator": "문서 제목과 정정 이력", "description": "공식 접수번호 20240424000222, 날짜 2024.04.24, 최초 접수 2024.04.17 확인"},
            {"chunk_id": "HDMS-PROS-01-p0003", "page": 3, "printed_page": 1, "description": "정정 신고일 2024년 04월 24일과 정정 이유"},
            {"chunk_id": "HDMS-PROS-01-p0054", "page": 54, "printed_page": 52, "description": "투자설명서 표지의 청약기간 2024년 4월 25일~26일"},
        ],
        "verification_limit": "동일 공시의 DART 접수·정정표와 증권사 PDF를 대조했다. PDF 제공 URL의 다운로드 폴더 날짜를 당시 공시일로 사용하지 않았다. 실제 공개 시각은 날짜보다 세밀하게 확인하지 못했다.",
        "version_note": "DART 접수번호 20240424000222의 2024-04-24 정정 투자설명서. 공식 접수 제목·정정 이력·정정표와 PDF 표지를 대조했고 실제 공개 시각은 날짜까지만 확인했다.",
        "original_date_discrepancy": "PDF 정정표 최초제출일의 2023년 표기는 보존했다. 공식 DART 이력에는 2024.04.17이 표시되어 있어 메타데이터는 DART 날짜를 사용한다.",
        "page_numbering": "page는 PDF 첫 장부터 센 1기반 물리 쪽이다. printed_page는 각 장 footer의 Page 숫자를 직접 읽었으며, 목차 2장은 null이다. 본문은 물리 쪽=인쇄 쪽+2이다.",
        "extraction": "PyMuPDF의 위치 정렬 텍스트를 쪽 전체에 적용했다. 모든 본문·표·주석을 포함하고 쪽별로 잘랐으며, 글자 색과 굵기는 보존하지 않는다.",
    }
    write_jsonl(PUBLIC / "chunks.jsonl", chunks)
    write_jsonl(PUBLIC / "documents.jsonl", [document])
    write_jsonl(PUBLIC / "case_manifest.jsonl", [manifest])
    shutil.copyfile(REPO / "phase1" / "IPO_PER_검토방법서.md", PUBLIC / "manual.md")
    summary = {
        "case_id": CASE_ID,
        "document_count": 1,
        "chunk_count": len(chunks),
        "empty_pages": [row["page"] for row in chunks if not row["text"].strip()],
        "unmapped_printed_pages": [row["page"] for row in chunks if row["printed_page"] is None],
        "is_pre_cutoff_verified": verified,
        "sha256": actual_hash,
        "version_checks": version_checks,
    }
    write_json(PUBLIC / "provenance" / "preparation_summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Download PDF and receipt metadata again")
    parser.add_argument("--render", action="store_true", help="Render the pages used for visual inspection")
    args = parser.parse_args()
    print(json.dumps(build(args.refresh, args.render), ensure_ascii=True, indent=2))
