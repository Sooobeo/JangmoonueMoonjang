"""Audited development calls for the current A1 design, including the paired B test."""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor

import fitz
from jsonschema import ValidationError, validate
from openai import OpenAI

from ipo_eval.agent_loop import output_json
from ipo_eval.runner import api_key
from ipo_eval.runtime_v2 import RunV2, audit_file, wire_dumps
from ipo_eval.schemas import S, arr, obj
from scripts.current_b import OUT, ROOT, dump, filing


def load(path):
    return json.loads(audit_file(path).read_bytes())


def digest(data):
    return hashlib.sha256(wire_dumps(data).encode("utf8")).hexdigest()


def ask(
    name,
    stage,
    instructions,
    payload,
    schema,
    output_limit=4200,
    verify=None,
    session=None,
):
    config = load(ROOT / "config/A0.json")
    config.update(
        condition=stage,
        case_id=name,
        version="current-dev-1",
        wall_seconds_max=180,
        max_model_calls=4,
        output_tokens_max=12000,
        max_format_repairs=1,
        format_repair_input_reserve=65000,
        format_repair_output_max=4200,
        max_transient_api_retries=1,
    )
    request = {
        "model": config["model"],
        "reasoning": {"effort": config["reasoning_effort"]},
        "store": False,
        "service_tier": "default",
        "max_output_tokens": output_limit,
        "instructions": instructions,
        "input": wire_dumps(payload),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "assessment",
                "strict": True,
                "schema": schema,
            }
        },
    }
    if stage in {"A1_LOOK", "A1_SELECT"}:
        config.update(
            wall_seconds_max=90,
            max_model_calls=2,
            max_run_usd=0.625,
            output_tokens_max=2200 if stage == "A1_LOOK" else 9800,
        )
    fingerprint = digest(request)
    base = OUT / "live" / name / stage
    legacy = base / fingerprint
    # Completed long-path caches remain readable. New attempts need room for the
    # run ID, stage name, and response filename on Windows.
    folder = legacy if (legacy / "result.json").is_file() else base / fingerprint[:16]
    cached = folder / "result.json"
    if cached.is_file():
        saved = load(cached)
        validate(saved["answer"], schema)
        if verify:
            verify(saved["answer"])
        return saved
    if os.getenv("IPO_RESUME_AFTER_CREDIT") != "1" and any(
        load(p).get("api_error_code")
        in {"credit_balance_exhausted", "insufficient_quota"}
        for p in (OUT / "live").rglob("*_error.json")
    ):
        raise RuntimeError(
            "Prior terminal billing error. After balance restoration set IPO_RESUME_AFTER_CREDIT=1 to resume."
        )
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / "active.lock"
    with lock.open("x") as stream:
        stream.write(str(os.getpid()))
    run = None
    try:
        run = session or RunV2(
            config, True, folder, OpenAI(api_key=api_key(), max_retries=0)
        )
        for attempt in range(2):
            raw = run.request(
                stage if not attempt else stage + "_format", request, "CURRENT"
            )
            try:
                answer = output_json(raw)
                validate(answer, schema)
                if verify:
                    verify(answer)
                break
            except (ValueError, RuntimeError, AssertionError, ValidationError) as exc:
                if attempt or run.repairs or stage == "A1_LOOK":
                    raise
                run.repairs += 1
                prior = [
                    c.get("text", "")
                    for item in raw.get("output", [])
                    for c in item.get("content", [])
                ]
                request = {
                    **request,
                    "input": wire_dumps(
                        {
                            "input": payload,
                            "prior_submission": prior,
                            "contract_issue": str(exc)[:400],
                        }
                    ),
                }
        summary = run.finish(
            "SUBMITTED", contract_versions=["current-dev-1"], actual_model_answer=True
        )
        result = {
            "answer": answer,
            "summary": summary,
            "evidence_dir": str(run.directory.relative_to(ROOT).as_posix()),
            "raw_response_id": raw.get("id"),
        }
        scratch = folder / "result.pending"
        dump(scratch, result)
        scratch.replace(cached)
        return result
    except Exception as exc:
        if run:
            run.finish(
                "FAILED", reason=type(exc).__name__, contract_versions=["current-dev-1"]
            )
        raise
    finally:
        lock.unlink(missing_ok=True)


B_SCHEMA = obj(
    {
        "price_krw": {"type": ["number", "null"]},
        "share_count": {"type": ["integer", "null"]},
        "observations": arr(
            obj({"issue": S, "page": {"type": "integer"}, "reason": S})
        ),
        "unresolved": arr(S),
    }
)
B_PROMPT = "최초 신고서만 보고 과거 실적 PER의 적용 주식 수와 주당 평가가액을 다시 구하라. 중요 판단형 누락 또는 오류가 실제 근거로 확인될 때 관측에 기록한다. 확인이 필요한 한계는 unresolved에 적는다. 표시 정밀도, 적용 이익 범위와 시점을 검토하라."


def b_pair(case):
    b = next(r for r in load(OUT / "b.json")["cases"] if r["case_id"] == case)
    pages = [269, 270] if case == "HDMS" else [207, 208]
    path, _, _ = filing(case)
    with fitz.open(path) as doc:
        context = {str(p): doc[p - 1].get_text(sort=True) for p in pages}
    expected = {
        k: int(v["display"].replace(",", "")) * (1000 if v["unit"] == "천주" else 1)
        for k, v in b["facts"].items()
        if k in {"price", "shares"}
    }
    results = []
    for enabled in [False, True] if case == "HDMS" else [True, False]:
        payload = {"original_physical_pages": context}
        if enabled:
            payload["pre_verification"] = {
                "period_scope": b["period_scope"],
                "facts": b["facts"],
                "rules": b["rules"],
            }
        res = ask(
            case,
            "B_with" if enabled else "B_without",
            B_PROMPT,
            payload,
            B_SCHEMA,
            2800,
        )
        a = res["answer"]
        results.append(
            {
                "b_provided": enabled,
                "price_correct": a["price_krw"] == expected["price"],
                "shares_correct": a["share_count"] == expected["shares"],
                "observations": a["observations"],
                "unresolved": a["unresolved"],
                "run_id": res["summary"]["run_id"],
                "estimated_usd": res["summary"][
                    "known_usage_cost_usd_standard_uncached"
                ],
                "seconds": res["summary"]["elapsed_seconds"],
                "evidence_dir": res["evidence_dir"],
            }
        )
    return {"case": case, "pages": pages, "pair": results}


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as pool:
        dump(OUT / "b_paired.json", list(pool.map(b_pair, ["HDMS", "MELCON"])))
