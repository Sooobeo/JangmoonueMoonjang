"""Run a disclosed Codex-proxy condition in isolated single-prompt CLI sessions."""

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from jsonschema import validate

from scripts.current_b import OUT, ROOT, dump
from scripts.current_live import digest, load


def ask_proxy(
    name, stage, instructions, payload, schema, output_limit=None, verify=None
):
    # This is a different execution condition from the paid Terra API experiment.
    request = {
        "instructions": instructions,
        "input": payload,
        "schema": schema,
        "model": "gpt-6.2-astra",
    }
    folder = OUT / "proxy" / name / stage / digest(request)[:16]
    final = folder / "result.json"
    if final.exists():
        res = load(final)
        validate(res["answer"], schema)
        if verify:
            verify(res["answer"])
        return res
    dump(folder / "request.json", request)
    extra = ""
    with tempfile.TemporaryDirectory(prefix="ipo_proxy_") as tmp:
        root = Path(tmp)
        schema_file = root / "contract.json"
        dump(schema_file, schema)
        cmd = [
            shutil.which("codex") or "codex",
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--json",
            "-m",
            request["model"],
            "-c",
            'model_reasoning_effort="medium"',
            "-C",
            str(root),
            "--output-schema",
            str(schema_file),
            "-o",
            str(root / "answer.json"),
            "-",
        ]
        start = time.monotonic()
        calls = []
        for attempt in range(2):
            out = root / "answer.json"
            out.unlink(missing_ok=True)
            prompt = (
                "Use only the supplied input. No tools, shell, files, web or workspace access. "
                "Return the final structured answer.\n"
                + instructions
                + extra
                + "\n"
                + json.dumps(payload, ensure_ascii=False)
            )
            try:
                proc = subprocess.run(
                    cmd, input=prompt.encode(), capture_output=True,
                    cwd=tmp, timeout=180, check=False,
                )
            except subprocess.TimeoutExpired:
                calls.append({"error":"timeout","seconds":180,"turn_usage":[],
                              "tool_events":None,"actual_usage_known":False})
                dump(folder / "attempts.json", calls)
                if attempt:
                    raise
                continue
            events = []
            for line in proc.stdout.decode("utf8", errors="replace").splitlines():
                if line.startswith("{"):
                    events.append(json.loads(line))
            tools = [
                e["item"]["type"]
                for e in events
                if e.get("item", {}).get("type")
                in {
                    "command_execution",
                    "mcp_tool_call",
                    "web_search",
                    "file_change",
                    "collab_tool_call",
                }
            ]
            usage = [
                e.get("usage") for e in events if e.get("type") == "turn.completed"
            ]
            calls.append(
                {
                    "returncode": proc.returncode,
                    "tool_events": tools,
                    "turn_usage": usage,
                    "events": [
                        e
                        for e in events
                        if e.get("type") in {"thread.started", "turn.failed", "error"}
                    ],
                }
            )
            dump(folder / "attempts.json", calls)
            if proc.returncode or tools or not out.exists():
                raise RuntimeError(
                    f"{name} {stage} CLI failure, code={proc.returncode}, tool_events={tools}"
                )
            a = json.loads(out.read_bytes())
            try:
                validate(a, schema)
                if verify:
                    verify(a)
                break
            except (ValueError, AssertionError) as exc:
                dump(folder / "invalid.json", a)
                if attempt:
                    raise
                extra = (
                    "\n출력 계약 보완: "
                    + str(exc)
                    + ". 제출 전 모든 원문 인용과 ID를 다시 확인한다."
                )
        res = {
            "answer": a,
            "evidence_dir": folder.relative_to(ROOT).as_posix(),
            "summary": {
                "run_id": f"{name}/{stage}/{digest(request)[:16]}",
                "execution_status": "SUBMITTED",
                "condition": "CODEX_PROXY",
                "elapsed_seconds": round(time.monotonic() - start, 2),
                "model": request["model"],
                "turn_usage": [u for c in calls for u in c["turn_usage"]],
                "estimated_cost_usd_standard_uncached": None,
            },
        }
        dump(final, res)
        return res
