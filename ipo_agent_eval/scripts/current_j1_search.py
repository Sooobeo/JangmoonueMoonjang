"""Review every frozen development J1 row with a uniform whole-filing search."""

import argparse
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import fitz

from scripts.current_b import OUT, ROOT, dump, filing
from scripts.current_live import S, arr, digest, load, obj
from scripts.current_proxy import ask_proxy

TARGET = OUT / "j1_search"
CASES = ("HDMS", "MELCON")
CAP = 4
NUM = re.compile(r"(?<![\d,])(?:\(\d{1,3}(?:,\d{3})+\)|[-−]?\d{1,3}(?:,\d{3})+)(?![\d,])")
FAIR = ("금융자산평가이익", "금융자산처분이익")
ANNUAL = ("당기순이익의귀속", "지배지분소유주", "지배기업의소유주", "지배기업소유주", "지배주주지분")
INTERIM = ("지배기업지분보통주당기순이익", "지배기업소유주지분당기순이익", "지배주주에게귀속되는당기순이익")
PROMPT = """개발 A1의 J1 원문 범위를 검증한다. 주어진 J1 항목을 각각 한 번 다룬다. 기존 공시 발췌와 추가로 찾은 최초 신고서 원문의 기간·귀속 범위·단위를 대조하라. B의 대안 계산은 같은 가정을 적용할 때의 시나리오다. 중요한 근거를 확인했으면 해결 범위와 남은 한계, 사람이 검토할 쟁점 또는 구체 자료 요청을 적는다. 신고서 기재 방식과 주관사의 원자료 확인 필요성을 구분한다. 조정 항목의 세후 효과와 공시 문구의 의미를 추정하지 않는다. 인용할 때는 제시된 물리 쪽 ID만 쓰고, 제시한 한 쟁점이 전체 우선순위를 바꾼다고 추론하지 않는다. 한국어 JSON을 반환한다."""
REVIEW = obj({"items": arr(obj({"item_id": S, "status": {"type": "string", "enum": ["해소", "부분 확인", "미확인"]},
                               "action": {"type": "string", "enum": ["사람 검토", "자료 요청", "기록 보관"]},
                               "confirmed": S, "remaining": S, "evidence_ids": arr(S)}))})


def compact(text):
    return "".join(text.split())


def contents(path):
    with fitz.open(path) as doc:
        return {number: page.get_text(sort=True) for number, page in enumerate(doc, 1)}


def search_score(text):
    serial = compact(text)
    attribution = sum(phrase in serial for phrase in ANNUAL)
    attribution_table = int("당기순이익의귀속" in serial and attribution >= 2)
    decimal_columns = sum(len(NUM.findall(line)) >= 3 for line in text.splitlines())
    timely_adjustments = sum(term in serial for term in FAIR)
    comparative = int("당반기" in serial and "전반기" in serial)
    onward_cashflow = int("현금흐름표" in serial and decimal_columns >= 1)
    after_gain = int("금융수익" in serial and "금융원가" in serial)
    sales_concentration = int("계절성" in serial and "연환산" in serial)
    prior_earn = max((len(NUM.findall(line)) for line in text.splitlines()
                      if any(term in compact(line) for term in INTERIM)), default=0)
    return {
        "annual_parent_profit": (10 * attribution_table + min(decimal_columns, 4)) if attribution_table else 0,
        "current_prior_interim_parent_profit": 10 * comparative + prior_earn if comparative and prior_earn >= 2 else 0,
        "annual_and_current_adjustment_rows": 10 * onward_cashflow + min(decimal_columns, 5)
        if onward_cashflow and timely_adjustments == 2 else 0,
        "comparative_interim_adjustment_rows": 10 * after_gain + comparative
        if comparative and after_gain and timely_adjustments == 2 else 0,
        "seasonality_supplement": 10 * sales_concentration + int("영업이익비중" in serial) if sales_concentration else 0,
    }


def coverage(book, already):
    scores = {page: search_score(text) for page, text in book.items()}
    role_ranking = {
        key: sorted(((page, row[key]) for page, row in scores.items() if row[key]), key=lambda item: (-item[1], item[0]))
        for key in next(iter(scores.values()))
    }
    chosen = []
    anchors = {}
    for role, hits in role_ranking.items():
        if not hits:
            continue
        best, _ = hits[0]
        if best in already or best in chosen:
            anchors[role] = best
        elif len(chosen) < CAP:
            anchors[role] = best
            chosen.append(best)
    return chosen, anchors, role_ranking


def source_rows(text, matcher, n):
    candidates = [line.strip() for line in text.splitlines() if matcher(compact(line)) and len(NUM.findall(line)) >= n]
    if not candidates:
        raise ValueError("Required sourced numeric row is absent")
    line = candidates[0]
    values = [Decimal(v.replace("(", "-").replace(")", "").replace("−", "-").replace(",", "")) for v in NUM.findall(line)]
    return values[:n], line


