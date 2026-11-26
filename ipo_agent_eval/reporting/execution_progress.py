"""Append operational counts without reading selections, answers, or grades."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]/"reports/a1_main/v1"


def snapshot():
    count=lambda pattern:sum(1 for _ in BASE.glob(pattern))
    state={k:count(p) for k,p in {
        "a0_role":"terra/*/A0.json","c_role":"terra/*/C.json","role_reviews":"terra/*/role_audit.json",
        "ranked":"terra/*/ranking.json","execution_failures":"terra/*/failure.json",
        "preparation_partial":"terra/*/preparation.json","blind_starts":"blind/*/*/attempt-*/outbound.txt",
        "blind_closed":"blind/*/*/attempt-*/closed.json","blind_first":"blind/*/first/accepted.json",
        "blind_second":"blind/*/second/accepted.json","blind_reconciled":"blind/*/reconcile/accepted.json",
        "blind_proposals":"blind/*/proposal.json","blind_sealed":"blind/*/sealed.json",
        "time_assignments":"timing/assignments.json","timing_finished":"timing/*/*/timing.json",
        "analysis":"analysis/results.json"}.items()}
    db=BASE/"terra/ledger.sqlite3"
    if db.exists():
        with closing(sqlite3.connect(db.as_uri()+"?mode=ro",uri=True)) as conn:
            state["terra_starts"]=conn.execute("select count(*) from attempt").fetchone()[0]
            state["terra_closed"]=conn.execute("select count(*) from outcome").fetchone()[0]
    output=BASE/"execution_events.jsonl"
    last=json.loads(output.read_bytes().splitlines()[-1]) if output.exists() else None
    if last is None or last["counts"]!=state:
        now=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")
        with output.open("a",encoding="utf8") as file:
            file.write(json.dumps({"at_kst":now,"counts":state})+"\n")
    print(json.dumps(state))


if __name__=="__main__":
    snapshot()
