"""B pilot: fixed retrieval -> extraction -> calculation -> J1-J4 -> submission."""
import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
import uuid
from importlib.metadata import version
from datetime import datetime, timezone
from pathlib import Path

import tiktoken
from dotenv import dotenv_values
from openai import OpenAI

from .calculations import calculate, sensitivity
from .cases import DEFAULT_CASE_ID, resolve_case
from .corpus import Corpus
from .schemas import EXTRACTION, REVIEW, ID_REPAIRS, MEMO_REPAIR
from .id_repairs import build_id_repair_targets, apply_id_repairs
from .validation import facts_in, final_status, validate_extraction, validate_review

ROOT = Path(__file__).resolve().parents[1]


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def write_json(path, value):
    path.write_text(dumps(value) + "\n", encoding="utf-8")


def api_key():
    """Read explicitly configured API credentials, never Codex account caches."""
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if value:
        return value
    for path in (ROOT / ".env", ROOT.parent / ".env"):
        if path.is_file():
            value = dotenv_values(path, encoding="utf-8-sig", interpolate=False).get("OPENAI_API_KEY")
            if isinstance(value, str) and value.strip():
                return value.strip()
    if sys.platform == "win32":
        import winreg
        for hive, path in [(winreg.HKEY_CURRENT_USER, "Environment"),
                           (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")]:
            try:
                with winreg.OpenKey(hive, path) as key:
                    value, _ = winreg.QueryValueEx(key, "OPENAI_API_KEY")
                if isinstance(value, str) and value.strip():
                    return value.strip()
            except OSError:
                pass
    return None


class BudgetError(RuntimeError):
    pass


class Run:
    def __init__(self, config, live, directory=None, client=None, base_directory=None):
        self.config = config
        self.live = live
        self.start = time.monotonic()
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_B_" + uuid.uuid4().hex[:8]
        self.directory = Path(directory) if directory else Path(base_directory or ROOT / "runs") / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.model_calls = self.tool_calls = self.input_tokens = self.output_tokens = self.repairs = 0
        self.estimated_usd = 0.0
        self.client = client
        self.encoder = tiktoken.get_encoding("o200k_base")
        self.requests = []
        self.escalations = []
        write_json(self.directory / "config.json", config)
        write_json(self.directory / "environment.json", {"python": sys.version, "packages": {name: version(name) for name in ("openai", "httpx", "jsonschema", "tiktoken", "PyMuPDF", "python-dotenv")}})
        self.log("run_created", {"mode": "LIVE" if live else "PREFLIGHT", "started_at_utc": datetime.now(timezone.utc).isoformat()})

    def log(self, event, data):
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"elapsed_seconds": round(time.monotonic() - self.start, 3), "event": event, **data}, ensure_ascii=False) + "\n")

    def remaining_time(self):
        return self.config["wall_seconds_max"] - (time.monotonic() - self.start)

    def check_time(self):
        if self.remaining_time() <= 0:
            raise BudgetError("Wall-clock limit reached")

    def tool(self, name, arguments, callback, reserved_calls=0):
        self.check_time()
        if self.tool_calls + 1 + reserved_calls > self.config["max_tool_calls"]:
            raise BudgetError("Tool call limit reached; final submission remains reserved")
        self.tool_calls += 1
        result = callback()
        self.log("tool_call", {"tool": name, "actor": "program_fixed", "arguments": arguments, "result": result})
        return result

    def call(self, stage, system, payload, schema, max_output):
        self.check_time()
        request = {"model": self.config["model"], "store": False, "service_tier": "default",
                   "reasoning": {"effort": self.config["reasoning_effort"]},
                   "input": [{"role": "system", "content": system}, {"role": "user", "content": dumps(payload)}],
                   "text": {"format": {"type": "json_schema", "name": stage, "strict": True, "schema": schema}},
                   "max_output_tokens": max_output}
        estimate = len(self.encoder.encode(dumps(request))) + 800
        if self.model_calls >= self.config["max_model_calls"]:
            raise BudgetError("Model call limit reached")
        reserve = self.config["format_repair_input_reserve"] if self.repairs == 0 and not stage.endswith("_format_repair") else 0
        if self.input_tokens + estimate + reserve > self.config["input_tokens_target_max"]:
            raise BudgetError("Estimated cumulative input exceeds target")
        if self.output_tokens + max_output > self.config["output_tokens_max"]:
            raise BudgetError("Output token budget would be exceeded")
        ceiling_cost = estimate * self.config["price_input_per_million_usd"] * 1.25 / 1e6 + max_output * self.config["price_output_per_million_usd"] / 1e6
        if self.estimated_usd + ceiling_cost > self.config["max_run_usd"]:
            raise BudgetError("Estimated per-run cost ceiling would be exceeded")
        self.model_calls += 1
        stem = f"{self.model_calls:02d}_{stage}"
        write_json(self.directory / (stem + "_request.json"), request)
        self.log("model_call_started", {"stage": stage, "input_tokens_estimated": estimate, "estimator": "o200k_base + 800; not a model-specific guarantee", "max_output_tokens": max_output})
        try:
            response = self.client.responses.create(**request, timeout=max(1.0, min(180.0, self.remaining_time())))
        except Exception as exc:
            # Never serialize SDK objects/headers that might contain a credential.
            code = getattr(exc, "code", None)
            safe_code = code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code) else None
            self.log("model_call_failed", {"stage": stage, "error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None), "api_error_code": safe_code, "usage_unknown": True})
            raise RuntimeError("API request failed: " + type(exc).__name__) from None
        raw = response.model_dump(mode="json")
        write_json(self.directory / (stem + "_response.json"), raw)
        usage = raw.get("usage") or {}
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        self.estimated_usd = (self.input_tokens * self.config["price_input_per_million_usd"] + self.output_tokens * self.config["price_output_per_million_usd"]) / 1e6
        self.log("model_call_completed", {"stage": stage, "response_id": raw.get("id"), "returned_model": raw.get("model"), "status": raw.get("status"), "usage": usage})
        if raw.get("status") != "completed":
            raise RuntimeError("Model response incomplete or refused; original response saved")
        if not usage:
            raise RuntimeError("API response lacks usage; cannot account for experiment budget")
        self.check_time()
        if self.output_tokens > self.config["output_tokens_max"] or self.input_tokens > self.config["input_tokens_target_max"]:
            raise BudgetError("Reported usage exceeded configured token limit")
        try:
            return json.loads(response.output_text), response.output_text
        except (ValueError, TypeError):
            return None, response.output_text

    def structured(self, stage, system, payload, schema, max_output, validator):
        value, raw_text = self.call(stage, system, payload, schema, max_output)
        errors = validator(value) if value is not None else ["Response was not a JSON object"]
        if not errors:
            return value
        self.log("format_validation", {"stage": stage, "errors": errors, "checks_factual_correctness": False})
        if self.repairs >= self.config["max_format_repairs"]:
            raise RuntimeError("Shared format repair allowance exhausted")
        self.repairs += 1
        if stage == "review" and isinstance(value, dict) and isinstance(value.get("memo"), list) and len(value["memo"]) > 5:
            probe = copy.deepcopy(value)
            probe["memo"] = value["memo"][:5]
            if not validator(probe):
                repair = {"memo": value["memo"], "instruction": "기존 메모의 겹치는 내용을 묶어 다섯 항목 이하로 다시 정리하라. 기존 사실과 결론만 사용하고 새로운 주장이나 판단을 추가하지 말라. 본문과 다른 필드는 프로그램이 그대로 보존한다."}
                replacement, _ = self.call(stage + "_format_repair", system, repair, MEMO_REPAIR, self.config["format_repair_output_max"])
                if replacement is None or not isinstance(replacement.get("memo"), list):
                    raise RuntimeError("Memo repair did not return a list")
                value = copy.deepcopy(value)
                value["memo"] = replacement["memo"]
                errors = validator(value)
                self.log("format_repair_result", {"stage": stage, "repair_kind": "memo_count_only", "errors": errors})
                if errors:
                    raise RuntimeError("Invalid structure after one shared format repair")
                return value
        if stage == "review" and value is not None and all(error.startswith("Evidence references unknown claim:") for error in errors):
            targets = build_id_repair_targets(value, payload["extraction"])
            repair = {"previous_output": value, "targets": targets,
                      "instruction": "각 targets의 path를 정확히 한 번씩 사용하고 allowed_ids 중 하나를 replacement로 고르라. 출처의 claim_id 연결만 고치는 공통 형식수정이다. 전체 답변을 다시 쓰지 말라. 숫자, 문장, 문서·페이지·위치, 선언된 주장 ID, 판단·요청 상태는 변경할 수 없다. 새 근거나 정답 피드백은 없다."}
            patch, _ = self.call(stage + "_format_repair", system, repair, ID_REPAIRS, self.config["format_repair_output_max"])
            if patch is None or not isinstance(patch.get("repairs"), list):
                raise RuntimeError("Evidence ID repair did not return a patch list")
            value = apply_id_repairs(value, targets, patch["repairs"])
            errors = validator(value)
            self.log("format_repair_result", {"stage": stage, "repair_kind": "evidence_claim_ids_only", "patches": patch["repairs"], "errors": errors})
            if errors:
                raise RuntimeError("Invalid structure after one shared format repair")
            return value
        # A formatting repair cannot launch a new search or reread the whole corpus.
        repair = {"previous_output": raw_text, "structural_errors": errors,
                  "allowed_locations": [{k: source[k] for k in ("doc_id", "chunk_id", "page")} for source in payload.get("sources", [])],
                  "extracted_input_ids": [{"field": field, "claim_id": fact["claim_id"], "missing": fact["value"] is None}
                                          for field, fact in facts_in(payload["extraction"])] if "extraction" in payload else [],
                  "instruction": "형식, 필수 항목, ID 연결만 고쳐 전체 JSON을 한국어로 다시 반환하라. 기존 출력의 사실 내용은 보존하라. 주어진 위치 목록은 인용 형식을 확인하기 위한 것이며, 새로운 사실을 뒷받침하지 않는다. 추가 검색이나 정답 피드백은 없다."}
        value, _ = self.call(stage + "_format_repair", system, repair, schema, self.config["format_repair_output_max"])
        errors = validator(value) if value is not None else ["Repair was not JSON"]
        self.log("format_repair_result", {"stage": stage, "errors": errors})
        if errors:
            raise RuntimeError("Invalid structure after one shared format repair")
        return value

    def finish(self, status, **extra):
        summary = {"run_id": self.run_id, "condition": "B", "mode": "LIVE" if self.live else "PREFLIGHT",
                   "case_id": self.config.get("case_id"), "config_version": self.config["version"],
                   "execution_status": status, "model": self.config["model"], "model_calls": self.model_calls,
                   "tool_calls": self.tool_calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                   "format_repairs": self.repairs, "elapsed_seconds": round(time.monotonic() - self.start, 3),
                   "estimated_cost_usd_standard_uncached": round(self.estimated_usd, 6),
                   "estimated_cost_krw_at_budget_fx": round(self.estimated_usd * self.config["budget_fx_krw_per_usd"], 2),
                   "cost_note": "Usage-based estimate, not an invoice. Cache writes, taxes and FX can differ. Failed requests may have unreported usage.", **extra}
        write_json(self.directory / "summary.json", summary)
        return summary


def retrieve(run, corpus):
    all_chunks = {}
    for step in run.config["fixed_queries"]:
        args = {"case_id": corpus.case["case_id"], "query": step["query"], "filters": {"cutoff_status": "BEFORE"}, "top_k": run.config["search_top_k"]}
        found = run.tool("search_corpus", args, lambda args=args: corpus.search_corpus(**args), reserved_calls=2)
        read_args = {"chunk_ids": [h["chunk_id"] for h in found["hits"]], "neighbor_pages": run.config["read_neighbor_pages"]}
        pages = run.tool("read_source", read_args, lambda read_args=read_args: corpus.read_source(**read_args), reserved_calls=2)
        for chunk in pages["chunks"]:
            all_chunks[chunk["chunk_id"]] = chunk
        run.log("fixed_stage", {"stage": step["stage"], "physical_pages": [c["page"] for c in pages["chunks"]]})
    packet = {"metadata": corpus.public_metadata(), "manual": corpus.manual,
              "sources": sorted(all_chunks.values(), key=lambda c: (c["doc_id"], c["page"])), "truncated": False}
    write_json(run.directory / "source_packet.json", packet)
    return packet, all_chunks


def calculation_inputs(extraction):
    values = {key: fact["value"] for key, fact in extraction["values"].items()}
    values["peers"] = [{"name": p["name"], **{k: p[k]["value"] for k in ("per", "market_cap_million_krw", "earnings_million_krw")}} for p in extraction["peers"]]
    return values


def submission_calculations(extraction, calcs, scenarios, review):
    """Attach field-level provenance to every calculation in the common output."""
    all_facts = list(facts_in(extraction))
    rows = []
    items = calcs["calculations"] + [scenarios["baseline"]] + scenarios["scenarios"]
    for item in items:
        keys = set(item["inputs"])
        peer_index = None
        if item["id"].startswith("peer_recomputed_per_"):
            peer_index = int(item["id"].rsplit("_", 1)[1]) - 1
        sources = [{"field": field, **fact} for field, fact in all_facts
                   if field in keys or ("peers" in keys and field.startswith("peers["))
                   or (peer_index is not None and field.startswith(f"peers[{peer_index}]."))]
        source_fields = {source["field"] for source in sources}
        rows.append({"calc_id": item["id"], "label": item["label"], "formula": item["formula"],
                     "inputs": sources, "result": item["result"], "unit": item["unit"], "status": item["status"],
                     "precision_status": "PUBLIC_INPUT_RECALCULATION" if item["status"] == "OK" else "NOT_CALCULABLE",
                     "precision": item["precision"], "evidence": [ev for fact in sources for ev in fact["evidence"]],
                     "missing_reason": item["reason"],
                     "related_request_ids": [m["request_id"] for m in review["missing_inputs"] if m["field"] in source_fields or m["field"] == "peers" and "peers" in keys],
                     "assumption": item.get("assumption"), "excluded_peer": item.get("excluded_peer"),
                     "difference_krw": item.get("difference_krw"), "difference_percent": item.get("difference_percent")})
    return rows


def render_report(report):
    label = report.get("issuer_name") or report.get("case_id") or "IPO"
    lines = [f"# {label} B 검토 결과", "", "이 문서는 API가 제출한 검토 의견과 프로그램의 계산 결과를 옮긴 것이다. 정답 채점은 아직 하지 않았다.", "",
             f"- 실행 ID: {report['run_id']}", f"- 자료 마감: {report['cutoff_at']}", f"- 프로그램이 정한 상태: {report['final_status']}",
             f"- AI가 보고한 상태: {report['model_reported_status']}", "", "## 확인 범위", ""]
    lines += ["- " + item for item in report["scope"]["verification_limits"]]
    lines += ["", "## 핵심 메모", ""] + ["- " + item for item in report["memo"]]
    for j in report["judgments"]:
        lines += ["", f"## {j['domain']} · {j['disposition']}", "", j["conclusion"], ""]
        for fact in j["facts"]:
            refs = "; ".join(f"{e['doc_id']} PDF {e['page']}쪽 · {e['locator']}" for e in fact["evidence"])
            lines += [f"- {fact['text']} ({refs})"]
        for label, key in [("판단을 뒷받침하는 원문", "evidence"), ("반대 근거로 검토한 원문", "counter_evidence")]:
            if j[key]:
                lines += ["", label + ":", ""] + [f"- {e['doc_id']} PDF {e['page']}쪽 · {e['locator']} (주장 {e['claim_id']})" for e in j[key]]
        if j["unknowns"]:
            lines += ["", "아직 확인하지 못한 점:", ""] + ["- " + u for u in j["unknowns"]]
        lines += ["", "다음 행동: " + j["next_action"]]
    lines += ["", "## 추가 확인 요청", "", "```json", dumps({"requests": report["requests"], "escalations": report["escalations"]}), "```",
              "", "## 계산 기록", "", "```json", dumps(report["calculations"]), "```",
              "", "숫자의 단위·기간·원문 위치는 같은 폴더의 review.json 안 extracted_inputs에서 확인할 수 있다.", ""]
    return "\n".join(lines)


def execute(live=False, root=ROOT, case_id=DEFAULT_CASE_ID, condition=None, repeat=1):
    if condition is not None:
        from .runner_v2 import execute_v2
        return execute_v2(live=live, root=root, case_id=case_id, condition=condition, repeat=repeat)
    root = Path(root).resolve()
    legacy_config = root / "config" / "B_v1.json"
    config = json.loads((legacy_config if legacy_config.exists() else root / "config" / "B.json").read_text(encoding="utf-8"))
    config["case_id"] = case_id
    run = Run(config, live, base_directory=root / "runs")
    try:
        corpus_directory, registration = resolve_case(root, case_id)
        corpus = Corpus(corpus_directory, case_id)
        run.log("case_selected", {"registration": registration, "metadata": corpus.public_metadata()})
        write_json(run.directory / "case_selection.json", {"registration": registration, "metadata": corpus.public_metadata()})
        run.log("corpus_verified", {"documents": corpus.verify()})
        hashes = {}
        for folder in (root / "ipo_eval", root / "prompts", root / "config"):
            for file in sorted(folder.iterdir()):
                if file.is_file() and file.suffix in (".py", ".md", ".json"):
                    hashes[str(file.relative_to(root))] = hashlib.sha256(file.read_bytes()).hexdigest()
        for filename in ("chunks.jsonl", "documents.jsonl", "case_manifest.jsonl", "manual.md"):
            file = corpus_directory / filename
            hashes[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
        if registration.get("manual_source"):
            file = root / registration["manual_source"]
            hashes[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
        for doc in corpus.documents:
            file = corpus_directory / "raw" / (doc["doc_id"] + ".pdf")
            hashes[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
        write_json(run.directory / "input_hashes.json", hashes)
        packet, shown_chunks = retrieve(run, corpus)
        key = api_key()
        if not live:
            return run.directory, run.finish("PREFLIGHT_COMPLETE", final_status=None, source_pages=len(shown_chunks), api_key_configured=bool(key), actual_model_answer=False)
        if not key:
            return run.directory, run.finish("NOT_STARTED_MISSING_API_KEY", final_status=None, actual_model_answer=False,
                                             next_action="Configure OPENAI_API_KEY or connect OpenAI Developers; no credential in chat.")
        # Fresh standalone Responses calls. No chat history, gold, private files or web tools.
        run.client = OpenAI(api_key=key, base_url="https://api.openai.com/v1", max_retries=0)
        common = (root / "prompts" / "common.md").read_text(encoding="utf-8")
        extraction_payload = {**packet, "task": "먼저 적용 이익, 다음 비교기업 배수, 다음 적용 주식수와 평가 결과를 정해진 양식에 추출하라. 숫자는 쉼표 없는 십진수 문자열로 쓴다. unit은 million_krw 필드에서 백만원, per 필드에서 배, reported_price_krw에서 원, 주식수 필드에서 주를 정확히 쓴다. claim_id는 X_로 시작하고 전부 고유하게 쓴다. 표의 단위와 주석을 확인하라. 없는 값은 null과 구체적인 missing_reason을 적는다. 정정 전/후 및 실제 공모가격을 혼동하지 말라. peers에는 실제 적용된 비교기업만 넣는다."}
        extraction = run.structured("extract", common, extraction_payload, EXTRACTION, config["extraction_output_max"], lambda v: validate_extraction(v, shown_chunks))
        write_json(run.directory / "extraction.json", extraction)
        inputs = calculation_inputs(extraction)
        provenance = [{"field": field, **fact} for field, fact in facts_in(extraction)]
        calc_args = {"inputs": inputs, "source_inputs": provenance}
        calcs = run.tool("calculate", calc_args, lambda: calculate(inputs), reserved_calls=2)
        scenarios = run.tool("sensitivity", calc_args, lambda: sensitivity(inputs), reserved_calls=2)
        calculation_record = {"source_inputs": provenance, "recalculation": calcs, "sensitivity": scenarios,
                              "precision_status": "PUBLIC_INPUT_RECALCULATION; original unrounded inputs not independently verified"}
        write_json(run.directory / "calculations.json", calculation_record)
        # Full provenance already lives in extraction; do not send a duplicate copy.
        payload = {**packet, "extraction": extraction,
                   "calculations": {key: value for key, value in calculation_record.items() if key != "source_inputs"},
                   "task": "J1, J2, J3, J4 순서로 한국어 검토 의견을 완성하라. 각 judgment_id는 J1 등 domain과 같게 하고, 새로운 사실의 claim_id는 R_로 시작한다. 계산 도구의 결과를 근거로 설명하되 대안은 계산상 가정임을 구분한다. 추출값 중 null인 필드는 전부 missing_inputs에 정확한 field 경로와 request_id를 적는다. values 안의 값은 필드명만, 비교기업 값은 peers[0].per 같은 경로를 쓴다. 비교기업 목록 자체가 없으면 field=peers로 정보 요청을 연결한다. REQUEST_INFO나 ESCALATE 처분에는 해당 판단 ID가 연결된 요청을 반드시 넣는다. 추가 검색은 할 수 없다. 원문 근거만으로 판단하고 전제와 한계를 밝힌다. 확인되지 않은 원자료나 회사 답변을 확보했다고 쓰지 않는다."}
        review = run.structured("review", common, payload, REVIEW, config["review_output_max"], lambda v: validate_review(v, extraction, shown_chunks, corpus.case["allowed_doc_ids"]))
        # One tool event registers all requests in its fixed slot. No external delivery.
        run.tool("request_information", {"requests": review["requests"]}, lambda: {"recorded": review["requests"], "sent_externally": False}, reserved_calls=2)
        run.tool("escalate", {"escalations": review["escalations"]}, lambda: {"recorded": review["escalations"], "sent_externally": False}, reserved_calls=1)
        status = final_status(review)
        report = {"run_id": run.run_id, "case_id": corpus.case["case_id"], "issuer_name": corpus.case["issuer_name"],
                  "cutoff_at": corpus.case["cutoff_at"], "config_version": config["version"],
                  **review, "extracted_inputs": extraction,
                  "calculations": submission_calculations(extraction, calcs, scenarios, review),
                  "calculation_notes": calcs["notes"] + scenarios["notes"], "final_status": status}
        result = run.tool("submit_review", {"submission_file": "review.json"}, lambda: {"valid": not validate_review(review, extraction, shown_chunks, corpus.case["allowed_doc_ids"]), "checks_factual_correctness": False})
        if not result["valid"]:
            raise RuntimeError("Final submission did not pass structural validation")
        write_json(run.directory / "review.json", report)
        (run.directory / "review.md").write_text(render_report(report), encoding="utf-8")
        return run.directory, run.finish("SUBMITTED", final_status=status, model_reported_status=review["model_reported_status"],
                                         status_mismatch=status != review["model_reported_status"], actual_model_answer=True)
    except Exception as exc:
        run.log("run_stopped", {"error_type": type(exc).__name__, "reason": str(exc)})
        return run.directory, run.finish("FAILED", final_status="FAILED", actual_model_answer=False, failure_reason=str(exc))


def main():
    parser = argparse.ArgumentParser(description="Run B/A0 v2 development comparison; default is a free local preflight.")
    parser.add_argument("--live", action="store_true", help="Use the configured API key to obtain a real Terra review")
    parser.add_argument("--case-id", default=DEFAULT_CASE_ID, help="Select a case registered in config/cases.json (default: HDMS-DEV-01)")
    parser.add_argument("--condition", choices=("B", "A0"), default="B", help="B: fixed program policy; A0: model-selected tools")
    parser.add_argument("--repeat", type=int, default=1, help="Positive repetition label; each invocation receives a fresh run ID")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    directory, summary = execute(live=args.live, case_id=args.case_id, condition=args.condition, repeat=args.repeat)
    print(dumps({"directory": str(directory), **summary}))
    return 0 if summary["execution_status"] in ("SUBMITTED", "PREFLIGHT_COMPLETE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
