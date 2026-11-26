"""Validation-role inputs and outputs. The evaluators never receive reference grades."""

import argparse
import hashlib
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
from pathlib import Path
from tempfile import gettempdir

import fitz
import httpx
from bs4 import BeautifulSoup

from scripts.current_b import OUT, ROOT, dump
from scripts.current_live import S, arr, ask, load, obj
from scripts.current_validation import cases, prepare

DEST = OUT / "validation_roles"
CACHE = Path(gettempdir()) / "ipo_a1_initial_registrations"
DART = "https://dart.fss.or.kr"
# A supplementary same-market candidate for each case; audited only on the private side.
CANDIDATES = {
    "GIGAVIS": [
        ("고영테크놀러지", "098460"),
        ("파크시스템스", "140860"),
        ("넥스틴", "348210"),
        ("인텍플러스", "064290"),
        ("오로스테크놀로지", "322310"),
    ],
    "TRUEN": [
        ("포커스에이치엔에스", "331380"),
        ("아이디스", "143160"),
        ("위세아이텍", "065370"),
        ("이노뎁", "303530"),
    ],
    "MANYO": [
        ("클리오", "237880"),
        ("아이패밀리에스씨", "114840"),
        ("네오팜", "092730"),
        ("애경산업", "018250"),
        ("브이티지엠피", "018290"),
        ("토니모리", "214420"),
    ],
    "PHILENERGY": [
        ("피엔티", "137400"),
        ("에이프로", "262260"),
        ("엔시스", "333620"),
        ("하나기술", "299030"),
    ],
}
STATES = ["수용", "문제 제기", "미확인"]
A0_ROW = obj(
    {
        "item_id": S,
        "state": {"type": "string", "enum": STATES},
        "reason": S,
        "physical_page": {"type": "integer"},
        "quote": S,
    }
)
A0_SCHEMA = obj({"items": arr(A0_ROW)})
A0_PROMPT = """독립적으로 최초 증권신고서 원문을 읽는 A0 검토자다. 원래 선택이 적절하면 수용, 구체적인 사실 오류·중요한 반대 근거가 있으면 문제 제기, 확인이 부족하면 미확인으로 구분한다. 선택이 공시되었다는 사실만으로 수용하지 말고 우선 찬반 근거를 대조하라. 각 항목마다 근거 쪽 한 곳에서 실제로 이어진 짧은 문구(표 셀도 가능), 물리 쪽 번호와 한국어 판단 이유를 제출하라. 추측한 자료나 페이지는 쓰지 마라. 모든 지정 항목을 한 번씩 다룬다."""


def compact(value):
    return re.sub(r"\s+", "", value).casefold()


def annual(ticker):
    """Fetch one pre-cutoff audited-period annual business section and pin exact bytes."""
    base = DEST / "sources" / ticker
    metadata = base / "source.json"
    if metadata.exists():
        return load(metadata)
    params = {
        "currentPage": "1",
        "maxResults": "100",
        "startDate": "20230201",
        "endDate": "20230330",
        "textCrpNm": ticker,
        "publicType": "A001",
        "sort": "date",
        "series": "desc",
    }
    base.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        search = client.get(DART + "/dsab001/search.ax", params=params)
        search.raise_for_status()
        soup = BeautifulSoup(search.content.decode("utf-8"), "html.parser")
        rows = [
            (
                re.search(r"rcpNo=(\d{14})", a["href"])[1],
                " ".join(a.find_parent("tr").stripped_strings),
            )
            for a in soup.select('a[href*="rcpNo"]')
            if compact(a.get_text()) == "사업보고서(2022.12)"
        ]
        receipt, identity = min(rows)
        url = DART + "/dsaf001/main.do?rcpNo=" + receipt
        cover = client.get(url)
        cover.raise_for_status()
        html = cover.content.decode("utf-8")
        result = {
            "receipt": receipt,
            "ticker": ticker,
            "published": receipt[:8],
            "cover_url": url,
            "identity": identity,
            "cover_title": BeautifulSoup(html, "html.parser").title.get_text(
                strip=True
            ),
            "sections": [],
        }
        for node in re.split(r"var node\d+\s*=\s*\{\};", html):
            fields = dict(re.findall(r"node\d+\['(\w+)'\]\s*=\s*\"([^\"]*)\"", node))
            if compact(fields.get("text", "")).replace("(제조서비스업)", "") not in (
                "1.사업의개요",
                "2.주요제품및서비스",
            ):
                continue
            req = {
                k: fields[k]
                for k in ("rcpNo", "dcmNo", "eleId", "offset", "length", "dtd")
            }
            page = client.get(
                DART + "/report/viewer.do", params=req, headers={"Referer": url}
            )
            page.raise_for_status()
            key = "business" if fields["text"].startswith("1") else "products"
            file = base / (key + ".html")
            text = " ".join(
                BeautifulSoup(
                    page.content, "html.parser", from_encoding="utf-8"
                ).stripped_strings
            )
            if len(text) < 80:
                raise ValueError("Empty annual section " + ticker)
            file.write_bytes(page.content)
            result["sections"].append(
                {
                    "key": key,
                    "title": fields["text"],
                    "url": str(page.url),
                    "snapshot": file.relative_to(ROOT).as_posix(),
                    "sha256": hashlib.sha256(page.content).hexdigest(),
                }
            )
        if not result["sections"]:
            raise ValueError("Missing business section " + ticker)
        dump(metadata, result)
        return result


