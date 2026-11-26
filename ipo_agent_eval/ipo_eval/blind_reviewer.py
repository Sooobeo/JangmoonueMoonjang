"""A1 blind reviewer B. Run via python -m ipo_eval.blind_reviewer --help.

The input is one self-contained, pre-masked UTF-8 JSON packet. No filenames,
retrieval functions, prior responses, labels or case metadata enter the prompt.
The externally frozen digest identifies the reviewed bytes. People still need
to check their provenance, masking, evidence coverage and presentation.
"""
import argparse
import hashlib
import json
import re
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from .agent_loop import output_json
from .runtime_v2 import RunV2, wire_dumps, write_json
from .schemas import S, arr, obj

ROOT = Path(__file__).resolve().parents[1]
VERSION = "a1-blind-v1"
TEXT = {"type": "string", "pattern": r"\S"}
EVIDENCE = obj({"evidence_id": {"type": "string", "pattern": r"^E[0-9]+$"}, "text": TEXT})
EVIDENCE_LIST = arr(EVIDENCE)
CANDIDATE = obj({"candidate_id": {"type": "string", "pattern": r"^C[0-9]+$"},
                 "business": EVIDENCE_LIST, "financials": EVIDENCE_LIST, "multiples": EVIDENCE_LIST})
PACKET = obj({"issuer_evidence": {**EVIDENCE_LIST, "minItems": 1},
              "candidates": {**arr(CANDIDATE), "minItems": 1}})
PROPOSAL = obj({"proposal": S, "reason": S, "evidence_ids": arr(S)})
DECISION = obj({"candidate_id": S, "decision": {"type": "string", "enum": ["INCLUDE", "REVIEW", "EXCLUDE"]},
                "reason": S, "evidence_ids": arr(S)})
REVIEW = obj({"status": {"type": "string", "enum": ["READY", "PENDING_INFO"]},
              "earnings": PROPOSAL, "aggregation": PROPOSAL, "candidates": arr(DECISION)})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def load_packet(path, expected):
    data = Path(path).read_bytes()
    if sha(data) != expected:
        raise ValueError("Packet does not match the pinned SHA-256.")
    packet = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object)
    Draft202012Validator(PACKET).validate(packet)
    candidate_ids = [row["candidate_id"] for row in packet["candidates"]]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("Duplicate candidate ID.")
    excerpts = list(packet["issuer_evidence"])
    for row in packet["candidates"]:
        for key in ("business", "financials", "multiples"):
            excerpts.extend(row[key])
    ids = [row["evidence_id"] for row in excerpts]
    if len(set(ids)) != len(ids):
        raise ValueError("Evidence IDs must be unique throughout the packet.")
    if any(re.search(r"https?://|file://", row["text"], re.IGNORECASE) for row in excerpts):
        raise ValueError("Mask destination URLs in the evidence text before freezing the packet.")
    return packet, set(ids)


def ordered_packet(packet, variant, seed):
    candidates = sorted(packet["candidates"], key=lambda row: row["candidate_id"])
    if variant == "B2":
        if len(candidates) < 2:
            raise ValueError("B2 needs at least two candidates to change their order.")
        shuffled = sorted(candidates, key=lambda row: sha(f"{seed}:{row['candidate_id']}".encode()))
        candidates = shuffled if shuffled != candidates else candidates[1:] + candidates[:1]
    return {**packet, "candidates": candidates}


def read_config(path):
    source = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    keys = ("model", "reasoning_effort", "max_model_calls", "max_tool_calls", "input_tokens_target_max",
            "output_tokens_max", "wall_seconds_max", "review_output_max", "max_run_usd",
            "budget_fx_krw_per_usd", "price_input_per_million_usd", "price_output_per_million_usd")
    config = {key: source[key] for key in keys}
    config.update(condition="A1_BLIND_B", version=VERSION, max_format_repairs=0,
                  max_transient_api_retries=1, max_model_calls=min(2, config["max_model_calls"]))
    return config


