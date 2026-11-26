"""Synthetic end-to-end challenge for the independent A1 verification program."""

import json
import runpy
from itertools import product
from pathlib import Path

from ipo_eval.a1_main_ledger import Ledger
from reporting import a1_main_recheck as independent
from scripts import a1_main_analysis as analysis
from scripts import a1_main_blind as blind
from scripts import a1_main_terra as terra
from scripts import a1_main_timing as timing


def put(path, value):
    blind.write_once(path, blind.wire(value))


def test_shared_deferred_range_agrees_with_every_assignment_including_ties():
    queues = {
        "ai": {"scores": {"a": 1, "b": 1, "c": 2, "d": 0, "e": 4}},
        "rule": {"scores": {"a": 4, "b": 2, "c": 2, "d": 3, "e": 0}},
    }
    for fixed in ([], ["a"], ["a", "e"]):
        grades = {k: independent.PENDING for k in queues["ai"]["scores"]}
        for n, key in enumerate(fixed):
            grades[key] = (independent.MINOR, independent.MATERIAL)[n]
        unresolved = [k for k, g in grades.items() if g == independent.PENDING]
        all_deltas = []
        for changes in product(
            (independent.MINOR, independent.MATERIAL), repeat=len(unresolved)
        ):
            final = {**grades, **dict(zip(unresolved, changes))}
            scores = [
                independent.primary(queues[arm]["scores"], final)
                for arm in ("ai", "rule")
            ]
            if scores[0] is not None:
                all_deltas.append(scores[0] - scores[1])
        bounds, valid = independent.deferred_range(queues, grades)
        assert valid == len(all_deltas)
        assert all(
            abs(a - b) < 1e-12
            for a, b in zip(bounds, (min(all_deltas), max(all_deltas)))
        )


def test_independent_recheck_37_routes_raw_votes_http_and_timing(tmp_path, monkeypatch):
    fixtures = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "tests/test_a1_main_terra.py")
    )
    case, ids, data, answers = fixtures["mock_case"]()
    cases = [case] + [str(20200000000000 + i) for i in range(36)]
    for module in (analysis, blind, timing):
        monkeypatch.setattr(module, "BASE", tmp_path)
    roster = tmp_path / "roster.json"
    monkeypatch.setattr(analysis, "ROSTER", roster)
    put(
        roster,
        {
            "rows": [
                {"receipt": c, "issuer": "워트" if c == cases[-1] else c} for c in cases
            ]
        },
    )
    states = {c: {"grading_ready": c in cases[:2]} for c in cases}
    put(
        tmp_path / "freeze.json",
        {"issuers": states, "roster_sha256": independent.digest(roster.read_bytes())},
    )
    for c in cases[1:]:
        put(
            tmp_path / "terra" / c / "preparation.json",
            {"fallback": "mandatory_only", "operational": None},
        )
    folder = tmp_path / "terra" / case
    ledger = Ledger(
        tmp_path / "terra/ledger.sqlite3",
        independent.digest((tmp_path / "freeze.json").read_bytes()),
    )
    by_prompt = {p: stage for stage, (p, _) in terra.contracts().items()}

    def transport(wire, timeout):
        stage = by_prompt[json.loads(wire)["instructions"]]
        return fixtures["raw"](answers[stage], id=stage)

    agent = terra.Assessor(ledger, transport)
    terra.run_case(case, data, agent, folder, True)
    audit = independent.read(folder / "audit_template.json")
    for key in audit["records"]:
        audit["records"][key] = {
            "status": "conditional" if key == ids[1] else "verified",
            "reason": "synthetic quote checked",
        }
    put(folder / "role_audit.json", audit)
    terra.run_case(case, data, agent, folder, False)
    i = tmp_path / "issuers" / case
    put(i / "b.json", data["b"])
    put(i / "items.json", data["items"])
    put(
        i / "grading.json",
        {
            "items": [
                {"item_id": r["id"], "question": r["question"]} for r in data["items"]
            ],
            "pages": {
                "1": "original filing quotation",
                "2": "additional filing quotation",
            },
        },
    )
    candidate_grades = {key: independent.GRADES[n % 4] for n, key in enumerate(ids)}

    def vote(task, instruction, schema, packet, check):
        if instruction == blind.RULE:
            items = [
                {"item_id": q["item_id"], "grade": candidate_grades[q["item_id"]]}
                for q in packet["items"]
            ]
            if task.name == "first":
                items[0]["grade"] = independent.PENDING
            record = {
                "answer": {"items": items},
                "sessions": [task.name],
                "valid": True,
            }
        else:
            source = {
                "model": "gpt-6.2-astra",
                "reasoning": "medium",
                "instructions": instruction,
                "schema": schema,
                "input": packet,
            }
            put(task / "request.json", source)
            blind.write_once(
                task / "attempt-1/outbound.txt",
                instruction.encode() + b"\n" + blind.wire(packet),
            )
            record = {
                "valid": True,
                "elapsed_seconds": 1.2,
                "session_seconds": 1,
                "verification_seconds": 0.1,
                "tool_events": [],
                "sessions": [task.name],
                "answer": {
                    "citations": [
                        {
                            "physical_page": 1,
                            "quote": "original filing quotation",
                            "locator": "table",
                        }
                    ]
                },
            }
        put(task / "attempt-1/closed.json", record)
        put(task / "accepted.json", record)
        return record

    monkeypatch.setattr(blind, "submit", vote)
    draft = blind.grade(case)
    put(
        tmp_path / "blind" / case / "source_audit.json",
        {
            k: {"supported": True, "basis": "synthetic source"}
            for k, r in draft["items"].items()
            if r["requires_source_audit"]
        },
    )
    blind.seal_grades(case)
    # Initial agreement includes this issuer although the third session failed twice.
    disputed = tmp_path / "blind" / cases[1]
    for phase, grade in (
        ("first", independent.MINOR),
        ("second", independent.MATERIAL),
    ):
        raw = {
            "valid": True,
            "answer": {"items": [{"item_id": "other", "grade": grade}]},
        }
        put(disputed / phase / "accepted.json", raw)
        put(disputed / phase / "attempt-1/closed.json", raw)
    for n in (1, 2):
        put(disputed / "reconcile" / f"attempt-{n}" / "closed.json", {"valid": False})
    allocation = timing.freeze_assignments(cases)
    for issuer, item in allocation["order"]:
        blind.timed_review(issuer, item)
    analysis.report(cases, states)
    verified = independent.recheck(tmp_path, roster)
    assert verified["differences"] == []
    assert (
        independent.read(tmp_path / "analysis/results.json")["agreement_denominator"]
        == len(ids) + 1
    )
    assert verified["pairs"] == 1 and verified["timing"]["assigned"] == 3
    artifact = tmp_path / "analysis/results.json"
    tamper = independent.read(artifact)
    tamper["overall"]["known_material"] += 1
    tamper["cost"]["accounted_ceiling_usd"] += 0.01
    tamper["operational_review_timing"]["paired_delta_seconds_ai_minus_rule"] += 1
    artifact.write_bytes(blind.wire(tamper))
    mismatch = independent.recheck(tmp_path, roster)["differences"]
    assert {r["source"] for r in mismatch} == {
        "all/known_material",
        "cost/accounted_ceiling_usd",
        "time/paired delta",
    }
