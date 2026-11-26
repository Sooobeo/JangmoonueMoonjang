"""Check the source row and the evidence still visible to each blinded reviewer."""

import hashlib
import json
import re
import unicodedata
from functools import cache

from lxml import html

from scripts.a1_main_items import BASE, MAIN

HEADER_ONLY = re.compile(
    r"^(?:(?:매출액|매출|금액|비율|비중|당기|전기|전전기|실적|단위|구분|[(%)\s/])+$)"
)
EMPTY_BUSINESS = (
    "사업부문의 구분 - 해당사항 없습니다",
    "나. 회사의 현황 (1) 영업개황 및 사업부문의 구분",
    "연결회사의 사업부문은 서로 다른 제품과 용역을 제공하는 사업 단위입니다",
    "매출 분류 유형 구분 품목 제",
    "사업부문 매출액 비중(%) 비고",
)
IDENTITIES = {
    "휠라홀딩스": r"(?<![A-Z])FILA(?![A-Z])",
    "대아티아이": r"DAEA\s*TI|대아글로벌",
    "에이치와이티씨": r"한영정공",
    "파수": r"스패로우|\b(?:Fasoo|Sparrow)\b",
    "아이퀘스트": r"디포커스",
    "제일일렉트릭": r"제일전기공업",
    "HLB이노베이션": r"Verismo\s+Therapeutics",
    "클리오": r"(?<![A-Z])CLIO(?![A-Z])",
    "코데즈컴바인": r"codes[ -]*combine",
    "케이사인": r"KSign",
}
METADATA = re.compile(
    r"접수번호|희망\s*공모가|주당\s*평가가액|비교기업|비교회사|유사회사|상장주선인|https?://|\b[A-Z]{2}[A-Z0-9]{9}\d\b"
)
NONPRODUCT = re.compile(r"^(?:내수|수출|국내|해외)\s+[\d,.%\s()\-]+$")


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flat(s):
    return "".join(unicodedata.normalize("NFKC", s).split()).casefold()


@cache
def source_rows(path):
    raw = path.read_bytes()
    doc = html.fromstring(raw.decode("utf-8", errors="replace"))
    return [(n.tag, " ".join(n.itertext()).strip()) for n in doc.xpath("//p|//tr")]


def content_issues(name, kind, fact, raw):
    quote = fact["text"]
    issues = []
    if len(quote) > 350:
        issues.append("350자 초과")
    if METADATA.search(quote):
        issues.append("기업 식별·선정·평가 정보 직접 노출")
    if name in IDENTITIES and re.search(IDENTITIES[name], quote, re.IGNORECASE):
        issues.append("후보의 영문명 또는 법인명 이력 직접 노출")
    if any(t in quote for t in ("[기업]리케이션", "펩[기업]")):
        issues.append("일반명사를 회사로 잘못 치환")
    if kind == "business" and (
        HEADER_ONLY.fullmatch(quote.strip())
        or NONPRODUCT.fullmatch(quote.strip())
        or any(t in quote for t in EMPTY_BUSINESS)
    ):
        issues.append("표머리·일반 안내·지역 수치만 있어 후보의 사업 확인 불가")
    if kind == "financials":
        data = quote.split(" · ")[-1]
        if not re.search(r"\d", data):
            issues.append("송신 제한 안에 매출 수치가 남지 않음")
        if not raw.get("period"):
            issues.append("원문 보고기간 미기록")
        if re.match(r"^(?:영업이익|당기순이익|당기순손익)\s", data):
            issues.append("매출구성이 아닌 이익 행")
    return issues


