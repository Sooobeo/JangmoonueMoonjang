"""Audited synthetic API compatibility check; never a company answer."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from openai import OpenAI
from ipo_eval.runner import api_key
from ipo_eval.runtime_v2 import RunV2, write_json
from ipo_eval.schemas import obj
from ipo_eval.tool_gateway import ToolGateway

target = Path(__file__).with_suffix(".json")
if target.exists():
    raise SystemExit("Probe already recorded; no silent retry")
config = json.loads((ROOT / "config/B.json").read_text(encoding="utf-8"))
config.update(case_id="SYNTHETIC_SCHEMA_COMPATIBILITY", repeat=1)
run = RunV2(config, True, ROOT / "runs", OpenAI(api_key=api_key(), max_retries=0))
gateway = ToolGateway(run, SimpleNamespace(case={"allowed_doc_ids": []}, by_id={}))
schema = obj({"calculation_uses": gateway.review_schema()["properties"]["calculation_uses"]})
request = run.base_request([{"role": "user", "content":
    "Synthetic schema compatibility test only. Return one USE of calc_id SYN_C with stated_value 1, related_judgment_ids [J1], reason synthetic, replacement_id null and unresolved false. No company data or financial recommendation."}], 512)
request["text"] = {"format": {"type": "json_schema", "name": "calculation_use_compatibility", "strict": True, "schema": schema}}
write_json(target, {"status": "STARTED", "directory": str(run.directory), "purpose": "API schema acceptance only; no real case input or answer",
    "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (ROOT / "ipo_eval/tool_gateway.py", ROOT / "ipo_eval/schemas_v2.py", ROOT / "config/B.json")}})
try:
    raw = run.request("schema_compatibility", request, "PROBE")
    summary = run.finish("COMPATIBILITY_PROBE_COMPLETE", final_status=None, actual_model_answer=False,
        schema_api_accepted=True, response_generation_complete=True)
except RuntimeError as exc:
    accepted = str(exc).startswith("MODEL_INCOMPLETE:")
    summary = run.finish("COMPATIBILITY_PROBE_ACCEPTED_INCOMPLETE" if accepted else "FAILED", final_status=None,
        actual_model_answer=False, schema_api_accepted=accepted, response_generation_complete=False, failure_reason=str(exc))
result = json.loads(target.read_text(encoding="utf-8"))
result.update(status="COMPLETE", summary=summary)
write_json(target, result)
print(json.dumps({"run_id": run.run_id, "status": summary["execution_status"], "schema_api_accepted": summary["schema_api_accepted"],
    "input_tokens": summary["input_tokens"], "output_tokens": summary["output_tokens"], "usage_unknown": summary["usage_unknown"]}))
raise SystemExit(0 if summary["schema_api_accepted"] else 1)
