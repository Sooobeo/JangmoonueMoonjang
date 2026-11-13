# Responses input adapter: diagnostic and first review

Status: PASS for offline validation; a real API compatibility probe is owned by the root agent and is not counted as completed here.

The sixth call in `runs/20261113T101439Z_A0_46ef2e9a` failed with `BadRequestError` / `unknown_parameter`. Its first reasoning item arrived in response 05. The raw SDK dump was appended to history without an input adapter, so request 06 included reasoning `content: []` and `status: null`. Earlier function calls also carried `namespace: null` and response status. The installed SDK is 2.33.0. Its reasoning input type permits an optional status enum, but not a null status. The old error record omitted `param`, so the precise server-rejected field cannot be established retrospectively from these artifacts alone.

`ipo_eval.response_input.to_response_input` builds detached input items at `RunV2.base_request`. It retains item order, IDs, encrypted reasoning, summaries, nonempty reasoning content, function arguments, tool outputs, message text and assistant phase. It omits function/reasoning output status, absent optional fields and empty reasoning content. Unknown item types or nonempty unknown fields fail explicitly. Raw response files and `context.json` retain the original output. The nullable-content refusal scan also accepts an SDK `content: null` without an unrelated Python error.

API failures now record `api_error_param` only if the value is a path of at most 160 characters drawn from ASCII letters, digits, underscore, dot, brackets and hyphen. Exception messages, bodies and credentials remain excluded; unknown usage remains unknown.

Validation:

- `python -m pytest tests/test_response_input_v2.py tests/test_runtime_v2.py tests/test_agent_loop_v2.py tests/test_d4_independent_review.py -q`: **33 passed in 8.44s**.
- The new mock transport rejects SDK-shaped optional replay metadata on every A0 follow-up, completes all seven calls, and checks raw/context preservation and exact encrypted-content/call-ID/argument replay.
- Additional cases preserve nonempty content and assistant phase, reject unsupported new content, handle null content, and verify safe/unsafe API error paths.
- The actual failed request was serialized offline. All 13 items and all semantic fields were retained, and the original file hash was unchanged. Field-level evidence is in `response_input_adapter_check.json`.

Official documentation confirms that stateless reasoning must be replayed with encrypted content and that original item order must be maintained: [Reasoning models](https://developers.openai.com/api/docs/guides/reasoning). The local SDK's `ResponseReasoningItemParam`, `ResponseFunctionToolCallParam` and `ResponseOutputMessageParam` supplied the input field contracts. The compatibility probe is still needed because local SDK annotations alone do not demonstrate server acceptance.

No execution-batch code or configuration was changed. No paid request was made by this reviewer.
