"""Read-only source/run audits; write only new remediation review reports."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import tiktoken

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from preserve_baseline import verify


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


encoder = tiktoken.get_encoding("o200k_base")
def tokens(value, pretty=False):
    return len(encoder.encode(json.dumps(value, ensure_ascii=False, indent=2 if pretty else None,
        separators=None if pretty else (",", ":"))))


rows = []
for saved in load(ROOT / "reports/a0_implementation/D5_v032_runs.json")["runs"]:
    if saved["condition"] != "A0":
        continue
    directory = Path(saved["directory"])
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    request_rows = []
    for path in sorted(directory.glob("*_explore_request.json")):
        request = load(path)
        compact_messages = deepcopy(request)
        for item in compact_messages["input"]:
            field = "content" if item.get("role") == "user" else "output" if item.get("type") == "function_call_output" else None
            if field and isinstance(item.get(field), str):
                try:
                    value = json.loads(item[field])
                except ValueError:
                    continue
                item[field] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        response_path = path.with_name(path.name.replace("_request", "_response"))
        request_rows.append({"request_file": path.relative_to(ROOT).as_posix(), "sha256": digest(path),
            "saved_pretty_json_tokens": tokens(request, True), "compact_outer_json_tokens": tokens(request),
            "compact_user_and_tool_json_tokens": tokens(compact_messages),
            "tool_schema_tokens_compact": tokens(request.get("tools", [])),
            "history_tokens_compact": tokens(request["input"]),
            "actual_input_tokens": load(response_path)["usage"]["input_tokens"] if response_path.exists() else None})
    output_rows = []
    for path in sorted(directory.glob("*_response.json")):
        if not any(stage in path.name for stage in ("finalize", "format_repair")):
            continue
        raw = load(path)
        output_rows.append({"file": path.relative_to(ROOT).as_posix(), "sha256": digest(path),
            "status": raw.get("status"), "output_tokens": raw.get("usage", {}).get("output_tokens"),
            "incomplete_details": raw.get("incomplete_details")})
    snapshot = load(directory / "snapshots.json")
    counts = Counter(event["tool"] for event in events if event["event"] == "tool_call" and event.get("actor") == "model")
    errors = [{key: event.get(key) for key in ("tool", "error_code", "message")} for event in events
        if event["event"] == "tool_envelope" and not event.get("ok")]
    rows.append({"case_id": saved["case_id"], "run_id": directory.name,
        "execution_status": saved["summary"]["execution_status"],
        "snapshot_id": snapshot["current_id"], "record_count": len(snapshot["snapshots"][snapshot["current_id"]]["records"]),
        "calculation_count": len(load(directory / "calculations.json")), "model_tool_counts": dict(counts),
        "explore_requests": request_rows, "final_and_repair_responses": output_rows, "tool_errors": errors})

diagnosis = {"review": "failure diagnosis review 2", "reviewer": "preservation_review",
    "checked_at_utc": datetime.now(timezone.utc).isoformat(), "status": "PASS_DIAGNOSIS_ONLY",
    "scope": "Original v032 artifact hashes and source inspected; no live API or original modification.",
    "token_measurement_note": "o200k_base local serialization estimates, not exact API usage attribution. Schema/history token counts are separate non-additive views. Inner JSON minification is a semantic-preserving counterfactual, not a claim that old requests were sent compactly.",
    "findings": ["All six A0 snapshots are X_EMPTY with zero records/calculations; only search/read were chosen during exploration.",
        "Repeated full tool schemas and accumulated full observations contribute to input growth. Minification reduces representation overhead but cannot guarantee different model actions.",
        "Four final submissions used business missing_inputs absent from the empty snapshot's declared UNRESOLVED set; this is a contract mismatch, not source absence.",
        "Three new-case final reviews exceeded the entire-JSON repair output allowance; HDMS repair instead failed HTTP500 and remains unknown usage.",
        "Patch repair can reduce response size only for already permitted format changes. Removing populated missing_inputs, inventing records or changing decisions stays forbidden."],
    "runs": rows}
write("diagnosis_2.json", diagnosis)
lines = ["# v032 실패 독립 진단 2", "", "판정: 원인 관측 검토 통과. 실제 개선 효과는 아직 미검증이다.", "",
    "보존한 여섯 A0의 원시 request·response·event·snapshot을 다시 읽었다. 전부 X_EMPTY, 등록 0개, 계산 0개이며 탐색 중 모델이 선택한 도구는 검색과 열람이었다. 실제 입력 usage와 직렬화 토큰 추정은 구분한다.", "",
    "| 기업 | 탐색 호출 | 실제 탐색 입력 합계 | 마지막 요청 pretty/compact 추정 | 같은 요청의 user·tool JSON까지 minify 추정 |",
    "|---|---:|---:|---:|---:|"]
for row in rows:
    last = row["explore_requests"][-1]
    lines.append(f"| {row['case_id']} | {len(row['explore_requests'])} | {sum(r['actual_input_tokens'] or 0 for r in row['explore_requests']):,} | {last['saved_pretty_json_tokens']:,} / {last['compact_outer_json_tokens']:,} | {last['compact_user_and_tool_json_tokens']:,} |")
lines += ["", "도구 schema와 누적 이력의 재전송이 입력을 사용하고, 들여쓰기 제거는 표현 비용을 줄인다. 추정값은 API 청구량의 분해나 인과 실험이 아니다. 남은 예산·등록 상태를 보여주더라도 모델이 등록과 계산을 선택할지는 실제 실행으로 확인해야 한다.", "",
    "HDMS와 신규 세 기업 COMMIT의 missing_inputs는 등록된 UNRESOLVED 집합과 달라 거절됐다. 빈 snapshot의 올바른 집합은 빈 배열이며 업무상 미완료가 없다는 의미는 아니다. 새 동적 schema는 이 집합만 노출하고 기존 정확 집합·요청 연결 검증을 유지해야 한다.", "",
    "SHINSUNGST·ALT·MILLIE의 최초 최종화 출력은 4,440/4,306/4,414토큰인데 전체 JSON repair는 2,500에서 미완료였다. HDMS는 HTTP500이므로 같은 실패로 합치지 않는다. 작은 patch는 허용된 형식 수정만 압축하며 기존 missing_inputs 항목 삭제, 수치·판단·상태·출처 변경과 미등록 사실 생성은 허용하지 않는다.", "",
    "B의 5,000토큰 extraction 미완료와 두 기업의 긴 공백 반복은 contracts의 별도 원문 진단과 일치한다. 내부 structured decoding 원인을 로그만으로 확정하지 않는다. 새 한도/계약/상태/repair를 동시에 바꾸므로 v032와 동조건 성능이나 단일 수정의 인과 효과로 보고해서는 안 된다.", "",
    "원문 경로, 해시와 각 요청의 추정·실제 값은 [diagnosis_2.json](diagnosis_2.json)에 보존했다. API 호출과 기존 보고서 수정은 없었다."]
(HERE / "diagnosis_2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

preservation = verify()
write("implementation_review_2_preservation.json", preservation)
paths = ["ipo_eval/wire_contract.py", "ipo_eval/format_patch.py", "ipo_eval/runtime_v2.py", "ipo_eval/budget.py",
    "ipo_eval/agent_loop.py", "ipo_eval/runner_v2.py", "ipo_eval/tool_gateway.py", "ipo_eval/validation_v2.py",
    "config/B.json", "config/A0.json", "prompts/A0.md", "prompts/common.md", "prompts/v2_contract.md",
    "tests/test_remediation_independent_review.py", "tests/test_remediation_integration.py",
    "tests/test_wire_contract.py", "tests/test_format_patch.py", "tests/test_runtime_transient_retry.py"]
config_b, config_a = load(ROOT / "config/B.json"), load(ROOT / "config/A0.json")
differences = [key for key in set(config_b) | set(config_a) if key != "condition" and config_b.get(key) != config_a.get(key)]
implementation = {"review": "implementation review 2", "reviewer": "preservation_review",
    "checked_at_utc": datetime.now(timezone.utc).isoformat(), "status": "PASS_WITH_PENDING_B_FATAL_SHORT_CIRCUIT",
    "ownership_disclosure": "Independent review of contracts wire/compact patch changes and root integration. Original patch implementation and runtime retry were authored by this reviewer, so those checks are implementer self-review rather than fully independent authorship.",
    "source_hashes": {path: digest(ROOT / path) for path in paths}, "config_differences_excluding_condition": differences,
    "tests": [{"scope": "compact wire, patch, root integration, runtime retry, independent boundary", "result": "96 passed in 8.48s"},
              {"scope": "independent boundary plus known B termination defect", "result": "3 passed, 2 xfailed in 4.78s"}],
    "checks": {"seven_kinds_lossless_aliases": True, "actual_read_coordinates_only": True,
        "same_snapshot_calculation_roundtrip": True, "raw_wire_and_context_retained": True,
        "schema_authorized_atomic_patch": True, "numeric_text_status_source_list_preserved": True,
        "neutral_state_no_automatic_A0_workflow": True, "observation_envelope_state_growth_reserved": True,
        "dynamic_missing_schema_with_original_semantic_validation": True, "unknown_usage_separate_reserved_not_zero": True,
        "single_same_request_server_retry_budget_recheck": True, "B_A0_common_config_equal": not differences,
        "prior_artifacts_and_source_snapshots_preserved": preservation["passed"]},
    "findings": [{"id": "IR2-01", "status": "RESOLVED_BEFORE_DIAG_FREEZE", "description": "Compact foreign chunk originally returned only UNREAD_EVIDENCE; root now rejects it as fatal ISOLATION_VIOLATION. Same corpus unread evidence remains recoverable. Three independent tests verify counted attempt, atomicity and fatal persistence."},
                 {"id": "IR2-02", "status": "PENDING_V041", "description": "B fixed runner invokes one format repair after fatal REGISTER/COMMIT isolation error. No data is read and no review is accepted after the fatal error, but one avoidable model call is attempted. This also existed in old B flow. Root deferred correction until DIAG_v040 ends so frozen production source is unchanged. Two strict-xfail reproductions record the defect."}],
    "preservation": preservation,
    "limitations": ["Mock-provider tests demonstrate orchestration and constraints, not autonomous model business completion.", "No API was called by this reviewer.", "Implementation review is not final acceptance until IR2-02 and actual paired-run criteria are satisfied."]}
write("implementation_review_2.json", implementation)
(HERE / "implementation_review_2.md").write_text("""# 실패 보완 구현 검토 2

