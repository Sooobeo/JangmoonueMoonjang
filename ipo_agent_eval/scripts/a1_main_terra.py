"""37-issuer Terra selection, gated by the main freeze and append-only ledger."""

import argparse
import asyncio
import json
import os
import re
import sqlite3
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Event

import httpx
import tiktoken
from jsonschema import ValidationError, validate
from openai import OpenAI

from ipo_eval.a1_main_ledger import LIMITS, Ledger, StageFailure, StopBatch, sha
from ipo_eval.agent_loop import output_json
from ipo_eval.blind_reviewer import PACKET
from ipo_eval.runner import api_key
from ipo_eval.runtime_v2 import wire_dumps
from scripts.current_b import ROOT
from scripts.current_selector import DECISION, LOOK, PROMPT, rule_table
from scripts.validation_roles import A0_PROMPT, proxy_schema, verify_role_answer

BASE = ROOT / "reports/a1_main/v1"
ROSTER = ROOT / "reports/a1_current/official/enrollment_expansion/roster.json"
ROSTER_SHA = "438e093bf95505b2e00fd8a42b76c6b3c553eaeff5bfeb572c6eac5cfc35ab9f"
LOOK_PROMPT = (
    "공시 심사에서 원문을 더 읽을 쪽만 고른다. 목록에서 서로 판단이 갈리거나 확인이 필요한 항목의 "
    "관련 물리 쪽을 합계 0~4개 반환한다. reason에는 선택 근거를 한 문장으로 쓴다."
)
C_SUFFIX = "\n방법별 범주에는 제안에서 선택한 내용을 기입한다. 해당 자료가 지지하지 않으면 UNKNOWN이다. EPS와 재무비율을 계산할 자료가 없으면 가격을 추정하지 않는다. 각 후보 판정에 그 후보의 근거 ID를 포함한다. 회사명과 후보의 포함·제외 이력 추정은 금지한다."
FINGERPRINTS = {
    "A0": (
        "a985080af50a8ce363f2a715437cdb3d0831b14348dd4e7b4e4d49a7a75b2ea9",
        "c69dc30da9004bea24bd076da423668fedbe9c3324b77ea7b41d339770a479fb",
    ),
    "C": (
        "d6a70da018ab4922300cd63fe7c7513452c8cfde48b4a7d77cdd48dd5007c701",
        "514b212212ceaf53ffb00093fafe7a4adad8f0b367ab84fcb61131cdf86cc729",
    ),
    "A1_LOOK": (
        "90b48aa8126ee366694a83e57f56f38f4eed1da0beada5808e0a926ae2f3005b",
        "7f7395d79b36eda04d1c685ff54394d71ca7545fba26fe3adb0cdafd5e9cae60",
    ),
    "A1_SELECT": (
        "efc8851e8a98c23348447eac519f9a097c7d8f86b1b46dc8ccd0af3161ea0abe",
        "264d5db99b473a4d7954992bbf5408171a24a5a74b10872b7ac7ef8856d72f96",
    ),
}
MODEL = "gpt-6.1-terra"
REQUIRED = ("a0", "items", "b", "catalog", "c", "c_private", "c_status")


def input_keys(decision):
    if decision["terra_ready"]:
        if not decision.get("a0_ready", True) or not decision.get("c_ready", True):
            raise StopBatch("inconsistent_issuer_readiness")
        return REQUIRED
    keys = []
    if decision.get("a0_ready"):
        keys.extend(("items", "a0"))
    if decision.get("c_ready"):
        keys.extend(("items", "c", "c_status", "c_private"))
    return tuple(dict.fromkeys(keys))


