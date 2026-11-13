# v032 A0 공통 실패 독립 진단 3

작성일: 2026-11-13. 검토자: case_roster 에이전트. 범위: 읽기 전용 원인 진단 및 수정 경계 검토. 사람이 채점한 보고서가 아니다. 이 검토에서 API를 호출하거나 코드, 실행 원본, 공개 원문, 비공개 기준표를 수정하지 않았다.

## 결론

v032 A0 여섯 실행에서 `calculate`와 `sensitivity`는 실제로 노출되어 있었다. 그러나 모델은 검색과 열람만 선택했고, 모든 실행이 입력 예산 예약 검사에서 `INPUT_RESERVATION`으로 최종화되었다. 최종 snapshot은 모두 `X_EMPTY`, 등록 records는 0, calculations는 빈 배열이다. 따라서 관측된 공통 경로는 **검색·열람 반복 → 누적 입력과 최종 제출 예약 한도 도달 → 등록·계산이 금지된 최종화 → 불완전한 제출 또는 제출 실패**이다.

예산 상태와 현재 등록 상태를 모델이 충분히 알 수 없었던 점, 긴 typed schema·전체 페이지·누적 대화의 반복 전송, 작은 단일 탐색 출력 한도는 공통 도구 계약의 사용성과 실행 가능성을 약화시켰다. 다만 모델이 등록보다 검색을 선택한 내부 이유는 로그로 확인할 수 없다. “반드시 예산 정보 부족 때문에 등록하지 않았다” 또는 “모델 성능만 문제였다”는 단정은 하지 않는다.

공통 계약 압축, 중립적인 상태·예산 제공, 실제 snapshot과 일치하는 최종 schema, 의미를 바꾸지 않는 작은 형식 patch는 B/A0 공통 보수로 허용할 수 있다. 프로그램이 등록할 사실이나 다음 도구를 골라 주거나 미등록을 감지해 계산을 자동 실행하는 변경은 A0의 자율 선택을 바꾼다. 예산을 늘리는 변경은 새 실험 조건이며 v032와 분리해야 한다.

## 확인한 원본과 관측

코드는 `reports/a0_implementation/D5_v032_source/`의 동결본을 기준으로 읽었다. 테스트는 수정 전 보존본 `reports/failure_remediation/baseline_source/ipo_agent_eval/tests/test_agent_loop_v2.py`와 대조한다. 실제 실행 식별은 `reports/a0_implementation/D5_v032_runs.json`, 각 실행의 `events.jsonl`, `snapshots.json`, `calculations.json`, raw response 및 기존 F/K/J 채점 보고서를 사용했다.

아래 입력은 **성공적으로 돌아온 탐색 응답들의 usage 합계**이다. “마지막 예약”은 마지막으로 기록된 허용 탐색 요청의 추정값이며, 그 다음 거절된 요청의 추정값으로 오해하면 안 된다. 입력 추정에는 오차가 있으므로 실제 usage와 별도로 취급한다.

| 기업 / run_id | 탐색 모델 호출 | 모델 검색 / 열람 호출 | 탐색 실제 입력 | 마지막 예약의 요청 입력 / 최종·repair 입력 | 강제 최종화 events 줄 | 결과 |
|---|---:|---:|---:|---:|---:|---|
| HDMS / `20261113T102350Z_A0_9b919d3e` | 8 | 7 / 1 | 106,011 | 23,706 / 37,804 | 45 | FAILED |
| MELCON / `20261113T102737Z_A0_775cc567` | 7 | 4 / 3 | 88,430 | 26,365 / 40,463 | 40 | SUBMITTED, HUMAN_REVIEW |
| DTS / `20261113T102939Z_A0_9536c596` | 8 | 4 / 4 | 104,480 | 29,303 / 43,401 | 45 | SUBMITTED, HUMAN_REVIEW |
| SHINSUNGST / `20261113T103143Z_A0_9bdd2148` | 7 | 4 / 3 | 91,619 | 32,820 / 46,918 | 40 | FAILED |
| ALT / `20261113T103423Z_A0_cc00c4a1` | 7 | 4 / 3 | 88,577 | 29,341 / 43,439 | 40 | FAILED |
| MILLIE / `20261113T103701Z_A0_d0d960a0` | 8 | 4 / 4 | 107,192 | 27,897 / 41,995 | 45 | FAILED |

