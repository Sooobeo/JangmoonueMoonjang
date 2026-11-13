# v042 후속 구현 독립 검토 3차

검토 결과: **PASS — 실제 API 및 6×2 실행 검증은 별도**. 이 검토에서 생산 소스는 변경하지 않았다. 검토자는 이전 공통 프롬프트 및 실행 드라이버 일부를 작성한 이력이 있어 완전한 맹검 감사는 아니다. 이번 변경의 판단 선택 보존·구조 계약·예산을 독립적으로 확인했다.

v041 중단 배치의 실패 두 개는 다른 원인이다. MELCON A0는 첫 등록을 작성하는 탐색 응답이 3,500토큰에서 잘렸고, MELCON B는 최종 계산 USE와 unresolved=true를 동시에 적어 기존 검증기에서 거절됐다. v042는 이 원본을 보존하고 공통 탐색 응답 상한과 생성 계약을 보완한다. 점수나 답변을 사후 수정하는 처리가 아니다.

`ToolGateway.review_schema()`의 세 가지 계산 사용 분기는 기존 `validation_v2.validate_review()` 규칙과 일치한다.

- USE: 숫자 stated_value, replacement_id=null, unresolved=false.
- 대체 가능한 REJECT: replacement_id에 ID, unresolved=false.
- 대체 불가능한 REJECT: replacement_id=null, unresolved=true.

USE/REJECT 자체, 계산 ID, 숫자, 거절 사유, 대체 대상, 업무 판단은 모델이 고른다. 공시 해석이나 독립 자료 확인의 미해결 상태는 judgments.unknowns/requests/escalations에 남길 수 있다. 계산을 USE하면서 그 계산 사용 상태를 미해결이라고 적는 구조 모순만 생성 단계에서 배제한다. 모델이 유효한 계산을 선택했는지, 현재 snapshot인지, 값이 정확한지, 대체 대상이 실제로 존재하는지는 계속 기존 검증기가 판단한다. 강제 등록·자동 EVALUATE·자동 민감도·자동 재검색은 추가되지 않았다. 이 범위는 A0 공통 도구 계약의 사용성 개선이며 선택 경로를 프로그램이 지정하는 A1 개입으로 보지 않는다.

공유 schema에 대한 예전 enum 오염의 재발 여부를 검사했다. 분기 별 leaf를 새 dict로 교체하며 공용 ID/DECIMAL/S 사전을 제자리 변경하지 않는다. synthetic gateway 두 개로 UNRESOLVED 0→1 상태와 별도 gateway의 0 상태를 확인했다. 허용된 missing_inputs.field 한 위치만 applied_per enum을 가진다. 반환 schema의 reason을 임의 변경해도 다음 반환값·다른 gateway·전역 REVIEW_V2는 변하지 않는다.

독립 검증은 USE/REJECT × replacement 유무 × unresolved true/false × stated_value null/숫자의 **16조합**을 검사했다. 기존 규칙상 유효한 5조합만 생성 schema를 통과했다. `pytest`의 remediation integration, wire contract, gateway v2, contracts v2는 **104 passed**였다. 한 실행 출력의 설명용 matrix_checked 상수는 24로 잘못 표시했으나 실제 루프는 2×2×2×2=16회이며 이 보고서는 실제 검사 수를 기록한다. 소스 수정이나 API 호출 없이 수행했다.

B/A0 config는 condition만 다르며 버전은 0.4.2-dev다. exploration_output_max=9,000, extraction_output_max=9,000이고 총 출력24,000·입력800,000·모델24·도구40·시간900초·비용상한1.25달러는 유지된다. 기존 exploration_output_limit가 잔여 출력에서 최종·보정11,500토큰 예약을 차감한다. 이미 출력5,000을 사용하면 다음 탐색 상한7,500, 사용10,000이면2,500, 사용12,500이면0으로 축소된다. 따라서 개별 상한 증가가 총량 제한을 우회하지 않는다. 다른 입력·시간·비용 예약도 그대로 적용된다.

남는 제한은 분명하다. 더 큰 상한은 등록 응답 잘림의 위험을 줄일 뿐 실제 응답이 상한 안에 끝난다거나 EVALUATE·민감도·최종 제출을 모두 수행한다고 보장하지 않는다. 구조가 유효해도 이익 기간·분모·비교기업 판단·외부 요청의 타당성은 별도 내용 검토가 필요하다. 실제 FIX_v042 원본을 실행별로 확인하고 실패는 보존해 분리 집계한다.

## 동결 전 추가 변경: 계산 역할 선택

DTS v041 B의 주당 계산 미실행을 조사하면서 `_selected()`의 별도 결함이 확인됐다. 기존 구현은 canonical share_count 선택이 명시돼도 reported_share_count/derived_share_count의 개별 선택이 함께 있으면 전체 후보가 여러 개라는 이유로 None을 반환할 수 있었다. 이는 모델의 정확한 역할별 결정을 무시한다. v042는 요청한 정확한 field/entity의 명시 선택을 먼저 따르며, 이 선택이 UNRESOLVED이면 다른 alias 값으로 자동 대체하지 않는다. 정확한 선택이 없을 때만 기존 alias 및 단일 사실 fallback을 그대로 사용한다. 모델이 실제로 canonical 선택을 누락한 옛 실행은 사후 보정하지 않는다.

추가 독립 검증에서 상충하는 공시 분모20과 합산 분모10을 **둘 다 보존한 synthetic snapshot**으로 EVALUATE 주당가액과 sensitivity baseline을 함께 확인했다. (1) alias 선택 둘만 있으면 UNAVAILABLE, (2) 모델이 canonical 역할에 공시20을 명시하면10,000,000, (3) 같은 역할을 명시 UNRESOLVED로 바꾸면 다시 UNAVAILABLE, (4) 파생10을 명시하면20,000,000이었다. 변경 전 snapshot은 각각 별도 ID로 남고 공시·파생 값도 모두 유지됐다. 결과는 `v042_role_selection_review_3.json`에 기록했다. 처음 만든 검사 fixture의 coverage claim ID 누락은 fixture에서만 수정했으며 생산 코드 문제로 분류하지 않았다.

공통 프롬프트는 역할 이름과 명시 방법을 설명하며 어느 분모를 고를지는 지정하지 않는다. 따라서 이 추가 수정도 자동 정답 선택이 아니라 모델이 내린 선택을 계산기가 정확히 따르게 하는 계약 보완이다. **추가 변경 검토 결과 PASS**, 실제 원문 적합성과 제출 성공은 이후 12회 실행에서 따로 검증한다.
