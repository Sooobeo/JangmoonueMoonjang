"""Small, schema-checked format repairs; never rewrite factual content.

Patches edit dictionary properties only. Lists, their order and membership,
claims, source locators, quantities and decisions cannot be replaced. The caller
still runs the ordinary contract/gateway checks on the returned candidate.
"""
from copy import deepcopy
import re

from jsonschema import Draft202012Validator

from .schemas import obj


class FormatPatchError(RuntimeError):
    pass


_PATH = {"type": "string", "minLength": 2, "maxLength": 600}
_EVIDENCE = {"evidence", "counter_evidence", "resolution_evidence", "treatment_evidence", "ev"}
PATCH_SCHEMA = obj({"operations": {"type": "array", "maxItems": 32, "items": {"anyOf": [
    obj({"op": {"type": "string", "enum": ["ADD_EMPTY"]}, "path": _PATH,
         "empty_kind": {"type": "string", "enum": ["NULL", "ARRAY", "OBJECT"]}}),
    obj({"op": {"type": "string", "enum": ["REMOVE_EXTRA"]}, "path": _PATH}),
    obj({"op": {"type": "string", "enum": ["NORMALIZE_INTEGER"]}, "path": _PATH}),
    obj({"op": {"type": "string", "enum": ["RELINK_CLAIM"]}, "path": _PATH,
         "claim_id": {"type": "string", "minLength": 1, "maxLength": 160}}),
]}}})


