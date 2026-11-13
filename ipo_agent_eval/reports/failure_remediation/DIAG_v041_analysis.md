# DIAG_v041 저장 실행 분석

관찰 시각: 2026-11-13T11:22:38.368325+00:00

계획4건 · 실제 시작4건 · API 시작4건 · 명시적 미시작0건 · 아직 확인되지 않음0건.

| 사례 | 조건 | 상태 | 레코드/사실 | 계산 수·상태 | 모델 선택 등록/계산/민감도 | 알려진 추정 USD | 불명 usage 요청 |
|---|---|---|---:|---|---|---:|---:|
| MELCON-DEV-01 | B | SUBMITTED | 64/26 | 25 {"UNAVAILABLE": 2, "OK": 23} | 0/0/0 | 0.22902225 | 0 |
| MELCON-DEV-01 | A0 | SUBMITTED | 51/23 | 26 {"OK": 26} | 2/1/1 | 0.29878685 | 0 |
| ALT-DEV-01 | B | SUBMITTED | 69/27 | 32 {"UNAVAILABLE": 7, "OK": 25} | 0/0/0 | 0.16223905 | 0 |
| ALT-DEV-01 | A0 | SUBMITTED | 51/27 | 32 {"UNAVAILABLE": 7, "OK": 25} | 2/1/1 | 0.29760745 | 0 |

알려진 사용량의 비용 추정 합계는 **$0.98765560**다. 누락 usage 요청0건, 가격을 계산하지 못한 usage0건. 배치 총액 추정은 `0.98765560`이며 청구액은 확인하지 않았다.

## MELCON-DEV-01 B

- 실행: `20261113T111430Z_B_3281abe6` · 발견 경로: `result_registry`
- 내용 상태: `HUMAN_REVIEW` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"program_fixed": {"search_corpus": 8, "read_source": 8, "REGISTER_BATCH": 1, "EVALUATE": 1, "sensitivity": 1, "submit_review": 1}, "program_commit": {"request_information": 1, "escalate": 1}}`
- 계산 kind/status: `{"share_sum": {"UNAVAILABLE": 1}, "share_count_difference": {"UNAVAILABLE": 1}, "peer_market_cap": {"OK": 2}, "peer_recomputed_per": {"OK": 2}, "peer_displayed_mean": {"OK": 1}, "peer_displayed_median": {"OK": 1}, "peer_recomputed_mean": {"OK": 1}, "price_from_reported_equity": {"OK": 1}, "price_from_displayed_per": {"OK": 1}, "reported_price_difference": {"OK": 1}, "displayed_price_difference": {"OK": 1}, "implied_per": {"OK": 1}, "price_from_recomputed_peer_mean": {"OK": 1}, "derivation_D_HC": {"OK": 1}, "derivation_D_WC": {"OK": 1}, "derivation_D_HB": {"OK": 1}, "derivation_D_WB": {"OK": 1}, "derivation_D_IR": {"OK": 1}, "sensitivity_baseline": {"OK": 1}, "sensitivity_displayed_mean": {"OK": 1}, "sensitivity_displayed_median": {"OK": 1}, "sensitivity_exclude_peer_1": {"OK": 1}, "sensitivity_exclude_peer_2": {"OK": 1}}`
- 제출 계산 USE/REJECT: `{"USE": 15, "REJECT": 2}`
- 원시 usage 합계: `{"input_tokens": 124911, "ordinary_input_tokens": 6, "cached_input_tokens": 0, "cache_write_30m_tokens": 124905, "cache_write_12h_tokens": 0, "output_tokens": 14577, "reasoning_tokens": 2124}`
- 원본: [runs/20261113T111430Z_B_3281abe6](../../runs/20261113T111430Z_B_3281abe6/)

## MELCON-DEV-01 A0

- 실행: `20261113T111430Z_A0_2a9c2a1c` · 발견 경로: `result_registry`
- 내용 상태: `HUMAN_REVIEW` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"model": {"search_corpus": 7, "read_source": 4, "REGISTER_BATCH": 2, "EVALUATE": 1, "sensitivity": 1, "escalate": 1, "submit_review": 1}, "program_commit": {"request_information": 1, "escalate": 1}}`
- 계산 kind/status: `{"share_sum": {"OK": 1}, "share_count_difference": {"OK": 1}, "peer_market_cap": {"OK": 2}, "peer_recomputed_per": {"OK": 2}, "peer_displayed_mean": {"OK": 1}, "peer_displayed_median": {"OK": 1}, "peer_recomputed_mean": {"OK": 1}, "price_from_reported_equity": {"OK": 1}, "price_from_displayed_per": {"OK": 1}, "reported_price_difference": {"OK": 1}, "displayed_price_difference": {"OK": 1}, "implied_per": {"OK": 1}, "price_from_recomputed_peer_mean": {"OK": 1}, "derivation_DS": {"OK": 1}, "derivation_DP": {"OK": 1}, "derivation_DH_CAP": {"OK": 1}, "derivation_DW_CAP": {"OK": 1}, "derivation_DH_PER": {"OK": 1}, "derivation_DW_PER": {"OK": 1}, "sensitivity_baseline": {"OK": 1}, "sensitivity_displayed_mean": {"OK": 1}, "sensitivity_displayed_median": {"OK": 1}, "sensitivity_exclude_peer_1": {"OK": 1}, "sensitivity_exclude_peer_2": {"OK": 1}}`
- 제출 계산 USE/REJECT: `{"USE": 11}`
- 원시 usage 합계: `{"input_tokens": 730921, "ordinary_input_tokens": 180, "cached_input_tokens": 559437, "cache_write_30m_tokens": 171304, "cache_write_12h_tokens": 0, "output_tokens": 11301, "reasoning_tokens": 592}`
- 원본: [runs/20261113T111430Z_A0_2a9c2a1c](../../runs/20261113T111430Z_A0_2a9c2a1c/)