def original(casepack):
    case = casepack["case"]
    pages = casepack["pages"]
    items = casepack["items"]

    def verify(answer):
        found = [v["item_id"] for v in answer["items"]]
        if sorted(found) != sorted(x["item_id"] for x in items):
            raise ValueError("Return all item IDs exactly once")
        for row in answer["items"]:
            quote = compact(row["quote"])
            if not quote or quote not in compact(
                pages.get(str(row["physical_page"]), "")
            ):
                raise ValueError(
                    "Use one short contiguous verbatim quote on the stated page for "
                    + row["item_id"]
                )

    result = ask(
        case,
        "V0",
        A0_PROMPT,
        {"items": items, "original_physical_pages": pages},
        A0_SCHEMA,
        5100,
        verify,
    )
    records = {}
    rows = []
    for i, r in enumerate(result["answer"]["items"], 1):
        eid = f"A{i:02}"
        records[eid] = {
            "source_group": casepack["receipt"],
            "url": casepack["source_url"],
            "pdf_sha256": casepack["pdf_sha256"],
            "physical_page": r["physical_page"],
            "excerpt": r["quote"],
        }
        rows.append(
            {
                "item_id": r["item_id"],
                "state": r["state"],
                "reason": r["reason"],
                "evidence_ids": [eid],
                "comparable": True,
            }
        )
    dump(
        DEST / case / "a0.json",
        {
            "items": rows,
            "sources": records,
            "run": result["evidence_dir"],
            "mode": "항목을 지정한 최초 신고서 발췌 직접 검토. 기존 전체 신고서 탐색형 A0와 달리 지정 항목과 공통 원문 쪽을 제공한다.",
        },
    )


def neutral(reg):
    case = reg["case_id"].split("-")[0]
    roster = CANDIDATES[case]
    frozen = load(OUT / "validation/freeze.json")[case]
    plan = load(DEST / "evidence_plan.json")
    ids = {
        x["question"].split("의 사업 비교")[0]: x["item_id"]
        for x in frozen["items"]
        if x["question_type"] == "J2"
    }
    assert {n for n, _ in roster[:-1]} == set(ids)
    sources = {}

    def add(summary, anchors, text, metadata):
        if not anchors or any(compact(a) not in compact(text) for a in anchors):
            raise ValueError(
                "Unverified source anchor for "
                + str(metadata)
                + " "
                + str([a for a in anchors if compact(a) not in compact(text)])
            )
        eid = "E" + str(len(sources) + 1)
        sources[eid] = {**metadata, "excerpt": summary, "verbatim_anchors": anchors}
        return {"evidence_id": eid, "text": summary}

    local = CACHE / (reg["receipt_no"] + ".pdf")
    if not local.exists():
        prepare(reg)
    assert hashlib.sha256(local.read_bytes()).hexdigest() == frozen["sha256"]
    with fitz.open(local) as doc:
        issuer = [
            add(
                s,
                a,
                doc[p - 1].get_text(sort=True),
                {
                    "url": reg["pdf_url"],
                    "source_group": reg["receipt_no"],
                    "physical_page": p,
                    "sha256": frozen["sha256"],
                    "published": reg["date_kst"],
                    "origin": "initial_filing_business_or_financials",
                },
            )
            for p, s, a in plan["issuer"][case]
        ]
    ordered = list(roster)
    random.Random(261126 + len(case)).shuffle(ordered)
    subjects = []
    links = {}
    for i, (name, ticker) in enumerate(ordered, 1):
        rec = annual(ticker)
        assert rec["published"] < reg["receipt_no"][:8]
        sec, summary, anchors = plan["candidate"][ticker]
        meta = next(r for r in rec["sections"] if r["key"] == sec)
        blob = (ROOT / meta["snapshot"]).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == meta["sha256"]
        text = " ".join(
            BeautifulSoup(blob, "html.parser", from_encoding="utf-8").stripped_strings
        )
        fact = add(
            summary,
            anchors,
            text,
            {
                **meta,
                "source_group": rec["receipt"],
                "published": rec["published"],
                "origin": "candidate_own_2022_annual",
                "cover_url": rec["cover_url"],
            },
        )
        cid = "C" + str(i)
        links[cid] = {
            "name": name,
            "item_id": ids.get(name),
            "ticker": ticker,
            "supplementary": name not in ids,
        }
        subjects.append(
            {"candidate_id": cid, "business": [fact], "financials": [], "multiples": []}
        )
    blind = {"issuer_evidence": issuer, "candidates": subjects}
    path = DEST / case / "c_packet.json"
    blobtext = json.dumps(blind, ensure_ascii=False)
    forbidden = [
        "최종 선정",
        "선정 여부",
        "제외 여부",
        "원본",
        "비교회사",
        "신고서",
        "공모가격",
        "기준주가",
        "공모가",
        "href",
        "http",
        case,
        reg["issuer"],
        *[n for n, _ in roster],
        *[t for _, t in roster],
        *ids.values(),
        *["대조군", "통제군"],
    ]
    if any(compact(term) in compact(blobtext) for term in forbidden):
        raise ValueError("Metadata leaked into C packet")
    dump(path, blind)
    from ipo_eval.blind_reviewer import load_packet

    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    load_packet(path, fingerprint)
    private = {
        "case": case,
        "receipt": reg["receipt_no"],
        "sha256": fingerprint,
        "published_cutoff": reg.get("published_kst", reg["date_kst"]),
        "sources": sources,
        "links": links,
        "scope": "원본 선정기업 15곳과 별도로 추가한 업종 내 후보 4곳을 합한 제한 표본. 산업 전수·재무 적격 여부 또는 공개시장 가격 포괄성은 확인하지 않았다. 후보별 자기 사업보고서의 사업·품목 근거 하나와 발행사 사업·재무정보를 제공한다. 일부 사업 묘사로 기업을 추정할 수 있다.",
        "control_basis": "동종 제품·공정·고객군을 기준으로 추가한 실재 상장사. 최초 신고서의 최종 선정·제외 여부 및 결론은 가린다. 독립 시장 전수 탐색은 수행하지 않았다.",
        "checks": [
            "원본 PDF와 후보 자체 사업보고서의 발행일·문서 해시 및 실제 연속된 근거 문구 대조",
            "기업 ID 무작위 배정, 후보명·발행사명·공시번호·선정/배제 표시·URL 검사, 전 후보 동일 필드 사용",
            "동결 항목 J2 전부와 회사별 추가 후보 1곳의 중복/누락 확인, 실제 C 전송물만 묶어 SHA-256·스키마 확인",
        ],
    }
    dump(DEST / case / "c_private.json", private)
    return blind, private


