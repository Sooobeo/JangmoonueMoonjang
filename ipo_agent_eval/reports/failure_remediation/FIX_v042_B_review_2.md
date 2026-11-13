# FIX_v042 B 실행 독립 2차 검토

COMPLETE

AI 비블라인드 보조 검토이며 인간 검토는 미완료다. 실행 원본·동결 코드·gold는 변경하지 않았다. 실행·계산 사용·회사별 K1~K3와 구조화 사실 근거를 확인하며, 제출 성공을 전체 방법론 정답으로 간주하지 않는다.

## HDMS-DEV-01

REVIEWED_WITH_INCOMPLETE_CALCULATIONS

20261113T113352Z_B_c3487bd1: SUBMITTED / PENDING_INFO

최종 계산 사용 {'USE': 11, 'REJECT': 7}; 현재 snapshot/결과 일치 18/18. 계산 상태 {'OK': 17, 'UNAVAILABLE': 5, 'INVALID': 11}.

- K1: 1점. 40,000,000+4,450,000+13,510+406,680=44,870,190주; 구주 제외 명시, share_sum 실제 USE.
- K2: 0점. 공시 평가액/분모 나눗셈이 basis 불일치로 INVALID이며 답변은 REJECT하여 미제출.
- K3: 0점. 이익×PER/분모 및 모든 주당 민감도가 scope 불일치로 INVALID. PER 평균/중앙값 자체 계산만 제시해 주당 재현/차이 미제출.

구조화 사실 12개: FULL 12, QUALIFIED 0, UNSUPPORTED 0; FULL/제출 사실 지지율 1.0. 전체 결론 정확도를 뜻하지 않는다.

| 주장 | 판정 | 근거 |
|---|---|---|
| J1-F1 | FULL | p331 적용 순이익·p424~425 기간/연결 지배귀속과 일치. |
| J1-F2 | FULL | p331 비교기업 온기 지배순익 주석과 일치. |
| J1-F3 | FULL | p331 회계/연결 범위 비교 제약 문구에 일치. |
| J2-F1 | FULL | p311 최종 네 기업·p331 개별 PER 일치. |
| J2-F2 | FULL | p312 신조/자산구조 및 해외3사 AM 외 장비제조 설명에 일치. |
| J2-F3 | FULL | p229 단계적 선정 기준과 p312 HD한국조선해양 사업 선정 이유 일치. |
| J2-F4 | FULL | p330 주가 최소값·공시 환율 변환 주석과 일치. |
| J3-F1 | FULL | p330~331 비교방법 및 산술평균31.5 설명과 일치. |
| J3-F2 | FULL | p312 신조·서비스 사업차이 설명과 일치. |
| J4-F1 | FULL | p332 구주 제외·두 옵션 합산·총수에 일치. |
| J4-F2 | FULL | p332 평가액·확정공모가 구별 정확. |
| J4-F3 | FULL | p41/42 전후 표의 동일 평가입력과 확정가 추가, p298 현재 본문을 구분. |

- canonical share_count 선택은 이번에 정상 등록됐으나 입력 CONTEXT 자유문구가 달라 가격/민감도 호환성 검사를 통과하지 못했다. 이익scope는 연결 지배귀속, 다른 issuer scope는 지배귀속평가, shares basis는 공모후잠재주식, 다른 basis는 상대가치산정으로 선언됐다. 공시 숫자 오류와 구분한다.
- 모든 주당 민감도 INVALID이며 최종도 이를 REJECT했다. 실제 민감도 계산·사용 완료의 수락 조건은 충족하지 않는다. SUBMITTED/PENDING_INFO는 산술 완료를 뜻하지 않는다.
- 공시 현지통화/환율 자료는 있지만 FX 변환 표현 미지원 때문에 해외 원화주가 미해결 및 R1 blocking이 남았다. R2는 내부 CONTEXT 재검토·새snapshot 계산을 외부 요청으로 넘겼다.
- 원문 기준이 실제 다르면 강제 통일해서는 안 되며, 이 검토에서 입력이나 결과를 자동 교정하지 않았다.

[원본 답변](../../runs/20261113T113352Z_B_c3487bd1/review.json), [계산](../../runs/20261113T113352Z_B_c3487bd1/calculations.json), [열람 원문](../../runs/20261113T113352Z_B_c3487bd1/source_packet.json). 상세 검증과 SHA-256은 동명 JSON에 보존했다.

## MELCON-DEV-01

REVIEWED_FAILURE

20261113T113649Z_B_13f17aec: FAILED / None

GLOBAL_CLAIM_ID_REDECLARATION: Final review declaration IDs F_E/F_S/F_SA/F_V collide with existing extraction claim IDs. Review-internal IDs are unique. Raw response completed; semantic-preserving empty format patch did not change declarations, so INVALID_REVIEW remains.

구조화 사실 0개: FULL 0, QUALIFIED 0, UNSUPPORTED 0; FULL/제출 사실 지지율 None. 전체 결론 정확도를 뜻하지 않는다.

| 주장 | 판정 | 근거 |
|---|---|---|

- 미제출필수 F/K/J는 protocol11.1에 따라0, final_status와 최종내용오류/잘못된완료/불필요보류 flag는 null. 원본 raw 수치가 있어도 성공 제출 점수로 소급 처리하지 않았다.
- 추출의 사실을 최종에서 같은 claim_id로 다시 선언해 기존 글로벌 namespace 규칙에 충돌했다. source숫자 오류나 USE분기 오류와 구분한다.

[원본 답변](../../runs/20261113T113649Z_B_13f17aec/review.json), [계산](../../runs/20261113T113649Z_B_13f17aec/calculations.json), [열람 원문](../../runs/20261113T113649Z_B_13f17aec/source_packet.json). 상세 검증과 SHA-256은 동명 JSON에 보존했다.

## DTS-DEV-01

REVIEWED_NOT_STARTED

## SHINSUNGST-DEV-01

REVIEWED_NOT_STARTED

## ALT-DEV-01

REVIEWED_NOT_STARTED

## MILLIE-DEV-01

REVIEWED_NOT_STARTED

F/J 전항목은 제출 실행에서 미채점이며 null이다. 실패 미제출이면 protocol 11.1에 따라 필수 F/K/J는 0이다. K1의 산술합계와 최신 전체분모 완전성은 별도로 판단한다. 버전 간 실행 조건 변경 때문에 순수 효과나 최종평가 성과로 해석하지 않는다.
