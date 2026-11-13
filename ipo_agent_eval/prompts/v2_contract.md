공통 v2 데이터 계약을 따른다. 원문 선택과 해석은 모델이 하고, 계산기는 명시된 입력에 대한 산술만 한다.
값의 출처(DISCLOSED/DERIVED/UNAVAILABLE/NOT_APPLICABLE), 직접공시 존재 상태, 업무상 사용 가능 상태를 구별한다. 못 찾은 값은 0으로 만들지 않는다.
논리 레코드는 record_id/kind/payload로 구성되며 실제 전송 표현은 제공된 wire 계약을 따른다. CONTEXT를 먼저 정의하고 VALUE가 context_id로 참조한다. issuer 값의 entity_id는 null, 비교기업 값은 그 PEER record_id다. 금액은 백만원, 주가는 원, 주식수는 주, PER은 배다.
CONTEXT의 source_snapshot_id는 적용하는 문서·공시 정정 구획·시점의 묶음이고, API의 input_snapshot_id(X_...)는 등록 결과로 받은 불변 데이터 버전이다. 두 ID를 혼동하지 않는다. basis는 수치의 적용 기준, scope는 회사/연결·별도 범위, period는 실적기간, as_of는 기준일이다. unit/period/as_of/scope/basis/source_snapshot_id는 모두 비어 있지 않아야 한다. 모르는 내용은 구체적으로 미확인이라고 기록하고 적합성을 임의로 보증하지 않는다.
값의 fact_id는 VALUE의 record_id다. claim_id는 별도의 고유 주장 ID이며 그 VALUE의 evidence.claim_id는 동일 claim_id다. 실제 받은 read_source의 문서/물리쪽/chunk_id/locator만 인용한다.
SHARE_COMPONENT의 kind별 수량 fact를 등록하고 적용 분모의 INCLUDE/EXCLUDE/UNRESOLVED를 원문 근거와 연결한다. EXCLUDE가 아닌 구성의 basis는 EXISTING이면 PRE_OFFER_BASE, 나머지는 INCREMENT다. 각 구성의 source_snapshot_id는 참조 수량 fact의 CONTEXT와 같아야 하며, 동일 분모에서 EXCLUDE가 아닌 구성들과 COVERAGE는 같은 문서·정정시점 묶음을 사용한다. 공모 후 총수를 기발행 수량으로 넣어 다시 신주를 더하지 않는다. 구주매출은 증가분이 아니다. 옵션은 원문의 적용 분모 판단을 명시한다. COVERAGE에는 COMPLETE/INCOMPLETE 및 근거/한계를 기록한다.
직접 공시값과 계산값을 각각 보존한다. DERIVATION의 허용식은 MARKET_CAP(기준주가,기준주식수), PER(시가총액,기간이익), PRICE(주식가치,분모), SHARE_SUM(포함 구성)이다. 출력 fact는 코드가 계산한다. DERIVED 수치를 임의로 쓰지 않는다.
SELECTION으로 필드별 선택 fact와 이유를 명시한다. 직접값이 없더라도 동일 기준 원입력으로 파생할 수 있으면 DERIVABLE이다. 사용 가능한 값을 선택할 수 없으면 UNRESOLVED이며 확인한 범위와 이유를 남긴다.
주당 계산의 분모 역할은 SELECTION의 field=share_count다. 공시 분모(reported_share_count)와 합산 분모(derived_share_count)를 함께 등록했다면, 개별 공시/파생 필드의 선택과 별개로 주당 계산에 사용할 fact를 share_count에 원문 근거와 이유로 명시한다. 공시값과 파생값은 계속 보존한다. share_count를 명시적으로 UNRESOLVED로 두면 다른 분모가 있더라도 자동 대체하지 않는다. 적합성을 확인하지 못한 분모를 계산을 통과시키기 위해 선택하지 않는다.
calculation_uses에 검토에서 사용한 calc_id와 USE/REJECT, stated_value 및 이유를 연결한다. USE 숫자는 계산 결과의 Decimal 값과 같아야 하며 현재 input_snapshot_id의 결과를 쓴다. 과거/잘못된 계산을 REJECT할 때는 대체 값/계산 ID 또는 unresolved를 명시한다. 계산을 배제해도 기록은 남는다.
calculation_uses의 상태는 세 가지다. USE는 현재 snapshot의 OK 계산을 사용하므로 stated_value는 결과와 같은 숫자 문자열, replacement_id는 null, unresolved는 false다. REJECT하면서 사용 가능한 대체 fact/calc를 제시하면 replacement_id에 그 ID를 쓰고 unresolved는 false다. REJECT하면서 대체할 수 없으면 replacement_id는 null, unresolved는 true다. 이 unresolved는 해당 계산 사용/대체가 미해결이라는 뜻이다. 분모의 경제적 적합성, 공시 해석, 독립 원자료 확인 같은 업무상 불확실성은 USE 계산의 unresolved로 표시하지 않고 judgments.unknowns와 requests/escalations에 구체적으로 남긴다. 어떤 계산을 사용하거나 배제할지, 어떤 업무 판단을 보류할지는 모델이 결정한다.
missing_inputs는 현재 snapshot에 실제 등록된 SELECTION 중 usability=UNRESOLVED인 업무 의존성만 담는다. 상태에 제공된 required_missing_input_fields의 각 키를 정확히 한 번씩 쓰고 OPEN request와 연결한다. 등록된 UNRESOLVED가 없으면 missing_inputs는 []다. 이는 업무가 모두 끝났다는 뜻이 아니다.
그 밖의 업무상 미확인, 미열람, 등록·계산 미완료는 judgments의 unknowns와 검토 한계에 쓰고 필요한 requests/escalations를 연결한다. not_found_reasons에는 실제 상황에 맞는 NOT_READ/SEARCH_NOT_FOUND/UNAVAILABLE_IN_ALLOWED_INPUT/BUDGET_LIMIT과 확인 범위를 남긴다. 모든 null이나 미완료를 새 UNRESOLVED 의존성 또는 외부 자료 부족으로 간주하지 않는다.
요청/이관은 version=1부터 시작한다. 수정할 때 version을 올리고 change_reason을 적는다. 기존 OPEN 항목을 최종 목록에서 빼도 없어지지 않는다. 취소(CANCELLED)는 이유가 필요하고 RESOLVED는 실제 열람 근거가 필요하다. 외부 전송/외부 답변을 받은 것으로 쓰지 않는다.
J1~J4 검토에는 원문 사실, 판단 근거, 반대 근거, 미확인, 다음 행동을 포함한다. 계산 성공은 공시 해석이 맞다는 판정이 아니다.
최종 judgments[].facts[].claim_id는 이미 등록한 추출 claim_id의 재사용·재정의가 아니라 새 주장 선언이다. 최종 스키마가 지정한 전용 접두어(REVIEW_ 또는 충돌을 피한 REVIEW2_ 등)로 시작하는 전역 고유 ID를 사용하고 해당 사실의 evidence.claim_id도 같은 새 ID를 쓴다. 기존 추출 claim_id를 판단의 evidence에서 참조하는 것과 새 fact로 선언하는 것은 구분한다. 선언 ID나 근거 연결을 숫자·판단과 함께 사후 자동 변경하지 않는다.

