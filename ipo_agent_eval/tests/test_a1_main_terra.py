"""No-network checks for the main frozen Terra selector and exact-byte reservation."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from ipo_eval.a1_main_ledger import ConcurrentChange, Ledger, StageFailure, StopBatch
from scripts import a1_main_terra as runner


def raw(answer, id="response", usage=True):
    result = {
        "id": id,
        "model": runner.MODEL,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(answer)}],
            }
        ],
    }
    if usage:
        result["usage"] = {"input_tokens": 125, "output_tokens": 25}
    return 200, json.dumps(result).encode()


def test_frozen_contracts_and_wire_caps():
    assert len(runner.contracts()) == 4
    assert runner.sha(runner.ROSTER.read_bytes()) == runner.ROSTER_SHA
    assert runner.LIMITS["A1_LOOK"] == (1100, 2, 2200, 2500000, 90)


def test_concurrent_reservation_and_unknown_reopen(tmp_path):
    path = tmp_path / "ledger.db"
    ledger = Ledger(path, "frozen")

    def contender(_):
        try:
            return ledger.reserve("issuer", "A0", 0, b'{"x":1}', 100, "initial")
        except ConcurrentChange:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        winners = list(pool.map(contender, range(4)))
    assert winners.count(None) == 3
    ledger = Ledger(path, "frozen")
    assert ledger.summary()["accounted_ceiling_usd"] == (100 * 5 + 5100 * 20) / 4e6
    assert ledger.summary()["unknown_or_pending"] == 1
    with pytest.raises(StopBatch, match="freeze_mismatch"):
        Ledger(path, "replacement")


def test_ordered_issuers_reserve_in_order_overlap_and_replay(tmp_path):
    ledger = Ledger(tmp_path / "db", "frozen")
    receipts = list("abcd")
    first_wave = Barrier(2)

    def send(wire, timeout):
        first_wave.wait(timeout=10)
        return raw({"physical_pages": [], "reason": "lookup"})

    def process(receipt, admitted, halted):
        assessor = runner.Assessor(ledger, send, admitted, halted)
        assessor.run(receipt, "A1_LOOK", {"receipt": receipt}, lambda x: None)

    runner.ordered_issuers(receipts, 2, process)
    with ledger.connect() as db:
        assert [
            r[0] for r in db.execute("select receipt from attempt order by id")
        ] == receipts
    runner.ordered_issuers(receipts, 4, process)
    assert ledger.summary()["attempts"] == 4
    with pytest.raises(ValueError):
        runner.ordered_issuers(["a", "a"], 2, process)


def test_peer_quota_drains_reserved_calls_and_stops_queued_issuers(tmp_path):
    ledger = Ledger(tmp_path / "db", "frozen")
    second_sent = Event()

    def process(receipt, admitted, halted):
        def send(wire, timeout):
            if receipt == "a":
                assert second_sent.wait(timeout=10)
                return 429, b'{"error":{"code":"insufficient_quota"}}'
            assert receipt == "b"
            second_sent.set()
            assert halted.wait(timeout=10)
            return raw({"physical_pages": [], "reason": "lookup"})

        assessor = runner.Assessor(ledger, send, admitted, halted)
        assessor.run(receipt, "A1_LOOK", {}, lambda x: None)
        assessor.run(receipt, "A1_SELECT", {}, lambda x: None)

    with pytest.raises(StopBatch, match="billing_suspended"):
        runner.ordered_issuers(list("abcd"), 2, process)
    assert ledger.summary()["attempts"] == 2
    assert ledger.summary()["unknown_or_pending"] == 1
    with pytest.raises(StopBatch, match="billing_suspended"):
        ledger.reserve("z", "C", 0, b"x", 100, "initial")


def test_global_and_stage_caps(tmp_path):
    ledger = Ledger(tmp_path / "db", "frozen")
    # A reservation just below $1.25. The 13th reservation would exceed $15.
    for i in range(12):
        ledger.reserve(str(i), "A0", 0, b"x", 970000 - 200000, "initial")
    with pytest.raises(StageFailure):
        ledger.reserve("0", "A0", 1, b"s", 31000, "initial")
    for i in range(12, 15):
        ledger.reserve(str(i), "A0", 0, b"x", 770000, "initial")
    with pytest.raises(StopBatch):
        ledger.reserve("15", "A0", 0, b"x", 770000, "initial")
    assert ledger.summary()["attempts"] == 15


def test_retry_replay_and_unknown_usage(tmp_path):
    ledger = Ledger(tmp_path / "db", "frozen")
    sent = []

    def send(wire, timeout):
        sent.append(wire)
        return (
            (503, b'{"error":{"code":"server_error"}}')
            if len(sent) == 1
            else raw({"physical_pages": [], "reason": "ok"})
        )

    agent = runner.Assessor(ledger, send)
    result = agent.run("x", "A1_LOOK", {}, lambda a: runner.check_look([], a))
    assert len(sent) == 2 and sent[0] == sent[1]
    assert agent.run("x", "A1_LOOK", {}, lambda a: runner.check_look([], a)) == result
    assert len(sent) == 2 and ledger.summary()["unknown_or_pending"] == 1
    assert ledger.summary()["known_standard_usd"] == 0.00025
    with pytest.raises(StopBatch, match="replay_request_drift"):
        agent.run("x", "A1_LOOK", {"changed": True}, lambda a: None)


def test_no_retry_on_missing_usage_or_lookup_contract(tmp_path):
    ledger = Ledger(tmp_path / "db", "frozen")
    agent = runner.Assessor(
        ledger,
        lambda *args: raw({"physical_pages": [99], "reason": "ref"}, usage=False),
    )
    with pytest.raises(StageFailure, match="usage_unknown"):
        agent.run("a", "A1_LOOK", {}, lambda a: runner.check_look([1], a))
    agent.transport = lambda *args: raw({"physical_pages": [99], "reason": "ref"})
    with pytest.raises(StageFailure, match="response_contract"):
        agent.run("b", "A1_LOOK", {}, lambda a: runner.check_look([1], a))
    assert ledger.summary()["attempts"] == 2


def test_billing_pause_resume_without_reset(tmp_path):
    ledger = Ledger(tmp_path / "db", "frozen")

    def blocked(*args):
        return 429, b'{"error":{"code":"insufficient_quota"}}'

    agent = runner.Assessor(ledger, blocked)
    with pytest.raises(StopBatch, match="billing"):
        agent.run("a", "A1_LOOK", {}, lambda a: None)
    with pytest.raises(StopBatch, match="billing"):
        agent.run("b", "A1_LOOK", {}, lambda a: None)
    assert ledger.summary()["attempts"] == 1
    ledger.resume_billing()
    agent.transport = lambda *args: raw({"physical_pages": [], "reason": "ok"})
    agent.run("a", "A1_LOOK", {}, lambda a: None)
    assert ledger.history("a", "A1_LOOK")[1]["kind"] == "billing_resume"
    assert ledger.summary()["unknown_or_pending"] == 1


def test_invalid_select_repair_and_preserve_pre_repair_request(tmp_path):
    ledger = Ledger(tmp_path / "db", "frozen")
    sent = []

    def send(wire, timeout):
        sent.append(json.loads(wire))
        return raw({"unexpected": True} if len(sent) == 1 else {"items": []})

    agent = runner.Assessor(ledger, send)
    agent.run(
        "1", "A1_SELECT", {"initial": True}, lambda r: runner.check_select([], set(), r)
    )
    assert "prior_submission" in json.loads(sent[1]["input"])
    assert sent[0]["input"] == '{"initial":true}'
    assert [r["kind"] for r in ledger.history("1", "A1_SELECT")] == [
        "initial",
        "format_repair",
    ]


def mock_case():
    receipt = "20231119000111"
    ids = [receipt + f"-{n:02d}" for n in range(1, 9)]
    items = [
        {
            "id": i,
            "family": "J1" if n < 2 else "J2" if n == 7 else "J3",
            "target": "회사",
            "original_choice": "value",
            "original_category": ("TRAILING_FOUR_QUARTERS", "STANDALONE")[n]
            if n < 2
            else None,
            "pages": [1, 2],
            "evidence": [{"id": "S" + str(n), "page": 1, "quote": "원문"}],
            "question": "근거?",
        }
        for n, i in enumerate(ids)
    ]
    packet = {
        "issuer_evidence": [{"evidence_id": "E1", "text": "발행사 내용"}],
        "candidates": [
            {
                "candidate_id": f"C{n}",
                "business": [{"evidence_id": f"E{n + 1}", "text": "업종"}],
                "financials": [],
                "multiples": [],
            }
            for n in (1, 2)
        ],
    }
    data = {
        "a0": {
            "items": [{"item_id": i} for i in ids],
            "original_physical_pages": {"1": "원문", "2": "추가"},
        },
        "b": {"mandatory": [ids[2]], "price_impact_fraction": {ids[0]: 0.05}},
        "c": packet,
        "c_status": {"ready": True},
        "c_private": {"links": {"C1": {"item_id": ids[-1]}, "C2": {"item_id": None}}},
        "catalog": {"pages": {"1": "원문", "2": "추가"}},
        "items": items,
    }
    methods = {
        k: {"choice": v, "reason": "근거", "evidence_ids": ["E1"]}
        for k, v in {
            "period": "TRAILING_FOUR_QUARTERS",
            "attribution": "CONSOLIDATED_PARENT",
            "expense": "UNKNOWN",
            "aggregation": "UNKNOWN",
        }.items()
    }
    proposal = {"reason": "근거", "evidence_ids": ["E1"], "proposal": "근거"}
    answers = {
        "A0": {
            "items": [
                {
                    "item_id": i,
                    "physical_page": 1,
                    "quote": "원문",
                    "reason": "근거",
                    "state": "수용",
                }
                for i in ids
            ]
        },
        "C": {
            "methods": methods,
            "status": "PENDING_INFO",
            "earnings": proposal,
            "aggregation": proposal,
            "candidates": [
                {
                    "candidate_id": f"C{n}",
                    "decision": "EXCLUDE",
                    "reason": "근거",
                    "evidence_ids": [f"E{n + 1}"],
                }
                for n in (1, 2)
            ],
        },
        "A1_LOOK": {"physical_pages": [2], "reason": "추가 확인"},
        "A1_SELECT": {
            "items": [
                {
                    "item_id": i,
                    "priority": 100 if n < 2 else 50,
                    "reason": "근거",
                    "action": "자료 요청" if n == 0 else "사람 검토",
                    "question_or_request": "자료?",
                    "evidence_ids": ["PDF-2"],
                }
                for n, i in enumerate(ids)
            ]
        },
    }
    return receipt, ids, data, answers


def test_roundtrip_locked_roles_semantic_audit_ranks_and_replay(tmp_path):
    receipt, ids, data, answers = mock_case()
    ledger = Ledger(tmp_path / "db", "frozen")
    packets = []
    specs = runner.contracts()

    def send(wire, timeout):
        request = json.loads(wire)
        stage = next(k for k, (p, _) in specs.items() if p == request["instructions"])
        packets.append((stage, json.loads(request["input"])))
        return raw(answers[stage], id=stage)

    agent = runner.Assessor(ledger, send)
    assert runner.run_case(receipt, data, agent, tmp_path, False).startswith("awaiting")
    assert [s for s, _ in packets] == ["A0", "C"]
    audit = runner.read(tmp_path / "audit_template.json")
    for key in audit["records"]:
        audit["records"][key] = {
            "status": "conditional" if key == ids[1] else "verified",
            "reason": "row scope inspected",
        }
    runner.lock_json(tmp_path / "role_audit.json", audit)
    assert runner.run_case(receipt, data, agent, tmp_path, False) == "rankings_locked"
    assert runner.run_case(receipt, data, agent, tmp_path, False) == "rankings_locked"
    assert len(packets) == 4
    ranking = runner.read(tmp_path / "ranking.json")
    assert ranking["rule"]["operational"] == [ids[2], ids[-1]]
    assert ranking["ai"]["fixed_k"] == [ids[2], ids[0]]
    assert ranking["ai"]["operational"] == [ids[2], ids[1]]
    assert ids[2] not in ranking["ai"]["waiting"]
    look = packets[2][1]
    select = packets[3][1]
    assert look["triz"] == [] and look["available_pages"] == [1, 2]
    assert "PDF-2" not in select["original_sources"] and list(
        select["additional_read"]
    ) == ["PDF-2"]
    assert all("source_audit" not in r["c"] for r in select["original_items"])
    assert runner.read(tmp_path / "merged.json")["items"][1]["c"]["state"] == "미확인"


def test_reject_forged_sources_cross_item_pages_and_blind_leak():
    receipt, ids, data, answers = mock_case()
    data["items"][0]["pages"] = [2]
    with pytest.raises(ValueError, match="invalid_item_page"):
        runner.check_a0(data["items"], data["a0"], answers["A0"])
    data["c"]["issuer_evidence"][0]["text"] = ids[0]
    with pytest.raises(StopBatch, match="metadata_leak"):
        runner.check_inputs(receipt, data)
    answers["A1_SELECT"]["items"][0]["evidence_ids"] = ["FORGED"]
    with pytest.raises(ValueError, match="citation"):
        runner.check_select(ids, {"PDF-2"}, answers["A1_SELECT"])
    with pytest.raises(ValueError, match="unique"):
        runner.check_look([1, 2], {"physical_pages": [1, 1]})


def test_empty_optional_and_all_unassigned():
    mandatory = ["only"]
    assert runner.allocate([], mandatory)["operational"] == mandatory
    assert (
        runner.allocate([{"item_id": "x", "eligible": False}], [])["operational"] == []
    )


@pytest.mark.parametrize("name,stage", [("a0", "A0"), ("c", "C")])
def test_partial_manifest_executes_only_the_eligible_role(tmp_path, name, stage):
    receipt, _, data, answers = mock_case()
    keys = runner.input_keys({"terra_ready": False, name + "_ready": True})
    sent = []

    def send(wire, timeout):
        sent.append(json.loads(wire))
        return raw(answers[stage], id=stage)

    assessor = runner.Assessor(Ledger(tmp_path / "db", "partial"), send)
    roles = runner.run_roles(receipt, {k: data[k] for k in keys}, assessor, tmp_path)
    assert (
        set(roles) == {stage}
        and len(sent) == 1
        and (tmp_path / (stage + ".json")).exists()
    )
    assert not (tmp_path / "ranking.json").exists()


def test_common_failure_still_attempts_other_independent_role(tmp_path):
    receipt, _, data, answers = mock_case()
    c_prompt = runner.contracts()["C"][0]

    def send(wire, timeout):
        if json.loads(wire)["instructions"] == c_prompt:
            return raw(answers["C"], id="C")
        return 429, b'{"error":{"code":"rate_limit_exceeded"}}'

    a = runner.Assessor(Ledger(tmp_path / "db", "failure"), send)
    with pytest.raises(StageFailure, match="common_input_failure"):
        runner.run_roles(receipt, data, a, tmp_path)
    assert (tmp_path / "C.json").exists()
    assert "A0" in runner.read(tmp_path / "role_failures.json")["failures"]
