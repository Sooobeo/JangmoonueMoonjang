"""Create the remediation review plan without claiming unperformed reviews."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def artifact(relative):
    path = ROOT / relative
    return {"file": relative, "exists": path.is_file(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


def local(name):
    return artifact("reports/failure_remediation/" + name)


def review(stage, number, reviewer, status, files=(), **extra):
    return {"review_id": f"{stage}_{number}", "ordinal": number, "reviewer": reviewer,
            "status": status, "final_acceptance": False, "artifacts": [local(name) for name in files], **extra}


manifest = {
    "schema_version": "failure_remediation_review_manifest_v1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "status": "IN_PROGRESS",
    "requirements": {"diagnosis_reviews": 3, "implementation_reviews": 3,
                     "final_batch_execution_reviews": 3, "overall_reviews": 3, "total_required": 12},
    "acceptance_complete": False,
    "policy": [
        "A report's existence does not mean final acceptance; pending reviews and open findings stay explicit.",
        "Reviews of v0.4.0 diagnostic source require a version-specific follow-up after v0.4.1 changes before the final paired batch.",
        "DIAG_v040 is four diagnostic attempts, not the final six-company paired batch and not final execution acceptance.",
        "The completed D0-D6 and three overall reviews in the prior immutable manifest remain separate and are never rewritten or counted as remediation reviews.",
        "Reviewers disclose authored components; cross-review is not represented as fully independent authorship where it is not.",
        "Final completion requires all twelve review slots, resolved required findings, final frozen source/results, and a fresh preservation check.",
    ],
    "prior_completed_manifest": {**artifact("reports/a0_implementation/review_manifest.json"),
                                 "policy": "IMMUTABLE; 21 stage and 3 overall reviews from the completed original task"},
    "baseline_manifest": local("baseline_manifest.json"),
    "diagnostic_plan": {**local("DIAG_v040_plan.json"), "role": "diagnostic_only", "final_batch_denominator": False},
    "final_batch": {"plan_file": None, "results_file": None, "source_snapshot": None,
                    "expected_companies": 6, "conditions": ["B", "A0"], "expected_attempts": 12,
                    "status": "NOT_STARTED_PENDING_V041_FIX_AND_FREEZE"},
    "stages": {
        "diagnosis": {
            "status": "AWAITING_ROOT_REVIEW_1_RECORD",
            "reviews": [
                review("diagnosis", 1, "root; compact contract diagnosis evidence by contracts",
                    "EVIDENCE_PRESENT_AWAITING_ROOT_SIGNOFF",
                    ["compact_wire_diagnosis.json", "compact_wire_review_1.json", "compact_wire_review_1.md"],
                    planned_primary_report="reports/failure_remediation/diagnosis_1.md",
                    scope="Observed v032 failures, compact transport causes and proposed correction boundary"),
                review("diagnosis", 2, "preservation_review", "COMPLETED_PASS_DIAGNOSIS_ONLY",
                    ["diagnosis_2.json", "diagnosis_2.md"],
                    scope="Original A0 input/schema/history estimates, empty snapshots, missing_inputs and repair-size mismatch"),
                review("diagnosis", 3, "case_roster", "COMPLETED_DIAGNOSIS_AND_BOUNDARY_REVIEW",
                    ["diagnosis_3.md"],
                    scope="Original failure path, test limitations, A0/A1 boundary and live acceptance requirements"),
            ],
        },
        "implementation": {
            "status": "V040_REVIEWED_WITH_OPEN_FINDING_V041_FOLLOWUPS_REQUIRED",
            "reviews": [
                review("implementation", 1, "root", "REPORT_ENCODING_REPAIR_REQUIRED",
                    ["implementation_review_1.md"], readable=False,
                    readability_evidence={"hangul_characters": 0, "question_marks": 486},
                    required_followup="Rewrite readable UTF-8 review and approve v0.4.1 frozen implementation after tests."),
                review("implementation", 2, "preservation_review", "V040_REVIEWED_WITH_OPEN_FINDING",
                    ["implementation_review_2.json", "implementation_review_2.md", "implementation_review_2_preservation.json"],
                    open_findings=["IR2-02"],
                    ownership_disclosure="Original patch/runtime implementer; independent compact extension and root integration reviewer.",
                    required_followup="Verify B fatal immediate termination after DIAG; remove two strict xfail markers and revalidate v0.4.1."),
                review("implementation", 3, "case_roster", "V040_PASS_AFTER_REPAIR_FOLLOWUP_REQUIRED",
                    ["implementation_review_3.md"],
                    ownership_disclosure="Independent integration reviewer; authored common prompts and approved driver fixes are disclosed.",
                    required_followup="Review v0.4.1 delta and final freeze against source/test records."),
            ],
            "supplemental_evidence_not_extra_required_slots": [local(name) for name in
                ("integration_review_2.json", "integration_review_2.md", "compact_patch_review_1.json")],
        },
        "execution": {
            "status": "NOT_STARTED_AWAITING_FINAL_PAIRED_BATCH",
            "required_scope": "Final twelve attempted or explicitly unstarted dispositions, frozen source, semantic work completion, grading, raw usage/cost/unknowns, actor/evidence/snapshot/ledger and preservation.",
            "reviews": [review("execution", number, reviewer, "NOT_STARTED", planned_primary_report=f"reports/failure_remediation/execution_review_{number}.json",
                prerequisite="Final frozen twelve-run batch and its artifacts must exist; DIAG is separate.")
                for number, reviewer in ((1, "root"), (2, "preservation_review"), (3, "case_roster or separately assigned cross-reviewer"))],
        },
        "overall": {
            "status": "NOT_STARTED_AWAITING_ALL_STAGE_REVIEWS_AND_DELIVERABLES",
            "required_scope": "Design coverage, source/tests, run and grade evidence, truthful completion limits, costs, documentation links, all review findings and final preservation.",
            "reviews": [review("overall", number, "To be assigned by root", "NOT_STARTED",
                planned_primary_report=f"reports/failure_remediation/final_review_{number}.json",
                prerequisite="All stage reviews and final reports must be complete; review cannot be inferred from a plan.")
                for number in (1, 2, 3)],
        },
    },
    "open_required_findings": [
        {"id": "IR2-02", "status": "PENDING_V041", "description": "B invokes unnecessary repair after fatal isolation; information and submission remain blocked.",
         "evidence": "tests/test_remediation_independent_review.py::test_b_fatal_isolation_stops_before_any_format_repair_api",
         "current_reproductions": "register and commit: two strict xfails; production source untouched during DIAG"},
        {"id": "MANIFEST-READABILITY-01", "status": "OPEN", "description": "implementation_review_1.md contains literal question marks instead of Korean; UTF-8 source rewrite requested."},
        {"id": "MANIFEST-DIAG1-SIGNOFF", "status": "OPEN", "description": "Compact diagnosis evidence exists; separate root diagnosis-1 scope/signoff record requested."},
    ],
    "final_preservation": {"status": "NOT_PERFORMED_FINAL_CHECK_REQUIRED", "artifact": None,
                           "prior_implementation_check": local("implementation_review_2_preservation.json")},
    "planned_updates": "Root updates this new manifest after actual follow-up reviews and final artifacts. Existing reports remain time-scoped evidence; v0.4.1 corrections should be new supplemental reports rather than silently changing v0.4.0 findings.",
}
assert sum(len(stage["reviews"]) for stage in manifest["stages"].values()) == 12
assert not manifest["acceptance_complete"]
path = HERE / "review_manifest.json"
if path.exists():
    raise SystemExit("Review manifest already exists; update its actual status deliberately instead of overwriting the plan.")
path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"file": str(path), "required_reviews": 12, "status": manifest["status"]}, ensure_ascii=False))
