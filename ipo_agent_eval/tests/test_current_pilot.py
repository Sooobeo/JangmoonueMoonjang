"""Regressions in current-pilot rules: attainable ties, missing source links, and scale."""

from decimal import Decimal

import pytest

from scripts.current_b import audit, mandatory_items, run
from scripts.current_selector import rule_table
from scripts.current_validation import verify


def test_ranking_uses_verified_evidence_before_price_and_preserves_ties():
    def item(key, state, refs, other="수용"):
        return {
            "item_id": key,
            "a0": {"judgment": state, "evidence_refs": refs},
            "c": {"state": other},
        }

    items = [
        item("A", "수용", []),
        item("B", "미확인", []),
        item("C", "문제 제기", ["bad"]),
        item("D", "문제 제기", ["ok"], "미확인"),
        item("E", "수용", []),
        item("F", "수용", []),
    ]
    rows = rule_table(items, {"ok": "원문"}, {"C": 0.8, "A": 0, "E": 0}, ["F"])["items"]
    assert [r["item_id"] for r in rows] == ["D", "B", "C", "A", "E"]
    assert [r["item_id"] for r in rows if r["eligible"]] == ["D"]
    assert rows[-1]["tie_key"] == rows[-2]["tie_key"]


def test_melcon_thousand_shares_and_source_absence():
    facts = run("MELCON")["facts"]
    share_rule, _, price = audit("MELCON", facts)
    assert Decimal(share_rule["calculated"]) == 12735000
    assert abs(Decimal(price["calculated"]) - 14173) < Decimal(".5")
    altered = {**facts, "price": {**facts["price"], "display":"18,000"}}
    assert mandatory_items("MELCON", audit("MELCON", altered)) == ["M10"]
    facts["shares"]["source_status"] = "미확인"
    assert [v["status"] for v in audit("MELCON", facts)] == ["미확인", "통과", "미확인"]


@pytest.mark.parametrize(
    "row",
    [
        {"item_id": "unknown", "quote": "표시", "physical_page": 3},
        {"item_id": "A", "quote": "존재하지 않음", "physical_page": 3},
        {"item_id": "A", "quote": "표시", "physical_page": 99},
        {"item_id": "A", "quote": " ", "physical_page": 3},
    ],
)
def test_reference_must_match_id_page_and_quote(row):
    with pytest.raises(ValueError):
        verify({"items": [row]}, ["A"], {"3": "원문 표시"})
