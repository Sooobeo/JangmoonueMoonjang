"""Locate the issuer's adopted method in each registration's underwriting section."""

import argparse
import re

import fitz

from scripts.current_b import OUT, dump
from scripts.current_live import load
from scripts.screen_a1_first_filings import CACHE

METHOD = re.compile(
    r"적용(?:재무수치|산식|가치평가방법)|(?:당사|동사)의주당평가가액은|"
    r"주당평가가액산출을위하여|(?:추정|적용)당기순이익은(?:발행회사|동사|당사)|"
    r"주당(?:평가가액|상대가치).{0,24}(?:EV/EBITDA|PSR|PBR)|(?:참고목적|참고용).{0,20}PER|"
    r"주주배정후실권주|제3자배정|일반공모증자")


def notes(window):
    base = OUT / "official/enrollment_expansion" / window
    for path in sorted((base / "locator").glob("*.json")):
        target = base / "method" / path.name
        if target.is_file():
            continue
        r = load(path)
        if not r.get("underwriter_physical_range"):
            continue
        start, end = r["underwriter_physical_range"]
        pages = sorted({*range(1, min(6, r["pdf_pages"]) + 1), *range(start, min(start + 12, end) + 1),
                        *(v["physical_page"] for v in r["method_tables"])})
        found = []
        with fitz.open(CACHE / path.with_suffix(".pdf").name) as doc:
            for p in pages:
                lines = [t.strip() for t in doc[p-1].get_text(sort=True).splitlines() if t.strip()]
                for i, line in enumerate(lines):
                    if METHOD.search("".join(line.split())):
                        found.append({"page": p, "line": line, "next": lines[i+1] if i+1 < len(lines) else ""})
        dump(target, {"receipt": r["receipt"], "issuer": r["issuer"], "rows": found})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("window")
    notes(parser.parse_args().window)
