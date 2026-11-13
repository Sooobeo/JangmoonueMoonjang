"""Read-only D5 input/config audit. Does not load credentials or call a model."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT))
from ipo_eval.cases import resolve_case
from ipo_eval.corpus import Corpus


def read_json(path):
    data = Path(path).read_bytes()
    return json.loads(data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit():
    configs = {condition: read_json(PROJECT / "config" / f"{condition}.json") for condition in ("B", "A0")}
    differences = {key: {condition: config.get(key) for condition, config in configs.items()}
                   for key in set(configs["B"]) | set(configs["A0"]) if configs["B"].get(key) != configs["A0"].get(key)}
    roster = read_json(HERE / "case_roster.json")
    registration = read_json(PROJECT / "config/cases.json")
    development = {case["case_id"]: case for case in roster["cases"] if case["cohort"] == "DEVELOPMENT"}
    evaluation = {case["case_id"]: case for case in roster["cases"] if case["cohort"] == "EVALUATION_CANDIDATE"}
    registered = {case["case_id"] for case in registration["cases"]}
    problems = []
    if set(differences) != {"condition"}:
        problems.append("B/A0 differ in shared configuration")
    if registered != set(development) or registered & set(evaluation):
        problems.append("Registered cases do not equal the development-only roster")
    if set(development) & set(evaluation):
        problems.append("Development/evaluation case overlap")
    if any(case.get("evaluation_live_allowed") for case in evaluation.values()):
        problems.append("An evaluation case is prematurely live-enabled")
    company_names = [case["issuer_name"] for case in roster["cases"] if case["cohort"] in {"DEVELOPMENT", "EVALUATION_CANDIDATE"}]
    if len(company_names) != len(set(company_names)):
        problems.append("Issuer appears in multiple assigned cases")
    cases = []
    for ident, case in development.items():
        directory, selected = resolve_case(PROJECT, ident)
        corpus = Corpus(directory, ident)
        verified = corpus.verify()
        mismatches = [name for name, expected in case["input_hashes"].items() if digest(directory / name) != expected]
        if mismatches:
            problems.append(f"{ident}: public input differs from roster: {mismatches}")
        gold = None
        if case.get("gold_path"):
            path = PROJECT / case["gold_path"]
            record = read_json(path)
            gold = {"path": case["gold_path"], "sha256": digest(path), "matches_roster": digest(path) == case["gold_sha256"],
                    "locked_before_model_answer": record.get("locked_before_model_answer"),
                    "private_do_not_include_in_model_input": record.get("private_do_not_include_in_model_input"),
                    "grading_status": record.get("grading_status"), "human_review_status": record.get("human_review_status"),
                    "outside_public_directory": not path.resolve().is_relative_to(directory.resolve())}
            if not all(gold[key] for key in ("matches_roster", "locked_before_model_answer", "private_do_not_include_in_model_input", "outside_public_directory")):
                problems.append(f"{ident}: gold lock/hash/isolation check failed")
        cases.append({"case_id": ident, "public_directory": selected["public_directory"],
                      "public_inputs_match_roster": not mismatches, "verified_documents": verified,
                      "source_pages": len(corpus.chunks), "manual_sha256": digest(directory / "manual.md"),
                      "gold": gold or {"preservation_reference": case.get("gold_preservation_reference")}})
    preflights = read_json(HERE / "D3_preflights_v031.json")
    observed_pairs = {(row["summary"]["case_id"], row["summary"]["condition"]) for row in preflights}
    expected_pairs = {(ident, condition) for ident in development for condition in ("B", "A0")}
    if observed_pairs != expected_pairs or len(preflights) != len(expected_pairs):
        problems.append("Preflight list does not cover each development case and condition exactly once")
    if any(row["summary"]["execution_status"] != "PREFLIGHT_COMPLETE" or row["summary"]["model_calls"] != 0 for row in preflights):
        problems.append("A preflight is incomplete or includes model calls")
    live_at_check = []
    for path in (PROJECT / "runs").glob("*/summary.json"):
        summary = read_json(path)
        if summary.get("case_id") in evaluation and summary.get("mode") == "LIVE":
            problems.append("Evaluation live run found: " + summary["run_id"])
        if summary.get("mode") == "LIVE" and summary.get("config_version", "").startswith("0.3"):
            live_at_check.append(summary["run_id"])
    return {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "stage": "D5 pre-run independent review 2",
            "passed": not problems, "problems": problems, "shared_config_differences": differences,
            "config_hashes": {condition: digest(PROJECT / "config" / f"{condition}.json") for condition in configs},
            "roster_sha256": digest(HERE / "case_roster.json"), "registered_development_cases": sorted(registered),
            "evaluation_candidate_cases": sorted(evaluation), "evaluation_live_allowed": False,
            "corpora_and_gold": cases, "preflight_count": len(preflights),
            "completed_v03_live_runs_at_check": live_at_check,
            "limits": ["Read-only hash, registration, corpus and configuration audit; no model requests.",
                       "Rubrics are AI-prepared and not independently human-adjudicated.",
                       "Evaluation candidates require W12 source/gold/protocol freeze before model execution.",
                       "HDMS retains its historical manual; both policies use the same manual within each case."]}


if __name__ == "__main__":
    report = audit()
    path = HERE / "D5_pre_run_review_2.json"
    if path.exists():
        raise SystemExit("Refusing to overwrite pre-run audit; use a separately named subsequent review.")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "problems": report["problems"],
                      "cases": len(report["corpora_and_gold"]), "preflights": report["preflight_count"],
                      "live_at_check": report["completed_v03_live_runs_at_check"]}, ensure_ascii=True))
    raise SystemExit(0 if report["passed"] else 1)
