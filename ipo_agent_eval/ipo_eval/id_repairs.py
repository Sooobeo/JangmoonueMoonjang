"""Constrain a common format repair to invalid evidence claim-ID references.

This module has no model calls, source access, scoring, or factual corrections.
The caller must run the complete structural validator after applying repairs.
"""

from copy import deepcopy
import re

_INDEX = r"(?:0|[1-9][0-9]*)"
_PATH = re.compile(
    rf"^/(?:judgments/{_INDEX}/(?:facts/{_INDEX}/evidence|evidence|counter_evidence)"
    rf"|(?:requests|escalations)/{_INDEX}/resolution_evidence)/{_INDEX}/claim_id$"
)


def _ids(review, extraction):
    values = [j["judgment_id"] for j in review["judgments"]]
    values += [f["claim_id"] for j in review["judgments"] for f in j["facts"]]
    values += [f["claim_id"] for f in extraction["values"].values()]
    values += [p[key]["claim_id"] for p in extraction["peers"]
               for key in ("per", "market_cap_million_krw", "earnings_million_krw")]
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Defined claim and judgment IDs must be nonempty strings")
    if len(set(values)) != len(values):
        raise ValueError("Duplicate defined IDs cannot be fixed by a reference-only repair")
    return sorted(values)


def build_id_repair_targets(review: dict, extraction: dict) -> list[dict]:
    """Find only bad evidence.claim_id references, in deterministic document order."""
    if not isinstance(review, dict) or not isinstance(extraction, dict):
        raise ValueError("Review and extraction must be objects")
    try:
        known = _ids(review, extraction)
        targets = []

        def add(base, evidence, allowed):
            if not isinstance(evidence, list):
                raise ValueError("Evidence must be a list")
            for index, item in enumerate(evidence):
                if not isinstance(item, dict) or "claim_id" not in item:
                    raise ValueError("Each evidence entry must have claim_id")
                if item["claim_id"] not in allowed:
                    targets.append({"path": f"{base}/{index}/claim_id", "allowed_ids": list(allowed)})

        for index, judgment in enumerate(review["judgments"]):
            for fact_index, fact in enumerate(judgment["facts"]):
                add(f"/judgments/{index}/facts/{fact_index}/evidence", fact["evidence"], [fact["claim_id"]])
            for field in ("evidence", "counter_evidence"):
                add(f"/judgments/{index}/{field}", judgment[field], known)
        for group in ("requests", "escalations"):
            for index, request in enumerate(review[group]):
                add(f"/{group}/{index}/resolution_evidence", request["resolution_evidence"], known)
        return targets
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Malformed review or extraction for reference repair") from exc


def _location(review, path):
    if not isinstance(path, str) or not _PATH.fullmatch(path):
        raise ValueError("Only evidence claim_id paths may be repaired")
    parts = path.split("/")[1:]
    current = review
    try:
        for part in parts[:-1]:
            if isinstance(current, list):
                current = current[int(part)]
            elif isinstance(current, dict):
                current = current[part]
            else:
                raise ValueError("Repair path does not address an existing evidence entry")
        if not isinstance(current, dict) or "claim_id" not in current:
            raise ValueError("Repair path does not address an existing claim_id")
        return current
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Repair path does not exist") from exc


def apply_id_repairs(review: dict, targets: list[dict], repairs: list[dict]) -> dict:
    """Apply a complete, exact set of allowed replacements to a deep copy.

    No JSON Patch operations, partial repairs, new paths, source changes, or
    other content edits are accepted. Invalid repair data leaves review intact.
    """
    if not isinstance(review, dict) or not isinstance(targets, list) or not isinstance(repairs, list):
        raise ValueError("Review must be an object; targets and repairs must be lists")
    allowed_by_path = {}
    for target in targets:
        if not isinstance(target, dict) or set(target) != {"path", "allowed_ids"}:
            raise ValueError("Each target must contain exactly path and allowed_ids")
        path, allowed = target["path"], target["allowed_ids"]
        location = _location(review, path)
        if path in allowed_by_path:
            raise ValueError("Duplicate target path")
        if not isinstance(allowed, list) or not allowed or any(not isinstance(i, str) or not i.strip() for i in allowed):
            raise ValueError("Allowed IDs must be a nonempty list of nonempty strings")
        if len(set(allowed)) != len(allowed):
            raise ValueError("Allowed IDs must be unique")
        if location["claim_id"] in allowed:
            raise ValueError("Target is already valid; refusing a stale or unnecessary repair")
        # Parent-fact ownership is an invariant, even if a target was tampered with.
        parts = path.split("/")[1:]
        if parts[0] == "judgments" and len(parts) == 7 and parts[2] == "facts":
            parent_id = review["judgments"][int(parts[1])]["facts"][int(parts[3])]["claim_id"]
            if allowed != [parent_id]:
                raise ValueError("Fact evidence may reference only its parent fact ID")
        allowed_by_path[path] = set(allowed)
    supplied = {}
    for repair in repairs:
        if not isinstance(repair, dict) or set(repair) != {"path", "replacement"}:
            raise ValueError("Each repair must contain exactly path and replacement")
        path, replacement = repair["path"], repair["replacement"]
        if not isinstance(path, str) or path not in allowed_by_path:
            raise ValueError("Repair path is not an approved target")
        if path in supplied:
            raise ValueError("Duplicate repair path")
        if not isinstance(replacement, str) or replacement not in allowed_by_path[path]:
            raise ValueError("Replacement is not an allowed claim ID")
        supplied[path] = replacement
    if set(supplied) != set(allowed_by_path):
        raise ValueError("Every target must be repaired exactly once")
    result = deepcopy(review)
    for path, replacement in supplied.items():
        _location(result, path)["claim_id"] = replacement
    return result
