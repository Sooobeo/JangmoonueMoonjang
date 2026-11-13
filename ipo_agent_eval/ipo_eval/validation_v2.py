"""Mechanical v2 submission checks; no gold answers or semantic correction."""
from decimal import Decimal, InvalidOperation

from jsonschema import Draft202012Validator

from .provenance import ContractError
from .schemas_v2 import REVIEW_V2


def field_key(field, entity_id=None):
    return f"{entity_id}.{field}" if entity_id is not None else field


def evidence_errors(evidence, read_chunks, known_claims):
    errors = []
    for item in evidence:
        chunk = read_chunks.get(item["chunk_id"])
        if not chunk or (chunk["doc_id"], chunk["page"]) != (item["doc_id"], item["page"]):
            errors.append("Evidence must reference an actually read allowed page: " + item["chunk_id"])
        if type(item["page"]) is not int or item["page"] < 1:
            errors.append("Evidence page must be a positive integer")
        if item["claim_id"] not in known_claims:
            errors.append("Evidence references unknown claim: " + item["claim_id"])
        if not item["locator"].strip():
            errors.append("Evidence requires a nonempty source locator")
    return errors


def facts_in_v2(logical):
    for fact_id, fact in logical["facts"].items():
        yield fact_id, fact


def unresolved_fields(logical):
    # The model explicitly declares whether the business field is usable. A
    # missing original observation with a selected derivation is not a gap.
    return {field_key(item["field"], item["entity_id"]) for item in logical["selections"]
            if item["usability"] == "UNRESOLVED"}


def final_status(review, valid=True):
    if not valid or review is None:
        return None
    if any(item["blocking"] and item["resolution_status"] == "OPEN" for item in review["escalations"]):
        return "HUMAN_REVIEW"
    if any(item["blocking"] and item["resolution_status"] == "OPEN" for item in review["requests"]):
        return "PENDING_INFO"
    return "READY"


