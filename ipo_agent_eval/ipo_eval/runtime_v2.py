"""Fresh, auditable Responses sessions shared by fixed B and autonomous A0."""
import json
from copy import deepcopy
import hashlib
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import tiktoken

from .budget import BudgetError, check_request, input_cost_ceiling, reservation
from .response_input import to_response_input


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def wire_dumps(value):
    """Compact JSON for model-bound content and request-size estimates."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_json(path, value):
    Path(path).write_text(dumps(value) + "\n", encoding="utf-8")


class RunV2:
    def __init__(self, config, live=False, base_directory=None, client=None):
        self.config = dict(config)
        self.live = live
        self.client = client
        self.start = time.monotonic()
        self.phase = "CREATED"
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{config['condition']}_" + uuid.uuid4().hex[:8]
        self.directory = Path(base_directory) / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.encoder = tiktoken.get_encoding("o200k_base")
        self.model_calls = self.tool_calls = self.input_tokens = self.output_tokens = self.repairs = 0
        self.cost_ceiling_usd = self.estimated_usd = 0.0
        self.unknown_input_tokens_reserved = self.unknown_output_tokens_reserved = 0
        self.unknown_cost_ceiling_usd = 0.0
        self.unknown_usage_attempts = []
        self.transient_retries = 0
        self.usage_unknown = False
        self.returned_models = []
        self.requests = []
        self.escalations = []
        self.observation_guard = None
        self.final_input_estimate = 0
        write_json(self.directory / "config.json", self.config)
        write_json(self.directory / "environment.json", {"python": sys.version, "packages": {
            name: version(name) for name in ("openai", "httpx", "jsonschema", "tiktoken", "PyMuPDF", "python-dotenv")}})
        self.log("run_created", {"mode": "LIVE" if live else "PREFLIGHT", "condition": config["condition"],
                                 "started_at_utc": datetime.now(timezone.utc).isoformat()})

    def log(self, event, data):
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"elapsed_seconds": round(time.monotonic() - self.start, 3),
                                     "event": event, "phase": self.phase, **data}, ensure_ascii=False) + "\n")

    def transition(self, phase, **reason):
        previous = self.phase
        self.phase = phase
        self.log("state_transition", {"from": previous, "to": phase, **reason})

    def remaining_time(self):
        return self.config["wall_seconds_max"] - (time.monotonic() - self.start)

    def check_time(self):
        if self.remaining_time() <= 0:
            raise BudgetError("WALL_TIME_LIMIT")

    def estimate(self, payload):
        return len(self.encoder.encode(wire_dumps(payload))) + 800

    def reserve_observation(self, result):
        if self.observation_guard:
            self.observation_guard(result)

    def tool(self, name, arguments, callback, reserved_calls=0, actor=None, call_id=None):
        self.check_time()
        if self.tool_calls + 1 + reserved_calls > self.config["max_tool_calls"]:
            raise BudgetError("TOOL_CALL_RESERVATION")
        self.tool_calls += 1
        actor = actor or ("model" if self.config["condition"] == "A0" else "program_fixed")
        call_id = call_id or f"program_{self.tool_calls:03d}"
        try:
            result = callback()
        except Exception as exc:
            self.log("tool_call", {"tool": name, "actor": actor, "call_id": call_id,
                                  "arguments": arguments, "error_type": type(exc).__name__, "error": str(exc),
                                  "tool_calls": self.tool_calls})
            raise
        self.log("tool_call", {"tool": name, "actor": actor, "call_id": call_id,
                              "arguments": arguments, "result": result, "tool_calls": self.tool_calls})
        return result

    def request(self, stage, request, phase, final_input_estimate=0):
        if phase == "EXPLORING":
            self.final_input_estimate = final_input_estimate
        retry_limit = self.config.get("max_transient_api_retries", 0)
        if type(retry_limit) is not int or retry_limit not in (0, 1):
            raise RuntimeError("INVALID_TRANSIENT_RETRY_LIMIT")
        frozen_request = deepcopy(request)
        estimate = self.estimate(frozen_request)
        fingerprint = hashlib.sha256(wire_dumps(frozen_request).encode("utf-8")).hexdigest()
        logical_id = f"{self.run_id}:{self.model_calls + 1:02d}:{stage}"
        for attempt in range(retry_limit + 1):
            try:
                audit = check_request(self, estimate, frozen_request["max_output_tokens"], phase, final_input_estimate)
            except BudgetError as exc:
                if attempt:
                    self.log("transient_retry_blocked", {"stage": stage, "logical_request_id": logical_id,
                             "retry_attempt": attempt, "reason": str(exc), "usage_unknown": True})
                raise
            self.log("budget_reservation", {"stage": stage, "retry_attempt": attempt, **audit})
            reserve = reservation(self.config, phase, self.repairs, final_input_estimate)
            timeout = min(180.0, self.remaining_time() - reserve.seconds)
            if timeout <= 0:
                raise BudgetError("TIME_RESERVATION")
            self.model_calls += 1
            self.transient_retries += int(attempt > 0)
            stem = f"{self.model_calls:02d}_{stage}"
            write_json(self.directory / f"{stem}_request.json", frozen_request)
            self.log("model_call_started", {"stage": stage, "input_tokens_estimated": estimate,
                     "estimator": "o200k_base compact JSON + 800; estimate, not guarantee",
                     "max_output_tokens": frozen_request["max_output_tokens"], "retry_attempt": attempt,
                     "logical_request_id": logical_id, "request_sha256": fingerprint})
            try:
                response = self.client.responses.create(**deepcopy(frozen_request), timeout=timeout)
                break
            except Exception as exc:
                self._reserve_unknown_usage(stage, estimate, frozen_request["max_output_tokens"])
                code = getattr(exc, "code", None)
                safe_code = code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code) else None
                param = getattr(exc, "param", None)
                safe_param = param if isinstance(param, str) and re.fullmatch(r"[A-Za-z0-9_.\[\]-]{1,160}", param) else None
                status = getattr(exc, "status_code", None)
                eligible = status in {500, 502, 503, 504} and safe_code not in {"insufficient_quota", "rate_limit_exceeded"}
                error = {"stage": stage, "error_type": type(exc).__name__, "http_status": status,
                         "api_error_code": safe_code, "api_error_param": safe_param, "usage_unknown": True,
                         "retry_attempt": attempt, "logical_request_id": logical_id,
                         "request_sha256": fingerprint, "retry_eligible": eligible}
                write_json(self.directory / f"{stem}_error.json", error)
                self.log("model_call_failed", error)
                if not eligible or attempt >= retry_limit:
                    raise RuntimeError("API_ERROR:" + type(exc).__name__) from None
                self.log("transient_retry_planned", {"stage": stage, "logical_request_id": logical_id,
                         "next_retry_attempt": attempt + 1, "same_request_sha256": fingerprint,
                         "unknown_usage_reservation_retained": True})
        raw = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
        write_json(self.directory / f"{stem}_response.json", raw)
        self.returned_models.append(raw.get("model"))
        usage = raw.get("usage")
        if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
            self._reserve_unknown_usage(stage, estimate, frozen_request["max_output_tokens"])
            self.log("model_usage_missing", {"stage": stage, "usage_unknown": True})
            raise RuntimeError("USAGE_MISSING")
        self.input_tokens += usage["input_tokens"]
        self.output_tokens += usage["output_tokens"]
        self.estimated_usd = (self.input_tokens * self.config["price_input_per_million_usd"] +
                              self.output_tokens * self.config["price_output_per_million_usd"]) / 1e6
        self.cost_ceiling_usd = input_cost_ceiling(self.config, self.input_tokens) + self.output_tokens * self.config["price_output_per_million_usd"] / 1e6
        self.log("model_call_completed", {"stage": stage, "response_id": raw.get("id"),
                 "returned_model": raw.get("model"), "status": raw.get("status"), "usage": usage})
        self.check_time()
        if self.input_tokens > self.config["input_tokens_target_max"] or self.output_tokens > self.config["output_tokens_max"]:
            raise BudgetError("ACTUAL_TOKEN_LIMIT_EXCEEDED")
        if self.cost_ceiling_usd > self.config["max_run_usd"]:
            raise BudgetError("ACTUAL_COST_CEILING_EXCEEDED")
        if (self.input_tokens + self.unknown_input_tokens_reserved > self.config["input_tokens_target_max"] or
                self.output_tokens + self.unknown_output_tokens_reserved > self.config["output_tokens_max"] or
                self.cost_ceiling_usd + self.unknown_cost_ceiling_usd > self.config["max_run_usd"]):
            raise BudgetError("UNKNOWN_USAGE_RESERVATION_EXCEEDED")
        for item in raw.get("output", []):
            if item.get("type") == "refusal" or any(c.get("type") == "refusal" for c in (item.get("content") or [])):
                raise RuntimeError("MODEL_REFUSAL")
        if raw.get("status") != "completed":
            raise RuntimeError("MODEL_INCOMPLETE:" + str((raw.get("incomplete_details") or {}).get("reason", raw.get("status"))))
        return raw

    def _reserve_unknown_usage(self, stage, estimated_input, max_output):
        """Unknown is not zero: retain a separate conservative estimate hold."""
        self.usage_unknown = True
        ceiling = input_cost_ceiling(self.config, estimated_input) + max_output * self.config["price_output_per_million_usd"] / 1e6
        self.unknown_input_tokens_reserved += estimated_input
        self.unknown_output_tokens_reserved += max_output
        self.unknown_cost_ceiling_usd += ceiling
        record = {"model_call": self.model_calls, "stage": stage, "input_tokens_estimated": estimated_input,
                  "output_tokens_max": max_output, "cost_ceiling_usd": ceiling,
                  "note": "Reservation from estimated input and maximum output; unknown actual usage remains unknown."}
        self.unknown_usage_attempts.append(record)
        self.log("unknown_usage_reserved", record)

    def base_request(self, history, max_output):
        return {"model": self.config["model"], "store": False, "service_tier": "default",
                "reasoning": {"effort": self.config["reasoning_effort"]}, "input": to_response_input(history),
                "max_output_tokens": max_output}

    def finish(self, status, **extra):
        self.transition(status)
        known_cost = round(self.estimated_usd, 6)
        summary = {"run_id": self.run_id, "condition": self.config["condition"],
                   "mode": "LIVE" if self.live else "PREFLIGHT", "case_id": self.config.get("case_id"),
                   "repeat": self.config.get("repeat", 1), "config_version": self.config["version"],
                   "contract_versions": ["extraction_v2", "review_v2"], "execution_status": status,
                   "model": self.config["model"], "returned_models": self.returned_models,
                   "model_calls": self.model_calls, "tool_calls": self.tool_calls,
                   "input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "format_repairs": self.repairs,
                   "elapsed_seconds": round(time.monotonic() - self.start, 3), "usage_unknown": self.usage_unknown,
                   "estimated_cost_usd_standard_uncached": None if self.usage_unknown else known_cost,
                   "known_usage_cost_usd_standard_uncached": known_cost,
                   "estimated_cost_krw_at_budget_fx": None if self.usage_unknown else round(known_cost * self.config["budget_fx_krw_per_usd"], 2),
                   "cost_ceiling_usd": round(self.cost_ceiling_usd, 6),
                   "transient_retries": self.transient_retries,
                   "unknown_usage_reservation": {"input_tokens_estimated": self.unknown_input_tokens_reserved,
                       "output_tokens_max": self.unknown_output_tokens_reserved,
                       "cost_ceiling_usd": round(self.unknown_cost_ceiling_usd, 6),
                       "attempts": self.unknown_usage_attempts},
                   "accounted_cost_ceiling_usd": round(self.cost_ceiling_usd + self.unknown_cost_ceiling_usd, 6),
                   "cost_note": "Usage estimate, not invoice; unknown usage is never counted as zero.", **extra}
        write_json(self.directory / "summary.json", summary)
        return summary