여섯 실행의 `snapshots.json#/current_id`는 `X_EMPTY`, `snapshots/X_EMPTY/records`는 `{}`, `calculations.json`은 `[]`다. 원래 두 SUBMITTED 사례 역시 산술 수행 성공 사례가 아니다. 전체 tool count에 들어 있는 `request_information` 및 `escalate`는 최종 COMMIT의 내부 ledger 동기화(`actor=program_commit`)다. 이를 모델이 탐색 중 요청·이관 도구를 선택한 것으로 세면 안 된다. 관련 구현은 동결 `tool_gateway.py:315` 이후이며, 표의 검색·열람은 `actor=model` 실제 tool_call만 센 값이다.

## 원인별 근거와 추론의 한계

### 1. 도구 노출 누락은 아니다

동결 `ipo_eval/tool_gateway.py:122`의 EXPLORING schema에는 허용한 7개 도구가 모두 있으며, `calculate.request`는 `REGISTER_BATCH`와 `EVALUATE` typed schema의 anyOf다. `tools()`는 각 schema를 `strict=true`로 제공한다(`:142`). 탐색마다 `agent_loop.py:72`에서 이를 요청에 넣는다. 등록 설명도 “typed records를 현재 snapshot에 원자적으로 추가”한다고 명시한다.

동결 `prompts/A0.md:3`은 작은 records 묶음 등록과 반환 snapshot 이어쓰기를, `:4`는 실제 EVALUATE/sensitivity 호출을 설명한다. `v2_contract.md:3`~`:9`는 CONTEXT/VALUE/PEER/SHARE_COMPONENT/DERIVATION/SELECTION과 단위·계산 연결을 명시한다. 따라서 “등록을 전혀 안내하지 않았다”, “calculate가 API에서 빠졌다”, “자유형 payload만 있었다”는 진단은 근거와 다르다.

그럼에도 다양한 레코드와 의존 ID를 정확하게 생성해야 하는 부담은 컸다. 탐색 한 응답 1,000토큰(추론 포함)과 작은 batch 안내의 조합이 실제 기업 입력을 얼마나 원활히 등록하게 하는지는 검증되지 않았다. `calculate`가 등록과 산술 두 기능을 겸하는 이름·계약도 학습 부담 가능성이 있다. 이는 사용성 가설이며 원인으로 확정하지 않는다. 기업 정답을 담지 않은 최소 synthetic 예제와 동등한 typed 표현 간소화로 검증할 수 있다.

### 2. 입력 예약은 작동했지만 모델에게 남은 실행 가능량이 보이지 않았다

동결 `agent_loop.py:80`~`:82`의 초기 payload가 보여주는 budget은 모델 호출 상한, 도구 호출 상한, 총 출력 상한, 단일 탐색 출력 상한뿐이다. 누적 입력 상한 160,000, 실제 사용량, 앞으로 최종화/repair에 예약할 입력량, 남은 달러·시간은 매 단계 모델에게 전달되지 않는다. 도구 envelope의 usage_delta만으로는 이런 잔량을 알아낼 수 없다.

`runtime_v2.py:17`의 dumps는 indent=2이며, `agent_loop.py:118`, `:134`는 raw model 출력과 전체 도구 결과를 대화에 누적한다. 모든 탐색 요청은 typed 도구 schema도 다시 보낸다. 토큰 사용은 페이지를 한 번 읽을 때만 발생하는 것이 아니라 뒤 요청의 입력에서도 누적된다. 최종화만의 입력도 그 대화를 포함한다.

동결 `budget.py:51`의 검사는 `실제 누적 입력 + 다음 요청 추정 입력 + 최종/repair 예약 입력 <= 상한`이다. 예약은 `budget.py:18` 및 `agent_loop.py:105`에서 계산한다. 이 검사는 비용·최종화 예산을 지키는 장치다. 없애거나 계산을 누락하면 해결이 아니다. 다만 입력 잔량을 보지 못한 채 탐색하던 모델은 `agent_loop.py:108`~`:112`의 강제 FINALIZING에 도달하면 더 등록·계산할 수 없다.

새 상태 정보는 같은 검사기에서 산출한 실제 사용량, 추정 다음 요청량, 최종/repair 예약량, 사용 가능 잔량, snapshot ID·record 수·등록된 UNRESOLVED 키·계산 ID를 정확하게 보여줘야 한다. 사용량과 추정값을 구분하고, 아직 선택하지 않은 다음 도구의 정확한 비용을 보장하지 않아야 한다. 상태 정보 자체도 입력 비용에 포함해야 한다.

### 3. 빈 snapshot과 missing_inputs 계약이 뒤늦게 충돌했다

