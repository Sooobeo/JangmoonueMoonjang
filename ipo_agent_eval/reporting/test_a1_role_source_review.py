import json

import fitz

from reporting import a1_role_source_review as review


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")


def test_source_worksheet_uses_only_role_and_disclosure_inputs(tmp_path):
    case = "20240101000001"
    document = tmp_path / "real.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text(
            (20, 50), "2023 consolidated total: 6 million. Cited original row."
        )
        pdf.save(document)
    with fitz.open(document) as pdf:
        original = pdf[0].get_text(sort=True)
    roster = tmp_path / "roster.json"
    put(
        roster,
        {
            "rows": [
                {
                    "receipt": case,
                    "pdf_file": document.name,
                    "pdf_sha256": review.sha(document.read_bytes()),
                }
            ]
        },
    )
    issuer = tmp_path / "issuers" / case
    terra = tmp_path / "terra" / case
    items = [
        {
            "id": k,
            "question": "period",
            "target": "issuer",
            "family": "J1",
            "pages": [1],
            "evidence": [{"page": 1, "quote": "2023"}],
        }
        for k in ("period", "attribution")
    ]
    put(issuer / "items.json", items)
    put(issuer / "a0.json", {"original_physical_pages": {"1": original}})
    put(
        terra / "A0.json",
        {
            "answer": {
                "items": [
                    {
                        "item_id": r["id"],
                        "physical_page": 1,
                        "state": "accepted",
                        "quote": "2023 consolidated total",
                        "reason": "reference",
                    }
                    for r in items
                ]
            }
        },
    )
    put(
        issuer / "c.json",
        {
            "issuer_evidence": [{"evidence_id": "E1", "text": "2023 result"}],
            "candidates": [],
        },
    )
    put(
        issuer / "c_private.json",
        {
            "links": {},
            "sources": {
                "E1": {"quote": "2023 result", "masked_excerpt": "2023 result"}
            },
        },
    )
    put(
        terra / "C.json",
        {
            "answer": {
                "methods": {
                    "period": {
                        "choice": "LAST_FY",
                        "reason": "source",
                        "evidence_ids": ["E1"],
                    },
                    "attribution": {
                        "choice": "UNKNOWN",
                        "reason": "missing",
                        "evidence_ids": [],
                    },
                },
                "candidates": [],
            }
        },
    )
    view = review.inspect(case, side=35, base=tmp_path, roster=roster)
    row = view["items"]["period"]
    assert (
        row["A0"]["exact"]
        and row["A0"]["input_matches_filing"]
        and row["A0"]["belongs_to_item"]
    )
    assert "6 million" in row["A0"]["surrounding"]
    assert row["C"]["source_context"]["E1"]["quote"] == "2023 result"
    assert row["C"]["own_evidence"] and row["C"]["private_mapping_matches"]
    assert not view["items"]["attribution"]["C"]["own_evidence"]
