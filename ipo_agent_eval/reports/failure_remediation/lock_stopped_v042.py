"""Preserve the stopped v042 batch and report its actual partial outcomes."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LABEL = "FIX_v042"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    path = HERE / name
    if path.exists():
        raise SystemExit("Never overwrite stopped-batch evidence: " + name)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


plan_path, results_path = HERE / (LABEL + "_plan.json"), HERE / (LABEL + "_runs.json")
plan, results = read(plan_path), read(results_path)
assert not results["complete"] and results["stopped_between_runs"]
assert len(results["runs"]) == len(plan["planned_runs"]) == 12
paths = {plan_path, results_path}
frozen = ROOT / plan["source_snapshot"]
for name, digest in plan["source_hashes"].items():
    path = frozen / name
    assert sha(path) == digest
    paths.add(path)
spec = importlib.util.spec_from_file_location("delivery_stopped_audit", HERE / "check_delivery.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
audit, unstarted = [], []
for row in results["runs"]:
    identity = {key: row[key] for key in ("case_id", "condition", "repeat")}
    if not row.get("directory"):
        assert row["summary"]["execution_status"].startswith("NOT_STARTED_")
        unstarted.append({**identity, "execution_status": row["summary"]["execution_status"],
                          "outcome_score": None, "reason": "Never started; not a failed model answer."})
        continue
    directory = Path(row["directory"]).resolve()
    assert directory.is_relative_to((ROOT / "runs").resolve())
    assert read(directory / "summary.json") == row["summary"]
    assert row["summary"]["execution_status"] in {"SUBMITTED", "FAILED"}
    paths.update(path for path in directory.rglob("*") if path.is_file())
    errors = []
    def require(ok, message):
        if not ok:
            errors.append(message)
    calculations = read(directory / "calculations.json")
    state = read(directory / "snapshots.json")
    if row["summary"]["execution_status"] != "SUBMITTED":
        errors.append("FAILED:" + str(row["summary"].get("failure_reason")))
    try:
        detail = checker.run_checks(row, plan, directory, require)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append("Accepted review artifact audit unavailable: " + type(exc).__name__)
        current_ok = [calc for calc in calculations if calc["status"] == "OK" and calc["input_snapshot_id"] == state["current_id"]]
        detail = {"registered_records": len(state["snapshots"][state["current_id"]]["records"]),
                  "evaluation_ok": sum(not calc["id"].startswith("sensitivity_") for calc in current_ok),
                  "sensitivity_ok": sum(calc["id"].startswith("sensitivity_") for calc in current_ok),
                  "note": "Partial saved state only; no accepted review artifact."}
    invalid = [{key: calc.get(key) for key in ("id", "status", "reason")} for calc in calculations
               if calc["input_snapshot_id"] == state["current_id"]
               and calc["status"] != "OK"]
    audit.append({**identity, "run_id": directory.name, "summary": row["summary"],
                  "execution_contract_details": detail, "acceptance_failures": errors,
                  "current_non_ok_calculations": invalid})
assert len(audit) == 4 and len(unstarted) == 8
entries = [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}
           for path in sorted(paths)]
now = datetime.now(timezone.utc).isoformat()
manifest = {"captured_at_utc": now, "label": LABEL, "registry_complete": False,
    "policy": "Immutable stopped batch: plan, all explicit dispositions, four started raw runs and frozen production source. Do not rewrite or pool into a later final batch.",
    "entry_count": len(entries), "entries": entries}
write("FIX_v042_interrupted_preservation.json", manifest)
report = {"checked_at_utc": now, "reviewer": "preservation_review", "label": LABEL,
    "status": "AUDITED_STOPPED_BATCH_NOT_FINAL_ACCEPTANCE", "planned": 12, "actual_started": 4, "not_started": 8,
    "dispositions": dict(Counter(row["summary"]["execution_status"] for row in results["runs"])),
    "all_planned_dispositions_recorded": True, "final_batch_complete": False,
    "known_cost_standard_uncached_usd": round(sum(row["summary"]["known_usage_cost_usd_standard_uncached"] for row in audit), 6),
    "usage_unknown_runs": sum(row["summary"]["usage_unknown"] for row in audit),
    "preservation_manifest": {"file": "reports/failure_remediation/FIX_v042_interrupted_preservation.json",
        "sha256": sha(HERE / "FIX_v042_interrupted_preservation.json"), "entry_count": len(entries)},
    "runs": audit, "unstarted": unstarted,
    "limits": ["SUBMITTED is distinct from completing numeric evaluation and sensitivity.",
        "Original source values, model choices, invalid calculations and raw responses remain unchanged.",
        "Future grouping-contract results require their own frozen paired batch.",
        "No API calls and no production-source changes by this reviewer."]}
write("FIX_v042_interrupted_review_2.json", report)
lines = ["# FIX_v042 중단 배치 2차 감사", "", "판정: 중단 기록 감사 완료. 최종 acceptance가 아니다.", "",
    f"계획 12회 중 실제 시작 {len(audit)}회, 미실행 {len(unstarted)}회다. 결과표는 complete=false와 각 미실행 처분을 유지한다. 실제 상태는 {report['dispositions']}다.", "",
    "| 기업/조건 | 등록 records | 현재 EVALUATE OK | 현재 sensitivity OK | 감사 |", "|---|---:|---:|---:|---|"]
for row in audit:
    detail = row["execution_contract_details"]
    lines.append(f"| {row['case_id']}/{row['condition']} | {detail['registered_records']} | {detail['evaluation_ok']} | {detail['sensitivity_ok']} | {'수치 완료 조건 미충족' if row['acceptance_failures'] else '개별 실행 검사 통과'} |")
lines += ["", "HDMS B는 canonical 분모 선택과 값이 있었지만 IE/IP/IS의 scope·basis 자유문자열이 서로 달라 주당가액과 sensitivity가 INVALID였다. 모델이 제출한 다른 비교 기준을 코드가 임의로 통일하지 않고 원래 오류 결과를 보존했다. 후속 group 참조 계약이 이 기록을 소급해 성공으로 바꾸지 않는다.", "",
    f"알려진 표준 비캐시 요율 추정 합계는 ${report['known_cost_standard_uncached_usd']:.6f}, usage_unknown 실행은 {report['usage_unknown_runs']}개다. 청구액이나 보수 예약 ceiling과 같다고 주장하지 않는다. 미실행 8회는 성능 점수 null이며 실패 답변으로 세지 않는다.", "",
    f"plan/results·동결 source·네 raw run의 {len(entries)}개 파일을 별도 immutable manifest로 잠갔다. 기존 497개 진단/중단/probe 잠금은 바꾸지 않았다. 세부 오류·원시 비용·미실행 목록은 FIX_v042_interrupted_review_2.json에 있다."]
(HERE / "FIX_v042_interrupted_review_2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "locked_files": len(entries), "dispositions": report["dispositions"],
                  "acceptance_failure_runs": sum(bool(row["acceptance_failures"]) for row in audit)}, ensure_ascii=False))
