# 멜콘 B 검토 결과

이 문서는 API가 제출한 검토 의견과 프로그램의 계산 결과를 옮긴 것이다. 정답 채점은 아직 하지 않았다.

- 실행 ID: 20261113T043350Z_B_2f186feb
- 자료 마감: 2026-09-29T23:59:59+09:00
- 프로그램이 정한 상태: PENDING_INFO
- AI가 보고한 상태: PENDING_INFO

## 확인 범위

- 2026-09-29 자료 마감 전에 제공된 투자설명서의 실제 수신 쪽만 검토했다. 추가 검색이나 독립 원자료 대조는 하지 않았다.
- 비교기업의 재무수치·주가·주식수는 투자설명서 인용값이다. 표시 전 원수치와 반올림 규칙은 확인하지 못했다.

## 핵심 메모

- 정정 후 확정 공모가 12,300원과 할인 전 주당 평가가액 14,173원은 서로 다른 값이다.
- 표시 입력으로 재계산한 평가가액은 약 14,172원이다. 소액 차이만으로 공시 오류라고 판단하지 않는다.
- 멜콘 반기 연환산·조정 이익과 비교기업 LTM 이익의 기간 및 조정 차이를 감안해야 한다.
- HPSP와 멜콘의 제품 역할 차이가 크며, HPSP 제외 가정의 평가가액은 약 9,446원이다.
- 우선 정정 후 주식수와 평가 분모의 관계 및 비교기업 표시 전 원수치를 확인한다.

## J1 · CONDITIONAL

지배주주 귀속 이익을 사용하는 범위는 대체로 맞지만, 멜콘은 반기 연환산·일회성 이익 조정치를, 비교기업은 LTM 이익을 사용한다. 조정과 기간 차이를 감안한 조건부 비교가 적절하다.

- 공시상 적용 이익은 2026년 반기 지배주주순이익 4,366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배한 6,894백만원이다. 연결손익계산서의 반기 지배지분 순이익은 4,365,970,787원이다. (MELCON-PROS-01 PDF 372쪽 · PER에 의한 평가가치 표와 주1; MELCON-PROS-01 PDF 491쪽 · 연결 포괄손익계산서, 당기순이익의 귀속)
- 비교기업 PER에는 2025년 3분기~2026년 2분기 LTM 순이익을 사용하며, 연결재무제표 작성 법인은 지배주주 귀속 이익을 사용한다. 공시는 반기 연환산이 하반기에도 상반기와 같은 실적을 전제한다고 설명한다. (MELCON-PROS-01 PDF 370쪽 · 비교기업 PER 산출 표와 주1; 연환산 한계)
- 공시는 주식 처분이익을 주된 사업과 무관한 일회성 이익으로 설명한다. 반면 세후 순이익에서 세전 이익 전액을 차감하며 법인세효과는 반영하지 않았다. (MELCON-PROS-01 PDF 373쪽 · 거래의 개요 및 제외 결론)
- 공시의 LTM 대안은 주식 처분이익 차감 후 5,988백만원이고, 2025년 대손상각비 1,590백만원을 세금효과 없이 가산하면 7,578백만원이다. 반기 연환산 기준은 두 값 사이에 있다. (MELCON-PROS-01 PDF 371쪽 · 적용 실적 기준별 재무수치 및 주당 평가가액 비교)

판단을 뒷받침하는 원문:

- MELCON-PROS-01 PDF 372쪽 · PER에 의한 평가가치 표와 주1 (주장 R_J1_1)
- MELCON-PROS-01 PDF 370쪽 · 비교기업 PER 산출 표와 주1 (주장 R_J1_2)

반대 근거로 검토한 원문:

- MELCON-PROS-01 PDF 371쪽 · 적용 실적 기준별 비교와 세금효과 주석 (주장 R_J1_4)

아직 확인하지 못한 점:

- 비교기업 LTM 이익에 포함된 비경상 손익과 법인세효과를 동일한 방식으로 조정할 수 있는 독립 원자료는 받지 못했다.
- 반기 실적을 두 배한 결과가 실제 연간 실적으로 이어질지는 알 수 없다.

다음 행동: 기간과 조정의 비대칭을 유지한 조건부 판단으로 기록하고, 비교기업 조정 내역을 확인한다.

## J2 · CONDITIONAL

워트와 HPSP는 반도체 전공정이라는 공통점이 있으나, HPSP는 제품 역할과 수익성이 크게 다르다. 두 기업의 산술평균은 참고 배수로 조건부 사용하되 HPSP 의존도를 별도로 보여야 한다.

