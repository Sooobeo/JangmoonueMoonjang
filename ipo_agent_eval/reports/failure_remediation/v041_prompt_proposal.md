# v041 공통 프롬프트 보완 초안

상태: 제안 문서만 작성. production 소스·config·prompt는 수정하지 않았다. v040 결과를 보존한 뒤 새 버전에서 B/A0에 동일하게 적용하는 공통 계약 설명이다. 특정 기업의 정답이나 피어·분모 선택을 제공하지 않는다.

## v2_contract.md에 넣을 설명

CONTEXT의 scope와 basis는 수치마다 다른 설명문을 붙이는 칸이 아니라, 계산 입력과 출력이 실제로 같은 비교 가능한 범위·적용 기준에 속하는지 선언하는 기준 표기다. 같은 원문 기준을 뜻하면 정확히 같은 문자열을 사용한다. 주가의 산정 방법, 주식수의 종류 등 개별 수치 설명은 근거 locator·선택 이유 등에서 구체적으로 구분한다. source_snapshot_id는 같은 문서·정정 시점 묶음의 ID이며 API input_snapshot_id와 다르다.

DERIVATION의 모든 입력과 출력 CONTEXT는 scope, basis, source_snapshot_id가 정확히 같아야 한다. MARKET_CAP, PRICE, SHARE_SUM은 as_of도 정확히 같아야 한다. 실제 같은 날짜는 YYYY-MM-DD 표기로 통일하고 날짜 뒤에 서로 다른 설명을 붙이지 않는다. 이익기간 period와 평가 기준일 as_of를 구분한다. 적용 단위는 각 필드에 맞게 유지한다. 같은 기준이라고 원문에서 확인할 수 없는 수치들을 계약 통과 목적으로 같은 표기로 맞추지 않는다. 실제 기준이 다르거나 비교 가능성을 확인하지 못하면 미해결 한계와 UNRESOLVED 선택을 남긴다.

EVALUATE와 sensitivity에서도 함께 계산할 입력의 entity_id, scope, basis, source_snapshot_id 호환성을 검사한다. 같은 발행사의 같은 평가 기준을 사용하면서 이익에는 "연결 재무", 주식수에는 "보통주", 평가금액에는 "가격 계산"처럼 서로 다른 scope/basis 설명을 붙이면 이 도구 계약에서는 다른 기준으로 처리된다. 실제로 같은 평가 범위에 대응하는 수치인지 원문으로 판단한 뒤 공통 기준 표기를 선언하고, 수치마다 다른 귀속·유형·산출 방법은 해당 사실의 근거와 선택 이유에 보존한다. 귀속·기준의 실질적인 차이를 숨기거나 지우면서 계산을 통과시키지 않는다.

계산할 출력 fact는 DERIVATION의 output_fact_id와 output field/context/claim으로 선언한다. 그 출력 ID를 VALUE 배열에 null 또는 추정값으로 중복 작성하지 않는다. 등록기가 허용식으로 계산한 출력 fact를 생성하므로, SELECTION의 selected_fact_id나 PEER의 해당 참조에는 그 출력 ID를 사용할 수 있다. 직접 공시값이 있으면 별도 VALUE ID로 원문값을 보존한다. DIRECT는 값이 있는 DISCLOSED fact를, DERIVABLE은 등록기가 성공적으로 생성한 값이 있는 DERIVED fact를 선택하는 상태다. 식을 적었다는 이유만으로 계산 불가 출력에 DERIVABLE을 선언하지 않는다.

등록 과정에서 DERIVATION 출력이 생성되는 것과 EVALUATE·sensitivity 작업 완료는 다르다. 검토에 연결할 계산 ID는 실제 EVALUATE와 sensitivity 결과에서 얻는다. A0의 도구·입력·순서·대안 선택권은 유지한다.

## 최소 synthetic 예시

아래 숫자·기업·문서 ID는 실제 사례가 아닌 계약 설명용 예시다. 실제 분석 입력으로 복사하지 않는다. 실제 사용 시에는 본인이 열람한 허용 원문의 값과 위치만 넣는다.