def make_request(config, packet, prompt):
    return {"model": config["model"], "reasoning": {"effort": config["reasoning_effort"]},
            "store": False, "service_tier": "default", "max_output_tokens": config["review_output_max"],
            "instructions": prompt, "input": wire_dumps(packet),
            "text": {"format": {"type": "json_schema", "name": "blind_review", "strict": True, "schema": REVIEW}}}


def audit_answer(answer, candidates, evidence):
    Draft202012Validator(REVIEW).validate(answer)
    counts = Counter(row["candidate_id"] for row in answer["candidates"])
    # Unsupported and omitted judgments remain scorable observations.
    judgments = [answer["earnings"], answer["aggregation"], *answer["candidates"]]
    return {"missing_candidates": sorted(candidates - counts.keys()),
            "unknown_candidates": sorted(counts.keys() - candidates),
            "duplicate_candidates": sorted(cid for cid, count in counts.items() if count > 1),
            "unknown_evidence_ids": sorted({eid for row in judgments for eid in row["evidence_ids"]} - evidence),
            "candidates_without_citations": [r["candidate_id"] for r in answer["candidates"] if not r["evidence_ids"]]}


def get_answer(run, request, candidates, evidence):
    """Allow one identical-input retry across invalid contracts and transport failures."""
    while True:
        raw = run.request("blind_review", request, "BLIND_REVIEW")
        try:
            answer = output_json(raw)
            audit = audit_answer(answer, candidates, evidence)
        except (RuntimeError, ValidationError) as exc:
            run.log("invalid_blind_submission", {"error_type": type(exc).__name__, "response_id": raw.get("id")})
            if run.model_calls < run.config["max_model_calls"]:
                continue
            raise
        return raw, answer, audit


def mock_answer(ids):
    pending = {"reason": "모의 응답", "evidence_ids": []}
    return {"status": "PENDING_INFO", "earnings": {"proposal": "", **pending},
            "aggregation": {"proposal": "", **pending},
            "candidates": [{"candidate_id": cid, "decision": "REVIEW", **pending} for cid in ids]}


def check_baseline(directory, freeze, mode, expected_request):
    path = Path(directory)
    prior = json.loads((path / "blind_input.json").read_text(encoding="utf-8"))
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    recorded_request = json.loads((path / "blind_request.json").read_text(encoding="utf-8"))
    required = {"live": "SUBMITTED", "mock": "MOCK_COMPLETE", "preflight": "PREFLIGHT_COMPLETE"}[mode]
    if (prior["variant"] != "B1" or prior["freeze"] != freeze or summary["execution_status"] != required
            or summary["run_id"] != prior["run_id"] or summary["mode"] != mode.upper()
            or recorded_request != expected_request or prior["request_sha256"] != sha(wire_dumps(expected_request).encode())):
        raise ValueError("B2 must reference B1 with matching mode, packet, seed, case, prompt and configuration.")
    return prior["run_id"]


