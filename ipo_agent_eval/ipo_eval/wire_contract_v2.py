"""Compact context-group transport for the unchanged extraction_v2 contract.

Groups are model-declared, batch-local dictionaries. Expansion copies their
four context fields verbatim; it neither infers equivalence nor certifies it.
Raw wire logs retain group names and unused declarations. Lossless guarantees
cover logical v2 record payloads, not arbitrary wire dictionary naming.
"""
from copy import deepcopy

from .provenance import ContractError
from .schemas import arr, obj
from .schemas_v2 import ID, enum
from .wire_contract import (EXTRACTION_WIRE, WIRE_INSTRUCTIONS, _validate,
                            expand_wire_extraction, to_wire_extraction)


def _schema():
    context = EXTRACTION_WIRE["properties"]["contexts"]["items"]["properties"]
    group = obj({"id": deepcopy(ID), **{key: deepcopy(context[key]) for key in ("t", "s", "b", "src")}})
    grouped_context = obj({"id": deepcopy(ID), "u": deepcopy(context["u"]),
                           "p": deepcopy(context["p"]),
                           "g": {**deepcopy(ID), "description": "batch-local group_id"}})
    properties = {"groups": arr(group), "contexts": arr(grouped_context)}
    properties.update({key: deepcopy(value) for key, value in EXTRACTION_WIRE["properties"].items() if key != "contexts"})
    return obj(properties)


EXTRACTION_WIRE_V2 = _schema()
REGISTER_WIRE_BATCH_V2 = obj({"operation": enum("REGISTER_BATCH"), "base_snapshot_id": deepcopy(ID),
                              "batch": deepcopy(EXTRACTION_WIRE_V2)})

WIRE_INSTRUCTIONS_V2 = "\n".join([
    "compact_v2는 같은 extraction_v2 정보의 전송 형식이다. 같은 비교기준을 모델이 판단해 groups에 한 번 선언하고 contexts가 참조한다.",
    "groups: id=배치 로컬 group_id, t=as_of, s=scope, b=basis, src=source_snapshot_id.",
    "contexts=CONTEXT: id=record_id, u=unit, p=period, g=이 배치 groups의 group_id. g의 t/s/b/src를 원문 그대로 확장한다.",
    "같은 평가 범위·적용 기준·기준일·공시 시점이라고 원문에서 판단한 입력/출력만 같은 g를 참조한다. 실제로 다르거나 비교가능성이 미확인이면 별도 group을 명시한다. 계산 통과를 위해 다른 기준을 합치지 않는다.",
    "unit과 실적기간 period는 각 context에 별도로 유지한다. 그룹 참조는 모델의 선언이며 계산기가 경제적 적합성을 승인한다는 뜻이 아니다.",
    "groups는 이 배치에서만 유효하다. 새 context의 g는 같은 배치에서 선언해야 하며 중복 group id와 없는 g는 거부된다. 이미 등록한 context_id를 쓰는 증분 배치에는 groups=[]/contexts=[]가 가능하다.",
    "사용하지 않는 유효 group은 원본 wire 로그에만 보존되며 논리 CONTEXT 레코드를 만들지 않는다. 그룹 이름 자체도 내부 fact/record ID가 아니다.",
    *[line for line in WIRE_INSTRUCTIONS.splitlines()
      if not line.startswith(("compact_v1", "contexts=CONTEXT"))],
])


def expand_wire_extraction_v2(wire, read_chunks):
    """Copy declared groups into six-field CONTEXT payloads without inference."""
    _validate(wire, EXTRACTION_WIRE_V2, "compact_v2")
    groups = {}
    for group in wire["groups"]:
        identifier = group["id"]
        if not identifier.strip() or identifier in groups:
            raise ContractError("Wire group IDs must be nonempty and unique within a batch", "INVALID_WIRE_CONTRACT")
        groups[identifier] = group
    contexts = []
    for context in wire["contexts"]:
        if context["g"] not in groups:
            raise ContractError("Context references an undefined batch-local group: " + context["g"], "INVALID_WIRE_CONTRACT")
        group = groups[context["g"]]
        contexts.append({"id": context["id"], "u": context["u"], "p": context["p"],
                         **{key: deepcopy(group[key]) for key in ("t", "s", "b", "src")}})
    v1 = {key: deepcopy(value) for key, value in wire.items() if key not in {"groups", "contexts"}}
    v1["contexts"] = contexts
    return expand_wire_extraction(v1, read_chunks)


def to_wire_extraction_v2(value, read_chunks):
    """Deduplicate only exact (as_of, scope, basis, source_snapshot_id) tuples."""
    v1 = to_wire_extraction(value, read_chunks)
    groups, contexts, identities = [], [], {}
    for context in v1["contexts"]:
        key = tuple(context[name] for name in ("t", "s", "b", "src"))
        if key not in identities:
            identifier = "G" + str(len(groups) + 1)
            identities[key] = identifier
            groups.append({"id": identifier, **{name: deepcopy(context[name]) for name in ("t", "s", "b", "src")}})
        contexts.append({"id": context["id"], "u": context["u"], "p": context["p"], "g": identities[key]})
    wire = {"groups": groups, "contexts": contexts,
            **{key: deepcopy(value) for key, value in v1.items() if key != "contexts"}}
    _validate(wire, EXTRACTION_WIRE_V2, "compact_v2")
    return wire
