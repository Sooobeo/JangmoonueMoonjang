# Compact 전송 계약 1차 검토

2026-11-13 · 구현자 자체 검토 · **오프라인 검증 통과, 실제 모델 효과 미검증**

기존 v2 경제 계약을 유지하는 `wire_contract.py`와 회귀 테스트를 추가했다. 루트의 contexts/values/shares/peers/derivations/selections/coverage 배열이 record kind를 나타내므로 모델이 kind/payload 포장을 반복하지 않는다. 약어의 원래 필드명은 스키마 설명과 WIRE_INSTRUCTIONS에 전부 있다. 값·기업·claim·문맥·origin·선택·포함근거는 그대로 모델이 명시한다. evidence의 doc_id/page만 실제 열람 chunk 좌표에서 복원한다.

7종 레코드 왕복 후 원 payload와 불변 snapshot ID/content, 논리 사실, 계산 결과가 같았다. 공시0·미확인·적용불가·직접/파생 불일치·선택 이유를 유지한다. 중복 ID, 누락/추가 키, 미열람·위조 좌표와 정수가 아닌 쪽 번호를 거절한다. 잘못된 파생 수치를 계산 결과로 바꿔 통과시키지 않는다. 입력·원본 계약을 변경하지 않는다. 신규23개와 기존 계약/계산을 합쳐 **71 passed in 4.01s**다.

실패 원본6개 모두 출력5000토큰에 도달했다. 네 기업은 레코드를 쓰다 잘렸고, ALT/MILLIE는 첫 VALUE의 evidence 배열 뒤 각각22,372자/227,869자의 연속 공백이 관찰됐다. [공식 OpenAI 문서](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)는 nested anyOf를 지원한다. 따라서 기존 스키마가 논리적으로 불가능했다고 단정하지 않는다. 새 스키마는 anyOf 분기를 없애고 nullable bookkeeping을 evidence 앞으로 옮겼다.

저장된 완성 레코드 prefix를 동일 값·ID와 양쪽 minified JSON으로 비교하면 전송토큰이10.1~23.2% 줄었다. 스키마 자체는1891→1798토큰이다. prefix는 크기 측정용이며 잘린 답을 복구하거나 제출 데이터로 사용하지 않았다. 이 수치는 완전한 추출이 기존5000토큰 안에 들어가거나 공백 퇴행이 해소되었다는 증거가 아니다. 실제 확인은 별도 새 실행으로 해야 한다.

API: `EXTRACTION_WIRE`, `REGISTER_WIRE_BATCH`, `WIRE_INSTRUCTIONS`, `to_wire_extraction(v2, read_chunks)`, `expand_wire_extraction(wire, read_chunks)`. 변환 후에도 기존 gateway/store 등록 검증을 반드시 거친다. `REGISTER_WIRE_BATCH`는 operation/base_snapshot_id/batch를 받고 batch가 compact 추출 객체다. 반환 v2의 레코드는 kind별로 그룹화되지만 기존 immutable snapshot 의미와 ID는 같다.

[정량 진단](compact_wire_diagnosis.json) · [검토·해시](compact_wire_review_1.json)
