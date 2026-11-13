# 실패 보완 통합 2차 검토

2026-11-13 · contracts 교차 검토 · **PASS_AFTER_REPAIR**

B/A0 runner·gateway·agent loop의 신규 compact/patch/dynamic schema 경로를 검토하고 실제 gateway를 쓰는 모의 통합 테스트11개를 작성했다. 등록→계산→제출, 원본 wire 인자·reasoning·call_id 보존, 검색과 열람의 구별, 기준표 격리, snapshot별 missing_inputs, 등록/최종 형식수정 성공과 의미수정 거절을 확인했다. compact patch 보완 단위32개를 함께 실행해 **43 passed**다.

수정한 연결 문제는 네 가지다. compact claim 연결을 최초 patch가 인식하지 못해 schema상 values/derivations의 기존 c와 ev[].claim 경로에 한정해 보완했다. runtime 사용량 예약의 새 속성명을 state가 읽도록 root가 수정했다. 추가된 envelope.state를 사전 관찰 예산 측정에 넣고 향후 ID·registry 증가 여유를 기록하도록 root가 보완했다. 독립 검토자가 지적한 코퍼스 밖 compact chunk는 fatal 격리 위반으로 차단하며 같은 코퍼스의 미열람 근거와 구별한다.

마지막 통합 테스트는 실제 예산 추정 payload에 전체 envelope/state/result가 포함되고 observation_state_reservation 기록이 남는지 확인했다. 형식수정이 계산값999를 허용된 결과10으로 고치려는 시도는 실패하고 review 파일도 만들지 않는다. 숫자나 판단을 수정해 성공한 것처럼 처리하지 않았다.

본 검토에서 API를 호출하지 않았다. mock 성공은 실제 기업 답변의 정확도나 공백 반복 해소 증거가 아니다. gateway/runner/loop는 독립 검토였고 compact patch 추가 부분은 이 검토자가 구현했으므로 별도 preservation_review의 독립 검토와 root 최종 검토를 함께 사용한다. 전체 회귀 재실행과 실제 진단 실행은 root의 동결 단계에서 수행한다.

[상세 검사·지적·파일 해시](integration_review_2.json) · [compact 구현 자체검토](compact_wire_review_1.md)
