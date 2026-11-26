"""Measure isolated Codex persona review of blinded operating-list tasks."""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from subprocess import SubprocessError

from jsonschema import ValidationError

from scripts.current_b import OUT, ROOT, dump
from scripts.current_live import S, arr, digest, obj
from scripts.current_proxy import ask_proxy
from scripts.current_selector import original_inputs

STORE = OUT / "persona_timing"
DEV = ("HDMS", "MELCON")
VALIDATION = ("GIGAVIS", "TRUEN", "MANYO", "PHILENERGY")
COHORTS = {"development": DEV, "validation": VALIDATION}
CASES = DEV + VALIDATION
ARMS = ("rule", "ai")
PROTOCOL = "ipo-persona-time-1"
ROLE = """당신은 가상의 국내 증권사 IPO 인수심사팀 공시 검토자다. 기업 재무·증권신고서 검토 경력 3년 수준이며, 배정받은 검토 한 건을 팀 내부 검토 메모로 마감한다.
절차 1. 제공된 최초 신고서 쪽에서 검토 질문에 대응하는 표·행, 본문 또는 각주를 찾아 공시가 실제로 주장하는 내용을 한 문장으로 적는다.
절차 2. 수치면 기간, 단위, 귀속, 분모를 맞춰 가능한 산식을 입력값부터 재계산한다. 사업 판단이면 조건에 찬성하는 근거와 반대 근거를 원문에서 대조한다. 확인 가능한 사실과 추가 원천이 필요한 판단을 구분한다.
절차 3. 팀에 넘길 결과를 한국어로 남긴다. 주장이 뒷받침되는지, 문제가 직접 확인되는지, 자료 부족으로 판단이 유보되는지를 표시한다. 제공된 PDF 물리 쪽의 문구나 행을 정확하게 인용한다. 유보라면 필요한 후속 확인 자료를 구체적으로 쓴다. 확인한 내용만 기록한다.
목록 출처나 다른 검토자의 판단을 추정하지 않는다. 검토 시간은 실행기가 측정하므로 시간 추정치를 답변에 쓰지 않는다."""
CITATION = obj(
    {
        "physical_page": {"type": "integer"},
        "locator": S,
        "quote": S,
    }
)
REVIEW = obj(
    {
        "filing_claim": S,
        "checked_basis_or_arithmetic": S,
        "outcome": {"type": "string", "enum": ["근거 확인", "쟁점 확인", "판단 유보"]},
        "finding": S,
        "follow_up": S,
        "citations": {**arr(CITATION), "minItems": 1, "maxItems": 3},
    }
)


def read(path):
    body = path.read_bytes()
    return json.loads(body), sha256(body).hexdigest()


def now_kst():
    return datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="milliseconds")


def elapsed(start):
    return round(time.perf_counter() - start, 6)


def normalized(text):
    return "".join(text.split())


def verify_answer(answer, pages):
    for key in ("filing_claim", "checked_basis_or_arithmetic", "finding", "follow_up"):
        if not answer[key].strip():
            raise ValueError(f"The reviewer must complete {key}")
    for citation in answer["citations"]:
        page = str(citation["physical_page"])
        quote = normalized(citation["quote"])
        if (
            page not in pages
            or len(quote) < 6
            or not citation["locator"].strip()
            or quote not in normalized(pages[page])
        ):
            raise ValueError(
                "Cite the exact text of a table row, footnote or sentence from a supplied physical page"
            )


def assignment_tasks():
    assignments = {}
    for provenance in ("proxy", "terra"):
        assignments[provenance] = {}
        for case in CASES:
            path = OUT / "ranking" / provenance / f"{case}.json"
            if not path.is_file():
                continue
            ranking, rank_sha = read(path)
            if ranking["case"] != case or ranking["selector_condition"] != (
                "TERRA" if provenance == "terra" else "CODEX_PROXY"
            ):
                raise ValueError(f"Unexpected operating list for {provenance} {case}")
            rows = {arm: ranking[arm]["operational"] for arm in ARMS}
            if any(len(v) != len(set(v)) for v in rows.values()):
                raise ValueError(f"Duplicate operating item in {provenance} {case}")
            assignments[provenance][case] = {"rank_sha256": rank_sha, **rows}
    return assignments


