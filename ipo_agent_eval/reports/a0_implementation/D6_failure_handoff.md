# 관찰된 실패와 A1 설계 인계

0.3.2-dev 개발 비교 12회를 근거로 작성했다. A1은 아직 구현·실행하지 않았다. 아래 기록은 한 실행의 여러 문제를 나눠 적은 것이므로 기록 수를 실패 실행 수로 세지 않는다.

실행별 도구 call_id·실제 열람 쪽·snapshot·계산 ID·점수 영향·재검토·비용 연결은 [전체 인계 JSON](D6_failure_handoff.json)에 있다. [실행 비교](D5_v032_comparison.json) 및 [채점 집계](D5_comparison_summary.md)와 대조한다.

| 기록 | 사례/조건 | 관찰 유형 | 실행 근거 | A1 후보 |
|---|---|---|---|---|
| D6-001 | HDMS-DEV-01 B | MODEL_INCOMPLETE:max_output_tokens | [events](../../runs/20261113T102248Z_B_73727ba7/events.jsonl) | 공통/실행 후속 |
| D6-002 | HDMS-DEV-01 A0 | API_ERROR:InternalServerError | [events](../../runs/20261113T102350Z_A0_9b919d3e/events.jsonl) | 공통/실행 후속 |
| D6-003 | HDMS-DEV-01 A0 | NO_REGISTERED_CALCULATION_BEFORE_FINALIZATION | [events](../../runs/20261113T102350Z_A0_9b919d3e/events.jsonl) | A1-C1 |
| D6-004 | HDMS-DEV-01 A0 | UNRESOLVED_DECLARATION_MISMATCH | [events](../../runs/20261113T102350Z_A0_9b919d3e/events.jsonl) | A1-C2 |
| D6-005 | MELCON-DEV-01 B | MODEL_INCOMPLETE:max_output_tokens | [events](../../runs/20261113T102638Z_B_667bfd52/events.jsonl) | 공통/실행 후속 |
| D6-006 | MELCON-DEV-01 A0 | NO_REGISTERED_CALCULATION_BEFORE_FINALIZATION | [events](../../runs/20261113T102737Z_A0_775cc567/events.jsonl) | A1-C1 |
| D6-007 | MELCON-DEV-01 A0 | AVAILABLE_WORK_DEFERRED | [events](../../runs/20261113T102737Z_A0_775cc567/events.jsonl) | A1-C3 |
| D6-008 | DTS-DEV-01 B | MODEL_INCOMPLETE:max_output_tokens | [events](../../runs/20261113T102840Z_B_bef29a8c/events.jsonl) | 공통/실행 후속 |
| D6-009 | DTS-DEV-01 A0 | NO_REGISTERED_CALCULATION_BEFORE_FINALIZATION | [events](../../runs/20261113T102939Z_A0_9536c596/events.jsonl) | A1-C1 |
| D6-010 | DTS-DEV-01 A0 | AVAILABLE_WORK_DEFERRED | [events](../../runs/20261113T102939Z_A0_9536c596/events.jsonl) | A1-C3 |
| D6-011 | SHINSUNGST-DEV-01 B | MODEL_INCOMPLETE:max_output_tokens | [events](../../runs/20261113T103045Z_B_25ff9e77/events.jsonl) | 공통/실행 후속 |
| D6-012 | SHINSUNGST-DEV-01 A0 | MODEL_INCOMPLETE:max_output_tokens | [events](../../runs/20261113T103143Z_A0_9bdd2148/events.jsonl) | 공통/실행 후속 |
| D6-013 | SHINSUNGST-DEV-01 A0 | FORMAT_REPAIR_OUTPUT_LIMIT | [events](../../runs/20261113T103143Z_A0_9bdd2148/events.jsonl) | 공통/실행 후속 |
| D6-014 | SHINSUNGST-DEV-01 A0 | NO_REGISTERED_CALCULATION_BEFORE_FINALIZATION | [events](../../runs/20261113T103143Z_A0_9bdd2148/events.jsonl) | A1-C1 |
| D6-015 | SHINSUNGST-DEV-01 A0 | UNRESOLVED_DECLARATION_MISMATCH | [events](../../runs/20261113T103143Z_A0_9bdd2148/events.jsonl) | A1-C2 |
| D6-016 | ALT-DEV-01 B | MODEL_INCOMPLETE:max_output_tokens | [events](../../runs/20261113T103324Z_B_332eb41f/events.jsonl) | 공통/실행 후속 |
| D6-017 | ALT-DEV-01 A0 | MODEL_INCOMPLETE:max_output_tokens | [events](../../runs/20261113T103423Z_A0_cc00c4a1/events.jsonl) | 공통/실행 후속 |
| D6-018 | ALT-DEV-01 A0 | FORMAT_REPAIR_OUTPUT_LIMIT | [events](../../runs/20261113T103423Z_A0_cc00c4a1/events.jsonl) | 공통/실행 후속 |
| D6-019 | ALT-DEV-01 A0 | NO_REGISTERED_CALCULATION_BEFORE_FINALIZATION | [events](../../runs/20261113T103423Z_A0_cc00c4a1/events.jsonl) | A1-C1 |
| D6-020 | ALT-DEV-01 A0 | UNRESOLVED_DECLARATION_MISMATCH | [events](../../runs/20261113T103423Z_A0_cc00c4a1/events.jsonl) | A1-C2 |
| D6-021 | MILLIE-DEV-01 B | MODEL_INCOMPLETE:max_output_tokens | [events](../../runs/20261113T103602Z_B_09ae0bb7/events.jsonl) | 공통/실행 후속 |
| D6-022 | MILLIE-DEV-01 A0 | MODEL_INCOMPLETE:max_output_tokens | [events](../../runs/20261113T103701Z_A0_d0d960a0/events.jsonl) | 공통/실행 후속 |
| D6-023 | MILLIE-DEV-01 A0 | FORMAT_REPAIR_OUTPUT_LIMIT | [events](../../runs/20261113T103701Z_A0_d0d960a0/events.jsonl) | 공통/실행 후속 |
| D6-024 | MILLIE-DEV-01 A0 | NO_REGISTERED_CALCULATION_BEFORE_FINALIZATION | [events](../../runs/20261113T103701Z_A0_d0d960a0/events.jsonl) | A1-C1 |
| D6-025 | MILLIE-DEV-01 A0 | UNRESOLVED_DECLARATION_MISMATCH | [events](../../runs/20261113T103701Z_A0_d0d960a0/events.jsonl) | A1-C2 |

