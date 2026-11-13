# v0.4.3 구현 2차 후속 검토

판정: **PASS_OFFLINE_AFTER_REPAIR**. compact_v2 group 참조, 최종 fact claim namespace, 실제 B/A0 경로와 형식 patch·예산·격리 보존을 독립 검토했다. production source 수정과 API 호출은 없다. tests/report만 추가·갱신했으며 최종 실제 배치와 전체 검토는 대기다.

group은 모델이 id/t/s/b/src를 선언하고 CONTEXT는 id/u/p/g로 참조한다. adapter는 지정 group의 as_of/scope/basis/source_snapshot_id 문자열을 그대로 확장한다. 문자열 trim, 의미 유사성 판단, 날짜 추정, 값 선택은 하지 않는다. 서로 다른 날짜·scope·basis·source tuple은 별도 group이고, unit과 이익기간은 context별로 보존된다. 실제 같은 비교 기준인지 판단하는 책임은 모델·검토자에게 있으며 group 공유가 경제적 적합성을 인증하지 않는다.

기존 extraction_v2 전체 payload, notes/limits, snapshot ID와 계산 결과의 round-trip 동등성을 확인했다. encoder만 정확히 같은 4개 문자열 tuple을 dedup한다. 서로 다른 group 이름의 같은 tuple을 expand할 때는 선언대로 복사한다. 임의 group 이름과 사용하지 않는 유효 group 선언의 wire round-trip 동일성은 보장하지 않으며 원본 wire 로그에 보존한다. unused group은 논리 CONTEXT나 새 fact를 만들지 않는다. 중복 group ID·없는 g·필수키 오류·불법 context override는 실패하고, 실제 read 외의 증거 좌표도 생성하지 않는다.

새 namespace는 현재 등록 claim ID가 사용하지 않는 REVIEW_/REVIEW2_/… prefix를 모델 생성 전에 schema에 명시한다. 모델이 새 fact ID와 본문을 생성하며 프로그램은 답변을 받은 후 rename하지 않는다. judgments[].facts[].claim_id leaf만 새 객체로 교체하고 ASCII suffix와 160자 제한을 적용한다. REVIEW_OLD·REVIEW2_OLD를 등록한 독립 검증에서 REVIEW3_을 선택했고 등록 사실·전역 REVIEW_V2·다른 text/doc/evidence claim schema는 바뀌지 않았다. 반환 schema를 바꿔도 다음 반환값은 오염되지 않는다.

형식 patch는 group id/t/s/b/src, context g/u/p, VALUE·최종 fact의 claim 선언을 삭제·재연결하지 못한다. 날짜를 정수화하거나 누락 group 기준을 null/빈배열/빈객체로 채우는 것도 거절한다. 기존 선언을 가리키는 evidence claim 연결만 허용된다. 등록 사실·수치·판단·상태·출처가 보정 과정에서 바뀌지 않는다.

B/A0의 실제 runner가 compact_v1과 compact_v2를 모두 처리하고 새 동적 prefix를 사용하는 통합 회귀를 확인했다. 외부 compact chunk는 fatal, 같은 corpus 미열람 chunk는 UNREAD로 구별하며, B도 fatal 오류 후 repair API를 더 쓰지 않는다. fixture가 v2 wire를 다시 생성하면서 테스트용 foreign mutation을 덮어쓰거나 옛 _review 인자 수를 쓰던 오류는 fixture에서만 수정했다. 생산 격리 결함으로 보고하지 않는다.

관찰 결과 전체와 상태 예약은 유지된다. B의 3×추출 한도는 계획상 allowance이고 수학적 상한이 아니다. 실제 최종 요청 직전에 다시 검사한다. 독립 B 통합 테스트에서 응답의 실제 입력 usage가 예측보다 크면 등록·EVAL·sensitivity 결과는 보존하고 review 요청 전 INPUT_RESERVATION으로 종료했다(model_calls=1, review API 0). group 내용을 줄이거나 자동 계산·전처리를 추가해 예산을 맞추지 않았다.

초기 group/patch 검증 61개, 이후 group·namespace·양 wire runner·격리·patch 검증 **103개가 12.46초에 통과**했다. 이 집합들은 중복되므로 합산하지 않는다. 공통 synthetic 예시도 실제 새 wire2 expander와 SnapshotStore에 등록해 P/S 원입력과 M=100의 파생값이 그대로임을 확인했다.

기존 원본 baseline과 완료 진단·중단·probe 잠금은 유지한다. FIX_v042의 3 SUBMITTED·1 FAILED·8 NOT_STARTED 및 수치 미완료는 소급 변경하지 않는다. 제출 성공·구조 적합성·실제 숫자 계산·근거 내용·F/K/J 정확도는 서로 다른 판정이다. 새 group 계약과 namespace가 실제 12회 모두를 성공시키는지는 최종 동결 배치에서 확인해야 한다.
