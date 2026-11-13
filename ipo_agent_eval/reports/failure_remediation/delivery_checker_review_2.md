# 최종 전달 검사 도구 2차 검토

판정: **PASS_OFFLINE_AFTER_REPAIR, 최종 FIX_v042 실행 검증은 대기**. 처음에는 root가 작성한 검사 도구를 독립 검토했고, 아래 결함을 전달한 뒤 root의 명시적 위임으로 검사 도구와 경계 테스트만 보완했다. 따라서 수정 부분은 구현자 검증이며 다른 검토자의 교차 확인을 요청했다. production runtime·config·prompt·동결 소스는 바꾸지 않았고 API도 호출하지 않았다.

기존 검사에는 세 가지 허위 통과 경로가 있었다. SUBMITTED 행의 directory가 null이면 실패 없이 건너뛸 수 있었다. 실행 ID/폴더의 중복과 행·저장 summary의 기업/조건/반복 일치 여부를 확인하지 않았다. 과거 snapshot의 sensitivity 호출과 다른 현재 계산 하나만 있어도 실제 현재 snapshot의 민감도 성공으로 판정할 수 있었다.

새 검사는 정확한 여섯 기업×B/A0×반복 1회를 확인하고 미완료·미실행·경로 누락을 통과시키지 않는다. run_id/디렉터리는 고유해야 하며 row·summary·case registration·실제 read packet의 기업 ID가 일치해야 한다. 원본 API 응답과 별개인 plan/summary의 완료 문구만 믿지 않는다.

해당 조건의 actor가 최종 snapshot을 실제 등록했고 같은 snapshot에서 EVALUATE와 sensitivity의 OK 결과를 각각 하나 이상 반환했는지 확인한다. 개별 UNAVAILABLE 계산은 허용하되 그 기능 전체를 성공으로 간주하지 않는다. 저장된 계산은 실제 tool_call의 결과와 같아야 하며 review는 두 기능의 현재 성공 결과를 각각 USE로 연결하고 같은 Decimal 값을 적어야 한다.

실제 성공한 read_source 결과와 source_packet/read history를 대조하고, 등록값·계산·최종 검토의 모든 증거 좌표가 실제 읽은 같은 문서/쪽인지 확인한다. 최종 원장의 기록과 버전이 다르거나 OPEN 요청을 빠뜨린 검토도 거절한다. 이는 위치·연결 검증이며 그 원문이 주장 내용을 의미적으로 지지하는지는 별도 사람 검토가 필요하다.

모델/도구 시도 수는 events와 맞아야 한다. 원시 request마다 response 또는 error 하나가 있고, 알려진 usage 합계가 summary와 같은지 확인한다. usage 미확인은 null 총비용과 양의 별도 예약을 유지해야 한다. 실제+미확인 예약의 모델/도구/입력/출력/시간/비용 상한을 검사한다. 청구액을 확인한 것으로 표현하지 않는다.

리뷰 검사는 diagnosis/implementation/execution/overall 네 단계 각각 1·2·3차 완료와 실제 해시가 있는 보고서를 요구한다. 빈 단계나 완료 flag만으로 통과하지 않는다. 원래 보존 검사와 모든 참조 해시 확인도 유지한다. 검사 자체는 결과·원본 파일을 쓰지 않으며 동적 import의 bytecode 생성도 억제한다. CLI 출력은 manifest의 해시 참조 대상에 넣지 않아 순환을 피한다.

초기 synthetic 경계 테스트 17개가 10.70초에 통과했다. contracts의 독립 검토에서 실제 성공 COMMIT 증거를 요구하지 않는 공백을 추가로 발견해 보완했고 19개가 통과했다. 진단·중단 실행 및 호환성 probe 보존 검사를 추가한 검증은 20개, FIX_v042 중단 원본 보존까지 포함한 최종 검증은 **22개가 12.51초에 통과**했다. 완전한 12개 가짜 artifact는 정상 통과하고 경로 없음·중복 폴더·기업 불일치·부분 배치·review 없음·과거/실패 민감도·잘못된 등록 actor·미열람 인용·read 기업 불일치·usage 변조·OPEN 누락·비어 있는 리뷰 단계·증거 없는 완료 flag·unknown 0처리·cap 위반·승인되지 않은 COMMIT·잘못된 원장 동기화 phase·중간실행 보존 manifest 누락은 실패한다. 테스트에서는 API를 호출하지 않았다.

최종 snapshot의 실제 COMMIT 성공은 정확히 한 번이어야 한다. 허용 actor와 FINALIZING/REPAIR phase, submission_id, SUBMITTED 결과와 상태 전이, 최종 내용 상태를 확인한다. program_commit의 요청·이관 동기화도 각 한 번이며 최종 원장과 COMMIT 결과가 같아야 한다. summary의 SUBMITTED라는 문구만으로 이를 대신할 수 없다. 추가 보완 후 DIAG_v041의 실제 네 실행에 대해 이 검사도 다시 통과했다.

비용은 frozen config 요율과 raw usage로 알려진 표준 추정·1.25 입력 단가 예약·미확인 예약을 다시 대조한다. 완료된 진단·중단 13개 실제 실행의 489개 파일과 별도 synthetic API 호환성 probe 8개 파일, FIX_v042 중단 4개 실행의 164개 파일, 총 661개 추가 원본도 검증한다. 이 probe는 회사 답변이나 최종 paired 성능 횟수에 포함하지 않는다.

추가로 DIAG_v041의 실제 네 실행을 읽기 전용 감사했다. 개별 실행 검사 네 개와 원본 보존은 모두 통과했지만, 정확히 여섯 기업×B/A0인 최종 배치가 아니므로 `Expected exactly six fresh B/A0 pairs` 한 사유로 거절했다. diagnostic subset을 최종 성공으로 세지 않는 의도된 결과다.

FIX_v041·FIX_v042는 중단된 별도 배치로 보존한다. 최종 검증 대상은 후속 FIX_v043으로 전환 예정이며, 12개 실행과 보고서가 갖춰지기 전에는 execution/overall 완료로 기록하지 않는다. 실제 최종 label의 `--skip-review-checks` 실행 검증과 최종 리뷰가 모두 끝난 뒤 전체 manifest 검증을 수행해야 한다.
