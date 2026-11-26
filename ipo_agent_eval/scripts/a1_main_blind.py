"""Blinded Codex grading and review timing for the frozen A1 main cohort."""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from jsonschema import validate

from scripts.current_persona_time import REVIEW, ROLE, verify_answer
from scripts.current_validation import GRADE, GRADES, RULE, verify

MODEL = "gpt-6.2-astra"
DISABLED = ("shell_tool", "unified_exec", "browser_use", "computer_use", "apps", "plugins",
            "multi_agent", "multi_agent_v2", "hooks", "memories", "view_image", "goals",
            "sleep_tool", "skill_search", "shell_snapshot", "remote_plugin", "artifact",
            "incremental_tools", "image_generation", "default_mode_request_user_input",
            "enable_request_compression")
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/a1_main/v1"
CATALOG = BASE / "codex_catalog.json"


def read(path):
    return json.loads(path.read_bytes())


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write_once(path, data):
    """Atomically publish fully written immutable bytes, including after concurrent retries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        try:
            os.link(tmp, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError(f"Immutable record differs: {path}")
    finally:
        tmp.unlink()


def prepare_catalog():
    # Keep the registered model and reasoning level. Remove every optional local tool surface.
    cache = Path.home() / ".codex/models_cache.json"
    model = next(m.copy() for m in read(cache)["models"] if m["slug"] == MODEL)
    for key in ("multi_agent_version", "multi_agent_reasoning_effort", "apply_patch_tool_type"):
        model.pop(key, None)
    model.update(experimental_supported_tools=[], shell_type="disabled", supports_search_tool=False,
                 node_repl_disabled=True, tool_mode="classic")
    write_once(CATALOG, wire({"models": [model]}))


def command(work, schema, extra=()):
    cmd = [shutil.which("codex") or "codex", "exec", "--ephemeral", "--ignore-user-config",
           "--ignore-rules", "--sandbox", "read-only", "--skip-git-repo-check",
           "-m", MODEL, "-C", str(work), "--json", "--output-schema", str(schema),
           "-c", 'model_reasoning_effort="medium"', "-c", 'web_search="disabled"',
           "-c", 'approval_policy="never"', "-c", "project_doc_max_bytes=0",
           "-c", "model_catalog_json=" + json.dumps(CATALOG.as_posix())]
    for name in DISABLED:
        cmd.extend(("--disable", name))
    cmd.extend(("--enable", "skip_host_skill_discovery"))
    return [*cmd, *extra, "-"]


def submit(task, instruction, schema, packet, check):
    task.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(task/"task_lock.sqlite3", timeout=0)) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        return submit_locked(task, instruction, schema, packet, check)


def submit_locked(task, instruction, schema, packet, check):
    request = wire({"model": MODEL, "reasoning": "medium", "input": packet,
                    "schema": schema, "instructions": instruction})
    write_once(task / "request.json", request)
    cached = task / "accepted.json"
    if cached.exists():
        record = read(cached)
        if record["request_sha256"] != hash_bytes(request):
            raise ValueError("Cached request mismatch")
        check(record["answer"])
        return record
    prompt = instruction.encode() + b"\n" + wire(packet)
    for attempt in (1, 2):
        folder = task / f"attempt-{attempt}"
        if folder.is_dir():
            if not (folder / "closed.json").exists():
                # The exclusive task lock is automatically released when the former owner exits.
                write_once(folder/"closed.json",wire({"valid":False,"attempt":attempt,
                           "error":"interrupted_unknown_usage_and_duration","elapsed_seconds":None}))
            record = read(folder / "closed.json")
            if record.get("valid"):
                write_once(cached, wire(record))
                return record
            continue
        folder.mkdir()
        start = time.monotonic()
        write_once(folder / "outbound.txt", prompt)
        rec = {"request_sha256": hash_bytes(request), "stdin_sha256": hash_bytes(prompt),
               "attempt": attempt, "started_unix": time.time(), "valid": False}
        try:
            with tempfile.TemporaryDirectory(prefix="a1_codex_") as root:
                work = Path(root) / "empty"
                work.mkdir()
                contract = Path(root) / "schema.json"
                contract.write_bytes(wire(schema))
                session_start = time.monotonic()
                try:
                    proc = subprocess.run(command(work, contract), input=prompt, cwd=work,
                                          timeout=180, capture_output=True)
                finally:
                    rec["session_seconds"] = time.monotonic() - session_start
            write_once(folder / "stdout.jsonl", proc.stdout)
            write_once(folder / "stderr.txt", proc.stderr)
            events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
            items = [event["item"] for event in events if "item" in event]
            rec["usage"] = [e["usage"] for e in events if e.get("usage")]
            rec["sessions"] = [e["thread_id"] for e in events if e.get("thread_id")]
            rec["tool_events"] = [item["type"] for item in items if item["type"] not in ("agent_message","reasoning")]
            if proc.returncode or rec["tool_events"] or b"tools::router" in proc.stderr:
                raise ValueError("CLI error or forbidden tool event")
            messages = [e["item"]["text"] for e in events if e["type"] == "item.completed"
                        and e.get("item", {}).get("type") == "agent_message"]
            if len(messages) != 1 or len(rec["sessions"]) != 1 or len(rec["usage"]) != 1:
                raise ValueError("Incomplete independent session")
            answer = json.loads(messages[0])
            mark = time.monotonic()
            try:
                validate(answer, schema)
                check(answer)
            finally:
                rec["verification_seconds"] = time.monotonic() - mark
            rec.update(answer=answer, valid=True)
        except subprocess.TimeoutExpired as exc:
            write_once(folder/"stdout.jsonl",exc.stdout or b"")
            write_once(folder/"stderr.txt",exc.stderr or b"")
            rec.update(error="timeout")
        except (OSError, ValueError, subprocess.SubprocessError, KeyError, RuntimeError) as exc:
            rec.update(error=type(exc).__name__ + ": " + str(exc)[:600])
        except Exception as exc:
            from jsonschema import ValidationError
            if not isinstance(exc, ValidationError):
                raise
            rec["error"] = "Output contract failed: " + exc.message[:600]
        rec["elapsed_seconds"] = time.monotonic() - start
        write_once(folder / "closed.json", wire(rec))
        if rec["valid"]:
            write_once(cached, wire(rec))
            return rec
    raise RuntimeError(f"Two starts exhausted: {task}")


def grade_packet(source, registry, keys=None):
    questions = [row for row in source["items"] if keys is None or row["item_id"] in keys]
    allowed = {r["id"]: set(r["pages"]) for r in registry}
    pages = {str(n): source["pages"][str(n)] for q in questions for n in allowed[q["item_id"]]}
    items = [{"item_id": q["item_id"], "question": q["question"],
              "physical_pages": sorted(allowed[q["item_id"]])} for q in questions]
    return {"items": items, "pages": pages}


def grade(case):
    source = read(BASE / "issuers" / case / "grading.json")
    registry = read(BASE / "issuers" / case / "items.json")
    allowed = {r["id"]: set(r["pages"]) for r in registry}
    if set(allowed) != {q["item_id"] for q in source["items"]}:
        raise ValueError("Neutral grading population mismatch")

    def score(label, keys=None):
        data = grade_packet(source, registry, keys)
        def check(answer):
            verify(answer, [i["item_id"] for i in data["items"]], data["pages"])
            for row in answer["items"]:
                if row["physical_page"] not in allowed[row["item_id"]] or not row["reason"].strip():
                    raise ValueError("Wrong item-specific page or missing reason")
        return submit(BASE / "blind" / case / label, RULE, GRADE, data, check)

    passes = {}
    failures = []
    for label in ("first", "second"):
        try:
            passes[label] = score(label)
        except RuntimeError as exc:
            if not str(exc).startswith("Two starts exhausted:"):
                raise
            failures.append(label)
    if failures:
        raise RuntimeError("Independent grading incomplete: " + ", ".join(failures))
    first, second = passes["first"], passes["second"]
    a, b = ({r["item_id"]: r for r in pass_["answer"]["items"]} for pass_ in (first, second))
    diffs = {key for key in a if a[key]["grade"] != b[key]["grade"]}
    hard = score("reconcile", diffs) if diffs else None
    resolutions = {r["item_id"]: r for r in hard["answer"]["items"]} if hard else {}
    if len({r["sessions"][0] for r in (first, second, hard) if r}) != 2 + bool(hard):
        raise ValueError("Repeated grader session")
    figures = {g: dict.fromkeys(GRADES, 0) for g in GRADES}
    rows = {}
    for key in a:
        votes = [a[key], b[key]] + ([resolutions[key]] if key in diffs else [])
        recorded = Counter(v["grade"] for v in votes)
        label, n = recorded.most_common(1)[0]
        figures[a[key]["grade"]][b[key]["grade"]] += 1
        rows[key] = {"grade": label if n >= 2 else "판정 유보", "votes": votes,
                     "requires_source_audit": key in diffs or label in GRADES[2:],
                     "reason": "다수 판정" if n >= 2 else "채점 불일치"}
    draft = {"items": rows, "n": len(a), "exact_agreement": len(a)-len(diffs), "cross_table": figures}
    write_once(BASE / "blind" / case / "proposal.json", wire(draft))
    return draft


def seal_grades(case):
    folder = BASE / "blind" / case
    draft = read(folder / "proposal.json")
    required = {k for k,v in draft["items"].items() if v["requires_source_audit"]}
    audit = read(folder / "source_audit.json") if required else {}
    if set(audit) != required:
        raise ValueError("Blind source audit incomplete")
    for key, entry in audit.items():
        if type(entry["supported"]) is not bool or not entry["basis"].strip():
            raise ValueError("Missing source assessment")
        row = draft["items"][key]
        row["adopted_grade"] = row["grade"] if entry["supported"] else "판정 유보"
        row["source_audit"] = entry
    grades = {k:v.get("adopted_grade",v["grade"]) for k,v in draft["items"].items()}
    write_once(folder / "sealed.json", wire({"grades": grades, "reference": draft}))


def timed_review(case, item):
    start = time.perf_counter()
    folder = BASE / "timing" / case / item
    issuer = BASE / "issuers" / case
    try:
        source = read(issuer / "grading.json")
        registry = read(issuer / "items.json")
        pack = grade_packet(source, registry, {item})
        if not pack["items"] or not pack["pages"]:
            raise KeyError(item)
    except (FileNotFoundError, KeyError):
        result = {"item":item,"packet_sha256":None,"valid_review":False,
                  "missing_reason":"neutral_question_or_source_pages_unavailable",
                  "attempts":0,"packet_prep_seconds":None,"observed_attempt_seconds":0,
                  "service_seconds":None,"verification_seconds":None,"whole_seconds":None,
                  "human_seconds":None}
        write_once(folder / "timing.json", wire(result))
        return result
    packet = {"check_question": pack["items"][0]["question"], "original_physical_pages": pack["pages"]}
    digest = hash_bytes(wire(packet))
    if not (folder / "prepared.json").exists():
        write_once(folder / "prepared.json", wire({"packet_sha256":digest,"packet_prep_seconds":time.perf_counter()-start}))
    prepared = read(folder / "prepared.json")
    if prepared["packet_sha256"] != digest:
        raise ValueError("Timing source packet changed after preparation")
    if (folder / "timing.json").exists():
        result = read(folder / "timing.json")
        if result["packet_sha256"] != digest:
            raise ValueError("Cached timing belongs to another question or evidence set")
        return result
    terminal_error = None
    try:
        submit(folder, ROLE, REVIEW, packet, lambda answer: verify_answer(answer, pack["pages"]))
    except RuntimeError as exc:
        # Preserve a missing valid measurement and the time spent on failed starts.
        if not str(exc).startswith("Two starts exhausted:"):
            raise
        terminal_error = "attempts_exhausted"
    starts = [read(path) for path in sorted(folder.glob("attempt-*/closed.json"))]
    known = bool(starts) and all(r["elapsed_seconds"] is not None for r in starts)
    measured = known and terminal_error is None
    prep = prepared["packet_prep_seconds"]
    result = {"item":item,"packet_sha256":digest,"valid_review":terminal_error is None,
              "missing_reason":terminal_error or ("interrupted_duration_unknown" if not known else None),
              "attempts":len(starts),"packet_prep_seconds":prep,
              "observed_attempt_seconds":sum(r["elapsed_seconds"] or 0 for r in starts),
              "service_seconds":sum(r.get("session_seconds",0) for r in starts) if measured else None,
              "verification_seconds":sum(r.get("verification_seconds",0) for r in starts) if measured else None,
              "human_seconds":None,"whole_seconds":prep+sum(r["elapsed_seconds"] for r in starts) if measured else None}
    write_once(folder / "timing.json", wire(result))
    return result
