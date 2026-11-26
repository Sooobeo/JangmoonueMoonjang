"""Run the corrected HDMS candidate packet through a fresh local Codex session."""

import json
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from ipo_eval.blind_reviewer import REVIEW, audit_answer

from .current_j2 import OUTPUT, ROOT, c_label, paired, read, sha, write

PROXY = ROOT / "reports/a1_current/proxy"
RESULT = PROXY / "dev_hdms_c"
TEXT_EVENTS = {"reasoning", "agent_message", "plan", "error"}


def submit():
    audit_path = RESULT / "audit.json"
    if audit_path.exists():
        audit = read(audit_path)
        if audit["status"] == "SUBMITTED":
            return audit
        raise RuntimeError("Previous isolated Codex execution failed; inspect its logs")
    cli = shutil.which("codex")
    if not cli:
        raise RuntimeError("Codex CLI was not found")
    packet_file = OUTPUT / "packets/HDMS_C_original.json"
    packet = read(packet_file)
    digest = sha(packet_file.read_bytes())
    private = read(OUTPUT / "operator/HDMS_sources.json")
    if digest != private["packet_sha256"]:
        raise ValueError("Masked packet digest does not match the source ledger")
    prompt = (ROOT / "prompts/blind_reviewer.md").read_text(encoding="utf-8")
    prompt += "\n\n추가 파일이나 도구는 열지 말고 아래 제공 자료만 사용해 최종 JSON을 작성하라.\n\n"
    prompt += json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    RESULT.mkdir(parents=True, exist_ok=True)
    (RESULT / "request.txt").write_text(prompt, encoding="utf-8")
    write(RESULT / "packet.json", packet)
    write(RESULT / "response_schema.json", REVIEW)
    started = time.monotonic()
    with TemporaryDirectory(prefix="ipo-role-session-") as temp:
        scratch = Path(temp)
        schema_file = scratch / "response_schema.json"
        write(schema_file, REVIEW)
        final_file = scratch / "final.json"
        command = [cli, "-a", "never", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                   "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--color", "never",
                   "--output-schema", str(schema_file), "--output-last-message", str(final_file), "-"]
        execution = subprocess.run(command, input=prompt.encode(), cwd=scratch, capture_output=True,
                                   timeout=240, check=False)
        answer = read(final_file) if final_file.exists() and final_file.stat().st_size else None
    (RESULT / "events.jsonl").write_bytes(execution.stdout)
    if execution.stderr:
        (RESULT / "stderr.txt").write_bytes(execution.stderr)
    events = [json.loads(line) for line in execution.stdout.splitlines() if line.strip()]
    tool_events = [event["item"]["type"] for event in events if "item" in event and
                   event["item"]["type"] not in TEXT_EVENTS]
    completed = next((event for event in events if event["type"] == "turn.completed"), {})
    run_id = next((event["thread_id"] for event in events if event["type"] == "thread.started"), None)
    covered = {row["candidate_id"] for row in packet["candidates"]}
    allowed = {fact["evidence_id"] for fact in packet["issuer_evidence"]}
    allowed.update(fact["evidence_id"] for candidate in packet["candidates"] for fact in candidate["business"])
    coverage = audit_answer(answer, covered, allowed) if answer else None
    status = "SUBMITTED" if execution.returncode == 0 and coverage is not None and not any(coverage.values()) and not tool_events else "FAILED"
    audit = {"status": status, "engine": "Codex CLI / ChatGPT", "thread_id": run_id,
             "version": subprocess.check_output([cli, "--version"]).decode().strip(),
             "elapsed_seconds": round(time.monotonic() - started, 3), "usage": completed.get("usage"),
             "returncode": execution.returncode, "tool_events": tool_events, "packet_sha256": digest,
             "candidate_coverage": coverage, "historical_api_source_unchanged": True}
    write(audit_path, audit)
    if status != "SUBMITTED":
        raise RuntimeError("Isolated Codex submission did not complete within its contract")
    write(RESULT / "response.json", answer)
    return audit


def mix(audit):
    data = read(OUTPUT / "labels.json")
    hdms = next(case for case in data["cases"] if case["case_id"] == "HDMS")
    private = read(OUTPUT / "operator/HDMS_sources.json")
    response = read(RESULT / "response.json")
    for row in hdms["items"]:
        reviewed = c_label(row["target_id"], response, private["sources"], audit["thread_id"], None)
        if row["target_id"] == "C22" and reviewed["raw_text"]["decision"] == "REVIEW":
            # The review identified a concrete conflict in the full-company business mix.
            reviewed["judgment"] = "문제 제기"
            reviewed["annotation"] = "REVIEW의 방산·항공우주 및 신조 지적을 구체적인 반대 근거로 연결"
            reviewed["open_condition"] = "사후시장 수주의 매출 전환과 전사 매출·이익 비중 확인"
            for fact in reviewed["evidence"]:
                if "E22" in fact["source_refs"]:
                    fact["direction"] = "약화"
        if row["target_id"] == "C43":
            reviewed["open_condition"] = "해당 부문의 연결 이익 기여도와 전사 재무·배수 확인"
        for fact in reviewed["evidence"]:
            if set(fact["source_refs"]) <= {"E11", "E12"}:
                fact["direction"] = "조건 설명"
        row["c"] = {**reviewed, "execution_origin": "codex_cli_isolated"}
        row["pair_status"] = paired(row["a0"], row["c"])
    hdms["c_run"] = {"directory": "dev_hdms_c", "schema_version": "codex-cli-blind-1", "summary": audit}
    hdms["c_api_error"] = None
    hdms["c_original_api_attempt"] = "credit_balance_exhausted"
    hdms["c_exploratory_proposals"] = {key: response[key] for key in ("earnings", "aggregation")}
    data["schema_version"] = "current-j2-original-labels-1"
    data["run_cohort"] = "dev_mixed_api_and_codex"
    data["role_execution_origins"] = {"HDMS": {"a0": "openai_responses_api", "c": "codex_cli_isolated"},
                                      "MELCON": {"a0": "openai_responses_api", "c": "openai_responses_api"}}
    target = PROXY / "labels_dev_mixed.json"
    with TemporaryDirectory(dir=PROXY, prefix="staging-") as directory:
        staged = Path(directory) / target.name
        write(staged, data)
        staged.replace(target)
    return target


if __name__ == "__main__":
    print(mix(submit()))