def ltm(book, table, b, permitted):
    keys = ("annual_parent_profit", "current_prior_interim_parent_profit",
            "annual_and_current_adjustment_rows", "comparative_interim_adjustment_rows")
    if not set(keys) <= table.keys():
        return {"status": "미산출", "reason": "같은 기준 온기·두 반기 귀속순이익 및 조정행이 함께 확인되지 않음"}
    annual, comparative, bridge, notes = (table[key] for key in keys)
    if not {annual, comparative, bridge, notes} <= permitted:
        raise ValueError("LTM sources outside provided evidence")
    try:
        annual_comparison, annual_row = source_rows(
            book[annual], lambda s: s.startswith(("지배지분소유주", "지배기업의소유주")), 2
        )
        (h1, prior), h1_row = source_rows(book[comparative], lambda s: any(term in s for term in INTERIM), 2)
        (bridge_h1, fy), fy_row = source_rows(book[bridge], lambda s: s.startswith("1.당기순이익"), 2)
        if bridge_h1 != h1 or annual_comparison != [h1, fy]:
            raise ValueError("Annual and interim profit rows do not align")
        bridge_flat = compact(book[bridge])
        notes_flat = compact(book[notes])
        if not ("단위:원" in bridge_flat and "단위:천원" in notes_flat and "당반기전반기" in notes_flat):
            raise ValueError("Source column/unit tags are insufficient for a fixed-unit LTM calculation")
        adjustments = []
        for term in FAIR:
            (now_reversal, annual_reversal), yr = source_rows(book[bridge], lambda s, term=term: term in s, 2)
            (now_rounded, old_rounded), half = source_rows(book[notes], lambda s, term=term: term in s, 2)
            if max(now_reversal, annual_reversal) > 0:
                raise ValueError("Gain rows must be cash flow reversals")
            now_gain, annual_gain = -now_reversal, -annual_reversal
            current_and_note_difference = abs(now_gain - now_rounded * 1000)
            if current_and_note_difference > 500:
                raise ValueError("Current annual roll-up and thousand-KRW note do not agree at displayed precision")
            adjustments.append({"category": term, "current_interim_krw": now_gain, "prior_annual_krw": annual_gain,
                                "prior_interim_krw": old_rounded * 1000,
                                "annual_current_row": yr, "interim_note_row": half})
        profits = {"current_interim_krw": h1, "prior_annual_krw": fy, "prior_interim_krw": prior}
        adjusted = {key: val - sum(row[key] for row in adjustments) for key, val in profits.items()}
        value = adjusted["prior_annual_krw"] + adjusted["current_interim_krw"] - adjusted["prior_interim_krw"]
        fact = b["facts"]
        per = Decimal(fact["per"]["display"])
        share = Decimal(fact["shares"]["display"].replace(",", "")) * (1000 if fact["shares"]["unit"] == "천주" else 1)
        published = Decimal(fact["price"]["display"].replace(",", ""))
        estimate = value * per / share
    except (ValueError, KeyError) as exc:
        return {"status": "미산출", "reason": str(exc)}
    return {
        "status": "가정 대안 산출", "scope": "연결 귀속 순이익을 최근 네 분기로 맞추고 평가·처분이익 차감을 동일 적용한 총액 기준 민감도다. 전반기 조정행은 천원 표시이며 세후 귀속 조정은 추가 가공하지 않았다.",
        "source_pages": dict(zip(keys, (annual, comparative, bridge, notes), strict=True)),
        "period_rows": {"annual_attribution": annual_row, "annual_profit": fy_row, "current_prior_profit": h1_row},
        "raw_profit": {k: str(v) for k, v in profits.items()}, "adjusted_profit": {k: str(v) for k, v in adjusted.items()},
        "adjustments": [{k: str(v) if isinstance(v, Decimal) else v for k, v in a.items()} for a in adjustments],
        "adjusted_ltm_krw": str(value), "displayed_per": str(per), "applied_shares": str(share),
        "published_price_krw": str(published), "alternative_price_krw": str(estimate.quantize(Decimal(".01"))),
        "relative_change_pct": str(((estimate / published - 1) * 100).quantize(Decimal(".0001"))),
    }


