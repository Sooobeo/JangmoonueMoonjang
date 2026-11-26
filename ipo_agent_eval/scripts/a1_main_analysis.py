"""Locked-cohort analysis. Incomplete rankings and substitute allocations never form a pair."""
from collections import Counter
import sqlite3
from contextlib import closing
from statistics import mean, stdev
import math

from scipy.stats import t
from scripts.a1_main_blind import BASE, hash_bytes, read, wire, write_once
from scripts.a1_main_terra import ROSTER
from scripts.current_evaluate import ARMS, KOREAN_GRADES, group_stats, summarize_case


def infer(rows):
    stats = group_stats(rows)
    complete = [r for r in rows if r["status"]=="COMPARED"]
    values = [r["concordance_delta_ai_minus_rule"] for r in complete if r["concordance_delta_ai_minus_rule"] is not None]
    n = len(values)
    variable = n >= 2 and min(values) != max(values)
    interval = stats["descriptive_95_t_interval"] if variable else None
    stats["descriptive_95_t_interval"] = interval
    stats["two_sided_p"] = float(2*t.sf(abs(mean(values)/(stdev(values)/math.sqrt(n))),n-1)) if variable else None
    stats["rank_superiority"] = bool(interval[0]>0) if n>=15 and variable else None
    stats["rank_decision_reason"] = ("유효 기업 15곳 미달" if n<15 else "기업별 차이 분산 0" if not variable
                                     else "95% 신뢰구간 하한에 따라 판정")
    stats["additional_valid_if_deferred_classified"] = sum(
        r["concordance_delta_ai_minus_rule"] is None and r["valid_pending_assignments"]>0 for r in complete)
    stats["known_operating_additional_miss_ceiling_satisfied"] = (
        not stats["ai_newly_missed_material_items"] if len(complete)==37 else None)
    stats["worst_operating_additional_misses"] = sum(
        len(r["operating_difference"]["newly_missed_by_ai"])
        + len((set(r["rule"]["operating"]["items"])-set(r["ai"]["operating"]["items"])) & set(r["pending"]))
        for r in complete) if complete else None
    total=stats["known_material"]
    for arm in ARMS:
        for name in ("fixed_same_k","operating"):
            summary=stats[name][arm]
            summary["material_recall"]=(total-summary["material_missed"])/total if total else None
            bounds=[(r["fixed_k"][arm] if name=="fixed_same_k" else r[arm]["operating"])["miss_count_bounds"]
                    for r in complete]
            summary["miss_count_bounds"]=[sum(v[i] for v in bounds) for i in (0,1)] if bounds else None
        rows_arm=[r[arm]["operating"] for r in complete]
        stats["operating"][arm].update(
            mandatory=sum(r["mandatory"] for r in rows_arm),additional=sum(r["additional"] for r in rows_arm),
            archived=sum(len(r["archived"]) for r in rows_arm),not_routed=sum(len(r["not_routed"]) for r in rows_arm),
            timed_issuers=sum(r["proxy_seconds"] is not None for r in rows_arm),
            timed_items=sum(r.get("timed_items",0) for r in rows_arm))
    curves = {}
    max_k = max((len(r["material"])+len(r["known_nonmaterial"])+len(r["pending"])-len(r["mandatory"])
                 for r in complete),default=0)
    for k in range(1,max_k+1):
        counts = {arm:0 for arm in ARMS}
        for r in complete:
            maximum=max(map(int,r["fixed_curve_by_k"]))
            cell = r["fixed_curve_by_k"][str(min(k,maximum))]
            for arm in ARMS:
                counts[arm]+=len(cell[arm]["material_found"])
        curves[str(k)]={a:{"found":value,"denominator":total,"recall":value/total if total else None}
                        for a,value in counts.items()}
    stats["same_k_curve"]=curves
    return stats


def terminal_grade(case):
    folder=BASE/"blind"/case
    if (folder/"sealed.json").exists():
        return "sealed"
    for stage in ("first","second","reconcile"):
        attempts=sorted((folder/stage).glob("attempt-*/closed.json"))
        if len(attempts)==2 and not any(read(p)["valid"] for p in attempts):
            return stage+"_failed"
    raise ValueError(case+" reference pending")


