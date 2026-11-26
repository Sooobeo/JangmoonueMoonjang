"""Audit the 37-issuer preparation without opening outcomes or using a model."""

import hashlib
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from pypdf import PdfReader

from scripts.a1_main_items import (
    BASE,
    COMMON,
    DATA,
    MAIN,
    SCALE,
    build,
    compact,
    dump,
    load,
)


def normalized(text):
    return re.sub(r"[\s,]", "", text).casefold()


def run():
    rows = load(BASE / "roster.json")["rows"]
    source_index = load(DATA / "valuation_sources.json")
    numeric_index = load(DATA / "valuation_rows.json")
    location_index = load(DATA / "evidence_locations.json")
    snapshots = {}
    total = Counter()
    for row in rows:
        key = row["receipt"]
        root = MAIN / "issuers" / key
        items, b, catalog, a0, grading = [
            load(root / filename)
            for filename in (
                "items.json",
                "b.json",
                "catalog.json",
                "a0.json",
                "grading.json",
            )
        ]
        path = BASE / row["pdf_file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["pdf_sha256"]
        with fitz.open(path) as doc:
            source_pages = {
                n: doc[n - 1].get_text(sort=True)
                for n in location_index[key]["read_pages"]
            }
        pages = {n: source_pages[int(n)] for n in catalog["pages"]}
        assert (
            pages
            == catalog["pages"]
            == a0["original_physical_pages"]
            == grading["pages"]
        )
        assert all(
            compact(ref["quote"]) in compact(pages[str(ref["page"])])
            for item in items
            for ref in item["evidence"]
        )
        assert [item["id"] for item in items] == [
            f"{key}-{j:02}" for j in range(1, len(items) + 1)
        ]
        j2 = [item for item in items if item["family"] == "J2"]
        assert [item["target"] for item in j2] == source_index[key]["peers"]
        assert len({r["target"] for r in j2}) == len(j2)
        assert [(r["family"], r["question"]) for r in items[:7]] == COMMON
        assert [r["item_id"] for r in grading["items"]] == [r["id"] for r in items]
        assert all(
            set(r) == {"item_id", "question", "question_type", "pages"}
            for r in grading["items"]
        )
        assert all(
            set(r)
            == {"item_id", "question", "question_type", "pages", "original_choice"}
            for r in a0["items"]
        )
        for r, neutral, role in zip(items, grading["items"], a0["items"]):
            assert r["pages"] == neutral["pages"] == role["pages"]
            assert r["question"] == role["question"] == neutral["question"]
            assert r["original_choice"] == role["original_choice"]
            assert all(e["page"] in r["pages"] for e in r["evidence"])
        assert set(b["price_impact_fraction"]) == {r["id"] for r in items}
        assert {r["id"] for r in items} >= set(b["mandatory"])
        pdf = PdfReader(path)
        independent = {
            n: normalized(pdf.pages[n - 1].extract_text())
            for n in {fact["page"] for fact in b["facts"].values()}
        }

        second_cells = {}
        for name, fact in b["facts"].items():
            assert normalized(fact["value"]) in independent[fact["page"]], (
                key,
                name,
                fact,
            )
            second_cells[name] = True
        assert len(b["peer_multiples"]) == len(j2), (key, b["peer_multiples"])
        peer_mean = mean(float(x) for x in b["peer_multiples"])
        calc_mean = float(
            next(c for c in b["rules"] if c["check"] == "비교 PER 산술평균")["estimate"]
        )
        assert abs(peer_mean - calc_mean) < 1e-9
        assert sum(c["shares"] for c in b["share_components"]) == int(
            next(c for c in b["rules"] if c["check"] == "적용 주식 수 구성")["estimate"]
        )
        earnings = next(
            c for c in b["rules"] if c["check"] == "적용 이익과 동일 기간 원문 손익"
        )
        statement = earnings["reconciliation"]
        scaled_sum = (
            sum(Decimal(v["signed_value"]) for v in statement["components"])
            * SCALE[statement["unit"]]
        )
        computed = (
            scaled_sum
            * Decimal(statement["annualization_numerator"])
            / Decimal(statement["annualization_denominator"])
        )
        assert abs(computed - Decimal(earnings["estimate"])) < Decimal("0.000001")
        for component in statement["components"]:
            assert normalized(component["quote"]) in normalized(
                pages[str(component["page"])]
            )
            assert normalized(str(abs(component["signed_value"]))) in normalized(
                component["quote"]
            ), (key, component)
        for alt in b["alternatives"]:
            assert all(
                compact(e["quote"]) in compact(pages[str(e["page"])])
                for e in alt["evidence"]
            )
        for r in items:
            valid = [
                a
                for a in b["alternatives"]
                if a["original_item"] == r["id"] and a["eligibility"] == "적격"
            ]
            expected = min(
                (
                    (a["priority"] != "오류 입력 수정", a["absolute_fraction"])
                    for a in valid
                ),
                default=(None, None),
            )[1]
            assert expected == b["price_impact_fraction"][r["id"]]
        hashes = {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "items.json",
                "b.json",
                "catalog.json",
                "a0.json",
                "grading.json",
                "preparation_items.json",
            )
        }
        with TemporaryDirectory() as replay:
            replay_root = Path(replay)
            with patch("scripts.a1_main_items.MAIN", replay_root):
                build(
                    row,
                    source_index[key],
                    numeric_index[key],
                    location_index[key],
                    source_pages,
                )
            assert all(
                hashlib.sha256(
                    (replay_root / "issuers" / key / name).read_bytes()
                ).hexdigest()
                == digest
                for name, digest in hashes.items()
            )
        counts = Counter(r["family"] for r in items)
        total.update(counts)
        snapshots[key] = {
            "issuer": row["issuer"],
            "family_counts": dict(counts),
            "review_1_source": {
                "pdf_hash": row["pdf_sha256"],
                "full_page_text_matches": len(pages),
                "direct_quote_checks": sum(len(r["evidence"]) for r in items),
                "pypdf_numeric_cells": second_cells,
            },
            "review_2_logic": {
                "peer_table_page": source_index[key]["peer_table_page"],
                "peer_count": len(j2),
                "mean_independently_recalculated": peer_mean,
                "share_components": len(b["share_components"]),
                "b_checks": b["rules"],
                "earnings_statement_links": len(statement["components"]),
                "priority_and_alternative_coverage_checked": True,
                "mandatory": b["mandatory"],
            },
            "review_3_design": {
                "grader_input_fields": sorted(grading["items"][0]),
                "a0_input_fields": sorted(a0["items"][0]),
                "item_scopes_checked": len(items),
                "preparation_hashes": hashes,
                "byte_identical_rebuild": True,
                "limitations": location_index[key]["gaps"],
            },
        }
    output = {
        "receipt_count": len(rows),
        "items": sum(total.values()),
        "family_counts": dict(total),
        "sources": [
            str(x.relative_to(DATA))
            for x in sorted(DATA.glob("*.json"))
            if x.name
            in {
                "evidence_locations.json",
                "valuation_sources.json",
                "valuation_rows.json",
            }
        ],
        "reviews": snapshots,
    }
    dump(MAIN / "item_preparation_review.json", output)
    print(
        json.dumps(
            {
                k: v
                for k, v in output.items()
                if k in {"receipt_count", "items", "family_counts"}
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    run()
