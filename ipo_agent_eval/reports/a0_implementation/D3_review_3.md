# D3 3차 독립 검토

검토자: contracts 에이전트(게이트웨이·회계 구현과 분리)
결과: PASS_AFTER_REPAIR

- 공통 7개 도구의 strict 계약, 현재 단계에서 COMMIT만 노출하는 규칙, 사례·문서·자료마감·외부경로 격리를 코드와 합성 입력으로 확인했다.
- 검색 발췌는 열람 근거가 되지 않으며 실제 페이지를 받은 뒤만 read set에 기록한다. 재열람 호출은 다시 계상하고 신규 페이지 수와 총 반환 페이지 수를 구분한다.
- 결과 예약 실패 시 페이지 열람 상태·레코드 등록이 바뀌지 않는다. 실패한 도구 시도는 실제 호출 수에 남는다.
- OPEN 요청을 최종 목록에서 빼도 원장에서 보존되고, 취소/비차단 변경은 버전과 사유를 요구한다. RESOLVED에는 실제 읽은 원문이 필요하다.
- 최종 동기화 2회+COMMIT 1회, 형식수정 후 재제출 1회가 실제로 계상된다. 과거 계산은 명시 REJECT로 보존할 수 있고 USE는 최종 snapshot과 Decimal 수치가 일치해야 한다.
- 공통층은 잘못된 자연어 결론을 자동 교정하지 않는다. 이는 별도 실패 채점 대상으로 남는다.

발견 및 수정:

1. check_request의 FINALIZING/REPAIR에서 이번 제출에 실제 필요한 도구 호출 수를 빠뜨린 경계를 발견했다. tool_calls=38인 최종화, tool_calls=40인 형식수정 API 요청을 호출 전에 차단하도록 root가 수정했다. 독립 재현 테스트를 추가해 통과를 확인했다.
2. schema integer가 1.0을 허용하는 경계에 대해 게이트웨이·원장·원문 page를 실제 Python int로 제한한 수정을 대조했다. provenance에도 같은 제한과 재현 테스트를 반영했다.

검증: `python -m pytest -q tests/test_gateway_v2.py tests/test_d3_independent_review.py tests/test_budget_v2.py tests/test_runtime_v2.py` — 61 passed.
독립 추가 파일 `tests/test_d3_independent_review.py` — 6 passed.

이 검토는 합성 검증이며 실제 모델 성능 결과나 최종 평가 완료를 의미하지 않는다. B의 기업별 무료 점검·공통 예산 정책은 root의 별도 사전점검 기록에서 확인한다.
