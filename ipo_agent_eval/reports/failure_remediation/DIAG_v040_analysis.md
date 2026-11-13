# DIAG_v040 저장 실행 분석

관찰 시각: 2026-11-13T11:12:50.744310+00:00

계획4건 · 실제 시작4건 · API 시작4건 · 명시적 미시작0건 · 아직 확인되지 않음0건.

| 사례 | 조건 | 상태 | 레코드/사실 | 계산 수·상태 | 모델 선택 등록/계산/민감도 | 알려진 추정 USD | 불명 usage 요청 |
|---|---|---|---:|---|---|---:|---:|
| MELCON-DEV-01 | B | FAILED | 0/0 | 0 {} | 0/0/0 | 0.10728350 | 0 |
| MELCON-DEV-01 | A0 | SUBMITTED | 48/24 | 0 {} | 1/0/0 | 0.17340535 | 0 |
| ALT-DEV-01 | B | FAILED | 90/42 | 32 {"UNAVAILABLE": 11, "INVALID": 19, "OK": 2} | 0/0/0 | 0.17559680 | 0 |
| ALT-DEV-01 | A0 | SUBMITTED | 41/21 | 19 {"UNAVAILABLE": 8, "OK": 7, "INVALID": 4} | 1/1/0 | 0.16475420 | 0 |

알려진 사용량의 비용 추정 합계는 **$0.62103985**다. 누락 usage 요청0건, 가격을 계산하지 못한 usage0건. 배치 총액 추정은 `0.62103985`이며 청구액은 확인하지 않았다.

## MELCON-DEV-01 B

- 실행: `20261113T110630Z_B_5147fc4b` · 발견 경로: `result_registry`
- 내용 상태: `None` · 실패 사유: INVALID_RECORD:Usability does not match its selected fact
- 도구 actor별: `{"program_fixed": {"search_corpus": 8, "read_source": 8, "REGISTER_BATCH": 2}}`
- 계산 kind/status: `{}`
- 제출 계산 USE/REJECT: `null`
- 원시 usage 합계: `{"input_tokens": 63052, "ordinary_input_tokens": 6, "cached_input_tokens": 0, "cache_write_30m_tokens": 63046, "cache_write_12h_tokens": 0, "output_tokens": 5694, "reasoning_tokens": 690}`
- 원본: [runs/20261113T110630Z_B_5147fc4b](../../runs/20261113T110630Z_B_5147fc4b/)

## MELCON-DEV-01 A0

