# 실패 보완 통합 구현 검토 3

작성일: 2026-11-13. v040 사전 판정: **PASS_AFTER_REPAIR**. live에서 IR3-04 발견 후 **REOPENED_FOR_V041_SCHEMA_FIX**로 재개했다. v041 수정과 아래 후속 검증을 마친 현재 상태: **PASS_AFTER_V041_REPAIR — 코드·무과금 통합 검토 통과**. 이 판정 이력을 보존하며 실제 모델의 업무 수행 성공 또는 최종 12회 acceptance 통과로 해석하지 않는다.

검토자는 case_roster 에이전트다. 원래 할당은 읽기 전용 통합 검토였고, 발견한 driver 결함에 대해 root가 별도로 `scripts/run_development_comparison.py` 수정을 승인했다. 그 파일의 수정과 검증은 이 검토자가 수행했다. 앞선 공통 프롬프트 수정도 이 검토자가 작성했으므로 해당 부분을 완전히 독립적인 타인 검토라고 주장하지 않는다. root 및 다른 검토자의 교차 확인을 함께 사용한다. 이 검토에서 실제 API는 호출하지 않았다.

## 검토 범위와 결론

`agent_loop.py`, `runner_v2.py`, `tool_gateway.py`, `runtime_v2.py`, `budget.py`, `wire_contract.py`, `format_patch.py`, B/A0 config, 공통·v2·A0 프롬프트, development batch driver, 기존 자료 보존을 확인했다. A0는 EXPLORING에서 실제 모델의 단일 function_call을 dispatch하며, 등록할 사실·포함/제외·피어·도구·순서를 프로그램이 대신 결정하지 않는다. B의 고정 흐름은 `actor=program_fixed`, 최종 ledger 동기화는 `program_commit`으로 구분된다.

공통 compact wire는 기존 typed payload 필드를 보존한다. 축약 evidence의 doc_id/page만 실제 read map에서 복원하며 새 사실·수치·관측 위치를 추론하지 않는다. 변환 뒤에도 기존 SnapshotStore의 참조·기간·단위·분모·근거·원자적 등록 검증을 거친다. 값의 출처나 SELECTION/COVERAGE를 자동 생성하지 않는다.

동적 최종 schema는 현재 snapshot의 명시된 UNRESOLVED 키를 사용한다. minItems/maxItems와 field enum으로 모델에 계약을 제공하고, 최종 검증에서는 중복 없이 정확히 한 번 연결되는지와 OPEN request까지 계속 확인한다. 빈 목록이 업무 완료를 뜻하지 않도록 prompt에 명시했다.

patch는 전체 리뷰 재작성 대신 허용된 dictionary property의 빈 필드 추가·여분 키 삭제·동일 정수 형식·기존 claim 연결만 허용한다. 숫자·사실·판단·요청 상태·출처·list membership 변경은 금지된다. compact evidence `ev[].claim`과 기존 review evidence의 연결도 기존 선언된 claim으로 제한한다. patch 이후 schema 및 gateway 의미 검증을 다시 수행한다.

## 발견 및 해소

| ID | 발견 | 영향 | 조치와 재검토 |
|---|---|---|---|
| IR3-01 | A0 observation guard는 bare result만 측정했으나 실제 history에는 envelope와 새 state가 추가됨 | 한계 부근에서 반환 전 예약 검사가 실제 최종 요청량을 과소평가할 수 있음 | root가 full envelope/current state를 포함해 측정하고, 모든 반환에 1,024토큰, registered_ids/calculations/active_records 증가에는 추가로 `2×exploration_output_max + 2×result 토큰`을 예약. 최종 전송 직전 실제 요청을 다시 검사함을 확인 |
| IR3-02 | workers=2 경로가 launch 전 기존 STOP을 확인하지 않음 | 이미 중지를 요청해도 첫 API 호출이 시작될 수 있음 | 승인받아 main과 각 worker의 실제 launch 직전에 STOP 검사. 해시 검사 중 생성된 STOP도 재검사. 진행 중 호출은 완료·보존하고 대기 작업은 취소 또는 미실행 기록 |
| IR3-03 | 계획은 소스를 복사·해시 저장하지만 각 live run이 현재 ROOT를 hash 검증 없이 읽음 | freeze 뒤 소스/config 변경을 계획과 다른 상태로 침묵 실행할 수 있음 | 승인받아 복사본과 원본 해시 일치 및 각 launch 직전 동결 source hash를 검사. 변경 시 `NOT_STARTED_SOURCE_CHANGED`, API 0, 미실행 row 보존 |
| IR3-04 | v040 live 후 root 발견: deepcopy가 schema 내부의 공유 S 객체 alias를 유지하는데 missing_inputs.field에 enum을 제자리 추가함 | UNRESOLVED가 비어 있지 않은 ALT B에서 doc_id·결론 등 무관한 string까지 enum으로 제한되어 잘못된 schema가 모델에 전달됨 | v041에서 해당 field dict 자체 교체. nonempty·empty·별도 gateway·모든 enum 경로 독립성 재검증 통과. 사전 리뷰가 놓친 구현 결함으로 기록하며 ALT B를 모델 자체 격리 위반으로 단정하지 않음 |