def produce_c(reg):
    from ipo_eval.blind_reviewer import REVIEW

    case = reg["case_id"].split("-")[0]
    packet, private = neutral(reg)
    rule = (ROOT / "prompts/blind_reviewer.md").read_text(encoding="utf8")

    def verify(a):
        ids = [r["candidate_id"] for r in a["candidates"]]
        if sorted(ids) != sorted(private["links"]):
            raise ValueError("Submit one row per candidate")
        common = {v["evidence_id"] for v in packet["issuer_evidence"]}
        for r in a["candidates"]:
            cid = r["candidate_id"]
            own = {
                v["evidence_id"]
                for c in packet["candidates"]
                if c["candidate_id"] == cid
                for v in c["business"]
            }
            if (
                not r["evidence_ids"]
                or not own.intersection(r["evidence_ids"])
                or not set(r["evidence_ids"]) <= common | own
            ):
                raise ValueError(
                    "Cite the matching candidate fact and any relevant issuer facts"
                )
        if not all(
            set(r["evidence_ids"]) <= set(private["sources"])
            for r in (a["earnings"], a["aggregation"])
        ):
            raise ValueError("Cite IDs provided in packet")

    result = ask(case, "VC", rule, packet, REVIEW, 3500, verify)
    dump(
        DEST / case / "c.json",
        {
            "answer": result["answer"],
            "evidence_dir": result["evidence_dir"],
            "packet_sha256": private["sha256"],
        },
    )


def proxy_schema(role):
    if role == "A0":
        return A0_SCHEMA
    from ipo_eval.blind_reviewer import REVIEW

    methods = {
        "period": [
            "LATEST_COMPLETE_FY",
            "TRAILING_FOUR_QUARTERS",
            "ANNUALIZED_INTERIM",
            "OTHER",
            "UNKNOWN",
        ],
        "attribution": ["STANDALONE", "CONSOLIDATED_PARENT", "OTHER", "UNKNOWN"],
        "aggregation": ["UNWEIGHTED_MEAN", "MEDIAN", "OTHER", "UNKNOWN"],
        "expense": ["ADJUST_DOCUMENTED_ITEMS", "RETAIN_REPORTED", "OTHER", "UNKNOWN"],
    }
    fields = {
        key: obj(
            {
                "choice": {"type": "string", "enum": vals},
                "reason": S,
                "evidence_ids": arr(S),
            }
        )
        for key, vals in methods.items()
    }
    return obj({**REVIEW["properties"], "methods": obj(fields)})