- 실행: `20261113T110630Z_A0_30c1b28b` · 발견 경로: `result_registry`
- 내용 상태: `HUMAN_REVIEW` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"model": {"search_corpus": 8, "read_source": 4, "REGISTER_BATCH": 1, "submit_review": 1}, "program_commit": {"request_information": 1, "escalate": 1}}`
- 계산 kind/status: `{}`
- 제출 계산 USE/REJECT: `{}`
- 원시 usage 합계: `{"input_tokens": 319422, "ordinary_input_tokens": 171, "cached_input_tokens": 225037, "cache_write_30m_tokens": 94214, "cache_write_12h_tokens": 0, "output_tokens": 8843, "reasoning_tokens": 468}`
- 원본: [runs/20261113T110630Z_A0_30c1b28b](../../runs/20261113T110630Z_A0_30c1b28b/)

## ALT-DEV-01 B

- 실행: `20261113T110740Z_B_31fd7dc2` · 발견 경로: `result_registry`
- 내용 상태: `None` · 실패 사유: ISOLATION_VIOLATION:The execution was terminated after an isolation violation
- 도구 actor별: `{"program_fixed": {"search_corpus": 8, "read_source": 8, "REGISTER_BATCH": 1, "EVALUATE": 1, "sensitivity": 1, "submit_review": 1}, "program_commit": {"submit_review": 1}}`
- 계산 kind/status: `{"share_sum": {"UNAVAILABLE": 1}, "share_count_difference": {"UNAVAILABLE": 1}, "peer_market_cap": {"UNAVAILABLE": 4}, "peer_recomputed_per": {"INVALID": 4}, "peer_displayed_mean": {"OK": 1}, "peer_displayed_median": {"OK": 1}, "peer_recomputed_mean": {"UNAVAILABLE": 1}, "price_from_reported_equity": {"INVALID": 1}, "price_from_displayed_per": {"INVALID": 1}, "reported_price_difference": {"UNAVAILABLE": 1}, "displayed_price_difference": {"UNAVAILABLE": 1}, "implied_per": {"INVALID": 1}, "price_from_recomputed_peer_mean": {"UNAVAILABLE": 1}, "derivation_d1": {"UNAVAILABLE": 1}, "derivation_d2": {"INVALID": 1}, "derivation_d3": {"INVALID": 1}, "derivation_d4": {"INVALID": 1}, "derivation_d5": {"INVALID": 1}, "derivation_d6": {"INVALID": 1}, "sensitivity_baseline": {"INVALID": 1}, "sensitivity_displayed_mean": {"INVALID": 1}, "sensitivity_displayed_median": {"INVALID": 1}, "sensitivity_exclude_peer_1": {"INVALID": 1}, "sensitivity_exclude_peer_2": {"INVALID": 1}, "sensitivity_exclude_peer_3": {"INVALID": 1}, "sensitivity_exclude_peer_4": {"INVALID": 1}}`
- 제출 계산 USE/REJECT: `null`
- 원시 usage 합계: `{"input_tokens": 90661, "ordinary_input_tokens": 9, "cached_input_tokens": 3906, "cache_write_30m_tokens": 86746, "cache_write_12h_tokens": 0, "output_tokens": 13392, "reasoning_tokens": 2406}`
- 원본: [runs/20261113T110740Z_B_31fd7dc2](../../runs/20261113T110740Z_B_31fd7dc2/)
- **실행기 스키마 결함 관찰:** missing_inputs.field의 enum이 출처 ID·결론 등 무관한 문자열에도 붙었다. 잘못된 출처 문자열을 모델의 독립적인 위조로 해석하지 않는다. 저장된 실패 상태는 그대로 유지한다.
  - 요청 `runs/20261113T110740Z_B_31fd7dc2/02_review_request.json` · 오염된 문자열 경로 40개
  - 요청 `runs/20261113T110740Z_B_31fd7dc2/03_format_repair_request.json` · 오염된 문자열 경로 40개

## ALT-DEV-01 A0

- 실행: `20261113T110846Z_A0_775083d3` · 발견 경로: `result_registry`
- 내용 상태: `HUMAN_REVIEW` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"model": {"search_corpus": 5, "read_source": 4, "REGISTER_BATCH": 1, "EVALUATE": 1, "submit_review": 1}, "program_commit": {"request_information": 1, "escalate": 1}}`
- 계산 kind/status: `{"share_sum": {"UNAVAILABLE": 1}, "share_count_difference": {"UNAVAILABLE": 1}, "peer_market_cap": {"UNAVAILABLE": 4}, "peer_recomputed_per": {"OK": 4}, "peer_displayed_mean": {"OK": 1}, "peer_displayed_median": {"OK": 1}, "peer_recomputed_mean": {"OK": 1}, "price_from_reported_equity": {"INVALID": 1}, "price_from_displayed_per": {"INVALID": 1}, "reported_price_difference": {"UNAVAILABLE": 1}, "displayed_price_difference": {"UNAVAILABLE": 1}, "implied_per": {"INVALID": 1}, "price_from_recomputed_peer_mean": {"INVALID": 1}}`
- 제출 계산 USE/REJECT: `{"USE": 3, "REJECT": 3}`
- 원시 usage 합계: `{"input_tokens": 313305, "ordinary_input_tokens": 165, "cached_input_tokens": 225509, "cache_write_30m_tokens": 87631, "cache_write_12h_tokens": 0, "output_tokens": 8755, "reasoning_tokens": 643}`
- 원본: [runs/20261113T110846Z_A0_775083d3](../../runs/20261113T110846Z_A0_775083d3/)

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
- `input_tokens_target_max`: `160000` → `400000`
- `max_model_calls`: `16` → `24`
- `max_run_usd`: `0.3` → `0.75`
- `max_transient_api_retries`: `null` → `1`
- `output_tokens_max`: `16000` → `24000`
- `review_output_max`: `8500` → `10000`
- `version`: `"0.3.2-dev"` → `"0.4.0-dev"`
- `wall_seconds_max`: `600` → `900`
- `wire_contract`: `null` → `"compact_v1"`

이 보고서는 기계적 실행·사용량 관찰이다. 숫자와 판단의 정답 채점은 별도이며, 제출 성공을 내용 정확성으로 해석하지 않는다. 미착수는 실패 분모에 넣지 않았고 진행 중 요청의 비용을0으로 확정하지 않았다.