def execute(packet_path, expected_sha256, case_id, seed, *, variant="B1", baseline=None, mode="preflight",
            output=ROOT / "runs", config_path=ROOT / "config/B.json", client=None):
    if mode not in {"preflight", "mock", "live"} or variant not in {"B1", "B2"}:
        raise ValueError("Invalid mode or variant.")
    if not case_id.strip() or type(seed) is not int or (variant == "B2") != bool(baseline):
        raise ValueError("Supply case ID, integer seed, and a baseline directory for B2 only.")
    packet, evidence = load_packet(packet_path, expected_sha256)
    ordered = ordered_packet(packet, variant, seed)
    ids = [row["candidate_id"] for row in ordered["candidates"]]
    config = read_config(config_path)
    prompt = (ROOT / "prompts/blind_reviewer.md").read_text(encoding="utf-8")
    request = make_request(config, ordered, prompt)
    freeze = {"case_id": case_id, "packet_sha256": expected_sha256, "seed": seed,
              "config_sha256": sha(wire_dumps(config).encode()), "prompt_sha256": sha(prompt.encode()),
              "contract_sha256": sha(wire_dumps([PACKET, REVIEW]).encode()), "version": VERSION}
    baseline_id = None
    if baseline:
        baseline_request = make_request(config, ordered_packet(packet, "B1", seed), prompt)
        baseline_id = check_baseline(baseline, freeze, mode, baseline_request)
    now = datetime.now(UTC)
    if mode == "live":
        run = RunV2({**config, "case_id": case_id}, live=True, base_directory=output, client=client)
        directory, run_id = run.directory, run.run_id
    else:
        run_id = f"{now:%Y%m%dT%H%M%SZ}_A1_BLIND_{variant}_{mode}_{uuid.uuid4().hex[:10]}"
        directory = Path(output) / run_id
        directory.mkdir(parents=True, exist_ok=False)
    metadata = {"run_id": run_id, "variant": variant, "freeze": freeze, "candidate_order": ids,
                "baseline_run_id": baseline_id, "request_sha256": sha(wire_dumps(request).encode()),
                "created_at_utc": now.isoformat(), "mode": mode.upper()}
    write_json(directory / "blind_input.json", metadata)
    write_json(directory / "blind_request.json", request)
    common = {"variant": variant, "mode": mode.upper(), "baseline_run_id": baseline_id,
              "contract_versions": [VERSION], "case_id": case_id}
    if mode == "preflight":
        summary = {"run_id": run_id, **common, "execution_status": "PREFLIGHT_COMPLETE",
                   "model_calls": 0, "actual_model_answer": False}
    elif mode == "mock":
        answer = mock_answer(ids)
        audit = audit_answer(answer, set(ids), evidence)
        write_json(directory / "mock_review.json", answer)
        summary = {"run_id": run_id, **common, "execution_status": "MOCK_COMPLETE",
                   "model_calls": 0, "actual_model_answer": False, "citation_and_coverage_audit": audit}
    else:
        from openai import OpenAI, OpenAIError

        from .runner import api_key

        try:
            if run.client is None:
                key = api_key()
                if not key:
                    return directory, run.finish("NOT_STARTED_MISSING_API_KEY", actual_model_answer=False, **common)
                run.client = OpenAI(api_key=key, base_url="https://api.openai.com/v1", max_retries=0)
            raw, answer, audit = get_answer(run, request, set(ids), evidence)
            write_json(directory / "blind_review.json", answer)
            summary = run.finish("SUBMITTED", actual_model_answer=True, answer_status=answer["status"],
                                 citation_and_coverage_audit=audit, response_id=raw.get("id"), **common)
        except (RuntimeError, ValueError, ValidationError, OpenAIError) as exc:
            # The shared transport already logs safe error codes, never credentials.
            summary = run.finish("FAILED", error_type=type(exc).__name__,
                                 actual_model_answer=bool(run.returned_models), **common)
        return directory, summary
    write_json(directory / "summary.json", summary)
    return directory, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True, help="Prepared, masked, self-contained JSON")
    parser.add_argument("--packet-sha256", required=True, help="SHA-256 frozen before running")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--seed", type=int, required=True, help="Preassigned B2 order seed, also recorded for B1")
    parser.add_argument("--variant", choices=("B1", "B2"), default="B1")
    parser.add_argument("--baseline", type=Path, help="Matching B1 run directory (B2 only)")
    parser.add_argument("--output-root", type=Path, default=ROOT / "runs")
    parser.add_argument("--config", type=Path, default=ROOT / "config/B.json", help="Model, price and budget config")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live", dest="mode", action="store_const", const="live")
    group.add_argument("--mock", dest="mode", action="store_const", const="mock")
    args = parser.parse_args()
    path, summary = execute(args.packet, args.packet_sha256, args.case_id, args.seed, variant=args.variant,
                            baseline=args.baseline, mode=args.mode or "preflight", output=args.output_root,
                            config_path=args.config)
    print(f"{summary['execution_status']} {path}")
    return int(summary["execution_status"] in {"FAILED", "NOT_STARTED_MISSING_API_KEY"})


if __name__ == "__main__":
    raise SystemExit(main())
