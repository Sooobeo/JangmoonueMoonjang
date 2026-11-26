"""Freeze original-file validation items and obtain blind, evidence-quoted proxy ratings.

The four validation cases are retired from the evaluation roster before rating.
No model output, trial condition, ranking, or previous grade enters either pass.
"""

import argparse
import hashlib
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz
import httpx

from scripts.current_b import OUT, ROOT, dump
from scripts.current_live import S, arr, ask, digest, load, obj

PEERS = {
    "GIGAVIS": ["고영테크놀러지", "파크시스템스", "넥스틴", "인텍플러스"],
    "TRUEN": ["포커스에이치엔에스", "아이디스", "위세아이텍"],
    "MANYO": ["클리오", "아이패밀리에스씨", "네오팜", "애경산업", "브이티지엠피"],
    "PHILENERGY": ["피엔티", "에이프로", "엔시스"],
}
COMMON = [
    ("J1", "발행사 적용 이익의 기간"),
    ("J1", "이익의 회계상 귀속 범위"),
    ("J3", "비교기업 기준주가의 관측기간·선택"),
    ("J3", "비교기업 PER의 집계 방식"),
    ("J3", "발행사 적용 주식 수"),
    ("J3", "주당 평가가액 계산"),
    ("J3", "공모가 할인율과 밴드"),
]
GRADES = ["수용 가능", "비중대 쟁점", "중대 쟁점", "판정 유보"]
ROW = obj(
    {
        "item_id": S,
        "grade": {"type": "string", "enum": GRADES},
        "reason": S,
        "physical_page": {"type": "integer"},
        "quote": S,
    }
)
GRADE = obj({"items": arr(ROW)})
RULE = """최초 증권신고서의 공모가 판단을 검토하는 독립 AI 대행 평가자다. 모든 항목을 지정된 네 등급으로 채점한다. 단순히 다른 가정에서 가격이 달라지는 것은 오류의 증거가 아니다. 중대 쟁점은 원문에서 확인되는 사실 오적용 또는 중요한 반대 근거 누락이 선정·산정 판단을 바꾸거나 적격 대안의 5% 이상 가격 차이를 뒷받침할 때다. 자료 부족으로 확정할 수 없으면 판정 유보. 각 행에 실제 원문 물리 쪽과 연속된 짧은 직접 인용을 적고, 근거와 남은 한계를 한국어로 설명한다. 인용은 표 셀 하나나 짧은 구절로 충분하다."""


def compact(t):
    return re.sub(r"\s+", "", t)


def verify(answers, ids, pages):
    rows = answers["items"]
    if len(rows) != len(ids) or {r["item_id"] for r in rows} != set(ids):
        raise ValueError("Provide exactly one row per assigned item ID")
    for row in rows:
        snippet = compact(row["quote"])
        if not snippet or snippet not in compact(
            pages.get(str(row["physical_page"]), "")
        ):
            raise ValueError(
                "Copy a contiguous, verbatim phrase at the claimed physical page for "
                + row["item_id"]
            )


def cases():
    registry = load(ROOT / "reports/a1_development/filing_screening.json")
    return sorted(
        [r for r in registry["cases"] if "EVAL" in r["case_id"]],
        key=lambda r: r["receipt_no"],
    )[:4]


