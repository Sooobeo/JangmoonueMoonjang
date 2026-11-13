"""Evaluator-only input audit. Never imported by the model runner."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import fitz
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/private/pilot_expansion_20261113"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    baseline = json.loads((OUT / "preservation_baseline.json").read_text(encoding="utf-8"))
    preservation = [{"path": name, "unchanged": (ROOT.parent / name).is_file() and sha(ROOT.parent / name) == value}
                    for name, value in baseline["files"].items()]
    cases = []
    for case_id, receipt_file in [("MELCON-DEV-01", "dart_main_20260929000194.html"), ("DTS-DEV-01", "receipt.html")]:
        public = ROOT / "data/cases" / case_id / "public"
        private = ROOT / "data/private" / case_id
        spec = json.loads((public / "provenance/source_spec.json").read_text(encoding="utf-8"))
        chunks = [json.loads(line) for line in (public / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
        pdf_path = public / "raw" / (spec["doc_id"] + ".pdf")
        soup = BeautifulSoup((private / receipt_file).read_bytes(), "html.parser")
        receipt_ids = [option.get("value") for option in soup.select("select#family option") if option.get("value", "").startswith("rcpNo=")]
        checks = {"pdf_hash": sha(pdf_path) == spec["expected_sha256"],
                  "receipt_title": soup.title.get_text(strip=True) == spec["issuer_name"] + "/투자설명서/" + spec["version_date"].replace("-", "."),
                  "receipt_history": set(receipt_ids) == {"rcpNo=" + spec["receipt_no"], "rcpNo=" + spec["original_receipt_no"]},
                  "common_method_bytes": (public / "manual.md").read_bytes() == (ROOT / "data/methods/IPO_PER_B_v0.2.md").read_bytes(),
                  "all_source_checks": all(v is True for v in spec["version_checks"].values()),
                  "whole_pdf": len(chunks) == spec["expected_pages"]}
        bad_pages = []
        with fitz.open(pdf_path) as pdf:
            for index, page in enumerate(pdf):
                text = page.get_text(sort=True)
                # Independent full-page audit of persisted corpus, not a sampling check.
                row = chunks[index]
                footer = re.search(r"(?:Page\s+(\d+)|-\s*(\d+)\s*-)\s*$", text)
                printed = int(footer.group(1) or footer.group(2)) if footer else None
                if (row["page"] != index + 1 or row["case_id"] != case_id or row["doc_id"] != spec["doc_id"]
                        or row["text"] != text or row["printed_page"] != printed
                        or row["text_sha256"] != hashlib.sha256(text.encode()).hexdigest()):
                    bad_pages.append(index + 1)
        checks["every_page_text_identity_footer_hash"] = not bad_pages
        cases.append({"case_id": case_id, "pages": len(chunks), "checks": checks, "bad_pages": bad_pages,
                      "receipt_ids": receipt_ids, "receipt_sha256": sha(private / receipt_file),
                      "public_files": {name: sha(public / name) for name in ["case_manifest.jsonl", "documents.jsonl", "chunks.jsonl", "manual.md"]}})
    report = {"audited_at_utc": datetime.now(timezone.utc).isoformat(), "preserved_file_count": len(preservation),
              "preservation_failures": [r for r in preservation if not r["unchanged"]], "cases": cases,
              "all_passed": all(r["unchanged"] for r in preservation) and all(all(c["checks"].values()) for c in cases)}
    path = OUT / ("input_audit_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path), "preserved_files": len(preservation), "pages_checked": sum(c["pages"] for c in cases), "all_passed": report["all_passed"]}, ensure_ascii=False))
    if not report["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