def isolated_cli(role_dir, prompt, schema):
    import shutil
    import subprocess
    import tempfile
    import time
    from datetime import datetime

    from jsonschema import validate

    role_dir.mkdir(parents=True, exist_ok=True)
    dump(role_dir / "schema.json", schema)
    (role_dir / "input.txt").write_text(prompt, encoding="utf-8")
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex CLI unavailable")
    with tempfile.TemporaryDirectory(prefix="masked-review-") as empty:
        command = [
            codex,
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "-s",
            "read-only",
            "-C",
            empty,
            "--json",
            "--color",
            "never",
            "-c",
            'web_search="disabled"',
            "-c",
            'model_reasoning_effort="medium"',
            "-c",
            "project_doc_max_bytes=0",
            "--output-schema",
            str(role_dir / "schema.json"),
            "-o",
            str(role_dir / "answer.json"),
        ]
        for feature in (
            "shell_tool",
            "unified_exec",
            "apps",
            "plugins",
            "browser_use",
            "in_app_browser",
            "view_image",
            "multi_agent",
            "skill_search",
            "memories",
        ):
            command.extend(["--disable", feature])
        command.append("-")
        started = datetime.now(UTC).isoformat()
        timer = time.monotonic()
        proc = subprocess.run(
            command,
            input=prompt.encode("utf-8"),
            capture_output=True,
            cwd=empty,
            timeout=420,
            check=False,
        )
        secs = round(time.monotonic() - timer, 3)
    events = proc.stdout.decode("utf-8", "replace")
    (role_dir / "events.jsonl").write_text(events, encoding="utf-8")
    stderr = proc.stderr.decode("utf-8", "replace")
    (role_dir / "diagnostics.txt").write_text(stderr, encoding="utf-8")
    if proc.returncode or not (role_dir / "answer.json").is_file():
        raise RuntimeError(
            f"Codex CLI exit {proc.returncode}: " + stderr[-240:] + " " + events[-260:]
        )
    entries = [json.loads(line) for line in events.splitlines() if line.startswith("{")]
    types = [
        row["item"]["type"]
        for row in entries
        if "item" in row and "type" in row["item"]
    ]
    if any(x not in ("agent_message", "reasoning") for x in types):
        raise ValueError("Unexpected CLI activity " + repr(types))
    answer = load(role_dir / "answer.json")
    validate(answer, schema)
    return answer, started, secs, types, entries


def verify_role_answer(role, payload, answer):
    if role == "A0":
        expected = {i["item_id"] for i in payload["items"]}
        if (
            len(answer["items"]) != len(expected)
            or {r["item_id"] for r in answer["items"]} != expected
        ):
            raise ValueError("A0 item coverage")
        for row in answer["items"]:
            quote = compact(row["quote"])
            if not quote or quote not in compact(
                payload["original_physical_pages"].get(str(row["physical_page"]), "")
            ):
                raise ValueError("A0 invalid excerpt " + row["item_id"])
    else:
        by_c = {
            c["candidate_id"]: {r["evidence_id"] for r in c["business"]}
            for c in payload["candidates"]
        }
        issuer = {f["evidence_id"] for f in payload["issuer_evidence"]}
        if len(answer["candidates"]) != len(by_c) or {
            r["candidate_id"] for r in answer["candidates"]
        } != set(by_c):
            raise ValueError("C candidate coverage")
        for r in answer["candidates"]:
            cited = set(r["evidence_ids"])
            own = by_c[r["candidate_id"]]
            if not cited & own or not cited <= issuer | own:
                raise ValueError("C citation mismatch " + r["candidate_id"])
        provided = issuer | set().union(*by_c.values())
        for m in [
            *answer["methods"].values(),
            answer["earnings"],
            answer["aggregation"],
        ]:
            if not set(m["evidence_ids"]) <= provided:
                raise ValueError("Unknown citation")
            if m.get("choice") not in ("UNKNOWN", None) and not m["evidence_ids"]:
                raise ValueError("Unsourced proposal")