def prepare(case, labels):
    baseline_path = OUT / "ranking/proxy" / f"{case}.json"
    baseline = load(baseline_path)
    raw_request = load(ROOT / baseline["decision_run"] / "request.json")["input"]
    rows = [row for row in labels["items"] if row["question_type"].startswith("J1")]
    if not rows or len({row["item_id"] for row in rows}) != len(rows):
        raise ValueError(f"Invalid J1 item coverage for {case}")
    book_path, prov, identity = filing(case)
    book = contents(book_path)
    initial = set()
    for ref in {*raw_request["original_sources"], *raw_request["additional_read"]}:
        match = re.fullmatch(r"(?:PDF-|[HM]-P)(\d+)", ref)
        if match:
            initial.add(int(match[1]))
    chosen, anchors, rankings = coverage(book, initial)
    if len(chosen) > CAP or len(set(chosen)) != len(chosen) or initial.intersection(chosen):
        raise ValueError("Additional catalog must contain only bounded new pages")
    sought = {p for row in rows for p in raw_request["physical_page_index"][row["item_id"]]}
    refs = {r for row in rows for role in ("a0", "c") for r in (row[role].get("evidence_refs") or [])}
    common = {k: v for k, v in raw_request["original_sources"].items() if k in refs or
              (k.startswith("PDF-") and int(k.split("-")[-1]) in sought)}
    common.update({k: v for k, v in raw_request["additional_read"].items() if int(k.split("-")[-1]) in sought})
    for page in anchors.values():
        if page in initial:
            ref = next((k for k in raw_request["original_sources"] if re.fullmatch(r"(?:PDF-|[HM]-P)0*" + str(page), k)), None)
            if ref:
                common[ref] = raw_request["original_sources"][ref]
            elif f"PDF-{page}" in raw_request["additional_read"]:
                common[f"PDF-{page}"] = raw_request["additional_read"][f"PDF-{page}"]
            else:
                raise ValueError("Already presented anchor missing")
    alt = ltm(book, anchors, raw_request["b_record"], set(chosen) | initial)
    payload = {"j1_items": [{"item_id": r["item_id"], "question": r["question"], "a0": r["a0"]["reason"],
                             "c": r["c"]["reason"]} for r in rows],
               "baseline_excerpts": common, "new_original_pages": {f"PDF-{p}": book[p] for p in chosen},
               "B_shared": raw_request["b_record"], "B_LTM_sensitivity": alt}
    manifest = {"case_id": case, "filing_sha256": identity, "receipt": prov["receipt_no"],
                "baseline_sha256": digest(baseline), "review_item_ids": [r["item_id"] for r in rows],
                "whole_document_page_count": len(book), "anchor_pages": anchors, "new_pages": chosen,
                "search_candidates": {key: [list(hit) for hit in hits[:8]] for key, hits in rankings.items()},
                "input_sha256": digest(payload), "prompt_sha256": digest(PROMPT)}
    destination = TARGET / case
    frozen = destination / "freeze.json"
    if frozen.exists() and load(frozen) != manifest:
        raise ValueError("J1 frozen inputs changed")
    dump(frozen, manifest)
    dump(destination / "input.json", payload)
    return manifest, payload


def submit(case, prepared):
    freeze, payload = prepared
    ids = set(freeze["review_item_ids"])
    refs = set(payload["baseline_excerpts"]) | set(payload["new_original_pages"])

    def verify(answer):
        if len(answer["items"]) != len(ids) or {r["item_id"] for r in answer["items"]} != ids:
            raise ValueError("각 J1 원본 항목 ID를 한 번씩 평가한다")
        for row in answer["items"]:
            if not row["evidence_ids"] or not set(row["evidence_ids"]) <= refs:
                raise ValueError(f"{row['item_id']}는 실제 제공된 근거 ID를 인용한다")

    response = ask_proxy(case, "J1_WHOLE_FILING", PROMPT, payload, REVIEW, 2200, verify)
    attempts = load(ROOT / response["evidence_dir"] / "attempts.json")
    if any(row["tool_events"] for row in attempts):
        raise ValueError("J1 reviewer used a tool")
    result = {"case_id": case, "items": response["answer"]["items"], "new_pages": freeze["new_pages"],
              "ltm": payload["B_LTM_sensitivity"], "evidence_dir": response["evidence_dir"],
              "summary": response["summary"], "attempts": len(attempts)}
    dump(TARGET / case / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    data = {c["case_id"]: c for c in load(OUT / "proxy/labels_dev_mixed.json")["cases"]}
    plans = {case: prepare(case, data[case]) for case in CASES}
    if args.prepare_only:
        for case, (freeze, payload) in plans.items():
            print(case, freeze["review_item_ids"], freeze["new_pages"], payload["B_LTM_sensitivity"].get("status"))
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            completed = list(pool.map(lambda case: submit(case, plans[case]), CASES))
        dump(TARGET / "summary.json", {"scope": "development-only, grade-free bounded catalog sensitivity",
                                       "frozen_baseline_preserved": True, "cases": completed})
        print("Completed", len(completed), "development issuers")
