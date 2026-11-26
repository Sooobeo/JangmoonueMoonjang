"""Collect substantive disagreements on actual A1 referrals for a descriptive follow-up."""
from scripts.a1_main_blind import BASE, hash_bytes, read, wire, write_once


def collect():
    selection_index = read(BASE/"analysis/citation_review/index.json")
    by_case = {}
    for case, state in selection_index.items():
        if state["selection"]!="ranking":
            continue
        folder = BASE/"terra"/case
        rank = read(folder/"ranking.json")
        merged = read(folder/"merged.json")
        items = {r["item_id"]:r for r in merged["items"]}
        selected = {r["item_id"]:r for r in rank["ai"]["items"]}
        rows=[]
        for key in rank["ai"]["operational"]:
            r = items[key]
            a,c = r["a0"],r["c"]
            opposed = {a["state"],c["state"]}=={"수용","문제 제기"} and c["comparable"]
            rows.append({"item_id":key,"question":r["question"],"states":[a["state"],c["state"]],
                         "directly_opposed":opposed,
                         "a0":a["reason"],"c":c["reason"],
                         "original_role_sources":{e:merged["sources"][e] for e in
                                                  sorted(set(a["evidence_ids"]+c["evidence_ids"]))},
                         "referral_reason":selected[key]["reason"] if key in selected else "공통 필수",
                         "referral_question":selected[key]["question_or_request"] if key in selected else None})
        by_case[case]={"rank_sha256":hash_bytes((folder/"ranking.json").read_bytes()),"routed":rows}
    write_once(BASE/"analysis/referral_disagreements.json",wire(by_case))


if __name__=="__main__":
    collect()
