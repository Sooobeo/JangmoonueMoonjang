# D4 2차 독립 검토

검토자: contracts 에이전트(루프·실행기 구현과 분리)
결과: PASS_AFTER_REPAIR

검토 범위: agent_loop.py, runner_v2.py, runtime_v2.py, budget.py, 공통/A0 프롬프트와 B/A0 설정.

- A0는 새로운 문서 목록·방법서·업무·도구 계약으로 시작한다. B의 선택 페이지나 직전 실행 답변을 초기 컨텍스트로 받지 않는다.
- Responses function_call의 call_id와 결과를 대응시키고 reasoning/encrypted_content 항목을 다음 요청에 보존한다. parallel_tool_calls=False이며 중복 ID·한 응답 다중 도구·도구 없는 종료는 추가 재시도 없이 구별된 실패로 남긴다.
- 모델 PREPARE 또는 예산 예약 침범으로 FINALIZING에 들어가며 COMMIT만 노출한다. 수치/주장/판단/근거위치/요청 상태를 형식수정으로 변경할 수 없다.
- B 정상경로의 공통 도구 22회, A0 실제 선택 actor와 program_commit 동기화 actor를 모의 응답으로 검증했다.
- 원본 응답·usage·실패 사유·현재 snapshot·원장·계산이 보존된다. 실제 API 거부·불완전·사용량 누락을 정상 제출로 바꾸지 않는다.
- 실행별 새로운 컨텍스트와 PRIVATE_GOLD sentinel 미전달 검사를 확인했다.

발견 및 수정:

1. 탐색 중 등록 형식수정을 최종 제출 후 수리와 같은 REPAIR 예약으로 취급해, 아직 필요한 최종화 예산을 사용할 수 있는 경계를 발견했다. root가 EXPLORATION_REPAIR를 도입해 최종 입력 추정치·8,500 출력·모델1회·도구3회·120초를 보존하도록 수정했다. 독립 테스트에서 시간/모델/도구/출력/입력의 각 경계를 호출 전에 차단함을 확인했다.
2. 형식수정을 이미 소비한 뒤에도 관찰 guard가 도구4회를 고정 예약하던 경계를 3+남은수리횟수로 고쳤다.
3. 3차 검토자가 발견한 최종수리 결과 context.json 누락의 수정도 독립 재현 테스트로 확인했다.

검증: `python -m pytest -q tests/test_d4_independent_review.py tests/test_agent_loop_v2.py tests/test_budget_v2.py tests/test_runtime_v2.py` — 34 passed.
독립 추가 파일 `tests/test_d4_independent_review.py`는 예약 경계 5개, 시간 상한 1개, 비정상 도구호출 2개, 최종컨텍스트 보존 1개를 검사한다.

한계: 이 검토는 모의 모델과 결정론적 불변조건 검사다. 실제 Terra 응답 품질, 실제 호출 호환성, 새 개발 성적은 D5 기록으로 별도 확인해야 한다.