이미 읽은 synthetic 문서가 같은 날짜·범위의 주가 100원과 보통주 1,000,000주를 제공한다고 가정한다. CP/CS/CM의 단위만 각 필드에 맞게 다르고 scope·basis·as_of·source_snapshot_id는 같은 실제 기준을 가리킨다. 입력 VALUE는 P와 S뿐이다. 계산 출력 M은 DERIVATION D의 out으로만 선언하고 PEER와 SELECTION에서 참조한다.

```json
{"contexts":[{"id":"CP","u":"원","p":"2000-12-31 시점","t":"2000-12-31","s":"SYN_PEER 보통주","b":"동일 기준일 보통주 평가","src":"SYN_DOC_CORRECTION_1"},{"id":"CS","u":"주","p":"2000-12-31 시점","t":"2000-12-31","s":"SYN_PEER 보통주","b":"동일 기준일 보통주 평가","src":"SYN_DOC_CORRECTION_1"},{"id":"CM","u":"백만원","p":"2000-12-31 시점","t":"2000-12-31","s":"SYN_PEER 보통주","b":"동일 기준일 보통주 평가","src":"SYN_DOC_CORRECTION_1"}],"values":[{"id":"P","f":"reference_price_krw","e":"PEER1","c":"FP","v":"100","x":"CP","o":"DISCLOSED","m":null,"d":null,"ev":[{"chunk":"SYN-p1","claim":"FP","at":"synthetic price"}]},{"id":"S","f":"reference_shares","e":"PEER1","c":"FS","v":"1000000","x":"CS","o":"DISCLOSED","m":null,"d":null,"ev":[{"chunk":"SYN-p1","claim":"FS","at":"synthetic shares"}]}],"shares":[],"peers":[{"id":"PEER1","n":"SYN_PEER","per":null,"cap":"M","earn":null,"price":"P","shares":"S"}],"derivations":[{"id":"D","op":"MARKET_CAP","inputs":["P","S"],"out":"M","f":"market_cap_million_krw","e":"PEER1","x":"CM","c":"FM"}],"selections":[{"id":"SEL","f":"market_cap_million_krw","e":"PEER1","disclosed":null,"selected":"M","status":"NOT_FOUND","use":"DERIVABLE","why":"synthetic same-basis inputs support the allowed derivation"}],"coverage":[],"notes":["SYNTHETIC ONLY"],"limits":[]}
```

이 예시는 무과금으로 `expand_wire_extraction`과 실제 `SnapshotStore.register`에 통과시켰다. 8개 레코드가 등록되고 M의 origin=DERIVED, value="100"(백만원)이 생성됐다. values에 M을 선언하지 않았다. 원본 데이터·모델 답변·private gold는 사용하지 않았다. 이 검사는 계약 예시의 실행 가능성을 확인한 것이며 실제 모델이 올바른 비교 기준을 판단함을 보증하지 않는다.

## 버전·예산 표기 제안

v041에서 제안된 공통 입력 cap 800,000 및 run cap $1.25는 v040의 400,000/$0.75와 다른 조건이다. 출력 24,000·model 24·tool 40·900초를 유지하더라도 전체 이력 재전송 비용에 대한 새 실행 조건으로 기록한다. 6기업×B/A0=12회 최대 계획 비용은 $15.00이며 진단 비용은 별도로 보존·집계한다. 예산 확대만의 효과나 프롬프트 보완만의 효과로 결과 개선을 단정하지 않는다.

v040 MELCON A0는 48개 입력 등록에는 성공했지만 그 뒤 INPUT_RESERVATION으로 최종화되어 EVALUATE와 sensitivity는 실행하지 못했다. 따라서 새 cap의 목적은 남은 작업을 모델이 선택할 실행 여유를 제공하는 것이다. 프로그램이 다음 행동을 자동 선택하거나 기존 답변을 다시 써서 정답률을 올리는 변경은 포함하지 않는다. 실제 새 실행에서 유효 제출·등록·산술·민감도 여부와 남는 의미 해석 오류를 분리하여 확인한다.
