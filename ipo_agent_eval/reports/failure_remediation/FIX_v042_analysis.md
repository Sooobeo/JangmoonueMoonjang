# FIX_v042 저장 실행 분석

관찰 시각: 2026-11-13T11:44:11.840459+00:00

계획12건 · 실제 시작4건 · API 시작4건 · 명시적 미시작8건 · 아직 확인되지 않음0건.

| 사례 | 조건 | 상태 | 레코드/사실 | 계산 수·상태 | 모델 선택 등록/계산/민감도 | 알려진 추정 USD | 불명 usage 요청 |
|---|---|---|---:|---|---|---:|---:|
| HDMS-DEV-01 | B | SUBMITTED | 92/33 | 33 {"OK": 17, "UNAVAILABLE": 5, "INVALID": 11} | 0/0/0 | 0.21203475 | 0 |
| HDMS-DEV-01 | A0 | SUBMITTED | 73/34 | 61 {"OK": 52, "UNAVAILABLE": 9} | 3/2/1 | 0.38892835 | 0 |
| MELCON-DEV-01 | B | FAILED | 59/20 | 22 {"UNAVAILABLE": 12, "OK": 10} | 0/0/0 | 0.22177915 | 0 |
| MELCON-DEV-01 | A0 | SUBMITTED | 51/23 | 25 {"OK": 25} | 1/1/1 | 0.28107360 | 0 |
| DTS-DEV-01 | B | NOT_STARTED_STOP_REQUESTED | — | — | — | — | — |
| DTS-DEV-01 | A0 | NOT_STARTED_STOP_REQUESTED | — | — | — | — | — |
| SHINSUNGST-DEV-01 | B | NOT_STARTED_STOP_REQUESTED | — | — | — | — | — |
| SHINSUNGST-DEV-01 | A0 | NOT_STARTED_STOP_REQUESTED | — | — | — | — | — |
| ALT-DEV-01 | B | NOT_STARTED_STOP_REQUESTED | — | — | — | — | — |
| ALT-DEV-01 | A0 | NOT_STARTED_STOP_REQUESTED | — | — | — | — | — |
| MILLIE-DEV-01 | B | NOT_STARTED_STOP_REQUESTED | — | — | — | — | — |
| MILLIE-DEV-01 | A0 | NOT_STARTED_STOP_REQUESTED | — | — | — | — | — |

알려진 사용량의 비용 추정 합계는 **$1.10381585**다. 누락 usage 요청0건, 가격을 계산하지 못한 usage0건. 배치 총액 추정은 `1.10381585`이며 청구액은 확인하지 않았다.

## HDMS-DEV-01 B

