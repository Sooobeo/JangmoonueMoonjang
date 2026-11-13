"""Freeze completed diagnostic and stopped-remediation raw attempt evidence."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = HERE / "intermediate_attempts_manifest.json"
LABELS = ("DIAG_v040", "DIAG_v041", "FIX_v041")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture():
    if MANIFEST.exists():
        raise SystemExit("Intermediate attempts already captured; never overwrite.")
    paths, batches = set(), []
    for label in LABELS:
        plan_path, result_path = HERE / (label + "_plan.json"), HERE / (label + "_runs.json")
        plan, results = read(plan_path), read(result_path)
        paths.update((plan_path, result_path))
        expected = {(x["case_id"], x["condition"], x["repeat"]) for x in plan["planned_runs"]}
        observed = {(x["case_id"], x["condition"], x["repeat"]) for x in results["runs"]}
        assert expected == observed and len(expected) == len(results["runs"])
        started = []
        for row in results["runs"]:
            if not row.get("directory"):
                assert row["summary"]["execution_status"].startswith("NOT_STARTED_")
                continue
            directory = Path(row["directory"]).resolve()
            assert directory.is_relative_to((ROOT / "runs").resolve())
            assert row["summary"]["execution_status"] in {"SUBMITTED", "FAILED"}
            assert row["summary"] == read(directory / "summary.json")
            started.append(directory.name)
            paths.update(path for path in directory.rglob("*") if path.is_file())
        frozen = ROOT / plan["source_snapshot"]
        for name, digest in plan["source_hashes"].items():
            path = frozen / name
            assert sha(path) == digest
            paths.add(path)
        batches.append({"label": label, "registry_complete": results["complete"],
            "planned": len(expected), "started_runs": started,
            "dispositions": dict(Counter(row["summary"]["execution_status"] for row in results["runs"]))})
    assert sum(len(batch["started_runs"]) for batch in batches) == 13
    entries = []
    for path in sorted(paths):
        assert not path.is_symlink() and not path.name.lower().startswith(".env")
        assert path.suffix.lower() not in {".key", ".pem", ".pfx", ".p12"}
        entries.append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)})
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "batches": batches,
        "policy": "Immutable prior attempts. A stopped registry remains complete=false with explicit unstarted rows. No diagnostic or stopped result is included in the final paired denominator. Derived analyses/reviews are excluded from this raw-evidence lock.",
        "entry_count": len(entries), "entries": entries}
    MANIFEST.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return verify()


def verify():
    manifest = read(MANIFEST)
    errors = [row["path"] for row in manifest["entries"]
              if not (ROOT / row["path"]).is_file() or sha(ROOT / row["path"]) != row["sha256"]]
    return {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "passed": not errors,
            "manifest_sha256": sha(MANIFEST), "entry_count": len(manifest["entries"]), "violations": errors}


if __name__ == "__main__":
    result = capture() if "--capture" in sys.argv else verify()
    if "--capture" in sys.argv:
        (HERE / "intermediate_attempts_initial_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
