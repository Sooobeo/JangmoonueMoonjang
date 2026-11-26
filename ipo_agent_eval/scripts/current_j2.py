"""Prepare and execute the current original-filings and J2 item pilot."""

import argparse
import hashlib
import json
import random
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

import fitz
import httpx
from bs4 import BeautifulSoup
from jsonschema import Draft202012Validator, ValidationError
from openai import OpenAI

from ipo_eval.blind_reviewer import execute as execute_c
from ipo_eval.blind_reviewer import load_packet
from ipo_eval.runner import api_key
from ipo_eval.runner_v2 import execute_v2, output_json
from ipo_eval.runtime_v2 import RunV2, wire_dumps, write_json

from .prepare_a1_a0 import CASE, make_workspace, settings

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "data/a1_pilot"
OUTPUT = ROOT / "reports/a1_current/j2"
ISSUERS = {"HDMS": "HD현대마린솔루션", "MELCON": "멜콘"}
JUDGMENTS = ["수용", "문제 제기", "미확인"]
TRIZ_FORMS = ("original", "format_only", "process_evidence_withheld")
TERMINAL_CREDIT_CODES = {"credit_balance_exhausted", "insufficient_quota"}
TRIZ_PROMPT = """발행사와 후보의 사업 구조를 공개 자료로 독립 검토한다. 자료에 제공된 사실에 근거해 후보의 PER 비교 적합성을 수용, 문제 제기, 미확인으로 판정하라. 제품 기능, 적용 공정, 매출 구성, 고객의 근거를 구별한다. 공정이 겹친다고 판단하면 양쪽의 어떤 적용이 문서로 확인되는지 적고 확인되지 않은 부분은 남길 조건에 기록한다. 사용한 근거 ID만 인용하며 다른 공정, 회사 또는 기간에서 확대 추론하지 않는다."""


