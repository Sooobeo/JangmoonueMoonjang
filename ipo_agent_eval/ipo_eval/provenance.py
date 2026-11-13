"""Atomic, immutable extraction snapshots and deterministic source propagation.

Only supplied, actually read pages are available here. This module never opens
documents, gold files, network resources, or other experiment runs.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import hashlib
import json

from jsonschema import Draft202012Validator

from .schemas_v2 import RECORD, FIELD_UNITS


class ContractError(ValueError):
    def __init__(self, message, code="INVALID_RECORD"):
        super().__init__(message)
        self.code = code


def decimal_text(value):
    text = format(value, "f")
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return "0" if text in ("-0", "+0") else text


def unique_evidence(evidence):
    seen, result = set(), []
    for item in evidence:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            result.append(deepcopy(item))
    return result


class SnapshotStore:
    def __init__(self, read_chunks=None):
        self.read_chunks = read_chunks if read_chunks is not None else {}
        self.current_id = "X_EMPTY"
        self._snapshots = {self.current_id: {"schema_version": "extraction_v2", "input_snapshot_id": self.current_id,
                                           "records": {}, "versions": {}}}

    def get(self, snapshot_id):
        if snapshot_id not in self._snapshots:
            raise ContractError("Unknown input snapshot: " + str(snapshot_id), "UNKNOWN_SNAPSHOT")
        return deepcopy(self._snapshots[snapshot_id])

    def export(self):
        return {"current_id": self.current_id, "snapshots": deepcopy(self._snapshots)}

    def register(self, base_snapshot_id, records):
        if base_snapshot_id != self.current_id:
            raise ContractError("Registration must extend the current immutable snapshot", "STALE_SNAPSHOT")
        if not isinstance(records, list) or not records:
            raise ContractError("A registration batch must contain records")
        ids = []
        candidate = self.get(base_snapshot_id)
        for record in records:
            errors = list(Draft202012Validator(RECORD).iter_errors(record))
            if errors:
                raise ContractError("Record schema: " + errors[0].message)
            rid = record["record_id"]
            if not rid.strip() or rid in ids:
                raise ContractError("Record IDs must be nonempty and unique within a batch")
            if rid in candidate["records"] and candidate["records"][rid]["kind"] != record["kind"]:
                raise ContractError("A record's kind cannot change between versions")
            ids.append(rid)
            candidate["records"][rid] = deepcopy(record)
            candidate["versions"][rid] = candidate["versions"].get(rid, 0) + 1
        canonical = json.dumps({"records": candidate["records"], "versions": candidate["versions"]},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        sid = "X_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        candidate["input_snapshot_id"] = sid
        # Validate all dependencies before publishing either the state or ID.
        self._logical(candidate)
        self._snapshots[sid] = candidate
        self.current_id = sid
        return {"input_snapshot_id": sid, "registered_ids": ids}

    def register_batch(self, base_snapshot_id, records, read_chunks=None):
        if read_chunks is not None:
            self.read_chunks = read_chunks
        return self.register(base_snapshot_id, records)

    def preview_register(self, base_snapshot_id, records):
        """Validate and predict the exact acknowledgement without mutation."""
        return deepcopy(self).register(base_snapshot_id, records)

    def logical(self, snapshot_id):
        return self._logical(self.get(snapshot_id))

    def facts(self, snapshot_id):
        return self.logical(snapshot_id)["facts"]

    def evidence_for(self, snapshot_id, fact_ids):
        facts = self.facts(snapshot_id)
        if any(fid not in facts for fid in fact_ids):
            raise ContractError("Evidence references unknown fact", "UNKNOWN_FACT")
        return unique_evidence([ev for fid in fact_ids for ev in facts[fid]["evidence"]])

    def _evidence(self, evidence, claims):
        for ev in evidence:
            chunk = self.read_chunks.get(ev["chunk_id"])
            if not chunk or (chunk["doc_id"], chunk["page"]) != (ev["doc_id"], ev["page"]):
                raise ContractError("Evidence must reference an actually read allowed page: " + ev["chunk_id"], "UNREAD_EVIDENCE")
            if type(ev["page"]) is not int or not ev["locator"].strip() or ev["claim_id"] not in claims:
                raise ContractError("Evidence needs a valid claim, integer page and locator")

    def _logical(self, snapshot):
        records, sid = snapshot["records"], snapshot["input_snapshot_id"]
        contexts = {rid: r["payload"] for rid, r in records.items() if r["kind"] == "CONTEXT"}
        derivations = {rid: r["payload"] for rid, r in records.items() if r["kind"] == "DERIVATION"}
        facts, outputs = {}, {}
        for did, derivation in derivations.items():
            fid = derivation["output_fact_id"]
            if fid in outputs:
                raise ContractError("Two derivations cannot produce the same fact")
            if fid in records and records[fid]["kind"] != "VALUE":
                raise ContractError("A derived fact ID cannot shadow a different record type")
            outputs[fid] = did

        def context(cid, field):
            if cid not in contexts:
                raise ContractError("Unknown context: " + cid, "UNKNOWN_CONTEXT")
            ctx = contexts[cid]
            if any(not value.strip() for value in ctx.values()):
                raise ContractError("Context fields must be nonempty")
            if ctx["unit"] != FIELD_UNITS[field]:
                raise ContractError("Incorrect unit for field " + field)
            return deepcopy(ctx)

        for rid, record in records.items():
            if record["kind"] != "VALUE":
                continue
            p = record["payload"]
            fact = {"fact_id": rid, **deepcopy(p), **context(p["context_id"], p["field"]), "input_snapshot_id": sid}
            fact.pop("context_id")
            if not p["claim_id"].strip():
                raise ContractError("Claim IDs must be nonempty")
            value = p["value"]
            if value is not None:
                number = Decimal(value)
                if not number.is_finite():
                    raise ContractError("Facts require finite decimals")
                if fact["unit"] == "주" and (number < 0 or number != number.to_integral_value()):
                    raise ContractError("Share quantities require nonnegative integers")
                fact["value"] = decimal_text(number)
            if p["origin"] == "DISCLOSED":
                if value is None or not p["evidence"] or p["missing_reason"] is not None or p["derivation_id"] is not None:
                    raise ContractError("DISCLOSED needs a value and source evidence only")
                self._evidence(p["evidence"], {p["claim_id"]})
            elif p["origin"] in {"UNAVAILABLE", "NOT_APPLICABLE"}:
                if value is not None or not p["missing_reason"] or not p["missing_reason"].strip() or p["derivation_id"] is not None:
                    raise ContractError("Missing/not-applicable values need null and an explicit reason")
                self._evidence(p["evidence"], {p["claim_id"]})
            elif rid not in outputs or not p["derivation_id"] or p["derivation_id"] != outputs[rid]:
                raise ContractError("DERIVED needs its matching derivation", "UNKNOWN_DERIVATION")
            facts[rid] = fact

        known_facts = set(facts) | set(outputs)
        for did, d in derivations.items():
            context(d["context_id"], d["field"])
            if not d["claim_id"].strip():
                raise ContractError("Derivation claim ID must be nonempty")
            if len(d["input_fact_ids"]) != len(set(d["input_fact_ids"])):
                raise ContractError("Derivation input IDs must be unique")
            if any(fid not in known_facts for fid in d["input_fact_ids"]):
                raise ContractError("Unknown derivation input fact", "UNKNOWN_FACT")
            if d["output_fact_id"] in facts and facts[d["output_fact_id"]]["origin"] != "DERIVED":
                raise ContractError("A derivation cannot overwrite a disclosed/missing fact")

        active, done, derivation_results = set(), set(), []
        def resolve(fid):
            if fid not in outputs:
                return facts[fid]
            if fid in active:
                raise ContractError("Derivation dependency cycle", "DEPENDENCY_CYCLE")
            if fid in done:
                return facts[fid]
            active.add(fid)
            did = outputs[fid]
            d = derivations[did]
            inputs = [resolve(i) for i in d["input_fact_ids"]]
            ctx = context(d["context_id"], d["field"])
            result, status, reason = self._derive(d, inputs, records, ctx)
            fact = {"fact_id": fid, "claim_id": d["claim_id"], "field": d["field"], "entity_id": d["entity_id"],
                    "value": result, **ctx, "origin": "DERIVED", "evidence": unique_evidence([ev for f in inputs for ev in f["evidence"]]),
                    "missing_reason": reason, "derivation_id": did, "input_snapshot_id": sid}
            old = facts.get(fid)
            if old is not None:
                if any(old[key] != fact[key] for key in ("value", "field", "entity_id", "unit", "period", "as_of", "scope", "basis", "source_snapshot_id", "claim_id")):
                    raise ContractError("Submitted derived value differs from deterministic calculation")
                if old["evidence"] and unique_evidence(old["evidence"]) != fact["evidence"]:
                    raise ContractError("Derived evidence must preserve the original input evidence")
            facts[fid] = fact
            derivation_results.append({"derivation_id": did, **deepcopy(d), "input_snapshot_id": sid,
                                       "result": result, "status": status, "reason": reason, "evidence": deepcopy(fact["evidence"])})
            active.remove(fid)
            done.add(fid)
            return fact
        for fid in outputs:
            resolve(fid)

        claims = [f["claim_id"] for f in facts.values()]
        if len(set(claims)) != len(claims):
            raise ContractError("Fact claim IDs must be unique")
        claim_set = set(claims) | set(records)
        components, peers, selections, coverage = [], [], [], []
        used_components, peer_names, selection_fields = set(), set(), set()
        for rid, record in records.items():
            p = deepcopy(record["payload"])
            kind = record["kind"]
            if kind == "SHARE_COMPONENT":
                if p["fact_id"] not in facts or facts[p["fact_id"]]["unit"] != "주":
                    raise ContractError("Share component must reference a registered share quantity", "UNKNOWN_FACT")
                if facts[p["fact_id"]]["entity_id"] is not None:
                    raise ContractError("Issuer share component cannot reference a peer quantity")
                if p["fact_id"] in used_components:
                    raise ContractError("The same quantity cannot be counted as two components")
                used_components.add(p["fact_id"])
                if p["denominator_treatment"] != "EXCLUDE":
                    required_basis = "PRE_OFFER_BASE" if p["kind"] == "EXISTING" else "INCREMENT"
                    if p["basis"] != required_basis:
                        raise ContractError("Share component basis mixes pre-offer base and increments")
                if p["kind"] == "SECONDARY_SALE" and p["denominator_treatment"] == "INCLUDE":
                    raise ContractError("Secondary sale does not increase issued shares")
                if not p["treatment_reason"].strip():
                    raise ContractError("Share treatment needs a reason")
                if p["denominator_treatment"] != "UNRESOLVED" and not p["treatment_evidence"]:
                    raise ContractError("Resolved share treatment needs source evidence")
                self._evidence(p["treatment_evidence"], claim_set)
                if p["source_snapshot_id"] != facts[p["fact_id"]]["source_snapshot_id"]:
                    raise ContractError("Share component source snapshot differs from its quantity")
                components.append({"component_id": rid, **p, "quantity": facts[p["fact_id"]]["value"]})
            elif kind == "COVERAGE":
                self._evidence(p["evidence"], claim_set)
                if not p["reason"].strip() or (p["coverage_status"] == "COMPLETE" and not p["evidence"]):
                    raise ContractError("Coverage declaration needs evidence or an explicit incompleteness reason")
                coverage.append({"coverage_id": rid, **p})
            elif kind == "PEER":
                normalized_name = p["name"].strip().casefold()
                if not normalized_name or normalized_name in peer_names:
                    raise ContractError("Peer names must be nonempty and unique")
                peer_names.add(normalized_name)
                field_map = {"per_fact_id": "per", "market_cap_fact_id": "market_cap_million_krw", "earnings_fact_id": "earnings_million_krw",
                             "reference_price_fact_id": "reference_price_krw", "reference_shares_fact_id": "reference_shares"}
                for key, field in field_map.items():
                    fid = p[key]
                    if fid is not None and (fid not in facts or facts[fid]["field"] != field or facts[fid]["entity_id"] != rid):
                        raise ContractError("Peer references unknown or mismatched fact: " + key)
                peers.append({"peer_id": rid, **p})
            elif kind == "SELECTION":
                unique = (p["entity_id"], p["field"])
                if unique in selection_fields:
                    raise ContractError("A field can have only one current selection")
                selection_fields.add(unique)
                self._selection(p, facts)
                selections.append({"selection_id": rid, **p})
        sources = {p["source_snapshot_id"] for p in components if p["denominator_treatment"] != "EXCLUDE"}
        if len(sources) > 1:
            raise ContractError("Share components mix source snapshots")
        if len(coverage) > 1 or (sources and coverage and coverage[0]["source_snapshot_id"] not in sources):
            raise ContractError("Coverage must identify the same denominator source snapshot")
        values = {}
        for fact in facts.values():
            if fact["entity_id"] is None and fact["field"] != "share_quantity":
                # Multiple source observations remain in facts; only an explicit
                # selection can disambiguate them, never last-write-wins.
                field = fact["field"]
                if field in values:
                    values[field] = None
                else:
                    values[field] = fact
        return {"schema_version": "extraction_v2", "input_snapshot_id": sid, "facts": facts,
                "values": values, "share_components": components, "peers": peers,
                "selections": selections, "coverage": coverage, "derivations": derivation_results}

    @staticmethod
    def _selection(p, facts):
        if not p["selection_reason"].strip():
            raise ContractError("Selection reason must be nonempty")
        for key in ("selected_fact_id", "disclosed_fact_id"):
            fid = p[key]
            if fid is not None:
                if fid not in facts:
                    raise ContractError("Selection references unknown fact", "UNKNOWN_FACT")
                fact = facts[fid]
                compatible = {p["field"]}
                if p["field"] in {"share_count", "reported_share_count", "derived_share_count"}:
                    compatible |= {"share_count", "reported_share_count", "derived_share_count"}
                if fact["field"] not in compatible or fact["entity_id"] != p["entity_id"]:
                    raise ContractError("Selection field/entity differs from its fact")
        selected = facts.get(p["selected_fact_id"])
        disclosed = facts.get(p["disclosed_fact_id"])
        if p["usability"] in {"DIRECT", "DERIVABLE"}:
            expected = "DISCLOSED" if p["usability"] == "DIRECT" else "DERIVED"
            if not selected or selected["origin"] != expected or selected["value"] is None:
                raise ContractError("Usability does not match its selected fact")
        elif p["selected_fact_id"] is not None:
            raise ContractError("Unresolved/not-applicable selections cannot choose a usable fact")
        if p["disclosure_status"] == "PRESENT" and (not disclosed or disclosed["origin"] != "DISCLOSED"):
            raise ContractError("PRESENT requires an actual disclosed fact")
        if p["disclosure_status"] == "NOT_FOUND" and disclosed and disclosed["origin"] != "UNAVAILABLE":
            raise ContractError("NOT_FOUND must preserve a missing original observation")
        if p["disclosure_status"] == "NOT_APPLICABLE" and disclosed and disclosed["origin"] != "NOT_APPLICABLE":
            raise ContractError("NOT_APPLICABLE conflicts with original observation")

    @staticmethod
    def _derive(d, inputs, records, output_context):
        operation = d["operation"]
        specifications = {"MARKET_CAP": (["원", "주"], "백만원"), "PER": (["백만원", "백만원"], "배"),
                          "PRICE": (["백만원", "주"], "원")}
        if operation in specifications:
            units, output_unit = specifications[operation]
            if [f["unit"] for f in inputs] != units or output_context["unit"] != output_unit:
                raise ContractError("Derivation arity/units do not match its allowed formula")
        elif any(f["unit"] != "주" for f in inputs) or output_context["unit"] != "주":
            raise ContractError("Share sum only accepts share quantities")
        roles = {"MARKET_CAP": ([{"reference_price_krw"}, {"reference_shares"}], {"market_cap_million_krw"}),
                 "PER": ([{"market_cap_million_krw"}, {"earnings_million_krw"}], {"per"}),
                 "PRICE": ([{"reported_equity_million_krw"}, {"reported_share_count", "share_count", "derived_share_count"}], {"reported_price_krw"})}
        if operation in roles:
            input_roles, output_roles = roles[operation]
            if d["field"] not in output_roles or any(f["field"] not in allowed for f, allowed in zip(inputs, input_roles)):
                raise ContractError("Derivation fields do not match its allowed formula roles")
        elif d["field"] != "derived_share_count":
            raise ContractError("SHARE_SUM must produce derived_share_count")
        if any(f["entity_id"] != d["entity_id"] for f in inputs):
            return None, "INVALID", "Derivation mixes entity IDs"
        # The caller declares these comparable contexts; this is not an
        # automatic interpretation of financial meaning in the original source.
        for key in ("scope", "basis", "source_snapshot_id"):
            if len({f[key] for f in inputs} | {output_context[key]}) != 1:
                return None, "INVALID", "Declared contexts are incompatible: " + key
        if operation in {"MARKET_CAP", "PRICE", "SHARE_SUM"} and len({f["as_of"] for f in inputs} | {output_context["as_of"]}) != 1:
            return None, "INVALID", "Reference dates are incompatible"
        if operation == "SHARE_SUM":
            components = [r["payload"] for r in records.values() if r["kind"] == "SHARE_COMPONENT"]
            coverage = [r["payload"] for r in records.values() if r["kind"] == "COVERAGE"]
            included = [r["fact_id"] for r in components if r["denominator_treatment"] == "INCLUDE"]
            if set(d["input_fact_ids"]) != set(included):
                raise ContractError("SHARE_SUM must use exactly the declared included components")
            if not components or len(coverage) != 1 or coverage[0]["coverage_status"] != "COMPLETE" or any(r["denominator_treatment"] == "UNRESOLVED" for r in components):
                return None, "UNAVAILABLE", "Share denominator coverage is incomplete or unresolved"
        if any(f["value"] is None for f in inputs):
            return None, "UNAVAILABLE", "Required input facts are unavailable: " + ", ".join(f["fact_id"] for f in inputs if f["value"] is None)
        numbers = [Decimal(f["value"]) for f in inputs]
        if operation in {"MARKET_CAP", "PER", "PRICE"} and any(n <= 0 for n in numbers):
            return None, "INVALID", "PER valuation inputs must be positive"
        with localcontext() as context:
            context.prec = 40
            context.rounding = ROUND_HALF_EVEN
            result = (numbers[0] * numbers[1] / Decimal(1000000) if operation == "MARKET_CAP" else
                      numbers[0] / numbers[1] if operation == "PER" else
                      numbers[0] * Decimal(1000000) / numbers[1] if operation == "PRICE" else sum(numbers, Decimal(0)))
        return decimal_text(result), "OK", None