- 공시는 분석기준일 2026-08-14에 산업·재무·사업·일반 유사성을 거쳐 워트와 HPSP를 선정했다. 사업 기준에는 온·습도 관련 제품·서비스 매출 비중 50% 이상과 전공정 적용이 포함된다. (MELCON-PROS-01 PDF 357쪽 · 비교기업 선정 기준표)
- 멜콘의 2026년 반기 별도 매출은 THC 60.7%, XPS 17.1%이고, 워트의 2025년 매출은 THC 73.02%다. HPSP의 2025년 매출은 고압수소 어닐링장비 89.1%다. 공시는 HPSP도 사업유사성 기준을 충족한 것으로 표시한다. (MELCON-PROS-01 PDF 360쪽 · 3차 사업 유사성 설명; MELCON-PROS-01 PDF 361쪽 · 3차 비교기업 선정 표, HPSP와 워트)
- 멜콘은 트랙 설비에 부속되어 공정 환경을 지원하지만 HPSP는 독립적인 어닐링 공정을 수행한다. 2026년 반기 영업이익률은 각각 16.5%와 56.9%이며, 공시 PER은 워트 17.45배, HPSP 34.92배다. (MELCON-PROS-01 PDF 363쪽 · 동사와 HPSP의 주요 차이점 및 PER 편차)
- 공시의 비교기업 PER 입력은 HPSP 이익 85,727백만원·주식수 82,300,000주·기준주가 36,373원, 워트 이익 5,098백만원·주식수 16,120,000주·기준주가 5,517원이다. 이익 행의 개별 단위는 백만원이다. (MELCON-PROS-01 PDF 370쪽 · 2026년 2분기 기준 비교기업 PER 산출 표)

판단을 뒷받침하는 원문:

- MELCON-PROS-01 PDF 363쪽 · 동사와 HPSP의 주요 차이점 (주장 R_J2_3)

반대 근거로 검토한 원문:

- MELCON-PROS-01 PDF 365쪽 · HPSP 사업 현황과 전공정 사업모델의 유사성 설명 (주장 J2)
- MELCON-PROS-01 PDF 361쪽 · 3차 비교기업 선정 표 (주장 R_J2_2)

아직 확인하지 못한 점:

- HPSP의 어닐링 매출이 온·습도 관련 매출 50% 기준에 포함되는 구체적 분류 근거는 제공된 표만으로 충분히 확인하기 어렵다.
- 각사의 매출 구성과 LTM 이익을 비교기업의 독립 원자료로 직접 대조하지 못했다.

다음 행동: HPSP의 기능적 유사성과 선정 기준 적용을 확인하고, 단일 기업 배수 민감도를 함께 제시한다.

## J3 · CONDITIONAL

공시 입력을 재계산하면 평가가액은 약 14,172원이며, 표시 정밀도 때문에 공시 14,173원과 약 0.65원 차이가 난다. 비교기업 선택과 적용 이익의 변화는 이보다 훨씬 큰 영향을 준다.

- 공시는 적용 이익 6,894백만원, PER 26.18배, 평가액 180,497백만원, 적용주식수 12,735,000주, 주당 평가가액 14,173원을 제시한다. 주식수는 기발행 10,000,000주 + 공모 신주 2,500,000주 + 의무인수 75,000주 + 선택권 160,000주다. (MELCON-PROS-01 PDF 372쪽 · PER에 의한 평가가치 및 적용주식수 내역)
- 재계산: 6,894 × 26.18 = 180,484.92백만원이고, 이를 12,735,000주로 나누면 14,172.35원이다. 공시 평가액 180,497백만원을 나누면 14,173.30원이다. 표시된 개별 PER 평균은 26.185배로, 공시 적용 배수 26.18배와 원수치·처리 정밀도가 다를 수 있다. (MELCON-PROS-01 PDF 372쪽 · PER에 의한 평가가치 표; MELCON-PROS-01 PDF 370쪽 · 비교기업 PER 산출 표)
- 계산상 가정: 이익과 주식수를 유지하고 HPSP를 제외해 워트의 17.45배만 적용하면 9,446원으로 기준 재계산값 대비 약 4,726원(-33.3%)이다. 반대로 워트를 제외하고 HPSP의 34.92배만 적용하면 18,904원으로 약 4,731원(+33.4%)이다. 어느 기업을 반드시 제외해야 한다는 뜻은 아니다. (MELCON-PROS-01 PDF 370쪽 · 비교기업 개별 PER; MELCON-PROS-01 PDF 372쪽 · 적용 이익과 주식수)
- 공시의 이익 기준 대안은 주당 평가가액으로 LTM 12,310원(-13.1%), 대손상각비를 가산한 LTM 15,579원(+9.9%)이다. 이는 공시 기준안 14,173원 대비이며, 세금효과를 고려하지 않은 대안이다. (MELCON-PROS-01 PDF 371쪽 · 적용 실적 기준별 주당 평가가액 비교와 주3)
- 표시된 두 PER의 평균과 중앙값은 모두 26.185배다. 이를 그대로 적용하는 계산상 가정은 14,175.06원으로 26.18배 기준 재계산값보다 2.71원 높다. 두 기업뿐이므로 중앙값은 집중도 문제를 없애지 못한다. (MELCON-PROS-01 PDF 370쪽 · 비교기업 개별 PER; MELCON-PROS-01 PDF 372쪽 · 적용 이익과 주식수)