- 실행: `20261113T113352Z_B_c3487bd1` · 발견 경로: `result_registry`
- 내용 상태: `PENDING_INFO` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"program_fixed": {"search_corpus": 8, "read_source": 8, "REGISTER_BATCH": 1, "EVALUATE": 1, "sensitivity": 1, "submit_review": 1}, "program_commit": {"request_information": 1, "escalate": 1}}`
- 계산 kind/status: `{"share_sum": {"OK": 1}, "share_count_difference": {"OK": 1}, "peer_market_cap": {"OK": 1, "UNAVAILABLE": 3}, "peer_market_cap_difference": {"OK": 1}, "peer_recomputed_per": {"OK": 4}, "peer_displayed_mean": {"OK": 1}, "peer_displayed_median": {"OK": 1}, "peer_recomputed_mean": {"OK": 1}, "price_from_reported_equity": {"INVALID": 1}, "price_from_displayed_per": {"INVALID": 1}, "reported_price_difference": {"UNAVAILABLE": 1}, "displayed_price_difference": {"UNAVAILABLE": 1}, "implied_per": {"INVALID": 1}, "price_from_recomputed_peer_mean": {"INVALID": 1}, "derivation_DS": {"OK": 1}, "derivation_DKC": {"OK": 1}, "derivation_DKP": {"OK": 1}, "derivation_DAP": {"OK": 1}, "derivation_DNP": {"OK": 1}, "derivation_DWP": {"OK": 1}, "sensitivity_baseline": {"INVALID": 1}, "sensitivity_displayed_mean": {"INVALID": 1}, "sensitivity_displayed_median": {"INVALID": 1}, "sensitivity_exclude_peer_1": {"INVALID": 1}, "sensitivity_exclude_peer_2": {"INVALID": 1}, "sensitivity_exclude_peer_3": {"INVALID": 1}, "sensitivity_exclude_peer_4": {"INVALID": 1}}`
- 제출 계산 USE/REJECT: `{"USE": 11, "REJECT": 7}`
- 원시 usage 합계: `{"input_tokens": 107957, "ordinary_input_tokens": 6, "cached_input_tokens": 0, "cache_write_30m_tokens": 107951, "cache_write_12h_tokens": 0, "output_tokens": 15418, "reasoning_tokens": 2195}`
- 원본: [runs/20261113T113352Z_B_c3487bd1](../../runs/20261113T113352Z_B_c3487bd1/)

## HDMS-DEV-01 A0

- 실행: `20261113T113352Z_A0_0c66acf1` · 발견 경로: `result_registry`
- 내용 상태: `PENDING_INFO` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"model": {"search_corpus": 4, "read_source": 4, "REGISTER_BATCH": 3, "EVALUATE": 2, "sensitivity": 1, "submit_review": 1}, "program_commit": {"request_information": 1, "escalate": 1}}`
- 계산 kind/status: `{"share_sum": {"OK": 2}, "share_count_difference": {"OK": 2}, "peer_market_cap": {"OK": 2, "UNAVAILABLE": 6}, "peer_market_cap_difference": {"OK": 2}, "peer_recomputed_per": {"UNAVAILABLE": 1, "OK": 7}, "peer_displayed_mean": {"OK": 2}, "peer_displayed_median": {"OK": 2}, "peer_recomputed_mean": {"UNAVAILABLE": 1, "OK": 1}, "price_from_reported_equity": {"OK": 2}, "price_from_displayed_per": {"OK": 2}, "reported_price_difference": {"OK": 2}, "displayed_price_difference": {"OK": 2}, "implied_per": {"OK": 2}, "price_from_recomputed_peer_mean": {"UNAVAILABLE": 1, "OK": 1}, "derivation_DS": {"OK": 2}, "derivation_DP": {"OK": 2}, "derivation_D1": {"OK": 2}, "derivation_D2": {"OK": 2}, "derivation_D3": {"OK": 2}, "derivation_D4": {"OK": 2}, "derivation_DM1": {"OK": 2}, "sensitivity_baseline": {"OK": 1}, "sensitivity_displayed_mean": {"OK": 1}, "sensitivity_displayed_median": {"OK": 1}, "sensitivity_exclude_peer_1": {"OK": 1}, "sensitivity_exclude_peer_2": {"OK": 1}, "sensitivity_exclude_peer_3": {"OK": 1}, "sensitivity_exclude_peer_4": {"OK": 1}}`
- 제출 계산 USE/REJECT: `{"USE": 12}`
- 원시 usage 합계: `{"input_tokens": 756749, "ordinary_input_tokens": 174, "cached_input_tokens": 513337, "cache_write_30m_tokens": 243238, "cache_write_12h_tokens": 0, "output_tokens": 11808, "reasoning_tokens": 815}`
- 원본: [runs/20261113T113352Z_A0_0c66acf1](../../runs/20261113T113352Z_A0_0c66acf1/)

## MELCON-DEV-01 B

- 실행: `20261113T113649Z_B_13f17aec` · 발견 경로: `result_registry`
- 내용 상태: `None` · 실패 사유: INVALID_REVIEW:Defined judgment and claim IDs must be nonempty and globally unique
- 도구 actor별: `{"program_fixed": {"search_corpus": 8, "read_source": 8, "REGISTER_BATCH": 1, "EVALUATE": 1, "sensitivity": 1, "submit_review": 1}, "program_commit": {"request_information": 1, "escalate": 1, "submit_review": 1}}`
- 계산 kind/status: `{"share_sum": {"UNAVAILABLE": 1}, "share_count_difference": {"UNAVAILABLE": 1}, "peer_market_cap": {"OK": 2}, "peer_recomputed_per": {"OK": 2}, "peer_displayed_mean": {"OK": 1}, "peer_displayed_median": {"OK": 1}, "peer_recomputed_mean": {"OK": 1}, "price_from_reported_equity": {"UNAVAILABLE": 1}, "price_from_displayed_per": {"UNAVAILABLE": 1}, "reported_price_difference": {"UNAVAILABLE": 1}, "displayed_price_difference": {"UNAVAILABLE": 1}, "implied_per": {"OK": 1}, "price_from_recomputed_peer_mean": {"UNAVAILABLE": 1}, "derivation_D_HC": {"OK": 1}, "derivation_D_WC": {"OK": 1}, "sensitivity_baseline": {"UNAVAILABLE": 1}, "sensitivity_displayed_mean": {"UNAVAILABLE": 1}, "sensitivity_displayed_median": {"UNAVAILABLE": 1}, "sensitivity_exclude_peer_1": {"UNAVAILABLE": 1}, "sensitivity_exclude_peer_2": {"UNAVAILABLE": 1}}`
- 제출 계산 USE/REJECT: `null`
- 원시 usage 합계: `{"input_tokens": 132512, "ordinary_input_tokens": 9, "cached_input_tokens": 5378, "cache_write_30m_tokens": 127125, "cache_write_12h_tokens": 0, "output_tokens": 12519, "reasoning_tokens": 1718}`
- 원본: [runs/20261113T113649Z_B_13f17aec](../../runs/20261113T113649Z_B_13f17aec/)

## MELCON-DEV-01 A0

