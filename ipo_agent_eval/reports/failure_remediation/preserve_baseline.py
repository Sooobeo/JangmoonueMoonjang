"""Capture and verify the completed A0 work before failure remediation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
WORKSPACE = PROJECT.parent
MANIFEST = HERE / "baseline_manifest.json"
EXCLUDED = {".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"}
SECRET_SUFFIXES = {".key", ".pem", ".pfx", ".p12"}


def permitted(path):
    return not path.is_symlink() and not path.name.lower().startswith(".env") and path.suffix.lower() not in SECRET_SUFFIXES and not any(part in EXCLUDED for part in path.parts) and not path.is_relative_to(HERE)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def capture():
    if MANIFEST.exists():
        raise SystemExit("Baseline already captured; no overwrite")
    paths = {}
    for name in ("ipo_eval", "config", "prompts", "scripts", "tests"):
        paths.update({p: "versioned_source" for p in (PROJECT / name).rglob("*") if p.is_file() and permitted(p)})
    for name in ("README.md", "pyproject.toml", ".gitignore"):
        path = PROJECT / name
        if path.exists() and permitted(path):
            paths[path] = "versioned_source"
    design = WORKSPACE / "whole plan"
    paths.update({p: "versioned_design" for p in design.rglob("*") if p.is_file() and permitted(p) and p.suffix.lower() in {".md", ".html", ".json", ".txt"}})
    for directory in [PROJECT / name for name in ("data", "runs", "grading_exports", "reports")] + [WORKSPACE / "phase1"]:
        paths.update({p: "immutable_evidence" for p in directory.rglob("*") if p.is_file() and permitted(p)})
    entries = []
    for path, category in sorted(paths.items()):
        relative = path.relative_to(WORKSPACE)
        row = {"path": relative.as_posix(), "category": category, "bytes": path.stat().st_size, "sha256": sha(path)}
        if category.startswith("versioned_"):
            snapshot = HERE / "baseline_source" / relative
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, snapshot)
            assert sha(snapshot) == row["sha256"]
            row["snapshot"] = snapshot.relative_to(HERE).as_posix()
        entries.append(row)
    def git(*args):
        return subprocess.check_output(["git", "-c", "core.quotepath=false", *args], cwd=WORKSPACE, encoding="utf-8", errors="strict").strip()
    report = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "workspace": str(WORKSPACE),
              "git_head": git("rev-parse", "HEAD"), "git_status": git("status", "--porcelain=v1", "--untracked-files=all"),
              "exclusions": [".env* and key/certificate suffixes; contents never read", "symlinks", "cache directories", "this remediation report directory"],
              "entries": entries, "entry_count": len(entries),
              "policy": "Existing evidence and prior reports are immutable. Versioned working source may change, but its baseline snapshot must remain exact. New remediation files are outside this baseline."}
    MANIFEST.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return verify()


def verify():
    report = json.loads(MANIFEST.read_text(encoding="utf-8"))
    violations, changed = [], []
    for row in report["entries"]:
        original = WORKSPACE / row["path"]
        if not original.is_file() or sha(original) != row["sha256"]:
            (violations if row["category"] == "immutable_evidence" else changed).append(row["path"])
        if "snapshot" in row:
            snapshot = HERE / row["snapshot"]
            if not snapshot.is_file() or sha(snapshot) != row["sha256"]:
                violations.append("snapshot:" + row["snapshot"])
    return {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "passed": not violations,
            "manifest_sha256": sha(MANIFEST), "entry_count": report["entry_count"],
            "snapshot_count": sum("snapshot" in row for row in report["entries"]),
            "immutable_count": sum(row["category"] == "immutable_evidence" for row in report["entries"]),
            "violations": violations, "versioned_source_changes": changed}


if __name__ == "__main__":
    result = capture() if "--capture" in sys.argv else verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "--capture" in sys.argv:
        (HERE / "baseline_initial_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result["passed"] else 1)
