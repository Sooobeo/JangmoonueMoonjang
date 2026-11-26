"""Prepare A0 sessions for the 3-form A1 pilot or 4-form calibration. Default: free preflight.

python -m scripts.prepare_a1_a0 --manifest operator.json --output prepared

Operator JSON fields: case_id, issuer_name, cutoff_at, seed, forms, evidence.
forms has original/canary/control, or original/canary_1/canary_2/control, each
with path and sha256. The two calibration canaries represent different target
candidates of one frozen subtype. Optional target_id and subtype fields are
checked as a pair across the two canaries when supplied. Common evidence
entries have path, sha256, source_url and available_at. Dates are KST dates;
times require ISO offsets. A same-day source of uncertain order can carry
precedence_evidence with path and sha256 for the reviewed proof of precedence.
Paths are relative to the manifest. Operator names, paths and provenance links
are kept out of the model corpus. The operator reviews the PDF text and layout
for clues before pinning the PDFs.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from ipo_eval.corpus import Corpus
from ipo_eval.runner_v2 import execute_v2

ROOT = Path(__file__).resolve().parents[1]
CASE = "PILOT-01"
PUBLIC = Path("data/cases") / CASE / "public"
ROLES = ("original", "canary", "control")
CALIBRATION_ROLES = ("original", "canary_1", "canary_2", "control")
KST = timezone(timedelta(hours=9))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    part = path.with_suffix(".tmp")
    part.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    part.replace(path)


def jsonl(path, values):
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in values), encoding="utf-8")


def read_pinned(base, spec):
    path = base / spec["path"]
    data = path.read_bytes()
    if sha(data) != spec["sha256"]:
        raise ValueError(f"Source hash mismatch: {path.name}")
    return data


def parse_time(value):
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        start = datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=KST)
        return start, start + timedelta(days=1)
    match = re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(?:\.(\d{1,6}))?)?(?:[+-]\d{2}:\d{2}|Z)", value)
    if not match:
        raise ValueError("Timestamps need an explicit timezone and precision.")
    instant = datetime.fromisoformat(value)
    instant = instant.astimezone(KST)
    precision = timedelta(minutes=1) if not match[1] else timedelta(seconds=1)
    if match[2]:
        precision = timedelta(microseconds=10 ** (6 - len(match[2])))
    return instant, instant + precision


def confirm_time(spec, cutoff, base):
    source_start, source_end = parse_time(spec["available_at"])
    cutoff_start, cutoff_end = parse_time(cutoff)
    if source_end <= cutoff_start:
        return
    if source_start >= cutoff_end:
        raise ValueError("Evidence was published after the filing.")
    if not spec.get("precedence_evidence"):
        raise ValueError("Same-day evidence needs proof that it was already public.")
    read_pinned(base, spec["precedence_evidence"])


def code_sources():
    # Existing A0 uses only the shared modules, with no A1 ranking or blind-B dependencies.
    return [path for path in sorted((ROOT / "ipo_eval").glob("*.py"))
            if not path.stem.startswith("a1_") and path.stem != "blind_reviewer"]


def settings():
    paths = [ROOT / "config/A0.json", ROOT / "data/methods/IPO_PER_B_v0.2.md",
             *(ROOT / "prompts" / name for name in ("common.md", "v2_contract.md", "A0.md")), *code_sources()]
    return {path.relative_to(ROOT).as_posix(): sha(path.read_bytes()) for path in paths}


def snapshot(work):
    return {p.relative_to(work).as_posix(): sha(p.read_bytes()) for d in ("ipo_eval", "config", "prompts", "data")
            for p in sorted((work / d).rglob("*")) if p.is_file()}


def add_document(public, number, blob, available, title):
    did = f"DOC-{number:02}"
    (public / "raw" / f"{did}.pdf").write_bytes(blob)
    with fitz.open(stream=blob, filetype="pdf") as pdf:
        if not pdf.is_pdf or pdf.needs_pass or len(pdf) == 0:
            raise ValueError(f"Unreadable PDF for {did}")
        texts = [page.get_text(sort=True) for page in pdf]
    if not any(text.strip() for text in texts):
        raise ValueError(f"{did} has no extractable text for A0.")
    meta = {"case_id": CASE, "doc_id": did, "source_url": f"urn:ipo:source:{did}",
            "available_at": available, "cutoff_status": "BEFORE"}
    document = {**meta, "title": title, "pages": len(texts), "sha256": sha(blob), "version_note": "검토 자료"}
    chunks = []
    for page, text in enumerate(texts, 1):
        if re.search(r"\[(?:(?:CANARY|카나리)(?:[ _-]?[12])?|CONTROL|정상\s*대조본)\]", text, re.IGNORECASE):
            raise ValueError("Remove explicit test labels from PDF text before freezing.")
        footer = re.search(r"Page\s+(\d+)\s*$", text)
        chunks.append({**meta, "chunk_id": f"{did}-p{page:04}", "page": page, "text": text,
                       "printed_page": int(footer[1]) if footer else None, "section_state": "CURRENT"})
    return document, chunks


def make_workspace(work, manifest, docs, config_hashes):
    public = work / PUBLIC
    (public / "raw").mkdir(parents=True)
    for rel in config_hashes:
        dest = public / "manual.md" if rel.startswith("data/methods/") else work / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dest)
        if sha(dest.read_bytes()) != config_hashes[rel]:
            raise ValueError("A0 settings changed during preparation.")
    dump(work / "config/cases.json", {"version": "A1-pilot", "cases": [
        {"case_id": CASE, "public_directory": PUBLIC.as_posix()}]})
    documents, chunks = [], []
    for number, (blob, available) in enumerate(docs, 1):
        title = "증권신고서(지분증권)" if number == 1 else "후보 기업 공개자료"
        document, pages = add_document(public, number, blob, available, title)
        documents.append(document)
        chunks.extend(pages)
    jsonl(public / "documents.jsonl", documents)
    jsonl(public / "chunks.jsonl", chunks)
    jsonl(public / "case_manifest.jsonl", [{"case_id": CASE, "issuer_name": manifest["issuer_name"],
          "cutoff_at": manifest["cutoff_at"], "allowed_doc_ids": [d["doc_id"] for d in documents]}])
    Corpus(public, CASE).verify()
    return snapshot(work)


def form_roles(forms):
    if set(forms) == set(ROLES):
        return ROLES
    if set(forms) != set(CALIBRATION_ROLES):
        raise ValueError("Expected original, canary, control or original, canary_1, canary_2, control.")
    pair = [forms["canary_1"], forms["canary_2"]]
    for field in ("target_id", "subtype"):
        if any(field in doc for doc in pair):
            values = [doc.get(field) for doc in pair]
            if not all(isinstance(v, str) and v.strip() for v in values):
                raise ValueError(f"Both calibration canaries must specify {field} when supplied.")
            equal = values[0].strip() == values[1].strip()
            if (field == "target_id" and equal) or (field == "subtype" and not equal):
                raise ValueError("Calibration needs distinct target IDs within the same subtype.")
    return CALIBRATION_ROLES


def prepare(manifest_path, output):
    raw = manifest_path.read_bytes()
    spec = json.loads(raw)
    forms = spec["forms"]
    roles = form_roles(forms)
    if type(spec["seed"]) is not int:
        raise ValueError("Freeze an integer order seed.")
    if not spec["case_id"].strip() or not spec["issuer_name"].strip() or not spec["evidence"]:
        raise ValueError("Issuer, case ID and common candidate evidence are required.")
    parse_time(spec["cutoff_at"])
    pinned_settings = settings()
    if output.exists():
        plan_bytes = (output / "plan.json").read_bytes()
        if sha(plan_bytes) != (output / "plan.sha256").read_text().strip():
            raise ValueError("Prepared order or input hash ledger has changed.")
        prior = json.loads(plan_bytes)
        if (prior["manifest_sha256"] != sha(raw) or (output / "operator_manifest.json").read_bytes() != raw
                or prior["a0_settings"] != pinned_settings):
            raise ValueError("Existing plan differs from the manifest or active A0 settings.")
        for entry in prior["order"]:
            if snapshot(output / entry["workspace"]) != entry["input_hashes"]:
                raise ValueError("Prepared workspace has changed.")
        return prior
    shared = []
    for item in spec["evidence"]:
        if not item["source_url"].strip():
            raise ValueError("Record the public provenance of each candidate source.")
        confirm_time(item, spec["cutoff_at"], manifest_path.parent)
        shared.append((read_pinned(manifest_path.parent, item), item["available_at"]))
    if len({(manifest_path.parent / forms[r]["path"]).resolve() for r in roles}) != len(roles):
        raise ValueError("The forms must use distinct PDF paths.")
    if len({forms[r]["sha256"] for r in roles}) != len(roles):
        raise ValueError("The forms must have distinct PDF snapshots.")
    version = "A1-A0-pilot-1" if roles == ROLES else "A1-A0-calibration-1"
    order = sorted(roles, key=lambda r: sha(f"{spec['seed']}:{r}".encode()))
    plan = {"version": version, "case_id": spec["case_id"], "manifest_sha256": sha(raw),
            "seed": spec["seed"], "a0_settings": pinned_settings, "order": []}
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as staging:
        batch = Path(staging) / "batch"
        batch.mkdir()
        for slot, role in enumerate(order, 1):
            name = f"session-{slot:02}"
            doc = read_pinned(manifest_path.parent, spec["forms"][role])
            hashes = make_workspace(batch / name, spec, [(doc, spec["cutoff_at"]), *shared], pinned_settings)
            plan["order"].append({"position": slot, "role": role, "workspace": name, "input_hashes": hashes})
        chunk_key = (PUBLIC / "chunks.jsonl").as_posix()
        if len({entry["input_hashes"][chunk_key] for entry in plan["order"]}) != len(roles):
            raise ValueError("Different PDF files yielded identical A0 source text.")
        dump(batch / "plan.json", plan)
        (batch / "plan.sha256").write_text(sha((batch / "plan.json").read_bytes()) + "\n", encoding="ascii")
        (batch / "operator_manifest.json").write_bytes(raw)
        batch.rename(output)
    return plan


@contextmanager
def batch_lock(output):
    """One executor per output; the OS releases this lock on process exit."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with (output.parent / f".{output.name}.lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def prior_runs(work, live, hashes):
    rows = []
    for directory in sorted((work / "runs").glob("*")):
        file = directory / "summary.json"
        if not file.exists():
            raise ValueError(f"Interrupted run needs reconciliation before another request: {directory.name}")
        data = json.loads(file.read_bytes())
        if data["mode"] == ("LIVE" if live else "PREFLIGHT"):
            if data["run_id"] != directory.name or data["case_id"] != CASE or data["condition"] != "A0":
                raise ValueError("Stored run summary does not belong to this A0 workspace.")
            if (directory / "input_hashes.json").exists():
                if json.loads((directory / "input_hashes.json").read_bytes()) != hashes:
                    raise ValueError("Stored A0 run and frozen input hashes differ.")
            elif data["execution_status"] in {"SUBMITTED", "PREFLIGHT_COMPLETE"}:
                raise ValueError("Stored run lacks the original input hash record.")
            if data["execution_status"] == "SUBMITTED" and not (directory / "review.json").is_file():
                raise ValueError("Stored submission lacks the review.")
            rows.append(data)
    return rows


