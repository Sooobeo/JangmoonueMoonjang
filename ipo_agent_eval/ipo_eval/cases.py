"""Select registered public inputs without accepting arbitrary corpus paths."""
import json
import re
from pathlib import Path, PurePosixPath


DEFAULT_CASE_ID = "HDMS-DEV-01"


def _fixed_path(root, relative):
    """Reject links that redirect an approved public location elsewhere."""
    lexical = root.joinpath(*PurePosixPath(relative).parts)
    if lexical.resolve() != lexical:
        raise ValueError("Registered input path is redirected: " + relative)
    return lexical


def resolve_case(root, case_id=DEFAULT_CASE_ID):
    root = Path(root).resolve()
    registry_path = root / "config" / "cases.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = registry["cases"]
    ids = [entry["case_id"] for entry in entries]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate registered case IDs")
    if not isinstance(case_id, str) or not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", case_id):
        raise ValueError("Invalid case ID")
    matches = [entry for entry in entries if entry["case_id"] == case_id]
    if not matches:
        raise ValueError("Case is not registered: " + case_id)
    entry = matches[0]
    expected = "data/public" if case_id == DEFAULT_CASE_ID else f"data/cases/{case_id}/public"
    if entry["public_directory"] != expected:
        raise ValueError("Registered corpus must use its dedicated public directory")
    directory = _fixed_path(root, expected)
    source = entry.get("manual_source")
    if source is not None:
        path = PurePosixPath(source)
        if path.parent != PurePosixPath("data/methods") or path.suffix != ".md":
            raise ValueError("Registered manual must be in data/methods")
        source_path = _fixed_path(root, source)
        if source_path.read_bytes() != (directory / "manual.md").read_bytes():
            raise ValueError("Case manual differs from its registered method version")
    return directory, {**entry, "registry_version": registry["version"]}
