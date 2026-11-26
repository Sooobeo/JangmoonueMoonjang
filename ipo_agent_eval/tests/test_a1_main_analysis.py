from itertools import product
from random import Random

import pytest
from scripts.current_evaluate import ARMS, concordance, pending_rank_bounds
from scripts.a1_main_analysis import infer
from scripts.a1_main_blind import grade_packet


def test_shared_pending_bounds_equal_exhaustive_assignments_with_ties():
    rng=Random(14)
    for n in range(1,9):
        keys=list(range(n))
        for _ in range(16):
            orders={arm:{k:rng.randrange(4) for k in keys} for arm in ARMS}
            m, other, pending=map(set,(keys[:n//4],keys[n//4:n//2],keys[n//2:]))
            actual,count=pending_rank_bounds(orders,m,pending)
            expected={arm:[] for arm in (*ARMS,"delta")}
            for bits in product((False,True),repeat=len(pending)):
                pos={k for k,bit in zip(sorted(pending),bits) if bit}
                if not (m|pos) or not (other|(pending-pos)):
                    continue
                scores=[concordance(orders[arm],m|pos,other|(pending-pos))["score"] for arm in ARMS]
                for column,score in zip(expected,[*scores,scores[1]-scores[0]]):
                    expected[column].append(score)
            assert count==len(expected["delta"])
            for k,v in expected.items():
                if v:
                    assert actual[k]==pytest.approx([min(v),max(v)])
                else:
                    assert actual[k] is None


def test_no_complete_pair_never_satisfies_zero_miss_or_superiority():
    result=infer([{"status":"INCOMPLETE"}]*37)
    assert result["known_operating_additional_miss_ceiling_satisfied"] is None
    assert result["two_sided_p"] is None
    assert result["fixed_same_k"]["ai"]["material_recall"] is None


def test_adjudicator_only_receives_assigned_questions_and_pages():
    registry=[{"id":"a","pages":[1]},{"id":"b","pages":[2]}]
    source={"items":[{"item_id":"a","question":"a?","original_choice":"never expose"},
                     {"item_id":"b","question":"b?"}],
            "pages":{"1":"p1","2":"p2"},"prior_answers":["forbidden"]}
    assert grade_packet(source,registry,{"a"})=={
        "items":[{"item_id":"a","question":"a?","physical_pages":[1]}],"pages":{"1":"p1"}}


def test_failed_first_rating_still_runs_the_independent_second(tmp_path,monkeypatch):
    from scripts import a1_main_blind as blind
    monkeypatch.setattr(blind,"BASE",tmp_path)
    folder=tmp_path/"issuers"/"case"
    blind.write_once(folder/"items.json",blind.wire([{"id":"x","pages":[1]}]))
    blind.write_once(folder/"grading.json",blind.wire({"items":[{"item_id":"x","question":"x?"}],"pages":{"1":"p"}}))
    observed=[]
    def fail(task,*args):
        observed.append(task.name)
        raise RuntimeError("Two starts exhausted: "+task.name)
    monkeypatch.setattr(blind,"submit",fail)
    with pytest.raises(RuntimeError,match="first, second"):
        blind.grade("case")
    assert observed==["first","second"]


def test_two_full_ratings_and_blinded_third_pass(tmp_path,monkeypatch):
    from scripts import a1_main_blind as blind
    monkeypatch.setattr(blind,"BASE",tmp_path)
    folder=tmp_path/"issuers"/"issuer"
    registry=[{"id":k,"pages":[i]} for i,k in enumerate(["a","b","c"],1)]
    blind.write_once(folder/"items.json",blind.wire(registry))
    blind.write_once(folder/"grading.json",blind.wire({"items":[{"item_id":k,"question":k} for k in "abc"],
                                                      "pages":{str(n):f"source {n}" for n in range(1,4)}}))
    ratings={"first":[0,0,1],"second":[0,2,2],"reconcile":[0,3]}
    seen={}
    def fake(task,instruction,schema,packet,check):
        assert instruction==blind.RULE and schema==blind.GRADE
        seen[task.name]=[q["item_id"] for q in packet["items"]]
        rows=[]
        for q,v in zip(packet["items"],ratings[task.name],strict=True):
            n=q["physical_pages"][0]
            rows.append({"item_id":q["item_id"],"grade":blind.GRADES[v],"physical_page":n,
                         "reason":"검증 설명","quote":f"source {n}"})
        answer={"items":rows}
        check(answer)
        return {"answer":answer,"sessions":[task.name]}
    monkeypatch.setattr(blind,"submit",fake)
    draft=blind.grade("issuer")
    assert seen=={"first":list("abc"),"second":list("abc"),"reconcile":list("bc")}
    assert draft["exact_agreement"]==1 and draft["n"]==3
    assert draft["items"]["c"]["grade"]=="판정 유보"
    r=tmp_path/"blind/issuer"
    blind.write_once(r/"source_audit.json",blind.wire({"b":{"supported":False,"basis":"scope mismatch"},
                                                      "c":{"supported":True,"basis":"disagreement retained"}}))
    blind.seal_grades("issuer")
    assert blind.read(r/"sealed.json")["grades"]=={"a":"수용 가능","b":"판정 유보","c":"판정 유보"}


def test_main_decisions_keep_all_37_and_exclude_id_ties():
    from scripts.current_evaluate import summarize_case
    def case(diff):
        rule_order=["a","b"]
        ai_order=list(reversed(rule_order))
        rule_rows=[{"item_id":key,"eligible":True,"tie_key":"(0, False, Decimal('0'))"} for key in rule_order]
        ai_rows=[{"item_id":key,"eligible":True,"action":"사람 검토","priority":v,"tie_key":str(v)}
                 for key,v in zip(ai_order,(100,95))]
        if not diff:
            ai_rows=[{**row,"priority":100,"tie_key":"100"} for row in reversed(ai_rows)]
        def arm(rows):
            keys=[r["item_id"] for r in rows]
            return {"items":rows,"fixed_k":keys[:1],"operational":keys[:1],"waiting":keys[1:]}
        ranking={"case":"t","mandatory":[],"common_item_count":2,"selector_condition":"TERRA","triz":[],
                 "decision_run":1,"lookup_run":2,"selector_seconds":0,"rule":arm(rule_rows),"ai":arm(ai_rows)}
        row=summarize_case("t",ranking,{"a":"acceptable","b":"material"},1,"TERRA")
        for side in ARMS:
            row[side]["operating"]["proxy_seconds"]=None
        return row
    high=case(True)
    tied=case(False)
    assert high["concordance_delta_ai_minus_rule"]==0.5
    assert tied["concordance_delta_ai_minus_rule"]==0
    assert infer([high]*14)["rank_superiority"] is None
    assert infer([high]*15)["rank_superiority"] is None
    result=infer([high]*14+[tied])
    assert result["rank_superiority"] is True
    assert result["known_operating_additional_miss_ceiling_satisfied"] is None
    assert infer([high]*36+[tied])["known_operating_additional_miss_ceiling_satisfied"] is True