def validate_review(value, store, read_chunks, document_ids, calculations, expected_snapshot=None):
    errors = [f"{'/'.join(map(str, error.absolute_path))}: {error.message}"
              for error in Draft202012Validator(REVIEW_V2).iter_errors(value)]
    if errors:
        return errors
    snapshot = value["input_snapshot_id"]
    if expected_snapshot is not None and snapshot != expected_snapshot:
        errors.append("Submission must use the frozen final input snapshot")
    if snapshot != store.current_id:
        errors.append("Submission cannot use an obsolete extraction snapshot")
    try:
        logical = store.logical(snapshot)
    except ContractError as exc:
        return errors + [str(exc)]
    judgments = value["judgments"]
    if [item["domain"] for item in judgments] != ["J1", "J2", "J3", "J4"]:
        errors.append("Exactly four judgments in J1, J2, J3, J4 order are required")
    judgment_ids = [item["judgment_id"] for item in judgments]
    claim_ids = [fact["claim_id"] for item in judgments for fact in item["facts"]]
    extraction_claims = [fact["claim_id"] for _, fact in facts_in_v2(logical)]
    defined = judgment_ids + claim_ids + extraction_claims
    if len(defined) != len(set(defined)) or any(not item.strip() for item in defined):
        errors.append("Defined judgment and claim IDs must be nonempty and globally unique")
    known_claims = set(defined)
    scope = value["scope"]["document_ids"]
    if not scope or len(scope) != len(set(scope)) or set(scope) - set(document_ids):
        errors.append("Scope must list unique allowed document IDs")
    for judgment in judgments:
        if not judgment["conclusion"].strip() or not judgment["next_action"].strip():
            errors.append("Judgment requires a conclusion and next action")
        if not judgment["facts"] and not judgment["unknowns"]:
            errors.append("Judgment requires source facts or explicit unknowns")
        if any(not text.strip() for text in judgment["unknowns"]):
            errors.append("Unknowns must describe the limitation")
        for fact in judgment["facts"]:
            if not fact["text"].strip() or not fact["evidence"]:
                errors.append("A factual claim requires text and actually read evidence")
            errors += evidence_errors(fact["evidence"], read_chunks, {fact["claim_id"]})
        errors += evidence_errors(judgment["evidence"] + judgment["counter_evidence"], read_chunks, known_claims)
    requests = value["requests"] + value["escalations"]
    request_ids = [item.get("request_id", item.get("escalation_id")) for item in requests]
    if len(request_ids) != len(set(request_ids)) or any(not item.strip() for item in request_ids):
        errors.append("Request and escalation IDs must be nonempty and globally unique")
    for item in requests:
        if type(item["version"]) is not int or item["version"] < 1:
            errors.append("Request version must be a positive integer JSON value")
        if not item["question"].strip() or not item["why_needed"].strip():
            errors.append("A request needs a specific question and reason")
        if not item["related_judgment_ids"] or set(item["related_judgment_ids"]) - set(judgment_ids):
            errors.append("Request references a missing judgment")
        if "review_focus" in item and not item["review_focus"].strip():
            errors.append("Escalation needs a review focus")
        if item["resolution_status"] == "RESOLVED" and not item["resolution_evidence"]:
            errors.append("Resolved requests require evidence from actually read pages")
        if item["resolution_status"] == "CANCELLED" and not (item["change_reason"] or "").strip():
            errors.append("Cancelled requests require an explicit reason")
        errors += evidence_errors(item["resolution_evidence"], read_chunks, known_claims)
    for judgment in judgments:
        group = (value["requests"] if judgment["disposition"] == "REQUEST_INFO" else
                 value["escalations"] if judgment["disposition"] == "ESCALATE" else None)
        if group is not None and not any(judgment["judgment_id"] in item["related_judgment_ids"] for item in group):
            errors.append("Disposition requires a linked request: " + judgment["judgment_id"])
    missing = unresolved_fields(logical)
    linked = [item["field"] for item in value["missing_inputs"]]
    if set(linked) != missing or len(linked) != len(set(linked)):
        errors.append("missing_inputs must name each declared UNRESOLVED business dependency exactly once")
    request_by_id = dict(zip(request_ids, requests))
    for item in value["missing_inputs"]:
        request = request_by_id.get(item["request_id"])
        if not request or request["resolution_status"] != "OPEN" or not item["missing_reason"].strip():
            errors.append("An unresolved dependency requires an OPEN request and explanation")
    used = set()
    for item in value["calculation_uses"]:
        calc_id = item["calc_id"]
        if calc_id in used:
            errors.append("Duplicate calculation use: " + calc_id)
        used.add(calc_id)
        calc = calculations.get(calc_id)
        if calc is None:
            errors.append("Unknown calculation ID: " + calc_id)
            continue
        if not item["related_judgment_ids"] or set(item["related_judgment_ids"]) - set(judgment_ids):
            errors.append("Calculation use requires existing judgment references")
        if not item["reason"].strip():
            errors.append("Calculation use/rejection requires a reason")
        if item["use"] == "USE":
            if calc["input_snapshot_id"] != snapshot or calc["status"] != "OK":
                errors.append("Used calculation must be OK and belong to the final snapshot")
            try:
                stated, actual = Decimal(item["stated_value"]), Decimal(calc["result"])
                if not stated.is_finite() or not actual.is_finite() or stated != actual:
                    errors.append("Structured stated value differs from calculation: " + calc_id)
            except (InvalidOperation, TypeError, ValueError):
                errors.append("Used calculation needs a finite Decimal stated value")
            if item["replacement_id"] is not None or item["unresolved"]:
                errors.append("USE cannot also declare a replacement or unresolved result")
        else:
            replacement = item["replacement_id"]
            if replacement is None:
                if not item["unresolved"]:
                    errors.append("REJECT requires a replacement or an explicit unresolved state")
            elif item["unresolved"] or replacement == calc_id:
                errors.append("REJECT cannot replace itself or combine replacement with unresolved")
            elif replacement in calculations:
                target = calculations[replacement]
                if target["input_snapshot_id"] != snapshot or target["status"] != "OK":
                    errors.append("Replacement calculation must be usable in the final snapshot")
            elif replacement not in logical["facts"] or logical["facts"][replacement]["value"] is None:
                errors.append("Replacement must reference a usable final fact or calculation")
    if len({item["field"] for item in value["not_found_reasons"]}) != len(value["not_found_reasons"]):
        errors.append("Not-found classifications must have unique field names")
    for item in value["not_found_reasons"]:
        if not item["field"].strip() or not item["explanation"].strip():
            errors.append("Not-found classifications require a field and explanation")
    return errors


validate_review_v2 = validate_review