## v2_contract.md에 넣을 설명

CONTEXT의 scope와 basis는 수치마다 다른 설명문을 붙이는 칸이 아니라, 계산 입력과 출력이 실제로 같은 비교 가능한 범위·적용 기준에 속하는지 선언하는 기준 표기다. 같은 원문 기준을 뜻하면 정확히 같은 문자열을 사용한다. 주가의 산정 방법, 주식수의 종류 등 개별 수치 설명은 근거 locator·선택 이유 등에서 구체적으로 구분한다. source_snapshot_id는 같은 문서·정정 시점 묶음의 ID이며 API input_snapshot_id와 다르다.

DERIVATION의 모든 입력과 출력 CONTEXT는 scope, basis, source_snapshot_id가 정확히 같아야 한다. MARKET_CAP, PRICE, SHARE_SUM은 as_of도 정확히 같아야 한다. 실제 같은 날짜는 YYYY-MM-DD 표기로 통일하고 날짜 뒤에 서로 다른 설명을 붙이지 않는다. 이익기간 period와 평가 기준일 as_of를 구분한다. 적용 단위는 각 필드에 맞게 유지한다. 같은 기준이라고 원문에서 확인할 수 없는 수치들을 계약 통과 목적으로 같은 표기로 맞추지 않는다. 실제 기준이 다르거나 비교 가능성을 확인하지 못하면 미해결 한계와 UNRESOLVED 선택을 남긴다.