## 우선 검토할 A1 후보

### A1-C1 · 탐색 중 등록·계산 진행 확인

실제 관찰: D6-003, D6-006, D6-009, D6-014, D6-019, D6-024

탐지 후보: 누적 입력 예약이 줄어드는 동안 search/read만 반복되고 snapshot=X_EMPTY 또는 계산 결과가 0개인 상태.

예상 재검토: PREPARE 전 실제 읽은 핵심 원입력을 작은 묶음으로 등록하고 EVALUATE/민감도로 이어갈지 모델이 다시 계획하게 한다. 추가 검색 일부를 대체한다.

코드가 정답 수치·포함 여부를 주입하지 않는다. 예산 부족이면 미완료를 보존한다.

추가 비용은 미측정이다. 기존 탐색을 대체하면 추가 호출은 0이며, 계획 범위는 모델·도구 각각 0~3회다. 한 추가 호출을 입력 16,000·출력 1,000토큰으로 가정하면 표준 비캐시 $0.021, 동일 입력의 캐시 쓰기 상한 가정은 $0.025다. 실제 이력 길이·캐시·실행에 따라 달라진다. 공통 총예산 안에서 배치하며, 불가능하면 실패를 남긴다.

### A1-C2 · 최종화 전 의존성 선언 확인

실제 관찰: D6-004, D6-015, D6-020, D6-025

탐지 후보: 등록한 UNRESOLVED SELECTION 집합과 최종 missing_inputs 연결이 불일치하는 실제 실패.

