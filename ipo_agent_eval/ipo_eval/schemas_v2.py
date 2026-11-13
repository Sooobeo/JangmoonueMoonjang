"""Version 2 contracts. No case-specific values or grading answers live here."""
from copy import deepcopy

from .schemas import EVIDENCE, REVIEW, S, NULLABLE_S, arr, obj


def enum(*values):
    return {"type": "string", "enum": list(values)}


ID = {"type": "string", "minLength": 1, "maxLength": 160}
DECIMAL = {"type": ["string", "null"], "pattern": r"^[+-]?[0-9]+(?:\.[0-9]+)?$", "maxLength": 80}
FIELD_UNITS = {
    "earnings_million_krw": "백만원", "applied_per": "배", "per": "배",
    "reported_equity_million_krw": "백만원", "reported_price_krw": "원",
    "reported_share_count": "주", "share_count": "주", "derived_share_count": "주",
    "existing_shares": "주", "new_shares": "주", "dilutive_shares": "주",
    "secondary_sale_shares": "주", "share_quantity": "주",
    "market_cap_million_krw": "백만원", "reference_price_krw": "원", "reference_shares": "주",
}
FIELD = enum(*FIELD_UNITS)
ORIGIN = enum("DISCLOSED", "DERIVED", "UNAVAILABLE", "NOT_APPLICABLE")
CONTEXT_PAYLOAD = obj({"unit": enum("백만원", "원", "주", "배"), "period": ID,
                       "as_of": ID, "scope": ID, "basis": ID, "source_snapshot_id": ID})
VALUE_PAYLOAD = obj({"field": FIELD, "entity_id": NULLABLE_S, "claim_id": ID,
                     "value": DECIMAL, "context_id": ID, "origin": ORIGIN,
                     "evidence": arr(EVIDENCE), "missing_reason": NULLABLE_S,
                     "derivation_id": NULLABLE_S})
SHARE_PAYLOAD = obj({"fact_id": ID,
                     "kind": enum("EXISTING", "PRIMARY_NEW", "MANDATORY_UNDERWRITER", "ADDITIONAL_UNDERWRITER",
                                  "OPTION", "SECONDARY_SALE", "OTHER_DILUTION"),
                     "denominator_treatment": enum("INCLUDE", "EXCLUDE", "UNRESOLVED"),
                     "treatment_reason": ID, "treatment_evidence": arr(EVIDENCE),
                     "source_snapshot_id": ID, "basis": enum("PRE_OFFER_BASE", "INCREMENT", "POST_OFFER_TOTAL")})
PEER_PAYLOAD = obj({"name": ID, **{key: NULLABLE_S for key in (
    "per_fact_id", "market_cap_fact_id", "earnings_fact_id", "reference_price_fact_id", "reference_shares_fact_id")}})
DERIVATION_PAYLOAD = obj({"operation": enum("MARKET_CAP", "PER", "PRICE", "SHARE_SUM"),
                          "input_fact_ids": {**arr(ID), "minItems": 1}, "output_fact_id": ID,
                          "field": FIELD, "entity_id": NULLABLE_S, "context_id": ID, "claim_id": ID})
SELECTION_PAYLOAD = obj({"field": FIELD, "entity_id": NULLABLE_S,
                         "disclosed_fact_id": NULLABLE_S, "selected_fact_id": NULLABLE_S,
                         "disclosure_status": enum("PRESENT", "NOT_FOUND", "NOT_APPLICABLE"),
                         "usability": enum("DIRECT", "DERIVABLE", "UNRESOLVED", "NOT_APPLICABLE"),
                         "selection_reason": ID})
COVERAGE_PAYLOAD = obj({"coverage_status": enum("COMPLETE", "INCOMPLETE"), "reason": ID,
                        "evidence": arr(EVIDENCE), "source_snapshot_id": ID})
PAYLOADS = {"VALUE": VALUE_PAYLOAD, "SHARE_COMPONENT": SHARE_PAYLOAD, "PEER": PEER_PAYLOAD,
            "DERIVATION": DERIVATION_PAYLOAD, "SELECTION": SELECTION_PAYLOAD,
            "COVERAGE": COVERAGE_PAYLOAD, "CONTEXT": CONTEXT_PAYLOAD}
RECORD = {"anyOf": [obj({"record_id": ID, "kind": enum(kind), "payload": payload})
                    for kind, payload in PAYLOADS.items()]}
EXTRACTION_V2 = obj({"records": arr(RECORD), "document_version_notes": arr(S), "extraction_limits": arr(S)})
REGISTER_BATCH = obj({"operation": enum("REGISTER_BATCH"), "base_snapshot_id": ID,
                      "records": {**arr(RECORD), "minItems": 1}})
CALCULATION_TYPES = ["SHARE_SUM", "SHARE_DIFFERENCE", "MARKET_CAP", "PER", "PRICE", "PEER_AGGREGATES", "ALL"]
EVALUATE = obj({"operation": enum("EVALUATE"), "input_snapshot_id": ID,
                "calculation_types": {**arr(enum(*CALCULATION_TYPES)), "minItems": 1}})
CALCULATION_USE = obj({"calc_id": ID, "use": enum("USE", "REJECT"), "stated_value": DECIMAL,
                       "related_judgment_ids": arr(ID), "reason": ID,
                       "replacement_id": NULLABLE_S, "unresolved": {"type": "boolean"}})
REVIEW_V2 = deepcopy(REVIEW)
for name in ("requests", "escalations"):
    item = REVIEW_V2["properties"][name]["items"]
    item["properties"]["resolution_status"] = enum("OPEN", "RESOLVED", "CANCELLED")
    item["properties"].update({"version": {"type": "integer", "minimum": 1}, "change_reason": NULLABLE_S})
    item["required"] = list(item["properties"])
REVIEW_V2["properties"].update({
    "input_snapshot_id": ID, "calculation_uses": arr(CALCULATION_USE),
    "not_found_reasons": arr(obj({"field": ID,
        "reason": enum("NOT_READ", "SEARCH_NOT_FOUND", "UNAVAILABLE_IN_ALLOWED_INPUT", "BUDGET_LIMIT"),
        "explanation": ID})),
})
REVIEW_V2["required"] = list(REVIEW_V2["properties"])
REQUEST_V2 = REVIEW_V2["properties"]["requests"]["items"]
ESCALATION_V2 = REVIEW_V2["properties"]["escalations"]["items"]
FACT_V2 = obj({"fact_id": ID, "claim_id": ID, "field": FIELD, "entity_id": NULLABLE_S,
               "value": DECIMAL, **CONTEXT_PAYLOAD["properties"], "origin": ORIGIN,
               "evidence": arr(EVIDENCE), "missing_reason": NULLABLE_S, "derivation_id": NULLABLE_S,
               "input_snapshot_id": ID})
