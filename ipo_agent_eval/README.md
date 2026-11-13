# IPO B/A0 개발 비교

공개 투자설명서의 과거 실적 PER 산정 근거를 GPT-6.1 Terra로 검토한다. B는 프로그램이 조회·추출·계산·제출 순서를 정하고, A0는 모델이 같은 공통 도구에서 다음 행동을 선택한다. 두 조건은 같은 모델·추론 설정·공개 입력·계산 계약·자원 상한을 사용한다.

2026년 11월 13일 기준, [파일럿 보완과 A0 상세설계](../whole%20plan/IPO_파일럿보완_A0_상세설계.md)의 **D0~D6 구현·실제 개발 비교·A1 인계, 단계별 세 차례 검토와 전체 세 차례 종합 검토를 마쳤다.** 모의 검증과 무료 사전 점검 통과를 실제 모델 성능 개선으로 집계하지 않는다.

현재 개발 설정은 `0.4.3-dev`다. 저장·검증 계약은 `extraction_v2/review_v2`를 유지하고 모델 전송에는 손실 없는 `compact_v2`, 형식 수정에는 `patch_v1`을 쓴다. [실패 보완 기록](reports/failure_remediation/)에서 새 진단·실행·보존 검토를 관리한다. [최초 구현 결과](reports/a0_implementation/implementation_report.md)와 [사례 배정표](reports/a0_implementation/case_roster.md)는 이전 기록으로 보존한다. 평가 후보의 본 실험, A1 구현, 독립된 사람 채점은 이후 단계다.

이전 `0.3.2-dev`의 실제 12회는 유효 제출 2회·실패 10회였으며, 제출한 답안도 등록·계산이 없었다. 이 결과와 당시 회귀 284개 통과 기록은 바꾸지 않는다. 실패 보완의 `DIAG_v040`은 제출 2회·실패 2회, 후속 `DIAG_v041`은 4회 모두 등록·계산·민감도 분석·제출을 완료했다. 전체 검증 `FIX_v041`에서 단일 탐색 출력 한도와 USE 상태 조합의 경계가 추가로 드러나, 제출 3회·실패 2회·미실행 7회로 중단 기록을 보존했다. 이 경계를 수정한 `FIX_v042`의 6기업 × 2조건 전체 검증을 준비 중이다. 설정·상한을 바꾼 새 개발 실행이므로 예산 확대와 다른 변경의 효과를 분리해서 입증한 실험은 아니다.

## 준비와 실행