예상 재검토: 탐색 단계에서 필요한 의존성 선언을 확인하고 최종화 입력에 현재 snapshot의 선언 집합을 명시하는 방안을 설계한다. COMMIT 후 탐색을 재개하거나 사실을 자동 수정하지 않는다.

공통 계약 설명 개선이 필요한 부분은 B/A0에 함께 적용할 공통 수정으로 분리한다. A1만 받는 확인 절차의 효과는 후속 실험에서 측정한다.

추가 비용은 미측정이다. 기존 탐색을 대체하면 추가 호출은 0이며, 계획 범위는 모델·도구 각각 0~3회다. 한 추가 호출을 입력 16,000·출력 1,000토큰으로 가정하면 표준 비캐시 $0.021, 동일 입력의 캐시 쓰기 상한 가정은 $0.025다. 실제 이력 길이·캐시·실행에 따라 달라진다. 공통 총예산 안에서 배치하며, 불가능하면 실패를 남긴다.

### A1-C3 · 코퍼스 안의 남은 작업과 외부 요청 구분

실제 관찰: D6-007, D6-010

탐지 후보: EXPLORING 중 확인 지점에서 요청원장 또는 중간 작업계획이 수치 등록·산술·허용 코퍼스 추가열람 같은 내부 작업을 외부 blocking 요청으로 넘기려는지 확인한다. 이미 읽은 사실과 아직 읽지 않은 자료를 구별한다.

예상 재검토: EXPLORING에서 남은 내부 작업을 현재 예약 예산으로 수행할 수 있는지 재계획한다. 외부 독립 자료 요청·사람 판단과 분리하고 예산이 막으면 BUDGET_LIMIT을 명시한다. FINALIZING/COMMIT에 진입한 뒤에는 조회·계산을 재개하지 않는다.

이번 최종 답안의 문제를 근거로 후속 A1의 탐색 중 확인 지점을 설계하는 후보다. 중간 계획/원장이 없으면 별도 확인 단계와 그 호출 비용이 필요하며 탐지 성공을 보장하지 않는다. HPSP와 같은 근거 있는 사업 판단 이관을 자동 취소하지 않는다. 모델의 요청 상태 변경은 기록하고 추후 채점한다.

추가 비용은 미측정이다. 기존 탐색을 대체하면 추가 호출은 0이며, 계획 범위는 모델·도구 각각 0~3회다. 한 추가 호출을 입력 16,000·출력 1,000토큰으로 가정하면 표준 비캐시 $0.021, 동일 입력의 캐시 쓰기 상한 가정은 $0.025다. 실제 이력 길이·캐시·실행에 따라 달라진다. 공통 총예산 안에서 배치하며, 불가능하면 실패를 남긴다.

## 공통 보완과 분리할 항목

B의 단일 추출은 출력 상한에서 중단됐다. ALT와 MILLIE에서는 많은 공백/탭 반복도 관찰돼 단순히 필요한 레코드가 길다는 원인만으로 설명하지 않는다. 전송 계약·고정 분할 추출을 새 버전에서 검토할 수 있지만, 이는 공통 기준선 실행 가능성 문제이며 A1의 효과로 주장하지 않는다.

긴 최종 JSON을 공통 형식 수정 2,500토큰으로 재작성하다 중단된 사례도 있다. 형식만 바꾸는 제한된 patch 계약 등은 별도 공통 설계 검토 대상이다. 이번 결과에는 숨은 재시도·사실 수정·상한 확대를 적용하지 않았다.

0.3.1의 이력 전송 HTTP 400은 공통 구현 결함으로 0.3.2에서 수정·검증했다. 이후 서버 오류와 사용량 불명은 실행 장애로 남겼다. 이런 사건을 A1의 방법론 개선 효과로 계산하지 않는다.

후속 W11에서는 탐지·미탐·오탐, 수치 등록·계산·제출 완료율, F/K/J, 추가 호출·비용을 각각 측정한다. 공통 보완은 B/A0 양쪽에 적용하고 A1만 추가로 받는 절차와 버전을 분리한다. 평가 후보 12개는 W12 동결 전 답변을 받지 않는다.
