"""The seven shared tools, scoped to one public case and one fresh execution."""
from copy import deepcopy
import re
import time
import uuid

from jsonschema import Draft202012Validator

from .budget import BudgetError, reservation
from .provenance import ContractError, SnapshotStore
from .schemas import S, arr, obj
from .schemas_v2 import (ID, REGISTER_BATCH, EVALUATE, REVIEW_V2, REQUEST_V2,
                         ESCALATION_V2, enum)
from .validation_v2 import evidence_errors, final_status, validate_review, unresolved_fields
from .wire_contract import REGISTER_WIRE_BATCH, expand_wire_extraction
from .wire_contract_v2 import REGISTER_WIRE_BATCH_V2, expand_wire_extraction_v2


class GatewayError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _schema_errors(schema, arguments):
    errors = [f"{'/'.join(map(str, item.absolute_path))}: {item.message}"
              for item in Draft202012Validator(schema).iter_errors(arguments)]
    def integers(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"page", "version", "top_k", "neighbor_pages"} and type(child) is not int:
                    errors.append(f"{key} must be an integer JSON value, not bool or float")
                integers(child)
        elif isinstance(value, list):
            for child in value:
                integers(child)
    integers(arguments)
    return errors


class RequestLedger:
    """Versioned requests remain visible even if omitted from a later response."""

    def __init__(self, read_chunks):
        self.read_chunks = read_chunks
        self._groups = {"requests": {}, "escalations": {}}
        self.history = []

    def export(self):
        return {**{key: deepcopy(list(value.values())) for key, value in self._groups.items()},
                "history": deepcopy(self.history)}

    def preview(self, group, entries, known_claims):
        if group not in self._groups:
            raise GatewayError("INVALID_ARGUMENT", "Unknown ledger group")
        schema = REQUEST_V2 if group == "requests" else ESCALATION_V2
        id_key = "request_id" if group == "requests" else "escalation_id"
        other = self._groups["escalations" if group == "requests" else "requests"]
        candidate = deepcopy(self._groups[group])
        changes, seen = [], set()
        for item in entries:
            errors = _schema_errors(schema, item)
            if errors:
                raise GatewayError("INVALID_ARGUMENT", "; ".join(errors))
            ident = item[id_key]
            if not ident.strip() or ident in seen or ident in other:
                raise GatewayError("INVALID_ARGUMENT", "Request IDs must be nonempty and unique across both ledgers")
            seen.add(ident)
            if not item["question"].strip() or not item["why_needed"].strip() or not item["related_judgment_ids"]:
                raise GatewayError("INVALID_ARGUMENT", "Request needs a question, reason and judgment references")
            if any(not ident.strip() for ident in item["related_judgment_ids"]):
                raise GatewayError("INVALID_ARGUMENT", "Judgment references must be nonempty")
            if group == "escalations" and not item["review_focus"].strip():
                raise GatewayError("INVALID_ARGUMENT", "Escalation needs a review focus")
            if item["resolution_status"] == "RESOLVED" and not item["resolution_evidence"]:
                raise GatewayError("INVALID_ARGUMENT", "RESOLVED requires actually read source evidence")
            if item["resolution_status"] == "CANCELLED" and not (item["change_reason"] or "").strip():
                raise GatewayError("INVALID_ARGUMENT", "CANCELLED requires an explicit reason")
            errors = evidence_errors(item["resolution_evidence"], self.read_chunks, known_claims)
            if errors:
                raise GatewayError("INVALID_ARGUMENT", "; ".join(errors))
            previous = candidate.get(ident)
            if previous == item:
                continue
            expected = previous["version"] + 1 if previous else 1
            if item["version"] != expected:
                raise GatewayError("INVALID_ARGUMENT", f"Request {ident} requires version {expected}")
            if previous and not (item["change_reason"] or "").strip():
                raise GatewayError("INVALID_ARGUMENT", "Changed request requires an explicit change reason")
            candidate[ident] = deepcopy(item)
            changes.append({"group": group, "id": ident, "previous": deepcopy(previous), "current": deepcopy(item)})
        return candidate, changes

    def update(self, group, entries, known_claims):
        candidate, changes = self.preview(group, entries, known_claims)
        self._groups[group] = candidate
        self.history.extend(changes)
        return {"registered_ids": [item.get("request_id", item.get("escalation_id")) for item in entries],
                "active_records": deepcopy(list(candidate.values())), "new_versions": len(changes),
                "external_messages_sent": 0}