def proxy_role(case, role):
    role_dir = DEST / "proxy" / case / ("C_neutral" if role == "C" else role)
    role_dir.mkdir(parents=True, exist_ok=True)
    success = role_dir / "result.json"
    packet_path = DEST / case / ("a0_input.json" if role == "A0" else "c_packet.json")
    payload = load(packet_path)
    if role == "A0":
        prompt = A0_PROMPT
    else:
        prompt = (ROOT / "prompts/blind_reviewer.md").read_text(encoding="utf-8")
        prompt += "\n방법별 범주에는 제안에서 선택한 내용을 기입한다. 해당 자료가 지지하지 않으면 UNKNOWN이다. EPS와 재무비율을 계산할 자료가 없으면 가격을 추정하지 않는다. 각 후보 판정에 그 후보의 근거 ID를 포함한다. 회사명과 후보의 포함·제외 이력 추정은 금지한다."
    prompt += "\n독립 문서심사 작업이다. 조회 도구, 파일, 브라우저, 메모리, 다른 에이전트 및 외부 정보 사용을 금한다. 아래 입력에만 근거하여 응답 스키마에 맞는 최종 JSON만 제출한다.\n"
    prompt += json.dumps(payload, ensure_ascii=False)
    schema = proxy_schema(role)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    prompt_sha = sha(prompt.encode("utf-8"))
    if success.exists():
        result = load(success)
        if result["prompt_sha256"] != prompt_sha:
            raise ValueError("Proxy prompt changed")
        return result
    answer, started, secs, types, entries = isolated_cli(role_dir, prompt, schema)
    verify_role_answer(role, payload, answer)
    result = {
        "role": role,
        "case": case,
        "answer": answer,
        "provider": "Codex CLI ChatGPT sign-in; fresh ephemeral process",
        "official_H1": False,
        "started_at_utc": started,
        "elapsed_s": secs,
        "prompt_sha256": prompt_sha,
        "packet_sha256": sha(packet_path.read_bytes()),
        "output_sha256": sha((role_dir / "answer.json").read_bytes()),
        "tool_item_types": sorted(set(types)),
        "thread_id": next((r["thread_id"] for r in entries if "thread_id" in r), None),
        "usage": [r["usage"] for r in entries if "usage" in r],
    }
    dump(success, result)
    print(case, role, "SUBMITTED", secs, flush=True)
    return result


