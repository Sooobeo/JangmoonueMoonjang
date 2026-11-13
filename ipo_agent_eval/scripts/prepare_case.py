"""Build a new registered pilot corpus from verified public metadata and full PDF.

Never reads gold, previous answers or private folders; never overwrites changed files.
HDMS keeps its historical input snapshot and is deliberately unsupported here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
NEW_CASES = {"MELCON-DEV-01": "MELCON-PROS-01", "DTS-DEV-01": "DTS-PROS-01"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def jsonl_bytes(rows):
    return ("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)).encode("utf-8")


def build(case_id, root=ROOT):
    if case_id not in NEW_CASES:
        raise ValueError("Only explicitly registered new pilot cases can be prepared")
    public = root / "data" / "cases" / case_id / "public"
    spec_path = public / "provenance" / "source_spec.json"
    spec_bytes = spec_path.read_bytes()
    spec = json.loads(spec_bytes)
    doc_id = NEW_CASES[case_id]
    if spec["case_id"] != case_id or spec["doc_id"] != doc_id:
        raise ValueError("Case/document identity mismatch")
    checks = spec["version_checks"]
    if not checks or any(value is not True for value in checks.values()):
        raise ValueError("Every public source/version check must be verified before preparation")
    cutoff = datetime.fromisoformat(spec["cutoff_at"])
    available = date.fromisoformat(spec["version_date"])
    subscription = date.fromisoformat(spec["general_subscription_start"])
    if cutoff.tzinfo is None or not available <= cutoff.date() < subscription:
        raise ValueError("Version/cutoff must precede general subscription")
    if spec["receipt_no"][:8] != available.strftime("%Y%m%d"):
        raise ValueError("Receipt and version dates disagree")
    pdf_path = public / "raw" / (doc_id + ".pdf")
    pdf_bytes = pdf_path.read_bytes()
    pdf_hash = digest(pdf_bytes)
    if pdf_hash != spec["expected_sha256"]:
        raise ValueError("PDF differs from verified source")
    manual_path = root / "data" / "methods" / "IPO_PER_B_v0.2.md"
    manual = manual_path.read_bytes()
    chunks = []
    with fitz.open(pdf_path) as pdf:
        if len(pdf) != spec["expected_pages"]:
            raise ValueError("Unexpected source page count")
        for index, page in enumerate(pdf):
            text = page.get_text(sort=True)
            footer = re.search(r"(?:Page\s+(\d+)|-\s*(\d+)\s*-)\s*$", text)
            chunks.append({
                "case_id": case_id, "doc_id": doc_id,
                "chunk_id": f"{doc_id}-p{index + 1:04d}", "page": index + 1,
                "printed_page": int(footer.group(1) or footer.group(2)) if footer else None,
                "text": text, "source_url": spec["source_url"],
                "available_at": spec["version_date"], "available_at_precision": "DATE",
                "cutoff_status": "BEFORE", "text_extraction_method": "PyMuPDF Page.get_text(sort=True)",
                "text_sha256": digest(text.encode("utf-8")),
                "previous_chunk_id": f"{doc_id}-p{index:04d}" if index else None,
                "next_chunk_id": f"{doc_id}-p{index + 2:04d}" if index + 1 < len(pdf) else None,
                "extraction_warnings": [
                    "글자 색과 굵기는 텍스트에 보존되지 않는다. 정정 전·후 제목과 본문 표를 함께 확인한다.",
                    "표가 다음 페이지로 이어질 수 있다. 단위·기간·열 제목이 없으면 앞뒤 페이지를 함께 읽는다.",
                ],
            })
    manifest = {key: spec[key] for key in ("case_id", "issuer_name", "issuer_legal_name", "market", "cutoff_at", "general_subscription_start")}
    manifest.update(cohort="DEVELOPMENT_PILOT", valuation_method="HISTORICAL_PER",
                    allowed_doc_ids=[doc_id], is_pre_cutoff_verified=True, cutoff_status="BEFORE",
                    manual_path="manual.md", manual_version="0.2.0-pilot",
                    case_facts_source="허용 공시의 본문. 방법서는 공통 절차만 제공하며 기준표는 모델에 제공하지 않는다.")
    document = {key: spec[key] for key in ("case_id", "doc_id", "receipt_no", "original_receipt_no", "dart_url", "source_url", "cutoff_at", "version_note", "version_checks", "version_evidence")}
    document.update(title=spec["issuer_name"] + " 정정 투자설명서",
                    version=spec["version_date"] + " 정정 투자설명서", local_path=f"raw/{doc_id}.pdf",
                    sha256=pdf_hash, byte_count=len(pdf_bytes), pages=len(chunks), page_count=len(chunks),
                    available_at=spec["version_date"], available_at_precision="DATE", cutoff_status="BEFORE",
                    is_pre_cutoff_verified=True,
                    page_numbering="page는 1기반 PDF 물리 쪽. printed_page는 매 장의 Page n 또는 - n - footer를 직접 읽은 값이며 확인되지 않으면 null이다.",
                    extraction="PyMuPDF 위치 정렬 텍스트를 모든 쪽에 적용. 표·본문·주석과 정정 전후를 선택 삭제 없이 포함.",
                    verification_limit="공식 접수·정정 이력과 원문을 대조했다. 실제 공개 시각은 날짜 단위까지만 확인했다.")
    outputs = {
        public / "case_manifest.jsonl": jsonl_bytes([manifest]),
        public / "documents.jsonl": jsonl_bytes([document]),
        public / "chunks.jsonl": jsonl_bytes(chunks),
        public / "manual.md": manual,
    }
    summary = {"case_id": case_id, "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "pages": len(chunks), "pdf_sha256": pdf_hash, "source_spec_sha256": digest(spec_bytes),
               "method_sha256": digest(manual), "empty_pages": [c["page"] for c in chunks if not c["text"].strip()],
               "unmapped_printed_pages": [c["page"] for c in chunks if c["printed_page"] is None],
               "prepared_file_sha256": {p.name: digest(b) for p, b in outputs.items()},
               "version_checks": checks, "all_checks_passed": True}
    summary_path = public / "provenance" / "preparation_summary.json"
    if summary_path.exists():
        saved = json.loads(summary_path.read_bytes())
        if {k: v for k, v in summary.items() if k != "created_at_utc"} != {k: v for k, v in saved.items() if k != "created_at_utc"}:
            raise FileExistsError("Prepared source/method/provenance differs from its saved summary")
        summary = saved
    # Validate every destination before writing anything. Identical rebuilds are safe.
    for path, data in outputs.items():
        if path.exists() and path.read_bytes() != data:
            raise FileExistsError(f"Refusing to replace different prepared input: {path}")
    for path, data in outputs.items():
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(data)
    if not summary_path.exists():
        with summary_path.open("xb") as stream:
            stream.write(json_bytes(summary))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True, choices=sorted(NEW_CASES))
    print(json.dumps(build(parser.parse_args().case_id), ensure_ascii=False, indent=2))