class ToolGateway:
    def __init__(self, run, corpus, store=None):
        self.run = run
        self.corpus = corpus
        self.read_chunks = {}
        self.store = store if store is not None else SnapshotStore(self.read_chunks)
        if store is not None:
            self.read_chunks = store.read_chunks
        self.calculations = {}
        self.search_hits = []
        self.ledger = RequestLedger(self.read_chunks)
        self.prepared_snapshot = None
        self.submitted_review = None
        self.submission_id = None
        self.fatal_error = None
        self._final_sync_done = False
        self._synced_arguments = None
        self.envelopes = []
        self.read_page_calls = 0
        self._seen_call_ids = set()

    def _schemas(self, phase):
        submit = (obj({"phase": enum("COMMIT"), "input_snapshot_id": ID, "review": self.review_schema()})
                  if phase in {"FINALIZING", "REPAIR"} else
                  obj({"phase": enum("PREPARE"), "input_snapshot_id": ID}))
        if phase in {"FINALIZING", "REPAIR"}:
            return {"submit_review": submit}
        register = {"compact_v1": REGISTER_WIRE_BATCH, "compact_v2": REGISTER_WIRE_BATCH_V2}.get(
            self.run.config.get("wire_contract"), REGISTER_BATCH)
        return {
            "search_corpus": obj({"query": {**S, "minLength": 1, "maxLength": 300},
                "top_k": {"type": "integer", "minimum": 1, "maximum": self.run.config.get("search_top_k_max", 3)},
                "filters": obj({"doc_id": {"type": ["string", "null"]}, "cutoff_status": enum("BEFORE")})}),
            "read_source": obj({"chunk_ids": {**arr(ID), "minItems": 1, "maxItems": 3},
                                "neighbor_pages": {"type": "integer", "minimum": 0, "maximum": 1}}),
            "calculate": obj({"request": {"anyOf": [register, EVALUATE]}}),
            "sensitivity": obj({"input_snapshot_id": ID,
                "alternatives": {**arr(enum("MEAN", "MEDIAN", "LEAVE_ONE_OUT")), "minItems": 1}}),
            "request_information": obj({"requests": arr(REQUEST_V2)}),
            "escalate": obj({"escalations": arr(ESCALATION_V2)}),
            "submit_review": submit,
        }

    def review_schema(self):
        schema = deepcopy(REVIEW_V2)
        if self.run.config.get("dynamic_submission_contract"):
            logical = self.store.logical(self.store.current_id)
            fields = sorted(unresolved_fields(logical))
            missing = schema["properties"]["missing_inputs"]
            missing.update(minItems=len(fields), maxItems=len(fields))
            if fields:
                # S is reused throughout the source schema; deepcopy preserves
                # that alias graph. Replace this leaf, never mutate the shared
                # string dictionary (which would constrain prose/doc IDs too).
                missing["items"]["properties"]["field"] = {
                    **missing["items"]["properties"]["field"], "enum": fields}
            # Expose the existing validator's mutually exclusive use/rejection
            # modes before generation. Replace whole branch leaves; shared ID,
            # string and Decimal dictionaries must remain untouched.
            base = schema["properties"]["calculation_uses"]["items"]
            use, replace, unresolved = (deepcopy(base) for _ in range(3))
            use["properties"].update({
                "use": enum("USE"),
                "stated_value": {**use["properties"]["stated_value"], "type": "string"},
                "replacement_id": {"type": "null"},
                "unresolved": {"type": "boolean", "enum": [False]},
            })
            replace["properties"].update({
                "use": enum("REJECT"), "replacement_id": deepcopy(ID),
                "unresolved": {"type": "boolean", "enum": [False]},
            })
            unresolved["properties"].update({
                "use": enum("REJECT"), "replacement_id": {"type": "null"},
                "unresolved": {"type": "boolean", "enum": [True]},
            })
            schema["properties"]["calculation_uses"]["items"] = {
                "anyOf": [use, replace, unresolved]}
            existing_claims = [fact["claim_id"] for fact in logical["facts"].values()]
            prefix, suffix = "REVIEW_", 2
            while any(claim.startswith(prefix) for claim in existing_claims):
                prefix = "REVIEW" + str(suffix) + "_"
                suffix += 1
            fact_properties = schema["properties"]["judgments"]["items"]["properties"]["facts"]["items"]["properties"]
            fact_properties["claim_id"] = {
                **fact_properties["claim_id"], "pattern": "^" + prefix + "[A-Za-z0-9_-]+$", "maxLength": 160,
                "description": "New review fact declaration: use a globally unique ID beginning with "
                    + prefix + "; do not redeclare a registered extraction claim ID."}
        return schema

    def state_view(self):
        """Neutral observations, never an instruction choosing A0's next action."""
        run = self.run
        fields = sorted(unresolved_fields(self.store.logical(self.store.current_id)))
        limits = {key: run.config[key] for key in ("max_model_calls", "max_tool_calls", "input_tokens_target_max", "output_tokens_max", "max_run_usd", "wall_seconds_max")}
        used = {"model_calls": run.model_calls, "tool_calls": run.tool_calls,
                "input_tokens": run.input_tokens, "output_tokens": run.output_tokens,
                "cost_ceiling_usd": run.cost_ceiling_usd,
                "uncertain_input_reserve": getattr(run, "unknown_input_tokens_reserved", 0),
                "uncertain_output_reserve": getattr(run, "unknown_output_tokens_reserved", 0),
                "uncertain_cost_reserve": getattr(run, "unknown_cost_ceiling_usd", 0)}
        reserved = reservation(run.config, run.phase, run.repairs, run.final_input_estimate)
        remaining = {"model_calls": limits["max_model_calls"] - used["model_calls"],
                     "tool_calls": limits["max_tool_calls"] - used["tool_calls"],
                     "input_tokens": limits["input_tokens_target_max"] - used["input_tokens"] - used["uncertain_input_reserve"],
                     "output_tokens": limits["output_tokens_max"] - used["output_tokens"] - used["uncertain_output_reserve"],
                     "cost_ceiling_usd": limits["max_run_usd"] - used["cost_ceiling_usd"] - used["uncertain_cost_reserve"]}
        return {"input_snapshot_id": self.store.current_id,
                "registered_record_count": len(self.store.get(self.store.current_id)["records"]),
                "registered_fact_ids": sorted(self.store.facts(self.store.current_id)),
                "calculation_ids": sorted(self.calculations), "read_page_count": len(self.read_chunks),
                "required_missing_input_fields": fields,
                "missing_inputs_contract": "Exactly one entry for each required field; other business unknowns belong in judgments.unknowns, not_found_reasons and requests.",
                "request_ledger": self.ledger.export(),
                "budget": {"limits": limits, "used": used, "remaining_before_reservations": remaining,
                    "last_final_input_estimate": run.final_input_estimate,
                    "reservation_at_last_estimate": vars(reserved),
                    "note": "The next full request and its finalization reservation are estimated again before sending; remaining values are not a promise of further tool calls.",
                    "remaining_seconds": round(run.remaining_time(), 1)}}

    def tools(self, phase="EXPLORING"):
        descriptions = {
            "search_corpus": "Search this case's registered public corpus. Excerpts are discovery hints, not read evidence. No external sources or paths.",
            "read_source": "Read complete source pages for up to 3 allowed chunk IDs with 0 or 1 neighbor page. Only returned pages may be cited.",
            "calculate": "REGISTER_BATCH adds typed records atomically to the current snapshot; EVALUATE computes allowed formulas from a registered snapshot. Refer to existing context/fact IDs.",
            "sensitivity": "Compute hypothetical mean, median or leave-one-out peer alternatives using the registered snapshot; alternatives are not disclosed facts.",
            "request_information": "Register or revise information requests. Every new ID starts at version 1; revisions require increment and reason. Nothing is sent externally.",
            "escalate": "Register or revise human-review escalations with version and evidence. Nothing is sent externally or marked reviewed automatically.",
            "submit_review": "PREPARE freezes the current snapshot for finalization. COMMIT supplies the final review, preserving all previous OPEN requests and actual calculation references.",
        }
        return [{"type": "function", "name": name, "description": descriptions[name],
                 "parameters": schema, "strict": True} for name, schema in self._schemas(phase).items()]

    def _known_claims(self, review=None):
        claims = {fact["claim_id"] for fact in self.store.facts(self.store.current_id).values()}
        if isinstance(review, dict):
            for judgment in review.get("judgments", []):
                if not isinstance(judgment, dict):
                    continue
                claims.add(judgment.get("judgment_id"))
                claims.update(fact.get("claim_id") for fact in judgment.get("facts", []) if isinstance(fact, dict))
        claims.discard(None)
        return claims

    def _boundary(self, name, arguments):
        allowed_docs = set(self.corpus.case["allowed_doc_ids"])
        forbidden_keys = {"case_id", "path", "file_path", "directory", "shell", "command", "url", "source_url"}

        def walk(value):
            if isinstance(value, dict):
                if set(value) & forbidden_keys:
                    raise GatewayError("ISOLATION_VIOLATION", "Caller cannot specify another case, path, URL or executable")
                if "doc_id" in value and value["doc_id"] is not None:
                    if not isinstance(value["doc_id"], str):
                        raise GatewayError("INVALID_ARGUMENT", "Document ID must be a string or null")
                    if value["doc_id"] not in allowed_docs:
                        raise GatewayError("ISOLATION_VIOLATION", "Document is outside the registered public case")
                if "cutoff_status" in value and value["cutoff_status"] != "BEFORE":
                    raise GatewayError("ISOLATION_VIOLATION", "Only material available before the cutoff is allowed")
                if (self.run.config.get("wire_contract") in {"compact_v1", "compact_v2"} and
                        {"chunk", "claim", "at"}.issubset(value) and
                        isinstance(value["chunk"], str) and value["chunk"] not in self.corpus.by_id):
                    raise GatewayError("ISOLATION_VIOLATION", "Compact evidence chunk is outside the registered public case")
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(arguments)
        if name == "read_source" and isinstance(arguments, dict):
            for chunk_id in arguments.get("chunk_ids", []) if isinstance(arguments.get("chunk_ids"), list) else []:
                if isinstance(chunk_id, str) and chunk_id not in self.corpus.by_id:
                    raise GatewayError("ISOLATION_VIOLATION", "Chunk is unknown or outside the registered public case")
        query = arguments.get("query", "") if isinstance(arguments, dict) else ""
        if name == "search_corpus" and isinstance(query, str) and re.search(r"https?://|file://|[A-Za-z]:[\\/]|(?:^|\s)\.\.[\\/]", query):
            raise GatewayError("ISOLATION_VIOLATION", "Search accepts corpus terms, not external locators")

    def dispatch(self, name, arguments, call_id=None, actor=None):
        call_id = call_id or "gateway_" + uuid.uuid4().hex[:12]
        before = self.run.tool_calls
        page_before = self.read_page_calls
        state_before = (self.store.current_id, len(self.read_chunks), len(self.calculations), len(self.ledger.history))
        started = time.monotonic()
        error_code = message = None
        result = None
        phase = self.run.phase
        reserved = (3 + int(self.run.repairs < self.run.config["max_format_repairs"])) if phase not in {"FINALIZING", "REPAIR"} else int(self.run.repairs < self.run.config["max_format_repairs"])
        if phase in {"FINALIZING", "REPAIR"} and name == "submit_review" and not self._final_sync_done:
            reserved += 2

        def invoke():
            if self.fatal_error:
                raise GatewayError("ISOLATION_VIOLATION", "The execution was terminated after an isolation violation")
            if call_id in self._seen_call_ids:
                raise GatewayError("INVALID_ARGUMENT", "Duplicate tool call ID")
            self._seen_call_ids.add(call_id)
            self._boundary(name, arguments)
            schemas = self._schemas(phase)
            if name not in schemas:
                raise GatewayError("INVALID_ARGUMENT", "Tool is not allowed in the current phase")
            if name == "read_source" and isinstance(arguments, dict) and isinstance(arguments.get("chunk_ids"), list) and len(arguments["chunk_ids"]) > 3:
                raise GatewayError("TOO_LARGE", "At most 3 chunk IDs and 9 full pages may be requested")
            errors = _schema_errors(schemas[name], arguments)
            if errors:
                raise GatewayError("INVALID_ARGUMENT", "; ".join(errors))
            return self._execute(name, arguments, call_id)

        try:
            result = self.run.tool(name, arguments, invoke, reserved_calls=reserved, actor=actor, call_id=call_id)
        except GatewayError as exc:
            error_code, message = exc.code, str(exc)
            if error_code == "ISOLATION_VIOLATION":
                self.fatal_error = error_code
        except ContractError as exc:
            error_code, message = exc.code, str(exc)
        except BudgetError as exc:
            error_code, message = "BUDGET_LIMIT", str(exc)
        if error_code is not None:
            state_after = (self.store.current_id, len(self.read_chunks), len(self.calculations), len(self.ledger.history))
            result = {"partial_execution": state_after != state_before}
        envelope = {"call_id": call_id, "tool": name, "ok": error_code is None, "result": result,
                    "error_code": error_code, "message": message,
                    "usage_delta": {"tool_calls": self.run.tool_calls - before,
                                    "pages": self.read_page_calls - page_before,
                                    "new_read_pages": len(self.read_chunks) - state_before[1],
                                    "seconds": round(time.monotonic() - started, 6)}}
        if self.run.config.get("dynamic_submission_contract"):
            envelope["state"] = self.state_view()
        self.envelopes.append(deepcopy(envelope))
        self.run.log("tool_envelope", envelope)
        return envelope

    def _execute(self, name, arguments, call_id):
        if name == "search_corpus":
            if not arguments["query"].strip():
                raise GatewayError("INVALID_ARGUMENT", "Query must contain search terms")
            filters = {key: value for key, value in arguments["filters"].items() if value is not None}
            result = self.corpus.search_corpus(self.corpus.case["case_id"], arguments["query"], filters, arguments["top_k"])
            self.run.reserve_observation(result)
            self.search_hits.append(deepcopy(result))
            return result
        if name == "read_source":
            result = self.corpus.read_source(arguments["chunk_ids"], arguments["neighbor_pages"])
            if len(result["chunks"]) > 9:
                raise GatewayError("TOO_LARGE", "At most 9 full pages can be returned; none have been marked read")
            self.run.reserve_observation(result)
            self.read_page_calls += len(result["chunks"])
            self.read_chunks.update({chunk["chunk_id"]: deepcopy(chunk) for chunk in result["chunks"]})
            return result
        if name == "calculate":
            request = arguments["request"]
            if request["operation"] == "REGISTER_BATCH":
                if self.run.config.get("wire_contract") in {"compact_v1", "compact_v2"}:
                    expand = (expand_wire_extraction_v2 if self.run.config["wire_contract"] == "compact_v2"
                              else expand_wire_extraction)
                    expanded = expand(request["batch"], self.read_chunks)
                    request = {"operation": "REGISTER_BATCH", "base_snapshot_id": request["base_snapshot_id"], "records": expanded["records"]}
                    self._boundary(name, request)
                result = self.store.preview_register(request["base_snapshot_id"], request["records"])
                self.run.reserve_observation(result)
                return self.store.register(request["base_snapshot_id"], request["records"])
            from .calculations_v2 import evaluate
            result = evaluate(self.store, request["input_snapshot_id"], request["calculation_types"])
            self.run.reserve_observation(result)
            self.calculations.update({calc["calc_id"]: deepcopy(calc) for calc in result["calculations"]})
            return result
        if name == "sensitivity":
            from .calculations_v2 import sensitivity
            result = sensitivity(self.store, arguments["input_snapshot_id"], arguments["alternatives"])
            self.run.reserve_observation(result)
            self.calculations.update({calc["calc_id"]: deepcopy(calc) for calc in result["calculations"]})
            return result
        if name in {"request_information", "escalate"}:
            group = "requests" if name == "request_information" else "escalations"
            known_claims = self._known_claims()
            candidate, changes = self.ledger.preview(group, arguments[group], known_claims)
            self.run.reserve_observation({"active_records": list(candidate.values()), "new_versions": len(changes)})
            result = self.ledger.update(group, arguments[group], known_claims)
            self._update_run_ledger()
            return result
        if arguments["phase"] == "PREPARE":
            snapshot = arguments["input_snapshot_id"]
            self.store.get(snapshot)
            if snapshot != self.store.current_id:
                raise GatewayError("STALE_SNAPSHOT", "PREPARE must use the current snapshot")
            result = {"phase": "FINALIZING", "input_snapshot_id": snapshot}
            self.run.reserve_observation(result)
            self.prepared_snapshot = snapshot
            return result
        return self._commit(arguments, call_id)

    def _update_run_ledger(self):
        exported = self.ledger.export()
        self.run.requests = exported["requests"]
        self.run.escalations = exported["escalations"]

    def _commit(self, arguments, call_id):
        snapshot = arguments["input_snapshot_id"]
        review = deepcopy(arguments["review"])
        self.store.get(snapshot)
        if snapshot != self.store.current_id or (self.prepared_snapshot is not None and snapshot != self.prepared_snapshot):
            raise GatewayError("STALE_SNAPSHOT", "COMMIT must use the current frozen snapshot")
        if review["input_snapshot_id"] != snapshot:
            raise GatewayError("INVALID_REVIEW", "Outer and review input snapshots differ")
        known_claims = self._known_claims(review)
        if not self._final_sync_done:
            # Validate both groups before either update to keep malformed ledger
            # batches atomic. The two synchronization calls are still recorded.
            preview_ledger = RequestLedger(self.read_chunks)
            preview_ledger._groups = deepcopy(self.ledger._groups)
            for group in ("requests", "escalations"):
                preview_ledger.update(group, review[group], known_claims)
            def synchronize(group):
                return self.ledger.update(group, review[group], known_claims)
            repair_reserve = int(self.run.repairs < self.run.config["max_format_repairs"])
            for index, (tool, group) in enumerate((("request_information", "requests"), ("escalate", "escalations"))):
                self.run.tool(tool, {group: review[group]}, lambda group=group: synchronize(group),
                              reserved_calls=(1 - index) + repair_reserve,
                              actor="program_commit", call_id=f"{call_id}_sync_{group}")
            self._final_sync_done = True
            self._synced_arguments = {group: deepcopy(review[group]) for group in ("requests", "escalations")}
        elif any(review[group] != self._synced_arguments[group] for group in ("requests", "escalations")):
            raise GatewayError("INVALID_REVIEW", "A format-only resubmission cannot alter already synchronized requests")
        self._update_run_ledger()
        ledger = self.ledger.export()
        review["requests"], review["escalations"] = ledger["requests"], ledger["escalations"]
        errors = validate_review(review, self.store, self.read_chunks, self.corpus.case["allowed_doc_ids"],
                                 self.calculations, expected_snapshot=self.prepared_snapshot or snapshot)
        if errors:
            raise GatewayError("INVALID_REVIEW", "; ".join(errors))
        self.prepared_snapshot = snapshot
        self.submitted_review = review
        self.submission_id = "SUB_" + uuid.uuid4().hex[:16]
        return {"submission_id": self.submission_id, "input_snapshot_id": snapshot,
                "execution_status": "SUBMITTED", "content_status": final_status(review),
                "requests": review["requests"], "escalations": review["escalations"]}


Gateway = ToolGateway
