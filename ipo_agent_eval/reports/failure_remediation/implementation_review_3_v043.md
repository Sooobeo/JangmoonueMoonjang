# v043 공통 계약 검토 3차

**PASS — 실제 12회 실행·내용 정확성은 별도 검증한다.** 검토 중 생산 소스·기존 실행·정답표는 변경하지 않았고 API는 호출하지 않았다. 검토자는 이전 프롬프트·드라이버 작성 이력이 있으므로 완전한 맹검 감사가 아니다.

compact_v2의 groups는 모델이 선언하는 배치 로컬 사전이다. as_of/scope/basis/source_snapshot_id를 한 번 쓰고 각 context는 unit/period/group_id를 가진다. 확장기는 모델이 지정한 group의 네 필드를 기계적으로 복사해 기존 논리 CONTEXT의 여섯 필드를 복원한다. unit과 실적기간은 합치지 않는다. 그룹 선택·별도 그룹 선언·원문 적합성·값·선택 fact·미해결 판단을 모델이 계속 결정한다. 동일 회사라는 이유로 자동 통일하거나 문구를 의미상 같다고 추론하는 코드는 없다.

encoder는 네 필드의 **정확한 문자열 tuple**만 중복 제거한다. 공백 차이도 합치지 않는다. decoder는 undefined/duplicate group ID를 거절하며 배치 사이의 group 상태를 숨겨 유지하지 않는다. 기존 context_id만 참조하는 증분 배치는 빈 groups/contexts를 사용할 수 있다. 유효한 미참조 group은 raw 로그에 남고 논리 레코드를 만들지 않는다. 그 사실을 계약이 명시한다. 무손실 보장은 논리 payload·snapshot·계산 결과를 대상으로 하며 모델이 정한 group 이름이나 미참조 group 자체를 재인코딩 후 동일하게 복원한다는 뜻은 아니다.

독립 synthetic 확인 결과는 `v043_independent_contract_check_3.json`에 기록했다. 기존 계약을 grouped wire로 왕복해 모든 레코드·snapshot ID·계산 결과가 같았다. 주식수 입력만 다른 basis의 group에 넣으면 기존 derivation INVALID가 유지됐다. 이 출력을 DERIVABLE로 선택한 batch는 원자적으로 거절되고 X_EMPTY가 유지됐다. 테스트에서 그 잘못된 선택만 제거한 별도 synthetic snapshot에는 INVALID 결과가 그대로 남았다. group이 계산 성공을 위해 다른 기준을 강제 합치지 않는다는 증거다.

최종 사실 claim ID 전용 namespace는 기존 등록 claim과의 선언 충돌을 생성 전에 피하는 형식 제한이다. REVIEW_ 접두어가 이미 사용 중이면 REVIEW2_ 등을 찾되 실제 사실·숫자·판단이나 기존 ID를 사후 변경하지 않는다. 등록에 REVIEW_A와 REVIEW2_B가 있으면 최종 사실 leaf만 ^REVIEW3_[A-Za-z0-9_-]+$와 전체 길이160 제한을 받는 것을 독립 검사했다. 접두어만 쓰거나 공백·한글 suffix 또는 길이 초과인 ID는 거절된다. 다른 gateway는 ^REVIEW_이며 전역 REVIEW_V2는 불변이었다. facts의 evidence.claim_id, judgment evidence.claim_id, judgment_id와 결론에는 이 pattern이 전파되지 않는다. 모델이 선택한 새 fact ID와 기존 fact를 참조하는 evidence를 구분한다. suffix의 의미나 내용은 코드가 만들지 않는다.

B와 A0가 같은 compact_v2 schema·설명·최종 namespace·검증기를 사용한다. runner의 extraction, gateway REGISTER_BATCH, 구조 보정 경로가 wire version을 고르며 v1도 별도 경로로 유지된다. config는 condition 외 모두 동일하고 0.4.3-dev다. 입력800,000·출력24,000·단일 탐색9,000·시간900초·모델24·도구40·비용상한1.25달러는 v042와 같다. A0의 검색·등록·계산·민감도 순서와 의미상 선택을 프로그램이 새로 지정하지 않는다. 따라서 이 변경은 공통 전송 계약의 사용성 보완이며 A1의 자동 판단·경로 개입으로 분류하지 않는다.

공통 프롬프트의 실제 grouped synthetic JSON을 v2 expander로 확장·등록했다. 8개 논리 레코드, MARKET_CAP 출력100, 원래 가정·입력·결과가 유지됐다. 기업별 정답이나 진단 답변은 예시에 없다.

관련 tests의 첫 실행은116통과·6실패였다. 실패는 구형 synthetic 응답의 최종 claim IDs가 새 접두어 계약을 따르지 않았기 때문이며, 값을 바꾸는 자동 수정으로 통과시키지 않았다. fixture가 실제 schema에 맞는 ID와 근거 참조를 생성하고 compact_v1/v2 양 경로를 검증하도록 갱신된 뒤, wire v1/v2·remediation integration·gateway·contracts 관련 **131개가 통과**했다. synthetic 시험과 실제 모델의 계약 준수는 다르므로 실제 제출·현재 snapshot 산술·민감도·원문 의미는 후속 배치에서 확인한다.

남는 위험은 모델이 실제로 다른 기준의 입력을 같은 group에 선언할 수 있다는 점이다. 계산 성공은 그 선언이 경제적으로 맞다는 인증이 아니다. 반대로 모델이 같은 기준을 별도 group의 서로 다른 문구로 선언하면 여전히 INVALID가 가능하다. 두 경우 모두 raw 선언과 원문을 대조하고, 원본을 수정하거나 정답을 자동 주입하지 않는다.