def record(fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


TEXT = {"type": "string"}
TRIZ_OUTPUT = record({
    "judgment": {"type": "string", "enum": JUDGMENTS},
    "reason": TEXT,
    "facts": {"type": "array", "items": record({"dimension": {"type": "string", "enum": [
        "제품", "적용 공정", "매출 구성", "고객", "기타"]}, "fact": TEXT,
        "evidence_refs": {"type": "array", "items": TEXT}})},
    "open_conditions": {"type": "array", "items": TEXT},
})


def read(path):
    return json.loads(path.read_bytes())


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def case_data(case):
    dossier = PILOT / case
    provenance = read(dossier / "filing/provenance.json")
    registry = read(dossier / "operator/original_items.json")
    filing = dossier / "filing" / f"{provenance['receipt_no']}.pdf"
    cutoff = provenance.get("published_kst") or provenance["published_local_date"]
    if (sha(filing.read_bytes()) != registry["source_sha256"] or
            registry["source_sha256"] != (provenance.get("pdf_sha256") or provenance.get("sha256")) or
            registry["source_receipt"] != provenance["receipt_no"]):
        raise ValueError(f"{case}: filing provenance and operator registry do not match")
    return filing, registry, cutoff, provenance


def original(case, live):
    filing, _, cutoff, _ = case_data(case)
    base = OUTPUT / "runs" / case / "a0_original"
    mode = "live" if live else "preflight"
    index = base / f"{mode}.json"
    if index.exists():
        return read(index)
    with TemporaryDirectory(prefix="ipo-current-a0-") as directory:
        workspace = Path(directory) / "workspace"
        manifest = {"issuer_name": ISSUERS[case], "cutoff_at": cutoff}
        make_workspace(workspace, manifest, [(filing.read_bytes(), cutoff)], settings())
        run_dir, summary = execute_v2(live=live, root=workspace, case_id=CASE, condition="A0")
        base.mkdir(parents=True, exist_ok=True)
        destination = base / run_dir.name
        shutil.copytree(run_dir, destination)
    result = {"case_id": case, "directory": destination.relative_to(OUTPUT).as_posix(), "summary": summary}
    write(index, result)
    return result


def compact(text):
    return "".join(text.split()).casefold()


def source_bytes(case, fact, filing):
    if "published" not in fact:
        return filing, filing.read_bytes()
    if "archive" in fact:
        path = PILOT / fact["archive"]
        return path, path.read_bytes()
    url = fact["url"]
    extension = ".pdf" if "page" in fact else ".html"
    path = OUTPUT / "source_snapshots" / case / (sha(url.encode())[:16] + extension)
    if not path.exists():
        response = httpx.get(url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    return path, path.read_bytes()


def source_index(case, plan, filing, cutoff, provenance):
    records = {}
    facts = [*plan["issuer"], *(fact for candidate in plan["candidates"] for fact in candidate["facts"])]
    for fact in facts:
        source_path, blob = source_bytes(case, fact, filing)
        when = fact.get("published")
        if when and date.fromisoformat(when) >= date.fromisoformat(cutoff[:10]):
            raise ValueError(f"{fact['id']}: prescreen requires an earlier calendar day")
        page = fact.get("page")
        if page:
            with fitz.open(stream=blob, filetype="pdf") as pdf:
                original = pdf[page - 1].get_text()
        else:
            original = BeautifulSoup(blob, "html.parser").get_text(" ", strip=True)
        if compact(fact["anchor"]) not in compact(original):
            raise ValueError(f"{fact['id']}: missing published source anchor in {source_path.name}")
        receipt = fact.get("receipt") if when else provenance["receipt_no"]
        local_url = fact.get("url")
        if local_url is None and receipt:
            local_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"
        if fact["id"] in records:
            raise ValueError(f"Duplicate evidence {fact['id']}")
        records[fact["id"]] = {
            "file": source_path.relative_to(ROOT).as_posix(), "sha256": sha(blob),
            "receipt": receipt, "url": local_url, "page": page, "published": when or cutoff,
            "published_before_cutoff": bool(when), "cutoff_basis": "earlier_date" if when else "initial_filing",
            "section": fact.get("section", "사업의 내용"), "excerpt": fact["text"],
            "source_group": receipt or sha(blob)[:16],
        }
    return records


def build_packets(case):
    filing, registry, cutoff, provenance = case_data(case)
    plan = read(OUTPUT / "public_evidence_plan.json")[case]
    known = {item["id"] for item in registry["items"]}
    if not {c["item"] for c in plan["candidates"] if c["item"]} <= known:
        raise ValueError("Candidate item absent from original-item freeze")
    records = source_index(case, plan, filing, cutoff, provenance)

    def masked(facts):
        return [{"evidence_id": row["id"], "text": row["text"]} for row in facts]

    packet = {"issuer_evidence": masked(plan["issuer"]), "candidates": [
        {"candidate_id": row["id"], "business": masked(row["facts"]), "financials": [], "multiples": []}
        for row in plan["candidates"]]}
    encoded = wire_dumps(packet).encode()
    forbidden = [ISSUERS[case], "최종 선정", "카나리", "정상 대조", "DART", *[c["name"] for c in plan["candidates"]],
                 *known, *[p["receipt"] for p in records.values() if p["receipt"]]]
    if any(compact(term) in compact(encoded.decode()) for term in forbidden):
        raise ValueError("Masked candidate packet contains operator metadata or an issuer identity")
    packet_path = OUTPUT / "packets" / f"{case}_C_original.json"
    write(packet_path, packet)
    digest = sha(packet_path.read_bytes())
    load_packet(packet_path, digest)
    private = {"case_id": case, "scope": plan["scope"], "packet_sha256": digest,
               "candidate_identity": {c["id"]: c["name"] for c in plan["candidates"]},
               "candidate_items": {c["id"]: c["item"] for c in plan["candidates"]}, "sources": records}
    write(OUTPUT / "operator" / f"{case}_sources.json", private)
    return packet_path, private


def blind(case, live, resume=False):
    packet, private = build_packets(case)
    base = OUTPUT / "runs" / case / "c_original"
    mode = "live" if live else "preflight"
    index = base / f"{mode}.json"
    if index.exists():
        prior = read(index)
        compatible = prior["packet_sha256"] == private["packet_sha256"]
        retry_after_credit = (resume and prior["summary"]["execution_status"] == "FAILED" and
                              api_error_code(OUTPUT / prior["directory"]) in TERMINAL_CREDIT_CODES)
        if compatible and not retry_after_credit:
            return prior
        if live and not retry_after_credit:
            raise ValueError("C live packet differs from the indexed request")
        write(base / f"{mode}-{prior['summary']['run_id']}.json", prior)
    directory, summary = execute_c(packet, private["packet_sha256"], case, seed=261126,
                                   mode=mode, output=base)
    result = {"case_id": case, "directory": directory.relative_to(OUTPUT).as_posix(),
              "packet_sha256": private["packet_sha256"], "summary": summary}
    write(index, result)
    return result


def triz_inputs():
    packet_path, _ = build_packets("MELCON")
    packet = read(packet_path)
    issuer = packet["issuer_evidence"]
    candidate = next(row for row in packet["candidates"] if row["candidate_id"] == "C26")["business"]
    forms = {
        "original": candidate,
        "format_only": list(reversed(candidate)),
        "process_evidence_withheld": [row for row in candidate if row["evidence_id"] != "E123"],
    }
    by_id = {row["evidence_id"]: row["text"] for row in candidate}
    invariant = {row["evidence_id"]: row["text"] for row in forms["format_only"]}
    changed = {row["evidence_id"]: row["text"] for row in forms["process_evidence_withheld"]}
    if invariant != by_id or changed != {key: value for key, value in by_id.items() if key != "E123"}:
        raise ValueError("TRIZ variants changed beyond their frozen dimensions")
    if not any("포토" in row["text"] for row in candidate) or any(
            re.search(r"포토|노광|EUV|코팅|현상", row["text"], re.IGNORECASE)
            for row in forms["process_evidence_withheld"]):
        raise ValueError("Process evidence is absent from baseline or leaks into the changed candidate excerpt")
    payloads = {name: {"question": "후보 C26의 사업 구조가 발행사의 PER 비교에 적합한가?",
                       "issuer_evidence": issuer, "candidate_evidence": evidence}
                for name, evidence in forms.items()}
    seed = 261126
    order = {}
    for role, delta in [("A0", 0), ("C", 1)]:
        order[role] = list(TRIZ_FORMS)
        random.Random(seed + delta).shuffle(order[role])
    freeze = {
        "case_id": "MELCON", "operator_item_id": "M04", "seed": seed, "order": order,
        "scope": "동일 중립 발췌의 항목 단위 독립 호출. 전체 A0/C 원판정 연결 뒤 TRIZ 적용 여부를 별도로 판단",
        "expected": {
            "original": "각 역할의 전체 원본 판정을 재현하는지 사후 확인",
            "format_only": "제시 순서만 뒤집어 판정과 핵심 공정 근거 유지 확인",
            "process_evidence_withheld": "후보의 포토 전공정 적용을 확인된 공통점에서 제거하고 필요 증빙을 밝힘. HBM 후공정·제품·고객 근거와 종합 수용을 유지할 수 있음",
        },
        "variant_sha256": {name: sha(wire_dumps(payload).encode()) for name, payload in payloads.items()},
        "prompt_sha256": sha(TRIZ_PROMPT.encode()), "output_schema_sha256": sha(wire_dumps(TRIZ_OUTPUT).encode()),
    }
    index = OUTPUT / "operator" / "M04_triz_freeze.json"
    if index.exists() and read(index) != freeze:
        raise ValueError("Frozen TRIZ specification changed")
    write(index, freeze)
    for name, packet in payloads.items():
        write(OUTPUT / "packets" / f"M04_{name}.json", packet)
    return payloads, freeze


def triz_call(role, variant, payload, contract):
    parent = OUTPUT / "runs" / "MELCON" / "triz" / role
    index = parent / f"{variant}.json"
    frozen_digest = sha(wire_dumps(payload).encode())
    if frozen_digest != contract["variant_sha256"][variant]:
        raise ValueError("TRIZ input does not match the frozen digest")
    if index.exists():
        previous = read(index)
        if previous["input_sha256"] != frozen_digest:
            raise ValueError("TRIZ indexed input differs from frozen specification")
        previous["api_error_code"] = api_error_code(OUTPUT / previous["directory"])
        return previous
    config = read(ROOT / "config" / ("A0.json" if role == "A0" else "B.json"))
    config.update(condition=f"J2_{role}_ITEM", case_id="MELCON-M04", version="current-j2-item-1",
                  max_model_calls=2, max_format_repairs=0, max_tool_calls=2,
                  max_transient_api_retries=1)
    run = RunV2(config, live=True, base_directory=parent)
    try:
        key = api_key()
        if not key:
            summary = run.finish("NOT_STARTED_MISSING_API_KEY", actual_model_answer=False)
        else:
            run.client = OpenAI(api_key=key, base_url="https://api.openai.com/v1", max_retries=0)
            request = run.base_request([{"role": "system", "content": TRIZ_PROMPT},
                                        {"role": "user", "content": wire_dumps(payload)}], 3000)
            request["text"] = {"format": {"type": "json_schema", "name": "item_business_review",
                                          "strict": True, "schema": TRIZ_OUTPUT}}
            raw = run.request("item_review", request, "ITEM_REVIEW")
            answer = output_json(raw)
            Draft202012Validator(TRIZ_OUTPUT).validate(answer)
            known = {row["evidence_id"] for key in ("issuer_evidence", "candidate_evidence") for row in payload[key]}
            cited = {ref for fact in answer["facts"] for ref in fact["evidence_refs"]}
            unknown = sorted(cited - known)
            write_json(run.directory / "item_review.json", answer)
            summary = run.finish("SUBMITTED", actual_model_answer=True, unknown_evidence_ids=unknown,
                                 uncited_fact_count=sum(not f["evidence_refs"] for f in answer["facts"]))
    except (RuntimeError, ValueError, ValidationError) as exc:
        summary = run.finish("FAILED", actual_model_answer=False, error_type=type(exc).__name__)
    result = {"role": role, "variant": variant, "directory": run.directory.relative_to(OUTPUT).as_posix(),
              "input_sha256": frozen_digest, "summary": summary, "api_error_code": api_error_code(run.directory)}
    write(index, result)
    return result


def triz(live):
    payloads, freeze = triz_inputs()
    if not live:
        return freeze

    credit_blocked = Event()
    if any(execution(case, kind, submission)[2] in TERMINAL_CREDIT_CODES for case in ISSUERS
           for kind, submission in (("a0_original", "review.json"), ("c_original", "blind_review.json"))):
        credit_blocked.set()

    def run_role(role):
        results = []
        for name in freeze["order"][role]:
            prior = OUTPUT / "runs" / "MELCON" / "triz" / role / f"{name}.json"
            if credit_blocked.is_set() and not prior.exists():
                results.append({"role": role, "variant": name, "input_sha256": freeze["variant_sha256"][name],
                                "summary": {"execution_status": "NOT_STARTED_CREDIT_EXHAUSTED", "model_calls": 0}})
                continue
            result = triz_call(role, name, payloads[name], freeze)
            results.append(result)
            if result.get("api_error_code") in TERMINAL_CREDIT_CODES:
                credit_blocked.set()
        return results

    with ThreadPoolExecutor(max_workers=2) as pool:
        groups = list(pool.map(run_role, freeze["order"]))
    results = [entry for rows in groups for entry in rows]
    write(OUTPUT / "M04_triz_runs.json", {"item_id": "M04", "runs": results})
    return {"item_id": "M04", "live_submitted": sum(row["summary"]["execution_status"] == "SUBMITTED" for row in results),
            "total_attempts": sum(row["summary"]["model_calls"] for row in results)}


def api_error_code(directory):
    errors = [read(path) for path in sorted(directory.glob("*_error.json"))]
    codes = [code for error in errors if (code := error.get("api_error_code"))]
    return next((code for code in codes if code in TERMINAL_CREDIT_CODES), codes[-1] if codes else None)


def execution(case, name, result_file):
    index = OUTPUT / "runs" / case / name / "live.json"
    if not index.exists():
        return {}, None, None
    result = read(index)
    directory = OUTPUT / result["directory"]
    summary = result["summary"]
    submission = read(directory / result_file) if summary["execution_status"] == "SUBMITTED" else None
    return result, submission, api_error_code(directory)


def original_pages(case, filing, cutoff, provenance):
    with fitz.open(filing) as pdf:
        page_texts = [" ".join(page.get_text().split()) for page in pdf]
    receipt = provenance["receipt_no"]
    prefix = "H" if case == "HDMS" else "M"

    def resolve(page):
        if not 1 <= page <= len(page_texts):
            raise ValueError(f"{case}: invalid cited page {page}")
        return f"{prefix}-P{page:04}", {"file": filing.relative_to(ROOT).as_posix(),
                                       "sha256": provenance.get("pdf_sha256") or provenance["sha256"],
                                       "receipt": receipt, "url": provenance["pdf_url"], "page": page,
                                       "published": cutoff, "published_before_cutoff": False,
                                       "cutoff_basis": "initial_filing", "section": "최초 증권신고서",
                                       "excerpt": page_texts[page - 1], "source_group": receipt}
    return resolve


def label(judgment, reason, *, raw=None, evidence=(), open_condition=None, run_id=None, status="linked"):
    return {"judgment": judgment, "reason": reason, "raw_text": raw, "evidence": list(evidence),
            "evidence_refs": sorted({ref for fact in evidence for ref in fact["source_refs"]}),
            "open_condition": open_condition, "run_id": run_id, "link_status": status}


def a0_label(item_id, case, report, links, source_for_page, source_records, run_id, error):
    if report is None:
        return label("미확인", f"A0 원본 제출 없음 ({error or '미실행'})", run_id=run_id, status="execution_missing")
    entry = links[item_id]
    original_judgment = next(row for row in report["judgments"] if row["domain"] == entry["domain"])
    claims = {row["claim_id"]: row for row in original_judgment["facts"]}
    evidence = []
    for claim_id in entry["claims"]:
        fact = claims[claim_id]
        selected = entry.get("fact_slice") or fact["text"]
        if selected not in fact["text"]:
            raise ValueError(f"{case}/{item_id}: edited A0 excerpt does not match the original response")
        references = []
        for link in fact["evidence"]:
            if entry.get("cite_pages") and link["page"] not in entry["cite_pages"]:
                continue
            expected = f"DOC-01-p{link['page']:04}"
            if link["doc_id"] != "DOC-01" or link["chunk_id"] != expected:
                raise ValueError(f"{case}/{item_id}: citation outside frozen filing corpus")
            ref, source = source_for_page(link["page"])
            source_records[ref] = source
            references.append({"source_ref": ref, "locator": link["locator"], "original_chunk_id": expected})
        if not references:
            raise ValueError(f"{case}/{item_id}: mapped A0 claim has no citation")
        evidence.append({"type": entry["type"], "fact": selected, "direction": entry["direction"],
                         "source_refs": [link["source_ref"] for link in references], "locations": references,
                         "original_claim_id": claim_id})
    return label(entry["judgment"], entry["reason"], raw=original_judgment, evidence=evidence,
                 open_condition=original_judgment["next_action"], run_id=run_id,
                 status="linked" if entry["judgment"] != "미확인" else "explicit_judgment_missing")


def c_label(candidate_id, report, source_records, run_id, error):
    if not candidate_id:
        return label("미확인", "공시 선택을 직접 알아야 하는 질문으로 C의 가림 상태에서 원본 판정과 대응하지 않는다.",
                     status="역할상 비교 불가", run_id=run_id)
    if report is None:
        return label("미확인", f"C 원본 제출 없음 ({error or '미실행'})", run_id=run_id, status="execution_missing")
    matched = [row for row in report["candidates"] if row["candidate_id"] == candidate_id]
    if len(matched) != 1:
        return label("미확인", "후보 판정 누락 또는 중복", raw=matched, run_id=run_id, status="explicit_judgment_missing")
    decision = matched[0]
    cited = decision["evidence_ids"]
    if not cited or set(cited) - set(source_records):
        return label("미확인", "가림 패킷에 연결되는 후보 판정 인용이 부족함", raw=decision, run_id=run_id,
                     status="invalid_citations")
    judgment = {"INCLUDE": "수용", "EXCLUDE": "문제 제기", "REVIEW": "미확인"}[decision["decision"]]
    dimensions = {"E101": "제품·적용 공정", "E121": "매출 구성·수익원", "E122": "고객·판매 방식",
                  "E123": "제품·적용 공정", "E124": "제품·적용 공정", "E188": "제품·적용 공정"}
    evidence = [{"type": dimensions.get(ref, "제품·적용 공정"), "fact": source_records[ref]["excerpt"],
                 "source_refs": [ref], "direction": "조건 설명" if ref in {"E101", "E124"} else
                 {"수용": "지지", "문제 제기": "약화", "미확인": "조건 설명"}[judgment]} for ref in cited]
    open_condition = ("HBM 후공정 매출과 배수 적용 전 동기간 재무 조건 확인" if candidate_id == "C26" else None)
    return label(judgment, decision["reason"], raw=decision, evidence=evidence,
                 open_condition=open_condition, run_id=run_id)


def paired(a0, c):
    if "미확인" in {a0["judgment"], c["judgment"]}:
        return "미확인 포함"
    if a0["judgment"] != c["judgment"]:
        return "판단 갈림"
    return "양쪽 수용" if a0["judgment"] == "수용" else "양쪽 문제 제기"


def labels(destination=None, annotations=None, official=False):
    destination = destination or OUTPUT / "labels.json"
    annotations = annotations or {}
    mappings = read(OUTPUT / "a0_item_links.json")
    cases = []
    names = {"H01": "J1 이익의 기간과 귀속", "H06": "J3 배수 집계", "H07": "J3 기준주가 선택",
             "H08": "J3 시세·배수 입력", "H09": "J3 주식 수", "H10": "J3 주당 평가가액", "H11": "J3 할인율",
             "M01": "J1 이익의 기간과 귀속", "M02": "J1 이익 조정", "M05": "J1 이익의 기간과 귀속",
             "M06": "J3 배수 집계", "M07": "J3 기준주가 선택", "M08": "J3 시세·배수 입력",
             "M09": "J3 주식 수", "M10": "J3 주당 평가가액", "M11": "J3 할인율"}
    for case in ISSUERS:
        filing, registry, cutoff, provenance = case_data(case)
        _, private = build_packets(case)
        a0_run, a0_report, a0_error = execution(case, "a0_original", "review.json")
        c_run, c_report, c_error = execution(case, "c_original", "blind_review.json")
        if official:
            for run in (a0_run, c_run):
                summary = run.get("summary", {})
                if not (summary.get("execution_status") == "SUBMITTED" and summary.get("mode") == "LIVE"
                        and summary.get("actual_model_answer") is True and summary.get("model") == "gpt-6.1-terra"
                        and set(summary.get("returned_models", [])) == {"gpt-6.1-terra"}):
                    raise ValueError(f"{case}: official bundle requires saved Terra A0 and C submissions")
            if c_run["packet_sha256"] != private["packet_sha256"]:
                raise ValueError(f"{case}: paid C request does not match the current frozen packet")
        fetch_page = original_pages(case, filing, cutoff, provenance)
        source_records = dict(private["sources"])
        item_to_candidate = {item: candidate for candidate, item in private["candidate_items"].items() if item}
        item_rows = []
        for original_item in registry["items"]:
            item_id = original_item["id"]
            candidate_id = item_to_candidate.get(item_id)
            pages = [original_item["page"], *original_item.get("also", original_item.get("pages", []))]
            original_refs = []
            for page in dict.fromkeys(pages):
                source_id, source = fetch_page(page)
                source_records[source_id] = source
                original_refs.append(source_id)
            a0 = a0_label(item_id, case, a0_report, mappings[case], fetch_page, source_records,
                          a0_run.get("summary", {}).get("run_id"), a0_error)
            c = c_label(candidate_id, c_report, private["sources"], c_run.get("summary", {}).get("run_id"), c_error)
            annotation = annotations.get(case, {}).get(item_id)
            if annotation:
                if (c["run_id"] != annotation["run_id"] or c["raw_text"]["decision"] != "REVIEW"
                        or annotation["source_ref"] not in c["evidence_refs"]):
                    raise ValueError(f"{case}/{item_id}: reason-based review annotation no longer matches source")
                c["judgment"] = "문제 제기"
                c["annotation"] = annotation["reason"]
                c["open_condition"] = annotation["open_condition"]
                for fact in c["evidence"]:
                    if annotation["source_ref"] in fact["source_refs"]:
                        fact["direction"] = "약화"
            question = (f"후보 {candidate_id}의 제품·공정·고객·매출 구조는 발행사의 PER 비교에 적합한가?"
                        if candidate_id else f"공시의 ‘{original_item['label']}’ 선택을 뒷받침할 근거가 충분한가?")
            item_rows.append({"item_id": item_id, "label": original_item["label"],
                              "question_type": names.get(item_id, "J2 사업 비교 적합성"),
                              "target_id": candidate_id, "question": question, "original_source_refs": original_refs,
                              "alternative": original_item["alternative"], "a0": a0, "c": c, "pair_status": paired(a0, c),
                              "comparison_status": "비교 가능" if candidate_id else "역할상 비교 불가",
                              "comparison_scope_note": ("워트 THC 비중의 A0 인용은 2025년 온기이고 C 인용은 2026년 반기다."
                                                        if item_id == "M04" else None)})
        if set(mappings[case]) != {row["item_id"] for row in item_rows}:
            raise ValueError(f"{case}: mapping does not cover exactly the frozen item list")
        if len(item_rows) != 11:
            raise ValueError(f"{case}: unexpected item count")
        triz_runs = OUTPUT / "M04_triz_runs.json"
        triz_note = ({"item_id": "M04", "status": "적용 불가", "reason": "전체 원본에서 A0가 워트 개별 사업 적합성을 명시 수용하지 않아 수용 합의가 성립하지 않았다. 분리 발췌는 시험 입력 타당성 점검에 보존했다.",
                     "live_submitted": sum(r["summary"]["execution_status"] == "SUBMITTED" for r in read(triz_runs)["runs"])
                     if triz_runs.exists() else 0, "runs_path": "M04_triz_runs.json" if triz_runs.exists() else None}
                    if case == "MELCON" else None)
        cases.append({"case_id": case, "cutoff": cutoff, "items": item_rows, "sources": source_records,
                      "c_exploratory_proposals": ({k: c_report[k] for k in ("earnings", "aggregation")} if c_report else {}),
                      "triz": [triz_note] if triz_note else [], "c_scope": private["scope"],
                      "a0_run": a0_run, "c_run": c_run, "a0_api_error": a0_error, "c_api_error": c_error})
    output = {"schema_version": "current-j2-original-labels-1", "cases": cases}
    if official:
        output["run_cohort"] = "dev_terra_responses_api"
    write(destination, output)
    return {"cases": len(cases), "items": sum(len(case["items"]) for case in cases), "file": destination.name}


def audit():
    model_data = read(OUTPUT / "labels.json")
    case_reviews = []
    for case in model_data["cases"]:
        case_id = case["case_id"]
        filing, _, _, _ = case_data(case_id)
        a0 = case["a0_run"]
        if a0:
            a0_dir = OUTPUT / a0["directory"]
            isolated = read(a0_dir / "input_hashes.json")
            pdf_hashes = {digest for name, digest in isolated.items() if name.endswith(".pdf")}
            if pdf_hashes != {sha(filing.read_bytes())} or any(re.search(r"operator|human|grade", name) for name in isolated):
                raise ValueError(f"{case_id}: isolated A0 run exposed other inputs")
        c = case["c_run"]
        if c:
            c_dir = OUTPUT / c["directory"]
            old_hash = c["packet_sha256"]
            packets = sorted((OUTPUT / "packets").glob(f"{case_id}_C_original*.json"))
            submitted_packet = next(packet for packet in packets if sha(packet.read_bytes()) == old_hash)
            request = read(c_dir / "blind_request.json")
            if json.loads(request["input"]) != read(submitted_packet):
                raise ValueError(f"{case_id}: sent C payload differs from the archived masked packet")
        for item in case["items"]:
            refs = {*item["original_source_refs"], *item["a0"]["evidence_refs"], *item["c"]["evidence_refs"]}
            if refs - case["sources"].keys():
                raise ValueError(f"{case_id}/{item['item_id']}: missing source reference")
            if item["c"]["link_status"] == "역할상 비교 불가" and item["c"]["evidence_refs"]:
                raise ValueError(f"{case_id}/{item['item_id']}: inapplicable C opinion was linked")
        case_reviews.append({"case_id": case_id, "items": len(case["items"]),
                             "source_refs_resolve": True, "a0_input_isolation_confirmed": bool(a0),
                             "c_sent_packet_replayed": bool(c),
                             "c_packet_for_next_use_sha256": sha((OUTPUT / "packets" /
                                                                  f"{case_id}_C_original.json").read_bytes())})
    payloads, freeze = triz_inputs()
    # This check exercises input and source references only. No model decision
    # or expected reaction is credited as a real trial result.
    local_results = {}
    for name, payload in payloads.items():
        refs = {row["evidence_id"] for row in payload["candidate_evidence"]}
        local_results[name] = {"candidate_evidence_refs": sorted(refs),
                               "photo_evidence_available": "E123" in refs,
                               "hbm_evidence_available": "E124" in refs,
                               "input_sha256": freeze["variant_sha256"][name]}
    check = {"run_type": "offline_contract_and_source_check", "model_calls": 0,
             "original_cases": case_reviews, "M04": local_results}
    write(OUTPUT / "local_checks.json", check)
    return {"case_reviews": len(case_reviews), "triz_inputs_checked": len(local_results), "model_calls": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    original_parser = commands.add_parser("original")
    original_parser.add_argument("case", choices=ISSUERS)
    original_parser.add_argument("--live", action="store_true")
    for name in ("prepare", "blind"):
        child = commands.add_parser(name)
        child.add_argument("case", choices=ISSUERS)
        if name == "blind":
            child.add_argument("--live", action="store_true")
            child.add_argument("--resume-after-credit", action="store_true",
                               help="Preserve the blocked attempt and make a fresh live run after funding is restored")
    trial = commands.add_parser("triz")
    trial.add_argument("--live", action="store_true")
    label_parser = commands.add_parser("labels")
    label_parser.add_argument("--output", type=Path)
    label_parser.add_argument("--annotations", type=Path)
    label_parser.add_argument("--official", action="store_true")
    commands.add_parser("audit")
    commands.add_parser("key-configured")
    args = parser.parse_args(argv)
    if args.command == "key-configured":
        print({"api_key_configured": bool(api_key())})
    elif args.command == "prepare":
        _, private = build_packets(args.case)
        print(json.dumps(private["packet_sha256"]))
    elif args.command == "triz":
        print(json.dumps(triz(args.live), ensure_ascii=False))
    elif args.command == "labels":
        if args.official and args.output is None:
            parser.error("--official requires a separate --output path")
        print(json.dumps(labels(args.output, read(args.annotations) if args.annotations else None, args.official),
                         ensure_ascii=False))
    elif args.command == "audit":
        print(json.dumps(audit(), ensure_ascii=False))
    elif args.command == "blind":
        if args.resume_after_credit and not args.live:
            parser.error("--resume-after-credit requires --live")
        result = blind(args.case, args.live, args.resume_after_credit)
        print(json.dumps(result, ensure_ascii=False))
    else:
        result = original(args.case, args.live)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