- 실행: `20261113T113652Z_A0_d8c07c9f` · 발견 경로: `result_registry`
- 내용 상태: `HUMAN_REVIEW` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"model": {"search_corpus": 5, "read_source": 4, "REGISTER_BATCH": 1, "EVALUATE": 1, "sensitivity": 1, "request_information": 1, "escalate": 1, "submit_review": 2}, "program_commit": {"request_information": 1, "escalate": 1}}`
- 계산 kind/status: `{"share_sum": {"OK": 1}, "share_count_difference": {"OK": 1}, "peer_market_cap": {"OK": 2}, "peer_recomputed_per": {"OK": 2}, "peer_displayed_mean": {"OK": 1}, "peer_displayed_median": {"OK": 1}, "peer_recomputed_mean": {"OK": 1}, "price_from_reported_equity": {"OK": 1}, "price_from_displayed_per": {"OK": 1}, "reported_price_difference": {"OK": 1}, "displayed_price_difference": {"OK": 1}, "implied_per": {"OK": 1}, "price_from_recomputed_peer_mean": {"OK": 1}, "derivation_DS": {"OK": 1}, "derivation_DHC": {"OK": 1}, "derivation_DWC": {"OK": 1}, "derivation_DHP": {"OK": 1}, "derivation_DWP": {"OK": 1}, "sensitivity_baseline": {"OK": 1}, "sensitivity_displayed_mean": {"OK": 1}, "sensitivity_displayed_median": {"OK": 1}, "sensitivity_exclude_peer_1": {"OK": 1}, "sensitivity_exclude_peer_2": {"OK": 1}}`
- 제출 계산 USE/REJECT: `{"USE": 11}`
- 원시 usage 합계: `{"input_tokens": 688805, "ordinary_input_tokens": 177, "cached_input_tokens": 532007, "cache_write_30m_tokens": 156621, "cache_write_12h_tokens": 0, "output_tokens": 11704, "reasoning_tokens": 646}`
- 원본: [runs/20261113T113652Z_A0_d8c07c9f](../../runs/20261113T113652Z_A0_d8c07c9f/)

## DTS-DEV-01 B

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: STOP_REQUESTED_BEFORE_API

## DTS-DEV-01 A0

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: STOP_REQUESTED_BEFORE_API

## SHINSUNGST-DEV-01 B

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: STOP_REQUESTED_BEFORE_API

## SHINSUNGST-DEV-01 A0

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: STOP_REQUESTED_BEFORE_API

## ALT-DEV-01 B

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: STOP_REQUESTED_BEFORE_API

## ALT-DEV-01 A0

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: STOP_REQUESTED_BEFORE_API

## MILLIE-DEV-01 B

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: STOP_REQUESTED_BEFORE_API

## MILLIE-DEV-01 A0

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: STOP_REQUESTED_BEFORE_API

## v032의 같은 사례·조건

실행 조건이 변경되어 아래 차이를 특정 수정의 순수 효과로 해석할 수 없다.

| 사례 | 조건 | v032 상태 | 계산 수 | 실패 사유 |
|---|---|---|---:|---|
| HDMS-DEV-01 | B | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |
| HDMS-DEV-01 | A0 | FAILED | 0 | API_ERROR:InternalServerError |
| MELCON-DEV-01 | B | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |
| MELCON-DEV-01 | A0 | SUBMITTED | 0 | — |
| DTS-DEV-01 | B | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |
| DTS-DEV-01 | A0 | SUBMITTED | 0 | — |
| SHINSUNGST-DEV-01 | B | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |
| SHINSUNGST-DEV-01 | A0 | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |
| ALT-DEV-01 | B | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |
| ALT-DEV-01 | A0 | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |
| MILLIE-DEV-01 | B | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |
| MILLIE-DEV-01 | A0 | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |

설정 변경(동결된 B 설정 대조):

- `dynamic_submission_contract`: `null` → `true`
- `exploration_output_max`: `1000` → `9000`
- `extraction_output_max`: `5000` → `9000`
- `format_repair_contract`: `null` → `"patch_v1"`
- `format_repair_output_max`: `2500` → `1500`
- `input_tokens_target_max`: `160000` → `800000`
- `max_model_calls`: `16` → `24`
- `max_run_usd`: `0.3` → `1.25`
- `max_transient_api_retries`: `null` → `1`
- `output_tokens_max`: `16000` → `24000`
- `review_output_max`: `8500` → `10000`
- `version`: `"0.3.2-dev"` → `"0.4.2-dev"`
- `wall_seconds_max`: `600` → `900`
- `wire_contract`: `null` → `"compact_v1"`

이 보고서는 기계적 실행·사용량 관찰이다. 숫자와 판단의 정답 채점은 별도이며, 제출 성공을 내용 정확성으로 해석하지 않는다. 미착수는 실패 분모에 넣지 않았고 진행 중 요청의 비용을0으로 확정하지 않았다.
