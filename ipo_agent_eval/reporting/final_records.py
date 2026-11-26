"""Append the terminal roster and execution history to the project chronology."""
from collections import Counter
import json
from pathlib import Path

from reporting.main_report import BASE, OUT, fmt, table

MARKER="## W13 본평가 실행과 독립 채점"


def read(p):
    return json.loads(p.read_bytes())


def record():
    results=read(BASE/"analysis/results.json")
    rows=results["issuers"]
    panel=results["overall"]
    time=results["operational_review_timing"]
    cost=results["cost"]
    states=Counter(r["grade_state"] for r in rows)
    grade_text={"sealed":"완료","first_failed":"첫 채점 실패","second_failed":"두 번째 채점 실패",
                "reconcile_failed":"조정 채점 실패","preparation_incomplete":"입력 결측"}
    grade_summary=", ".join(f"{grade_text.get(s,s)} {n}곳" for s,n in states.items())
    records=[]
    for r in rows:
        op=BASE/"terra"/r["case"]
        if r["status"]=="COMPARED":
            status="완료"
        elif (op/"preparation.json").exists():
            status="가림 입력 결측"
        elif (op/"failure.json").exists():
            status="공통 입력·선별 실패"
        else:
            status="순위 완료"
        if isinstance(r["selection_state"],str) and r["selection_state"]=="ranked":
            status="완료"
        if "mandatory" in r:
            get_list=lambda arm:", ".join(v.rsplit("-",1)[-1] for v in r[arm]["operating"]["items"]) or "없음"
            rule,ai=get_list("rule"),get_list("ai")
        elif (op/"ranking.json").exists():
            rank=read(op/"ranking.json")
            rule,ai=(", ".join(v.rsplit("-",1)[-1] for v in rank[a]["operational"]) or "없음" for a in ("rule","ai"))
        else:
            rule=ai="—"
        fallback="—"
        if isinstance(r["selection_state"],dict):
            saved=r["selection_state"]
            method="규칙" if saved.get("fallback")=="rule" else "공통 필수"
            transferred=saved.get("operational")
            ids=", ".join(v.rsplit("-",1)[-1] for v in transferred) if transferred is not None else "자료 없음"
            fallback=f"{method} · {ids or '0건'}"
        records.append([r["issuer"],r["original_count"],"유효" if r["role_a0"] else "결측",
                        "유효" if r["role_c"] else "결측",status,grade_text.get(r["grade_state"],r["grade_state"]),
                        rule,ai,fallback,fmt(r.get("concordance_delta_ai_minus_rule")) if r.get("concordance_delta_ai_minus_rule") is not None else "—"])
    steps=[MARKER,
        f"첫 전송 전에 원본·역할 입력·후보 자료·검사 코드·의존성 버전을 고정했다. 동결 목록 SHA-256은 \u0060{(BASE/'freeze.sha256').read_text().strip()}\u0060이다. "
        f"37곳 전부가 명단에 남았다. A0의 유효 제출은 {sum(r['role_a0'] for r in rows)}곳, C의 유효 제출은 {sum(r['role_c'] for r in rows)}곳이다. ",
        table(["파트","1차 검토","2차 검토","3차 검토"],[
            ["역할·선별","역할별 전송 파일과 응답 ID, 입력과 실제 원문 쪽을 대조했다.","A0와 C의 제시 근거·단위·기간과 이유를 검토했다.","등록 근거, 필수 보존, 같은 한 자리와 실제 배정 목록을 재계산했다."],
            ["맹검 기준표","독립 첫째·둘째 세션, 배정 항목과 허용 쪽을 확인했다.","유효 등급 불일치를 격리해 조정하고 원문 검토가 필요한 항목을 확인했다.","유효한 원판정·인용과 잠근 최종 등급을 대조했다. 실패는 기술적 결측으로 집계했다."],
            ["대행 검토 시간","두 실제 이관 목록에서 중복을 제거하고 항목 배정 순서와 해시를 확인했다.","배정 출처와 기준표가 가려졌는지 확인하고 성공·실패·재시도를 기록했다.","양쪽 공통 항목에 같은 관측을 넣고 양쪽 시간이 모두 있는 기업의 합계를 대조했다."]]),
        f"채점 최종 상태는 {grade_summary}다. 검토 시간 측정은 서로 다른 배정 {time['unique']['assigned_items']}건 중 {time['unique']['timed_items']}건이 유효했다. "
        f"Terra 전송 {cost['attempts']}회 중 확인 사용량은 {cost['known_usage']}회, 미확인·예약은 {cost['unknown_or_pending']}회다. 확인된 표준단가 추정은 {cost['known_standard_usd']:.6f}달러다.",
        "[입력 동결 목록](v1/freeze.json) · [Terra 기업별 원장](v1/terra/) · [독립 기준표 재검산](v1/blind/grading_closure_audit.json) · [고유 항목 시간 측정](v1/timing/) · [역할 근거 원문 검토](v1/role_source_review/)",
        "## W14 분석과 결과 보고",
        f"완전한 기업 쌍은 {panel['complete_pairs']}곳이고 주 순위 비교에 유효한 곳은 {panel['valid_concordance_pairs']}곳이다. "
        f"기업 동일 가중의 AI − 규칙 차이는 {fmt(panel['primary_equal_issuer_ai_minus_rule'])}이다. 모집·채점·선별 결측 사유는 원장에 기업별로 보존했다.",
        "27곳의 확정 중대 8건 가운데 규칙은 2건, AI는 3건을 실제 이관했다. 공통 이관은 1건이고, 규칙만 고른 산일전기 08번은 AI 검토 대기가 됐다. AI만 고른 문항은 워트 11번과 키스트론 10번이었다. 전체 명단의 추가 누락 총수는 결측이 있어 알 수 없지만 이미 최소 1건이 확인됐다. 목표 15곳에 비해 순위 유효 기업이 6곳이어서 순위 우위를 판정할 수 없었다.",
        f"양쪽의 검토시간 합계를 낼 수 있는 {time['paired_issuer_count']}곳에서 규칙 {fmt(time['paired_proxy_seconds']['rule'])}초, AI {fmt(time['paired_proxy_seconds']['ai'])}초였다. AI 쪽이 {fmt(time['paired_delta_seconds_ai_minus_rule'])}초 길었다. 유효한 검토 메모 44개 중에도 산술 오류가 있었다. 산일전기 08번에서 세 수량 합을 900,000주 크게 적어 원문에 대조한 결과를 남겼다. [시간과 메모의 원문 검증](v1/timing/persona_source_audit.json) · [순위·중대 회수의 독립 검산](v1/analysis/publication_pair_crosscheck.json)",
        "### 기업별 실제 이관",
        "이관 열의 숫자는 각 접수번호 뒤의 원본 질문 번호다. ‘없음’은 유효한 목록에 이관 항목이 0건이라는 뜻이다. 대시는 해당 비교·측정값을 얻지 못한 경우다. 순위가 완성됐더라도 기준표 결측이나 등급군 부족이 있으면 순위 차이를 추정할 수 없다.",
        table(["발행기업","질문","A0","C","두 순위","기준표","규칙 이관","AI 이관","대체 이관","순위 차이"],records),
        "[결과 원장](v1/analysis/results.json) · [제출용 보고서](제출용_보고서.md)",
        "### 보관한 결과의 재검산",
        "프로젝트의 ipo_agent_eval 폴더에서 아래 명령을 실행하면 이미 저장한 입력, 응답과 산출물을 대조한다. 독립 검산기는 실제 응답에서 두 순위를 다시 만들고, 등급 투표·공통 필수·순위 동률·유보 범위·비용과 시간의 분모를 결과 원장과 비교한다.",
        "```powershell\npython -m reporting.a1_cli_recovery recheck\n```",
    ]
    grades = ["수용 가능", "비중대 쟁점", "중대 쟁점", "판정 유보"]
    cells = {(a,b):v for a,b,v in results['pre_adjudication_cross_table']}
    common_names = {"not_routed":"규칙의 이관 요건 미충족", "waiting":"한 자리 상한으로 대기",
                    "request":"자료 요청", "archived":"기록 보관", "transferred":"이관"}
    reasons = []
    role_reviews={"A0":Counter(),"C":Counter()}
    for p in (BASE/"role_source_review").glob("*.json"):
        inspection=read(p)
        if "reviews" not in inspection:
            continue
        for role in role_reviews:
            role_reviews[role].update(v['status'] for v in inspection['reviews']['3_semantic'][role].values())
    for row in rows:
        if row['status'] != 'COMPARED':
            continue
        for side in ('rule','ai'):
            for key, outcome in row[side]['operating']['missed_status'].items():
                reasons.append([row['issuer'],key,'규칙' if side=='rule' else 'AI',common_names[outcome]])
    steps += ["### 역할의 판단을 원문과 대조한 결과",
              "A0는 공시 원문을 읽었고 C는 후보 자료를 읽었다. 원문 감사자는 발행사·기간·범위·수치와 인용이 판단을 뒷받침하는지 기록했다. C에서는 발행사의 이익 기간·귀속과 자료가 있는 실제 비교기업의 판단이 대조 대상이다.",
              table(['역할','근거 지지','조건부 판단','근거 부족','인용 불일치'],
                    [[role,*[counts[k] for k in ('verified','conditional','insufficient','citation_mismatch')]] for role,counts in role_reviews.items()]),
              "### 채점이 갈린 정도", 
              f"첫째·둘째 채점이 모두 유효한 회사는 {len(results['agreement_cases'])}곳이고 대상 질문은 {results['agreement_denominator']}개다. 행은 첫 판정, 열은 둘째 판정이다. 마지막 원문 감사가 등급에 반영되기 전의 값이다.",
              table(['첫째 / 둘째',*grades],[[a,*[cells.get((a,b),0) for b in grades]] for a in grades]),
              "### 검토 자리를 늘리면 회수가 얼마나 바뀌나",
              "공통 필수 외에 정해진 수만큼 위에서부터 고른 경우다. 각 칸은 완료 기업 가운데 회수한 확정 중대 쟁점 건수다. 운영 판단에 쓰는 자리는 기업당 한 건이다.",
              table(['추가 자리 수','규칙 회수','AI 회수','전체 확정 중대'],
                    [[k,cell['rule']['found'],cell['ai']['found'],cell['rule']['denominator']]
                     for k,cell in sorted(panel['same_k_curve'].items(),key=lambda kv:int(kv[0]))]),
              "### 판정 유보가 남긴 범위",
              f"각 유보 항목의 등급을 두 방식에 똑같이 적용하면 순위 비교에 추가로 들어올 가능성이 있는 기업은 {panel['additional_valid_if_deferred_classified']}곳이다. 아래 누락 차이는 규칙의 누락 건수에서 AI의 누락 건수를 뺀 값이다. 양수이면 AI가 더 적게 놓쳤다.",
              table(['완료 쌍의 유보 조합','규칙 누락 − AI 누락 (건)'],
                    [[label," ~ ".join(map(str,panel[k])) if panel[k] is not None else "산출 불가"] for label,k in
                     [('같은 한 자리','fixed_same_k_miss_delta_pending_bounds'),('실제 이관','operating_miss_delta_pending_bounds')]]),
              "### 실제 목록에서 놓친 확정 중대 쟁점",
              (table(['발행기업','질문 ID','방식','해당 항목의 처리'],reasons) if reasons else
               "완료 기업의 실제 목록에서 관측한 확정 중대 누락은 없었다." if panel['complete_pairs'] else "완료된 기업 쌍이 없어 집계하지 못했다."),
              "### 실제 사용량과 경과 시간",
              "Terra는 입력 토큰 백만 개당 1달러, 출력 토큰 백만 개당 5달러의 프로젝트 표준단가로 계산했다. 이 표의 경과는 각 요청의 대기와 응답 시간을 합산한 값이다. 요청이 동시에 진행된 경우가 있어 프로젝트 전체 경과와 다르다.",
              table(['Terra 단계','전송','추가 시도','입력 토큰','출력 토큰','표준단가 추정(달러)','요청 경과 합(초)'],
                    [[s['stage'],s['sends'],s['noninitial_sends'],s['input_tokens'],s['output_tokens'],
                      f"{(s['input_tokens']+5*s['output_tokens'])/1e6:.6f}" if s['known_usage'] else '미확인',
                      fmt(s['service_seconds'],1)] for s in results['terra_by_stage']]),
              table(['Codex 작업','시작 세션','유효 세션','사용량 확인 세션'],
                    [[label, results['codex'][key]['sessions_started'],results['codex'][key]['valid_sessions'],
                      results['codex'][key]['sessions_with_usage']] for key,label in [('blind','독립 채점과 조정'),('timing','대행 검토 시간')]]),
              "고유 배정 중 성공한 항목들의 원문 준비는 "
              +fmt(time['unique']['observed_sums']['packet_prep_seconds'],2)+"초, 모델 세션은 "
              +fmt(time['unique']['observed_sums']['service_seconds'],2)+"초, 인용 검증은 "
              +fmt(time['unique']['observed_sums']['verification_seconds'],2)+"초였다. 전체 경과 합계는 "
              +fmt(time['unique']['observed_sums']['whole_seconds'],2)+"초였다. 실패한 배정과 양쪽 처리 시간을 모두 얻은 회사는 시간 원장의 별도 분모로 기록했다.",
              "### 근거 감사와 독립 재계산",
              "두 순위와 등급을 잠근 뒤 실제 이관과 동일한 한 자리 목록에서 선택이 달랐던 질문을 모았다. 질문별로 역할별 원판정, 각 방식의 조치, 원문 근거의 ID와 독립 채점 인용을 대조했다. [근거 감사 원장](v1/analysis/citation_review/summary.json) · [독립 재계산](v1/analysis/independent_recheck.json)"]
    steps += ["### 상호 재질문 조건의 재점검",
              "개발 때는 두 역할이 같은 사실과 결정에 대해 서로 반대하는 상태가 두 회사 이상에서 반복될 때만 추가 질문을 시험하기로 했다. 합의 점검 신호를 주지 않은 이번 A1에서 실제로 이관한 31건을 이 기준으로 다시 읽었다. 역할 판단이 같은 방향이거나, 한쪽이 조건부·자료 부족이거나, 역할의 검토 대상이 서로 다른 사례를 구분했다. 잠정 방향 차이는 에스엘에스바이오 한 건이었다. 31건 사이의 465개 조합에서 같은 구체적 갈등이 반복된 적격 쌍은 0개였다. 후속 재질문은 발동하지 않았다. [실제 이관의 원판정과 근거](v1/analysis/referral_disagreements.json) · [조건부 재질문 독립 검토](v1/analysis/referral_trigger_review.json)"]
    if time['unique']['missing_items']:
        by_id={row['case']:row['issuer'] for row in rows}
        missing=[]
        for entry in time['unique']['missing_items']:
            job=read(BASE/"timing"/entry['case']/entry['item']/"timing.json")
            missing.append([by_id[entry['case']],entry['item'],job['attempts'],
                            fmt(job.get('observed_attempt_seconds'),2),entry['reason']])
        steps+=["### 유효 검토 시간을 얻지 못한 배정",
                "실패한 시도의 경과는 원장에 남기고, 두 목록의 시간 차이에는 해당 기업을 넣지 않았다.",
                table(['기업','항목','시도 횟수','실패 시도 경과 합(초)','종료 상태'],missing)]
    steps+=["성공한 시간 측정도 그 항목에 배정된 쪽에서 한 작업이다. 예를 들어 씨엠티엑스 04번의 검토자는 229~231쪽의 세 PER 평균 19.2배를 재현했다. 두 기업을 최종 선정했다고 쓴 196쪽은 배정 자료에 없었다. 이 검토의 완료 시간은 앞쪽 서술과 산정표의 불일치까지 해소하는 데 걸린 시간으로 해석할 수 없다."]
    path=OUT/"전체_진행기록.md"
    prefix=path.read_text(encoding="utf8").split("\n"+MARKER,1)[0]
    path.write_text(prefix.rstrip()+"\n\n"+"\n\n".join(steps)+"\n",encoding="utf8")

    plan=OUT.parents[2]/"update plan"/"이제 할 일.md"
    history=plan.read_text(encoding="utf8").split("## 이제 할 일",1)[0]
    history=history.split("## 본평가 종료 상태",1)[0]
    start=history.index("**본 평가용 발행기업")
    historical_body=history[start:].rstrip()
    title=("# A1 전체 진행 현황\n\n2026-11-27 KST. 37곳에 등록한 본평가의 실행·분석·보고를 마쳤다. "
           f"규칙과 AI의 순위 및 기준표를 함께 확보한 기업은 {panel['complete_pairs']}곳, "
           f"중대·비중대 쟁점의 순위 비교에 쓸 수 있는 기업은 {panel['valid_concordance_pairs']}곳이다. "
           "[처음부터 끝까지의 진행 기록](../ipo_agent_eval/reports/a1_main/전체_진행기록.md) · "
           "[제출용 보고서](../ipo_agent_eval/reports/a1_main/제출용_보고서.md)\n\n## 본평가 전 기록\n\n")
    end=("## 본평가 종료 상태\n\n"
         "1. **W12.** 37곳 406개 질문과 최초 신고서 원본을 동결했다. 36곳의 후보 자료를 준비했고, 노브랜드의 별도 후보 자료 결측은 흐름표에 남겼다.\n"
         "2. **W13.** 독립 채점·역할 검토·두 목록·배정 시간의 성공·실패를 원장에 기록했다. 채점 실행기의 시작 안내와 영문 회사명 가림 정정은 변경 전후 입력 및 영향 기업과 연결했다.\n"
         "3. **W14.** 순위·중대 누락·이관량·대행 시간을 계산했다. 목록이 달랐던 항목의 원문, 원장 재계산과 문서 세 형식을 검토했다. "
         "[단계별 세 차례 검토](../ipo_agent_eval/reports/a1_main/v1/단계별_검토.md) · [결과 원장](../ipo_agent_eval/reports/a1_main/v1/analysis/results.json)\n\n"
         "사람 평가자의 기준표와 노동시간은 별도 실측 과제다. 자동 보류, 재질문, 카나리 등 조건부 실험의 적용 범위와 검증 이력은 전체 진행 기록에 정리했다.\n")
    plan.write_text(title+historical_body+"\n\n"+end,encoding="utf8")

    review_path=BASE/"단계별_검토.md"
    review_mark="## 본평가 종료 후 검토"
    before=review_path.read_text(encoding="utf8").split("\n"+review_mark,1)[0].rstrip()
    citation=read(BASE/"analysis/citation_review/summary.json")
    replay=read(BASE/"analysis/independent_recheck.json")
    identity=read(BASE/"analysis/identity_sensitivity.json")
    raw_names=read(BASE/"corrections/c_blind_names/audit.json")
    actual_names=read(BASE/"corrections/c_blind_names/actual_exposure.json")
    rule_for_names=(f"Terra 전송 45건을 받은 뒤 가림 명칭을 다시 확인했다. 발행사와 후보의 카드 "
                    f"{sum(q['n_cards'] for q in raw_names['rows'] if q.get('n_cards'))}개, 원문 근거 "
                    f"{sum(q['n_evidence'] for q in raw_names['rows'] if q.get('n_evidence'))}개를 검사했다. "
                    f"정정 전 C를 보낸 기업은 {raw_names['n_distinct_C_before_pause']}곳이었다. "
                    f"실제 송신본에 발행사·후보 자신의 직접 이름이 남은 곳은 {identity['self_exposed']}곳, "
                    f"제3자까지 포함하면 {identity['any_direct_exposed']}곳이다. "
                    "이미 평가한 회사는 새 입력으로 다시 평가하지 않았다. 아직 보내지 않은 자료에서는 등록한 문자열만 중립 표시로 바꿨다. "
                    "원일티엔아이의 한 발췌에서는 치환 후 350자 한도를 지키면서 문장과 숫자를 남기기 위해 짧은 표시를 사용했다. "
                    "달바글로벌에 실제로 보낸 후보 카드에는 ‘에이프릴스킨’이 남았다. 해당 브랜드가 후보 에이피알의 옛 법인명이라는 사실을 확인해 이미 보낸 자료의 최종 노출 범위에 포함했다. "
                    "[에이피알의 사명 변경 기록](https://apr-blog.com/apr-youth-employment) · "
                    "[사건 당시 집계](v1/corrections/c_blind_names/audit.json) · [전송본별 노출](v1/corrections/c_blind_names/actual_exposure.json) · "
                    "[실제 전송문·응답 근거 검증](v1/corrections/c_blind_names/completed_wire_proof.json)")
    if len(actual_names['rows'])!=37:
        raise ValueError("Incomplete ultimate exposure census")
    all_text=path.read_text(encoding="utf8").replace("## W14 분석과 결과 보고",
             "### 후보 자료의 가림 정정\n\n"+rule_for_names+"\n\n## W14 분석과 결과 보고",1)
    path.write_text(all_text,encoding="utf8")
    review_append=[review_mark,
        "각 행은 실행을 마친 뒤 서로 다른 기록에서 결과를 다시 확인한 내용이다. 자료 판단에는 공시 심사자·회계 검토자 역할의 AI를 사용했다.",
        table(['검토 대상','1차 · 원문과 입력','2차 · 판단과 논리','3차 · 설계 및 재현'],[
            ['독립 채점',f"37곳 전체를 최초·반복 채점에 배정하고 각 세션의 중립 질문·허용 쪽과 인용을 확인했다.",
             f"첫 두 제출을 모두 확보한 {len(results['agreement_cases'])}곳, {results['agreement_denominator']}개 항목에서 조정 전 등급을 대조했다. 불일치·중대·유보 항목은 채점표만 보는 검토자가 원문으로 확인했다.",
             f"유보와 제출 실패를 구분했다. 기업별 최종 상태는 {grade_summary}. 실제 목록을 합치기 전에 기준표를 잠갔다."],
            ['역할·가림·선별',f"A0 유효 {sum(r['role_a0'] for r in rows)}곳, C 유효 {sum(r['role_c'] for r in rows)}곳을 확인했다. 가림 정정 이전과 이후의 전송물은 별도 해시에 연결했다.",
             "원문 기간·귀속·사업 비교 범위가 역할 판정을 지지하는지 대조했다. 같은 항목의 두 역할과 공통 검산값을 두 선별 방식에 동일하게 연결했다.",
             f"원 응답에서 순위, 공통 필수와 추가 이관을 재계산했고, 실제 발송문 가운데 발행사·후보 자신을 직접 드러낸 {identity['self_exposed']}곳을 뺀 결과를 보조표에 실었다."],
            ['이관 검토 시간',f"실제 목록의 중복을 제거한 {time['unique']['assigned_items']}개 배정과 전체 순서를 대조했다.",
             "배정 경로를 숨긴 질문과 허용 쪽, 응답·인용 유효성, 원문 준비·서비스·검증의 측정분을 확인했다.",
             f"양쪽에서 같은 질문은 한 번 잰 시간을 공유했다. 두 목록 전체 시간이 있는 {time['paired_issuer_count']}곳의 합을 재계산했다."],
            ['분석·인용',f"등록 37곳, 전체 완료 {panel['complete_pairs']}곳, 순위 유효 {panel['valid_concordance_pairs']}곳의 분모를 대조했다.",
             f"두 방식의 선택이 달랐던 {citation['items']}개 질문의 실제 근거와 한계를 점검했다. 같은 K, 실제 이관, 공통 필수, 유보 배정과 워트 제외값을 각각 확인했다.",
             f"원장부터 독립 재계산한 {replay['checks']:,}개 대조 항목에서 차이는 {len(replay['differences'])}개였다. 검정과 37곳 전체 운영 기준에 필요한 분모를 설계 문서와 다시 맞췄다."]]),
        "[채점과 역할의 기업별 실패](analysis/terminal_flow.json) · [목록 차이 원문 감사](analysis/citation_review/summary.json) · [독립 검산](analysis/independent_recheck.json) · [가림 민감도](analysis/identity_sensitivity.json)"]
    review_path.write_text(before+"\n\n"+"\n\n".join(review_append)+"\n",encoding="utf8")


if __name__=="__main__":
    record()