def retryable(summary):
    reason = summary.get("failure_reason", "")
    families = ("API_ERROR:InternalServerError", "API_ERROR:APITimeoutError", "API_ERROR:APIConnectionError",
                "MODEL_INCOMPLETE:", "INVALID_", "NO_VALID_SUBMISSION", "FORMAT_REPAIR_EXHAUSTED",
                "REPAIR_", "DUPLICATE_OR_MISSING_CALL_ID", "MULTIPLE_TOOL_CALLS_", "UNKNOWN_TOOL")
    return summary["execution_status"] == "FAILED" and reason.startswith(families)


def run_batch(manifest, output, live=False, execute=execute_v2):
    with batch_lock(output):
        plan = prepare(manifest, output)
        mode = "live" if live else "preflight"
        ledger = {"manifest_sha256": plan["manifest_sha256"], "mode": mode, "sessions": []}
        expected = "SUBMITTED" if live else "PREFLIGHT_COMPLETE"
        for entry in plan["order"]:
            work = output / entry["workspace"]
            rows = prior_runs(work, live, entry["input_hashes"])
            attempts = [r for r in rows if r["execution_status"] != "NOT_STARTED_MISSING_API_KEY"]
            while not attempts or (live and len(attempts) == 1 and retryable(attempts[0])):
                if snapshot(work) != entry["input_hashes"] or settings() != plan["a0_settings"]:
                    raise ValueError("Inputs changed before execution.")
                _, result = execute(live=live, root=work, case_id=CASE, condition="A0",
                                    key_provider=None if live else lambda: None)
                rows.append(result)
                if result["execution_status"] == "NOT_STARTED_MISSING_API_KEY":
                    break
                attempts.append(result)
            chosen = next((r["run_id"] for r in rows if r["execution_status"] == expected), None)
            ledger["sessions"].append({"role": entry["role"], "position": entry["position"],
                "selected_run": chosen, "attempts": [{"run_id": r["run_id"], "status": r["execution_status"],
                    "model_calls": r["model_calls"], "cost_usd": r.get("estimated_cost_usd_standard_uncached"),
                    "transport_retries": r.get("transient_retries"), "usage_unknown": r.get("usage_unknown"),
                    "reason": r.get("failure_reason")} for r in rows]})
            dump(output / f"{mode}.json", ledger)
            if rows[-1]["execution_status"] == "NOT_STARTED_MISSING_API_KEY":
                break
        return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New batch directory, or same batch to resume")
    parser.add_argument("--live", action="store_true", help="Make actual A0 submissions; default is free preflight")
    args = parser.parse_args()
    result = run_batch(args.manifest.resolve(), args.output.resolve(), args.live)
    complete = sum(s["selected_run"] is not None for s in result["sessions"])
    expected = len(json.loads((args.output / "plan.json").read_bytes())["order"])
    print(f"{result['mode']}: {complete}/{expected}; {args.output}")
    return int(complete != expected)


if __name__ == "__main__":
    raise SystemExit(main())
