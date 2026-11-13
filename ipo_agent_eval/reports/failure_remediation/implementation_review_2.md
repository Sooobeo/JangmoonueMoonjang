# 실패 보완 구현 검토 2

판정: 핵심 계약·통합은 통과했으며 **B 격리 위반 직후 repair 호출 중단 1건은 v0.4.1 수정 대기**다. 실제 실행 성공 판정이 아니다.

compact 변환은 7종 payload 전 필드를 일대일로 보존한다. doc/page는 실제 열람 chunk 좌표에서만 복원하고, 값·기간·단위·선택·포함 상태를 추론하지 않는다. round-trip snapshot과 계산 결과 동일성, 미열람 근거 거절, 중복 ID·잘못된 파생값 거절을 확인했다.

patch는 schema상 여분 키 삭제, 누락 빈필드 추가, page/version의 동일 정수화, 이미 선언된 claim에 대한 증거 연결만 허용한다. compact claim 선언과 ev 경로도 schema와 실제 경로로 제한한다. 배열 구성·수치·본문·판단·요청 상태·출처 변경은 실패하며 원본/patch/적용 결과와 raw API 기록을 보존한다. 초기 patch와 runtime은 검토자 본인 구현이므로 이 부분은 자기 검토이고, contracts가 보완한 compact 경로와 root 통합은 독립 검토다.

root 통합에서 B/A0 공통 설정은 condition 외 차이가 없다. 상태는 현재 snapshot·ID·ledger·예산 관측이며 A0의 다음 행동을 자동 선택하지 않는다. 관측 전 예약에 envelope·현재 상태·상태 증가 여유를 포함하며, 최종 호출 직전 전체 요청을 재계산한다. missing_inputs는 등록된 UNRESOLVED 정확 집합을 명시하고 원래 서버 검증을 유지한다. 빈 배열이 업무 완료를 뜻하지 않는다.

HTTP500/502/503/504만 같은 요청을 최대 1회 재시도한다. 매 시도는 model_calls·request·오류 로그에 남고 unknown usage는 별도 입력 추정/최대 출력/비용 예약으로 누적된다. 재시도 전 여섯 예산을 다시 검사하며 400·quota·refusal·incomplete를 재시도하지 않는다. 로그는 읽기 좋은 JSON, 모델용 새 payload와 토큰 추정은 compact JSON을 쓴다. 알려진 비용과 unknown 예약 및 실제 청구액은 구별한다.

독립 검토에서 compact의 외부 chunk 오류가 fatal로 분류되지 않음을 발견했다. root가 DIAG 동결 전에 수정했고, 같은 corpus 미열람 구별·상태 원자성·fatal 지속을 추가 검증했다. 관련 96개 테스트가 8.48초에 통과했다.

남은 IR2-02: B run_fixed는 fatal REGISTER/COMMIT 오류에도 format repair API를 1회 더 시도한다. 정보 접근과 제출은 계속 막히며 불필요 호출의 문제다. v032에도 있었던 경로이고 live 동결 중이므로 수정하지 않았다. root가 DIAG 4회 뒤 v0.4.1 수정으로 결정했다. 독립 테스트는 3 pass, 2 strict xfail로 현재 결함을 명시한다. 수정 뒤 xfail을 제거하고 재검증해야 한다.

기존 증거 1,847개와 소스/설계 복사 67개, 총 1,914개 보존 검사에 위반은 없다. 세부 해시·범위·테스트·보완 상태는 [implementation_review_2.json](implementation_review_2.json), 보존 결과는 [implementation_review_2_preservation.json](implementation_review_2_preservation.json)에 있다. 이 검토에서 API를 호출하거나 이전 보고서를 수정하지 않았다.
