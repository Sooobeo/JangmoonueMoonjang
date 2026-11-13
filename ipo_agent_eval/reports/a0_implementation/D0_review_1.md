# D0 1차 검토 — 원본 보존 범위

검토일: 2026년 11월 13일 (Asia/Seoul)  
검토자: Codex preservation_review  
대상: 상세설계 11절 D0, 13절 기존 기록 보존

판정: **통과**. 구현 전 기준선을 만들었으며, 원본의 변경·누락은 발견하지 않았다.

보존 목록은 [preservation_manifest.json](preservation_manifest.json)에 저장했다. Git 기준 커밋은 `1102edaa9bc27307500662e40fa6fffd3ef33234`다. 작업 시작 전부터 존재한 수정·미추적 문서는 Git 상태와 실제 파일의 해시로 기록했으며 되돌리지 않았다.

| 확인 범위 | 파일 수 | 검토 내용 |
|---|---:|---|
| 기존 공개·비공개 입력 및 PDF | 124 | 세 기업의 원본 PDF, 공개 코퍼스, 방법서, 비공개 기준표·R001 채점 포함 |
| 기존 runs | 171 | 19개 실행 디렉터리의 요청·응답·결과·실패·사용량 기록 포함 |
| 기존 grading_exports | 346 | 답변·채점 문서와 검증용 렌더 파일 포함 |
| 기존 reports | 22 | 종전 파일럿 보고·비용·검증 기록 포함 |
| 변경 가능한 코드·설정·지시문 등 | 27 | SHA256와 변경 전 사본 보존 |
| 설계 문서 | 8 | SHA256와 변경 전 사본 보존 |

합계 698개이며, 이 중 663개 기존 증거 파일은 바이트 단위로 유지해야 한다. 코드·설계 35개는 작업본을 수정할 수 있으나 [baseline_source](baseline_source)의 변경 전 사본을 유지한다. 새 사례·실행·보고 파일은 추가할 수 있다.

세 기업 PDF, 비공개 `gold.json`, `grade_R001.json`, HDMS `R001_proxy_grade.json`, 실제 HDMS R001 실행 `20261111T233807Z_B_2db53c6b`가 목록에 들어 있는지 확인했다. 비공개 자료는 여기서 보존 대상으로 해시만 계산했으며 실험 모델 입력으로 전달하지 않았다.

초기 검증은 [D0_preservation_initial_check.json](D0_preservation_initial_check.json)에 남겼다. 전체 파일 해시와 35개 사본이 일치했고, 변경·누락·사본 불일치는 0건이었다. `.env*` 및 인증서·비밀 키 확장자는 대상에서 제외했으며 해당 내용은 읽지 않았다. 캐시·심볼릭 링크와 새 산출물 디렉터리 자체도 제외했다.

구현 이후에는 다음 명령으로 원본 보존을 다시 확인한다. 출력 파일은 기존 파일과 다른 이름을 사용한다.

```powershell
python reports/a0_implementation/verify_preservation.py --output reports/a0_implementation/D0_preservation_recheck_01.json
```

이 검토는 D0의 첫 번째 검토다. 나머지 두 검토 및 이후 단계 검토를 대신하지 않는다.

## 후속 검토에 따른 보완

D0 3차 독립 검토에서 프로젝트 폴더 밖 `phase1`의 세 기업 채점기준표와 공통 검토방법서가 최초 목록에서 빠진 점을 발견했다. 이 네 파일은 수정 전 상태에서 [별도 보존 목록](preservation_supplement_phase1.json)에 추가했으며, 최초 manifest를 다시 작성하지 않았다. [보완 후 확인](D0_preservation_supplement_check.json)은 총 702개(변경 금지 증거 667개, 버전 관리 코드·설계 35개) 모두 통과했다. 자동 검사는 이 보완 목록도 필수로 확인한다.
