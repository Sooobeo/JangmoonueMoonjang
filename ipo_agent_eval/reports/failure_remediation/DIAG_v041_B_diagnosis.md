# DIAG v0.4.1 B 실제 실행 진단

AI 비블라인드 보조 검토이며 인간 검토는 미완료다. 원본 실행·동결 코드·gold는 수정하지 않았다. F/J 전항목 채점이 아니라 핵심 3개 산술과 구조화 사실의 출처 적합성을 검토했다.

## MELCON-DEV-01 · 20261113T111430Z_B_3281abe6

SUBMITTED / HUMAN_REVIEW. API 2회, 형식 수정 0회, 재시도 0회. 등록·EVALUATE·민감도 완료. 계산 {'UNAVAILABLE': 2, 'OK': 23}, 최종 사용 {'USE': 15, 'REJECT': 2}; 모든 USE는 현재 snapshot의 OK 결과와 정확히 일치한다.

- K1: 네 공시 구성 독립합 12735000주 = 계산기 partial_sum. 완전 합계는 UNAVAILABLE이며 답변도 확정하지 않았다.
- K2: 14173.30192383195916764821358460934432666원, 독립 재계산 일치.
- K3: 14172.35335689045936395759717314487632509원, 독립 재계산 일치.

Issuer half-year annualized adjusted earnings and peer LTM periods remain distinct. HPSP/WORT entity IDs remain distinct. Common scope/basis labels represent the same disclosed valuation table, not a forced accounting equivalence.
Issuer as_of remains 신고서 제출일(날짜 미확인), although filing metadata provides 2026-09-29. This reduces date specificity; it does not alter the quoted inputs.

구조화 제출 사실 14개 중 실제 읽은 위치 14개, FULL 14, QUALIFIED 0, UNSUPPORTED 0. 근거 지지율은 FULL/제출 사실 = 100%다. 결론 전반 정확도나 투자 적합성의 비율이 아니다.

| claim_id | 쪽 | 원문 대조 |
|---|---|---|
| F_J1_BASE | 372, 491 | p372 반기 지배순익·세전 주식이익 차감·연환산과 p491 원단위 귀속 순익이 일치한다. |
| F_J1_PERIOD | 369, 370 | p369 LTM 기간과 p370 반기 연환산 한계 설명이 일치한다. |
| F_J1_ALT | 371 | p371 LTM 5,988/대손가산 7,578, 세효과 미고려 및 평가가액을 정확히 인용한다. |
| F_J1_LABEL | 372, 492, 371 | p372의 919, p492 평가/처분 손익 원단위, p371의 918 표시를 구별한다. |
| F_J2_SELECTION | 357, 370 | p357 선정 기준과 p370 두 회사 및 배수가 일치한다. |
| F_J2_DIFFERENCE | 363 | p363 장비 역할 차이와 영업이익률을 정확히 인용한다. |
| F_J2_WORT | 367 | p367 워트 경쟁관계 및 현재 반기 매출구성과 일치한다. |
| F_J2_INPUTS | 368, 370 | p368 기준주가 및 p370 주식수·LTM 이익과 일치한다. |
| F_J3_VAL | 372 | p372 적용 이익·PER·분모·평가가치를 정확히 인용한다. |
| F_J3_PEERS | 363 | p363 장비 차이 및 두 PER을 직접 지원한다. |
| F_J3_DENOM | 372, 66 | p372 네 구성과 p66 추가취득 25,000주를 구분한다. |
| F_J4_VERSION | 3, 71, 72 | p3 정정일·사유 및 p71/72 정정 전후 가격을 구분한다. |
| F_J4_SHARES | 126, 372 | p126 상장/옵션 포함 수량과 p372 평가 분모 차이를 보존한다. |
| F_J4_PRIOR | 127, 126 | p127에 남은 종전 수량/가격을 p126 현행 수량과 구분한다. |

남는 한계:

- K1 remains UNAVAILABLE because additional underwriter 25,000 shares are UNRESOLVED. The review explicitly calls 12,735,000 a partial sum, preserving the discrepancy with latest listing/option totals.
- R1 combines a legitimate denominator-intent question with primary/secondary offering information already partly available on read p389. That avoidable information request is not evidence that the entire HUMAN_REVIEW is unnecessary.
- Peer financial statement consolidation scope and hidden rounding rules are not independently verified. 919/918 label and pretax deduction questions remain explicit.

