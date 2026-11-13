"""Shared B/A0 accounting. Reservations are checked before any model request."""
from dataclasses import dataclass


class BudgetError(RuntimeError):
    pass


@dataclass(frozen=True)
class Reservation:
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    seconds: float = 0


def reservation(config, phase, repairs, final_input_estimate=0):
    repair_available = repairs < config["max_format_repairs"]
    repair_input = config["format_repair_input_reserve"] if repair_available else 0
    repair_output = config["format_repair_output_max"] if repair_available else 0
    if phase in {"EXPLORING", "EXPLORATION_REPAIR"}:
        return Reservation(
            final_input_estimate + repair_input,
            config["review_output_max"] + repair_output,
            1 + int(repair_available), 3 + int(repair_available),
            config["finalization_seconds_reserve"] + (config["repair_seconds_reserve"] if repair_available else 0),
        )
    if phase == "FINALIZING" and repair_available:
        return Reservation(repair_input, repair_output, 1, 1, config["repair_seconds_reserve"])
    return Reservation()


def input_cost_ceiling(config, tokens):
    # Cache writes can cost 1.25x uncached input. Never assume a cache hit.
    return tokens * config["price_input_per_million_usd"] * 1.25 / 1e6


def check_request(run, estimated_input, max_output, phase, final_input_estimate=0):
    c = run.config
    r = reservation(c, phase, run.repairs, final_input_estimate)
    if phase in {"REPAIR", "EXPLORATION_REPAIR"} and estimated_input > c["format_repair_input_reserve"]:
        raise BudgetError("REPAIR_INPUT_LIMIT")
    if run.remaining_time() <= r.seconds:
        raise BudgetError("TIME_RESERVATION")
    if run.model_calls + 1 + r.model_calls > c["max_model_calls"]:
        raise BudgetError("MODEL_CALL_RESERVATION")
    current_tools = 3 if phase == "FINALIZING" else 1
    if run.tool_calls + r.tool_calls + current_tools > c["max_tool_calls"]:
        raise BudgetError("TOOL_CALL_RESERVATION")
    unknown_input = getattr(run, "unknown_input_tokens_reserved", 0)
    unknown_output = getattr(run, "unknown_output_tokens_reserved", 0)
    unknown_cost = getattr(run, "unknown_cost_ceiling_usd", 0)
    if run.input_tokens + unknown_input + estimated_input + r.input_tokens > c["input_tokens_target_max"]:
        raise BudgetError("INPUT_RESERVATION")
    if max_output <= 0 or run.output_tokens + unknown_output + max_output + r.output_tokens > c["output_tokens_max"]:
        raise BudgetError("OUTPUT_RESERVATION")
    ceiling = run.cost_ceiling_usd + unknown_cost + input_cost_ceiling(c, estimated_input + r.input_tokens)
    ceiling += (max_output + r.output_tokens) * c["price_output_per_million_usd"] / 1e6
    if ceiling > c["max_run_usd"]:
        raise BudgetError("COST_RESERVATION")
    return {"input_estimated": estimated_input, "max_output": max_output,
            "reserved": r.__dict__, "request_and_reserved_cost_ceiling_usd": ceiling,
            "unknown_usage_reserved": {"input_tokens_estimated": unknown_input, "output_tokens_max": unknown_output,
                                       "cost_ceiling_usd": unknown_cost}}


def exploration_output_limit(run):
    c = run.config
    r = reservation(c, "EXPLORING", run.repairs)
    return min(c["exploration_output_max"], c["output_tokens_max"] - run.output_tokens -
               getattr(run, "unknown_output_tokens_reserved", 0) - r.output_tokens)
