"""Compact model transport for the unchanged extraction_v2 record contract.

Only key names, record grouping and redundant read-page coordinates change.
No value, context, claim, origin, selection, treatment or reason is inferred.
The caller must still register expanded records through SnapshotStore.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from jsonschema import Draft202012Validator

from .provenance import ContractError
from .schemas import EVIDENCE, arr, obj, S
from .schemas_v2 import EXTRACTION_V2, ID, PAYLOADS, enum


# Ordered fields also determine the order produced by Structured Outputs.
# Nullable bookkeeping fields precede evidence; evidence is always last.
WIRE_LAYOUT = {
    "contexts": ("CONTEXT", {"u": "unit", "p": "period", "t": "as_of",
        "s": "scope", "b": "basis", "src": "source_snapshot_id"}),
    "values": ("VALUE", {"f": "field", "e": "entity_id", "c": "claim_id",
        "v": "value", "x": "context_id", "o": "origin", "m": "missing_reason",
        "d": "derivation_id", "ev": "evidence"}),
    "shares": ("SHARE_COMPONENT", {"f": "fact_id", "k": "kind",
        "t": "denominator_treatment", "r": "treatment_reason",
        "src": "source_snapshot_id", "b": "basis", "ev": "treatment_evidence"}),
    "peers": ("PEER", {"n": "name", "per": "per_fact_id", "cap": "market_cap_fact_id",
        "earn": "earnings_fact_id", "price": "reference_price_fact_id",
        "shares": "reference_shares_fact_id"}),
    "derivations": ("DERIVATION", {"op": "operation", "inputs": "input_fact_ids",
        "out": "output_fact_id", "f": "field", "e": "entity_id",
        "x": "context_id", "c": "claim_id"}),
    "selections": ("SELECTION", {"f": "field", "e": "entity_id",
        "disclosed": "disclosed_fact_id", "selected": "selected_fact_id",
        "status": "disclosure_status", "use": "usability", "why": "selection_reason"}),
    "coverage": ("COVERAGE", {"status": "coverage_status", "why": "reason",
        "src": "source_snapshot_id", "ev": "evidence"}),
}
_EVIDENCE_FIELDS = {"evidence", "treatment_evidence"}
_WIRE_EVIDENCE = obj({"chunk": deepcopy(EVIDENCE["properties"]["chunk_id"]),
                      "claim": deepcopy(EVIDENCE["properties"]["claim_id"]),
                      "at": deepcopy(EVIDENCE["properties"]["locator"])})


def _wire_schema():
    properties = {}
    for group, (kind, aliases) in WIRE_LAYOUT.items():
        fields = {"id": deepcopy(ID)}
        for short, full in aliases.items():
            fields[short] = (arr(deepcopy(_WIRE_EVIDENCE)) if full in _EVIDENCE_FIELDS
                             else deepcopy(PAYLOADS[kind]["properties"][full]))
            fields[short]["description"] = full
        properties[group] = arr(obj(fields))
    properties.update(notes=arr(S), limits=arr(S))
    return obj(properties)


EXTRACTION_WIRE = _wire_schema()
REGISTER_WIRE_BATCH = obj({"operation": enum("REGISTER_BATCH"), "base_snapshot_id": deepcopy(ID),
                           "batch": deepcopy(EXTRACTION_WIRE)})

WIRE_INSTRUCTIONS = "\n".join([
    "compact_v1은 extraction_v2와 같은 정보의 전송 형식이다. 들여쓰기·공백 반복 없이 간결한 JSON으로 출력한다.",
    "각 배열의 id는 record_id다. 아래 키만 줄였으며 경제 필드명과 enum 값은 원래 이름을 사용한다.",
    *[f"{group}={kind}: " + ", ".join(f"{short}={full}" for short, full in aliases.items())
      for group, (kind, aliases) in WIRE_LAYOUT.items()],
    "ev의 각 항목은 {chunk: 실제 읽은 chunk_id, claim: claim_id, at: locator}다. doc_id/page는 그 chunk의 실제 열람 좌표로만 복원된다.",
    "notes=document_version_notes, limits=extraction_limits. 모든 배열과 각 항목의 필수 키를 출력한다. 해당 종류가 없으면 빈 배열이다.",
    "CONTEXT를 공유하고 id는 짧고 고유하게 정한다. claim과 모든 연결 ID는 일관되게 명시한다. entity_id null은 발행사이며 비교기업은 PEER의 id를 쓴다.",
    "금액·기간·범위·기준·포함/제외·선택 이유를 생략하거나 추측하지 않는다. 공시 0, UNAVAILABLE, NOT_APPLICABLE을 구별한다.",
    "DERIVED는 허용식과 원입력을 명시한다. 변환기는 계산하거나 누락 사실을 채우지 않는다. SELECTION/COVERAGE도 원문에 근거해 명시한다.",
])


def _validate(value, schema, label):
    error = next(Draft202012Validator(schema).iter_errors(value), None)
    if error is not None:
        path = ".".join(map(str, error.absolute_path)) or "<root>"
        raise ContractError(f"{label} schema at {path}: {error.message}", "INVALID_WIRE_CONTRACT")


def _read_location(chunk_id, read_chunks):
    if not isinstance(read_chunks, Mapping):
        raise ContractError("read_chunks must be the caller's actually read-page map", "UNREAD_EVIDENCE")
    chunk = read_chunks.get(chunk_id)
    if not isinstance(chunk, Mapping):
        raise ContractError("Evidence references an unread chunk: " + chunk_id, "UNREAD_EVIDENCE")
    doc_id, page = chunk.get("doc_id"), chunk.get("page")
    if (not isinstance(doc_id, str) or not doc_id.strip() or type(page) is not int
            or page < 1 or chunk.get("chunk_id", chunk_id) != chunk_id):
        raise ContractError("Actually read chunk has invalid coordinates: " + chunk_id, "UNREAD_EVIDENCE")
    return doc_id, page


def _expand_evidence(items, read_chunks):
    result = []
    for item in items:
        doc_id, page = _read_location(item["chunk"], read_chunks)
        result.append({"doc_id": doc_id, "chunk_id": item["chunk"], "page": page,
                       "claim_id": item["claim"], "locator": item["at"]})
    return result


def _compress_evidence(items, read_chunks):
    result = []
    for item in items:
        location = _read_location(item["chunk_id"], read_chunks)
        if type(item["page"]) is not int or (item["doc_id"], item["page"]) != location:
            raise ContractError("Evidence coordinates differ from the actually read chunk", "UNREAD_EVIDENCE")
        result.append({"chunk": item["chunk_id"], "claim": item["claim_id"], "at": item["locator"]})
    return result


def _unique_record_id(record_id, seen):
    if not record_id.strip() or record_id in seen:
        raise ContractError("Wire record IDs must be nonempty and unique within a batch", "INVALID_WIRE_CONTRACT")
    seen.add(record_id)


def expand_wire_extraction(wire, read_chunks):
    """Return v2 records without inference or mutation, or fail closed.

    Records are grouped in WIRE_LAYOUT order. Within-group order, all payload
    values, evidence order/duplicates and notes are preserved. Record ordering
    is not part of the immutable snapshot hash; record IDs and payloads are.
    Semantic validity remains the existing registration contract's decision.
    """
    _validate(wire, EXTRACTION_WIRE, "compact_v1")
    records, seen = [], set()
    for group, (kind, aliases) in WIRE_LAYOUT.items():
        for item in wire[group]:
            _unique_record_id(item["id"], seen)
            payload = {full: (_expand_evidence(item[short], read_chunks) if full in _EVIDENCE_FIELDS
                              else deepcopy(item[short])) for short, full in aliases.items()}
            records.append({"record_id": item["id"], "kind": kind, "payload": payload})
    value = {"records": records, "document_version_notes": deepcopy(wire["notes"]),
             "extraction_limits": deepcopy(wire["limits"])}
    _validate(value, EXTRACTION_V2, "expanded extraction_v2")
    return value


def to_wire_extraction(value, read_chunks):
    """Encode existing v2 data without silently repairing coordinates or IDs."""
    _validate(value, EXTRACTION_V2, "extraction_v2")
    wire = {group: [] for group in WIRE_LAYOUT}
    groups = {kind: (group, aliases) for group, (kind, aliases) in WIRE_LAYOUT.items()}
    seen = set()
    for record in value["records"]:
        _unique_record_id(record["record_id"], seen)
        group, aliases = groups[record["kind"]]
        payload = record["payload"]
        wire[group].append({"id": record["record_id"], **{
            short: (_compress_evidence(payload[full], read_chunks) if full in _EVIDENCE_FIELDS
                    else deepcopy(payload[full])) for short, full in aliases.items()}})
    wire.update(notes=deepcopy(value["document_version_notes"]), limits=deepcopy(value["extraction_limits"]))
    _validate(wire, EXTRACTION_WIRE, "compact_v1")
    return wire
