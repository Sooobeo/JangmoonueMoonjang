"""Verify adjudicated issuer-profit formulas in the 2025 H2 registered DART filings."""

from concurrent.futures import ThreadPoolExecutor

import fitz

from scripts.assemble_evaluation_filings import BASE, compact, offer_anchor, sha
from scripts.current_b import dump
from scripts.current_live import load
from scripts.enrollment_2024h1 import history
from scripts.screen_a1_first_filings import CACHE

DEST = BASE / "2025H2"
PINNED = {
    "20250908000140": (217, "2025년도 상반기 기준 과거 12개월(LTM) 당기순이익(①) × 비교회사 PER",
                       "2025년 반기 기준 LTM 당기순이익", 239),
    "20250908000329": (201, "2025년 반기 LTM 기준 매출 컷오프 효과를 반영한 당기순이익(①) X 유사기업 PER",
                       "2025년 반기 LTM, 매출 컷오프 조정 당기순이익", 225),
    "20250930000546": (239, "2025년 반기 LTM 기준 당기순이익 (①) x 유사기업의 PER",
                       "2025년 반기 LTM 당기순이익", 258),
    "20251001000684": (209, "2025년 반기 연환산 조정 당기순이익(①) x 유사기업 PER",
                       "2025년 반기 연환산 조정 당기순이익", 230),
    "20251103000252": (213, "동사의 주당 평가가액은 동사의 2025년 반기 기준 지배기업 당기순이익을 연환산한 이익을",
                       "2025년 반기 지배기업 당기순이익 연환산", 227),
    "20251223000517": (256, "동사의 주당 평가가액은 동사의 2025년 3분기 순이익 연환산을 기준으로 PER를 적용하여",
                       "2025년 3분기 누적 순이익 연환산", 279),
}


def verify(receipt):
    row = load(DEST / "locator" / (receipt + ".json"))
    trace = history(row, destination=DEST)
    if trace["prior_relevant_title_records"]:
        return {"receipt": receipt, "issuer": row["issuer"], "prior_filings": trace["prior_relevant_title_records"]}
    page, quote, basis, price = PINNED[receipt]
    pdf = CACHE / (receipt + ".pdf")
    if sha(pdf) != row["pdf_sha256"] or not row["exact_title_and_earliest_family"]:
        raise ValueError(f"{receipt}: initial filing or hash mismatch")
    with fitz.open(pdf) as doc:
        offer = offer_anchor(doc)
        if compact(quote) not in compact(doc[page - 1].get_text(sort=True)):
            raise ValueError(f"{receipt}: issuer source quote not found")
        table = compact(doc[price - 1].get_text(sort=True))
        if "per" not in table or ("평가가액" not in table and "주당" not in table):
            raise ValueError(f"{receipt}: invalid applied PER price table")
    fields = ("receipt", "corp_code", "issuer", "pdf_url", "pdf_sha256")
    return {**{k: row[k] for k in fields}, "period_or_method": basis,
            "ipo_status_anchor": offer, "issuer_valuation_anchor": {"page": page, "quote": quote},
            "price_table_page": price, "prior_relevant_title_records": [],
            "history": "corporate_history/" + receipt + ".json"}


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        verified = list(pool.map(verify, PINNED))
    dump(DEST / "eligible.json", {"rows": [r for r in verified if "pdf_url" in r],
                                "held_prior_history": [r for r in verified if "prior_filings" in r]})