def contracts():
    c_prompt = (ROOT / "prompts/blind_reviewer.md").read_text(
        encoding="utf8"
    ) + C_SUFFIX
    specs = {
        "A0": (A0_PROMPT, proxy_schema("A0")),
        "C": (c_prompt, proxy_schema("C")),
        "A1_LOOK": (LOOK_PROMPT, LOOK),
        "A1_SELECT": (PROMPT, DECISION),
    }
    for key, (prompt, schema) in specs.items():
        packed = json.dumps(
            schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        if (sha(prompt.encode()), sha(packed)) != FINGERPRINTS[key]:
            raise StopBatch("prompt_or_schema_drift:" + key)
    return specs


def lock_json(path, value):
    """Publish immutable bytes after fsync. A replay must reproduce the same file."""
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        try:
            os.link(temp, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise StopBatch("immutable_artifact_changed:" + str(path))
    finally:
        temp.unlink()
    return sha(data)


def load_freeze(path):
    if path.resolve() != (BASE / "freeze.json").resolve():
        raise StopBatch("unexpected_freeze_location")
    data = path.read_bytes()
    if (
        sha(data)
        != (BASE / "freeze.sha256").read_text(encoding="utf8").strip().split()[0]
    ):
        raise StopBatch("freeze_hash_mismatch")
    manifest = json.loads(data)
    roster_bytes = ROSTER.read_bytes()
    receipts = [row["receipt"] for row in json.loads(roster_bytes)["rows"]]
    if (
        sha(roster_bytes) != ROSTER_SHA
        or manifest["protocol"] != "a1-main-v1"
        or manifest["roster_sha256"] != ROSTER_SHA
        or len(receipts) != 37
        or set(receipts) != set(manifest["issuers"])
    ):
        raise StopBatch("roster_or_protocol_mismatch")
    files = {}
    for name, digest in manifest["files"].items():
        file = (ROOT / name).resolve()
        if (
            not file.is_relative_to(ROOT.parent)
            or file in files
            or sha(file.read_bytes()) != digest
        ):
            raise StopBatch("frozen_file_drift:" + name)
        files[file] = digest
    dependencies = [
        Path(__file__),
        ROOT / "ipo_eval/a1_main_ledger.py",
        ROSTER,
        ROOT / "prompts/blind_reviewer.md",
        ROOT / "scripts/current_selector.py",
        ROOT / "scripts/validation_roles.py",
    ]
    for receipt in receipts:
        keys = input_keys(manifest["issuers"][receipt])
        dependencies.extend(
            BASE / "issuers" / receipt / (key + ".json") for key in keys
        )
    missing = [str(p) for p in dependencies if p.resolve() not in files]
    if missing:
        raise StopBatch("unfrozen_dependencies:" + str(missing))
    return sha(data), receipts, manifest["issuers"], files


class Transport:
    def __init__(self):
        key = api_key()
        if not key:
            raise StopBatch("missing_project_api_key")
        # Reuse the pilot's API endpoint and account selection. Send the bytes
        # already recorded in the ledger. The HTTP transport performs zero retries.
        with OpenAI(api_key=key, max_retries=0) as sdk:
            self.url = str(sdk.base_url).rstrip("/") + "/responses"
            self.headers = {
                k: v for k, v in sdk.default_headers.items() if isinstance(v, str)
            }
            self.headers["Content-Type"] = "application/json"

    def __call__(self, wire, timeout):
        async def send():
            async with httpx.AsyncClient(
                follow_redirects=False, timeout=timeout
            ) as client:
                response = await client.post(
                    self.url, content=wire, headers=self.headers
                )
                metadata = {
                    k: v
                    for k, v in response.headers.items()
                    if k
                    in {
                        "x-request-id",
                        "openai-version",
                        "openai-processing-ms",
                        "x-ms-deployment-name",
                        "openai-model",
                        "x-model-deployment-id",
                    }
                }
                return response.status_code, response.content, metadata

        async def bounded():
            return await asyncio.wait_for(send(), timeout)

        return asyncio.run(bounded())


class Assessor:
    def __init__(self, ledger, transport, admitted=None, halted=None):
        self.ledger = ledger
        self.transport = transport
        self.specs = contracts()
        self.encoder = tiktoken.get_encoding("o200k_base")
        self.admitted = admitted
        self.halted = halted

    def run(self, receipt, stage, packet, validator):
        prompt, schema = self.specs[stage]
        request = {
            "model": MODEL,
            "reasoning": {"effort": "medium"},
            "store": False,
            "service_tier": "default",
            "max_output_tokens": LIMITS[stage][0],
            "instructions": prompt,
            "input": wire_dumps(packet),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "assessment",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        prior = self.ledger.history(receipt, stage)
        elapsed_before = sum(r["elapsed"] or 0 for r in prior)
        start = time.monotonic()
        repair = retry = False
        kind = "initial"
        for n in range(LIMITS[stage][1] + 1):
            wire = wire_dumps(request).encode()
            if n < len(prior):
                record = prior[n]
                if (
                    record["request_hash"] != sha(wire)
                    or record["request"] != wire
                    or record["kind"] != kind
                ):
                    raise StopBatch("replay_request_drift")
            else:
                estimated = (
                    len(self.encoder.encode(wire.decode(), disallowed_special=())) + 800
                )
                remaining = (
                    LIMITS[stage][4] - elapsed_before - (time.monotonic() - start)
                )
                if remaining <= 0:
                    raise StageFailure("stage_time_cap")
                if self.halted is not None and self.halted.is_set():
                    raise StopBatch("stopped_by_peer")
                identifier = self.ledger.reserve(
                    receipt, stage, n, wire, estimated, kind
                )
                if self.admitted is not None:
                    self.admitted.set()
                t = time.monotonic()
                status, body, error, headers = None, b"", None, {}
                try:
                    status, body, *metadata = self.transport(wire, remaining)
                    if metadata:
                        headers = metadata[0]
                except (httpx.HTTPError, TimeoutError, OSError) as exc:
                    error = type(exc).__name__
                self.ledger.finish(
                    identifier, time.monotonic() - t, status, body, error, headers
                )
                record = self.ledger.history(receipt, stage)[n]
            if not record["finished"]:
                raise StageFailure("interrupted_attempt_unknown_usage")
            if sha(record["body"]) != record["body_hash"]:
                raise StopBatch("response_hash_mismatch")
            self.ledger.verify_caps(receipt, stage)
            if record["blocked"]:
                if record["resumed"]:
                    kind = "billing_resume"
                    continue
                raise StopBatch("billing_suspended")
            if record["error"] == "model_not_found":
                raise StopBatch("required_model_unavailable")
            if not record["status"] or not 200 <= record["status"] < 300:
                if (
                    record["status"] in (500, 502, 503, 504)
                    and not retry
                    and record["error"]
                    not in {"rate_limit_exceeded", "insufficient_quota"}
                ):
                    retry, kind = True, "transient_retry"
                    continue
                raise StageFailure(
                    f"http_or_transport_failure:{record['status']}:{record['error']}"
                )
            if record["actual_input"] is None:
                raise StageFailure("response_usage_unknown")
            raw = json.loads(record["body"])
            if raw.get("status") != "completed":
                raise StageFailure("incomplete:" + str(raw.get("incomplete_details")))
            if raw.get("model") != MODEL and not re.fullmatch(
                re.escape(MODEL) + r"-\d{4}-\d{2}-\d{2}", raw.get("model") or ""
            ):
                raise StopBatch("returned_model_mismatch")
            if not raw.get("id") or any(
                item.get("type") not in {"reasoning", "message"}
                or any(c.get("type") == "refusal" for c in item.get("content", []))
                for item in raw.get("output", [])
            ):
                raise StageFailure("refusal_or_unexpected_output")
            history = self.ledger.history(receipt, stage)
            elapsed = sum(r["elapsed"] or 0 for r in history[: n + 1])
            if elapsed > LIMITS[stage][4]:
                raise StageFailure("stage_time_cap")
            try:
                answer = output_json(raw)
                validate(answer, schema)
                validator(answer)
            except (ValueError, RuntimeError, ValidationError) as exc:
                if stage == "A1_LOOK" or repair:
                    raise StageFailure("response_contract:" + str(exc)[:250]) from exc
                previous = [
                    c.get("text", "")
                    for i in raw.get("output", [])
                    for c in i.get("content", [])
                ]
                request = {
                    **request,
                    "input": wire_dumps(
                        {
                            "input": packet,
                            "prior_submission": previous,
                            "contract_issue": str(exc)[:400],
                        }
                    ),
                }
                repair, retry, kind = True, False, "format_repair"
                continue
            return {
                "answer": answer,
                "id": raw["id"],
                "seconds": elapsed,
                "attempt": record["id"],
                "wire_sha256": record["request_hash"],
                "response_sha256": record["body_hash"],
            }
        raise StageFailure("stage_attempt_cap")


def read(path):
    return json.loads(path.read_bytes())


def c_sources(packet):
    result = {r["evidence_id"]: r["text"] for r in packet["issuer_evidence"]}
    if len(result) != len(packet["issuer_evidence"]):
        raise StopBatch("duplicate_C_issuer_evidence_id")
    for candidate in packet["candidates"]:
        for row in candidate["business"] + candidate["financials"]:
            if row["evidence_id"] in result:
                raise StopBatch("duplicate_C_source_id")
            result[row["evidence_id"]] = row["text"]
    return result


def check_c(packet, answer):
    # Financials are allowed sources in the main protocol as well as business excerpts.
    both = [
        {**c, "business": c["business"] + c["financials"]} for c in packet["candidates"]
    ]
    verify_role_answer("C", {**packet, "candidates": both}, answer)
    if any(not r["reason"].strip() for r in answer["candidates"]):
        raise ValueError("missing_candidate_reason")


def check_a0(items, packet, answer):
    verify_role_answer("A0", packet, answer)
    pages = {r["id"]: r["pages"] for r in items}
    for row in answer["items"]:
        if (
            row["physical_page"] not in pages[row["item_id"]]
            or not row["reason"].strip()
        ):
            raise ValueError("invalid_item_page_or_reason:" + row["item_id"])


def check_inputs(receipt, data):
    items = data["items"]
    ids = [row["id"] for row in items]
    if (
        len(ids) < 7
        or len(set(ids)) != len(ids)
        or not all(i.startswith(receipt + "-") for i in ids)
    ):
        raise StopBatch("frozen_registry_mismatch")
    if "a0" in data:
        a0 = data["a0"]
        if (
            set(a0) != {"items", "original_physical_pages"}
            or [r["item_id"] for r in a0["items"]] != ids
        ):
            raise StopBatch("frozen_A0_mismatch")
    if "catalog" in data:
        cat = data["catalog"]["pages"]
        for row in items:
            if not row["pages"] or any(str(p) not in cat for p in row["pages"]):
                raise StopBatch("catalog_missing_item_pages")
    if "b" in data:
        b = data["b"]
        if (
            not set(b["mandatory"]).issubset(ids)
            or len(set(b["mandatory"])) != len(b["mandatory"])
            or set(b["price_impact_fraction"]) - set(ids)
            or any(x is not None and x < 0 for x in b["price_impact_fraction"].values())
        ):
            raise StopBatch("B_and_registry_mismatch")
    if "c" not in data:
        return
    c = data["c"]
    if not data["c_status"]["ready"] or set(c) != {"issuer_evidence", "candidates"}:
        raise StopBatch("C_gate_or_blinding")
    packet_schema = {
        **PACKET,
        "properties": {
            **PACKET["properties"],
            "candidates": {**PACKET["properties"]["candidates"], "minItems": 0},
        },
    }
    validate(c, packet_schema)
    if any(len(r["business"]) > 2 or len(r["financials"]) > 2 for r in c["candidates"]):
        raise StopBatch("C_excerpt_count")
    excerpts = c_sources(c).values()
    if any(
        len(r["text"]) > 350
        for candidate in c["candidates"]
        for r in candidate["business"] + candidate["financials"]
    ) or any(
        re.search(r"https?://|file://|(?<!\d)\d{14}(?!\d)", s, re.IGNORECASE)
        or any(i in s for i in ids)
        for s in excerpts
    ):
        raise StopBatch("C_excerpt_or_metadata_leak")
    links = data["c_private"]["links"]
    if (
        set(links) != {r["candidate_id"] for r in c["candidates"]}
        or len(c["candidates"]) != len(links)
        or any(
            not candidate["business"] or candidate["multiples"]
            for candidate in c["candidates"]
        )
        or any(v.get("item_id") and v["item_id"] not in ids for v in links.values())
    ):
        raise StopBatch("C_mapping_or_packet_mismatch")
    originals = [r["item_id"] for r in links.values() if r.get("item_id")]
    if len(set(originals)) != len(originals) or (
        originals and len(originals) == len(links)
    ):
        raise StopBatch("C_mapping_or_supplementary_absent")


def merge(data, role, audit):
    items = data["items"]
    issuer_refs = {e["evidence_id"] for e in data["c"]["issuer_evidence"]}
    sources = c_sources(data["c"])
    a0 = {r["item_id"]: r for r in role["A0"]["answer"]["items"]}
    blind = role["C"]["answer"]
    decisions = {r["candidate_id"]: r for r in blind["candidates"]}
    by_item = {
        v["item_id"]: decisions[cid]
        for cid, v in data["c_private"]["links"].items()
        if v.get("item_id")
    }
    combined = []
    for n, row in enumerate(items):
        key = row["id"]
        a = a0[key]
        ref = f"A{n + 1:02}"
        if ref in sources:
            raise StopBatch("A0_C_source_collision")
        sources[ref] = a["quote"]
        c = {
            "state": "미확인",
            "reason": "역할상 비교 불가",
            "comparable": False,
            "evidence_ids": [],
        }
        if n < 2 or key in by_item:
            proposal = (
                by_item[key]
                if key in by_item
                else blind["methods"][("period", "attribution")[n]]
            )
            audit_row = audit[key]
            c.update(
                native=proposal,
                reason=proposal["reason"],
                evidence_ids=proposal["evidence_ids"],
            )
            if audit_row["status"] != "verified":
                c["limit"] = (
                    "인용 불일치"
                    if audit_row["status"] == "citation_mismatch"
                    else "조건부 응답"
                    if audit_row["status"] == "conditional"
                    else "자료 부족"
                )
            elif key in by_item:
                c.update(
                    state={
                        "INCLUDE": "수용",
                        "EXCLUDE": "문제 제기",
                        "REVIEW": "미확인",
                    }[proposal["decision"]],
                    comparable=True,
                )
            elif (
                proposal["choice"] not in {"OTHER", "UNKNOWN"}
                and row.get("original_category") not in {None, "OTHER", "UNKNOWN"}
                and issuer_refs.intersection(proposal["evidence_ids"])
            ):
                c.update(
                    state="수용"
                    if row["original_category"] == proposal["choice"]
                    else "문제 제기",
                    comparable=True,
                )
            else:
                c["limit"] = "자료 부족"
        elif row["family"] == "J2":
            c["reason"] = "자료 부족"
        # The initial excerpt contains the first direct page of each item.
        # Later physical pages enter the selector only through its single lookup.
        item_refs = []
        for e in row["evidence"]:
            if e["page"] != row["pages"][0]:
                continue
            eid = e["id"]
            if eid in sources and sources[eid] != e["quote"]:
                raise StopBatch("item_source_collision")
            item_refs.append(eid)
            sources[eid] = e["quote"]
        combined.append(
            {
                "item_id": key,
                "question": row["question"],
                "question_type": row["family"],
                "original_evidence_ids": item_refs,
                "target": row["target"],
                "original_choice": row.get("original_choice"),
                "a0": {**a, "evidence_ids": [ref], "comparable": True},
                "c": c,
            }
        )
    return combined, sources


def allocate(rows, mandatory):
    eligible = [r["item_id"] for r in rows if r["eligible"]]
    return {
        "items": rows,
        "fixed_k": mandatory + [r["item_id"] for r in rows[:1]],
        "operational": mandatory + eligible[:1],
        "waiting": eligible[1:],
    }


def check_look(pages, answer):
    picks = answer["physical_pages"]
    if len(picks) > 4 or len(set(picks)) != len(picks) or not set(picks) <= set(pages):
        raise ValueError("Use at most four unique allowed physical pages")


def check_select(ids, cite, answer):
    rows = answer["items"]
    if len(rows) != len(ids) or {r["item_id"] for r in rows} != set(ids):
        raise ValueError("exactly one row per original ID required")
    for row in rows:
        if (
            not set(row["evidence_ids"]) <= cite
            or not row["reason"].strip()
            or row["action"] != "자료 요청"
            and not row["evidence_ids"]
            or row["action"] != "기록 보관"
            and not row["question_or_request"].strip()
        ):
            raise ValueError(
                "invalid citation, rationale, or question: " + row["item_id"]
            )


def rank(receipt, data, items, sources, assessor, folder):
    b = data["b"]
    mandatory, impacts = b["mandatory"], b["price_impact_fraction"]
    index = {r["id"]: r["pages"] for r in data["items"]}
    pages = {int(k): v for k, v in data["catalog"]["pages"].items()}
    initial = {ps[0] for ps in index.values()}
    allowed = {**sources, **{f"PDF-{p}": pages[p] for p in sorted(initial)}}
    rules = allocate(rule_table(items, allowed, impacts, mandatory)["items"], mandatory)
    lock_json(folder / "rule.json", rules)
    catalog = [
        {
            "id": r["item_id"],
            "question": r["question"],
            "a0": r["a0"]["state"],
            "c": r["c"]["state"],
            "a0_reason": r["a0"]["reason"][:180],
            "c_reason": r["c"]["reason"][:180],
            "pages": index[r["item_id"]],
        }
        for r in items
    ]
    lookup = assessor.run(
        receipt,
        "A1_LOOK",
        {"item_catalog": catalog, "available_pages": sorted(pages), "triz": []},
        lambda a: check_look(pages, a),
    )
    picks = lookup["answer"]["physical_pages"]
    added = {f"PDF-{p}": pages[p] for p in picks}
    selection = {
        "original_items": items,
        "original_sources": allowed,
        "b_record": b,
        "original_price_impacts": impacts,
        "physical_page_index": index,
        "materiality": "공개 근거가 선택을 바꿀 가능성 또는 적격 대안 5% 이상. 민감도 단독은 불충분.",
        "triz": [],
        "mandatory": mandatory,
        "additional_k": 1,
        "additional_read": added,
    }
    cite = set(allowed) | set(added)
    output = assessor.run(
        receipt, "A1_SELECT", selection, lambda a: check_select(index, cite, a)
    )
    rows = sorted(
        output["answer"]["items"], key=lambda r: (-r["priority"], r["item_id"])
    )
    ai = allocate(
        [
            {**r, "tie_key": str(r["priority"]), "eligible": r["action"] == "사람 검토"}
            for r in rows
            if r["item_id"] not in mandatory
        ],
        mandatory,
    )
    return {
        "case": receipt,
        "selector_condition": "TERRA",
        "mandatory": mandatory,
        "common_item_count": len(items),
        "rule": rules,
        "ai": ai,
        "triz": [],
        "lookup_pages": picks,
        "initial_refs": sorted(allowed),
        "lookup_refs": list(added),
        "presented_refs": sorted(cite),
        "lookup_run": lookup["attempt"],
        "decision_run": output["attempt"],
        "selector_seconds": lookup["seconds"] + output["seconds"],
    }


def run_roles(receipt, data, assessor, folder):
    check_inputs(receipt, data)
    roles = {}
    errors = {}
    validators = {
        "a0": lambda a: check_a0(data["items"], data["a0"], a),
        "c": lambda a: check_c(data["c"], a),
    }
    for name, verify in validators.items():
        if name not in data:
            continue
        key = name.upper()
        try:
            roles[key] = assessor.run(receipt, key, data[name], verify)
            lock_json(folder / (key + ".json"), roles[key])
        except StopBatch:
            raise
        except StageFailure as exc:
            errors[key] = str(exc)
    if errors:
        lock_json(
            folder / "role_failures.json", {"failures": errors, "successful": roles}
        )
        raise StageFailure("common_input_failure:" + str(errors))
    return roles


def run_case(receipt, data, assessor, folder, roles_only):
    roles = run_roles(receipt, data, assessor, folder)
    if roles["A0"]["id"] == roles["C"]["id"]:
        raise StopBatch("role_response_id_collision")
    digest = lock_json(folder / "roles.json", roles)
    needed = [r["id"] for r in data["items"][:2]]
    needed.extend(
        v["item_id"] for v in data["c_private"]["links"].values() if v.get("item_id")
    )
    template = {
        "roles_sha256": digest,
        "records": {i: {"status": None, "reason": ""} for i in needed},
    }
    lock_json(folder / "audit_template.json", template)
    audit_path = folder / "role_audit.json"
    if roles_only or not audit_path.exists():
        return "awaiting_blind_role_source_review"
    audit = read(audit_path)
    records = audit["records"]
    if (
        audit["roles_sha256"] != digest
        or set(records) != set(needed)
        or any(
            r.get("status")
            not in {"verified", "insufficient", "conditional", "citation_mismatch"}
            or not r.get("reason", "").strip()
            for r in records.values()
        )
    ):
        raise StopBatch("role_source_review_contract")
    lock_json(folder / "role_audit_locked.json", audit)
    items, sources = merge(data, roles, records)
    lock_json(folder / "merged.json", {"items": items, "sources": sources})
    result = rank(receipt, data, items, sources, assessor, folder)
    lock_json(folder / "ranking.json", result)
    return "rankings_locked"


def ordered_issuers(receipts, workers, process):
    """Admit the first new reservation in roster order and drain in-flight work on a pause."""
    if not 1 <= workers <= 4 or len(set(receipts)) != len(receipts):
        raise ValueError("Expected up to four workers and distinct roster entries")
    halted = Event()

    def worker(receipt, admitted):
        try:
            if not halted.is_set():
                return process(receipt, admitted, halted)
        except BaseException:
            halted.set()
            raise
        finally:
            # A cache-only or ineligible issuer also releases the next roster entry.
            admitted.set()

    pending = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        try:
            for receipt in receipts:
                if halted.is_set():
                    break
                admitted = Event()
                pending.append(pool.submit(worker, receipt, admitted))
                admitted.wait()
            # Keep the first substantive cause even if an earlier roster entry saw
            # another worker's pause while it was about to make its next request.
            errors = [f.exception() for f in pending if f.exception() is not None]
            if errors:
                raise next(
                    (e for e in errors if str(e) != "stopped_by_peer"), errors[0]
                )
        finally:
            halted.set()


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--freeze", type=Path)
    cli.add_argument("--preflight", action="store_true")
    cli.add_argument("--roles-only", action="store_true")
    cli.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    cli.add_argument("--resume-billing", action="store_true")
    args = cli.parse_args(argv)
    contracts()
    if args.preflight and not args.freeze:
        print(json.dumps(FINGERPRINTS, indent=2))
        return
    if not args.freeze:
        cli.error("--freeze is required to execute")
    digest, receipts, decisions, files = load_freeze(args.freeze)
    destination = BASE / "terra"
    if args.preflight:
        for case in receipts:
            keys = input_keys(decisions[case])
            if keys:
                check_inputs(case, load_inputs(case, files, keys))
        print("37 issuers verified against freeze.")
        return
    destination.mkdir(parents=True, exist_ok=True)
    # An OS-backed SQLite lock vanishes on exit or crash; the immutable budget
    # database still enforces atomic reservations from every worker.
    with closing(
        sqlite3.connect(destination / "batch_lock.sqlite3", timeout=0)
    ) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        ledger = Ledger(destination / "ledger.sqlite3", digest)
        if args.resume_billing:
            ledger.resume_billing()
        transport = (
            Transport() if any(input_keys(d) for d in decisions.values()) else None
        )

        def process(receipt, admitted, halted):
            keys = input_keys(decisions[receipt])
            assessor = Assessor(ledger, transport, admitted, halted) if keys else None
            folder = destination / receipt
            if not decisions[receipt]["terra_ready"]:
                mandatory = None
                b_path = BASE / "issuers" / receipt / "b.json"
                if (
                    b_path.resolve() in files
                    and sha(b_path.read_bytes()) == files[b_path.resolve()]
                ):
                    mandatory = read(b_path).get("mandatory")
                if keys:
                    try:
                        run_roles(
                            receipt, load_inputs(receipt, files, keys), assessor, folder
                        )
                    except StopBatch:
                        raise
                    except StageFailure:
                        # Per-role failures and successful submissions are already preserved.
                        pass
                lock_json(
                    folder / "preparation.json",
                    {
                        "case": receipt,
                        "reasons": decisions[receipt].get("reasons", []),
                        "complete_pair": False,
                        "fallback": "mandatory_only",
                        "operational": mandatory,
                    },
                )
                print(receipt, "preparation_incomplete")
                return
            data = load_inputs(receipt, files, keys)
            try:
                state = run_case(receipt, data, assessor, folder, args.roles_only)
            except StopBatch:
                raise
            except StageFailure as exc:
                rule_path = folder / "rule.json"
                mandatory = data["b"]["mandatory"]
                fallback = (
                    read(rule_path)["operational"] if rule_path.exists() else mandatory
                )
                lock_json(
                    folder / "failure.json",
                    {
                        "case": receipt,
                        "reason": str(exc),
                        "complete_pair": False,
                        "fallback": "rule" if rule_path.exists() else "mandatory_only",
                        "operational": fallback,
                    },
                )
                state = str(exc)
            print(receipt, state, flush=True)

        ordered_issuers(receipts, args.workers, process)
        print(json.dumps(ledger.summary(), indent=2))


def load_inputs(receipt, files, keys=REQUIRED):
    data = {}
    for key in keys:
        path = BASE / "issuers" / receipt / (key + ".json")
        raw = path.read_bytes()
        if sha(raw) != files[path.resolve()]:
            raise StopBatch("issuer_inputs_changed")
        data[key] = json.loads(raw)
    return data


if __name__ == "__main__":
    main()