판정: 핵심 계약·통합은 통과했으며 **B 격리 위반 직후 repair 호출 중단 1건은 v0.4.1 수정 대기**다. 실제 실행 성공 판정이 아니다.

compact 변환은 7종 payload 전 필드를 일대일로 보존한다. doc/page는 실제 열람 chunk 좌표에서만 복원하고, 값·기간·단위·선택·포함 상태를 추론하지 않는다. round-trip snapshot과 계산 결과 동일성, 미열람 근거 거절, 중복 ID·잘못된 파생값 거절을 확인했다.

patch는 schema상 여분 키 삭제, 누락 빈필드 추가, page/version의 동일 정수화, 이미 선언된 claim에 대한 증거 연결만 허용한다. compact claim 선언과 ev 경로도 schema와 실제 경로로 제한한다. 배열 구성·수치·본문·판단·요청 상태·출처 변경은 실패하며 원본/patch/적용 결과와 raw API 기록을 보존한다. 초기 patch와 runtime은 검토자 본인 구현이므로 이 부분은 자기 검토이고, contracts가 보완한 compact 경로와 root 통합은 독립 검토다.

root 통합에서 B/A0 공통 설정은 condition 외 차이가 없다. 상태는 현재 snapshot·ID·ledger·예산 관측이며 A0의 다음 행동을 자동 선택하지 않는다. 관측 전 예약에 envelope·현재 상태·상태 증가 여유를 포함하며, 최종 호출 직전 전체 요청을 재계산한다. missing_inputs는 등록된 UNRESOLVED 정확 집합을 명시하고 원래 서버 검증을 유지한다. 빈 배열이 업무 완료를 뜻하지 않는다.