def approved_sources(case):
    pages_by_item, pages, _, _ = original_inputs(case)
    if case in DEV:
        data, source_sha = read(
            ROOT / "data/a1_pilot" / case / "operator/original_items.json"
        )
        labels = {row["id"]: row["label"] for row in data["items"]}
        pdf_sha = data["source_sha256"]
    else:
        data, source_sha = read(OUT / "validation/freeze.json")
        labels = {row["item_id"]: row["question"] for row in data[case]["items"]}
        pdf_sha = data[case]["sha256"]
    if set(labels) != set(pages_by_item):
        raise ValueError(f"Frozen original item IDs differ for {case}")
    return pages_by_item, pages, labels, pdf_sha, source_sha


def task_data(item, bundle):
    pages_by_item, texts, labels, pdf_sha, source_sha = bundle
    pages = {
        str(page): texts[page]
        for page in sorted(set(pages_by_item[item]))
        if page in texts and texts[page].strip()
    }
    if not pages:
        raise ValueError(f"No authorized pages loaded for {item}")
    # Neither a list origin nor a reviewer answer may appear in the input.
    packet = {"check_question": labels[item], "original_physical_pages": pages}
    key = digest(
        {
            "protocol": PROTOCOL,
            "instructions": ROLE,
            "schema": REVIEW,
            "packet": packet,
            "pdf_sha": pdf_sha,
        }
    )
    return packet, key, pdf_sha, source_sha


def timed_task(case_item):
    case, item = case_item
    started = time.perf_counter()
    stamp = now_kst()
    record = {
        "case": case,
        "item_id": item,
        "protocol": PROTOCOL,
        "started_kst": stamp,
        "human_minutes": None,
        "active_human_seconds": None,
        "active_model_reasoning_seconds": None,
    }
    try:
        packet, key, pdf_sha, source_sha = task_data(item, approved_sources(case))
        record.update(
            task_sha256=key,
            source_pdf_sha256=pdf_sha,
            source_registry_sha256=source_sha,
            authorized_physical_pages=[
                int(page) for page in packet["original_physical_pages"]
            ],
            packet_prep_seconds=elapsed(started),
        )
        path = STORE / "tasks" / case / f"{item}-{key[:12]}.json"
        if path.is_file():
            saved, _ = read(path)
            if saved["status"] == "REVIEWED":
                verify_answer(saved["answer"], packet["original_physical_pages"])
                return saved
        # The shared mask is stable across cohorts and selector arms. No original item ID is sent in the packet.
        stage = "PERSONA_" + key[:18]
        request = {
            "instructions": ROLE,
            "input": packet,
            "schema": REVIEW,
            "model": "gpt-6.2-astra",
        }
        expected_evidence_dir = OUT / "proxy" / case / stage / digest(request)[:16]
        existing_service = (expected_evidence_dir / "result.json").is_file()
        record["evidence_dir"] = expected_evidence_dir.relative_to(ROOT).as_posix()
        requested = time.perf_counter()
        response = ask_proxy(
            case,
            stage,
            ROLE,
            packet,
            REVIEW,
            1200,
            lambda answer: verify_answer(answer, packet["original_physical_pages"]),
        )
        record["review_call_wrapper_seconds"] = (
            elapsed(requested) if not existing_service else None
        )
        confirmed = time.perf_counter()
        verify_answer(response["answer"], packet["original_physical_pages"])
        attempts, _ = read(ROOT / response["evidence_dir"] / "attempts.json")
        if any(row.get("tool_events") for row in attempts):
            raise ValueError("Reviewer left the original-source packet")
        record["quote_and_boundary_verification_seconds"] = elapsed(confirmed)
        record.update(
            status="REVIEWED",
            source="original_pdf_only",
            answer=response["answer"],
            closed_kst=now_kst(),
            original_review_service_seconds=response["summary"]["elapsed_seconds"],
            actual_end_to_end_seconds=elapsed(started)
            if not existing_service
            else None,
            recovered_from_existing_service=existing_service,
            attempts=len(attempts),
            timed_out_attempts=sum(a.get("error") == "timeout" for a in attempts),
            evidence_dir=response["evidence_dir"],
        )
        dump(path, record)
    except (
        KeyError,
        ValueError,
        RuntimeError,
        OSError,
        SubprocessError,
        ValidationError,
    ) as exc:
        record.update(
            status="FAILED",
            error=str(exc),
            closed_kst=now_kst(),
            actual_end_to_end_seconds=elapsed(started),
        )
        dump(STORE / "failed_tasks" / f"{case}-{item}.json", record)
    return record


