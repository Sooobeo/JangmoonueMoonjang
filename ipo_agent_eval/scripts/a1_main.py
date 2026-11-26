"""Preflight, freeze, blind grading and timing for a1-main-v1. Run with python -m scripts.a1_main."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz
from scripts.a1_main_blind import (BASE, ROOT, MODEL, CATALOG, GRADE, RULE, ROLE, REVIEW,
                                   grade, hash_bytes, read, seal_grades, timed_review, wire, write_once)
from scripts.a1_main_terra import ROSTER, ROSTER_SHA, contracts, check_inputs, load_freeze, input_keys
from scripts.current_validation import COMMON

PROTOCOL = ROOT.parent / "update plan/A1_본평가_동결_프로토콜.md"
TEAM = PROTOCOL.with_name("real real update.md")
PACKAGES = ("openai","httpx","tiktoken","jsonschema","PyMuPDF","pypdf","scipy","beautifulsoup4","lxml","python-dotenv","pyarrow")


def runtime_info():
    return {"python":sys.version,"platform":platform.platform(),"packages":
            {name:importlib.metadata.version(name) for name in PACKAGES}}


def fingerprints():
    protocol = PROTOCOL.read_text(encoding="utf8")
    for prompt,schema in [*contracts().values(),(RULE,GRADE),(ROLE,REVIEW)]:
        for data in (prompt.encode(),wire(schema)):
            if hash_bytes(data) not in protocol:
                raise ValueError("Registered instruction/schema differs from implementation")


def pdf_check(row, folder):
    path = ROSTER.parent / row["pdf_file"]
    if hash_bytes(path.read_bytes())!=row["pdf_sha256"]:
        raise ValueError(f"Wrong PDF bytes: {row['receipt']}")
    files = ("items","b","a0","catalog","grading","preparation_items")
    if any(not (folder/(name+".json")).exists() for name in files):
        return False, ["항목·B·질문 입력 작성 중"]
    items, b, a0, cat, grading, prepared = (read(folder/(name+".json")) for name in files)
    ids = [r["id"] for r in items]
    if not (len(items)>=7 and len(ids)==len(set(ids)) and all(k.startswith(row["receipt"]+"-") for k in ids)):
        raise ValueError("Original population/IDs")
    if ids != [f"{row['receipt']}-{offset:02}" for offset in range(1,len(ids)+1)]:
        raise ValueError("Original serial order changed")
    if [(q["family"],q["question"]) for q in items[:7]] != COMMON:
        raise ValueError("Seven common questions differ from protocol")
    if [q["family"] for q in items[7:]] != ["J1"]*prepared["adjustment_count"]+["J2"]*prepared["peer_count"]:
        raise ValueError("Adjustment / peer row counts differ from registry")
    if [i["item_id"] for i in grading["items"]] != ids or [i["item_id"] for i in a0["items"]]!=ids:
        raise ValueError("Role populations differ")
    if set(grading)!={"items","pages"} or any(set(q)-{"item_id","question","question_type","pages","physical_pages"}
                                             for q in grading["items"]):
        raise ValueError("Blind grader received non-neutral data")
    if b["pdf_sha256"]!=row["pdf_sha256"] or prepared["verified_source_sha256"]!=row["pdf_sha256"]:
        raise ValueError("B/registry PDF mismatch")
    if not all(prepared[k] is True for k in ("full_j1_adjustment_review","final_per_peer_order_verified",
                                             "b_valuation_cells_verified")):
        return False, ["항목 모집단·근거 대조 미완료"]
    cat_pages=cat["pages"]
    with fitz.open(path) as doc:
        if len(doc)!=row["pdf_pages"]:
            raise ValueError("PDF physical page count changed")
        for n, saved in cat_pages.items():
            if not 1<=int(n)<=len(doc) or doc[int(n)-1].get_text(sort=True)!=saved:
                raise ValueError("Catalog bytes differ from physical page "+n)
    for item, question in zip(items,grading["items"]):
        if item["question"]!=question["question"] or any(str(n) not in grading["pages"] for n in item["pages"]):
            raise ValueError("Mismatched item or isolated page")
        for ev in item["evidence"]:
            page = str(ev["page"])
            short = "".join(ev["quote"].split())
            if not short or short not in "".join(cat_pages[page].split()) or int(page) not in item["pages"]:
                raise ValueError("Unreproducible original quote "+item["id"])
    if any(cat_pages.get(n)!=s for n,s in grading["pages"].items()) or any(
            cat_pages.get(n)!=s for n,s in a0["original_physical_pages"].items()):
        raise ValueError("Grader page leak")
    check_inputs(row["receipt"],{"items":items,"catalog":cat,"b":b,"a0":a0})
    return True, []


def preflight():
    fingerprints()
    isolation = read(BASE/"isolation.json")
    if (isolation["active_tools"] or hash_bytes(CATALOG.read_bytes()) != isolation["catalog_sha256"]
            or hash_bytes(Path(shutil.which("codex")).read_bytes()) != isolation["codex_binary_sha256"]):
        raise ValueError("Codex isolation drift")
    rows = read(ROSTER)["rows"]
    if hash_bytes(ROSTER.read_bytes())!=ROSTER_SHA or len(rows)!=37 or len({r["corp_code"] for r in rows})!=37:
        raise ValueError("Original roster mismatch")
    flow={}
    for row in rows:
        case = row["receipt"]
        folder=BASE/"issuers"/case
        try:
            ready, reasons = pdf_check(row,folder)
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            raise ValueError(f"{case}: {exc}") from exc
        cs = folder/"c_status.json"
        status = read(cs) if cs.exists() else None
        c_ready = bool(ready and status and status.get("ready") is True)
        if not c_ready:
            reasons.append(status.get("reasons",status.get("reason","C 가림자료 미완료")) if status else "C 자료 작성 중")
        state = {"grading_ready":ready,"a0_ready":ready,"c_ready":c_ready,"terra_ready":ready and c_ready,
                 "reasons":reasons,"preparation_recorded":cs.exists() and (folder/"preparation_items.json").exists()}
        if c_ready:
            data={k:read(folder/(k+".json")) for k in input_keys(state)}
            check_inputs(case,data)
        flow[case]=state
    return flow


def freeze():
    flow=preflight()
    if not all(r["preparation_recorded"] for r in flow.values()):
        raise ValueError("37 preparation decisions must be recorded before first transmission")
    prepared = read(BASE/"c_preparation.json")
    expected = {key: val["c_ready"] for key, val in flow.items()}
    if ({r["receipt"]: r["ready"] for r in prepared["rows"]} != expected
            or prepared["ready"] != sum(expected.values())):
        raise ValueError("C preparation summary does not match the final 37 issuer packets")
    review = read(BASE/"c_three_reviews.json")
    if (review["issuers_with_findings"] or {r["receipt"]: r["prepared"] for r in review["rows"]} != expected):
        raise ValueError("C review findings or version mismatch")
    for r in review["rows"]:
        packet = BASE/"issuers"/r["receipt"]/"c.json"
        if r["wire_sha256"] != (hash_bytes(packet.read_bytes()) if packet.exists() else None):
            raise ValueError(f"Reviewed C packet was subsequently changed: {r['receipt']}")
    for r in read(BASE/"c_content_review.json")["issuers"]:
        folder=BASE/"issuers"/r["receipt"]
        packet=folder/"c.json"
        if (r["findings"] or r["wire_sha256"] != (hash_bytes(packet.read_bytes()) if packet.exists() else None)
                or r["private_sha256"] != hash_bytes((folder/"c_private.json").read_bytes())):
            raise ValueError(f"Unresolved C content or source review: {r['receipt']}")
    # A source mismatch raises above. A real source shortage stays in the cohort under its own reason.
    paths = {ROSTER, PROTOCOL, TEAM, PROTOCOL.with_name("updateplan.md"), ROOT/"pyproject.toml",
             CATALOG, BASE/"isolation.json", BASE/"item_preparation_review.json", BASE/"c_preparation.json",
             ROOT/"reporting/a1_role_source_review.py", ROOT/"reporting/a1_main_recheck.py"}
    paths.update(p for p in BASE.glob("*.json") if p.name != "freeze.json")
    for row in read(ROSTER)["rows"]:
        paths.add(ROSTER.parent/row["pdf_file"])
    for directory,pattern in ((ROOT/"scripts","*.py"), (ROOT/"ipo_eval","*.py"),(ROOT/"config","*"),
                              (ROOT/"prompts","*"),(BASE/"issuers","*"),(BASE/"c_source","*"),
                              (ROOT/"data/a1_main","*"),(BASE/"preparation","*")):
        paths.update(p for p in directory.rglob(pattern) if p.is_file() and "__pycache__" not in p.parts)
    manifest={"protocol":"a1-main-v1","model":MODEL,"roster_sha256":ROSTER_SHA,
              "runtime":runtime_info(),"issuers":flow,"files":{
              Path(os.path.relpath(p,ROOT)).as_posix():hash_bytes(p.read_bytes()) for p in sorted(paths)}}
    raw=wire(manifest)
    write_once(BASE/"freeze.json",raw)
    write_once(BASE/"freeze.sha256",(hash_bytes(raw)+"\n").encode())
    load_freeze(BASE/"freeze.json")
    return flow


def run_tasks(tasks, handler, workers):
    def attempt(arg):
        try:
            handler(*arg)
            return "complete"
        except (ValueError,RuntimeError,OSError) as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for args,outcome in zip(tasks,pool.map(attempt,tasks)):
            print(*args,outcome,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("preflight","freeze","grade","seal-grades","time","report"))
    parser.add_argument("--workers",type=int,default=4)
    args=parser.parse_args()
    if args.action in {"preflight","freeze"}:
        flow=freeze() if args.action=="freeze" else preflight()
        print(json.dumps(flow,ensure_ascii=False,indent=2))
        return
    _,cases,states,_=load_freeze(BASE/"freeze.json")
    if read(BASE/"freeze.json")["runtime"]!=runtime_info():
        raise ValueError("Frozen runtime differs")
    if args.action=="grade":
        if hash_bytes(Path(shutil.which("codex")).read_bytes())!=read(BASE/"isolation.json")["codex_binary_sha256"]:
            raise ValueError("Codex binary differs from isolation test")
        run_tasks([(c,) for c in cases if states[c]["grading_ready"]],grade,args.workers)
    elif args.action=="seal-grades":
        run_tasks([(c,) for c in cases if (BASE/"blind"/c/"proposal.json").exists()],seal_grades,1)
    elif args.action=="time":
        if hash_bytes(Path(shutil.which("codex")).read_bytes())!=read(BASE/"isolation.json")["codex_binary_sha256"]:
            raise ValueError("Codex binary differs from isolation test")
        from scripts.a1_main_timing import freeze_assignments
        run_tasks(freeze_assignments(cases)["order"],timed_review,1)
    else:
        from scripts.a1_main_analysis import report
        report(cases,states)


if __name__=="__main__":
    main()
