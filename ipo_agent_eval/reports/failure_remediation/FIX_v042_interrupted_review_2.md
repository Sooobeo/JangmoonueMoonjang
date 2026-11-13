# FIX_v042 중단 배치 2차 감사

판정: 중단 기록 감사 완료. 최종 acceptance가 아니다.

계획 12회 중 실제 시작 4회, 미실행 8회다. 결과표는 complete=false와 각 미실행 처분을 유지한다. 실제 상태는 {'SUBMITTED': 3, 'FAILED': 1, 'NOT_STARTED_STOP_REQUESTED': 8}다.

| 기업/조건 | 등록 records | 현재 EVALUATE OK | 현재 sensitivity OK | 감사 |
|---|---:|---:|---:|---|
| HDMS-DEV-01/B | 92 | 17 | 0 | 수치 완료 조건 미충족 |
| HDMS-DEV-01/A0 | 73 | 24 | 7 | 개별 실행 검사 통과 |
| MELCON-DEV-01/B | 59 | 10 | 0 | 수치 완료 조건 미충족 |
| MELCON-DEV-01/A0 | 51 | 20 | 5 | 개별 실행 검사 통과 |

HDMS B는 canonical 분모 선택과 값이 있었지만 IE/IP/IS의 scope·basis 자유문자열이 서로 달라 주당가액과 sensitivity가 INVALID였다. 모델이 제출한 다른 비교 기준을 코드가 임의로 통일하지 않고 원래 오류 결과를 보존했다. 후속 group 참조 계약이 이 기록을 소급해 성공으로 바꾸지 않는다.

알려진 표준 비캐시 요율 추정 합계는 $1.943268, usage_unknown 실행은 0개다. 청구액이나 보수 예약 ceiling과 같다고 주장하지 않는다. 미실행 8회는 성능 점수 null이며 실패 답변으로 세지 않는다.

plan/results·동결 source·네 raw run의 164개 파일을 별도 immutable manifest로 잠갔다. 기존 497개 진단/중단/probe 잠금은 바꾸지 않았다. 세부 오류·원시 비용·미실행 목록은 FIX_v042_interrupted_review_2.json에 있다.
