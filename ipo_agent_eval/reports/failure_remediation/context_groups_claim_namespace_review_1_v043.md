# v0.4.3 1차 검토 — context group과 최종 주장 namespace

판정: **PASS_AFTER_TEST_FIXTURE_REPAIR**. 유료 API 호출 없이 관련 회귀 **150개 통과(14.33초)**.

FIX_v042 HDMS B에서는 숫자 입력이 있었지만 context의 scope/basis/as_of 문구가 달라 주당가치·민감도가 INVALID였다. compact_v2는 같은 비교기준이라고 모델이 판단한 context만 같은 group을 참조하도록 한다. 기존 strict 계산 비교는 유지한다. 실제로 다르거나 미확인인 기준을 자동으로 합치지 않는다.

FIX_v042 MELCON B의 최종 신규 fact는 등록된 추출 주장 F_E/F_S/F_SA/F_V를 재정의해 거절됐다. 이제 최종 facts의 claim_id 선언 leaf에만 등록 주장과 겹치지 않는 REVIEW_ 계열 prefix와 비어 있지 않은 suffix 규칙을 노출한다. 모델 응답을 사후 rename하지 않으며 evidence·judgment·다른 문자열과 boolean leaf는 바꾸지 않는다.

검증은 전체 record 종류의 payload·Decimal 문자열·snapshot ID·계산 결과 동등성, exact tuple만 dedup, unit/period 보존, batch-local/undefined/duplicate/unused 경계, 증분 등록, B/A0 양조건의 compact_v1/v2 등록→계산→제출, 원본 wire 로그, 실제 read 격리·원자성, 기존 claim 충돌 회피, schema alias 불변, 형식 patch의 의미 변경 거절을 포함한다.

unused valid group은 원본 로그에 남지만 참조 context가 없으면 내부 record를 생성하지 않는다. 무손실 보장 범위는 extraction_v2 payload·snapshot·계산이며, 임의 group 이름 또는 unused dictionary를 다시 인코딩했을 때 같은 wire JSON으로 돌아오는 것은 보장하지 않는다.

첫 통합 mock은 이전 R_J1 ID를 생성해 거절됐으므로 실제 스키마 prefix를 읽도록 fixture만 고쳤다. suffix 강화 전 패턴을 기대한 독립 테스트 1개도 별도 검토자에게 갱신 요청했다. Python JSONSchema의 `$`가 마지막 개행 앞을 허용하는 점은 제약의 한계로 남겼으며, 지원 여부가 불분명한 정규식을 추가하지 않았다.

이 결과는 실제 API 실행 성공이나 금융 판단 정확도의 입증이 아니다. 모델이 비교기준 동등성을 판단해야 하고, 신규 사실 사이의 고유 ID도 계속 validator가 확인한다. 기존 실제 실행 원본과 평가는 수정하지 않았다. 상세 명령·범위·시점별 SHA-256은 동명의 JSON에 기록했다.