HTTP500/502/503/504만 같은 요청을 최대 1회 재시도한다. 매 시도는 model_calls·request·오류 로그에 남고 unknown usage는 별도 입력 추정/최대 출력/비용 예약으로 누적된다. 재시도 전 여섯 예산을 다시 검사하며 400·quota·refusal·incomplete를 재시도하지 않는다. 로그는 읽기 좋은 JSON, 모델용 새 payload와 토큰 추정은 compact JSON을 쓴다. 알려진 비용과 unknown 예약 및 실제 청구액은 구별한다.

독립 검토에서 compact의 외부 chunk 오류가 fatal로 분류되지 않음을 발견했다. root가 DIAG 동결 전에 수정했고, 같은 corpus 미열람 구별·상태 원자성·fatal 지속을 추가 검증했다. 관련 96개 테스트가 8.48초에 통과했다.

남은 IR2-02: B run_fixed는 fatal REGISTER/COMMIT 오류에도 format repair API를 1회 더 시도한다. 정보 접근과 제출은 계속 막히며 불필요 호출의 문제다. v032에도 있었던 경로이고 live 동결 중이므로 수정하지 않았다. root가 DIAG 4회 뒤 v0.4.1 수정으로 결정했다. 독립 테스트는 3 pass, 2 strict xfail로 현재 결함을 명시한다. 수정 뒤 xfail을 제거하고 재검증해야 한다.

기존 증거 1,847개와 소스/설계 복사 67개, 총 1,914개 보존 검사에 위반은 없다. 세부 해시·범위·테스트·보완 상태는 [implementation_review_2.json](implementation_review_2.json), 보존 결과는 [implementation_review_2_preservation.json](implementation_review_2_preservation.json)에 있다. 이 검토에서 API를 호출하거나 이전 보고서를 수정하지 않았다.
""", encoding="utf-8")
print(json.dumps({"diagnosis_runs": len(rows), "preservation_passed": preservation["passed"],
    "config_differences": differences, "implementation_status": implementation["status"]}, ensure_ascii=False))
