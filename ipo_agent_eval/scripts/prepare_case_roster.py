"""Reproduce W09 recruitment and issuer-level allocation before evaluation responses.

The selected scale is a development-stage 6/12 proposal, not a W12 freeze.
Six already deeply analysed issuers are forced development. Remaining eligible
issuers are shuffled with the protocol seed and assigned evaluation candidates.
"""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import random
import re

import fitz

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/a0_implementation"
ARCHIVE = REPORTS / "case_roster_sources/evaluation_screening"
SEED = 20261026
# Only identity, cutoff, method and business metadata are reviewed for held-out candidates.
# No candidate response or scoring criteria are created here.
REVIEWED = {
    "GIGAVIS": ("2023-05-15", 57, 300, "ANNUAL", "2022 실제이익, 주식보상비용 조정", "반도체 기판 광학검사 장비", "광학", "KOSDAQ"),
    "MANYO": ("2023-05-25", 54, 244, "ANNUAL", "2022 실제이익", "화장품 브랜드", "화장품", "KOSDAQ"),
    "SLSBIO": ("2023-10-10", 52, 281, "LTM", "2023H1 LTM, 비교기업 파생상품 손익 조정", "의약품 품질검사 및 신약개발 지원", "의약품", "KOSDAQ"),
    "ECOEYE": ("2023-11-10", 67, 307, "LTM", "2023H1 LTM", "온실가스 감축 및 탄소배출권 사업", "온실가스", "KOSDAQ"),
    "HANSSAK": ("2023-09-19", 81, 344, "LTM", "2023H1 LTM", "망연계 보안 솔루션", "망연계", "KOSDAQ"),
    "INSWAVE": ("2023-09-14", 60, 303, "LTM", "2023H1 LTM, 파생상품평가손실 조정", "기업 UI 소프트웨어", "소프트웨어", "KOSDAQ"),
    "SYSTEEL": ("2023-11-01", 50, 249, "LTM", "2023H1 LTM", "건축용 데크플레이트 제조", "데크", "KOSDAQ"),
    "APR": ("2024-02-14", 67, 345, "INTERIM_ANNUALIZED", "2023Q3 누적 실제이익 연환산", "화장품 및 뷰티 디바이스", "화장품", "KOSPI"),
    "SANIL": ("2024-07-18", 55, 311, "LTM", "2024Q1 LTM, 우리사주 주식보상비용 조정", "산업용 변압기 제조", "변압기", "KOSPI"),
    "JEONJIN": ("2024-08-08", 52, 243, "LTM", "2024Q1 LTM", "콘크리트 펌프카 제조", "콘크리트", "KOSPI"),
    "TRUEN": ("2023-05-08", 63, 252, "ANNUAL", "2022 실제이익", "영상감시 카메라 및 영상 솔루션", "카메라", "KOSDAQ"),
    "PHILENERGY": ("2023-07-05", 71, 263, "LTM", "2023Q1 LTM, 파생상품손익 조정", "이차전지 제조장비", "이차전지", "KOSDAQ"),
}
EXCLUDED = {
    "COXEM": (297, "FORECAST_PER", "2025년 추정 당기순이익 현재가치를 적용하므로 과거실적 PER 범위에서 제외."),
    "NOBLAND": (386, "PBR", "최종 공모가 산정표 및 평가모형이 PBR. 앞부분에 잔존한 과거 PER 위험문구로 판정하지 않음."),
    "PURIT": (304, "MIXED_PER_EV_EBITDA", "EV/EBITDA 평가가액과 PER 평가가액을 같은 비중으로 평균. PER 주평가 핵심 표본에는 넣지 않고 혼합방법 확장 후보로 보존."),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    rows = []
    old = [("HDMS-DEV-01", "data/public"), ("MELCON-DEV-01", "data/cases/MELCON-DEV-01/public"), ("DTS-DEV-01", "data/cases/DTS-DEV-01/public")]
    new = [(c, f"data/cases/{c}/public") for c in ["SHINSUNGST-DEV-01", "ALT-DEV-01", "MILLIE-DEV-01"]]
    for case, directory in old + new:
        base = ROOT / directory
        manifest = json.loads((base / "case_manifest.jsonl").read_text(encoding="utf8").splitlines()[0])
        docs = [json.loads(x) for x in (base / "documents.jsonl").read_text(encoding="utf8").splitlines()]
        row = {"case_id": case, "issuer_name": manifest["issuer_name"], "market": manifest["market"],
               "cohort": "DEVELOPMENT", "eligibility": "HISTORICAL_PER_PUBLIC_SOURCE_VERIFIED",
               "assignment_reason": "Already deeply analysed; permanently excluded from final evaluation pool.",
               "public_directory": directory, "cutoff_at": manifest["cutoff_at"],
               "source_documents": [{k:d.get(k) for k in ["doc_id", "receipt_no", "sha256", "source_url"]} for d in docs],
               "public_corpus_prepared": True, "private_gold_prepared": True,
               "human_gold_review_complete": False, "live_development_ready": True,
               "evaluation_live_allowed": False,
               "input_hashes": {f:sha(base/f) for f in ["case_manifest.jsonl", "documents.jsonl", "chunks.jsonl", "manual.md"]}}
        if (ROOT / f"data/cases/{case}/private/gold.json").exists():
            gold = ROOT / f"data/cases/{case}/private/gold.json"
            row["gold_path"] = str(gold.relative_to(ROOT)).replace("\\", "/")
            row["gold_sha256"] = sha(gold)
        else:
            row["gold_preservation_reference"] = "D0 original and phase1 supplemental preservation manifests"
        rows.append(row)
    for slug, fields in REVIEWED.items():
        subscription, cover_page, valuation_page, period, basis, business, keyword, market = fields
        meta = json.loads((ARCHIVE / f"{slug}.json").read_bytes())
        pdf = ARCHIVE / f"{slug}.pdf"
        assert sha(pdf) == meta["pdf_sha256"]
        html = (ARCHIVE / f"{slug}_receipt.html").read_text(encoding="utf8")
        versions = sorted(set(re.findall(r'<option[^>]*value="rcpNo=([0-9]{14})"[^>]*title="투자설명서"', html)))
        cutoff_day = date.fromisoformat(subscription) - timedelta(days=1)
        applicable = [r for r in versions if r[:8] <= cutoff_day.strftime("%Y%m%d")]
        assert applicable and max(applicable) == meta["receipt_no"]
        with fitz.open(pdf) as document:
            cover = document[cover_page - 1].get_text(sort=True)
            assert "청약기간" in cover
            valuation = document[valuation_page - 1].get_text(sort=True)
            assert "PER" in valuation and "당기순이익" in valuation
            business_page = next((i+1 for i in range(cover_page, len(document)) if keyword in document[i].get_text()), None)
            assert business_page
        rows.append({"case_id": f"{slug}-EVAL-01", "issuer_name": meta["issuer_name"], "market": market,
                     "cohort": "EVALUATION_CANDIDATE", "eligibility": "HISTORICAL_PER_PUBLIC_SOURCE_VERIFIED",
                     "source_url": meta["source_url"], "dart_url": meta["dart_url"], "receipt_no": meta["receipt_no"],
                     "source_pdf": str(pdf.relative_to(ROOT)).replace("\\", "/"), "source_sha256": meta["pdf_sha256"],
                     "source_pages": meta["page_count"], "source_version_date": date.fromisoformat(meta["receipt_no"][:8]).isoformat(),
                     "cutoff_at": cutoff_day.isoformat()+"T23:59:59+09:00", "general_subscription_start": subscription,
                     "cover_pdf_page": cover_page, "valuation_pdf_page": valuation_page,
                     "prospectus_version_receipts": versions, "latest_before_cutoff_verified": True,
                     "earnings_period_type": period, "earnings_basis": basis, "nonfinancial_business": business,
                     "business_keyword_evidence_pdf_page": business_page,
                     "eligibility_checks": {"domestic_nonfinancial": True, "primary_method_historical_per": True,
                                            "complete_primary_pdf_available": True, "cutoff_precedes_subscription": True},
                     "public_pdf_archived": True, "public_corpus_prepared": False, "private_gold_prepared": False,
                     "human_gold_review_complete": False, "model_answer_requested": False,
                     "live_development_ready": False, "evaluation_live_allowed": False,
                     "remaining_before_W12": ["Build complete public corpus and verify extraction", "Prepare and review private gold before any response", "Freeze final sample, model, settings, scoring and costs"],
                     "eligibility_limit": "Date-precision availability; final financial inputs checked only for eligibility, not independently audited. Foreign-peer and shared-peer/source metadata still need full census before W12."})
    for slug, (page, method, reason) in EXCLUDED.items():
        meta = json.loads((ARCHIVE / f"{slug}.json").read_bytes())
        rows.append({"case_id": slug+"-EXCLUDED", "issuer_name": meta["issuer_name"], "cohort": "EXCLUDED_CORE",
                     "eligibility": method, "exclusion_reason": reason, "valuation_pdf_page": page,
                     "receipt_no": meta["receipt_no"], "source_url": meta["source_url"], "source_sha256": meta["pdf_sha256"],
                     "public_pdf_archived": True, "public_corpus_prepared": False, "private_gold_prepared": False,
                     "live_development_ready": False, "evaluation_live_allowed": False})
    forced = sorted(row["case_id"] for row in rows if row["cohort"] == "DEVELOPMENT")
    eligible = sorted(row["case_id"] for row in rows if row["cohort"] == "EVALUATION_CANDIDATE")
    pool_hash = hashlib.sha256(json.dumps({"forced_development": forced, "eligible_unseen": eligible}, sort_keys=True).encode()).hexdigest()
    random.Random(SEED).shuffle(eligible)
    assignment = {"seed": SEED, "algorithm": "Python random.Random(seed).shuffle(sorted eligible case IDs)",
                  "input_pool_sha256": pool_hash, "forced_development": forced, "evaluation_candidate_order": eligible,
                  "random_new_development_count": 0,
                  "note": "Deeply analysed firms now total6. Under proposed6/12 scale all12 remaining eligible firms become evaluation candidates; seed controls order, not a claim of random sampling from all Korean IPOs.",
                  "final_scale_frozen": False, "W12_final_decision_required": True}
    report = {"version": "W09-development-proposal-1", "prepared_on": "2026-11-13",
              "recruitment_window": {"from": "2023-01-01", "through": "2026-10-26", "status": "prior proposal retained for development; final recruitment scope before W12"},
              "recruitment_method": "Purposeful feasible public-source recruitment; not an exhaustive IPO census or random population sample. No model results used in inclusion decisions.",
              "counts": {"development": 6, "evaluation_candidates": 12, "excluded_core": 3, "total_reviewed": 21},
              "readiness": "Six development cases have public corpora and private rubrics. Twelve evaluation PDFs/eligibility checks are prepared; evaluation corpora and gold remain unprepared and no evaluation answer may be requested before W12.",
              "assignment": assignment, "cases": rows,
              "shared_peer_observations": [{"cases": ["HANSSAK-EVAL-01", "INSWAVE-EVAL-01"], "peers": ["케이사인", "파수", "지니언스"], "status": "Observed in primary comparison tables; separate original peer filings not yet collected."}],
              "remaining_scope": ["Full peer overlap/foreign peer census", "Evaluation input/gold preparation", "W12 final freeze", "Human scoring review tracked separately; no fabricated completed review"]}
    assert len(set(r["case_id"] for r in rows)) == 21
    assert not set(forced).intersection(eligible)
    raw = (json.dumps(report, ensure_ascii=False, indent=2)+"\n").encode("utf8")
    output = REPORTS / "case_roster.json"
    if output.exists() and output.read_bytes() != raw:
        raise FileExistsError("Roster already frozen as a proposal; write a separately versioned update")
    if not output.exists():
        output.write_bytes(raw)
    md = ["# W09 사례 모집·배정 기록", "", "2026-11-13 개발 단계 배정안. 기존 3개와 새로 자세히 검토한 3개를 개발용으로 고정하고, 공개 원문에서 적격성을 확인한 12개를 평가 후보로 분리했다. 전체 IPO 모집단을 무작위 추출한 표본은 아니다. 최종 규모와 모집 기간은 W12 전에 확정한다.", "", "개발 6개는 공개 전체 입력과 비공개 기준표가 있다. 평가 12개는 원문 PDF·공개일·청약일·최종 과거실적 PER 방식까지 확인했다. 평가 코퍼스·기준표는 아직 만들지 않았으며 W12 동결 전 모델 답변을 요청하지 않는다.", "", "| 기업 | 배정 | 원문/기준표 | 근거 또는 남은 작업 |", "|---|---|---|---|"]
    for row in rows:
        label = {"DEVELOPMENT": "개발 고정", "EVALUATION_CANDIDATE": "평가 후보", "EXCLUDED_CORE": "핵심 제외"}[row["cohort"]]
        readiness = "전체 입력·기준표 준비" if row["cohort"]=="DEVELOPMENT" else "PDF 확보·기준표 미작성"
        note = row.get("exclusion_reason", row.get("earnings_basis", "이미 자세히 분석한 기업; 사람 기준표 검토는 미완료"))
        link = row.get("dart_url", row.get("source_url", ""))
        name = f"[{row['issuer_name']}]({link})" if link else row["issuer_name"]
        md.append(f"| {name} | {label} | {readiness} | {note} |")
    md += ["", "배정 시드 `20261026`. 기업 ID 정렬 후 동일 시드로 섞은 순서를 JSON에 저장했다. 상세분석 기업이 이미 6개라 추가 무작위 개발 배정은 0개이고, 남은 적격 12개 모두 평가 후보가 된다. 원문 PDF SHA256·물리 쪽수·버전 목록·자료 마감·남은 준비 상태는 [case_roster.json](case_roster.json)에 있다.", "", "코셈은 미래 추정이익, 노브랜드는 최종 PBR, 퓨릿은 PER/EV·EBITDA 동등 혼합평가여서 핵심 표본에서 제외했다. 노브랜드의 앞부분 잔존 PER 문구와 퓨릿의 PER 보조표만으로 포함하지 않았다. 공개시각은 날짜 단위로 확인했으며, 외국 비교기업 및 공유 원천 전체 목록은 W12 전 보완해야 한다.", "", "신규 3개 기준표는 모델 답변을 보기 전에 작성했다. AI 검토 및 계산 검증과 규리의 실제 검토 완료는 구분한다.", ""]
    (REPORTS / "case_roster.md").write_text("\n".join(md), encoding="utf8")
    print(json.dumps({"counts": report["counts"], "roster_sha256": sha(output), "assignment": assignment}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
