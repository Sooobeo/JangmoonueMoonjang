"""Explain terminal missingness by replaying rejected requests after all comparisons close."""
import json
from collections import Counter

from reporting.a1_cli_recovery import effective_read
from scripts.a1_main_blind import BASE, read, wire, write_once


def wrong_pages(attempt):
    request = read(attempt.parent/"request.json")["input"]
    allowed = {row["item_id"]: row["physical_pages"] for row in request["items"]}
    events = [json.loads(s) for s in (attempt/"stdout.jsonl").read_bytes().splitlines() if s.strip()]
    replies = [e["item"]["text"] for e in events if e.get("item",{}).get("type")=="agent_message"
               and e["type"]=="item.completed"]
    if not replies:
        return []
    items = json.loads(replies[-1])["items"]
    return [{"item": r["item_id"], "submitted_page":r["physical_page"],
             "allowed_pages":allowed.get(r["item_id"],[]),"missing_reason":not bool(r["reason"].strip())}
            for r in items if r["physical_page"] not in allowed.get(r["item_id"],[]) or not r["reason"].strip()]


def create():
    result = read(BASE/"analysis/results.json")
    summary = Counter()
    cases = []
    for r in result["issuers"]:
        case = r["case"]
        op = BASE/"terra"/case
        errors = read(op/"role_failures.json")["failures"] if (op/"role_failures.json").exists() else {}
        row = {"case":case, "issuer":r["issuer"],"selection":r["selection_state"],"role_errors":errors,
               "grade":r["grade_state"],"exhausted_grade_jobs":{}}
        if r["selection_state"]=="ranked":
            select_label="전체 순위 완성"
        elif (op/"preparation.json").exists():
            select_label="후보 자료 준비 결측"
        else:
            select_label="역할 제출 실패" if errors else "선별 실패"
        summary[select_label]+=1
        if r["grade_state"]!="sealed":
            kinds=set()
            for stage in ("first", "second", "reconcile"):
                folder=BASE/"blind"/case/stage
                attempts=sorted(folder.glob("attempt-*/closed.json"))
                if len(attempts)!=2 or (folder/"accepted.json").exists():
                    continue
                rejected = []
                for p in attempts:
                    d=effective_read(p)
                    if d["valid"]:
                        raise ValueError("Unaccepted valid submission")
                    err=d.get("error","")
                    mismatches=wrong_pages(p.parent) if "Wrong item-specific page or missing reason" in err else []
                    if mismatches and any(q["submitted_page"] not in q["allowed_pages"] for q in mismatches):
                        kinds.add("문항 허용 쪽 위반")
                    if mismatches and any(q["missing_reason"] for q in mismatches):
                        kinds.add("판정 이유 누락")
                    if not mismatches:
                        kinds.add(err.split(":")[0] or "기타 제출 오류")
                    rejected.append({"attempt":p.parent.name,"validator_error":err,"mismatches":mismatches})
                row["exhausted_grade_jobs"][stage]=rejected
            row["grade_failure_kinds"]=sorted(kinds)
        else:
            summary["기준표 완성"]+=1
        cases.append(row)
    write_once(BASE/"analysis/terminal_flow.json",wire({"counts":dict(summary),"issuers":cases}))


if __name__=="__main__":
    create()