def audit(row):
    receipt = row["receipt"]
    root = MAIN / "issuers" / receipt
    private = read(root / "c_private.json")
    status = read(root / "c_status.json")
    wire = root / "c.json"
    packet = read(wire) if wire.is_file() else private["draft"]
    findings = []
    checked_rows = 0
    financial_rows = 0
    missing_periods = 0

    def issue(eid, kind, msg):
        findings.append({"id": eid, "kind": kind, "detail": msg})

    if status["ready"] != wire.is_file() or packet != private["draft"]:
        issue(None, "전송물", "준비 상태와 송신 후보 파일 불일치")
    if set(packet) != {"issuer_evidence", "candidates"}:
        issue(None, "전송물", "예정되지 않은 최상위 키")
    catalog = private["sources"]
    all_ids = []
    for r in packet["issuer_evidence"]:
        all_ids.append(r["evidence_id"])
        if len(r["text"]) > 350 or METADATA.search(r["text"]):
            issue(r["evidence_id"], "발행사", "길이 제한 또는 메타데이터 노출")
    for candidate in packet["candidates"]:
        cid = candidate["candidate_id"]
        link = private["links"][cid]
        name = link["name"]
        document = private["candidate_documents"][link["ticker"]]
        if document["published"].replace("-", "") >= receipt[:8]:
            issue(cid, "출처", "접수 뒤 공개된 후보 자료")
        if (
            set(candidate) != {"candidate_id", "business", "financials", "multiples"}
            or candidate["multiples"]
        ):
            issue(cid, "전송물", "후보 입력 열 또는 배수 비공개 위반")
        for kind in ("business", "financials"):
            if len(candidate[kind]) > 2 or (kind == "business" and not candidate[kind]):
                issue(cid, kind, "발췌 개수 오류")
            for fact in candidate[kind]:
                eid = fact["evidence_id"]
                all_ids.append(eid)
                raw = catalog[eid]
                for reason in content_issues(name, kind, fact, raw):
                    issue(eid, kind, reason)
                if raw.get("receipt") != document.get("receipt") or not raw.get(
                    "location"
                ):
                    issue(eid, kind, "허용된 후보·보고서·위치 불일치")
                path = MAIN / raw["snapshot"]
                if sha(path) != raw["sha256"]:
                    issue(eid, "출처", "해시 불일치")
                match = re.search(r"/ (p|tr) (\d+)$", raw["location"])
                if match:
                    rs = source_rows(path)
                    ix = int(match[2]) - 1
                    original_paragraph = raw.get("full_paragraph", raw["quote"])
                    offset = raw.get("excerpt_offset", 0)
                    if (
                        ix >= len(rs)
                        or rs[ix][0] != match[1]
                        or flat(rs[ix][1]) != flat(original_paragraph)
                        or original_paragraph[offset:] != raw["quote"]
                    ):
                        issue(
                            eid, "원문 행", "독립 HTML 파서의 원문 위치/내용 대조 필요"
                        )
                    else:
                        checked_rows += 1
                    if raw.get("header_rows") and [
                        flat(rs[i - 1][1]) for i in raw["header_rows"]
                    ] != [flat(t) for t in raw["table_headers"]]:
                        issue(eid, "표 머리글", "행 위치와 원문 불일치")
                if kind == "financials":
                    financial_rows += 1
                    if (
                        raw.get("period")
                        and raw["period"] not in fact["text"]
                        and not re.search(
                            r"20\d\d|第\s*\d+期|제\s*\d+\s*기|fiscal year|quarter ended|months ended",
                            fact["text"],
                            re.IGNORECASE,
                        )
                    ):
                        missing_periods += 1
    if set(all_ids) != set(catalog) or len(all_ids) != len(catalog):
        issue(None, "전송물", "원본·전송물 ID 중복 또는 누락")
    return {
        "receipt": receipt,
        "issuer": row["issuer"],
        "wire_prepared": status["ready"],
        "wire_sha256": sha(wire) if wire.is_file() else None,
        "private_sha256": sha(root / "c_private.json"),
        "evidence_ids_checked": len(all_ids),
        "candidate_html_rows_at_exact_location": checked_rows,
        "financial_excerpts": financial_rows,
        "financial_excerpts_without_period_in_visible_text": missing_periods,
        "findings": findings,
    }


def main():
    rows = [audit(row) for row in read(BASE / "roster.json")["rows"]]
    result = {
        "reviews": [
            "후보 보고서·기준일·원문 실제 행의 독립 HTML 파서 대조",
            "최종 350자 안의 제품·매출 근거 내용 및 법인 식별자 확인",
            "준비 표시·실제 송신 후보 바이트·비공개 자료 ID와 열 대조",
        ],
        "scope": "기계 대조와 명시적으로 식별된 내용 오류를 기록. 각 원문의 최초 적격 문장과 외국어 자료 의미는 별도 원문 판독 필요.",
        "issuers": rows,
    }
    target = MAIN / "c_content_review.json"
    output = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf8")
    if not target.exists() or target.read_bytes() != output:
        target.write_bytes(output)
    print(
        len(rows),
        sum(r["wire_prepared"] for r in rows),
        sum(len(r["findings"]) for r in rows),
    )


if __name__ == "__main__":
    main()