동결 `validation_v2.py:34`는 snapshot에서 `SELECTION.usability=UNRESOLVED`로 명시된 키만 미해결 의존성으로 인정한다. `:113`~`:121`는 최종 `missing_inputs`가 그 집합과 정확히 일치하고 각 항목이 OPEN request에 연결되어야 한다고 검사한다. 빈 snapshot의 선언된 집합은 빈 집합이므로 `missing_inputs=[]`가 맞다. 이는 “업무상 미완료가 없다”는 뜻이 아니다.

HDMS와 신규 세 A0의 COMMIT은 모두 `missing_inputs must name each declared UNRESOLVED business dependency exactly once`로 거절되었다. 해당 tool_envelope는 HDMS events 52행, SHINSUNGST/ALT 47행, MILLIE 52행이다. 모델은 읽지 못한 내용·계산 미완료를 보고하려 했지만, 사전에 UNRESOLVED selection을 등록하지 않은 상태였다. 원문의 공백, 등록의 공백, 계산 미완료를 같은 필드로 표현하기 쉬운 계약이었다.

실제 snapshot의 허용 missing key를 최종 schema와 메시지에 동일하게 주는 것은 계약 정합성 보수다. 단순 maxItems/field enum만으로 중복 없이 정확히 한 번 연결됨이 보장되지는 않으므로 서버의 기존 정확 집합·중복·OPEN request 검증은 유지해야 한다. 빈 배열을 허용했다고 등록·계산 미완료가 사라져서는 안 된다. 그 미완료는 `not_found_reasons`, 검토 한계, 판단 상태와 업무완료 지표에 계속 드러나야 한다. 모델 대신 UNRESOLVED/USABLE을 선언하거나 필요한 사실을 채워 넣으면 안 된다.

### 4. 전체 JSON 형식 재작성은 작은 repair 한도와 맞지 않았다

동결 `repair_structure`는 오류와 전체 이전 JSON을 보내고 같은 전체 JSON을 다시 요구한다(`agent_loop.py:50`~`:65`). `_format_only`는 리스트 길이, 숫자·주장·판단·출처 변경을 금지한다(`:21`~`:47`). 따라서 missing_inputs의 잘못된 항목들을 제거하거나 새 selection을 등록하는 것은 일반 형식 repair로 해결할 수 없다. 최종화 이후 탐색 재개도 금지되어 있다.

신규 세 A0의 최초 최종화 응답은 각각 출력 4,440 / 4,306 / 4,414토큰이며, 재작성 응답은 모두 2,500토큰 한도에서 `incomplete:max_output_tokens`로 끝났다. SHINSUNGST·ALT는 `08_finalize_response.json`과 `09_format_repair_response.json`, MILLIE는 `09_finalize_response.json`과 `10_format_repair_response.json`을 대조했다. HDMS는 동일한 선행 계약 오류 이후 repair API500으로 끝났으므로 토큰 한도 실패로 합치면 안 된다. unknown usage도 0으로 취급하지 않는다.

작은 patch 방식은 전체 리뷰 재출력 비용을 줄일 수 있다. 허용 path와 변경 종류를 제한하고 적용 후 원본 대비 의미불변 및 전체 검증을 해야 한다. 금액·판단·요청 상태·기존 list cardinality를 바꾸어 실패를 성공으로 만드는 repair는 금지한다. 등록 누락이라는 업무 실패를 repair가 대신 해결해서도 안 된다. 한 번의 B/A0 공통 형식 보정 정책, 원본과 patch 원문 보존을 유지한다.

### 5. B의 출력 실패와도 구분해야 한다

신규 세 B는 최초 extraction 출력 5,000토큰에서 미완료였다. ALT raw text 26,339자 중 후행 공백 22,372자, MILLIE 232,404자 중 후행 공백 227,869자가 관측되었다. 이는 원문 긴 JSON이 자연스럽게 잘린 현상만으로 설명할 수 없다. 관측 가능한 사실은 JSON 값/근거 생성 중 대량 공백 반복과 미완료이며, 모델·API·structured decoding 중 어느 층의 원인인지 로그만으로 확정할 수 없다. typed 표현을 간소화하고 공백 반복을 별도 감시하되, 출력 상한 증가만으로 고쳐졌다고 판단하지 않는다. 기존 raw 답변을 정답 extraction으로 대체하지 않는다.

## 테스트가 실제 실패를 잡지 못한 이유

