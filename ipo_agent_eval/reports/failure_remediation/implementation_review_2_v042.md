# v0.4.2 구현 2차 후속 검토

판정: **PASS_OFFLINE_AFTER_REPAIR**. 탐색 응답 상한·계산 사용 3분기·명시 분모 선택 우선순위를 독립 검토했다. production source는 읽기만 했고 tests/report만 추가했다. API 호출은 없다. 최종 FIX_v042 실행 성공과 내용 정확도는 별도 검토 대기다.

공통 계산 사용 schema는 기존 validator의 세 상태를 생성 전에 명시한다. USE는 숫자 문자열·replacement_id=null·unresolved=false, REJECT는 대체 ID·unresolved=false 또는 대체 없음·unresolved=true다. 실제 계산 ID 선택, USE/REJECT 결정, 설명과 판단은 모델이 한다. 원래 REVIEW_V2와 의미 검증기는 바뀌지 않았고 현재 snapshot·OK 상태·Decimal 값·대체 ID 실재 여부를 계속 검증한다. 형식 patch가 모순된 판단 상태를 바꿔 성공시키지도 않는다.

분기마다 객체를 복사하고 실제 바꾸는 leaf를 교체한다. 공용 S/ID/DECIMAL의 alias를 제자리 변경하지 않으며 다른 문자열·blocking boolean으로 제한이 번지지 않는다. B text review와 A0 최종 도구가 같은 동적 schema를 쓰고 legacy flag=false는 기존 계약을 반환한다. 실제 API에서의 생성 결과는 새 실행으로 확인해야 한다.

계산기의 _selected는 먼저 정확한 field/entity의 명시 SELECTION을 따른다. share_count가 선택된 경우 reported_share_count·derived_share_count의 개별 보존 선택 때문에 다시 모호해지지 않는다. 명시 share_count가 UNRESOLVED이면 사용 가능한 alias가 있어도 None을 유지한다. 정확한 역할 선택이 없으면 기존 alias/fact fallback과 다중 후보의 UNAVAILABLE를 유지한다. 코드는 모델 대신 분모를 새로 선택하지 않는다.

공시 100,000주·파생 200,000주가 공존하는 synthetic 회귀에서 모델이 공시를 고르면 주당 5,000원, 파생을 고르면 2,500원이며 sensitivity도 같은 선택을 따른다. 이전 snapshot은 계속 UNAVAILABLE이고 두 원래 값은 보존된다. DTS B의 관측에는 canonical share_count 선택 자체가 없었으므로 그 실행을 이 코드 결함만으로 설명하지 않는다. 검토 중 발견한 추가 결함은 명시 선택을 추가해도 이전 코드가 모호하다고 처리했다는 점이다.

B/A0 설정은 condition 외 동일하다. 단일 탐색·B 추출 상한은 9,000이며 총 출력 24,000·입력 800,000·회당 $1.25·model 24·tool 40·900초는 유지한다. 추가 독립 테스트에서 최종+repair 11,500 예약을 확인했다. 이미 출력 8,000을 쓰면 탐색 한도는 4,500, 별도 unknown 출력 예약이 1,500이면 3,000으로 줄며 9,000을 그대로 요청하면 OUTPUT_RESERVATION으로 거절된다. 상한 확대가 총량을 우회하지 않는다.

검증은 두 겹으로 수행했다. 3분기·budget·patch·runtime·실제 runner 통합 관련 97개가 5.99초에 통과했다. 마지막 분모 변경까지 포함한 calculations/contracts/3분기/budget/runner/독립 검증 90개가 7.50초에 통과했다. 두 집합은 중복되므로 합산하지 않는다. 핵심 alias·의미 변경 거부·실제 current snapshot·raw 보존 검증이 유지된다.

이전 DIAG_v040·DIAG_v041·FIX_v041의 실제 13개 시작 실행, plan/results와 동결 source 489개 파일은 intermediate_attempts_manifest.json으로 추가 잠갔다. 초기 검증 위반은 0이다. FIX_v041은 3 SUBMITTED·2 FAILED·7 NOT_STARTED이며 중단된 complete=false 상태 그대로 보존한다. 새 FIX_v042의 성능 분모에 섞지 않는다. 기존 v032 이전 원본 baseline 1,914개도 별도로 유지한다.

남은 제한은 실제 응답 길이·원문 해석·판단 정확도·도구 선택이다. 9,000토큰이 모든 등록을 보장하지 않고, 구조화 USE가 옳다고 계산 입력이나 방법론까지 옳은 것은 아니다. 최종 12회 실행 검증, F/K/J 및 근거 내용 검토, 종합 3회와 최종 보존은 아직 미완료다.
