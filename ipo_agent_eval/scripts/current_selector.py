"""Rank and allocate original items without access to the reference grades."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import fitz

from scripts.current_b import OUT, ROOT, dump, filing
from scripts.current_live import S, arr, ask, load, obj
from scripts.current_validation import cases as validation_cases
from scripts.current_validation import prepare

D = Decimal
ACTIONS = ["사람 검토", "자료 요청", "기록 보관"]
LOOK = obj({"physical_pages": {**arr({"type": "integer"}), "maxItems": 4}, "reason": S})
ROW = obj(
    {
        "item_id": S,
        "action": {"type": "string", "enum": ACTIONS},
        "priority": {"type": "integer", "minimum": 1, "maximum": 100},
        "reason": S,
        "evidence_ids": arr(S),
        "question_or_request": S,
    }
)
DECISION = obj({"items": arr(ROW)})
PROMPT = """최초 신고서 원본 항목 전부에 대해 A0와 가림 검토자 C의 근거를 대조하는 A1이다. 제공된 원문과 B 계산만 사실 근거로 사용한다. 갈림은 원문에서 기간·분모·사업범위를 맞추고 해소 여부를 판단한다. 수용 합의의 근거 점검 결과는 원본을 재검토할 단서다. 검토 중대성, 원문에서 확인 가능한 쟁점, 가격 영향을 순서대로 고려해 1~100 우선순위 점수를 매긴다(클수록 먼저, 실제 동률 허용). 가정 대안의 가격 영향만으로 오류로 판단하지 않는다. 사람 검토는 실제 중요한 확인 질문, 자료 요청은 결정적인 부족 자료, 기록 보관은 해소 근거나 비중대 사유를 적는다. 확인한 내용만 인용하고 실제 제공된 원문 ID를 사용한다. 모든 항목에 조치·사유·근거와 필요한 질문을 기록한다. 자료 부족을 중대 오류로 확정하지 않는다. 한국어로 제출한다."""


def state(role):
    return role.get("judgment", role.get("state", "미확인"))


def evidence_ids(role):
    refs = list(role.get("evidence_ids") or role.get("evidence_refs") or [])
    for e in role.get("evidence") or []:
        if isinstance(e, str):
            refs.append(e)
        elif isinstance(e, dict):
            refs.extend(
                e.get("source_refs")
                or e.get("evidence_refs")
                or e.get("evidence_ids")
                or []
            )
            for key in ("source_id", "evidence_id"):
                if e.get(key):
                    refs.append(e[key])
    return {r for r in refs if isinstance(r, str)}


def rule_table(items, sources, impacts, mandatory):
    ranking = []
    for row in items:
        key = row["item_id"]
        roles = [row["a0"], row["c"]]
        challenge = any(
            state(r) == "문제 제기" and evidence_ids(r).intersection(sources)
            for r in roles
        )
        group = 0 if challenge else 1 if any(state(r) == "미확인" for r in roles) else 2
        impact = impacts.get(key)
        raw = (group, impact is None, -D(str(impact)) if impact is not None else D("0"))
        ranking.append((key, raw, challenge))
    ranking.sort(key=lambda r: (r[1], r[0]))
    return {
        "items": [
            {"item_id": k, "tie_key": str(raw), "eligible": eligible}
            for k, raw, eligible in ranking
            if k not in mandatory
        ]
    }


def original_inputs(case):
    if case in {"HDMS", "MELCON"}:
        path, _, _ = filing(case)
        reg = load(ROOT / "data/a1_pilot" / case / "operator/original_items.json")
        page_index = {
            i["id"]: list(
                dict.fromkeys([i["page"], *i.get("also", []), *i.get("pages", [])])
            )
            for i in reg["items"]
        }
        b = next(c for c in load(OUT / "b.json")["cases"] if c["case_id"] == case)
        if case == "HDMS":
            prices = load(ROOT / "reports/a1_development/hdms_original_preflight.json")[
                "estimated_alternatives_using_published_inputs"
            ]
        else:
            prices = load(
                ROOT / "data/a1_pilot/MELCON/operator/original_source_checks.json"
            )["estimates_from_displayed_inputs"]
        impact = {
            k: next(v for n, v in row.items() if n.startswith("absolute_change"))
            for k, row in prices.items()
        }
        with fitz.open(path) as doc:
            pages = {
                n: doc[n - 1].get_text(sort=True)
                for n in sorted({v for vs in page_index.values() for v in vs})
            }
        return page_index, pages, b, impact
    spec = next(r for r in validation_cases() if r["case_id"].startswith(case + "-"))
    pack = prepare(spec)
    pages = {int(k): v for k, v in pack["pages"].items()}
    p = spec["price_table_pdf_page"]
    index = {
        i["item_id"]: (
            [p, p - 1] if i["question_type"] != "J2" else list(range(p - 8, p + 1))
        )
        for i in pack["items"]
    }
    b = load(OUT / "validation/b.json")[case]
    return index, pages, b, b.get("price_impact_fraction", {})


def grade_free_case(case, labels, proxy=False, without_triz=False, held_items=(), lookup_output_limit=1100,
                    compact_lookup=False):
    from scripts.current_proxy import ask_proxy

    assessor = ask_proxy if proxy else ask
    index, pages, b, impact = original_inputs(case)
    items = labels["items"]
    keys = set(index)
    initial_pages = {ps[0] for ps in index.values()}
    if keys != {r["item_id"] for r in items} or len(items) != len(keys):
        raise ValueError("Mismatch between frozen registry and label keys for " + case)
    if held_items:
        held = set(held_items)
        if not held < keys or held.intersection(b["mandatory"]):
            raise ValueError("Deferral must retain every mandatory item and a decision set")
        keys = keys - held
        items = [r for r in items if r["item_id"] in keys]
        index = {key: value for key, value in index.items() if key in keys}
    sources = labels.get("sources", labels.get("source_index", {}))
    if isinstance(sources, list):
        sources = {s.get("source_id") or s["evidence_id"]: s for s in sources}
    mandatory = b["mandatory"]
    original_pages = {
        f"PDF-{p}": v for p, v in pages.items() if p in initial_pages
    }
    source_text = {}
    for k, s in sources.items():
        if isinstance(s, str):
            source_text[k] = s
        else:
            v = s.get("excerpt") or s.get("text") or s.get("quote") or s.get("fact")
            if v:
                source_text[k] = v
    allowed = {**source_text, **original_pages}
    rule = rule_table(items, allowed, impact, mandatory)
    payload = {
        "original_items": items,
        "original_sources": allowed,
        "b_record": b,
        "original_price_impacts": impact,
        "physical_page_index": index,
        "materiality": "공개 근거가 선택을 바꿀 가능성 또는 적격 대안 5% 이상. 민감도 단독은 불충분.",
        "triz": [] if without_triz else labels.get("triz", []),
        "mandatory": mandatory,
        "additional_k": 1,
    }

    def check_look(a):
        picks = a["physical_pages"]
        if len(picks) != len(set(picks)) or not set(picks) <= pages.keys():
            raise ValueError("Choose distinct available page numbers from the catalog.")

    req = {**payload, "available_pages": sorted(pages)}
    lookup_prompt = PROMPT + " 같은 기업 선별의 조회 단계다. 실제 불일치 확인에 필요한 물리 쪽을 0~4개 고른다."
    if compact_lookup:
        req = {
            "item_catalog": [{"id": row["item_id"], "question": row["question"],
                              "a0": state(row["a0"]), "c": state(row["c"]),
                              "a0_reason": row["a0"].get("reason", "")[:180],
                              "c_reason": row["c"].get("reason", "")[:180],
                              "pages": index[row["item_id"]]} for row in items],
            "available_pages": sorted(pages), "triz": payload["triz"],
        }
        lookup_prompt = ("공시 심사에서 원문을 더 읽을 쪽만 고른다. 목록에서 서로 판단이 갈리거나 확인이 필요한 항목의 "
                         "관련 물리 쪽을 합계 0~4개 반환한다. reason에는 선택 근거를 한 문장으로 쓴다.")
    lookup = assessor(
        case,
        "A1_LOOK",
        lookup_prompt,
        req,
        LOOK,
        lookup_output_limit,
        check_look,
    )
    reads = {f"PDF-{p}": pages[p] for p in lookup["answer"]["physical_pages"]}
    cite = set(allowed) | set(reads)

    def check_output(a):
        submitted = [r["item_id"] for r in a["items"]]
        if len(submitted) != len(keys) or set(submitted) != keys:
            raise ValueError("Supply exactly one row per original item ID.")
        for row in a["items"]:
            if not set(row["evidence_ids"]) <= cite:
                raise ValueError(
                    "Use exact provided original_sources or additional_read IDs for "
                    + row["item_id"]
                )
            if (
                not row["reason"].strip()
                or row["action"] != "자료 요청"
                and not row["evidence_ids"]
            ):
                raise ValueError(
                    "Supply reason and valid original citations for " + row["item_id"]
                )
            if row["action"] != "기록 보관" and not row["question_or_request"].strip():
                raise ValueError(
                    "Supply concrete question or document request for " + row["item_id"]
                )

    selection = assessor(
        case,
        "A1_SELECT",
        PROMPT,
        {**payload, "additional_read": reads},
        DECISION,
        3800,
        check_output,
    )
    sorted_ai = sorted(
        selection["answer"]["items"], key=lambda r: (-r["priority"], r["item_id"])
    )
    ai = {
        "items": [
            {**r, "tie_key": str(r["priority"]), "eligible": r["action"] == "사람 검토"}
            for r in sorted_ai
            if r["item_id"] not in mandatory
        ]
    }
    for arm in (ai, rule):
        arm["fixed_k"] = mandatory + [r["item_id"] for r in arm["items"][:1]]
        eligible = [r["item_id"] for r in arm["items"] if r["eligible"]]
        arm["operational"] = mandatory + eligible[:1]
        arm["waiting"] = eligible[1:]
    result = {
        "case": case,
        "mandatory": mandatory,
        "rule": rule,
        "ai": ai,
        "lookup_pages": list(reads),
        "lookup_run": lookup["evidence_dir"],
        "decision_run": selection["evidence_dir"],
        "triz": payload["triz"],
        "common_item_count": len(items),
        "presented_refs": sorted(cite),
        "selector_seconds": lookup["summary"]["elapsed_seconds"]
        + selection["summary"]["elapsed_seconds"],
    }
    if lookup_output_limit != 1100:
        result["technical_recovery_lookup_output_limit"] = lookup_output_limit
    if compact_lookup:
        result["lookup_method"] = "compact_catalog_recovery_v1"
    result["selector_condition"] = "CODEX_PROXY" if proxy else "TERRA"
    group = "proxy" if proxy else "terra"
    if without_triz:
        group += "_without_triz"
    if held_items:
        result["held_items"] = sorted(held_items)
        target = OUT / "deferral/remaining_selector.json" if proxy else OUT / "official/deferral" / (case + ".json")
        dump(target, result)
    else:
        dump(OUT / "ranking" / group / (case + ".json"), result)
    return result


def read_cases(path):
    bundle = load(path)["cases"]
    if isinstance(bundle, dict):
        return bundle
    return {r["case_id"].split("-")[0]: r for r in bundle}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("labels", type=Path)
    parser.add_argument("--codex-proxy", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--without-triz", action="store_true")
    parser.add_argument("--compact-lookup", action="store_true")
    parser.add_argument("--lookup-recovery-output-limit", type=int, choices=range(1101, 2201), metavar="1101-2200")
    args = parser.parse_args()
    cases = read_cases(args.labels)
    if args.case:
        cases = {args.case: cases[args.case]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda c: grade_free_case(c, cases[c], args.codex_proxy, args.without_triz,
                                                lookup_output_limit=args.lookup_recovery_output_limit or 1100,
                                                compact_lookup=args.compact_lookup), cases))


if __name__ == "__main__":
    main()