IR3-01의 allowance는 측정된 전체 페이지에 중복으로 2배를 붙이지 않는다. 상태가 늘어나는 기능 결과에만 보수 예약을 붙인다. 현재 계약의 새 ID·UNRESOLVED enum·ledger history 증가를 다룰 합리적인 보수값이며 토큰 사용의 수학적 상한이나 실제 비용 확정값은 아니다. 런타임은 추정이라는 점과 실제 전송 전 재검사를 유지한다.

IR3-04는 사전 테스트가 등록된 UNRESOLVED가 빈 경로 및 schema 자체 유효성에 집중하여 놓쳤다. dict deepcopy를 했다는 사실만으로 모든 내부 노드가 서로 독립적인 객체가 된다고 판단해서는 안 된다. ALT A0와 MELCON A0는 실제 최종 요청에서 missing_inputs minItems=0, field enum 미설정이어서 이 enum 주입 경로를 타지 않았음을 별도 확인했다.

v041 후속 검토에서 관련 integration/independent review/format patch **49개 테스트 통과**를 확인했다. 별도 무과금 재현으로 UNRESOLVED=0의 모든 enum 경로가 원본과 같고, UNRESOLVED=1에서는 missing_inputs.field에만 해당 enum이 추가되며, 두 gateway에 applied_per/earnings_million_krw를 각각 등록해도 서로 영향을 주지 않음을 확인했다. 반환 schema의 enum을 수동 수정해도 다음 반환 schema 및 전역 REVIEW_V2가 바뀌지 않았다. B의 fatal isolation은 format repair 요청 전에 즉시 종료된다.

v041의 실제 공통 prompt에서 synthetic JSON block을 파싱해 기존 확장기·SnapshotStore로 다시 실행했고 8 records 및 M=100 생성에 성공했다. 예산 제안이나 진단 결과는 prompt에 포함되지 않았다. 공통 config는 condition 외 완전히 동일하며 0.4.1-dev, 입력 800,000/$1.25다. 나머지 출력·모델·도구·시간 상한은 유지한다. 검토자는 이 v041 production 소스를 수정하지 않았다.

IR3-02/03의 미실행 기록은 `directory=null`, `actual_model_answer=false`, `final_status=null`, 모델·도구 호출 0이다. 이는 모델 제출 실패와 다르므로 F/K/J 필수 미제출 0점 정책의 “시도한 실행”에 섞으면 안 된다. 중지된 batch의 `complete=false`, 미실행 계획 및 완료된 실행은 모두 기록된다. 모든 `NOT_STARTED_*`를 집계기에서 명시적으로 분리해야 한다.

freeze 검사와 실제 호출 사이에 다른 프로세스가 파일을 바꾸는 것을 OS 수준에서 잠그지는 않는다. 따라서 live 중 production source/config/prompt/driver 변경 금지 운영 원칙과 각 run input_hashes 대조를 계속 유지해야 한다. 이번 검토 완료 후 root가 production 변경 중지를 알렸다.

## 실제로 수행한 무과금 검증

