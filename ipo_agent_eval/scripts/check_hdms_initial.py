"""Rebuild the HDMS initial-filing corpus and exercise A0 locally without an API call.

Run from ipo_agent_eval with python -m scripts.check_hdms_initial.
The operator item register and human grading sheets never enter the A0 workspace.
"""
import hashlib
import json
import re
import shutil
from decimal import Decimal
from pathlib import Path
from statistics import mean, median
from tempfile import TemporaryDirectory

import fitz

from ipo_eval.corpus import Corpus
from ipo_eval.runner_v2 import execute_v2

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "data/a1_pilot/HDMS"
CASE = "PILOT-01"
DOC = "DOC-01"


def jsonl(path, records):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def compact(text):
    return "".join(text.split()).casefold()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check(project):
    registry = json.loads((PILOT / "operator/original_items.json").read_bytes())
    receipt = registry["source_receipt"]
    source = PILOT / "filing" / f"{receipt}.pdf"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    require(digest == registry["source_sha256"], "Unexpected filing version")
    with fitz.open(source) as doc:
        pages = [p.get_text(sort=True) for p in doc]
    require(len(pages) == 572, "Incomplete filing")
    for item in registry["items"]:
        require(compact(item["anchor"]) in compact(pages[item["page"] - 1]), item["id"])
    require(len({i["id"] for i in registry["items"]}) == len(registry["items"]), "Duplicate item")

    # Compare the printed numerator and denominator with the original table and notes.
    caps = [8093614, 20837071, 14757028, 11916525]
    profits = [221682, 812835, 464742, 370862]
    for n in caps + profits:
        require(f"{n:,}" in pages[268], f"Missing peer input {n}")
    for n in [4761293, 40000000, 4450000, 420190, 44870190, 106113]:
        require(f"{n:,}" in pages[269], f"Missing valuation input {n}")
    for n in [151116175331, 104926507806]:
        require(f"{n:,}" in pages[358], f"Missing net income {n}")
    shares = 40000000 + 4450000 + 420190
    multiples = [Decimal(c) / e for c, e in zip(caps, profits)]
    eps = Decimal(151116175331) / shares
    baseline = Decimal(106113)
    table_price = Decimal(4761293 * 1000000) / shares
    require(round(table_price) == baseline and shares == 44870190, "Valuation or share bridge mismatch")
    # The issuer reports rounded peer inputs. Keep reconstructed estimates labelled.
    estimates = {"H01": Decimal(104926507806) / shares * mean(multiples)}
    for index, item in enumerate(["H02", "H03", "H04", "H05"]):
        estimates[item] = eps * mean(multiples[:index] + multiples[index + 1:])
    estimates["H06"] = eps * median(multiples)
    # The four columns on PDF pp. 267–269 are in the same issuer order.
    closing = [Decimal(x) for x in ("118500", "415.10", "676.00", "14.01")]
    peer_shares = [70773116, 413326315, 175921849, 591723390]
    rates = [Decimal(x) for x in ("1", "128.41", "125.20", "1437.45")]
    close_row = next(line for line in pages[266].splitlines() if "평가일 종가 (A)" in line)
    require(close_row.split()[-4:] == ["118,500", "415.10", "676.00", "14.01"], "Closing price columns")
    for n in peer_shares:
        require(f"{n:,}" in pages[267], "Peer share counts")
    for rate in ("128.41", "125.20", "1,437.45"):
        require(rate in pages[268], "Exchange rate")
    closing_pe = [px * n * fx / (profit * 1000000)
                  for px, n, fx, profit in zip(closing, peer_shares, rates, profits, strict=True)]
    estimates["H07"] = eps * mean(closing_pe)

    directory = project / "data/cases" / CASE / "public"
    (directory / "raw").mkdir(parents=True)
    (project / "config").mkdir()
    (project / "prompts").mkdir()
    (project / "ipo_eval").mkdir()
    for file in (ROOT / "ipo_eval").glob("*.py"):
        shutil.copyfile(file, project / "ipo_eval" / file.name)
    for name in ["common.md", "v2_contract.md", "A0.md"]:
        shutil.copyfile(ROOT / "prompts" / name, project / "prompts" / name)
    shutil.copyfile(ROOT / "config/A0.json", project / "config/A0.json")
    shutil.copyfile(ROOT / "data/methods/IPO_PER_B_v0.2.md", directory / "manual.md")
    shutil.copyfile(source, directory / "raw" / f"{DOC}.pdf")
    (project / "config/cases.json").write_text(json.dumps({
        "version": "A1-dev", "cases": [{"case_id": CASE, "public_directory": directory.relative_to(project).as_posix()}]
    }), encoding="utf-8")
    date = "2024-03-25"
    meta = {"case_id": CASE, "doc_id": DOC, "available_at": date, "cutoff_status": "BEFORE",
            "source_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"}
    jsonl(directory / "documents.jsonl", [{**meta, "title": "증권신고서(지분증권)", "pages": len(pages),
          "sha256": digest, "available_at_precision": "DATE", "version_note": "최초 접수본"}])
    jsonl(directory / "case_manifest.jsonl", [{"case_id": CASE, "issuer_name": "HD현대마린솔루션",
          "cutoff_at": date, "allowed_doc_ids": [DOC]}])
    chunks = []
    for page, text in enumerate(pages, 1):
        footer = re.search(r"Page\s+(\d+)\s*$", text)
        chunks.append({**meta, "chunk_id": f"{DOC}-p{page:04}", "page": page,
                       "printed_page": int(footer[1]) if footer else None, "text": text,
                       "section_state": "CURRENT"})
    jsonl(directory / "chunks.jsonl", chunks)
    corpus = Corpus(directory, CASE)
    corpus.verify()
    require(corpus.read_source([f"{DOC}-p0270"])["chunks"][0]["text"] == pages[269], "Read mismatch")
    require(bool(corpus.search_corpus(CASE, "주당 평가가액")["hits"]), "Valuation table not searchable")
    run_dir, summary = execute_v2(live=False, root=project, case_id=CASE, condition="A0", key_provider=lambda: None)
    require(summary["execution_status"] == "PREFLIGHT_COMPLETE" and summary["actual_model_answer"] is False, "A0 preflight failed")
    require(summary["model_calls"] == 0, "Unexpected model call")
    return {
        "source_sha256": digest, "pages": len(pages), "original_item_anchors": len(registry["items"]),
        "same_rater_repeat_sample": [i["id"] for i in registry["items"] if i["repeat_sample"]],
        "per_reconstructed_from_published_caps_and_profit": str(mean(multiples)),
        "disclosed_market_cap_to_price_krw": str(table_price), "published_price_krw": int(baseline),
        "rounding_and_unit_checks": {
            "diluted_shares": shares, "published_cap_million_krw": 4761293,
            "bridge": "4,761,293 million KRW / 44,870,190 shares",
            "reported_offer_band_krw": [73300, 83400],
            "displayed_discount_endpoints": ["0.214", "0.309"],
            "exact_from_displayed_discount_before_band_rounding": [
                str(baseline * Decimal("0.691")), str(baseline * Decimal("0.786"))
            ]
        },
        "estimated_alternatives_using_published_inputs": {
            k: {"price_krw": str(v), "absolute_change_from_published_P0": str(abs(v - baseline) / baseline)}
            for k, v in estimates.items()},
        "a0": {"execution_status": summary["execution_status"], "model_calls": summary["model_calls"],
               "docs": corpus.case["allowed_doc_ids"], "isolated_input_files":
               sorted(str(p.relative_to(directory).as_posix()) for p in directory.rglob("*") if p.is_file()),
               "run_id": run_dir.name}
    }


if __name__ == "__main__":
    with TemporaryDirectory(prefix="hdms-a1-preflight-") as work:
        print(json.dumps(check(Path(work)), ensure_ascii=False, indent=2))