Python 3.11 이상을 사용하고 이 `ipo_agent_eval` 폴더에서 실행한다.

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
python -m ipo_eval.runner --help
```

`--live`가 없으면 API를 호출하지 않는 무료 사전 점검이다. 기본 사례는 `HDMS-DEV-01`, 기본 조건은 B다.

```powershell
python -m ipo_eval.runner --condition B --case-id HDMS-DEV-01
python -m ipo_eval.runner --condition A0 --case-id HDMS-DEV-01
```

| 기업 | case_id |
|---|---|
| HD현대마린솔루션 | `HDMS-DEV-01` |
| 멜콘 | `MELCON-DEV-01` |
| 디티에스 | `DTS-DEV-01` |
| 신성에스티 | `SHINSUNGST-DEV-01` |
| 에이엘티 | `ALT-DEV-01` |
| 밀리의서재 | `MILLIE-DEV-01` |

실제 모델 답변은 명시적으로 `--live`를 붙여 요청한다.

```powershell
python -m ipo_eval.runner --condition B --case-id MELCON-DEV-01 --repeat 1 --live
python -m ipo_eval.runner --condition A0 --case-id MELCON-DEV-01 --repeat 1 --live
```

`--repeat`는 1 이상의 **반복 식별 번호**다. `--repeat 2`는 두 번 실행하라는 뜻이 아니라 반복 번호 2의 새 실행 한 건을 만든다. 호출할 때마다 새 실행 ID와 컨텍스트를 사용한다. 답변을 본 뒤 유리한 결과만 남기는 재실행은 하지 않는다.

인증값은 현재 프로세스의 `OPENAI_API_KEY`, `ipo_agent_eval/.env`, 프로젝트 최상위 `.env`, Windows 사용자·시스템 환경변수 순서로 확인한다. 키는 로그에 저장하지 않으며 `.env`는 Git 추적 대상에서 제외한다. 실제 호출은 `gpt-6.1-terra`, `reasoning_effort=medium`, SDK `max_retries=0`을 사용한다. 실행기는 HTTP 500/502/503/504에만 동일 요청을 최대 한 번 재시도하며 모든 시도와 미확인 사용량 예약을 기록한다. 400·한도/잔액 오류·거부·불완전 답변을 임의 재요청하지 않는다.

## B와 A0의 실행 흐름

두 조건은 `search_corpus`, `read_source`, `calculate`, `sensitivity`, `request_information`, `escalate`, `submit_review`를 공유한다.

B는 기존 다섯 검색에 주식수 구성, 비교기업 원입력, 이익 문맥 검색을 더해 **여덟 검색을 모든 기업에 같은 순서로** 수행한다. 각 검색의 상위 두 쪽과 앞뒤 한 쪽을 전체 페이지로 읽고 중복을 제거한다. 모델이 추출한 레코드를 한 번 등록한 뒤 계산·민감도를 실행하고 J1~J4 검토를 받는다. 검색 결과가 모두 있는 정상 경로의 실제 도구 호출은 22회이며 통상 모델 호출은 추출·검토의 두 번이다. `actor=program_fixed`는 프로그램이 고른 행동이다.

A0는 문서 목록·자료 마감·공통 방법서·업무·도구 계약에서 시작한다. 모델이 검색→열람→작은 레코드 묶음 등록→계산→재조회 등의 순서를 선택한다. `parallel_tool_calls=False`로 한 행동씩 관찰하고, 같은 실행의 응답·reasoning 항목과 `call_id`에 대응하는 결과를 보존한다. B의 선택 페이지나 과거 답변은 초기 입력으로 전달하지 않는다. `actor=model`은 실제 모델이 선택한 도구 행동이다.

모델이 `PREPARE`를 선택하거나 다음 탐색이 예약 예산을 침범하면 최종화로 넘어간다. 최종화에서는 현재 스냅샷의 근거·계산·미확인 사항으로 `COMMIT`만 제출한다. 최종 요청·이관 동기화 두 회는 `actor=program_commit`으로 계상한다. 요청과 이관은 기록만 하며 외부 메시지를 보내거나 사람이 검토했다고 표시하지 않는다.

## 입력·계산·제출 계약

값은 십진수 문자열 또는 `null`이며 공시값·파생값·미확인·적용 불가를 구분한다. 0은 원문에 명시된 값일 때 공시값으로 기록한다. `CONTEXT`, `VALUE`, `SHARE_COMPONENT`, `PEER`, `DERIVATION`, `SELECTION`, `COVERAGE`의 일곱 레코드 종류를 사용한다.

주식수는 구성 수량과 `INCLUDE/EXCLUDE/UNRESOLVED`를 따로 등록한다. 완전성 선언과 필요한 포함 수량이 갖춰지면 전체 합계를 계산하고, 그렇지 않으면 완전 합계는 `null`, 확인된 부분은 `partial_sum`으로 남긴다. 구주매출을 증가분에 더하지 않으며 옵션을 무조건 포함하지 않는다.

직접 시가총액이 없어도 같은 기준의 주가·주식수로 파생 계산할 수 있다. 직접값과 파생값이 함께 있으면 원본·차이·선택 이유를 보존한다. 계산기는 허용된 Decimal 산술과 명시된 문맥의 정합성을 검사하며 원문 해석이나 경제적 선택이 맞는지 자동 채점하지 않는다.

레코드 묶음 등록은 원자적으로 검증하고 새 불변 `input_snapshot_id`를 만든다. 계산에는 해당 스냅샷, 입력 fact ID, 식, 결과, 단위, 상태와 원문 근거가 연결된다. 최종 `calculation_uses`의 `USE` 수치는 그 계산의 Decimal 결과와 같아야 한다. 과거 계산의 명시적인 `REJECT`는 이유와 대체 값 또는 미해결 상태를 남긴다.

검색 발췌와 실제 열람은 별도 기록이다. 인용은 `read_source`에서 실제 받은 허용 페이지에 한정한다. `page`는 첫 장부터 세는 물리 PDF 쪽 번호이고 `printed_page`는 확인된 문서 바닥의 쪽 번호다. 공개 코퍼스 밖 경로·다른 기업·기준표·기존 답변·자료 마감 이후 문서 접근은 차단한다.

형식수정은 등록과 최종 제출을 합쳐 전체 실행에서 최대 한 번이다. 전체 답안을 다시 쓰지 않고 허용된 빈 필드·여분 키·정수 표기·기존 주장과 출처의 ID 연결을 patch로 고친다. 수치·주장·판단·출처 위치·요청 상태·배열 구성은 변경할 수 없다. 탐색 중 형식수정에도 최종화 예산을 남긴다. 자연어 결론의 의미적 모순을 자동 교정하는 A1 기능은 공통층에 포함하지 않는다.

도구 관찰에는 현재 등록 ID·계산 ID·미해결 의존성·예산 사용량과 예약을 제공한다. 다음 행동은 A0가 고른다. 최종 `missing_inputs`는 실제 등록된 UNRESOLVED selection과 정확히 일치해야 하며, 그 밖의 미열람·업무상 미확인은 unknowns와 요청에 구분해 쓴다.

## 비용과 실행 상한

`config/B.json`과 `config/A0.json`에 같은 공통 상한을 둔다. 아래 단가·환산값은 프로젝트 예산 설정이며 청구서 금액이 아니다.

| 항목 | 현재 개발 설정 |
|---|---:|
| 모델·추론 | `gpt-6.1-terra / medium` |
| 모델 호출·도구 호출 | 24회·40회 |
| 누적 입력 목표·누적 출력 상한 | 800,000·24,000토큰 |
| B 추출 출력 | 최대 9,000토큰 |
| A0 탐색 출력 | 한 응답 최대 9,000, 초기 총 여유 12,500토큰 |
| 최종화·형식수정 출력 예약 | 10,000·1,500토큰 |
| 형식수정 입력 예약 | 16,000토큰 |
| 전체 시간 | 900초 |
| 최종화·형식수정 시간 예약 | 120·60초 |
| 실행 비용 상한 | 1.25달러 |
| 예산용 환율 | 1달러당 1,400원 |

출력에는 추론 토큰도 포함된다. 현재 이력·최종 스키마·예정 도구 결과를 포함해 입력과 비용을 예약한다. 입력은 `o200k_base`로 사전 추정하고 매 응답의 실제 usage를 누적한다. 비용 상한에는 입력 캐시 쓰기의 1.25배 가능성도 반영한다. 예약은 완료 보장이 아니며 실제 사용량이 한도를 넘거나 시간이 부족하면 실패를 보존한다. 사용량이 확인되지 않은 요청의 총비용은 `null`과 `usage_unknown=true`로 남긴다.

초기 `0.3.0-dev`의 상위 세 쪽 검색은 멜콘의 전체 페이지를 포함할 때 예약 입력 추정이 188,922토큰으로 상한을 넘었다. 실제 답변을 받기 전에 **모든 기업과 B/A0 공통 검색 상한을 1~2로 조정한 `0.3.1-dev`**를 적용했다. 여덟 검색과 전체 페이지 열람, 모델·토큰·비용·시간 상한을 유지했다. [조정 근거](reports/a0_implementation/retrieval_budget_adjustment.md), [초기 점검](reports/a0_implementation/D3_preflights_initial.json), [조정 후 점검](reports/a0_implementation/D3_preflights_v031.json)을 보존한다. 열람 도구 자체는 한 번에 chunk ID 최대 3개, 이웃 0~1쪽, 중복 제거 후 최대 9쪽이다.

## 실행 상태와 저장 파일

각 실행은 `runs/<UTC날짜>_<B또는A0>_<고유번호>/`에 저장한다. UTC는 한국시간보다 아홉 시간 느리다.

| 상태 | 의미 |
|---|---|
| `PREFLIGHT_COMPLETE` | 무료 준비 점검 완료. 실제 모델 답변 없음 |
| `PREFLIGHT_BLOCKED_BUDGET` | 고정 실행 계획이 예산 예약을 통과하지 못해 API 호출 전 차단 |
| `NOT_STARTED_MISSING_API_KEY` | 키가 없어 실제 실행을 시작하지 못함 |
| `SUBMITTED` | 유효한 제출 계약을 통과함. 정답 판정과 별개 |
| `FAILED` | 실행을 완료하지 못한 사유와 확보된 원본 기록 보존 |

제출 내용의 상태는 별도로 `READY`, `PENDING_INFO`, `HUMAN_REVIEW`를 기록한다. 미해결 blocking 이관이 우선하고 그다음 정보 요청이다. 이전 OPEN 항목은 최종 목록에서 생략해도 원장에 남는다. `READY`는 정답이나 투자 판단 승인이라는 뜻이 아니다. 무효 제출의 내용 상태는 `null`이다.

| 파일 | 내용 |
|---|---|
| `config.json`, `environment.json`, `input_hashes.json` | 설정·패키지·코드·공개 입력의 실행 당시 식별값 |
| `events.jsonl` | 상태 전이, actor, 모델·도구 호출, 예산 예약, 실패 사유 |
| `*_request.json`, `*_response.json` | API 요청과 원본 응답·반환 모델·usage |
| `source_packet.json`, `retrieval_history.json` | 실제 받은 전체 페이지, 검색·열람 기록 |
| `snapshots.json`, `extraction.json` | 등록 레코드의 모든 불변 스냅샷과 현재 논리 입력 |
| `calculations.json` | 계산 ID·입력·결과·근거와 미계산/배제 대상 기록 |
| `request_ledger.json` | 요청·이관의 현재 상태와 버전별 이력 |
| `context.json` | A0의 실제 응답 항목과 관찰을 누적한 컨텍스트 |
| `review.json`, `review.md` | 유효한 최종 제출이 있을 때의 답변 |
| `summary.json` | 실행/내용 상태, 호출·사용량·시간·비용·실패 요약 |

## 검증과 기존 파일럿 보존

모의 검증은 v1 호환, v2 등록·근거 전파·산술, 도구 격리, 예산 예약, 요청 원장, A0 성공·미제출·오류·형식수정 경로를 검사한다. 실제 성적 비교는 D5의 새로운 실행 원본과 별도 채점에서 판단한다. 기존 HDMS·멜콘·DTS 파일럿 점수를 새 B 점수로 대신 쓰지 않는다.

기존 입력·PDF·기준표·R001 답변·채점 결과는 [보존 목록](reports/a0_implementation/preservation_manifest.json)과 [추가 보존 목록](reports/a0_implementation/preservation_supplement_phase1.json)으로 관리한다. 이전 코드·설정·문서 사본은 [baseline_source](reports/a0_implementation/baseline_source/)에 있다. [보존 검사 도구](reports/a0_implementation/verify_preservation.py)로 원본과 보존 사본의 해시를 다시 확인할 수 있다.

기존 Python 호출의 호환 경로도 유지한다. `ipo_eval.runner.execute()`에서 `condition`을 생략하면 v1 B 흐름과 `config/B_v1.json`을 사용한다. 기존 v1 추출·검토·계산 계약과 과거 파일을 읽는 코드는 남아 있다. 새로운 B/A0 구현을 Python에서 호출할 때는 `condition="B"` 또는 `condition="A0"`를 명시한다. CLI의 기본값은 이미 v2 B이므로 Python의 호환 기본값과 구별한다.

```python
from ipo_eval.runner import execute

# v1 호환 경로의 무료 점검
old_directory, old_summary = execute(live=False, case_id="HDMS-DEV-01")

# v2 공통 계약을 사용하는 A0 무료 점검
new_directory, new_summary = execute(live=False, case_id="HDMS-DEV-01", condition="A0", repeat=1)
```

과거 결과는 [3기업 파일럿 기록](reports/3기업_파일럿_확장_검증기록.md), [HDMS 첫 답변 설명](reports/HDMS_B_첫답변_설명.md), [R001 AI 대행 채점 검토](reports/R001_대행채점_검증기록.md)에서 확인한다. 과거 HDMS는 `0.1.4-pilot`, 멜콘·DTS는 `0.2.1-pilot` 결과이며 현재 v2 설정으로 재실행한 결과가 아니다.
