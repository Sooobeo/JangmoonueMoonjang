# FIX_v043 저장 실행 분석

관찰 시각: 2026-11-13T11:53:04.092915+00:00

계획12건 · 실제 시작2건 · API 시작2건 · 명시적 미시작0건 · 아직 확인되지 않음10건.

| 사례 | 조건 | 상태 | 레코드/사실 | 계산 수·상태 | 모델 선택 등록/계산/민감도 | 알려진 추정 USD | 불명 usage 요청 |
|---|---|---|---:|---|---|---:|---:|
| HDMS-DEV-01 | B | RUNNING | 99/37 | 37 {"OK": 31, "UNAVAILABLE": 6} | 0/0/0 | 0.0970455 | 1 |
| HDMS-DEV-01 | A0 | RUNNING | 61/35 | 61 {"OK": 52, "UNAVAILABLE": 9} | 2/2/1 | 0.20688785 | 1 |
| MELCON-DEV-01 | B | NOT_YET_OBSERVED | — | — | — | — | — |
| MELCON-DEV-01 | A0 | NOT_YET_OBSERVED | — | — | — | — | — |
| DTS-DEV-01 | B | NOT_YET_OBSERVED | — | — | — | — | — |
| DTS-DEV-01 | A0 | NOT_YET_OBSERVED | — | — | — | — | — |
| SHINSUNGST-DEV-01 | B | NOT_YET_OBSERVED | — | — | — | — | — |
| SHINSUNGST-DEV-01 | A0 | NOT_YET_OBSERVED | — | — | — | — | — |
| ALT-DEV-01 | B | NOT_YET_OBSERVED | — | — | — | — | — |
| ALT-DEV-01 | A0 | NOT_YET_OBSERVED | — | — | — | — | — |
| MILLIE-DEV-01 | B | NOT_YET_OBSERVED | — | — | — | — | — |
| MILLIE-DEV-01 | A0 | NOT_YET_OBSERVED | — | — | — | — | — |

알려진 사용량의 비용 추정 합계는 **$0.30393335**다. 누락 usage 요청2건, 가격을 계산하지 못한 usage0건. 배치 총액 추정은 `None`이며 청구액은 확인하지 않았다.

## HDMS-DEV-01 B

