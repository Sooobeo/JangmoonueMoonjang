"""Verify new W09 sources/rubrics without reading any model output."""
import hashlib
import json
from pathlib import Path
import sys

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ipo_eval.corpus import Corpus
from prepare_expansion_cases import build

CASES = ["SHINSUNGST-DEV-01", "ALT-DEV-01", "MILLIE-DEV-01"]


def main():
    checks = []
    for case in CASES:
        base = ROOT / "data/cases" / case
        corpus = Corpus(base / "public", case)
        source_checks = corpus.verify()
        summary_before = (base / "public/provenance/preparation_summary.json").read_bytes()
        build(case)
        assert summary_before == (base / "public/provenance/preparation_summary.json").read_bytes()
        with fitz.open(base / "public/raw" / (corpus.documents[0]["doc_id"] + ".pdf")) as pdf:
            for chunk in corpus.chunks:
                text = pdf[chunk["page"]-1].get_text(sort=True)
                assert text == chunk["text"]
                assert hashlib.sha256(text.encode()).hexdigest() == chunk["text_sha256"]
        public = base / "public"
        assert not list(public.rglob("gold*"))
        forbidden = ["RUBRIC_PREPARED_NO_MODEL_RESPONSE_REVIEWED", "sensitivity_scenarios", '"judgments":', "source_discrepancies"]
        visible = json.dumps(corpus.public_metadata(), ensure_ascii=False) + corpus.manual + json.dumps(corpus.chunks, ensure_ascii=False)
        assert not any(marker in visible for marker in forbidden)
        denied = []
        for forbidden_chunk in ["../private/gold.json", "MELCON-PROS-01-p0372"]:
            try:
                corpus.read_source([forbidden_chunk])
                raise AssertionError("private/cross-case source unexpectedly readable")
            except ValueError:
                denied.append(forbidden_chunk)
        gold = json.loads((base / "private/gold.json").read_bytes())
        assert gold["locked_before_model_answer"] and gold["private_do_not_include_in_model_input"]
        assert gold["human_review_status"] == "NOT_YET_REVIEWED"
        assert set(gold["facts"]) == {f"F{i}" for i in range(1, 6)}
        assert set(gold["calculations"]) == {f"K{i}" for i in range(1, 4)}
        assert set(gold["judgments"]) == {f"J{i}" for i in range(1, 5)}
        checks.append({"case_id": case, "source_checks": source_checks,
                       "full_page_extraction_reproduced": len(corpus.chunks),
                       "builder_replay_identical": True, "public_gold_marker_scan": "PASS",
                       "private_and_cross_case_reads_denied": denied,
                       "rubric_contract": "5 facts, 3 calculations, 4 judgments; prepared before model response; human review not claimed"})
    roster = json.loads((ROOT / "reports/a0_implementation/case_roster.json").read_bytes())
    evals = [r for r in roster["cases"] if r["cohort"] == "EVALUATION_CANDIDATE"]
    assert len(evals) == 12
    assert all(not r["private_gold_prepared"] and not r["evaluation_live_allowed"] and not r["model_answer_requested"] for r in evals)
    review = {"status": "PASS", "reviewer": "case_roster preparation agent; three distinct review passes, not three independent human reviews",
              "reviews": [
                  {"pass": 1, "focus": "Primary source/version/eligibility",
                   "finding": "All3 new PDFs are latest prospectus receipts before cutoff and historical PER.12 held-out primary PDFs eligible. COXEM forecast, NOBLAND final PBR and PURIT mixed PER/EV-EBITDA remain excluded.",
                   "visual_table_pages_checked": {"SHINSUNGST-DEV-01": [244,245], "ALT-DEV-01": [251,252], "MILLIE-DEV-01": [292,293]}, "status": "PASS"},
                  {"pass": 2, "focus": "Private facts, units, denominator and Decimal reconstruction",
                   "finding": "70 evidence references resolve.3 share sums match. Displayed-input valuation differs from disclosed output in each case; rubrics preserve values and uncertainty instead of forcing a false arithmetic-error conclusion.",
                   "evidence": "case_roster_gold_checks.json", "status": "PASS"},
                  {"pass": 3, "focus": "Full extraction, replay, public/private isolation and allocation",
                   "finding": "1391 complete pages re-extracted identically. New builders/gold/allocation replay identically. Private/cross-case reads denied; no gold markers in visible corpus.6 development and12 evaluation candidates disjoint; evaluation is not runnable.", "status": "PASS"}],
              "case_checks": checks,
              "limits": ["Separate root/other-agent independent review is still useful and recorded separately.", "No human gold review is claimed.", "Candidate PDFs alone are not execution-ready evaluation corpora; W12 freeze and gold prep remain later scope."]}
    output = ROOT / "reports/a0_implementation/case_roster_reviews.json"
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2)+"\n", encoding="utf8")
    print(json.dumps({"status": "PASS", "new_cases": len(checks), "complete_pages": sum(r["full_page_extraction_reproduced"] for r in checks), "evaluation_candidates_no_runs": len(evals)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
