"""Create once, then verify the pre-A0 evidence inventory without reading secrets.

Run from any working directory:
    python reports/a0_implementation/verify_preservation.py --create
    python reports/a0_implementation/verify_preservation.py --output ...json
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
REPOSITORY = PROJECT.parent
MANIFEST = HERE / "preservation_manifest.json"
SUPPLEMENT = HERE / "preservation_supplement_phase1.json"
IMMUTABLE_DIRECTORIES = ("data", "runs", "grading_exports", "reports")
SOURCE_DIRECTORIES = ("ipo_eval", "config", "prompts", "scripts", "tests")
SOURCE_FILES = ("pyproject.toml", "README.md", ".gitignore")
SKIP_DIRECTORIES = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".venv", "node_modules"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def permitted(path: Path) -> bool:
    if path.is_symlink() or any(part in SKIP_DIRECTORIES for part in path.parts):
        return False
    if path.name.startswith(".env") or path.suffix.lower() in {".key", ".pem", ".pfx", ".p12"}:
        return False
    return not path.is_relative_to(HERE)


def git(*args: str) -> str:
    return subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=REPOSITORY,
                          check=True, capture_output=True, encoding="utf-8").stdout.strip()


def create() -> dict:
    if MANIFEST.exists() or (HERE / "baseline_source").exists():
        raise SystemExit("Refusing to overwrite the existing pre-implementation baseline.")
    paths: dict[Path, str] = {}
    for directory in IMMUTABLE_DIRECTORIES:
        for path in (PROJECT / directory).rglob("*"):
            if path.is_file() and permitted(path):
                paths[path] = "immutable_evidence"
    for directory in SOURCE_DIRECTORIES:
        for path in (PROJECT / directory).rglob("*"):
            if path.is_file() and permitted(path):
                paths[path] = "versioned_source"
    for filename in SOURCE_FILES:
        path = PROJECT / filename
        if path.is_file() and permitted(path):
            paths[path] = "versioned_source"
    for path in (REPOSITORY / "whole plan").rglob("*"):
        if path.is_file() and permitted(path):
            paths[path] = "versioned_design"
    entries = []
    for path, category in sorted(paths.items(), key=lambda item: str(item[0])):
        entry = {"path": path.relative_to(REPOSITORY).as_posix(), "category": category,
                 "bytes": path.stat().st_size, "sha256": sha256(path)}
        if category in {"versioned_source", "versioned_design"}:
            destination = HERE / "baseline_source" / path.relative_to(REPOSITORY)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            if sha256(destination) != entry["sha256"]:
                raise RuntimeError(f"Snapshot copy mismatch: {path.name}")
            entry["snapshot"] = destination.relative_to(HERE).as_posix()
        entries.append(entry)
    manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "client_date": "2026-11-13", "client_timezone": "Asia/Seoul",
        "phase": "D0", "git_head": git("rev-parse", "HEAD"),
        "git_status_at_capture": git("status", "--short"),
        "policy": {
            "immutable_evidence": "Every existing data/run/grading/report file must retain its original bytes.",
            "versioned_source": "Working source may change; its copied pre-change snapshot must remain identical.",
            "versioned_design": "Design documents may be updated with evidence; pre-change copies are retained.",
            "excluded": ["reports/a0_implementation (this new artifact directory)", "cache directories", ".env*", ".key/.pem/.pfx/.p12", "symlinks"],
            "new_files": "New run, report, source and case files are allowed and do not replace baseline evidence."
        },
        "counts_by_category": dict(Counter(entry["category"] for entry in entries)),
        "entries": entries,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = list(manifest["entries"])
    supplements = []
    if SUPPLEMENT.exists():
        supplement = json.loads(SUPPLEMENT.read_text(encoding="utf-8"))
        entries.extend(supplement["entries"])
        supplements.append({"path": SUPPLEMENT.name, "sha256": sha256(SUPPLEMENT),
                            "entry_count": len(supplement["entries"])})
    violations = []
    changes = []
    if not SUPPLEMENT.exists() and (REPOSITORY / "phase1").exists():
        violations.append({"path": SUPPLEMENT.name, "reason": "required_phase1_supplement_missing"})
    for entry in entries:
        path = (REPOSITORY / entry["path"]).resolve()
        if not path.is_relative_to(REPOSITORY):
            violations.append({"path": entry["path"], "reason": "manifest_path_outside_repository"})
            continue
        exists = path.is_file()
        digest = sha256(path) if exists else None
        if digest != entry["sha256"]:
            change = {"path": entry["path"], "before": entry["sha256"], "after": digest,
                      "reason": "changed" if exists else "missing"}
            if entry["category"] == "immutable_evidence":
                violations.append(change)
            else:
                changes.append(change)
        if "snapshot" in entry:
            snapshot = (HERE / entry["snapshot"]).resolve()
            if not snapshot.is_relative_to(HERE / "baseline_source"):
                violations.append({"path": entry["path"], "reason": "snapshot_path_outside_baseline"})
            elif not snapshot.is_file() or sha256(snapshot) != entry["sha256"]:
                violations.append({"path": entry["path"], "reason": "baseline_snapshot_changed_or_missing"})
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": sha256(MANIFEST), "git_head_at_capture": manifest["git_head"],
        "total_entries": len(entries), "supplements": supplements,
        "counts_by_category": dict(Counter(entry["category"] for entry in entries)),
        "passed": not violations, "violations": violations,
        "versioned_working_files_changed": changes,
        "new_files_policy": "New files are outside the frozen baseline and allowed."
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.create:
        create()
    report = verify()
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if arguments.output:
        destination = arguments.output.resolve()
        if not destination.is_relative_to(HERE) or destination == MANIFEST or destination.is_relative_to(HERE / "baseline_source"):
            parser.error("Verification output must be a new report within a0_implementation, outside the frozen baseline.")
        if destination.exists():
            parser.error("Refusing to overwrite an existing verification report; choose a new filename.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    print(content)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
