"""Public output contracts, independent of any case-specific grading answers."""

def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def arr(items):
    return {"type": "array", "items": items}


S = {"type": "string"}
NULLABLE_S = {"type": ["string", "null"]}
EVIDENCE = obj({"doc_id": S, "chunk_id": S, "page": {"type": "integer"}, "claim_id": S, "locator": S})
FACT = obj({"claim_id": S, "value": NULLABLE_S, "unit": S, "period": S, "description": S,
            "evidence": arr(EVIDENCE), "missing_reason": NULLABLE_S})
VALUE_FIELDS = ["earnings_million_krw", "applied_per", "reported_equity_million_krw", "reported_price_krw",
                "share_count", "existing_shares", "new_shares", "dilutive_shares", "secondary_sale_shares"]
PEER = obj({"name": S, "per": FACT, "market_cap_million_krw": FACT, "earnings_million_krw": FACT})
EXTRACTION = obj({"values": obj({key: FACT for key in VALUE_FIELDS}), "peers": arr(PEER),
                  "document_version_notes": arr(S), "extraction_limits": arr(S)})
CLAIM = obj({"claim_id": S, "text": S, "evidence": arr(EVIDENCE)})
JUDGMENT = obj({"judgment_id": S, "domain": {"type": "string", "enum": ["J1", "J2", "J3", "J4"]},
                "conclusion": S, "disposition": {"type": "string", "enum": ["ACCEPT", "CONDITIONAL", "REQUEST_INFO", "ESCALATE"]},
                "facts": arr(CLAIM), "evidence": arr(EVIDENCE), "counter_evidence": arr(EVIDENCE),
                "unknowns": arr(S), "next_action": S})
REQUEST_BASE = {"question": S, "why_needed": S, "related_judgment_ids": arr(S), "blocking": {"type": "boolean"},
                "resolution_status": {"type": "string", "enum": ["OPEN", "RESOLVED"]}, "resolution_evidence": arr(EVIDENCE)}
REVIEW = obj({"scope": obj({"document_ids": arr(S), "verification_limits": arr(S)}),
              "judgments": {**arr(JUDGMENT), "minItems": 4, "maxItems": 4}, "requests": arr(obj({"request_id": S, **REQUEST_BASE})),
              "escalations": arr(obj({"escalation_id": S, "review_focus": S, **REQUEST_BASE})),
              "missing_inputs": arr(obj({"field": S, "missing_reason": S, "request_id": S})),
              "memo": {**arr(S), "maxItems": 5}, "model_reported_status": {"type": "string", "enum": ["READY", "PENDING_INFO", "HUMAN_REVIEW"]}})

ID_REPAIRS = obj({"repairs": arr(obj({"path": S, "replacement": S}))})
MEMO_REPAIR = obj({"memo": {**arr(S), "maxItems": 5}})
