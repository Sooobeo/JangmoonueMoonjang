"""Record version-specific follow-up without rewriting v040 review evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(name):
    path = HERE / name
    return {"file": path.relative_to(ROOT).as_posix(), "exists": path.is_file(),
            "sha256": sha(path) if path.is_file() else None}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


target = HERE / "implementation_review_2_v041.json"
if target.exists():
    raise SystemExit("Version-specific review already exists; use an explicit new supplement for later changes.")
plan = load(HERE / "DIAG_v040_plan.json")
changed = [name for name, old in plan["source_hashes"].items() if sha(ROOT / name) != old]
expected = {"ipo_eval/runner_v2.py", "ipo_eval/tool_gateway.py", "config/A0.json", "config/B.json", "prompts/v2_contract.md", "pyproject.toml"}
assert set(changed) == expected
a, b = load(ROOT / "config/A0.json"), load(ROOT / "config/B.json")
assert a["version"] == b["version"] == "0.4.1-dev"
assert {k: v for k, v in a.items() if k != "condition"} == {k: v for k, v in b.items() if k != "condition"}
documents = {}
for name in ("implementation_review_1.md", "diagnosis_1.md"):
    text = (HERE / name).read_text(encoding="utf-8")
    documents[name] = {"hangul_characters": sum("가" <= char <= "힣" for char in text),
                       "replacement_characters": text.count("\ufffd"), "sha256": sha(HERE / name)}
    assert documents[name]["hangul_characters"] > 100 and not documents[name]["replacement_characters"]
now = datetime.now(timezone.utc).isoformat()
report = {
    "review": "implementation review 2, v0.4.1 follow-up", "reviewer": "preservation_review",
    "checked_at_utc": now, "status": "PASS_OFFLINE_AFTER_REPAIR", "version": "0.4.1-dev",
    "scope": "Independent delta review of root changes; tests and new reports edited only, no production source or API calls.",
    "prior_review": artifact("implementation_review_2.json"),
    "changed_production_files_from_v040": changed,
    "source_hashes": {name: sha(ROOT / name) for name in plan["source_hashes"]},
    "tests": [
        {"command": "python -X utf8 -m pytest tests/test_remediation_independent_review.py tests/test_remediation_integration.py tests/test_format_patch.py tests/test_wire_contract.py tests/test_runtime_transient_retry.py -q", "result": "99 passed in 10.26s", "xfail": 0},
        {"command": "python -X utf8 -m pytest tests/test_remediation_independent_review.py tests/test_remediation_integration.py::test_dynamic_missing_field_enum_does_not_restrict_unrelated_review_strings -q", "result": "7 passed in 3.74s", "note": "Includes the subsequently added synthetic prompt registration test; not a separate seven-test suite to add to the earlier count."},
    ],
    "test_file_sha256": sha(ROOT / "tests/test_remediation_independent_review.py"),
    "findings": [
        {"id": "IR2-02", "status": "RESOLVED_V041", "resolution": "B REGISTER and COMMIT fatal errors now call _required immediately. Two formerly strict-xfail tests now pass: model calls exactly 1/2, zero format repairs, FAILED/null final status and no accepted review."},
        {"id": "V041-SCHEMA-ALIAS", "status": "RESOLVED_INDEPENDENTLY_VERIFIED", "resolution": "Dynamic missing_inputs.field enum replaces its leaf dictionary. It no longer mutates the aliased shared string schema used for prose/doc/claim/source fields. Exact unresolved-field validation stays active.", "evidence": artifact("alias_regression_review_2.json")},
        {"id": "MANIFEST-READABILITY-01", "status": "RESOLVED_V041", "resolution": "Root implementation review rewritten as readable UTF-8 Korean; replacement count zero."},
        {"id": "MANIFEST-DIAG1-SIGNOFF", "status": "RESOLVED_V041", "resolution": "Root diagnosis_1.md explicitly records diagnosis scope and uncertainty."},
    ],
    "checks": {"B_A0_condition_only_config_difference": True,
        "input_cap": 800000, "per_run_dollar_cap": 1.25,
        "same_model_and_reasoning": a["model"] == "gpt-6.1-terra" and a["reasoning_effort"] == "medium",
        "prompt_explains_existing_contract_not_fact_or_action_selection": True,
        "same_context_labels_only_when_source_bases_are_actually_same": True,
        "derived_output_not_duplicated_as_null_value": True,
        "synthetic_example_registers_market_cap_100_million": True,
        "no_programmatic_A0_registration_or_calculation_added": True,
        "known_and_unknown_usage_accounting_unchanged": True},
    "documents": documents,
    "limits": ["Offline contract and orchestration checks do not establish real model completion or answer correctness.",
        "v0.4.1 changes both contract explanation and input/cost caps; results cannot be presented as same-condition v032 improvement or one-factor causal evidence.",
        "DIAG_v041 remains diagnostic; final twelve-run frozen batch, three execution reviews and three overall reviews are pending.",
        "Final preservation verification is deferred until the final delivery checkpoint; prior source snapshots/reports are not rewritten here."],
}
write(target, report)
(HERE / "implementation_review_2_v041.md").write_text("""# v0.4.1 구현 2차 후속 검토

판정: **PASS_OFFLINE_AFTER_REPAIR**. root의 v0.4.1 변경을 읽고 tests/report만 수정했다. 실제 API는 호출하지 않았으며 실제 업무 완료 판정은 대기다.

