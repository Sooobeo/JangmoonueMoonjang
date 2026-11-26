"""Apply the logged client-notice correction without changing the frozen study inputs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

from jsonschema import ValidationError, validate
from scripts import a1_main_blind as blind

ROOT=blind.ROOT
BASE=blind.BASE
REPAIR=BASE/"corrections/cli_notice"
read=blind.read
wire=blind.wire
sha=blind.hash_bytes
publish=blind.write_once
original_command=blind.command
NOTICE=("Under-development features enabled: skip_host_skill_discovery. Under-development features are incomplete "
        "and may behave unpredictably. To suppress this warning, set " +
        chr(96)+"suppress_unstable_features_warning = true"+chr(96)+" in "+str(Path.home()/".codex/config.toml")+".")
GATE=b"a1-main-v1 temporary admission pause before starting any CLI subprocess\n"


def quiet_command(work,schema,extra=()):
    return original_command(work,schema,["-c","suppress_unstable_features_warning=true",*extra])


def verify_historical(attempt):
    old=read(attempt/"closed.json")
    req=read(attempt.parent/"request.json")
    if req["instructions"]!=blind.RULE or req["schema"]!=blind.GRADE or req["model"]!=blind.MODEL:
        raise ValueError("Historical correction is restricted to the original registered grading task")
    if old["request_sha256"]!=sha(wire(req)) or old["stdin_sha256"]!=sha((attempt/"outbound.txt").read_bytes()):
        raise ValueError("Historical input or payload mismatch")
    log=(attempt/"stdout.jsonl").read_bytes()
    err=(attempt/"stderr.txt").read_bytes()
    events=[json.loads(line) for line in log.splitlines() if line.strip()]
    # Accept a terminal result only when the sole error is the exact local pre-turn banner.
    if ([e["type"] for e in events]!=["thread.started","item.completed","turn.started","item.completed","turn.completed"] or
            events[1]["item"]!={"id":"item_0","type":"error","message":NOTICE} or
            events[3]["item"]["type"]!="agent_message" or b"tools::router" in err or
            old["sessions"]!=[events[0]["thread_id"]] or old["usage"]!=[events[4]["usage"]] or
            old["tool_events"]!=["error"] or old.get("valid")):
        raise ValueError("Not the documented client-only notice pattern")
    correction={**old,"valid":False,"tool_events":[],"notice_only_original":True,
                "original_closed_sha256":sha((attempt/"closed.json").read_bytes()),
                "original_stdout_sha256":sha(log),"original_stderr_sha256":sha(err),
                "original_return_code":"not retained; single turn.completed with final response and usage verified"}
    packet=req["input"]
    start=perf_counter()
    try:
        answer=json.loads(events[3]["item"]["text"])
        validate(answer,blind.GRADE)
        allowed={r["item_id"]:set(r["physical_pages"]) for r in packet["items"]}
        blind.verify(answer,list(allowed),packet["pages"])
        if any(r["physical_page"] not in allowed[r["item_id"]] or not r["reason"].strip() for r in answer["items"]):
            raise ValueError("Wrong item-specific page or missing reason")
    except (ValueError,ValidationError,KeyError) as exc:
        correction["error"]="Original validation: "+str(exc)[:550]
    else:
        correction.pop("error",None)
        correction.update(answer=answer,valid=True)
    correction["verification_seconds"]=perf_counter()-start
    return correction


def offline():
    from scripts import a1_main_isolation as isolation
    observed=[]
    runner=subprocess.run
    def capture(*args,**kwargs):
        result=runner(*args,**kwargs)
        if kwargs.get("input")==b"synthetic success":
            events=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            observed.append({"returncode":result.returncode,"items":[e["item"]["type"] for e in events if "item" in e],
                             "router_event":b"tools::router" in result.stderr,"terminal":events[-1]["type"]})
        return result
    with patch.object(isolation,"command",quiet_command),patch.object(subprocess,"run",capture):
        isolation.isolation_check()
    if len(observed)!=1 or observed[0]["returncode"] or observed[0]["router_event"] or (
            set(observed[0]["items"])-{"reasoning","agent_message"}) or observed[0]["terminal"]!="turn.completed":
        raise ValueError("Offline CLI emitted a substantive error or tool event")
    return observed[0]


def apply_repair():
    safety=offline()
    pause=read(REPAIR/"admission_pause.json")
    original_files=sorted(BASE.glob("blind/*/*/attempt-*/outbound.txt"))
    if sorted(p.relative_to(BASE).as_posix() for p in original_files)!=sorted(pause["already_launched"]):
        raise ValueError("A new transmission escaped the operational pause")
    tasks={}
    for outbound in original_files:
        attempt=outbound.parent
        if not (attempt/"closed.json").is_file():
            raise ValueError("Original process has not drained")
        path=attempt/"notice_revalidation.json"
        if path.exists():
            record=read(path)
        else:
            record=verify_historical(attempt)
            publish(path,wire(record))
        tasks.setdefault(attempt.parent,[]).append((attempt,record))
    used={}
    for task,attempts in tasks.items():
        eligible=[(p,r) for p,r in sorted(attempts) if r["valid"]]
        if eligible:
            p,r=eligible[0]
            publish(task/"accepted.json",wire(r))
            used[task.relative_to(BASE).as_posix()]=p.name
    files={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in
           [Path(__file__),ROOT/"scripts/a1_main_blind.py",ROOT/"scripts/a1_main_analysis.py",BASE/"freeze.json"]}
    evidence={"freeze_sha256":sha((BASE/"freeze.json").read_bytes()),"source_hashes":files,
              "affected_issuers":sorted({p.parent.parent.parent.name for p in original_files}),
              "transmitted":len(original_files),"raw_responses_recovered":sum(len(v) for v in tasks.values()),
              "original_requests_repeated_because_of_notice":sum(p.parent.name=="attempt-2" for p in original_files),
              "local_banner":NOTICE,"offline_cli_test":safety,"earliest_valid_by_task":used,
              "theoretical_incident_scope":"Codex client admission only; Terra inputs, selector, item census, grades, analysis rules and limits preserved",
              "revalidation_totals":dict(Counter("contract_valid" if r["valid"] else "contract_invalid"
                                                for values in tasks.values() for _,r in values)),
              "historical_return_code_limitation":"Original per-attempt exit code was not persisted. Each transcript used has a final answer, completed turn, usage, and no non-banner error or tool event."}
    publish(REPAIR/"resolution.json",wire(evidence))
    for location in pause["temporary_non_directory_gates"]:
        gate=(BASE/location).resolve()
        if not gate.is_relative_to((BASE/"blind").resolve()) or gate.name not in ("attempt-1","attempt-2"):
            raise ValueError("Unexpected admission gate location")
        if gate.is_file():
            if gate.read_bytes()!=GATE:
                raise ValueError("Unexpected admission gate contents")
            gate.unlink()
    print(json.dumps({k:evidence[k] for k in ("transmitted","raw_responses_recovered","revalidation_totals",
                                               "original_requests_repeated_because_of_notice")}))


def effective_read(path):
    if path.name=="closed.json":
        side=path.with_name("notice_revalidation.json")
        if side.is_file():
            decision=read(side)
            if (decision["original_closed_sha256"]!=sha(path.read_bytes()) or
                    decision["original_stdout_sha256"]!=sha(path.with_name("stdout.jsonl").read_bytes()) or
                    decision["original_stderr_sha256"]!=sha(path.with_name("stderr.txt").read_bytes())):
                raise ValueError("Recovery reference differs from the preserved response")
            return decision
    return read(path)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["repair","grade","time","report","recheck"])
    parser.add_argument("--workers",type=int,default=5)
    args=parser.parse_args()
    if args.mode=="repair":
        return apply_repair()
    resolution=read(REPAIR/"resolution.json")
    for key,digest in resolution["source_hashes"].items():
        if sha((ROOT/key).read_bytes())!=digest:
            raise ValueError("Original or corrected runtime changed")
    from scripts import a1_main, a1_main_analysis
    blind.command=quiet_command
    a1_main_analysis.read=effective_read
    if args.mode=="recheck":
        from reporting import a1_main_recheck
        a1_main_recheck.read=effective_read
        sys.argv=["a1_main_recheck","--record"]
        return a1_main_recheck.main()
    sys.argv=["a1_main",args.mode,"--workers",str(args.workers)]
    a1_main.main()


if __name__=="__main__":
    main()