## ALT-DEV-01 B

- 실행: `20261113T111719Z_B_33614eb2` · 발견 경로: `result_registry`
- 내용 상태: `HUMAN_REVIEW` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"program_fixed": {"search_corpus": 8, "read_source": 8, "REGISTER_BATCH": 1, "EVALUATE": 1, "sensitivity": 1, "submit_review": 1}, "program_commit": {"request_information": 1, "escalate": 1}}`
- 계산 kind/status: `{"share_sum": {"UNAVAILABLE": 1}, "share_count_difference": {"UNAVAILABLE": 1}, "peer_market_cap": {"UNAVAILABLE": 4}, "peer_recomputed_per": {"OK": 4}, "peer_displayed_mean": {"OK": 1}, "peer_displayed_median": {"OK": 1}, "peer_recomputed_mean": {"OK": 1}, "price_from_reported_equity": {"OK": 1}, "price_from_displayed_per": {"OK": 1}, "reported_price_difference": {"OK": 1}, "displayed_price_difference": {"OK": 1}, "implied_per": {"OK": 1}, "price_from_recomputed_peer_mean": {"OK": 1}, "derivation_DS": {"UNAVAILABLE": 1}, "derivation_DP": {"OK": 1}, "derivation_D1": {"OK": 1}, "derivation_D2": {"OK": 1}, "derivation_D3": {"OK": 1}, "derivation_D4": {"OK": 1}, "sensitivity_baseline": {"OK": 1}, "sensitivity_displayed_mean": {"OK": 1}, "sensitivity_displayed_median": {"OK": 1}, "sensitivity_exclude_peer_1": {"OK": 1}, "sensitivity_exclude_peer_2": {"OK": 1}, "sensitivity_exclude_peer_3": {"OK": 1}, "sensitivity_exclude_peer_4": {"OK": 1}}`
- 제출 계산 USE/REJECT: `{"USE": 11, "REJECT": 1}`
- 원시 usage 합계: `{"input_tokens": 81279, "ordinary_input_tokens": 6, "cached_input_tokens": 5061, "cache_write_30m_tokens": 76212, "cache_write_12h_tokens": 0, "output_tokens": 13343, "reasoning_tokens": 1604}`
- 원본: [runs/20261113T111719Z_B_33614eb2](../../runs/20261113T111719Z_B_33614eb2/)

## ALT-DEV-01 A0

- 실행: `20261113T111721Z_A0_4b26cbd9` · 발견 경로: `result_registry`
- 내용 상태: `HUMAN_REVIEW` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"model": {"search_corpus": 6, "read_source": 4, "REGISTER_BATCH": 2, "EVALUATE": 1, "sensitivity": 1, "request_information": 1, "escalate": 1, "submit_review": 1}, "program_commit": {"request_information": 1, "escalate": 1}}`
- 계산 kind/status: `{"share_sum": {"UNAVAILABLE": 1}, "share_count_difference": {"UNAVAILABLE": 1}, "peer_market_cap": {"UNAVAILABLE": 4}, "peer_recomputed_per": {"OK": 4}, "peer_displayed_mean": {"OK": 1}, "peer_displayed_median": {"OK": 1}, "peer_recomputed_mean": {"OK": 1}, "price_from_reported_equity": {"OK": 1}, "price_from_displayed_per": {"OK": 1}, "reported_price_difference": {"OK": 1}, "displayed_price_difference": {"OK": 1}, "implied_per": {"OK": 1}, "price_from_recomputed_peer_mean": {"OK": 1}, "derivation_DS": {"UNAVAILABLE": 1}, "derivation_DP": {"OK": 1}, "derivation_D1": {"OK": 1}, "derivation_D2": {"OK": 1}, "derivation_D3": {"OK": 1}, "derivation_D4": {"OK": 1}, "sensitivity_baseline": {"OK": 1}, "sensitivity_displayed_mean": {"OK": 1}, "sensitivity_displayed_median": {"OK": 1}, "sensitivity_exclude_peer_1": {"OK": 1}, "sensitivity_exclude_peer_2": {"OK": 1}, "sensitivity_exclude_peer_3": {"OK": 1}, "sensitivity_exclude_peer_4": {"OK": 1}}`
- 제출 계산 USE/REJECT: `{"USE": 8, "REJECT": 1}`
- 원시 usage 합계: `{"input_tokens": 728665, "ordinary_input_tokens": 180, "cached_input_tokens": 556099, "cache_write_30m_tokens": 172386, "cache_write_12h_tokens": 0, "output_tokens": 10828, "reasoning_tokens": 845}`
- 원본: [runs/20261113T111721Z_A0_4b26cbd9](../../runs/20261113T111721Z_A0_4b26cbd9/)

