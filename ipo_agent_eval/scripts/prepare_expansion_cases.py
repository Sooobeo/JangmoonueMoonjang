"""Prepare new W09 development sources without replacing historical inputs.

download saves exact DART PDFs and receipt metadata for source verification.
build requires independently verified source_spec.json values and SHA256.
The source builder never reads private grading records or previous answers.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

import fitz
import httpx

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "SHINSUNGST-DEV-01": ("20231006000225", "SHINSUNGST-PROS-01"),
    "ALT-DEV-01": ("20230714000229", "ALT-PROS-01"),
    "MILLIE-DEV-01": ("20230915000282", "MILLIE-PROS-01"),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_once(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f"Refusing to replace different content: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def download(case_id: str) -> dict:
    receipt, doc_id = CASES[case_id]
    public = ROOT / "data" / "cases" / case_id / "public"
    archive = ROOT / "reports" / "a0_implementation" / "case_roster_sources"
    pdf_path = public / "raw" / f"{doc_id}.pdf"
    receipt_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"
    with httpx.Client(follow_redirects=True) as session:
        session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://dart.fss.or.kr/"})
        response = session.get(receipt_url, timeout=60)
        response.raise_for_status()
        text = response.content.decode("utf-8")
        documents = re.findall(r"openPdfDownload\('([0-9]+)', '([0-9]+)'", text)
        documents = [item for item in documents if item[0] == receipt]
        if len(documents) != 1:
            raise ValueError("Expected exactly one PDF download link for this receipt")
        document_no = documents[0][1]
        popup = f"https://dart.fss.or.kr/pdf/download/main.do?rcp_no={receipt}&dcm_no={document_no}"
        session.headers["Referer"] = receipt_url
        response_popup = session.get(popup, timeout=60)
        response_popup.raise_for_status()
        pdf_url = f"https://dart.fss.or.kr/pdf/download/pdf.do?rcp_no={receipt}&dcm_no={document_no}"
        if f"rcp_no={receipt}&amp;dcm_no={document_no}" not in response_popup.text and f"rcp_no={receipt}&dcm_no={document_no}" not in response_popup.text:
            raise ValueError("DART download popup does not contain the expected PDF link")
        session.headers["Referer"] = popup
        pdf = session.get(pdf_url, timeout=120)
        pdf.raise_for_status()
        if not pdf.content.startswith(b"%PDF-"):
            raise ValueError("DART did not return a PDF")
    write_once(pdf_path, pdf.content)
    write_once(archive / f"{case_id}_receipt.html", response.content)
    with fitz.open(stream=pdf.content, filetype="pdf") as document:
        pages = len(document)
    metadata = {"case_id": case_id, "doc_id": doc_id, "receipt_no": receipt,
                "document_no": document_no, "dart_url": receipt_url, "source_url": pdf_url,
                "pdf_sha256": digest(pdf.content), "pdf_bytes": len(pdf.content), "pages": pages,
                "receipt_html_sha256": digest(response.content),
                "note": "Session cookies are not persisted. Downloaded bytes are exact DART PDF bytes."}
    write_once(archive / f"{case_id}_download.json", json_bytes(metadata))
    return metadata


def build(case_id: str) -> dict:
    receipt, doc_id = CASES[case_id]
    public = ROOT / "data" / "cases" / case_id / "public"
    spec_path = public / "provenance" / "source_spec.json"
    spec = json.loads(spec_path.read_bytes())
    if spec["case_id"] != case_id or spec["doc_id"] != doc_id or spec["receipt_no"] != receipt:
        raise ValueError("Source identity mismatch")
    if not spec["version_checks"] or any(value is not True for value in spec["version_checks"].values()):
        raise ValueError("Every source/version/eligibility check must be verified")
    cutoff = datetime.fromisoformat(spec["cutoff_at"])
    if cutoff.tzinfo is None or not date.fromisoformat(spec["version_date"]) <= cutoff.date() < date.fromisoformat(spec["general_subscription_start"]):
        raise ValueError("Source and cutoff must precede subscription")
    if receipt[:8] != spec["version_date"].replace("-", ""):
        raise ValueError("Receipt date mismatch")
    pdf_path = public / "raw" / f"{doc_id}.pdf"
    pdf_hash = digest(pdf_path.read_bytes())
    if pdf_hash != spec["expected_sha256"]:
        raise ValueError("PDF differs from reviewed source")
    chunks = []
    with fitz.open(pdf_path) as pdf:
        if len(pdf) != spec["expected_pages"]:
            raise ValueError("Unexpected page count")
        for index, page in enumerate(pdf):
            text = page.get_text(sort=True)
            footer = re.search(r"(?:Page\s+(\d+)|-\s*(\d+)\s*-)\s*$", text)
            chunks.append({"case_id": case_id, "doc_id": doc_id,
                           "chunk_id": f"{doc_id}-p{index + 1:04d}", "page": index + 1,
                           "printed_page": int(footer.group(1) or footer.group(2)) if footer else None,
                           "text": text, "source_url": spec["source_url"],
                           "available_at": spec["version_date"], "available_at_precision": "DATE",
                           "cutoff_status": "BEFORE", "text_sha256": digest(text.encode("utf-8")),
                           "text_extraction_method": "PyMuPDF Page.get_text(sort=True)",
                           "previous_chunk_id": f"{doc_id}-p{index:04d}" if index else None,
                           "next_chunk_id": f"{doc_id}-p{index + 2:04d}" if index + 1 < len(pdf) else None,
                           "extraction_warnings": ["Original formatting, colour and bold are not preserved; inspect correction headings and complete neighbouring pages."]})
    manifest = {key: spec[key] for key in ("case_id", "issuer_name", "issuer_legal_name", "market", "cutoff_at", "general_subscription_start")}
    manifest.update(cohort="DEVELOPMENT", valuation_method="HISTORICAL_PER", allowed_doc_ids=[doc_id],
                    is_pre_cutoff_verified=True, cutoff_status="BEFORE", manual_path="manual.md",
                    manual_version="IPO_PER_B_v0.2", case_facts_source="Only the registered public prospectus; private criteria are excluded.")
    document = {key: spec[key] for key in ("case_id", "doc_id", "receipt_no", "original_receipt_no", "dart_url", "source_url", "cutoff_at", "version_note", "version_checks", "version_evidence")}
    document.update(title=spec["issuer_name"] + " 정정 투자설명서", version=spec["version_date"] + " 정정 투자설명서",
                    local_path=f"raw/{doc_id}.pdf", sha256=pdf_hash, byte_count=pdf_path.stat().st_size,
                    pages=len(chunks), page_count=len(chunks), available_at=spec["version_date"],
                    available_at_precision="DATE", cutoff_status="BEFORE", is_pre_cutoff_verified=True,
                    page_numbering="page is 1-based physical PDF page; printed_page is its extracted footer or null",
                    extraction="Complete pages extracted using PyMuPDF with no selected-page deletion or truncation",
                    verification_limit="Public availability is verified to date precision, not intraday timestamp.")
    def jsonl(rows):
        return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    outputs = {public / "case_manifest.jsonl": jsonl([manifest]), public / "documents.jsonl": jsonl([document]),
               public / "chunks.jsonl": jsonl(chunks), public / "manual.md": (ROOT / "data/methods/IPO_PER_B_v0.2.md").read_bytes()}
    for path, content in outputs.items():
        if path.exists() and path.read_bytes() != content:
            raise FileExistsError(f"Refusing to overwrite different prepared input: {path}")
    for path, content in outputs.items():
        write_once(path, content)
    summary = {"case_id": case_id, "pages": len(chunks), "pdf_sha256": pdf_hash,
               "source_spec_sha256": digest(spec_path.read_bytes()), "empty_pages": [row["page"] for row in chunks if not row["text"].strip()],
               "prepared_file_sha256": {path.name: digest(content) for path, content in outputs.items()},
               "version_checks": spec["version_checks"], "all_checks_passed": True}
    write_once(public / "provenance/preparation_summary.json", json_bytes(summary))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["download", "build"])
    parser.add_argument("--case-id", required=True, choices=sorted(CASES))
    args = parser.parse_args()
    print(json.dumps((download if args.operation == "download" else build)(args.case_id), ensure_ascii=False, indent=2))