보존된 `tests/test_agent_loop_v2.py:16`~`:38`의 fixture는 실제 기업 PDF가 아닌 한 쪽의 synthetic 텍스트다. `Scripted.create():98`~`:105`는 search → read → REGISTER_BATCH → EVALUATE → search → PREPARE 순서를 fixture가 직접 결정한다. 반환 usage도 매번 input=100/output=100으로 고정한다(`:108`~`:109`). `test_T15_full_autonomous_path...`는 이 순서의 gateway·state·call_id 연결이 되는지를 확인한다. **실제 모델이 독립적으로 그 순서를 선택함을 확인하는 테스트가 아니다.** 이 경로에는 sensitivity 선택도 없다.

`test_T13_budget_forces_only_finalization_without_an_exploration_call`은 예산이 부족할 때 추가 탐색 없이 제출하는 경계의 작동을 확인하며, 산술·민감도 업무가 완료됐는지는 요구하지 않는다. 작동 경계 테스트로는 유효하지만 운영 성공의 근거로 쓰면 안 된다. 합성 fixture의 짧은 리뷰는 전체 JSON repair가 실물 리뷰보다 작은 출력 한도에서 실패하는 상황도 드러내지 못한다.

필요한 검증 계층은 분리해야 한다. (1) typed schema·API wire·의미불변 보정 단위 검증, (2) 실제 corpus 크기와 누적 history·예약을 쓰는 무과금 예산 검증, (3) 실제 모델의 선택·등록·계산·제출을 관측하는 제한된 probe, (4) 수정과 한도를 동결한 6기업×B/A0 새 paired 실행이다. synthetic 성공이나 schema상 SUBMITTED만으로 (3)·(4)를 대체할 수 없다.

## 제안된 0.4.0 수정의 A0/A1 경계

다음은 구현 완료 판정이 아니라 root가 제안한 수정안에 대한 독립 경계 검토다. 새 코드를 별도 최종 검토해야 한다.

| 제안 | 공통 보수로 인정하는 조건 | 경계를 넘는 변경 |
|---|---|---|
| wire JSON minify | 동일 데이터·타입·한글·전체 페이지·ID를 보존하고 저장 원본과 실제 전송 payload를 구별 | 값/근거 삭제, 숨은 요약·절단으로 예산을 맞춤 |
| typed 배열 compact | B/A0가 같은 명시 계약을 받고 의미·출처·단위·선택 상태를 모두 보존; old/new round-trip 동등성 검증 | 원문을 코드가 읽어 사실/피어/분모를 자동 선정하거나 누락값 생성 |
| 현재 snapshot·remaining budget | 사실적인 상태, 계산식과 추정 한계를 공통 제공; 모델이 다음 행동 선택 | “N회 검색했으므로 지금 등록하라” 같은 진행상황별 전략 지시나 강제 tool choice |
| snapshot 맞춤 최종 schema | 실제 선언된 UNRESOLVED를 직렬화; 정확 집합 검증·한계 보고 유지 | 모델 대신 UNRESOLVED/USABLE 선언, 누락 업무를 완료로 변경 |
| 1,500토큰 patch repair | 형식·기존 claim 연결 등 허용한 변경만, 원문·patch·적용 결과 보존 | 수치·판단·요청 상태 변경, 새 근거/등록/계산/전략 추가 |
| 등록·산술·민감도를 공통 업무요구로 명시 | B/A0 동일 평가 업무를 사전 명시; A0의 순서·도구·입력 선택은 그대로 | A0만 실패 징후에 맞춘 코칭, 자동 REGISTER/EVALUATE/sensitivity 호출 |
| 예산 400k 입력/24k 출력/24 model/40 tool/900초/$0.75 | 새 0.4.0 조건으로 양쪽 동결, 모든 시도 기록, 실제 예약과 비용 검사 유지 | v032와 동조건 개선 효과로 합산, 성공할 때까지 비공개 재실행 |

입력 한도 확대·탐색 출력 3,500·B extraction 9,000·review 10,000·patch 1,500은 기존 계약 표현과 업무량을 감당하도록 하는 실행조건 변경이다. 계획상 공통 cap이 같더라도 B 고정 흐름과 A0 선택 흐름의 호출 수·출력 배분이 다른 점은 기록해야 한다. 이런 다중 변경의 결과를 한 가지 수정의 인과 효과라고 표현할 수 없다.

연구용 A1 후보인 “등록 진척 없음 감지 후 재계획”, “읽은 필수 근거에 대한 계산 우선 지시”, “내부 미완료를 외부 요청으로 돌리려는 시점의 행동 교정”은 별도 연구 개입으로 남긴다. 특히 FINALIZING/COMMIT 뒤 탐색을 재개하는 수선은 허용하지 않는다. 완료 검증기가 미완료 실행을 실패/불완전으로 판정하는 것은 가능하지만, 그 검증기가 A0 대신 작업을 수행해서는 안 된다.