## v032의 같은 사례·조건

실행 조건이 변경되어 아래 차이를 특정 수정의 순수 효과로 해석할 수 없다.

| 사례 | 조건 | v032 상태 | 계산 수 | 실패 사유 |
|---|---|---|---:|---|
| MELCON-DEV-01 | B | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |
| MELCON-DEV-01 | A0 | SUBMITTED | 0 | — |
| ALT-DEV-01 | B | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |
| ALT-DEV-01 | A0 | FAILED | 0 | MODEL_INCOMPLETE:max_output_tokens |

설정 변경(동결된 B 설정 대조):

- `dynamic_submission_contract`: `null` → `true`
- `exploration_output_max`: `1000` → `3500`
- `extraction_output_max`: `5000` → `9000`
- `format_repair_contract`: `null` → `"patch_v1"`
- `format_repair_output_max`: `2500` → `1500`
- `input_tokens_target_max`: `160000` → `800000`
- `max_model_calls`: `16` → `24`
- `max_run_usd`: `0.3` → `1.25`
- `max_transient_api_retries`: `null` → `1`
- `output_tokens_max`: `16000` → `24000`
- `review_output_max`: `8500` → `10000`
- `version`: `"0.3.2-dev"` → `"0.4.1-dev"`
- `wall_seconds_max`: `600` → `900`
- `wire_contract`: `null` → `"compact_v1"`

이 보고서는 기계적 실행·사용량 관찰이다. 숫자와 판단의 정답 채점은 별도이며, 제출 성공을 내용 정확성으로 해석하지 않는다. 미착수는 실패 분모에 넣지 않았고 진행 중 요청의 비용을0으로 확정하지 않았다.