def schedule(assignments):
    tasks = {
        (case, item)
        for ranks in assignments.values()
        for case, row in ranks.items()
        for arm in ARMS
        for item in row[arm]
    }
    # The predetermined SHA-256 order is independent of rank, condition origin and evaluator outputs.
    return sorted(
        tasks,
        key=lambda r: sha256(f"{PROTOCOL}:blind-order:{r[0]}:{r[1]}".encode()).digest(),
    )


def saved_task(case, item):
    folder = STORE / "tasks" / case
    files = list(folder.glob(f"{item}-*.json"))
    if len(files) > 1:
        _, key, _, _ = task_data(item, approved_sources(case))
        files = [p for p in files if p.stem == f"{item}-{key[:12]}"]
    if files:
        record, record_sha = read(files[0])
        return {**record, "record_sha256": record_sha}
    failed = STORE / "failed_tasks" / f"{case}-{item}.json"
    if failed.is_file():
        record, record_sha = read(failed)
        return {**record, "record_sha256": record_sha}
    return {
        "case": case,
        "item_id": item,
        "status": "UNMEASURED",
        "human_minutes": None,
    }


def audit_records(measured):
    source_cache = {}
    verified = []
    for pair, record in measured.items():
        if record["status"] != "REVIEWED":
            continue
        case, item = pair
        if case not in source_cache:
            source_cache[case] = approved_sources(case)
        packet, key, pdf_sha, source_sha = task_data(item, source_cache[case])
        if (
            record["task_sha256"] != key
            or record["source_pdf_sha256"] != pdf_sha
            or record["source_registry_sha256"] != source_sha
        ):
            raise ValueError(f"Timed packet and frozen source differ for {case} {item}")
        evidence = ROOT / record["evidence_dir"]
        request, request_sha = read(evidence / "request.json")
        response, response_sha = read(evidence / "result.json")
        attempts, _ = read(evidence / "attempts.json")
        if (
            request["input"] != packet
            or request["instructions"] != ROLE
            or request["schema"] != REVIEW
            or response["answer"] != record["answer"]
            or any(attempt.get("tool_events") for attempt in attempts)
        ):
            raise ValueError(
                f"Masked source or response integrity failure for {case} {item}"
            )
        verify_answer(record["answer"], packet["original_physical_pages"])
        if (
            record["original_review_service_seconds"]
            != response["summary"]["elapsed_seconds"]
            or record["human_minutes"] is not None
            or record["active_model_reasoning_seconds"] is not None
        ):
            raise ValueError(f"Timing provenance failure for {case} {item}")
        total = record["actual_end_to_end_seconds"]
        if total is not None:
            phases = sum(
                record[name]
                for name in (
                    "packet_prep_seconds",
                    "review_call_wrapper_seconds",
                    "quote_and_boundary_verification_seconds",
                )
            )
            if total < phases - 0.000010:
                raise ValueError(
                    f"Measured elapsed duration is shorter than its phases for {case} {item}"
                )
        verified.append(
            {
                "case": case,
                "item_id": item,
                "request_sha256": request_sha,
                "response_sha256": response_sha,
                "timing_sha256": record["record_sha256"],
            }
        )
    return verified