근거: [원본 리뷰](../../runs/20261113T111430Z_B_3281abe6/review.json), [계산](../../runs/20261113T111430Z_B_3281abe6/calculations.json), [열람 원문](../../runs/20261113T111430Z_B_3281abe6/source_packet.json). 파일별 SHA-256은 동명 JSON에 보존했다.

## ALT-DEV-01 · 20261113T111719Z_B_33614eb2

SUBMITTED / HUMAN_REVIEW. API 2회, 형식 수정 0회, 재시도 0회. 등록·EVALUATE·민감도 완료. 계산 {'UNAVAILABLE': 7, 'OK': 25}, 최종 사용 {'USE': 11, 'REJECT': 1}; 모든 USE는 현재 snapshot의 OK 결과와 정확히 일치한다.

- K1: 네 공시 구성 독립합 8960259주 = 계산기 partial_sum. 완전 합계는 UNAVAILABLE이며 답변도 확정하지 않았다.
- K2: 27145.62097457227519874146495095733281817원, 독립 재계산 일치.
- K3: 27136.49944404508842880546198497163977068원, 독립 재계산 일치.

Issuer scope explicitly says mixed earnings and selection reason preserves 2022 Apr-Dec pretax plus 2023Q1 controlling posttax. Peer market-cap as_of 2023-05-18 and earnings as_of 2023-03-31 remain distinct; shared peer context carries separate entity IDs. No cross-company operand mixing observed.
Issuer valuation as_of is unknown. Peer consolidation scope is unknown, correctly retained rather than fabricated.

구조화 제출 사실 12개 중 실제 읽은 위치 12개, FULL 12, QUALIFIED 0, UNSUPPORTED 0. 근거 지지율은 FULL/제출 사실 = 100%다. 결론 전반 정확도나 투자 적합성의 비율이 아니다.

| claim_id | 쪽 | 원문 대조 |
|---|---|---|
| J1F1 | 251 | p251의 두 기간·세전/지배순익 구분과 합계가 일치한다. |
| J1F2 | 251 | p251 법인세이익 배제 취지와 2023Q1 세금비용 반영을 정확히 인용한다. |
| J1F3 | 320 | p320 전체/지배귀속 순익 및 2022Q1 미검토 표시와 일치한다. |
| J2F1 | 245, 247 | p245/247 TTM 흑자·매출 선별 및 시그네틱스 PER 57.1 제외와 일치한다. |
| J2F2 | 246, 132 | p246 비교기업 사업/매출 구성과 p132 발행사 Turnkey 확대가 지원한다. |
| J2F3 | 251 | p251 네 기업 시가총액·순이익·표시 PER을 정확히 인용한다. |
| J3F1 | 251 | p251 적용 입력과 네 PER에 모두 일치한다. |
| J3F2 | 246 | p246 COF·골드범프·기타 매출 비중을 정확히 인용한다. |
| J4F1 | 251 | p251 평가시가총액·분모·평가가액과 일치한다. |
| J4F2 | 252, 106 | p252 네 구성 및 p106 청약미달 시 의무취득 조정을 구별한다. |
| J4F3 | 34, 35 | p34 정정 전과 p35 정정 후 가격을 구분한다. |
| J4F4 | 247, 249, 251 | p247/251 실제 표 간 차이 및 p248~249 천원단위 상세표를 정확히 구별한다. |

남는 한계:

- K1 remains UNAVAILABLE because model declared COVERAGE INCOMPLETE for unconfirmed options/additional/secondary stock despite registering all four disclosed denominator components. The 8,960,259 component sum is independently correct; final review reports only the partial sum. This is an incompleteness/conservative selection issue, not arithmetic failure or runtime breakage.
- Four peer price-times-shares calculations remain UNAVAILABLE (eight explicit unverified inputs); disclosed market-cap divided by earnings PER calculations succeed.
- Mixed pretax/posttax and controlling-scope treatment warrants the stated human review. Missing hidden precision and the observed Doosan table discrepancy are not silently repaired.

근거: [원본 리뷰](../../runs/20261113T111719Z_B_33614eb2/review.json), [계산](../../runs/20261113T111719Z_B_33614eb2/calculations.json), [열람 원문](../../runs/20261113T111719Z_B_33614eb2/source_packet.json). 파일별 SHA-256은 동명 JSON에 보존했다.

실행 조건이 달라 이전 버전 대비 순수 효과로 단정하지 않는다. 실제 제출 성공과 산술 정상화를 확인했으며, 분모 완전성·추가 정보 요청의 적절성은 별도 후속 검토 사항이다.