def merge_proxy_labels(official=False):
    """Compare blinded, source-grounded proposals with the frozen original only after both role runs."""
    frozen = load(OUT / "validation/freeze.json")
    labels = {}
    group = "official" if official else "proxy"
    b_all = load(OUT / "validation/b.json")
    for case, info in frozen.items():
        src = load(DEST / case / "c_private.json")
        common_b = b_all[case]
        if (
            common_b["sha256"] != info["sha256"]
            or common_b["receipt"] != info["receipt"]
        ):
            raise ValueError("B and role sources disagree")
        first = load(DEST / group / case / "A0" / "result.json")
        second = load(DEST / group / case / "C_neutral" / "result.json")
        successful = {first["thread_id"], second["thread_id"]}
        if None in successful or len(successful) != 2:
            raise ValueError("Require distinct successful role sessions")
        assert (
            first["packet_sha256"]
            == hashlib.sha256((DEST / case / "a0_input.json").read_bytes()).hexdigest()
        )
        assert second["packet_sha256"] == src["sha256"]
        assert not any(
            t in {"command_execution", "mcp_tool_call", "web_search", "file_change"}
            for t in first["tool_item_types"] + second["tool_item_types"]
        )
        original = {r["item_id"]: r for r in first["answer"]["items"]}
        blind = second["answer"]
        decisions = {r["candidate_id"]: r for r in blind["candidates"]}
        by_item = {r["item_id"]: cid for cid, r in src["links"].items() if r["item_id"]}
        mapping = {
            1: (
                "period",
                "TRAILING_FOUR_QUARTERS"
                if case == "PHILENERGY"
                else "LATEST_COMPLETE_FY",
            ),
            2: (
                "attribution",
                "STANDALONE" if case in ("GIGAVIS", "TRUEN") else "CONSOLIDATED_PARENT",
            ),
            4: ("aggregation", "UNWEIGHTED_MEAN"),
            8: ("expense", "ADJUST_DOCUMENTED_ITEMS"),
        }
        original_refs = {
            "GIGAVIS": {
                "period": 234,
                "attribution": 295,
                "aggregation": 234,
                "expense": 234,
            },
            "TRUEN": {"period": 195, "attribution": 263, "aggregation": 195},
            "MANYO": {"period": 185, "attribution": 184, "aggregation": 184},
            "PHILENERGY": {
                "period": 185,
                "attribution": 185,
                "aggregation": 184,
                "expense": 185,
            },
        }[case]
        sources = dict(src["sources"])
        items = []
        reg = next(r for r in cases() if r["case_id"].startswith(case + "-"))
        all_eid = {
            f["evidence_id"]
            for f in load(DEST / case / "c_packet.json")["issuer_evidence"]
        }
        for item in info["items"]:
            iid = item["item_id"]
            i = int(iid.split("-")[-1])
            a = original[iid]
            aeid = "A" + str(i).zfill(2)
            sources[aeid] = {
                "source_group": reg["receipt_no"],
                "sha256": reg["pdf_sha256"],
                "url": reg["pdf_url"],
                "physical_page": a["physical_page"],
                "excerpt": a["quote"],
                "origin": "original_filing",
            }
            if iid in by_item:
                candidate = decisions[by_item[iid]]
                c = {
                    "state": {
                        "INCLUDE": "수용",
                        "REVIEW": "미확인",
                        "EXCLUDE": "문제 제기",
                    }[candidate["decision"]],
                    "reason": candidate["reason"],
                    "evidence_ids": candidate["evidence_ids"],
                    "comparable": True,
                    "scope": "사업 비교 적합성",
                    "native_decision": candidate["decision"],
                }
            elif i in mapping:
                key, expected = mapping[i]
                proposal = blind["methods"][key]
                sources_c = proposal["evidence_ids"]
                scope = (
                    "발행사 이익 기간"
                    if key == "period"
                    else "발행사 이익 귀속"
                    if key == "attribution"
                    else "집계"
                    if key == "aggregation"
                    else "비경상 손익 조정"
                )
                comparable = (
                    key in ("period", "attribution")
                    and bool(set(sources_c) & all_eid)
                    and proposal["choice"] not in ("UNKNOWN", "OTHER")
                )
                c = {
                    "state": ("수용" if proposal["choice"] == expected else "문제 제기")
                    if comparable
                    else "미확인",
                    "reason": proposal["reason"],
                    "evidence_ids": sources_c,
                    "comparable": comparable,
                    "scope": scope,
                    "native_choice": proposal["choice"],
                    "original_choice": expected,
                    "original_mapping_physical_page": original_refs[key],
                    "limit": (
                        "발행사 자료로 기간·귀속에 관한 독립 제안의 방향만 비교한다."
                        if comparable
                        else "공통 가격·비경상 손익·구체적인 귀속/기간의 근거가 부족하거나 제안이 조건부/미확정이다."
                    ),
                }
            else:
                c = {
                    "state": "미확인",
                    "reason": "C에는 원 공모가격, 주식수, 할인율 또는 후보 시장가격의 관측치가 없고 해당 산출 결과를 제출하도록 하지 않았다.",
                    "comparable": False,
                    "scope": "C 검토 범위 밖",
                    "evidence_ids": [],
                }
            items.append(
                {
                    **item,
                    "a0": {
                        "state": a["state"],
                        "reason": a["reason"],
                        "evidence_ids": [aeid],
                        "comparable": True,
                    },
                    "c": c,
                    "price_impact": common_b["price_impact_fraction"].get(iid),
                    "price_impact_scope": common_b["alternative_coverage"],
                }
            )
        assert len(items) == len(original) and {i["item_id"] for i in items} == set(
            original
        )
        assert all(
            set(item[role]["evidence_ids"]) <= set(sources)
            for item in items
            for role in ("a0", "c")
        )
        aligned = [
            r["item_id"]
            for r in items
            if r["question_type"] == "J2"
            and r["a0"]["state"] == r["c"]["state"] == "수용"
        ]
        labels[case] = {
            "case": case,
            "items": items,
            "sources": sources,
            "source_index": (DEST / case / "c_private.json")
            .relative_to(ROOT)
            .as_posix(),
            "supplementary": [
                {**v, "decision": decisions[cid]}
                for cid, v in src["links"].items()
                if v["supplementary"]
            ],
            "aligned_acceptance_j2": aligned,
            "official_H1_eligible": official,
            "b_source": "reports/a1_current/validation/b.json",
            "mandatory": common_b["mandatory"],
            "common_b_rules": common_b["rules"],
            "price_impact_fraction": common_b["price_impact_fraction"],
            "proxy_role_coverage": not official,
            "scope": src["scope"],
            "run_paths": {
                role: (
                    DEST
                    / group
                    / case
                    / ("C_neutral" if role == "C" else role)
                    / "result.json"
                )
                .relative_to(ROOT)
                .as_posix()
                for role in ["A0", "C"]
            },
            "review": [
                {
                    "round": 1,
                    "check": "역할별 별도 세션, 도구 실행 없음, 입력 해시와 개별 원문 근거 확인",
                    "remedy": "회사·선정 단서가 있는 운영자 자료는 C 입력에서 제외했다.",
                },
                {
                    "round": 2,
                    "check": "가린 후보 판정과 15개 해당 항목/4개 부가 후보를 운영자 단계에서 대조",
                    "remedy": "C의 REVIEW는 유보 묶음으로 매핑해 단순 증거 부족을 반대로 분류하지 않았다.",
                },
                {
                    "round": 3,
                    "check": "모든 원본 항목과 참조 근거 ID의 존재, 공통 B와 역할의 분리 확인",
                    "remedy": "후보별 시장배수·주식수·할인율과 구체적인 비경상 항목이 없는 C에 확정 가격영향·방법 일치 판정을 부여하지 않았다.",
                },
            ],
        }
    rows = [r for d in labels.values() for r in d["items"]]
    assert len(rows) == 45
    threads = [
        load(DEST / group / case / role / "result.json")["thread_id"]
        for case in labels
        for role in ("A0", "C_neutral")
    ]
    if len(set(threads)) != 8:
        raise ValueError("Role contexts overlapped")
    bundle = {
        "cases": labels,
        "n": len(rows),
        "condition": "CODEX_CLI_PROXY",
        "scientific_H1_eligible": False,
        "method_deviation": "대상 항목을 지정한 발췌형 A0와 후보별 제한된 사업자료의 가림 C를 ChatGPT에 로그인한 Codex CLI에서 회사·역할별 새로 실행했다. 공식 API 조건과 비용을 대체하지 않는다. C의 사업 유사성 및 충분한 근거를 인용한 구체적 기간·귀속 제안만 원본 선택과 대조한다.",
        "method_repair": "최초 파일럿 C의 출력 선택지에 특정 손익 종류가 포함된 점을 발견해 그 4건은 제외했다. 전체 회사에 공통인 일반적 기간·손익 선택지로 수정하고 별도 세션에서 4건을 전부 재실행했다. C_neutral 아래 실제 응답만 집계했다.",
        "raw_cost_usd": None,
    }
    if official:
        bundle.update(
            condition="OFFICIAL_TERRA_TARGETED_VALIDATION",
            scientific_H1_eligible=True,
            method_deviation="지정한 최초 신고서 항목과 자료를 받은 A0 및 공개 사업 근거에 한정된 C를 회사·역할별 OpenAI Responses 공식 모델로 독립 실행했다. 검증 표본에서의 과제이며 정식 효과 확증 여부는 별도 평가한다.",
            method_repair="앞서 잔액 부족으로 응답이 없던 VC 요청의 중립 자료 묶음을 재사용했다. 일반적인 기간·귀속·집계·손익조정 선택지와 자료 부족 처리 지침을 출력 계약에 추가했다. 기존 대리 답변은 포함하지 않았다.",
            usage_records=[
                labels[c]["run_paths"][r] for c in labels for r in ("A0", "C")
            ],
        )
    dump(DEST / group / "labels.json", bundle)