def _parts(path):
    if not path.startswith("/") or re.search(r"~(?![01])", path):
        raise FormatPatchError("INVALID_PATCH_POINTER")
    parts = tuple(part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/"))
    if not parts or any(not part for part in parts):
        raise FormatPatchError("INVALID_PATCH_POINTER")
    return parts


def _variants(schema, value):
    """Select object union branches by existing enum/const discriminators.

    The original may violate required/additionalProperties, so full validation
    cannot select a branch. A missing discriminator keeps all possible branches;
    removal is then allowed only for keys absent from every possible branch.
    """
    if "$ref" in schema or "allOf" in schema:
        raise FormatPatchError("UNSUPPORTED_PATCH_TARGET_SCHEMA")
    choices = schema.get("anyOf", schema.get("oneOf"))
    if choices is None:
        return [schema]
    retained = []
    for choice in choices:
        compatible = True
        if isinstance(value, dict):
            for key, rule in choice.get("properties", {}).items():
                if key in value and (("enum" in rule and value[key] not in rule["enum"]) or
                                     ("const" in rule and value[key] != rule["const"])):
                    compatible = False
                    break
        if compatible:
            retained.extend(_variants(choice, value))
    if not retained:
        raise FormatPatchError("PATCH_TARGET_DISCRIMINATOR_INVALID")
    return retained


def _parent(value, schema, parts):
    node, candidates = value, [schema]
    for part in parts[:-1]:
        expanded = [variant for candidate in candidates for variant in _variants(candidate, node)]
        if isinstance(node, dict):
            if part not in node:
                raise FormatPatchError("PATCH_PARENT_MISSING")
            candidates = [s["properties"][part] for s in expanded if part in s.get("properties", {})]
            node = node[part]
        elif isinstance(node, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", part) or int(part) >= len(node):
                raise FormatPatchError("PATCH_ARRAY_INDEX_INVALID")
            candidates = [s["items"] for s in expanded if isinstance(s.get("items"), dict)]
            node = node[int(part)]
        else:
            raise FormatPatchError("PATCH_PARENT_NOT_CONTAINER")
        if not candidates:
            raise FormatPatchError("PATCH_PATH_OUTSIDE_SCHEMA")
    if not isinstance(node, dict):
        raise FormatPatchError("PATCH_CANNOT_EDIT_ARRAY_OR_ROOT")
    candidates = [variant for candidate in candidates for variant in _variants(candidate, node)]
    return node, parts[-1], candidates


def _compact_evidence_path(parts):
    return (len(parts) >= 5 and parts[-5] in {"values", "shares", "coverage"}
            and parts[-3] == "ev" and parts[-1] == "claim")


def defined_claim_ids(value, target_schema=None):
    """Collect existing declarations, excluding all evidence references."""
    found = set()
    def visit(node, schemas=None, in_evidence=False, path=()):
        if isinstance(node, dict):
            expanded = [variant for schema in (schemas or []) for variant in _variants(schema, node)]
            for key, child in node.items():
                child_schemas = [schema["properties"][key] for schema in expanded if key in schema.get("properties", {})]
                if schemas is not None and not child_schemas:
                    continue
                compact_declaration = (key == "c" and len(path) >= 2 and path[-2] in {"values", "derivations"}
                    and any(rule.get("description") == "claim_id" for rule in child_schemas))
                if not in_evidence and (key in {"claim_id", "judgment_id"} or compact_declaration) and isinstance(child, str) and child.strip():
                    found.add(child)
                visit(child, child_schemas if schemas is not None else None, in_evidence or key in _EVIDENCE, (*path, key))
        elif isinstance(node, list):
            child_schemas = [schema["items"] for schema in (schemas or []) if isinstance(schema.get("items"), dict)]
            for index, child in enumerate(node):
                visit(child, child_schemas if schemas is not None else None, in_evidence, (*path, index))
    visit(value, [target_schema] if target_schema is not None else None)
    return found


def validate_format_only(before, after, path=()):
    """Check value invariants after schema/path-authorized patch operations.

    This is an additional invariant check, not a replacement for apply_format_patch
    (which alone authorizes removed/added properties against the target schema).
    """
    if isinstance(before, dict) and isinstance(after, dict):
        for key in before.keys() & after.keys():
            validate_format_only(before[key], after[key], (*path, key))
        for key in after.keys() - before.keys():
            if after[key] is not None and after[key] != [] and after[key] != {}:
                raise FormatPatchError("PATCH_ADDED_CONTENT")
        return
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            raise FormatPatchError("PATCH_CHANGED_LIST")
        for index, (left, right) in enumerate(zip(before, after)):
            validate_format_only(left, right, (*path, index))
        return
    if before == after and type(before) is type(after):
        return
    if path and path[-1] == "claim_id" and any(part in _EVIDENCE for part in path if isinstance(part, str)):
        if isinstance(after, str) and after.strip():
            return
    if _compact_evidence_path(path) and isinstance(after, str) and after.strip():
        return
    if path and path[-1] in {"page", "version"} and isinstance(before, str) and before.isdecimal() and type(after) is int and int(before) == after:
        return
    raise FormatPatchError("PATCH_CHANGED_FACT_OR_DECISION")


def apply_format_patch(original, patch, target_schema, known_claim_ids=()):
    """Apply a bounded patch atomically and return a detached valid candidate.

    ADD_EMPTY: absent schema property only. REMOVE_EXTRA: property forbidden by
    every applicable closed schema only. NORMALIZE_INTEGER: existing decimal
    text page/version -> same integer. RELINK_CLAIM: an evidence claim_id -> an
    already declared claim/judgment ID. No list edits or root replacement exist.
    """
    if list(Draft202012Validator(PATCH_SCHEMA).iter_errors(patch)):
        raise FormatPatchError("INVALID_FORMAT_PATCH")
    candidate = deepcopy(original)
    declared = defined_claim_ids(original, target_schema) | set(known_claim_ids)
    paths = []
    for operation in patch["operations"]:
        parts = _parts(operation["path"])
        if any(parts[:len(prior)] == prior or prior[:len(parts)] == parts for prior in paths):
            raise FormatPatchError("PATCH_DUPLICATE_OR_OVERLAPPING_PATH")
        paths.append(parts)
        parent, key, schemas = _parent(candidate, target_schema, parts)
        rules = [s["properties"][key] for s in schemas if key in s.get("properties", {})]
        op = operation["op"]
        if op == "REMOVE_EXTRA":
            if key not in parent or rules or not all(s.get("additionalProperties") is False for s in schemas):
                raise FormatPatchError("PATCH_CAN_ONLY_REMOVE_EXTRA_PROPERTY")
            del parent[key]
        elif op == "ADD_EMPTY":
            if key in parent or not rules:
                raise FormatPatchError("PATCH_CAN_ONLY_ADD_MISSING_PROPERTY")
            value = {"NULL": None, "ARRAY": [], "OBJECT": {}}[operation["empty_kind"]]
            if not any(Draft202012Validator(rule).is_valid(value) for rule in rules):
                raise FormatPatchError("PATCH_EMPTY_VALUE_NOT_ALLOWED")
            parent[key] = value
        elif op == "NORMALIZE_INTEGER":
            old = parent.get(key)
            if key not in {"page", "version"} or not isinstance(old, str) or not old.isdecimal() or not rules:
                raise FormatPatchError("PATCH_INTEGER_NORMALIZATION_NOT_ALLOWED")
            value = int(old)
            if not any(rule.get("type") == "integer" and Draft202012Validator(rule).is_valid(value) for rule in rules):
                raise FormatPatchError("PATCH_INTEGER_OUTSIDE_SCHEMA")
            parent[key] = value
        else:
            evidence_shape = {"doc_id", "chunk_id", "page", "claim_id", "locator"}.issubset(parent)
            full_evidence = key == "claim_id" and any(part in _EVIDENCE for part in parts[:-1]) and evidence_shape
            compact_shape = {"chunk", "claim", "at"}
            compact_evidence = (_compact_evidence_path(parts) and compact_shape.issubset(parent)
                and any(set(s.get("properties", {})) == compact_shape for s in schemas))
            if not rules or not (full_evidence or compact_evidence):
                raise FormatPatchError("PATCH_CLAIM_LINK_OUTSIDE_EVIDENCE")
            if operation["claim_id"] not in declared:
                raise FormatPatchError("PATCH_UNKNOWN_CLAIM_ID")
            parent[key] = operation["claim_id"]
    validate_format_only(original, candidate)
    errors = list(Draft202012Validator(target_schema).iter_errors(candidate))
    if errors:
        details = ";".join("/".join(map(str, error.absolute_path)) + ":" + error.validator for error in errors[:5])
        raise FormatPatchError("PATCH_TARGET_SCHEMA_INVALID:" + details)
    return candidate