- 실행: `20261113T115106Z_B_2517ee1e` · 발견 경로: `unlisted_matching_live_directory`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"program_fixed": {"search_corpus": 8, "read_source": 8, "REGISTER_BATCH": 1, "EVALUATE": 1, "sensitivity": 1}}`
- 계산 kind/status: `{"share_sum": {"OK": 1}, "share_count_difference": {"OK": 1}, "peer_market_cap": {"OK": 1, "UNAVAILABLE": 3}, "peer_market_cap_difference": {"OK": 1, "UNAVAILABLE": 3}, "peer_recomputed_per": {"OK": 4}, "peer_displayed_mean": {"OK": 1}, "peer_displayed_median": {"OK": 1}, "peer_recomputed_mean": {"OK": 1}, "price_from_reported_equity": {"OK": 1}, "price_from_displayed_per": {"OK": 1}, "reported_price_difference": {"OK": 1}, "displayed_price_difference": {"OK": 1}, "implied_per": {"OK": 1}, "price_from_recomputed_peer_mean": {"OK": 1}, "derivation_DS": {"OK": 1}, "derivation_DP": {"OK": 1}, "derivation_DKV": {"OK": 1}, "derivation_DK": {"OK": 1}, "derivation_DA": {"OK": 1}, "derivation_DG": {"OK": 1}, "derivation_DW": {"OK": 1}, "sensitivity_baseline": {"OK": 1}, "sensitivity_displayed_mean": {"OK": 1}, "sensitivity_displayed_median": {"OK": 1}, "sensitivity_exclude_peer_1": {"OK": 1}, "sensitivity_exclude_peer_2": {"OK": 1}, "sensitivity_exclude_peer_3": {"OK": 1}, "sensitivity_exclude_peer_4": {"OK": 1}}`
- 제출 계산 USE/REJECT: `null`
- 원시 usage 합계: `{"input_tokens": 47461, "ordinary_input_tokens": 3, "cached_input_tokens": 0, "cache_write_30m_tokens": 47458, "cache_write_12h_tokens": 0, "output_tokens": 7544, "reasoning_tokens": 817}`
- 원본: [runs/20261113T115106Z_B_2517ee1e](../../runs/20261113T115106Z_B_2517ee1e/)

## HDMS-DEV-01 A0

- 실행: `20261113T115106Z_A0_6aec2588` · 발견 경로: `unlisted_matching_live_directory`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰
- 도구 actor별: `{"model": {"search_corpus": 3, "read_source": 3, "REGISTER_BATCH": 2, "EVALUATE": 2, "sensitivity": 1}}`
- 계산 kind/status: `{"share_sum": {"OK": 2}, "share_count_difference": {"OK": 2}, "peer_market_cap": {"OK": 2, "UNAVAILABLE": 6}, "peer_market_cap_difference": {"OK": 2}, "peer_recomputed_per": {"UNAVAILABLE": 1, "OK": 7}, "peer_displayed_mean": {"OK": 2}, "peer_displayed_median": {"OK": 2}, "peer_recomputed_mean": {"UNAVAILABLE": 1, "OK": 1}, "price_from_reported_equity": {"OK": 2}, "price_from_displayed_per": {"OK": 2}, "reported_price_difference": {"OK": 2}, "displayed_price_difference": {"OK": 2}, "implied_per": {"OK": 2}, "price_from_recomputed_peer_mean": {"UNAVAILABLE": 1, "OK": 1}, "derivation_DS": {"OK": 2}, "derivation_DP": {"OK": 2}, "derivation_D1": {"OK": 2}, "derivation_D2": {"OK": 2}, "derivation_D3": {"OK": 2}, "derivation_D4": {"OK": 2}, "derivation_DC1": {"OK": 2}, "sensitivity_baseline": {"OK": 1}, "sensitivity_displayed_mean": {"OK": 1}, "sensitivity_displayed_median": {"OK": 1}, "sensitivity_exclude_peer_1": {"OK": 1}, "sensitivity_exclude_peer_2": {"OK": 1}, "sensitivity_exclude_peer_3": {"OK": 1}, "sensitivity_exclude_peer_4": {"OK": 1}}`
- 제출 계산 USE/REJECT: `null`
- 원시 usage 합계: `{"input_tokens": 582314, "ordinary_input_tokens": 33, "cached_input_tokens": 456922, "cache_write_30m_tokens": 125359, "cache_write_12h_tokens": 0, "output_tokens": 5462, "reasoning_tokens": 401}`
- 원본: [runs/20261113T115106Z_A0_6aec2588](../../runs/20261113T115106Z_A0_6aec2588/)

## MELCON-DEV-01 B

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰

## MELCON-DEV-01 A0

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰

## DTS-DEV-01 B

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰

## DTS-DEV-01 A0

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰

## SHINSUNGST-DEV-01 B

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰

## SHINSUNGST-DEV-01 A0

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰

## ALT-DEV-01 B

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰

## ALT-DEV-01 A0

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰

## MILLIE-DEV-01 B

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰

## MILLIE-DEV-01 A0

- 실행: `None` · 발견 경로: `None`
- 내용 상태: `None` · 실패 사유: 없음 또는 아직 미관찰

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
- `version`: `"0.3.2-dev"` → `"0.4.3-dev"`
- `wall_seconds_max`: `600` → `900`
- `wire_contract`: `null` → `"compact_v2"`

이 보고서는 기계적 실행·사용량 관찰이다. 숫자와 판단의 정답 채점은 별도이며, 제출 성공을 내용 정확성으로 해석하지 않는다. 미착수는 실패 분모에 넣지 않았고 진행 중 요청의 비용을0으로 확정하지 않았다.
