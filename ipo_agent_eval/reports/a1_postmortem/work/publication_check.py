"""Check the published analysis against the frozen run, source links and Word render."""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import fitz

OUT = Path(__file__).resolve().parents[1]
WORK = OUT / "work"
DEST = WORK / "publication_check.json"


def read(path):
    return json.loads(path.read_bytes())


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(pdf_path):
    report = OUT / "공모가_검토_AI_사후분석.md"
    word = report.with_suffix(".docx")
    csv_path = WORK / "statistics/기업별_37곳_결과.csv"
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len({r["DART 접수번호"] for r in rows}) == len(rows) == 37
    assert sum(int(r["등록 문항 수"]) for r in rows) == 406

    replay = read(WORK / "policy_replay.json")
    assert replay["input_sha256"] == checksum(OUT.parent / "a1_main/v1/analysis/results.json")
    arms = {"rule": (23, 2, 6), "ai": (26, 3, 10), "union": (38, 4, 12),
            "ties_only": (23, 5, 8), "rule_first_fill": (26, 2, 6)}
    for arm, expected in arms.items():
        s = replay["counts"][arm]
        assert (s["items"], s["중대 쟁점"], s["판정 유보"]) == expected
    assert len(replay["issuers"]) == 27
    changed = sum(r["referrals"]["rule"] != r["referrals"]["ties_only"] for r in replay["issuers"])
    assert changed == 9

    paragraphs = report.read_text(encoding="utf8").splitlines()
    headings = [s[3:] for s in paragraphs if s.startswith("## ")]
    pages = []
    with fitz.open(pdf_path) as doc:
        assert len(doc) == len(headings) == 6
        for number, (page, heading) in enumerate(zip(doc, headings), 1):
            blocks = page.get_text("blocks")
            plain = "".join(page.get_text().split())
            assert "".join(heading.split()) in plain
            assert any(b[4].strip() == str(number) for b in blocks)
            bottom = max(b[3] for b in blocks if not b[4].strip().isdigit())
            assert 530 < bottom < page.rect.height - 51
            pages.append({"heading": heading, "body_end_pt": round(bottom, 1)})
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(word) as archive:
        docxml = ET.fromstring(archive.read("word/document.xml"))
    body = docxml.find("w:body", ns)
    tables = len(body.findall("w:tbl", ns))
    text_count = len(body.findall(".//w:p", ns))
    assert tables == 6 and text_count == 152

    checked_links = {}
    for file in sorted(OUT.rglob("*.md")):
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", file.read_text(encoding="utf8"))
        local = [unquote(urlsplit(link).path) for link in links if not urlsplit(link).scheme]
        for target in local:
            path = (file.parent / target).resolve()
            assert path == DEST or path.exists(), f"{file.name} -> {target}"
        checked_links[file.relative_to(OUT).as_posix()] = len(local)
    deliverables = [report, word, report.with_suffix(".html"), OUT / "공식_참고자료와_근거.md",
                    OUT / "분석_진행기록.md", csv_path, WORK / "mechanisms/중대쟁점_사례분석.md"]
    return {"frozen_input_sha256": replay["input_sha256"], "company_rows": len(rows),
            "policy_switches": changed, "rendered_pages": pages, "native_tables": tables,
            "text_blocks_verified_across_formats": text_count, "local_link_counts": checked_links,
            "deliverable_sha256": {f.relative_to(OUT).as_posix(): checksum(f) for f in deliverables},
            "rendered_pdf_sha256": checksum(pdf_path)}


if __name__ == "__main__":
    result = check(Path(sys.argv[1]))
    DEST.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print("Verified reports, 37 companies, policy totals, local references and six rendered pages.")
