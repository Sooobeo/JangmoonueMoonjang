"""Post-run development check of one information request against the permitted original PDF."""

import re

import fitz

from scripts.current_b import OUT, dump, filing
from scripts.current_live import S, arr, load, obj
from scripts.current_proxy import ask_proxy


def norm(s):
    return re.sub(r"\s+", "", s)


# Fixed search patterns over the original full filing rather than item outcome labels.
QUERIES = [
    ("반기 계절성", ["상반기", "하반기", "계절성", "매출", "영업이익"]),
    (
        "지배주주 손익 기간표",
        ["2025년", "2026년", "지배기업", "소유주", "반기", "당기순이익", "누적"],
    ),
    (
        "금융자산 조정 구성",
        ["처분이익", "평가이익", "평가손실", "2025년", "2026년", "금융"],
    ),
    (
        "주당이익 비교기간",
        ["기본주당순이익", "지배기업", "소유주", "2025년", "2026년", "반기"],
    ),
]


def run():
    case = "MELCON"
    ranking = load(OUT / "ranking/proxy/MELCON.json")
    row = next(x for x in ranking["ai"]["items"] if x["item_id"] == "M01")
    path, _, sha = filing(case)
    with fitz.open(path) as doc:
        text = {p.number + 1: p.get_text(sort=True) for p in doc}
    selected = {}
    for label, terms in QUERIES:

        def score(p, terms=terms):
            s = norm(text[p])
            return (
                sum(t in s for t in terms),
                sum(min(4, s.count(t)) for t in terms),
                -p,
            )

        best = max((p for p in text if p not in selected), key=score)
        selected[best] = {
            "search": label,
            "terms": terms,
            "page": best,
            "excerpt": text[best],
        }
    payload = {"prior_item": row, "reopened_original_pages": list(selected.values())}
    schema = obj(
        {
            "action": {
                "type": "string",
                "enum": ["사람 검토", "자료 요청", "기록 보관"],
            },
            "findings": S,
            "cited_pages": arr({"type": "integer"}),
            "remaining_request": S,
        }
    )

    def verify(a):
        if not a["cited_pages"] or not set(a["cited_pages"]) <= selected.keys():
            raise ValueError("Cite only provided physical pages.")

    res = ask_proxy(
        case,
        "POSTHOC_PERIOD_LOOKUP",
        "최초 신고서의 기존 자료 요청을 검토한다. 새로 찾은 원문에서 해소되는 내용과 여전히 필요한 숫자를 구분한다. 실제로 근거를 확인한 범위에서 해당 한 항목의 조치를 선택한다. 다른 항목 순위는 결정하지 않는다.",
        payload,
        schema,
        verify=verify,
    )
    dump(
        OUT / "lookup_check.json",
        {
            "case": case,
            "item": "M01",
            "scope": "post-hoc development sensitivity",
            "frozen_ranking_changed": False,
            "prior_action": row["action"],
            "sha256": sha,
            "retrieved": [
                {"physical_page": p, "search": v["search"]} for p, v in selected.items()
            ],
            "result": res,
        },
    )


if __name__ == "__main__":
    run()