계산할 출력 fact는 DERIVATION의 output_fact_id와 output field/context/claim으로 선언한다. 그 출력 ID를 VALUE 배열에 null 또는 추정값으로 중복 작성하지 않는다. 등록기가 허용식으로 계산한 출력 fact를 생성하므로, SELECTION의 selected_fact_id나 PEER의 해당 참조에는 그 출력 ID를 사용할 수 있다. 직접 공시값이 있으면 별도 VALUE ID로 원문값을 보존한다. DIRECT는 값이 있는 DISCLOSED fact를, DERIVABLE은 등록기가 성공적으로 생성한 값이 있는 DERIVED fact를 선택하는 상태다. 식을 적었다는 이유만으로 계산 불가 출력에 DERIVABLE을 선언하지 않는다.

등록 과정에서 DERIVATION 출력이 생성되는 것과 EVALUATE·sensitivity 작업 완료는 다르다. 검토에 연결할 계산 ID는 실제 EVALUATE와 sensitivity 결과에서 얻는다. A0의 도구·입력·순서·대안 선택권은 유지한다.



## 최소 synthetic 예시

아래 숫자·기업·문서 ID는 실제 사례가 아닌 계약 설명용 예시다. 실제 분석 입력으로 복사하지 않는다. 실제 사용 시에는 본인이 열람한 허용 원문의 값과 위치만 넣는다.

이미 읽은 synthetic 문서가 같은 날짜·범위의 주가 100원과 보통주 1,000,000주를 제공한다고 가정한다. CP/CS/CM의 단위만 각 필드에 맞게 다르고 scope·basis·as_of·source_snapshot_id는 같은 실제 기준을 가리킨다. 입력 VALUE는 P와 S뿐이다. 계산 출력 M은 DERIVATION D의 out으로만 선언하고 PEER와 SELECTION에서 참조한다.

compact_v2에서는 그 공통 비교기준을 groups의 G1에 한 번 선언하고 CP/CS/CM이 g=G1을 참조한다. 실제로 다른 비교기준이거나 같다고 확인하지 못한 경우에는 다른 group을 선언하며, 단위와 실적기간은 각 context에 그대로 둔다. 같은 그룹을 쓰는 판단은 모델이 원문에 근거해 명시한다.

```json
{"groups":[{"id":"G1","t":"2000-12-31","s":"SYN_PEER 보통주","b":"동일 기준일 보통주 평가","src":"SYN_DOC_CORRECTION_1"}],"contexts":[{"id":"CP","u":"원","p":"2000-12-31 시점","g":"G1"},{"id":"CS","u":"주","p":"2000-12-31 시점","g":"G1"},{"id":"CM","u":"백만원","p":"2000-12-31 시점","g":"G1"}],"values":[{"id":"P","f":"reference_price_krw","e":"PEER1","c":"FP","v":"100","x":"CP","o":"DISCLOSED","m":null,"d":null,"ev":[{"chunk":"SYN-p1","claim":"FP","at":"synthetic price"}]},{"id":"S","f":"reference_shares","e":"PEER1","c":"FS","v":"1000000","x":"CS","o":"DISCLOSED","m":null,"d":null,"ev":[{"chunk":"SYN-p1","claim":"FS","at":"synthetic shares"}]}],"shares":[],"peers":[{"id":"PEER1","n":"SYN_PEER","per":null,"cap":"M","earn":null,"price":"P","shares":"S"}],"derivations":[{"id":"D","op":"MARKET_CAP","inputs":["P","S"],"out":"M","f":"market_cap_million_krw","e":"PEER1","x":"CM","c":"FM"}],"selections":[{"id":"SEL","f":"market_cap_million_krw","e":"PEER1","disclosed":null,"selected":"M","status":"NOT_FOUND","use":"DERIVABLE","why":"synthetic same-basis inputs support the allowed derivation"}],"coverage":[],"notes":["SYNTHETIC ONLY"],"limits":[]}
```