def workload(items, measured):
    available = [
        measured[item] for item in items if measured[item]["status"] == "REVIEWED"
    ]
    phase = {
        "source_prep_seconds_sum": "packet_prep_seconds",
        "review_service_seconds_sum": "original_review_service_seconds",
        "review_call_wrapper_seconds_sum": "review_call_wrapper_seconds",
        "quote_verification_seconds_sum": "quote_and_boundary_verification_seconds",
        "end_to_end_seconds_sum": "actual_end_to_end_seconds",
    }
    totals = {}
    for output_key, source_key in phase.items():
        times = [
            row[source_key] for row in available if row.get(source_key) is not None
        ]
        totals[output_key] = round(sum(times), 3) if len(times) == len(items) else None
    return {
        "assigned": len(items),
        "measured": len(available),
        **totals,
        "human_minutes": None,
    }


def compare(assignments, copied, measured):
    results = {}
    for kind, ranked in assignments.items():
        rows = []
        for case, armsets in ranked.items():
            arms = {a: [(case, item) for item in armsets[a]] for a in ARMS}
            row = {
                "case": case,
                "rank_sha256": armsets["rank_sha256"],
                "shared_items": sorted(set(armsets["rule"]) & set(armsets["ai"])),
            }
            for arm in ARMS:
                row[arm] = {"items": armsets[arm], **workload(arms[arm], measured)}
            rows.append(row)
        cohorts = {}
        for name, cases in COHORTS.items():
            in_scope = {case: data for case, data in ranked.items() if case in cases}
            totals = {
                arm: workload(
                    [(case, item) for case, a in in_scope.items() for item in a[arm]],
                    measured,
                )
                if in_scope
                else None
                for arm in ARMS
            }
            cohorts[name] = {"ranked": len(in_scope), "expected": len(cases), **totals}
        results[kind] = {
            "rows": rows,
            "cohorts": cohorts,
            "missing_ranked_cases": [case for case in CASES if case not in ranked],
        }
    return {
        "protocol": PROTOCOL,
        "updated_kst": now_kst(),
        "measured_any_arm": sum(v["status"] == "REVIEWED" for v in measured.values()),
        "schedule": copied,
        "distinct_task_phases": workload(list(measured), measured),
        "results": results,
        "human_minutes": None,
        "selected_for_future_evaluation_opened": 0,
        "time_definitions": {
            "end_to_end": "작업 시작에서 결과 메모 증빙 검증까지. 대기열 진입 전후의 시간과 각 조건의 동시 실행 시간은 포함하지 않음",
            "review_service": "가림 Codex 세션 관측 경과. 실행 초기화·전송·모델 응답·재시도가 포함될 수 있음",
            "active": "능동 검토 내부 시간, 네트워크만의 시간 및 인간 작업시간은 미측정",
            "shared_item": "동일 기업·항목에는 한 fresh session 원본 관측값을 두 이관 조건에 공통 적용",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="store_true", help="Run only missing arm-masked persona tasks"
    )
    parser.add_argument("--workers", type=int, default=4)
    opts = parser.parse_args(argv)
    assignments = assignment_tasks()
    ordered = schedule(assignments)
    copied = [{"case": case, "item_id": item} for case, item in ordered]
    dump(
        STORE / "task_set.json",
        {"protocol": PROTOCOL, "ordered_union": copied, "ranked_sources": assignments},
    )
    if opts.run:
        missing = [
            pair for pair in ordered if saved_task(*pair)["status"] != "REVIEWED"
        ]
        with ThreadPoolExecutor(max_workers=opts.workers) as pool:
            for result in pool.map(timed_task, missing):
                print(result["case"], result["item_id"], result["status"], flush=True)
    measured = {task: saved_task(*task) for task in ordered}
    summary = compare(assignments, copied, measured)
    summary["verified_task_evidence"] = audit_records(measured)
    dump(STORE / "timing.json", summary)
    print(f"{summary['measured_any_arm']}/{len(ordered)} distinct tasks measured")


if __name__ == "__main__":
    main()
