# v0.4.2 계산 사용 계약 1차 검토

PASS. FIX v0.4.1 멜콘 B는 USE 7개에 unresolved=true를 동시에 제출해 실패했다. 형식 수정은 의미를 바꾸지 않아 이 모순을 그대로 거부했다.

동적 전송 스키마에 기존 validator의 세 가지 허용 모드를 노출했다. USE는 숫자 문자열·대체 null·미해결 false, REJECT는 사용 가능한 대체 ID 또는 미해결 true 중 하나를 모델이 선택한다. 업무상 불확실성은 judgment/request에 남기도록 공통 설명을 보강했다.

base REVIEW_V2/PAYLOAD는 보존했고 배열 items 전체를 교체했다. 공유 string/Decimal/boolean leaf를 제자리 수정하지 않는다. requests/escalations의 blocking=true도 계속 허용된다. calc ID나 어떤 결과를 사용할지는 강제하지 않는다.

신규 18개와 기존 통합·형식수정·gateway·agent loop를 포함한 108개 테스트 통과(6.60초). 선택 분기 안의 빈 null 추가/여분 키 삭제만 가능하며 USE/REJECT 의미를 고치는 patch는 거부하고 원본을 보존한다. 실제 API 검증은 루트의 새 동결 배치에서 진행한다.
