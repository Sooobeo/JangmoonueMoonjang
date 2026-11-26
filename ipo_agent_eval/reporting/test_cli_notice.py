import pytest

from reporting import a1_cli_recovery as recovery


@pytest.fixture
def recorded_attempt(tmp_path):
    b=recovery.blind
    folder=tmp_path/"first"/"attempt-1"
    folder.mkdir(parents=True)
    packet={"items":[{"item_id":"one","physical_pages":[1],"question":"근거가 있는가?"}],"pages":{"1":"공시 원문"}}
    req={"instructions":b.RULE,"schema":b.GRADE,"model":b.MODEL,"reasoning":"medium","input":packet}
    payload=b.RULE.encode()+b"\n"+b.wire(packet)
    (folder.parent/"request.json").write_bytes(b.wire(req))
    (folder/"outbound.txt").write_bytes(payload)
    row={"item_id":"one","grade":"수용 가능","physical_page":1,"reason":"원문 확인","quote":"공시 원문"}
    events=[{"type":"thread.started","thread_id":"test"},
            {"type":"item.completed","item":{"id":"item_0","type":"error","message":recovery.NOTICE}},
            {"type":"turn.started"},
            {"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":b.wire({"items":[row]}).decode()}},
            {"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":10}}]
    (folder/"stdout.jsonl").write_bytes(b"\n".join(map(b.wire,events)))
    (folder/"stderr.txt").write_bytes(b"")
    (folder/"closed.json").write_bytes(b.wire({"valid":False,"tool_events":["error"],"sessions":["test"],
                           "usage":[events[-1]["usage"]],"request_sha256":b.hash_bytes(b.wire(req)),
                           "stdin_sha256":b.hash_bytes(payload)}))
    return folder


def test_accept_only_the_known_pre_turn_local_notice(recorded_attempt):
    assert recovery.verify_historical(recorded_attempt)["valid"]
    p=recorded_attempt/"stdout.jsonl"
    p.write_bytes(p.read_bytes().replace(b"Under-development",b"Unexpected"))
    with pytest.raises(ValueError,match="notice pattern"):
        recovery.verify_historical(recorded_attempt)


def test_tool_attempt_stays_invalid(recorded_attempt):
    (recorded_attempt/"stderr.txt").write_bytes(b"codex::tools::router")
    with pytest.raises(ValueError,match="notice pattern"):
        recovery.verify_historical(recorded_attempt)


def test_real_quote_contract_still_applies(recorded_attempt):
    p=recorded_attempt/"stdout.jsonl"
    p.write_bytes(p.read_bytes().replace("공시 원문".encode(),"없는 문구".encode()))
    assert not recovery.verify_historical(recorded_attempt)["valid"]
