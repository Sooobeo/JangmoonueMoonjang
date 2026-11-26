"""Audit citations after the complete cohort's reference and selection paths have closed."""
import argparse
from collections import Counter
import json

from reporting.a1_cli_recovery import effective_read
from scripts.a1_main_blind import BASE, hash_bytes, read, wire, write_once
from scripts.a1_main_difference_audit import compare
from scripts import a1_main_analysis
from scripts.a1_main_terra import load_freeze

FOLDER=BASE/"analysis/citation_review"


def prepare():
    _,cases,states,_=load_freeze(BASE/"freeze.json")
    a1_main_analysis.read=effective_read
    finished={}
    for case in cases:
        folder=BASE/"terra"/case
        selection=next((key for key in ("ranking","failure","preparation") if (folder/(key+".json")).exists()),None)
        if not selection:
            raise ValueError("Selection still open: "+case)
        grade=a1_main_analysis.terminal_grade(case) if states[case]["grading_ready"] else "preparation_incomplete"
        finished[case]={"selection":selection,"grade":grade}
    for case, state in finished.items():
        if state=={"selection":"ranking","grade":"sealed"}:
            packet=wire(compare(case))
            write_once(FOLDER/case/"packet.json",packet)
            state["packet_sha256"]=hash_bytes(packet)
            state["difference_items"]=len(json.loads(packet)["items"])
    write_once(FOLDER/"index.json",wire(finished))
    return finished


def digest_reviews():
    index=read(FOLDER/"index.json")
    verdicts=Counter()
    records={}
    for case, record in index.items():
        if "packet_sha256" not in record:
            continue
        packet=read(FOLDER/case/"packet.json")
        if hash_bytes(wire(packet))!=record["packet_sha256"]:
            raise ValueError("Post-lock packet changed")
        if not packet["items"]:
            continue
        reference=FOLDER/case/"review.json"
        review=read(reference)
        if set(review)!=set(packet["items"]):
            raise ValueError("Missing citation review "+case)
        for key,judgment in review.items():
            if (judgment["assessment"] not in {"지지","일부 지지","근거 부족"} or
                    not judgment["basis"].strip() or not set(judgment["refs"])<=set(packet["items"][key]["cited_sources"])):
                raise ValueError("Invalid citation review "+key)
            verdicts[judgment["assessment"]]+=1
        records[case]=hash_bytes(reference.read_bytes())
    result={"paired_issuers":sum("packet_sha256" in r for r in index.values()),
            "issuers_with_differences":len(records),"items":sum(verdicts.values()),"assessments":dict(verdicts),
            "reviews_sha256":records,"changes_to_locked_grades_or_ranks":0}
    write_once(FOLDER/"summary.json",wire(result))
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["prepare","verify"])
    action=parser.parse_args().action
    if action=="prepare":
        rows=prepare()
        print("closed",len(rows),"difference items",sum(r.get("difference_items",0) for r in rows.values()))
    else:
        print(json.dumps(digest_reviews(),ensure_ascii=False))