def check_aliases():
    """DART's viewer can show a contemporary company name on a 2022 report."""
    records = {}
    for name, ticker in (
        ("고영테크놀러지", "098460"),
        ("포커스에이치엔에스", "331380"),
        ("브이티지엠피", "018290"),
    ):
        rec = annual(ticker)
        target = DEST / "sources" / ticker / "identity.html"
        details = target.with_suffix(".json")
        if details.exists():
            out = load(details)
        else:
            with httpx.Client(timeout=30) as client:
                page = client.get(rec["cover_url"])
                page.raise_for_status()
                matches = []
                for block in re.split(
                    r"var node\d+\s*=\s*\{\};", page.content.decode("utf-8")
                ):
                    fields = dict(
                        re.findall(r"node\d+\['(\w+)'\]\s*=\s*\"([^\"]*)\"", block)
                    )
                    if compact(fields.get("text", "")) == "1.회사의개요":
                        matches.append(fields)
                if len(matches) != 1:
                    raise ValueError("Ambiguous identity section " + ticker)
                req = {
                    k: matches[0][k]
                    for k in ("rcpNo", "dcmNo", "eleId", "offset", "length", "dtd")
                }
                view = client.get(
                    DART + "/report/viewer.do",
                    params=req,
                    headers={"Referer": rec["cover_url"]},
                )
                view.raise_for_status()
                target.write_bytes(view.content)
                out = {
                    "url": str(view.url),
                    "sha256": hashlib.sha256(view.content).hexdigest(),
                    "receipt": rec["receipt"],
                    "historical_name": name,
                    "snapshot": target.relative_to(ROOT).as_posix(),
                    "viewer_title_today": rec["cover_title"],
                }
                dump(details, out)
        raw = target.read_bytes()
        assert out["sha256"] == hashlib.sha256(raw).hexdigest()
        assert name in BeautifulSoup(
            raw, "html.parser", from_encoding="utf-8"
        ).get_text(" ", strip=True)
        records[ticker] = out
    return records


def run_errors(case, role):
    paths = sorted((OUT / "live" / case / role).glob("*/*/*_error.json"))
    return [{"file": p.relative_to(ROOT).as_posix(), **load(p)} for p in paths]


