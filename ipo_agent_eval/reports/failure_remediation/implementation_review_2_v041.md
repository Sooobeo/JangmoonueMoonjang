# v0.4.1 구현 2차 후속 검토

판정: **PASS_OFFLINE_AFTER_REPAIR**. root의 v0.4.1 변경을 읽고 tests/report만 수정했다. 실제 API는 호출하지 않았으며 실제 업무 완료 판정은 대기다.

B는 REGISTER와 COMMIT에서 fatal 격리 위반을 받으면 즉시 실패한다. 이전 IR2-02 재현 두 개의 xfail을 제거했고 모델 호출이 각각 1/2회, format repair 0회, review artifact 없음으로 통과했다. 외부 자료 접근·제출 방어뿐 아니라 불필요한 repair 호출도 중단한다.

동적 missing_inputs.field의 enum은 새 leaf 객체에 넣는다. deepcopy가 보존하는 shared string 객체의 alias를 직접 변경하지 않으므로 본문·doc ID·claim ID 등으로 enum이 퍼지지 않는다. 실제 UNRESOLVED 집합의 schema 제한과 서버 검증은 계속 유지된다. contracts의 14개 문자열 경로 및 새 schema 불변 회귀를 교차 확인했다.

공통 prompt는 기존 등록기의 같은 scope/basis/source_snapshot_id와 필요한 as_of 계약을 설명한다. 실제 원문 기준이 같은 경우만 같은 표기를 쓰며 다른 기준을 통과 목적으로 맞추지 말라고 명시한다. DERIVATION 출력은 별도 null VALUE로 중복 작성하지 않는다. synthetic 예시를 실제 변환·등록기에 넣어 입력 P/S만 등록되고 M=100백만원의 파생 fact와 DERIVABLE 선택이 생성됨을 추가 검증했다. 이 예시는 실기업 정답이나 A0 행동 순서를 제공하지 않는다.

B/A0는 condition 외 설정 차이가 없고 새 공통 입력 한도 800,000·회당 $1.25를 사용한다. 모델/reasoning은 같다. prompt와 상한을 함께 바꾸므로 이전 조건과 같은 실험 또는 단일 수정의 인과 효과로 표현해서는 안 된다.

관련 99개 테스트가 10.26초에 통과했고 xfail은 없다. 이후 synthetic 예시 테스트를 추가한 독립 경계+alias 7개 검증은 3.74초에 통과했다. 두 집합은 중복되므로 106개로 합산하지 않는다. source delta는 runner, gateway, 두 config, v2 prompt, pyproject의 6개 파일이며 runtime/budget/compact/patch 구현을 추가 수정하지 않았다.

root 구현 1차 보고서와 진단 1차 보고서의 한글을 실제 파일에서 확인했다(각 549/402자, U+FFFD 0). 이전 문자 손상·진단 서명 누락은 해소했다. 원래 v0.4.0 2차 보고서는 시점 증거로 그대로 유지한다. 새 해시·테스트·세부 결과는 [implementation_review_2_v041.json](implementation_review_2_v041.json)에 있다.

최종 12회 실행·채점·실행 검토 3회·종합 검토 3회와 최종 보존 확인은 아직 미완료다. DIAG_v041의 통과를 최종 acceptance로 대신하지 않는다.
