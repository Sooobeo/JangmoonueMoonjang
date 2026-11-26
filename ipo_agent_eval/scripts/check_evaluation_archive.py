"""Independently check the completed archive and render the human-readable enrollment list."""

from collections import Counter
from datetime import date

from pypdf import PdfReader

from scripts.assemble_evaluation_filings import BASE, WINDOWS, compact, sha
from scripts.current_b import OUT, ROOT, dump
from scripts.current_live import load


def run():
    path = BASE / "roster.json"
    roster = load(path)
    rows = roster["rows"]
    codes, receipts = ({r[key] for r in rows} for key in ("corp_code", "receipt"))
    files = list((BASE / "filings_source").glob("*.pdf"))
    if len(codes) != len(receipts) or len(receipts) != 37 or {f.stem for f in files} != receipts:
        raise ValueError("Missing, duplicate, or unexpected archive member")
    new_rows = rows[14:]
    per_window = {w: sorted(load(BASE / w / "eligible.json")["rows"], key=lambda r: r["receipt"]) for w in WINDOWS}
    scheduled = sorted(((i, index, r["receipt"]) for index, pool in enumerate(per_window.values())
                        for i, r in enumerate(pool)))
    if [x[2] for x in scheduled[:23]] != [r["receipt"] for r in new_rows]:
        raise ValueError("Manifest diverges from stratified chronological selection")
    proof = []
    for row in rows:
        p = BASE / row["pdf_file"]
        history_file = f"corporate_history/{row['receipt']}.json"
        h = next((candidate for candidate in (BASE / "history_review" / history_file,
                  BASE / row["cohort"] / history_file) if candidate.exists()), None)
        history = load(h) if h else {}
        if (history.get("corp_code") != row["corp_code"] or history.get("window_start") != "19990101"
                or history.get("window_end") != row["receipt"][:8] or not history.get("validated_target_in_final_window")
                or history.get("prior_relevant_title_records") != []):
            raise ValueError(f"Corporate issuance history needs review for {row['issuer']}")
        if sha(p) != row["pdf_sha256"]:
            raise ValueError(f"Byte digest differs: {p.name}")
        a = row["issuer_valuation_anchor"]
        with p.open("rb") as stream:
            reader = PdfReader(stream)
            if len(reader.pages) != row["pdf_pages"]:
                raise ValueError(f"Page count differs: {p.name}")
            alt = compact(reader.pages[a["page"] - 1].extract_text())
            # Different PDF decoders can reorder table cells. Track exact match separately.
            q = compact(a["quote"])
            exact = q in alt
            per_pages = []
            for idx in dict.fromkeys([row.get("price_table_page", a["page"]), a["page"], a["page"] - 1, a["page"] + 1]):
                if 1 <= idx <= len(reader.pages):
                    page_text = compact(reader.pages[idx - 1].extract_text())
                    if "per" in page_text or "p/e" in page_text or "주가수익" in page_text:
                        per_pages.append(idx)
                        break
            if not per_pages:
                raise ValueError(f"{row['issuer']} PER corroboration requires a separate table page")
            proof.append({"receipt": row["receipt"], "sha256_reverified": True, "pages_reverified": True,
                          "history_file": h.relative_to(BASE).as_posix(), "history_sha256": sha(h),
                          "pypdf_issuer_quote_exact": exact, "pypdf_per_page": per_pages[0]})
    counts = Counter(r["cohort"] for r in rows)
    inputs = [ROOT / "reports/a1_development/filing_screening.json", OUT / "official/enrollment/screened_all.json",
              BASE / "모집규칙.md", *(BASE / window / "eligible.json" for window in WINDOWS)]
    dump(BASE / "verification.json", {"roster_sha256": sha(path), "issuers": len(codes), "unique_receipts": len(receipts),
         "pdf_files": len(files), "bytes": sum(f.stat().st_size for f in files), "source_sha256_verified": len(proof),
         "selection_order_reproduced": True, "selection_inputs_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs},
         "cohorts": dict(counts), "second_pdf_decoder": proof,
         "scope": "Enrollment and archiving only. No outcome measurements."})
    lines = ["# 본 평가 최초 신고서 37곳", "", ("2026-11-26 KST. 기존 미사용 8곳과 2024년 4분기에 확인한 6곳에 "
             "신규 23곳을 더했다. 표의 원문 링크는 DART PDF에서 발행사 적용 이익 근거가 있는 쪽을 가리킨다. "
             "접수번호를 누르면 DART 원본과 정정 이력을 확인할 수 있다."), "",
             (f"**37개 법인 · 37개 원본 PDF · {roster['pdf_bytes']/1024**2:,.1f} MiB.** "
             f"추가로 확인한 문서 적격 예비 후보는 {len(roster['reserve'])}곳이다. 유효 기업 목표 15곳의 충족 여부는 후속 채점에서 판단한다."), "",
             "| 구간 | 발행사 | 최초 접수일 | 적용 이익 | 원문 근거 | DART 접수 |", "|---|---|---|---|---:|---|"]
    for row in rows:
        page = row["issuer_valuation_anchor"]["page"]
        pub = date.fromisoformat(row["date_kst"]).isoformat()
        lines.append(f"| {row['cohort']} | {row['issuer']} | {pub} | {row['period_or_method'].replace('|', '／')} "
                     f"| [{page}쪽]({row['pdf_url']}#page={page}) | [{row['receipt']}]({row['dart_url']}) |")
    if roster["reserve"]:
        reserve_links = [f"[{r['issuer']}](https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['receipt']})"
                         for r in roster["reserve"]]
        lines += ["", "## 예비 후보", "", "모집 순서에서 정원 다음에 위치한 문서 적격 기업이다. "
                  + " · ".join(reserve_links)]
    screen = load(BASE / "2025H2/screening.json")["rows"]
    myungin = next(row for row in screen if row["receipt"] == "20250821000397")
    lines += ["", "## 모집과 확인", "",
              ("1. DART 접수 이력과 PDF를 대조해 공모 목적과 발행사의 적용 실적을 확인했다. 참고용 PER 표, 추정 이익을 적용한 공모, "
              "다른 배수로 가격을 정한 공모를 모집에서 제외했다."),
              "2. 기존 사용 발행사와 법인코드·접수번호를 대조했다. 편입한 37곳은 1999년부터 해당 접수일까지 DART 발행공시 이력을 조회해 선행 지분신고서·철회 표시를 점검했다. 네 구간의 확인분에서 접수 순으로 한 곳씩 순환해 23곳을 선택했다.",
              ("3. 보관본 37개의 SHA-256과 페이지 수를 다시 검산했다. 독립 PDF 해독기로 산정 페이지에서 PER 표기를 확인하고, "
              "발행사 원문 인용의 텍스트 일치 여부를 파일별로 기록했다."), "",
              "워트는 개발 과정에서 멜콘의 비교기업으로 원문 자료가 사용된 이력이 있다. 이번 명단의 중복 단위는 발행사이며, 워트 자체의 IPO 평가 결과는 모집에 사용하지 않았다.",
              ("명인제약은 192쪽의 실제 산정식에서 EV/EBITDA를 적용해 제외했다. 210쪽의 PER 계산은 참고용이었다. "
               f"[명인제약 최초 신고서]({myungin['pdf_url']}#page=192)"),
              "", "[모집 규칙](모집규칙.md) · [전체 명단과 해시](roster.json) · [독립 검산](verification.json) · [산정표 쪽수 정정](locator_correction.json)", ""]
    (BASE / "확보한 기업.md").write_text("\n".join(lines), encoding="utf8")


if __name__ == "__main__":
    run()
