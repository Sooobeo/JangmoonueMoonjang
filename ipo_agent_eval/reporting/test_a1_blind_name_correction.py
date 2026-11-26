import json
import runpy
import sqlite3
from pathlib import Path

import pytest

from reporting import a1_blind_name_correction as correction
from scripts import a1_main_terra as terra


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(correction.canonical(value))


def test_short_marker_only_for_candidates_at_registered_limit():
    text = "한전 포스코 " + "x" * 342
    packet = {
        "issuer_evidence": [],
        "candidates": [
            {"business": [{"evidence_id": "E1", "text": text}], "financials": []}
        ],
    }
    sources = {
        "sources": {"E1": {"masked_excerpt": text, "quote": text, "redactions": {}}}
    }
    fixes = {
        "E1": [
            {"literal": literal, "replacement": "○○"} for literal in ("한전", "포스코")
        ]
    }
    changed, _ = correction.substitute(packet, sources, fixes)
    assert correction.rows(changed)["E1"]["text"] == "○○ ○○ " + "x" * 342
    packet["candidates"][0]["business"][0]["text"] = "한전 포스코"
    sources["sources"]["E1"]["masked_excerpt"] = "한전 포스코"
    with pytest.raises(ValueError, match="substitution"):
        correction.substitute(packet, sources, fixes)


def test_prospective_only_or_verified_original_and_paired_selector(
    tmp_path, monkeypatch
):
    fixtures = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "tests/test_a1_main_terra.py")
    )
    sent, _, packet, answers = fixtures["mock_case"]()
    fresh = "20240101000002"
    directory = tmp_path / "corrections/c_blind_names"
    freeze = tmp_path / "freeze.json"
    boundary = tmp_path / "terra/operator_pause_blind_identifiers.json"
    for key, value in (
        ("BASE", tmp_path),
        ("DIRECTORY", directory),
        ("FREEZE", freeze),
        ("BOUNDARY", boundary),
    ):
        monkeypatch.setattr(correction, key, value)
    write(freeze, {"original_manifest": True})
    policy = tmp_path / "corrections/c_identity/판단규칙.md"
    write(policy, "prospective only")
    write(directory / "aliases.json", {"name": "Company Name"})
    write(
        directory / "replacements.json",
        {
            c: {"E1": [{"literal": "Company Name", "replacement": "[기업]"}]}
            for c in (sent, fresh)
        },
    )
    datasets = {}
    for case in (sent, fresh):
        data = json.loads(json.dumps(packet).replace(sent, case))
        data["c"]["issuer_evidence"][0]["text"] = "Company Name supplies steel."
        data["c_private"]["sources"] = {
            eid: {"masked_excerpt": r["text"], "quote": r["text"], "redactions": {}}
            for eid, r in correction.rows(data["c"]).items()
        }
        datasets[case] = data
        for k in ("c", "c_private"):
            write(tmp_path / "issuers" / case / (k + ".json"), data[k])
    exposed_packet = datasets[sent]["c"]
    pause_rows = []
    boundary.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(tmp_path / "terra/ledger.sqlite3")
    db.execute(
        "CREATE TABLE attempt(id INTEGER PRIMARY KEY,receipt TEXT,stage TEXT,kind TEXT,request BLOB,request_hash TEXT)"
    )

    def insert(n, case, stage, payload, kind="initial"):
        raw = correction.canonical({"input": correction.canonical(payload).decode()})
        db.execute(
            "INSERT INTO attempt VALUES(?,?,?,?,?,?)",
            (n, case, stage, kind, raw, correction.sha(raw)),
        )

    for n in range(1, 46):
        stage = "C" if n == 1 else "A0"
        insert(n, sent, stage, exposed_packet if stage == "C" else {})
        pause_rows.append([n, sent, stage, "initial", 200])
    db.execute(
        "CREATE TRIGGER operator_pause_admission BEFORE INSERT ON attempt BEGIN SELECT RAISE(ABORT,'pause'); END"
    )
    db.commit()
    write(boundary, {"reservations": pause_rows})
    monkeypatch.setattr(
        terra,
        "load_freeze",
        lambda path: (
            correction.sha(freeze.read_bytes()),
            [sent, fresh],
            {c: {"c_ready": True} for c in datasets},
            {},
        ),
    )
    monkeypatch.setattr(
        terra,
        "load_inputs",
        lambda case, files, keys: {k: datasets[case][k] for k in keys},
    )
    original = {c: (tmp_path / "issuers" / c / "c.json").read_bytes() for c in datasets}
    write(
        directory / "audit.json",
        {
            "rows": [
                {
                    "case": c,
                    "original_sha256": correction.sha(original[c]),
                    "sent_before_pause": c == sent,
                    "original_flags": {
                        "direct_self_or_issuer": True,
                        "direct_third_party": False,
                    },
                    "prospective_flags": {
                        "direct_self_or_issuer": False,
                        "direct_third_party": False,
                    },
                }
                for c in datasets
            ],
            **{
                k: correction.sha(p.read_bytes())
                for k, p in {
                    "decision_rule_sha256": policy,
                    "before_pause_reservations_sha256": boundary,
                    "aliases_sha256": directory / "aliases.json",
                    "replacements_sha256": directory / "replacements.json",
                }.items()
            },
        },
    )
    record = correction.prepare()
    assert record["applied"] == [fresh] and record[
        "already_exposed_with_identifiers"
    ] == [sent]
    with correction.effective_inputs():
        retained = terra.load_inputs(sent, {}, ("c", "c_private"))
        changed = terra.load_inputs(fresh, {}, ("c", "c_private"))
        assert retained["c"] == exposed_packet
        assert changed["c"]["issuer_evidence"][0]["text"] == "[기업] supplies steel."
        assert (
            changed["c_private"]["sources"]["E1"]["quote"]
            == "Company Name supplies steel."
        )
        assert (
            correction.review.read(tmp_path / "issuers" / fresh / "c.json")
            == changed["c"]
        )
    assert all(
        (tmp_path / "issuers" / c / "c.json").read_bytes() == v
        for c, v in original.items()
    )
    db.execute("DROP TRIGGER operator_pause_admission")
    insert(46, fresh, "C", changed["c"])
    insert(
        47,
        fresh,
        "C",
        {"input": changed["c"], "prior_submission": []},
        kind="format_repair",
    )
    sources = {k: r["text"] for k, r in correction.rows(changed["c"]).items()}
    insert(48, fresh, "A1_SELECT", {"original_sources": sources})
    db.commit()
    db.execute("CREATE TABLE outcome(id INTEGER PRIMARY KEY,body BLOB,body_hash TEXT)")
    for c, n in ((sent, 1), (fresh, 47)):
        _, body = fixtures["raw"](answers["C"])
        body_hash = correction.sha(body)
        db.execute("INSERT INTO outcome VALUES(?,?,?)", (n, body, body_hash))
        write(
            tmp_path / "terra" / c / "C.json",
            {"attempt": n, "response_sha256": body_hash, "answer": answers["C"]},
        )
    db.commit()
    result = correction.proof(final=True)
    assert result["checked_citations"] > 0
    assert result["actual"][fresh] == {"C": [46, 47], "A1_SELECT": [48]}
    sources["E1"] = "Company Name supplies steel."
    insert(49, fresh, "A1_SELECT", {"original_sources": sources})
    db.commit()
    with pytest.raises(ValueError, match="different C source"):
        correction.proof()
    write(directory / "replacements.json", {})
    with pytest.raises(ValueError, match="binding changed"):
        correction.verified()
    db.close()
