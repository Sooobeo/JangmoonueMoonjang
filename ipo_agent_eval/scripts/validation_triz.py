"""Targeted follow-up on same-fact, dual acceptance; uses no reference grades."""

import argparse
import hashlib
import json
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import fitz
from bs4 import BeautifulSoup

from scripts.validation_roles import (
    CACHE,
    DEST,
    ROOT,
    STATES,
    S,
    annual,
    arr,
    dump,
    isolated_cli,
    load,
    obj,
)

BASE = DEST / "proxy" / "triz"
LABEL = DEST / "proxy" / "labels.json"
FORMS = ("original", "format", "directional")
ROLES = ("A0", "C")
ELIGIBILITY = {
    "GIGAVIS-09": (
        False,
        "A0 근거는 반도체 기판 외관검사 및 수출 구조이다. C가 확인한 3D 검사장비 매출에는 전자제품 생산라인도 포함되어 기판 검사 매출 비중과 수요주기 차이가 해소되지 않았다.",
    ),
    "GIGAVIS-12": (
        False,
        "A0는 FC-BGA용 검사장비와 공통 고객을 근거로 삼았다. C의 패키지·SSD·메모리 합산 매출 및 플립칩 부문표는 FC-BGA·고객별 매출을 분리하지 않는다. 양쪽이 확인한 적용 범위와 반대 근거가 일치하지 않는다.",
    ),
    "MANYO-10": (
        False,
        "A0는 자체 브랜드, 규모와 수익성을, C는 보습·기초 화장품 매출 96%를 중심 근거로 삼았다. C에 제기된 클렌징 구성·생산방식은 A0의 규모 비교로 확인할 수 없다.",
    ),
    "TRUEN-08": (
        True,
        "두 역할 모두 보안 카메라 판매와 발행사 매출의 핵심인 IP 카메라의 제품 기능 중첩을 확인했다. A0가 언급하고 C에서 유보한 저장장치 등 사업 비중은 2022년 원본 및 후보 자체 사업보고서에서 AI 카메라 46.1%, IP 카메라 2.4%, NVR 29.6%, DVR 4.8%로 일치한다. 본 시험 범위는 사업 제품 중첩이며 재무·가격 결론은 유보한다.",
    ),
    "TRUEN-09": (
        True,
        "두 역할 모두 보안 카메라의 판매를 공통 기능으로 삼았다. C가 확인을 요구한 저장장치 및 기타 비중은 A0 근거인 원본 표와 후보 자체 2022년 표에서 카메라 47.7%, 레코더 25.1%, 기타 27.2%로 일치한다. 고객별·제품별 이익률 등 가격 결론은 유보한다.",
    ),
}
PEERS = {
    "TRUEN-08": {
        "name": "포커스에이치엔에스",
        "ticker": "331380",
        "camera": "2022년 보안용 AI 카메라 매출은 46.1%, IP 카메라는 2.4%였다.",
        "other": "2022년 네트워크 영상저장장치(NVR) 매출 비중은 29.6%, 디지털 영상저장장치(DVR)는 4.8%였다.",
        "anchors": ["46.1%", "2.4%", "29.6%", "4.8%"],
    },
    "TRUEN-09": {
        "name": "아이디스",
        "ticker": "143160",
        "camera": "2022년 영상보안 카메라 매출 비중은 47.7%였다.",
        "other": "2022년 영상저장장치 매출 비중은 25.1%, 영상관리 소프트웨어·제품 액세서리 등 기타는 27.2%였다.",
        "anchors": ["47.7%", "25.1%", "27.2%"],
    },
}
PROMPT = """제공된 발행사·후보 사실로만 사업 비교 적합성을 판정한다. 같은 완제품 기능이 후보와 발행사 양쪽의 실질적인 매출원인지 확인한다. 관련 산업 소속, 인접 제품 또는 연결되는 장비는 직접적인 완제품 중첩과 구분한다. 제품 기능 중첩에 관한 근거상태(proven, contradicted, unknown), 사업 적합성(수용, 문제 제기, 미확인), 근거와 남은 반대 근거·한계를 제출한다. 자료에 없으면 기억으로 보충하지 않는다. 외부·파일·도구·다른 에이전트 사용 금지. 제공된 근거 ID만 인용한다."""
SCHEMA = obj(
    {
        "decision": {"type": "string", "enum": STATES},
        "product_overlap": {
            "type": "string",
            "enum": ["proven", "contradicted", "unknown"],
        },
        "reason": S,
        "remaining": S,
        "evidence_ids": arr(S),
    }
)
EXPECTED = {
    "original": {"decision": "수용", "product_overlap": "proven", "evidence": "B"},
    "format": {
        "same_decision_as_original": True,
        "product_overlap": "proven",
        "evidence": "B",
    },
    "directional": {
        "product_overlap": "unknown",
        "allowed_decisions": STATES,
        "evidence": "C",
        "basis": "후보의 카메라 제품·매출 근거 전부를 제거한다. 저장장치와 영상보안에 따른 간접 유사성은 남는다. 원래 대상이 해당 제품을 판매하지 않는다고 단정할 근거도 없다.",
    },
}


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def encoded(v):
    return json.dumps(
        v, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def source_proof():
    m = load(DEST / "TRUEN" / "a0_input.json")
    with fitz.open(CACHE / "20230404002347.pdf") as doc:
        issuer = doc[225].get_text(sort=True)
    assert "81.94%" in issuer
    idx = {}
    for key, params in PEERS.items():
        a = m["original_physical_pages"]["188"]
        rec = annual(params["ticker"])
        sec = next(x for x in rec["sections"] if x["key"] == "products")
        raw = (ROOT / sec["snapshot"]).read_bytes()
        assert sha(raw) == sec["sha256"]
        c = " ".join(
            BeautifulSoup(raw, "html.parser", from_encoding="utf-8").stripped_strings
        )
        assert all(q in a and q in c for q in params["anchors"])
        idx[key] = {
            "A0": {
                "issuer_page": 226,
                "candidate_page": 188,
                "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20230404002347",
            },
            "C": {
                "issuer_page": 226,
                "candidate_section": sec,
                "candidate_receipt": rec["receipt"],
                "cutoff_exclusive": "20230404",
                "available": rec["published"],
                "anchor_values": params["anchors"],
            },
        }
    return idx


def materials(item, role):
    v = PEERS[item]
    issuer = [
        {
            "id": "A",
            "text": "2022년 발행사 매출에서 고해상도 네트워크 영상보안용 IP 카메라가 81.94%였다. 방범·어린이 보호·주정차 등 영상감시 용도로 판매한다.",
        }
    ]
    target = (
        {
            "issuer": "트루엔",
            "candidate": v["name"],
            "basis": "최초 신고서 사업·제품 매출 발췌",
        }
        if role == "A0"
        else {
            "issuer": "발행기업",
            "candidate": "후보",
            "basis": "발행기업 및 후보가 공개한 사업·제품 매출 발췌",
        }
    )
    retained = {"id": "C", "text": v["other"]}
    pivot = {"id": "B", "text": v["camera"]}
    rows = {
        "original": [pivot, retained],
        "format": [retained, pivot],
        "directional": [retained],
    }
    result = {
        k: {**target, "issuer_evidence": issuer, "candidate_evidence": x}
        for k, x in rows.items()
    }
    assert rows["format"] == list(reversed(rows["original"]))
    assert rows["directional"] == [r for r in rows["original"] if r["id"] != "B"]
    assert not any(
        t.lower() in encoded(rows["directional"]).decode().lower()
        for t in ("카메라", "camera", "cam ", "촬영", "촬상")
    )
    if role == "C":
        for packet in result.values():
            txt = encoded(packet).decode()
            assert not any(
                t in txt
                for t in (
                    "트루엔",
                    "아이디스",
                    "포커스",
                    "TRUEN",
                    "선정",
                    "제외",
                    "공모가",
                    "효과",
                    "directional",
                    "대조군",
                )
            )
    return result


def freeze():
    BASE.mkdir(exist_ok=True, parents=True)
    target = BASE / "freeze.json"
    main = load(LABEL)
    candidates = {
        iid for c in main["cases"].values() for iid in c["aligned_acceptance_j2"]
    }
    assert candidates == set(ELIGIBILITY)
    provenance = source_proof()
    tasks = []
    for item in sorted(PEERS):
        for role in ROLES:
            for form, p in materials(item, role).items():
                tasks.append(
                    {
                        "item": item,
                        "role": role,
                        "form": form,
                        "sha256": sha(encoded(p)),
                    }
                )
    random.Random(261126).shuffle(tasks)
    spec = {
        "base_labels_sha256": sha(LABEL.read_bytes()),
        "eligibility": ELIGIBILITY,
        "source_proof": provenance,
        "expected": EXPECTED,
        "target": "사업 비교 적합성 및 동일 완제품의 실질적 매출원 중첩",
        "task_order": tasks,
        "prompt_sha256": sha(PROMPT.encode()),
        "response_schema_sha256": sha(encoded(SCHEMA)),
        "procedure": "최초 판정의 공통 근거를 시험하는 항목별 재검토. A0는 원본 회사명이 있는 최초 신고서 수치 발췌, C는 후보 자체의 동기간 사업보고서 및 발행사 중립 발췌를 받는다. 양 역할 모두 다른 형태·기대·가설은 볼 수 없다. 조건부 재무·가격 결론은 범위 밖이다.",
    }
    if target.exists():
        current = load(target)
        assert encoded(
            {k: v for k, v in current.items() if k != "frozen_utc"}
        ) == encoded(spec)
        return current
    spec["frozen_utc"] = datetime.now(UTC).isoformat()
    dump(target, spec)
    return spec


def execute(task):
    item, role, form = task["item"], task["role"], task["form"]
    packet = materials(item, role)[form]
    assert sha(encoded(packet)) == task["sha256"]
    folder = BASE / "runs" / item / role / form
    if (folder / "result.json").is_file():
        old = load(folder / "result.json")
        assert old["packet_sha256"] == task["sha256"]
        return
    prompt = PROMPT + "\n" + json.dumps(packet, ensure_ascii=False)
    a, started, secs, types, events = isolated_cli(folder, prompt, SCHEMA)
    allowed = {
        r["id"] for r in packet["issuer_evidence"] + packet["candidate_evidence"]
    }
    if not a["evidence_ids"] or not set(a["evidence_ids"]) <= allowed:
        raise ValueError("Unprovided evidence cited")
    th = next(r["thread_id"] for r in events if "thread_id" in r)
    dump(
        folder / "result.json",
        {
            "item": item,
            "role": role,
            "form": form,
            "started_utc": started,
            "elapsed_s": secs,
            "thread_id": th,
            "usage": [e["usage"] for e in events if "usage" in e],
            "event_types": sorted(set(types)),
            "answer": a,
            "packet_sha256": task["sha256"],
            "prompt_sha256": sha(prompt.encode()),
            "answer_sha256": sha((folder / "answer.json").read_bytes()),
        },
    )
    print(item, role, form, flush=True)


def summarize():
    spec = freeze()
    labels = load(LABEL)
    results = {}
    threads = set()
    token_sum = {}
    wall = 0
    starts = []
    finishes = []
    for item in PEERS:
        pair = {}
        for role in ROLES:
            trial = {}
            for form in FORMS:
                folder = BASE / "runs" / item / role / form
                run = load(folder / "result.json")
                if (
                    run["thread_id"] in threads
                    or run["started_utc"] <= spec["frozen_utc"]
                ):
                    raise ValueError("Need independently frozen run")
                threads.add(run["thread_id"])
                wall += run["elapsed_s"]
                starts.append(datetime.fromisoformat(run["started_utc"]).timestamp())
                finishes.append(starts[-1] + run["elapsed_s"])
                for u in run["usage"]:
                    for k, v in u.items():
                        if isinstance(v, int):
                            token_sum[k] = token_sum.get(k, 0) + v
                assert run["answer_sha256"] == sha(
                    (folder / "answer.json").read_bytes()
                )
                assert run["prompt_sha256"] == sha(
                    (folder / "input.txt").read_text(encoding="utf8").encode()
                )
                trial[form] = run["answer"]
            base, fmt, change = [trial[x] for x in FORMS]
            checks = {
                "original_reproduced": base["decision"] == "수용"
                and base["product_overlap"] == "proven"
                and "B" in base["evidence_ids"],
                "format_preserved": base["decision"] == fmt["decision"]
                and fmt["product_overlap"] == "proven"
                and "B" in fmt["evidence_ids"],
                "direction_responsive": change["product_overlap"] == "unknown"
                and "C" in change["evidence_ids"]
                and "B" not in change["evidence_ids"],
            }
            pair[role] = {"decisions": trial, "checks": checks}
        robust = all(all(d["checks"].values()) for d in pair.values())
        status = "원본 근거 재현" if robust else "원본 근거 재확인"
        signal = (
            "양 역할의 원본 제품 중첩 판단이 재현되어 이 항목에 추가 검토 신호를 부여하지 않는다."
            if robust
            else "두 역할의 합의가 시험 전반에서 일관되게 뒷받침되지 않아 원본의 제품 매출 근거를 다시 확인한다."
        )
        labels["cases"]["TRUEN"].setdefault("triz", []).append(
            {"item_id": item, "status": status, "signal": signal}
        )
        results[item] = pair
    assert len(threads) == 12
    for c in labels["cases"].values():
        c.setdefault("triz", [])
    d = {
        "eligibility": ELIGIBILITY,
        "original_labels_sha256": sha(LABEL.read_bytes()),
        "freeze": str((BASE / "freeze.json").relative_to(ROOT)),
        "tests": results,
        "actual_sessions": len(threads),
        "sum_role_seconds": round(wall, 3),
        "observed_parallel_wall_seconds": round(max(finishes) - min(starts), 3),
        "tokens": token_sum,
        "known_usd": None,
        "official_H1": False,
        "review": [
            {
                "round": 1,
                "check": "5개 합의에서 근거가 일치하고 관련 반대 근거가 해결되는지 점검했다.",
                "remedy": "FC-BGA 단위 노출과 규모·수익성에 기반한 합의를 방향 실험에서 제외했고 저장장치 비중은 후보 별도 연차보고서까지 대조했다.",
            },
            {
                "round": 2,
                "check": "형태 변경 전후 항목 집합의 동일성과 방향 변경 후 제품 근거의 잔존 여부를 확인했다.",
                "remedy": "카메라 관련 후보 근거를 한 행에 모아 제거했으며, 연결·저장 장비를 카메라 완제품으로 추론하지 않도록 동일 질문을 사용했다.",
            },
            {
                "round": 3,
                "check": "사전 등록 일시·기대와 역할 12개 세션의 해시·인용·실제 결과를 확인했다.",
                "remedy": "내용 변경에 따른 근거 판단과 최종 수용 등급을 따로 대조했다. 선택기에는 시험용 텍스트·기대·변형 답변을 전달하지 않았다.",
            },
        ],
        "scope": "일부 발췌를 사용한 독립 Codex CLI 대리 실행. 가격·재무 적격 또는 전체 비교대상 모집단을 시험하지 않았다.",
    }
    dump(BASE / "audit.json", d)
    dump(DEST / "proxy" / "labels_triz.json", labels)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("op", choices=["freeze", "run", "summarize"])
    a = p.parse_args()
    if a.op == "freeze":
        freeze()
    elif a.op == "run":
        run_spec = freeze()
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(execute, run_spec["task_order"]))
    else:
        summarize()