def prepare(row):
    from pypdf import PdfReader

    from scripts.screen_a1_first_filings import get

    case = row["case_id"].split("-")[0]
    cache = Path(tempfile.gettempdir()) / "ipo_a1_initial_registrations"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (row["receipt_no"] + ".pdf")
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        content = get(client, row["pdf_url"], path)
    if hashlib.sha256(content).hexdigest() != row["pdf_sha256"]:
        raise ValueError("Wrong original PDF version")
    prices_page = row["price_table_pdf_page"]
    with fitz.open(path) as d:
        pages = {
            str(n): d[n - 1].get_text(sort=True)
            for n in range(prices_page - 16, prices_page + 4)
        }
        # Also include independently located income notes and financial statements.
        for term in (
            "연결포괄손익계산서",
            "주식기준보상",
            "파생상품평가손실",
            "영업부문",
            "주요 제품 및 서비스",
        ):
            candidates = [
                p
                for p in d
                if p.number + 1 > prices_page + 5 and term in compact(p.get_text())
            ]
            for p in candidates[:2]:
                pages[str(p.number + 1)] = p.get_text(sort=True)
    second_decoder = compact(
        " ".join(PdfReader(path).pages[prices_page - 1].extract_text().split())
    )
    assert "PER" in second_decoder and "주당평가가액" in second_decoder
    body = compact(" ".join(pages.values()))
    peers = PEERS[case]
    assert all(compact(peer) in body for peer in peers)
    definitions = list(COMMON)
    if case in {"GIGAVIS", "PHILENERGY"}:
        definitions.append(("J1", "주식보상비용 또는 파생상품 손익 조정"))
    definitions += [("J2", f"{p}의 사업 비교 적합성") for p in peers]
    items = [
        {"item_id": f"{case}-{i:02}", "question_type": kind, "question": q}
        for i, (kind, q) in enumerate(definitions, 1)
    ]
    return {
        "case": case,
        "receipt": row["receipt_no"],
        "pdf_sha256": row["pdf_sha256"],
        "source_url": row["pdf_url"],
        "input_scope": "valuation section and located company financial note excerpts",
        "items": items,
        "pages": pages,
    }


def rate(pack, assessor=ask):
    case = pack["case"]

    def score(stage, items):
        return assessor(
            case,
            stage,
            RULE,
            {"items": items, "pages": pack["pages"]},
            GRADE,
            4600,
            lambda a: verify(a, [v["item_id"] for v in items], pack["pages"]),
        )

    first = score("VALIDATION_PROXY_FIRST", pack["items"])
    sample = sorted(pack["items"], key=lambda r: digest(["repeat", r["item_id"]]))[:6]
    repeat = score("VALIDATION_PROXY_REPEAT", sample)
    first_rows = {r["item_id"]: r for r in first["answer"]["items"]}
    differences = [
        r
        for r in repeat["answer"]["items"]
        if r["grade"] != first_rows[r["item_id"]]["grade"]
    ]
    if differences:
        keys = {r["item_id"] for r in differences}
        items = [i for i in pack["items"] if i["item_id"] in keys]
        payload = {
            "items": items,
            "pages": pack["pages"],
            "first": [first_rows[i] for i in sorted(keys)],
            "repeat": differences,
        }
        final = assessor(
            case,
            "VALIDATION_PROXY_RECONCILE",
            RULE + " 두 선행 판정과 원문을 대조해 최종 판정을 기록한다.",
            payload,
            GRADE,
            3500,
            lambda a: verify(a, sorted(keys), pack["pages"]),
        )
        first_rows.update({r["item_id"]: r for r in final["answer"]["items"]})
    rows = list(first_rows.values())
    return {
        "case": case,
        "items": rows,
        "repeat_n": len(sample),
        "initial_disagreements": len(differences),
        "major": sum(r["grade"] == "중대 쟁점" for r in rows),
        "other": sum(r["grade"] in GRADES[:2] for r in rows),
        "pending": sum(r["grade"] == "판정 유보" for r in rows),
        "human_minutes": None,
        "review": [
            "verified original hash, both PDF decoders and item coverage",
            "blind six-item second rating and quote check on every submission",
            "adjudicated different ratings against source, audited counts",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-proxy", action="store_true")
    opts = parser.parse_args()
    from scripts.current_proxy import ask_proxy

    packs = list(map(prepare, cases()))
    freeze = {
        p["case"]: {
            "receipt": p["receipt"],
            "sha256": p["pdf_sha256"],
            "items": p["items"],
            "packet_hash": digest(p),
        }
        for p in packs
    }
    f = OUT / "validation/freeze.json"
    if f.exists() and load(f) != freeze:
        raise ValueError("Validation inputs changed since freeze")
    dump(f, freeze)

    def process(pack):
        result = rate(pack, ask_proxy if opts.codex_proxy else ask)
        result["grader"] = "CODEX_PROXY" if opts.codex_proxy else "TERRA_PROXY"
        target = OUT / "validation" / ("codex" if opts.codex_proxy else "terra")
        dump(target / (result["case"] + ".json"), result)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(process, packs))


if __name__ == "__main__":
    main()