1. `test_wire_contract.py`, `test_format_patch.py`, `test_gateway_v2.py`, `test_runtime_v2.py`: **102 passed**. 기존 typed 데이터와 compact의 snapshot·산술 동등성, 실제 read 위치 제한, 누락값 자동 생성 금지, 형식 patch의 의미 변경 거부, gateway/runtime 경계를 확인했다.
2. 추가된 `test_runtime_transient_retry.py`, `test_remediation_integration.py`, `test_remediation_independent_review.py`: **41 passed**. 신규 통합 및 transient retry 검증을 확인했다.
3. 새 current config의 compact/dynamic/patch 옵션을 그대로 켠 별도 임시 synthetic B/A0 실행: 둘 다 **SUBMITTED**, 동일 snapshot `X_3753f52b3a1ad7ed1e791a77`. B는 모델 2회·계산 레코드 14개, A0는 모델 7회·계산 레코드 1개였다. 이 A0 fixture는 EVALUATE만 선택하므로 민감도 수행이나 실제 모델 선택을 증명하지 않는다. 이전 테스트 fixture가 새 옵션을 제거하던 경로와 별도로 현재 옵션이 연결되는지만 확인한 것이다.
4. driver는 실제 runner를 stub으로 바꾼 임시 workspace에서 **7개 시나리오 통과**. workers=1/2의 기존 STOP은 live stub 호출 0회, workers=1/2의 freeze 후 소스 변경은 0회, 실행 중 STOP은 각각 이미 시작한 1회/2회만 완료, 정상 workers=2는 12회 완료. 모든 경우 12개 계획의 결과 또는 미실행 disposition이 중복·누락 없이 보존됐다. 실제 API나 실제 사례 run 폴더에는 쓰지 않았다.
5. driver `py_compile` 및 `git diff --check` 통과. prompt UTF-8 대체문자·후행 공백 없음과 구 cap 문구 제거를 확인했다.

driver 무과금 7개 검사에서는 main/worker 함수를 실제로 호출하되 `execute_v2`만 stub으로 대체했다. 특히 실제 ThreadPoolExecutor의 두 worker에서 STOP 후 추가 대기 작업이 API를 시작하지 않는지와 이미 시작한 작업이 결과를 남기는지를 확인했다. 검사에 사용한 임시 디렉터리는 검증 후 정리되었다.

## cap·retry·보존

B와 A0 config를 JSON으로 비교한 결과 **condition만 다르다**. 공통 버전은 0.4.0-dev, 입력 400,000·출력 24,000·model 24·tool 40·900초·$0.75, extraction 9,000·review 10,000·patch 1,500·탐색 단일 3,500이다. 모델과 reasoning effort는 이전과 같다. 새로운 조건이므로 v032와 동조건 성능으로 합치지 않는다.

transient retry는 500/502/503/504만 대상으로 같은 frozen request를 최대 한 번 더 보내고 요청 hash·attempt를 남긴다. SDK 숨은 retry는 꺼져 있다. 429·인증·quota 오류, completed/incomplete 답변의 결과를 보고 다시 답변을 고르는 동작은 하지 않는다. 실패 요청의 미확인 사용량은 추정 입력·최대 출력·보수 비용을 별도 예약하고 `usage_unknown=true`를 유지한다. 다음 시도도 실제 누적+unknown 예약+최종화 예약 한도를 검사한다. 알려진 사용량 0과 미확인 총사용량을 혼동하지 않는다.

`preserve_baseline.py` 재검증 시 manifest SHA256은 `6e1d056cfa772a8e43e3f67fe19f3519a2ebf94164ae51ef315e2c0a99b2dfff`였다. **전체 1,914개, source/design snapshot 67개, immutable evidence 1,847개, violations=[]**로 통과했다. 작업 소스의 승인된 변경은 별도 목록으로 보고되고 원본 snapshot은 정확히 유지됐다. 원문·비공개 기준표·v031/v032 실행·기존 보고서를 수정하지 않았다.

## 실제 진단 및 후속 판정

root가 `DIAG_v040` MELCON/ALT B/A0 네 실행을 별도 계획·동결하는 것으로 인계했다. diagnostic subset과 workers 수는 plan에 기록한다. 이 소수 진단 결과를 최종 6기업×B/A0=12회 평가 결과로 대신하지 않는다.

진단에서 확인할 것은 (1) 실제 REGISTER_BATCH 성공과 current snapshot, (2) 실제 EVALUATE·sensitivity 성공 및 calc_id 연결, (3) 유효 최종 제출, (4) 이미 읽은 핵심 입력의 등록/계산 미완료를 외부 자료 부재로 돌리지 않는지, (5) 항목별 원문 지지와 F/K/J 정확도, (6) 실제 비용·실패·retry 보존이다. 유효 제출이 있어도 방법론 정확도를 자동으로 통과시키지 않는다.

남아 있는 live 실패 가능성은 모델의 사실·기간·분모 선택 오류, 아직 검증하지 못한 실제 출력 길이·공백 반복, 제한된 탐색에서의 검색·등록 우선순위, 실제 API 처리다. 합성·단위 테스트가 이를 해결했다고 주장하지 않는다. 새 실제 실행 결과를 보고 채점·실패 진단을 계속해야 한다.