판단을 뒷받침하는 원문:

- MELCON-PROS-01 PDF 372쪽 · PER에 의한 평가가치 및 적용주식수 (주장 R_J3_1)
- MELCON-PROS-01 PDF 370쪽 · 비교기업 개별 PER (주장 R_J3_3)

반대 근거로 검토한 원문:

- MELCON-PROS-01 PDF 371쪽 · 실적 기준별 대안 (주장 R_J3_4)

아직 확인하지 못한 점:

- 평가액과 배수의 표시 전 정밀도 및 처리 규칙은 확인되지 않아 소액 차이의 정확한 원인을 확정할 수 없다.
- 민감도는 나머지 입력을 고정한 가정이며 적정 공모가 예측이 아니다.

다음 행동: 공시값과 표시값 재계산 차이를 병기하고 원수치 확인 전 공시 오류로 단정하지 않는다.

## J4 · REQUEST_INFO

정정 후 확정 공모가는 12,300원이고 할인 전 평가가액 14,173원과 다르다. 산정표는 재현 가능하나 정정 후 상장예정주식수와 평가표 분모의 관계, 비교기업 원수치는 추가 확인이 필요하다.

- 물리 71쪽의 주13 정정 전 요약은 희망공모가 10,700~12,300원을 제시한다. 물리 72쪽의 주13 정정 후 요약은 평가가액 14,173원을 유지하면서 공모가 산정 결과와 주당 확정공모가액을 12,300원으로 기재한다. (MELCON-PROS-01 PDF 71쪽 · 주13 정정 전 공모가 산정 요약표; MELCON-PROS-01 PDF 72쪽 · 주13 정정 후 공모가 산정 요약표와 평가결과)
- 공시는 추가 의무인수로 상장예정주식수가 변동되었다고 설명하며 물리 126쪽에 12,600,000주를 기재한다. 반면 평가표는 75,000주 의무인수와 160,000주 선택권을 포함한 12,735,000주를 유지한다. 공모주식 2,500,000주는 전량 신주모집으로 기재되어 구주매출은 없다. (MELCON-PROS-01 PDF 70쪽 · 주12 앞 정정 사유; MELCON-PROS-01 PDF 126쪽 · 상장 이후 유통물량 위험; MELCON-PROS-01 PDF 372쪽 · 평가 적용주식수 내역; MELCON-PROS-01 PDF 389쪽 · 리스크집행위원회 공모 개요)
- 계산상 가정으로 정정 후 상장예정 12,600,000주에 선택권 160,000주를 전량 더하면 12,760,000주다. 다른 입력을 고정하고 표시 이익과 PER을 사용하면 약 14,144.59원으로, 기존 분모 기준 14,172.35원보다 약 27.77원 낮다. 이는 평가표가 실제로 변경되었다는 뜻은 아니다. (MELCON-PROS-01 PDF 126쪽 · 상장예정주식수 및 주식매수선택권 위험; MELCON-PROS-01 PDF 372쪽 · 평가 적용 이익, PER과 주식수)
- 비교기업 시가총액은 수신된 PER 표에 직접 표시되지 않는다. 표의 기준주가와 주식수를 곱한 계산상 값은 HPSP 2,993,497.9백만원, 워트 88,934.04백만원이다. 이는 별도 원자료로 확인한 시가총액이 아니다. (MELCON-PROS-01 PDF 370쪽 · 비교기업 PER 산출 표, 기준주가와 적용주식수)

판단을 뒷받침하는 원문:

- MELCON-PROS-01 PDF 72쪽 · 주13 정정 후 요약 및 확정공모가액 (주장 R_J4_1)
- MELCON-PROS-01 PDF 126쪽 · 상장예정주식수 (주장 R_J4_2)

반대 근거로 검토한 원문:

- MELCON-PROS-01 PDF 372쪽 · 평가 적용주식수 표 (주장 R_J3_1)

아직 확인하지 못한 점:

- 추가 의무인수 25,000주가 기존 평가 분모에 반영되지 않은 이유와 정정 후에도 기존 평가 분모를 유지하는 취지는 확인되지 않았다.
- 공시 인용 비교기업 값과 계산상 시가총액은 독립 원자료 검증을 대신하지 않는다.

다음 행동: 허용 문서의 마감 전 원문에서 정정 후 주식수와 평가표의 적용 시점·관계를 확인하고, 원수치 및 처리 규칙을 요청한다.

## 추가 확인 요청

