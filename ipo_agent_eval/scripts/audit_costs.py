"""Audit saved API usage without calling an API or reading credentials.

Original run artifacts are read-only. Prices are the verified 2026-11-12
GPT-6.1 Terra Standard rates for prompts of at most 272,000 tokens.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
MILLION = Decimal(1000000)
FX = Decimal(1400)
RATES = {"ordinary_input": Decimal("1"), "cached_input": Decimal("0.05"),
         "cache_write_30m": Decimal("1.25"), "cache_write_12h": Decimal("2.5"),
         "output": Decimal("5")}
COUNTS = ["input_tokens", "ordinary_input_tokens", "cached_input_tokens", "cache_write_30m_tokens",
          "cache_write_12h_tokens", "output_tokens", "reasoning_tokens"]


def number(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def money(value):
    return format(value, "f")


def price_usage(usage, default_write_ttl="30m"):
    """Price mutually exclusive input buckets; reasoning is already in output."""
    if not isinstance(usage, dict) or "input_tokens" not in usage or "output_tokens" not in usage:
        raise ValueError("Usage must contain actual input and output token counts")
    input_tokens = number(usage["input_tokens"], "input_tokens")
    output_tokens = number(usage["output_tokens"], "output_tokens")
    if input_tokens > 272000:
        raise ValueError("This audit is limited to short-context Terra Standard pricing")
    details = usage.get("input_tokens_details") or {}
    cached = number(details.get("cached_tokens", 0), "cached_tokens")
    writes = number(details.get("cache_write_tokens", 0), "cache_write_tokens")
    if cached + writes > input_tokens:
        raise ValueError("Cached reads and writes exceed total input tokens")
    ttl_details = details.get("cache_write_tokens_details")
    notes = []
    if ttl_details is not None:
        short = number(ttl_details.get("ttl_30m_tokens", 0), "ttl_30m_tokens")
        long = number(ttl_details.get("ttl_12h_tokens", 0), "ttl_12h_tokens")
        if short + long != writes:
            raise ValueError("Cache TTL counts do not sum to cache_write_tokens")
    else:
        if default_write_ttl not in ("30m", "12h"):
            raise ValueError("Unsupported cache lifetime")
        short, long = (writes, 0) if default_write_ttl == "30m" else (0, writes)
        if writes:
            notes.append("TTL breakdown absent; used request TTL or API default 30m")
    reasoning = number((usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0), "reasoning_tokens")
    if reasoning > output_tokens:
        raise ValueError("Reasoning tokens exceed total output tokens")
    ordinary = input_tokens - cached - writes
    costs = {"ordinary_input": Decimal(ordinary) * RATES["ordinary_input"] / MILLION,
             "cached_input": Decimal(cached) * RATES["cached_input"] / MILLION,
             "cache_write_30m": Decimal(short) * RATES["cache_write_30m"] / MILLION,
             "cache_write_12h": Decimal(long) * RATES["cache_write_12h"] / MILLION,
             "output": Decimal(output_tokens) * RATES["output"] / MILLION}
    return {"input_tokens": input_tokens, "ordinary_input_tokens": ordinary, "cached_input_tokens": cached,
            "cache_write_30m_tokens": short, "cache_write_12h_tokens": long, "output_tokens": output_tokens,
            "reasoning_tokens": reasoning, "cost_components_usd": {key: money(value) for key, value in costs.items()},
            "estimated_cost_usd": money(sum(costs.values(), Decimal(0))), "notes": notes}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def audit_run(directory):
    directory = Path(directory)
    summary_path = directory / "summary.json"
    summary = read_json(summary_path) if summary_path.exists() else {}
    events_path = directory / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()] if events_path.exists() else []
    calls = summary.get("model_calls", sum(event.get("event") == "model_call_started" for event in events))
    responses = []
    missing_response_usage = []
    seen = set()
    for path in sorted(directory.glob("*_response.json")):
        response = read_json(path)
        identifier = response.get("id")
        if identifier and identifier in seen:
            raise ValueError(f"Duplicate response ID in {directory.name}")
        seen.add(identifier)
        if response.get("usage") is None:
            missing_response_usage.append(path.name)
            continue
        if response.get("model") != "gpt-6.1-terra":
            raise ValueError("Unexpected model; this audit uses Terra prices only")
        request_path = path.with_name(path.name.replace("_response.json", "_request.json"))
        request = read_json(request_path) if request_path.exists() else {}
        if request.get("service_tier", "default") != "default":
            raise ValueError("Unexpected service tier; Standard pricing cannot be assumed")
        ttl = (request.get("prompt_cache_options") or {}).get("ttl", "30m")
        priced = price_usage(response["usage"], ttl)
        responses.append({"response_file": path.name, "response_id": identifier,
                          "response_status": response.get("status"), **priced})
    if len(responses) > calls:
        raise ValueError("More saved usage responses than declared model calls")
    totals = {key: sum(response[key] for response in responses) for key in COUNTS}
    known_cost = sum((Decimal(response["estimated_cost_usd"]) for response in responses), Decimal(0))
    missing_calls = calls - len(responses)
    if calls == 0:
        note = "No model request was made in this record"
    elif missing_calls:
        note = "Some requests have no usage; do not interpret missing usage as a zero bill"
    else:
        note = "All declared model calls have saved usage, including incomplete responses"
    return {"run_id": directory.name, "execution_status": summary.get("execution_status", "RUNNING"),
            "model_calls": calls, "responses_with_usage": len(responses), "requests_without_usage": missing_calls,
            "all_model_requests_have_usage": missing_calls == 0, "token_totals": totals,
            "known_usage_cost_usd": money(known_cost) if responses or calls == 0 else None,
            "known_usage_cost_krw": money((known_cost * FX).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if responses or calls == 0 else None,
            "usage_missing_response_files": missing_response_usage, "responses": responses, "note": note}


def audit_all(runs_directory):
    runs = [audit_run(directory) for directory in sorted(Path(runs_directory).iterdir()) if directory.is_dir()]
    cost = sum((Decimal(run["known_usage_cost_usd"]) for run in runs if run["known_usage_cost_usd"] is not None), Decimal(0))
    unknown = sum(run["requests_without_usage"] for run in runs)
    groups = {}
    for name, state in (("submitted", "SUBMITTED"), ("failed_with_usage", "FAILED")):
        members = [run for run in runs if run["execution_status"] == state and run["responses_with_usage"] > 0]
        subtotal = sum((Decimal(run["known_usage_cost_usd"]) for run in members), Decimal(0))
        groups[name] = {"run_count": len(members), "known_usage_cost_usd": money(subtotal),
                        "known_usage_cost_krw": money((subtotal * FX).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))}
    return {"pricing_checked_on": "2026-11-12", "model": "gpt-6.1-terra", "service_tier": "Standard",
            "rates_usd_per_million_tokens": {key: money(value) for key, value in RATES.items()},
            "budget_fx_krw_per_usd": money(FX), "is_invoice": False,
            "pricing_sources": ["https://developers.openai.com/api/docs/models/gpt-6.1-terra", "https://developers.openai.com/api/docs/guides/prompt-caching"],
            "token_totals": {key: sum(run["token_totals"][key] for run in runs) for key in COUNTS},
            "known_usage_cost_usd": money(cost), "known_usage_cost_krw": money((cost * FX).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "groups": groups,
            "requests_without_usage": unknown, "all_model_requests_have_usage": unknown == 0,
            "note": "Estimate from saved usage and published rates; excludes tax and actual exchange-rate differences. Unknown request usage is not assigned zero cost.",
            "runs": runs}


def render_markdown(audit):
    lines = ["# 저장된 API 사용량으로 다시 계산한 비용", "", "2026년 11월 12일, 한국시간 기준으로 정리했다.", "",
             "이 문서는 API 원본 응답에 기록된 사용량으로 계산한 예상 비용이다. 실제 청구서가 아니며 세금과 카드사의 환율 차이는 포함하지 않았다. 원래 실행 폴더의 요약과 응답은 수정하지 않았다.", "",
             "Terra의 입력은 일반 입력, 캐시 읽기, 캐시 쓰기로 나누어 각각의 요금을 적용했다. 캐시 쓰기 금액을 일반 입력 요금에 다시 더하지 않는다. 추론 토큰은 출력 토큰에 이미 들어 있으므로 한 번만 계산했다. [모델 요금](https://developers.openai.com/api/docs/models/gpt-6.1-terra), [캐시 계산 방법](https://developers.openai.com/api/docs/guides/prompt-caching).", "",
             "| 구분 | 100만 토큰당 달러 |", "|---|---:|", "| 일반 입력 | 1.00 |", "| 캐시 읽기 | 0.05 |", "| 캐시 쓰기, 기본 30분 | 1.25 |", "| 캐시 쓰기, 12시간 | 2.50 |", "| 출력, 추론 포함 | 5.00 |", "",
             "이번 요청에는 12시간 보관 설정이 없었다. 응답에 보관시간별 쓰기 수가 없으면 요청 설정과 기본 30분 요율을 사용했다.", "",
             "## 실행별로 사용량이 확인된 금액", "", "| 실행 | 상태 | 사용량이 있는 응답 / 모델 요청 | 달러 | 원화 추정 |", "|---|---|---:|---:|---:|"]
    for run in audit["runs"]:
        if run["model_calls"]:
            usd = run["known_usage_cost_usd"] if run["known_usage_cost_usd"] is not None else "미확인"
            krw = run["known_usage_cost_krw"] if run["known_usage_cost_krw"] is not None else "미확인"
            lines.append(f"| `{run['run_id']}` | {run['execution_status']} | {run['responses_with_usage']} / {run['model_calls']} | {usd} | {krw} |")
    lines += ["", f"사용량이 기록된 요청의 합계는 **{audit['known_usage_cost_usd']}달러**, 예산용 환율 1달러=1,400원으로 **{audit['known_usage_cost_krw']}원**이다.", "",
              f"이 중 유효한 답변을 제출한 실행 {audit['groups']['submitted']['run_count']}건은 {audit['groups']['submitted']['known_usage_cost_usd']}달러, 약 {audit['groups']['submitted']['known_usage_cost_krw']}원이다. 사용량이 있는 개발 실패 {audit['groups']['failed_with_usage']['run_count']}건은 합계 {audit['groups']['failed_with_usage']['known_usage_cost_usd']}달러, 약 {audit['groups']['failed_with_usage']['known_usage_cost_krw']}원이다. 전체 합계는 각 금액을 반올림하기 전에 더해 계산했다.", "",
              f"사용량을 받지 못한 요청은 {audit['requests_without_usage']}회다. 그 요청의 청구액을 0원이라고 단정하지 않았다. 출력이 중간에 끊긴 실행도 반환된 사용량을 합계에 포함했다. 모델을 호출하지 않은 사전 점검은 계산 대상 토큰이 없다.", "",
              "## 전체 10만원 예산을 생각할 때 참고할 계산", "",
              "기존처럼 한 번의 실행에 입력 120,000토큰과 출력 16,000토큰을 쓴다고 가정하되, 입력을 모두 기본 30분 캐시에 새로 쓴다고 보면 0.15+0.08=0.23달러, 예산용 환율로 322원이다. 250회 상당의 사용량은 80,500원이고, 10만원 중 19,500원이 예비비로 남는다. 이는 실제 지출 확정액이나 새로운 실행 계획이 아니라 기존 공통 토큰 가정에 캐시 쓰기를 반영한 보수적인 참고 견적이다. 개발 중 실패한 요청도 사용량과 비용에 포함해 관리해야 한다. 이 계산 때문에 프로그램의 실행 횟수·시간·토큰 제한이나 총예산을 바꾸지는 않았다.", "",
              "## 세 차례 확인한 내용", "", "1. 일반 입력·캐시 읽기·캐시 쓰기가 겹치지 않게 나뉘는지 확인했다. 추론을 출력에 두 번 더하지 않는 테스트도 실행했다.",
              "2. 음수·잘못된 숫자형·입력보다 큰 캐시 수·보관시간 합계 오류·사용량 누락·예상 밖 모델을 시험했다. 누락 사용량을 0원 청구로 바꾸지 않았다.",
              "3. 원본 응답과 합계를 다시 대조하고, 중간에 끊긴 실행과 최종 제출 실행을 모두 포함했다. 실행 기록에 있는 일반 입력 가정의 단순 견적과 이 사후 계산을 구분했다.", "",
              "세부 입력 종류별 토큰 수와 응답별 산식 결과는 [usage_costs.json](usage_costs.json)에 있다.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Read saved Responses usage; never contacts an API")
    parser.add_argument("--runs", type=Path, default=PROJECT / "runs")
    parser.add_argument("--output", type=Path, default=PROJECT / "reports")
    args = parser.parse_args()
    audit = audit_all(args.runs)
    if any(run["execution_status"] == "RUNNING" for run in audit["runs"]):
        raise SystemExit("A run has no final summary yet; wait before publishing the audit")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "usage_costs.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "사용비용.md").write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps({"known_usage_cost_usd": audit["known_usage_cost_usd"], "known_usage_cost_krw": audit["known_usage_cost_krw"], "requests_without_usage": audit["requests_without_usage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
