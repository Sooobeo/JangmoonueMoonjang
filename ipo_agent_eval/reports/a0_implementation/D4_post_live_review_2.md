# D4 실제 호출 후 수정 독립 2차 검토

검토자: preservation_review. 판정: **PASS**.

`response_input.py`와 `runtime_v2.py`의 전송 변환을 검토했다. 실제 HTTP 400이 발생했던 `20261113T101439Z_A0_46ef2e9a/06_explore_request.json`의 13개 이력 항목을 변환해 순서와 ID, call_id, 이름, 원문 arguments 문자열, 도구 출력, summary, encrypted_content, 역할, nonempty content를 각각 대조했다. 빠진 항목이나 의미 필드 변경이 없다. 제거된 값은 function_call의 선택적 null namespace/상태와 reasoning의 빈 content/null 상태뿐이다. 변환은 깊은 복사본을 반환하며 원본 raw/context를 수정하지 않는다. 이전 중단 배치에서 동결한 81개 실행·계획 파일 해시가 검토 전후 일치했다.

공식 OpenAI 문서는 stateless 호출에서 모든 출력 항목과 reasoning, assistant phase를 순서대로 이어 붙여 전달하도록 설명한다. 구현은 해당 이력을 보존하고 알 수 없는 non-null 필드나 항목 유형은 오류로 중단한다. 암호화된 reasoning 문자열은 해석하거나 편집하지 않는다. 확인한 근거는 [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)와 설치된 SDK 2.33.0의 Responses 입력 TypedDict다. SDK 타입의 허용 필드만으로 서버 수락을 보장한다고 주장하지 않는다.

독립 재실행에서 adapter·runtime·agent loop·D4 회귀 **33개가 통과했다(7.12초)**. SDK 모양의 응답을 반환하는 mock은 원본 기록과 다음 요청의 call_id/암호문/인자 연결을 검증한다. 추가 사례는 nonempty reasoning content, assistant phase, 알려지지 않은 타입, null content, 안전한 API 오류 경로 기록을 검사한다. 원시 예외 메시지나 본문은 기록하지 않고, 사용량 없는 실패 호출은 unknown으로 남긴다.

root가 수행한 실제 호환성 probe의 요청 input이 독립 변환 결과와 동일함을 확인했다. 서버는 입력 17,263·출력 16토큰을 반환했다. 의도적인 16토큰 상한으로 incomplete였고 도구 실행 0회, 연구 실행 아님, 최종 검토 없음이다. 이는 이 요청의 전송 호환성 확인이며 기업 분석 성공 결과가 아니다. 기존 실패 로그에는 param이 없어 어떤 개별 필드가 거절됐는지는 소급 확정하지 않았다. 자세한 원본 대조와 probe 요약은 `D4_post_live_review_2.json`에 있다.

0.3.1 대비 B/A0 설정 변화는 version/change_note뿐이고 두 조건의 상한과 모델·프롬프트는 유지됐다. 배치 실행기의 STOP 처리는 실행 사이에서 완료된 시도와 남은 계획을 보존하고 종료한다. 0.3.2는 새 계획·소스로 동결되어 이전 실패·중단 결과와 구분된다. 이 검토자는 유료 API를 추가 호출하지 않았다.
