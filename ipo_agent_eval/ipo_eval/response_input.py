"""Serialize the replayable subset of Responses output without changing its audit copy.

SDK ``model_dump`` includes unset output metadata. It is an audit representation,
not a wire-input serializer. Keep item order, identifiers, reasoning, arguments,
and message content; omit output status and absent optional fields on replay.
"""
from copy import deepcopy


_FIELDS = {
    "reasoning": ("type", "id", "summary", "encrypted_content", "content"),
    "function_call": ("type", "id", "call_id", "name", "arguments", "namespace"),
    "function_call_output": ("type", "id", "call_id", "output"),
    "message": ("type", "id", "role", "content", "status", "phase"),
}


def to_response_input(history):
    """Return detached API input items; never mutate raw responses or context.

    This project only requests text and custom function calls. Unknown item types
    fail explicitly instead of dropping an item and breaking reasoning continuity.
    Nonempty reasoning content and assistant phase are preserved when supplied.
    """
    result = []
    for item in history:
        if not isinstance(item, dict):
            raise RuntimeError("UNSUPPORTED_RESPONSE_INPUT_ITEM")
        kind = item.get("type", "message")
        if kind not in _FIELDS:
            raise RuntimeError("UNSUPPORTED_RESPONSE_INPUT_TYPE")
        allowed = set(_FIELDS[kind]) | {"status"}
        if any(key not in allowed and value is not None for key, value in item.items()):
            raise RuntimeError("UNSUPPORTED_RESPONSE_INPUT_FIELD")
        wire = {key: deepcopy(item[key]) for key in _FIELDS[kind]
                if key in item and item[key] is not None}
        # SDK defaults may add content=[] to reasoning, although no reasoning
        # text was returned. Encrypted reasoning and summaries remain untouched.
        if kind == "reasoning" and not wire.get("content"):
            wire.pop("content", None)
        result.append(wire)
    return result