```json
{
  "requests": [
    {
      "request_id": "REQ-01",
      "question": "마감 전에 이용 가능한 허용 문서 원문에서 정정 후 상장예정주식수 12,600,000주와 평가표의 12,735,000주 적용 시점 및 추가 의무인수 25,000주의 평가 반영 여부를 확인할 수 있는 부분은 어디인가?",
      "why_needed": "발행조건 정정 후에도 기존 평가 분모가 유지된 이유를 판단하기 위해 필요하다.",
      "related_judgment_ids": [
        "J4"
      ],
      "blocking": true,
      "resolution_status": "OPEN",
      "resolution_evidence": []
    },
    {
      "request_id": "REQ-02",
      "question": "HPSP와 워트의 분석기준일 주가·상장주식수·LTM 지배주주순이익의 표시 전 값, 적용 조정 및 배수·평가액 처리 규칙을 확인할 수 있는 마감 전 허용 원문이 있는가?",
      "why_needed": "비교기업 입력과 소수점 처리 차이를 확인하기 위해 필요하다. 독립 원자료 대조에는 허용 범위 확대가 별도로 필요하다.",
      "related_judgment_ids": [
        "J1",
        "J2",
        "J3",
        "J4"
      ],
      "blocking": true,
      "resolution_status": "OPEN",
      "resolution_evidence": []
    },
    {
      "request_id": "REQ-03",
      "question": "HPSP의 고압수소 어닐링장비 매출을 온·습도 관련 제품 매출 50% 이상 기준에 포함한 구체적인 판단 근거가 마감 전 허용 원문에 있는가?",
      "why_needed": "공시의 기능적 유사성과 사업 선정 기준 적용을 함께 평가하기 위해 필요하다.",
      "related_judgment_ids": [
        "J2"
      ],
      "blocking": false,
      "resolution_status": "OPEN",
      "resolution_evidence": []
    }
  ],
  "escalations": []
}
```

## 계산 기록