def audit():
    evidence = {}
    alias = check_aliases()
    frozen = load(OUT / "validation/freeze.json")
    b_path = OUT / "validation/b.json"
    verified_b = load(b_path) if b_path.is_file() else {}
    for reg in cases():
        case = reg["case_id"].split("-")[0]
        _, private = neutral(reg)
        p = prepare(reg)
        a_v = {"original_physical_pages": p["pages"], "items": p["items"]}
        dump(DEST / case / "a0_input.json", a_v)
        ids = {r["item_id"] for r in frozen[case]["items"]}
        assert len(ids) == len(frozen[case]["items"])
        assert len([r for r in private["links"].values() if r["supplementary"]]) == 1
        assert (
            sum(r["item_id"] in ids for r in private["links"].values())
            == len(private["links"]) - 1
        )
        actual = {}
        for role, filename in [("V0", "a0.json"), ("VC", "c.json")]:
            result = DEST / case / filename
            errors = run_errors(case, role)
            if not result.exists() and not errors:
                raise ValueError(
                    "Missing evidence of actual role attempt " + case + role
                )
            actual[role] = {
                "submitted": result.exists(),
                "audited_errors": errors,
                "answer": result.relative_to(ROOT).as_posix()
                if result.exists()
                else None,
            }
        evidence[case] = {
            "original_receipt": reg["receipt_no"],
            "original_sha256": reg["pdf_sha256"],
            "frozen_item_count": len(ids),
            "frozen_j2_item_count": len(private["links"]) - 1,
            "neutral_candidate_count": len(private["links"]),
            "candidate_sources_published": [
                min(annual(t)["published"] for n, t in CANDIDATES[case]),
                max(annual(t)["published"] for n, t in CANDIDATES[case]),
            ],
            "masked_packet_sha256": private["sha256"],
            "a0_targeted_input_sha256": hashlib.sha256(
                (DEST / case / "a0_input.json").read_bytes()
            ).hexdigest(),
            "private_source_index": (DEST / case / "c_private.json")
            .relative_to(ROOT)
            .as_posix(),
            "role_execution": actual,
            "common_b_source": b_path.relative_to(ROOT).as_posix()
            if case in verified_b
            else None,
            "mandatory": verified_b.get(case, {}).get("mandatory"),
            "price_impact_fraction": verified_b.get(case, {}).get(
                "price_impact_fraction"
            ),
            "official_H1_role_coverage": all(o["submitted"] for o in actual.values()),
            "eligibility": (
                "공통 B·가격영향·동일 예산 및 평가 결과 검증 필요"
                if all(o["submitted"] for o in actual.values())
                else "공식 A0·C의 짝지은 실제 응답이 확보되지 않아 공식 H1 비교 불가. 공통 B와 검증된 가격영향은 별도 필드에 기록한다."
            ),
        }
    auditrec = {
        "cases": evidence,
        "historical_identity_checks": alias,
        "schema_version": 1,
        "method": "A0는 원본 범위의 항목지정 발췌 검토로 기존 탐색형 전체 A0와 다르다. C는 공개 전기 사업보고서 원자료와 발행사 중립 증거에 기반한 맹검 제안이다. 후보는 전수 모집단이 아니다. 중립 입력에는 비교사별 재무·배수와 적정 공모가격 정답이 없다.",
        "input_exposure": "검증 네 회사의 참조 채점과 A1 순위는 열람하지 않았다. 협업 슬롯 조회에 이미 종료된 개발 사례의 합계 등급이 표시되었으며 검증 역할의 공급자 요청 입력에는 들어가지 않았다.",
        "checks": [
            {
                "round": 1,
                "check": "네 원본 버전·해시·물리 페이지와 비교사·추가후보별 연차보고서 원본을 확인했다.",
                "remedy": "직접 PDF 응답 본문이 비는 경우 DART 뷰어 목차에서 사업 개요·주요 제품의 정식 HTML 문서를 받아 보존했다.",
            },
            {
                "round": 2,
                "check": "동결된 45개 항목과 J2의 15개 원래 기업을 후보 19곳에 연결하고 이름·선정여부를 입력에서 분리했다.",
                "remedy": "DART 제목에서 현재 명칭이 표시되는 사례는 원 연차보고서의 ‘회사의 개요’에 나온 당시 법적 명칭을 대조했다.",
            },
            {
                "round": 3,
                "check": "동일한 입력을 출처 해시·원문 구절과 재대조하고 공식 모델 응답의 존재 및 오류 코드를 독립 확인했다.",
                "remedy": "긴 Windows 실행 경로를 짧은 단계명으로 수정했다. 응답이 없는 경우 충전 전 공식 결과·조건 간 측정값을 생성하지 않는다.",
            },
        ],
    }
    dump(DEST / "feasibility.json", auditrec)


def primary_source_inventory():
    stocks = [v for roster in CANDIDATES.values() for _, v in roster]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for rec in pool.map(annual, stocks):
            print(rec["ticker"], rec["receipt"], rec["cover_title"], flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "stage",
        choices=["sources", "packets", "a0", "c", "audit", "proxy", "merge-proxy"],
    )
    ap.add_argument("--case", choices=list(CANDIDATES))
    ap.add_argument("--role", choices=["A0", "C"])
    args = ap.parse_args()
    if args.stage == "sources":
        primary_source_inventory()
    elif args.stage == "merge-proxy":
        merge_proxy_labels()
    elif args.stage == "proxy":
        tasks = [
            (case, role)
            for case in ([args.case] if args.case else CANDIDATES)
            for role in ([args.role] if args.role else ["A0", "C"])
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(proxy_role, case, role) for case, role in tasks]
            for f in futures:
                f.result()
    elif args.stage == "audit":
        audit()
    elif args.stage == "packets":
        for row in cases():
            neutral(row)
    elif args.stage == "c":
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(produce_c, cases()))
    elif args.stage == "a0":
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda row: original(prepare(row)), cases()))