## 수정 후 실제 acceptance

새 batch는 사전 plan에 6개 개발 기업×B/A0=12회, 버전·모델·프롬프트·공통 cap·순서·반복수·예산·probe 제외 규칙을 남기고 소스를 동결해야 한다. probe는 별도 ID로 보존하고 최종 paired 성능 분모에 섞지 않는다. 12회 run cap 합계는 $9.00이며 probe 예산은 별도로 기록한다. 실제 청구액과 사용량 기반 추정액을 혼동하지 않는다.

각 12회에 대해 다음 항목을 실제 artifact로 확인한다. 통과를 위해 데이터를 지어내거나 오류 답변을 덮어쓰지 않는다.

1. **유효 제출:** 실제 API 완료, 검증 통과한 review artifact, J1~J4와 ledger 일관성. FAILED이면 이유·unknown usage·raw partial을 보존한다. SUBMITTED 단독으로 실질 완료라 하지 않는다.
2. **등록:** 모델이 읽은 원문에 연결된 비어 있지 않은 typed records, 올바른 CONTEXT/단위/기간/주식 구성/피어 및 선택 상태. A0는 실제 `actor=model` REGISTER_BATCH가 있어야 한다. dummy record 하나로 통과하지 않는다. B는 기존 고정 흐름의 기록임을 구분한다.
3. **산술:** 현재 최종 snapshot에서 실제 성공한 계산 ID, 사용 입력과 Decimal 결과, review `calculation_uses` 연결. 기존 K1~K3 기준에 따른 PER 집계·기업가치/주당가치·분모 점검을 항목별로 채점한다. EVALUATE 호출 한 번이나 오류 계산만으로 통과하지 않는다.
4. **민감도:** 실제 sensitivity 실행, 허용 대안과 가정·결과·현재 snapshot 연결, 검토에서 결과를 해석한 근거. 피어 둘의 중앙값이 평균과 같은 경우에도 도구 호출만으로 J3 만점을 주지 않는다. 자료에 근거한 대안 또는 미변화 이유를 구분한다.
5. **근거 적합성과 업무 판단:** 실제 read 위치와 원문 의미 지지를 claim별 FULL/QUALIFIED/UNSUPPORTED로 확인한다. 구조화 최종 claims의 FULL/제출 claim 수와 사실·계산·방법론 정확도를 별도 집계한다. 읽은 입력의 등록/계산 미완료를 외부 자료 부재로 돌렸는지도 요청 항목별로 검토한다.
6. **비용·보존·독립성:** 새 budget의 누적 입력/출력/모델/도구/시간/달러 cap 및 최종/repair 예약, API500 unknown usage, 자동 retry 여부, 모든 실패 artifact를 확인한다. v031/v032·D0·원문·비공개 기준표 해시와 동결 source를 보존하고, 이후 모델에는 비공개 gold를 전달하지 않는다.

F1~F5는 각각 0/1, K1~K3는 각각 0/1, J1~J4는 각각 0/1/2로 기존 기준표를 적용한다. 상위 프로토콜 §11.1에 따라 **실제로 시도했으나 제출하지 못한 필수 항목은 0점**, 미실행은 null이다. 실패의 final_status와 미관측 내용오류·잘못된완료·불필요보류 판정은 null이며, 원문 partial은 실패 진단 근거로만 쓴다. 필수 항목 0점과 내용 오류 관찰은 서로 다르다. 유효 제출률, 등록·산술·민감도 완료율, 실패율, F/K/J 점수, 비용을 함께 보고한다.

12회 모두 유효 제출+실제 등록+산술+민감도가 확인되지 않으면 “실제 실패 원인 해결 완료”로 판정하지 않는다. 실패 유형과 미충족 항목을 그대로 남기고 추가 수정을 새로운 버전·사전 계획으로 분리한다. 운영 통과와 방법론적으로 올바른 답변은 다른 판정이므로, 위 작업 경로가 성공해도 F/K/J 채점과 독립 최종 검토는 계속 필요하다.

## 검토 한계

이 보고서는 v032 원본과 제안된 수정 경계를 검토한 것이다. 새 0.4.0 코드와 실제 응답의 성공을 확인한 보고서가 아니다. 예산 증가나 계약 압축이 모델 행동을 개선할지는 새 실제 실행으로 확인해야 한다. 단일 반복의 여섯 개발 사례 결과를 전체 IPO에 일반화하거나 최종 평가 후보 12개를 이미 검증했다고 보고하지 않는다.
