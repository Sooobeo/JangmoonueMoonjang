"""Replay the six archived M04 provider requests without modifying the original experiment."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from jsonschema import Draft202012Validator
from openai import OpenAI

from ipo_eval.runner import api_key
from ipo_eval.runtime_v2 import RunV2, wire_dumps
from scripts.current_j2 import (
    OUTPUT,
    ROOT,
    TRIZ_OUTPUT,
    TRIZ_PROMPT,
    output_json,
    read,
    sha,
    write,
)
from scripts.current_selector import read_cases

HERE = OUTPUT.parent / "official/excerpt_feasibility"


def freeze():
    contract = read(OUTPUT / "operator/M04_triz_freeze.json")
    prior = read(OUTPUT / "M04_triz_runs.json")["runs"]
    jobs = {}
    for role, names in contract["order"].items():
        jobs[role] = []
        for pos, name in enumerate(names):
            entry = next(v for v in prior if v["role"] == role and v["variant"] == name)
            folder = OUTPUT / entry["directory"]
            requestfile = folder / "01_item_review_request.json"
            req = read(requestfile)
            assert (
                req["input"][0]["content"] == TRIZ_PROMPT
                and sha(TRIZ_PROMPT.encode()) == contract["prompt_sha256"]
            )
            payload = json.loads(req["input"][1]["content"])
            assert payload == read(OUTPUT / "packets" / f"M04_{name}.json")
            assert (
                sha(wire_dumps(payload).encode())
                == entry["input_sha256"]
                == contract["variant_sha256"][name]
            )
            assert (
                req["text"]["format"]["schema"] == TRIZ_OUTPUT
                and sha(wire_dumps(TRIZ_OUTPUT).encode())
                == contract["output_schema_sha256"]
            )
            assert (
                req["model"] == read(folder / "config.json")["model"]
                and req["store"] is False
            )
            assert entry["api_error_code"] == "credit_balance_exhausted" and not list(
                folder.glob("*_response.json")
            )
            jobs[role].append(
                {
                    "order": pos + 1,
                    "role": role,
                    "variant": name,
                    "legacy": folder.relative_to(ROOT).as_posix(),
                    "legacy_error_sha256": sha(
                        (folder / "01_item_review_error.json").read_bytes()
                    ),
                    "payload_sha256": entry["input_sha256"],
                    "request_file_sha256": sha(requestfile.read_bytes()),
                    "request_wire_sha256": sha(wire_dumps(req).encode()),
                }
            )
    manifest = {
        "archived_six_error_index_sha256": sha(
            (OUTPUT / "M04_triz_runs.json").read_bytes()
        ),
        "old_freeze_file_sha256": sha(
            (OUTPUT / "operator/M04_triz_freeze.json").read_bytes()
        ),
        "jobs": jobs,
        "expected": contract["expected"],
        "formal_TRIZ_eligible": False,
        "scope": "Both runs use the identical neutral, standalone excerpt. Prior official roles did not jointly accept M04; this technical retry cannot supply formal H1, H2 or TRIZ signals.",
    }
    target = HERE / "freeze.json"
    if target.exists():
        assert {
            k: v for k, v in read(target).items() if k != "frozen_after_funding_utc"
        } == manifest
    else:
        write(
            target,
            {**manifest, "frozen_after_funding_utc": datetime.now(UTC).isoformat()},
        )
    return manifest


def one(job):
    source = ROOT / job["legacy"]
    out = HERE / "runs" / job["role"] / str(job["order"])
    index = out / "result.json"
    if index.exists():
        res = read(index)
        assert res["request_wire_sha256"] == job["request_wire_sha256"]
        return res
    out.mkdir(parents=True, exist_ok=True)
    lock = out / "active.lock"
    with lock.open("x") as stream:
        stream.write(datetime.now(UTC).isoformat())
    try:
        req = read(source / "01_item_review_request.json")
        assert sha(wire_dumps(req).encode()) == job["request_wire_sha256"]
        candidates = list(out.glob("*/*_response.json"))
        if candidates:
            response_file = max(candidates)
            raw = read(response_file)
            folder = response_file.parent
            summary = read(folder / "summary.json")
        else:
            if any(out.glob("*/events.jsonl")):
                raise RuntimeError(
                    "Existing non-indexed request with no saved answer; audit before reuse."
                )
            run = RunV2(
                read(source / "config.json"),
                live=True,
                base_directory=out,
                client=OpenAI(
                    api_key=api_key(),
                    base_url="https://api.openai.com/v1",
                    max_retries=0,
                ),
            )
            try:
                raw = run.request("item_review", req, "ITEM_REVIEW")
            except (OSError, RuntimeError, ValueError) as err:
                run.finish(
                    "FAILED", actual_model_answer=False, reason=type(err).__name__
                )
                raise
            folder = run.directory
            summary = run.finish("SUBMITTED", actual_model_answer=True)
        answer = output_json(raw)
        Draft202012Validator(TRIZ_OUTPUT).validate(answer)
        payload = json.loads(req["input"][1]["content"])
        valid = {
            e["evidence_id"]
            for k in ["candidate_evidence", "issuer_evidence"]
            for e in payload[k]
        }
        cited = {e for fact in answer["facts"] for e in fact["evidence_refs"]}
        assert answer["facts"] and cited and cited <= valid
        assert all(f["evidence_refs"] for f in answer["facts"])
        recorded = read(next(folder.glob("01_item_review_request.json")))
        assert (
            recorded == req
            and sha(wire_dumps(recorded).encode()) == job["request_wire_sha256"]
        )
        res = {
            **job,
            "actual_run_dir": folder.relative_to(ROOT).as_posix(),
            "raw_response_id": raw["id"],
            "answer": answer,
            "summary": summary,
            "evidence_ids_checked": sorted(cited),
        }
        write(index, res)
        return res
    finally:
        lock.unlink(missing_ok=True)


def run():
    spec = freeze()
    with ThreadPoolExecutor(max_workers=2) as pool:
        groups = list(
            pool.map(lambda group: [one(job) for job in group], spec["jobs"].values())
        )
    rows = [r for g in groups for r in g]
    assert len({r["raw_response_id"] for r in rows}) == 6
    assert spec == freeze()
    labelpath = OUTPUT.parent / "official/dev_labels.json"
    full = next(
        i for i in read_cases(labelpath)["MELCON"]["items"] if i["item_id"] == "M04"
    )
    comparison = {}
    starts = []
    finishes = []
    for role in spec["jobs"]:
        variants = {r["variant"]: r for r in rows if r["role"] == role}
        order = []
        for name, r in variants.items():
            folder = ROOT / r["actual_run_dir"]
            prior = read(ROOT / r["legacy"] / "01_item_review_error.json")
            assert (
                prior["http_status"] == 429
                and prior["request_sha256"] == r["request_wire_sha256"]
            )
            assert (
                sha((folder / "01_item_review_request.json").read_bytes())
                == r["request_file_sha256"]
            )
            events = [
                json.loads(t)
                for t in (folder / "events.jsonl")
                .read_text(encoding="utf8")
                .splitlines()
            ]
            stamp = next(
                e["started_at_utc"] for e in events if e["event"] == "run_created"
            )
            order.append((stamp, name))
            started = datetime.fromisoformat(stamp).timestamp()
            starts.append(started)
            finishes.append(started + r["summary"]["elapsed_seconds"])
        assert [f for _, f in sorted(order)] == [
            r["variant"] for r in spec["jobs"][role]
        ]
        answers = {k: r["answer"] for k, r in variants.items()}
        status = full[role.lower()]["judgment"]
        for name, ans in answers.items():
            refs = {
                eid
                for f in ans["facts"]
                if f["dimension"] == "적용 공정"
                for eid in f["evidence_refs"]
            }
            assert ("E123" in refs) == (name != "process_evidence_withheld")
        changed = answers["process_evidence_withheld"]
        assert any(
            "후보" in cond and "포토" in cond for cond in changed["open_conditions"]
        )
        comparison[role] = {
            "full_official_original_state": status,
            "standalone_original": answers["original"]["judgment"],
            "matches_full_original": status == answers["original"]["judgment"],
            "format_only": answers["format_only"]["judgment"],
            "after_removal": changed["judgment"],
            "format_preserves_judgment_and_process_citation": True,
            "after_removal_candidate_photo_process_now_requires_evidence": True,
        }
    write(
        HERE / "ledger.json",
        {
            "formal_TRIZ_eligible": False,
            "regression_only": True,
            "rows": rows,
            "observed_standalone": comparison,
            "unchanged_source_full_labels_sha256": sha(labelpath.read_bytes()),
            "interpretation": "A0 moved from its full-filing unknown to acceptance on the isolated excerpt; C reproduced acceptance. Both maintained judgment and the process citation after reordering. Removing E123 caused both roles to request evidence for candidate photolithography application. A0 changed overall judgment to unknown, while C conditionally retained acceptance on other evidence.",
            "summary": {
                "valid_answers": len(rows),
                "observed_parallel_span_seconds": round(max(finishes) - min(starts), 3),
                "calls": sum(r["summary"]["model_calls"] for r in rows),
                "known_standard_uncached_usd_estimate": round(
                    sum(
                        r["summary"]["known_usage_cost_usd_standard_uncached"]
                        for r in rows
                    ),
                    6,
                ),
                "input_tokens": sum(r["summary"]["input_tokens"] for r in rows),
                "output_tokens": sum(r["summary"]["output_tokens"] for r in rows),
                "cumulative_seconds": round(
                    sum(r["summary"]["elapsed_seconds"] for r in rows), 3
                ),
            },
            "three_reviews": [
                "Checked six archived 429 files, order, user packets, schema, prompt and exact complete request hashes before new calls.",
                "Validated actual provider responses against frozen schema and every cited ID against the corresponding sent packet.",
                "Checked independent response IDs and usage against raw records, preserved all original failure files and official label/rank paths.",
            ],
        },
    )


if __name__ == "__main__":
    run()