def report(cases,states):
    from scripts.a1_main_timing import summary
    timing = summary(cases)
    flow=[]
    roster={r["receipt"]:r for r in read(ROSTER)["rows"]}
    confusion=Counter()
    agreement_cases=[]
    for case in cases:
        op=BASE/"terra"/case
        rank_path=op/"ranking.json"
        failure_path=next((op/n for n in ("failure.json","preparation.json") if (op/n).is_file()),None)
        if not rank_path.exists() and not failure_path:
            raise ValueError(case+" selection pending")
        grade_state=terminal_grade(case) if states[case]["grading_ready"] else "preparation_incomplete"
        folder=BASE/"issuers"/case
        items=read(folder/"items.json") if (folder/"items.json").exists() else []
        base={"case":case,"issuer":roster[case]["issuer"],"preparation":states[case],
              "original_count":len(items) or None,"role_a0":(op/"A0.json").exists(),"role_c":(op/"C.json").exists(),
              "grade_state":grade_state,"selection_state":"ranked" if rank_path.exists() else read(failure_path),
              "status":"INCOMPLETE"}
        raw_passes=[BASE/"blind"/case/stage/"accepted.json" for stage in ("first","second")]
        if all(path.is_file() for path in raw_passes):
            first,second=({r["item_id"]:r["grade"] for r in read(path)["answer"]["items"]} for path in raw_passes)
            if first.keys()!=second.keys():
                raise ValueError(case+" pre-adjudication populations differ")
            agreement_cases.append(case)
            confusion.update((g,second[item]) for item,g in first.items())
        if rank_path.exists() and grade_state=="sealed":
            gold=read(BASE/"blind"/case/"sealed.json")
            ranking=read(rank_path)
            if ranking["mandatory"] != read(folder/"b.json")["mandatory"]:
                raise ValueError("Frozen mandatory list differs")
            base.update(summarize_case(case,ranking,{k:KOREAN_GRADES[v] for k,v in gold["grades"].items()},1,"TERRA"))
            base["cohort"]="a1-main-v1"
            for arm in ARMS:
                r=base[arm]["operating"]
                recorded = timing["per_case"][case][arm]
                r["timed_items"]=recorded["timed_items"]
                r["proxy_seconds"]=recorded["whole_seconds"]
        flow.append(base)
    from ipo_eval.a1_main_ledger import Ledger
    ledger=Ledger(BASE/"terra/ledger.sqlite3",hash_bytes((BASE/"freeze.json").read_bytes()))
    database=BASE/"terra/ledger.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.row_factory=sqlite3.Row
        usage=[dict(r) for r in db.execute("""
            SELECT a.stage, count(*) AS sends, count(o.input_n) AS known_usage,
                   sum(o.input_n) AS input_tokens, sum(o.output_n) AS output_tokens,
                   sum(o.elapsed) AS service_seconds, count(o.elapsed) AS timed_sends,
                   sum(CASE WHEN a.kind != 'initial' THEN 1 ELSE 0 END) AS noninitial_sends
            FROM attempt a LEFT JOIN outcome o USING(id) GROUP BY a.stage""")]
    codex_time={}
    for group in ("blind","timing"):
        attempts=list((BASE/group).glob("*/*/attempt-*/closed.json"))
        records=[read(p) for p in attempts]
        tokens=[r["usage"][0] for r in records if len(r.get("usage",[]))==1]
        codex_time[group]={"sessions_started":len(records),"valid_sessions":sum(r.get("valid",False) for r in records),
                           "sessions_with_usage":len(tokens),"usage":dict(sum((Counter(u) for u in tokens),Counter())),
                           "cost":None}
    result={"protocol":"a1-main-v1","issuers":flow,"overall":infer(flow),
            "excluding_wort":infer([r for r in flow if r["issuer"]!="워트"]),
            "cost":ledger.summary(),"terra_by_stage":usage,"codex":codex_time,
            "human_review_seconds":None,"human_reference":None,"operational_review_timing":timing,
            "pre_adjudication_cross_table":[[g,h,n] for (g,h),n in sorted(confusion.items())],
            "exact_grade_agreement":sum(n for (g,h),n in confusion.items() if g==h)/sum(confusion.values())
                                      if sum(confusion.values()) else None,
            "agreement_denominator":sum(confusion.values()),"agreement_cases":agreement_cases}
    write_once(BASE/"analysis/results.json",wire(result))
    return result
