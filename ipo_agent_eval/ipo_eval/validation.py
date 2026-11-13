"""Structural checks only. No gold, scoring, numeric correction, or semantic grading."""
import re
from jsonschema import Draft202012Validator
from .schemas import EXTRACTION, REVIEW


def facts_in(extraction):
    for key, fact in extraction["values"].items():
        yield key, fact
    for index, peer in enumerate(extraction["peers"]):
        for key in ("per", "market_cap_million_krw", "earnings_million_krw"):
            yield f"peers[{index}].{key}", peer[key]


def evidence_errors(evidence, chunks, known_claims):
    errors = []
    for ev in evidence:
        chunk = chunks.get(ev["chunk_id"])
        if not chunk or (chunk["doc_id"], chunk["page"]) != (ev["doc_id"], ev["page"]):
            errors.append("Unknown or mismatched evidence location: " + ev["chunk_id"])
        if ev["claim_id"] not in known_claims:
            errors.append("Evidence references unknown claim: " + ev["claim_id"])
        if not ev["locator"].strip():
            errors.append("Evidence requires a table or paragraph locator")
    return errors


def validate_extraction(value, chunks):
    errors = [e.message for e in Draft202012Validator(EXTRACTION).iter_errors(value)]
    if errors:
        return errors
    facts = list(facts_in(value))
    ids = [fact["claim_id"] for _, fact in facts]
    if len(set(ids)) != len(ids) or any(not i.strip() for i in ids):
        errors.append("Extraction claim IDs must be nonempty and unique")
    for field, fact in facts:
        unit = "백만원" if "million_krw" in field else "배" if field.endswith("per") else "원" if field == "reported_price_krw" else "주"
        if fact["unit"] != unit:
            errors.append(f"Field {field} must use unit {unit}")
        if fact["value"] is not None and not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", fact["value"]):
            errors.append("Input must be a finite decimal string without commas: " + field)
        if not fact["period"].strip() or not fact["description"].strip():
            errors.append("Input needs period and description: " + field)
        if fact["value"] is None and not fact["missing_reason"]:
            errors.append("Missing input needs a reason: " + field)
        if fact["value"] is not None and not fact["evidence"]:
            errors.append("Extracted input needs source evidence: " + field)
        errors += evidence_errors(fact["evidence"], chunks, {fact["claim_id"]})
    return errors


def validate_review(value, extraction, chunks, document_ids):
    errors = [e.message for e in Draft202012Validator(REVIEW).iter_errors(value)]
    if errors:
        return errors
    if [j["domain"] for j in value["judgments"]] != ["J1", "J2", "J3", "J4"]:
        errors.append("Exactly four judgments in J1, J2, J3, J4 order are required")
    jids = [j["judgment_id"] for j in value["judgments"]]
    fids = [f["claim_id"] for j in value["judgments"] for f in j["facts"]]
    xids = [f["claim_id"] for _, f in facts_in(extraction)]
    ids = jids + fids
    if len(set(ids)) != len(ids) or set(ids) & set(xids) or any(not i.strip() for i in ids):
        errors.append("Judgment and fact IDs must be unique, including extraction IDs")
    known = set(ids + xids)
    if not value["scope"]["document_ids"] or set(value["scope"]["document_ids"]) - set(document_ids):
        errors.append("Scope must name allowed documents")
    if len(value["memo"]) > 5:
        errors.append("Memo can contain at most five items")
    for j in value["judgments"]:
        if not j["conclusion"].strip() or not j["next_action"].strip():
            errors.append("Judgment needs a conclusion and next action")
        if not j["facts"] and not j["unknowns"]:
            errors.append("Judgment needs facts or explicit unknowns")
        for f in j["facts"]:
            if not f["text"].strip() or not f["evidence"]:
                errors.append("A factual claim needs text and evidence")
            errors += evidence_errors(f["evidence"], chunks, {f["claim_id"]})
        errors += evidence_errors(j["evidence"] + j["counter_evidence"], chunks, known)
    all_requests = value["requests"] + value["escalations"]
    request_ids = [r.get("request_id", r.get("escalation_id")) for r in all_requests]
    if len(set(request_ids)) != len(request_ids) or any(not i.strip() for i in request_ids):
        errors.append("Request and escalation IDs must be nonempty and unique")
    for request in all_requests:
        if not request["question"].strip() or not request["why_needed"].strip():
            errors.append("A request needs a specific question and reason")
        if not request["related_judgment_ids"] or set(request["related_judgment_ids"]) - set(jids):
            errors.append("Request references missing judgment")
        if request["resolution_status"] == "RESOLVED" and not request["resolution_evidence"]:
            errors.append("Resolved requests need evidence from the supplied corpus")
        errors += evidence_errors(request["resolution_evidence"], chunks, known)
    for judgment in value["judgments"]:
        kind = judgment["disposition"]
        group = value["requests"] if kind == "REQUEST_INFO" else value["escalations"] if kind == "ESCALATE" else None
        if group is not None and not any(judgment["judgment_id"] in r["related_judgment_ids"] for r in group):
            errors.append("Disposition requires a linked request: " + judgment["judgment_id"])
    missing = {field for field, fact in facts_in(extraction) if fact["value"] is None}
    if not extraction["peers"]:
        missing.add("peers")
    linked = {item["field"] for item in value["missing_inputs"]}
    if missing != linked or len(linked) != len(value["missing_inputs"]):
        errors.append("Every missing extracted input needs exactly a named missing_inputs entry")
    for item in value["missing_inputs"]:
        if item["request_id"] not in request_ids or not item["missing_reason"].strip():
            errors.append("Missing input must link to a request and explain the gap")
    return errors


def final_status(review, valid=True):
    if not valid or review is None:
        return "FAILED"
    if any(r["blocking"] and r["resolution_status"] != "RESOLVED" for r in review["escalations"]):
        return "HUMAN_REVIEW"
    if any(r["blocking"] and r["resolution_status"] != "RESOLVED" for r in review["requests"]):
        return "PENDING_INFO"
    return "READY"