```json
[
  {
    "calc_id": "share_sum",
    "label": "평가에 사용하는 주식수의 합계",
    "formula": "existing_shares + new_shares + dilutive_shares; secondary_sale_shares is excluded",
    "inputs": [
      {
        "field": "existing_shares",
        "claim_id": "X_EXISTING",
        "value": "10000000",
        "unit": "주",
        "period": "증권신고서 제출일 현재 평가 기준",
        "description": "기발행 보통주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EXISTING",
            "locator": "적용주식수 내역, 기발행보통주식수"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "new_shares",
        "claim_id": "X_NEW",
        "value": "2500000",
        "unit": "주",
        "period": "IPO 공모",
        "description": "공모 신주발행주식수. 표의 상장주선인 의무인수분 75000주는 별도임",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_NEW",
            "locator": "적용주식수 내역, 공모 신주발행주식수"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "dilutive_shares",
        "claim_id": "X_DILUTIVE",
        "value": "160000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "평가 적용주식수에 포함된 주식매수선택권. 상장주선인 의무인수분 75000주는 별도 항목임",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_DILUTIVE",
            "locator": "적용주식수 내역, 주식매수선택권"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "secondary_sale_shares",
        "claim_id": "X_SECONDARY",
        "value": "0",
        "unit": "주",
        "period": "IPO 공모",
        "description": "공모주식 2500000주가 전량 신주모집으로 기재되어 구주매출은 없음",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0389",
            "page": 389,
            "claim_id": "X_SECONDARY",
            "locator": "리스크집행위원회 논의내용, 공모에 관한 사항"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "12660000",
    "unit": "shares",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EXISTING",
        "locator": "적용주식수 내역, 기발행보통주식수"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_NEW",
        "locator": "적용주식수 내역, 공모 신주발행주식수"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_DILUTIVE",
        "locator": "적용주식수 내역, 주식매수선택권"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0389",
        "page": 389,
        "claim_id": "X_SECONDARY",
        "locator": "리스크집행위원회 논의내용, 공모에 관한 사항"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "share_count_difference",
    "label": "주식수 합계와 공시 주식수의 차이",
    "formula": "share_sum - share_count",
    "inputs": [
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "existing_shares",
        "claim_id": "X_EXISTING",
        "value": "10000000",
        "unit": "주",
        "period": "증권신고서 제출일 현재 평가 기준",
        "description": "기발행 보통주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EXISTING",
            "locator": "적용주식수 내역, 기발행보통주식수"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "new_shares",
        "claim_id": "X_NEW",
        "value": "2500000",
        "unit": "주",
        "period": "IPO 공모",
        "description": "공모 신주발행주식수. 표의 상장주선인 의무인수분 75000주는 별도임",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_NEW",
            "locator": "적용주식수 내역, 공모 신주발행주식수"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "dilutive_shares",
        "claim_id": "X_DILUTIVE",
        "value": "160000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "평가 적용주식수에 포함된 주식매수선택권. 상장주선인 의무인수분 75000주는 별도 항목임",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_DILUTIVE",
            "locator": "적용주식수 내역, 주식매수선택권"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "secondary_sale_shares",
        "claim_id": "X_SECONDARY",
        "value": "0",
        "unit": "주",
        "period": "IPO 공모",
        "description": "공모주식 2500000주가 전량 신주모집으로 기재되어 구주매출은 없음",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0389",
            "page": 389,
            "claim_id": "X_SECONDARY",
            "locator": "리스크집행위원회 논의내용, 공모에 관한 사항"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "-75000",
    "unit": "shares",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EXISTING",
        "locator": "적용주식수 내역, 기발행보통주식수"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_NEW",
        "locator": "적용주식수 내역, 공모 신주발행주식수"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_DILUTIVE",
        "locator": "적용주식수 내역, 주식매수선택권"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0389",
        "page": 389,
        "claim_id": "X_SECONDARY",
        "locator": "리스크집행위원회 논의내용, 공모에 관한 사항"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "price_from_reported_equity",
    "label": "공시된 주식가치를 주식수로 나눈 가격",
    "formula": "reported_equity_million_krw * 1000000 / share_count",
    "inputs": [
      {
        "field": "reported_equity_million_krw",
        "claim_id": "X_EQUITY",
        "value": "180497",
        "unit": "백만원",
        "period": "2026년 반기 연환산 평가",
        "description": "PER 평가가치 표의 기업가치 평가액",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EQUITY",
            "locator": "PER에 의한 멜콘의 평가가치, 기업가치 평가액"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "14173.30192383195916764821358460934432666",
    "unit": "KRW/share",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EQUITY",
        "locator": "PER에 의한 멜콘의 평가가치, 기업가치 평가액"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "price_from_displayed_per",
    "label": "이익과 표시 배수로 다시 계산한 가격",
    "formula": "earnings_million_krw * 1000000 * applied_per / share_count",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "applied_per",
        "claim_id": "X_PER",
        "value": "26.18",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "HPSP와 워트의 PER 산술평균으로 공시된 적용 배수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "14172.35335689045936395759717314487632509",
    "unit": "KRW/share",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "reported_price_difference",
    "label": "공시 가치에서 계산한 가격과 공시 가격의 차이",
    "formula": "price_from_reported_equity - reported_price_krw",
    "inputs": [
      {
        "field": "reported_equity_million_krw",
        "claim_id": "X_EQUITY",
        "value": "180497",
        "unit": "백만원",
        "period": "2026년 반기 연환산 평가",
        "description": "PER 평가가치 표의 기업가치 평가액",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EQUITY",
            "locator": "PER에 의한 멜콘의 평가가치, 기업가치 평가액"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "reported_price_krw",
        "claim_id": "X_PRICE",
        "value": "14173",
        "unit": "원",
        "period": "2026년 반기 연환산 평가",
        "description": "할인 전 주당 평가가액. 확정공모가액 12300원과 구분됨",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0077",
            "page": 77,
            "claim_id": "X_PRICE",
            "locator": "주14 정정 후 희망공모가액 결정 표"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "0.30192383195916764821358460934432666",
    "unit": "KRW/share",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EQUITY",
        "locator": "PER에 의한 멜콘의 평가가치, 기업가치 평가액"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0077",
        "page": 77,
        "claim_id": "X_PRICE",
        "locator": "주14 정정 후 희망공모가액 결정 표"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "displayed_price_difference",
    "label": "표시 배수에서 계산한 가격과 공시 가격의 차이",
    "formula": "price_from_displayed_per - reported_price_krw",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "applied_per",
        "claim_id": "X_PER",
        "value": "26.18",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "HPSP와 워트의 PER 산술평균으로 공시된 적용 배수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "reported_price_krw",
        "claim_id": "X_PRICE",
        "value": "14173",
        "unit": "원",
        "period": "2026년 반기 연환산 평가",
        "description": "할인 전 주당 평가가액. 확정공모가액 12300원과 구분됨",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0077",
            "page": 77,
            "claim_id": "X_PRICE",
            "locator": "주14 정정 후 희망공모가액 결정 표"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "-0.64664310954063604240282685512367491",
    "unit": "KRW/share",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0077",
        "page": 77,
        "claim_id": "X_PRICE",
        "locator": "주14 정정 후 희망공모가액 결정 표"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "implied_per",
    "label": "공시된 주식가치에서 거꾸로 계산한 배수",
    "formula": "reported_equity_million_krw / earnings_million_krw",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "reported_equity_million_krw",
        "claim_id": "X_EQUITY",
        "value": "180497",
        "unit": "백만원",
        "period": "2026년 반기 연환산 평가",
        "description": "PER 평가가치 표의 기업가치 평가액",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EQUITY",
            "locator": "PER에 의한 멜콘의 평가가치, 기업가치 평가액"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "26.18175224833188279663475485929794023789",
    "unit": "multiple",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EQUITY",
        "locator": "PER에 의한 멜콘의 평가가치, 기업가치 평가액"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "peer_displayed_mean",
    "label": "비교기업의 표시 배수 평균",
    "formula": "sum(peer.per) / count(peers)",
    "inputs": [
      {
        "field": "peers[0].per",
        "claim_id": "X_HPSP_PER",
        "value": "34.92",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].market_cap_million_krw",
        "claim_id": "X_HPSP_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[0].earnings_million_krw",
        "claim_id": "X_HPSP_EARNINGS",
        "value": "85727",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].per",
        "claim_id": "X_WORT_PER",
        "value": "17.45",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].market_cap_million_krw",
        "claim_id": "X_WORT_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[1].earnings_million_krw",
        "claim_id": "X_WORT_EARNINGS",
        "value": "5098",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "26.185",
    "unit": "multiple",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [
      "REQ-02",
      "REQ-02"
    ],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "peer_displayed_median",
    "label": "비교기업의 표시 배수 중앙값",
    "formula": "median(peer.per)",
    "inputs": [
      {
        "field": "peers[0].per",
        "claim_id": "X_HPSP_PER",
        "value": "34.92",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].market_cap_million_krw",
        "claim_id": "X_HPSP_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[0].earnings_million_krw",
        "claim_id": "X_HPSP_EARNINGS",
        "value": "85727",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].per",
        "claim_id": "X_WORT_PER",
        "value": "17.45",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].market_cap_million_krw",
        "claim_id": "X_WORT_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[1].earnings_million_krw",
        "claim_id": "X_WORT_EARNINGS",
        "value": "5098",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "26.185",
    "unit": "multiple",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [
      "REQ-02",
      "REQ-02"
    ],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "peer_recomputed_per_1",
    "label": "HPSP: 시가총액과 이익으로 다시 계산한 배수",
    "formula": "market_cap_million_krw / earnings_million_krw",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].per",
        "claim_id": "X_HPSP_PER",
        "value": "34.92",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].market_cap_million_krw",
        "claim_id": "X_HPSP_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[0].earnings_million_krw",
        "claim_id": "X_HPSP_EARNINGS",
        "value": "85727",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": null,
    "unit": "multiple",
    "status": "UNAVAILABLE",
    "precision_status": "NOT_CALCULABLE",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      }
    ],
    "missing_reason": "market_cap_million_krw: 입력값이 없습니다.",
    "related_request_ids": [
      "REQ-02"
    ],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "peer_recomputed_per_2",
    "label": "워트: 시가총액과 이익으로 다시 계산한 배수",
    "formula": "market_cap_million_krw / earnings_million_krw",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].per",
        "claim_id": "X_WORT_PER",
        "value": "17.45",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].market_cap_million_krw",
        "claim_id": "X_WORT_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[1].earnings_million_krw",
        "claim_id": "X_WORT_EARNINGS",
        "value": "5098",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": null,
    "unit": "multiple",
    "status": "UNAVAILABLE",
    "precision_status": "NOT_CALCULABLE",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      }
    ],
    "missing_reason": "market_cap_million_krw: 입력값이 없습니다.",
    "related_request_ids": [
      "REQ-02"
    ],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "peer_recomputed_mean",
    "label": "개별 기업에서 다시 계산한 배수의 평균",
    "formula": "mean(peer.market_cap_million_krw / peer.earnings_million_krw)",
    "inputs": [
      {
        "field": "peers[0].per",
        "claim_id": "X_HPSP_PER",
        "value": "34.92",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].market_cap_million_krw",
        "claim_id": "X_HPSP_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[0].earnings_million_krw",
        "claim_id": "X_HPSP_EARNINGS",
        "value": "85727",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].per",
        "claim_id": "X_WORT_PER",
        "value": "17.45",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].market_cap_million_krw",
        "claim_id": "X_WORT_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[1].earnings_million_krw",
        "claim_id": "X_WORT_EARNINGS",
        "value": "5098",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": null,
    "unit": "multiple",
    "status": "UNAVAILABLE",
    "precision_status": "NOT_CALCULABLE",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      }
    ],
    "missing_reason": "일부 기업을 임의로 제외하지 않았습니다. HPSP.market_cap_million_krw: 입력값이 없습니다. / 워트.market_cap_million_krw: 입력값이 없습니다.",
    "related_request_ids": [
      "REQ-02",
      "REQ-02"
    ],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "price_from_recomputed_peer_mean",
    "label": "다시 계산한 비교기업 평균 배수를 적용한 가격",
    "formula": "earnings_million_krw * 1000000 * peer_recomputed_mean / share_count",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].per",
        "claim_id": "X_HPSP_PER",
        "value": "34.92",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].market_cap_million_krw",
        "claim_id": "X_HPSP_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[0].earnings_million_krw",
        "claim_id": "X_HPSP_EARNINGS",
        "value": "85727",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].per",
        "claim_id": "X_WORT_PER",
        "value": "17.45",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].market_cap_million_krw",
        "claim_id": "X_WORT_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[1].earnings_million_krw",
        "claim_id": "X_WORT_EARNINGS",
        "value": "5098",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": null,
    "unit": "KRW/share",
    "status": "UNAVAILABLE",
    "precision_status": "NOT_CALCULABLE",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      }
    ],
    "missing_reason": "일부 기업을 임의로 제외하지 않았습니다. HPSP.market_cap_million_krw: 입력값이 없습니다. / 워트.market_cap_million_krw: 입력값이 없습니다.",
    "related_request_ids": [
      "REQ-02",
      "REQ-02"
    ],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "baseline",
    "label": "공시에 표시된 적용 배수로 계산한 기준 가격",
    "formula": "earnings_million_krw * 1000000 * applied_per / share_count",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "applied_per",
        "claim_id": "X_PER",
        "value": "26.18",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "HPSP와 워트의 PER 산술평균으로 공시된 적용 배수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "14172.35335689045936395759717314487632509",
    "unit": "KRW/share",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [],
    "assumption": null,
    "excluded_peer": null,
    "difference_krw": null,
    "difference_percent": null
  },
  {
    "calc_id": "displayed_mean",
    "label": "비교기업의 표시 배수 평균을 적용",
    "formula": "earnings_million_krw * 1000000 * mean(peer.per) / share_count",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "applied_per",
        "claim_id": "X_PER",
        "value": "26.18",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "HPSP와 워트의 PER 산술평균으로 공시된 적용 배수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].per",
        "claim_id": "X_HPSP_PER",
        "value": "34.92",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].market_cap_million_krw",
        "claim_id": "X_HPSP_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[0].earnings_million_krw",
        "claim_id": "X_HPSP_EARNINGS",
        "value": "85727",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].per",
        "claim_id": "X_WORT_PER",
        "value": "17.45",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].market_cap_million_krw",
        "claim_id": "X_WORT_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[1].earnings_million_krw",
        "claim_id": "X_WORT_EARNINGS",
        "value": "5098",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "14175.06007067137809187279151943462897527",
    "unit": "KRW/share",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [
      "REQ-02",
      "REQ-02"
    ],
    "assumption": "계산상 대안이며 실제로 이 배수를 적용해야 한다는 뜻은 아닙니다.",
    "excluded_peer": null,
    "difference_krw": "2.70671378091872791519434628975265018",
    "difference_percent": "0.01909854851031321619556913674560733386606"
  },
  {
    "calc_id": "displayed_median",
    "label": "비교기업의 표시 배수 중앙값을 적용",
    "formula": "earnings_million_krw * 1000000 * median(peer.per) / share_count",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "applied_per",
        "claim_id": "X_PER",
        "value": "26.18",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "HPSP와 워트의 PER 산술평균으로 공시된 적용 배수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].per",
        "claim_id": "X_HPSP_PER",
        "value": "34.92",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].market_cap_million_krw",
        "claim_id": "X_HPSP_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[0].earnings_million_krw",
        "claim_id": "X_HPSP_EARNINGS",
        "value": "85727",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].per",
        "claim_id": "X_WORT_PER",
        "value": "17.45",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].market_cap_million_krw",
        "claim_id": "X_WORT_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[1].earnings_million_krw",
        "claim_id": "X_WORT_EARNINGS",
        "value": "5098",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "14175.06007067137809187279151943462897527",
    "unit": "KRW/share",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [
      "REQ-02",
      "REQ-02"
    ],
    "assumption": "계산상 대안이며 실제로 이 배수를 적용해야 한다는 뜻은 아닙니다.",
    "excluded_peer": null,
    "difference_krw": "2.70671378091872791519434628975265018",
    "difference_percent": "0.01909854851031321619556913674560733386606"
  },
  {
    "calc_id": "exclude_peer_1",
    "label": "HPSP 한 곳을 제외한 표시 배수 평균을 적용",
    "formula": "earnings_million_krw * 1000000 * mean(remaining peer.per) / share_count",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "applied_per",
        "claim_id": "X_PER",
        "value": "26.18",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "HPSP와 워트의 PER 산술평균으로 공시된 적용 배수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].per",
        "claim_id": "X_HPSP_PER",
        "value": "34.92",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].market_cap_million_krw",
        "claim_id": "X_HPSP_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[0].earnings_million_krw",
        "claim_id": "X_HPSP_EARNINGS",
        "value": "85727",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].per",
        "claim_id": "X_WORT_PER",
        "value": "17.45",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].market_cap_million_krw",
        "claim_id": "X_WORT_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[1].earnings_million_krw",
        "claim_id": "X_WORT_EARNINGS",
        "value": "5098",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "9446.431095406360424028268551236749116608",
    "unit": "KRW/share",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [
      "REQ-02",
      "REQ-02"
    ],
    "assumption": "계산상 대안이며 실제로 이 배수를 적용해야 한다는 뜻은 아닙니다.",
    "excluded_peer": "HPSP",
    "difference_krw": "-4725.922261484098939929328621908127208482",
    "difference_percent": "-33.34606569900687547746371275783040488923"
  },
  {
    "calc_id": "exclude_peer_2",
    "label": "워트 한 곳을 제외한 표시 배수 평균을 적용",
    "formula": "earnings_million_krw * 1000000 * mean(remaining peer.per) / share_count",
    "inputs": [
      {
        "field": "earnings_million_krw",
        "claim_id": "X_EARNINGS",
        "value": "6894",
        "unit": "백만원",
        "period": "2026년 반기 연환산",
        "description": "반기 지배주주 순이익 4366백만원에서 세전 주식 처분이익 919백만원을 차감한 뒤 2배로 연환산한 적용 이익",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_EARNINGS",
            "locator": "PER에 의한 멜콘의 평가가치, 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "applied_per",
        "claim_id": "X_PER",
        "value": "26.18",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "HPSP와 워트의 PER 산술평균으로 공시된 적용 배수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "share_count",
        "claim_id": "X_SHARES",
        "value": "12735000",
        "unit": "주",
        "period": "공시된 주당 평가가액 산정 기준",
        "description": "기발행주식, 공모 신주, 상장주선인 의무인수분과 주식매수선택권을 합한 평가 적용주식수",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0372",
            "page": 372,
            "claim_id": "X_SHARES",
            "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].per",
        "claim_id": "X_HPSP_PER",
        "value": "34.92",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[0].market_cap_million_krw",
        "claim_id": "X_HPSP_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[0].earnings_million_krw",
        "claim_id": "X_HPSP_EARNINGS",
        "value": "85727",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_HPSP_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].per",
        "claim_id": "X_WORT_PER",
        "value": "17.45",
        "unit": "배",
        "period": "2026년 2분기 LTM",
        "description": "비교기업 PER",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_PER",
            "locator": "2026년 2분기 기준 비교기업 PER 산출"
          }
        ],
        "missing_reason": null
      },
      {
        "field": "peers[1].market_cap_million_krw",
        "claim_id": "X_WORT_CAP",
        "value": null,
        "unit": "백만원",
        "period": "2026년 8월 14일 분석 기준",
        "description": "PER 산출에 사용된 시가총액",
        "evidence": [],
        "missing_reason": "제공된 PER 산출표에는 기준주가와 상장주식수는 있으나 시가총액이 직접 기재되어 있지 않음"
      },
      {
        "field": "peers[1].earnings_million_krw",
        "claim_id": "X_WORT_EARNINGS",
        "value": "5098",
        "unit": "백만원",
        "period": "2025년 3분기~2026년 2분기",
        "description": "비교기업 PER 산출 적용 당기순이익. 연결재무제표 작성 법인은 지배주주 귀속 기준",
        "evidence": [
          {
            "doc_id": "MELCON-PROS-01",
            "chunk_id": "MELCON-PROS-01-p0370",
            "page": 370,
            "claim_id": "X_WORT_EARNINGS",
            "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
          }
        ],
        "missing_reason": null
      }
    ],
    "result": "18903.68904593639575971731448763250883392",
    "unit": "KRW/share",
    "status": "OK",
    "precision_status": "PUBLIC_INPUT_RECALCULATION",
    "precision": {
      "decimal_digits": 40,
      "rounding": "ROUND_HALF_EVEN",
      "rounded_to_currency_unit": false
    },
    "evidence": [
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_EARNINGS",
        "locator": "PER에 의한 멜콘의 평가가치, 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0372",
        "page": 372,
        "claim_id": "X_SHARES",
        "locator": "PER에 의한 멜콘의 평가가치, 적용주식수 내역"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_HPSP_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_PER",
        "locator": "2026년 2분기 기준 비교기업 PER 산출"
      },
      {
        "doc_id": "MELCON-PROS-01",
        "chunk_id": "MELCON-PROS-01-p0370",
        "page": 370,
        "claim_id": "X_WORT_EARNINGS",
        "locator": "2026년 2분기 기준 비교기업 PER 산출, 적용 당기순이익 및 주1"
      }
    ],
    "missing_reason": null,
    "related_request_ids": [
      "REQ-02",
      "REQ-02"
    ],
    "assumption": "계산상 대안이며 실제로 이 배수를 적용해야 한다는 뜻은 아닙니다.",
    "excluded_peer": "워트",
    "difference_krw": "4731.33568904593639575971731448763250883",
    "difference_percent": "33.38426279602750190985485103132161955688"
  }
]
```

숫자의 단위·기간·원문 위치는 같은 폴더의 review.json 안 extracted_inputs에서 확인할 수 있다.