B는 REGISTER와 COMMIT에서 fatal 격리 위반을 받으면 즉시 실패한다. 이전 IR2-02 재현 두 개의 xfail을 제거했고 모델 호출이 각각 1/2회, format repair 0회, review artifact 없음으로 통과했다. 외부 자료 접근·제출 방어뿐 아니라 불필요한 repair 호출도 중단한다.

동적 missing_inputs.field의 enum은 새 leaf 객체에 넣는다. deepcopy가 보존하는 shared string 객체의 alias를 직접 변경하지 않으므로 본문·doc ID·claim ID 등으로 enum이 퍼지지 않는다. 실제 UNRESOLVED 집합의 schema 제한과 서버 검증은 계속 유지된다. contracts의 14개 문자열 경로 및 새 schema 불변 회귀를 교차 확인했다.

공통 prompt는 기존 등록기의 같은 scope/basis/source_snapshot_id와 필요한 as_of 계약을 설명한다. 실제 원문 기준이 같은 경우만 같은 표기를 쓰며 다른 기준을 통과 목적으로 맞추지 말라고 명시한다. DERIVATION 출력은 별도 null VALUE로 중복 작성하지 않는다. synthetic 예시를 실제 변환·등록기에 넣어 입력 P/S만 등록되고 M=100백만원의 파생 fact와 DERIVABLE 선택이 생성됨을 추가 검증했다. 이 예시는 실기업 정답이나 A0 행동 순서를 제공하지 않는다.

B/A0는 condition 외 설정 차이가 없고 새 공통 입력 한도 800,000·회당 $1.25를 사용한다. 모델/reasoning은 같다. prompt와 상한을 함께 바꾸므로 이전 조건과 같은 실험 또는 단일 수정의 인과 효과로 표현해서는 안 된다.

관련 99개 테스트가 10.26초에 통과했고 xfail은 없다. 이후 synthetic 예시 테스트를 추가한 독립 경계+alias 7개 검증은 3.74초에 통과했다. 두 집합은 중복되므로 106개로 합산하지 않는다. source delta는 runner, gateway, 두 config, v2 prompt, pyproject의 6개 파일이며 runtime/budget/compact/patch 구현을 추가 수정하지 않았다.

root 구현 1차 보고서와 진단 1차 보고서의 한글을 실제 파일에서 확인했다(각 549/402자, U+FFFD 0). 이전 문자 손상·진단 서명 누락은 해소했다. 원래 v0.4.0 2차 보고서는 시점 증거로 그대로 유지한다. 새 해시·테스트·세부 결과는 [implementation_review_2_v041.json](implementation_review_2_v041.json)에 있다.

최종 12회 실행·채점·실행 검토 3회·종합 검토 3회와 최종 보존 확인은 아직 미완료다. DIAG_v041의 통과를 최종 acceptance로 대신하지 않는다.
""", encoding="utf-8")

manifest_path = HERE / "review_manifest.json"
manifest = load(manifest_path)
original_path = HERE / "review_manifest_initial.json"
if not original_path.exists():
    original_path.write_bytes(manifest_path.read_bytes())
manifest["updated_at_utc"] = now
manifest["status"] = "IN_PROGRESS_V041_OFFLINE_REVIEWS"
manifest["initial_manifest_snapshot"] = artifact("review_manifest_initial.json")
diagnosis = manifest["stages"]["diagnosis"]
diagnosis["status"] = "THREE_REVIEWS_RECORDED"
diagnosis["reviews"][0].update(status="COMPLETED_ROOT_DIAGNOSIS_REVIEW", review_complete=True,
    artifacts=[artifact("diagnosis_1.md"), *diagnosis["reviews"][0]["artifacts"]])
for record in diagnosis["reviews"][1:]:
    record["review_complete"] = True
implementation = manifest["stages"]["implementation"]
implementation["status"] = "V041_REVIEW_3_FOLLOWUP_PENDING"
first = implementation["reviews"][0]
first.update(status="V041_ROOT_REVIEW_RECORDED", readable=True,
    readability_evidence=documents["implementation_review_1.md"], artifacts=[artifact("implementation_review_1.md")],
    required_followup="Root final freeze/test approval and live acceptance remain separate.")
second = implementation["reviews"][1]
second.update(status="V041_PASS_OFFLINE_AFTER_REPAIR", open_findings=[], review_complete=True,
    followup_artifacts=[artifact("implementation_review_2_v041.json"), artifact("implementation_review_2_v041.md"), artifact("alias_regression_review_2.json")],
    required_followup="Final execution acceptance and final preservation check; v041 implementation defects identified in review 2 are resolved.")
manifest["resolved_findings"] = [{**finding, "status": "RESOLVED_V041", "resolution_evidence": artifact("implementation_review_2_v041.json")}
    for finding in manifest["open_required_findings"]]
manifest["open_required_findings"] = []
manifest["final_batch"]["status"] = "NOT_STARTED_PENDING_V041_THIRD_REVIEW_DIAGNOSTIC_AND_FREEZE"
manifest.setdefault("update_history", []).append({"at_utc": now, "reviewer": "preservation_review",
    "change": "Recorded root diagnosis/readability repairs and v041 implementation review2; resolved required findings; final execution/overall/final preservation remain pending."})
assert not manifest["acceptance_complete"]
assert len([record for stage in manifest["stages"].values() for record in stage["reviews"]]) == 12
write(manifest_path, manifest)
print(json.dumps({"review": report["status"], "manifest": manifest["status"], "resolved_findings": 4}, ensure_ascii=False))
