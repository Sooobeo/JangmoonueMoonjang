"""Preserve the response and write a separate, attributed proxy grading record."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
RUN = ROOT / "runs/20261111T233807Z_B_2db53c6b"
DEST = ROOT / "grading_exports/HDMS_R001_대행채점결과.docx"
PRIVATE = ROOT / "data/private"
PRIVATE.mkdir(exist_ok=True)
report = json.loads((RUN / "review.json").read_text(encoding="utf-8"))
source_doc = ROOT / "grading_exports/HDMS_R001_답변_채점자료.docx"
source_paths = [source_doc, REPO / "phase1/HDMS_DEV_01_채점기준표.md",
                REPO / "whole plan/IPO_Experiment_Protocol.html",
                *[RUN / name for name in ("review.json", "review.md", "extraction.json", "calculations.json", "source_packet.json")]]
hashes = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
map_data = json.loads((PRIVATE / "grading_export_map_R001.json").read_text(encoding="utf-8"))
assert hashes[str((RUN / "review.json").relative_to(REPO))] == map_data["source_review_sha256"]

facts = [
    {"id": "F1", "value": "2023년 온기 연결 지배주주 순이익 151,116백만원", "answer": "J1 사실 R_J1_ISSUER·R_J1_PEER_PERIOD", "source": "PDF 331쪽 PER·적용 순이익 표, 332쪽 주1, 425쪽 당기순이익 귀속", "reason": "금액·단위·연간 기간·지배주주 귀속 기준이 모두 맞다."},
    {"id": "F2", "value": "HD한국조선해양 36.5배, Alfa Laval 25.6배, Kongsberg 31.8배, Wärtsilä 32.1배. 공시 적용 산술평균 31.5배", "answer": "J2 사실 R_J2_PEERS", "source": "PDF 330쪽 상대가치 산출 방법, 331쪽 PER 표, 332쪽 주2", "reason": "최종 네 비교기업·개별 표시 PER·평균 방식·공시 적용 배수가 모두 맞다."},
    {"id": "F3", "value": "평가시가총액 4,761,293백만원, 적용 잠재주식수 44,870,190주", "answer": "J3 사실 R_J3_EQUITY와 다음 행동, 4절 추출값", "source": "PDF 332쪽 주당 평가가액 산출 내역", "reason": "금액과 적용 주식수 모두 공시와 일치한다."},
    {"id": "F4", "value": "기존 40,000,000주 + 신주 4,450,000주 + 희석가능 420,190주. 구주 4,450,000주는 추가하지 않음", "answer": "J3 사실 R_J3_SHARES와 다음 행동", "source": "PDF 332쪽 주식수 표와 옵션 주석", "reason": "신주와 구주를 구분했고, 희석가능분 13,510+406,680=420,190주도 맞다."},
    {"id": "F5", "value": "할인 전 주당 평가가액 106,113원", "answer": "J3 사실 R_J3_EQUITY, J4 사실 R_J4_PRICE", "source": "PDF 332쪽 주당 평가가액·희망공모가액 산출 내역", "reason": "확정 공모가 83,400원과 구분해 기록했다."},
]
calculations = [
    {"id": "K1", "answer": "J3 다음 행동의 주식수 산식", "source": "PDF 332쪽 주식수 표·주석", "formula": "40,000,000 + 4,450,000 + 420,190 = 44,870,190주", "reason": "기존 주식·신주·희석가능분만 합산했다. 구주매출을 다시 더하지 않았다."},
    {"id": "K2", "answer": "J3 다음 행동의 106,112.61원", "source": "PDF 332쪽 평가시가총액·주당 평가가액", "formula": "4,761,293 × 1,000,000 ÷ 44,870,190 = 106,112.6106219원", "reason": "백만원을 원으로 환산했고, 원 단위 반올림 시 공시 106,113원과 일치한다."},
    {"id": "K3", "answer": "J3 결론·다음 행동·미확인 사항", "source": "PDF 331쪽 PER 표, 332쪽 평가액 표", "formula": "151,116 × 31.5 = 4,760,154백만원 → 106,087.2262854원", "reason": "표시 PER을 그대로 쓴 가격은 공시 106,113원보다 25.7737146원 낮다. 표의 시가총액÷이익으로 다시 얻은 평균은 31.5075506674배, 주당 106,112.6557888원이다. 평가시가총액은 약 4,761,295.0267백만원으로 공시보다 약 2.0267백만원 높아 차이가 남는다. 답변은 근접 재현과 실제 처리 규칙의 증명을 구분했고, 정확한 미반올림·반올림·절사 방식은 미확인으로 남겼다."},
]
judgments = [
    {"id": "J1", "title": "적용 이익의 비교 가능성", "score": 2,
     "quote": "2023년 온기 연결 지배주주순이익을 적용한 선택은 비교기업 PER의 공시상 기간·귀속 기준과 일치하므로 비교 출발점으로 조건부 수용할 수 있다.",
     "answer": "J1 결론, R_J1_ISSUER·R_J1_PEER_PERIOD·R_J1_PEER_DIFFERENCE",
     "source": "PDF 331~332쪽 PER·적용 순이익 및 주석, 425쪽 이익 귀속, 313쪽 HD한국조선해양 요약 연결 재무정보",
     "reason": "양쪽의 기간과 이익 귀속 범위를 확인하고, 그 일치가 배수 비교의 출발점을 뒷받침한다는 판단으로 연결했다. 발행사 별도 이익 143,474,006,953원과 연결 이익을 구별했다. HD한국조선해양의 221,682백만원과 221,711백만원 차이를 실제 제약으로 적고 원인을 지어내지 않았다. 기준표 J1의 2점 요건을 충족한다.",
     "boundary": "회계·연결 범위의 세부 일치나 독립 원자료까지 검증한 점수를 부여한 것은 아니다. 29백만원 차이의 원인은 여전히 미해결이다."},
    {"id": "J2", "title": "비교기업을 사용하는 판단", "score": 2,
     "quote": "네 비교기업의 평균 PER은 공시가 설명한 산업·기능적 유사성을 반영한 참고치로 조건부 사용한다. 신조·제조 및 비해양 사업의 차이가 있어 발행사에 그대로 적용되는 유일한 정답으로 보기는 어렵다.",
     "answer": "J2 결론, R_J2_ISSUER_BUSINESS·R_J2_MIX, 판단 근거·반대 근거, 다음 행동",
     "source": "PDF 230쪽 공급망·유지보수 유사성, 309~310쪽 매출 구성, 312쪽 신조·제조·자산 구조 차이",
     "reason": "네 비교기업을 특정하고 수요·공급망·유지보수의 연관성과 사업 구성의 차이를 함께 다뤘다. HD한국조선해양의 조선 매출 83.1%와 해외 기업의 제조·비해양 사업 비중을 조건부 배수 사용의 이유로 연결했다. 그 판단을 신조 중심 기업을 제외한 민감도로 이어 갔으므로 단순한 구성비 나열을 넘어선다.",
     "boundary": "차이가 성장·위험·수익성과 배수에 미치는 경로를 더 자세히 설명할 수 있다. 현 기준은 그 효과의 정량 조정까지 필수로 요구하지 않는다."},
    {"id": "J3", "title": "대안 계산과 결과 해석", "score": 2,
     "quote": "민감도 가정으로 표시 PER 중앙값 31.95배는 107,602.76원으로 표시배수 기준 대비 +1,515.53원(+1.43%), 신조 비중이 높은 HD한국조선해양을 제외한 나머지 평균 약 29.83배는 100,474.15원으로 -5,613.08원(-5.29%)이다.",
     "answer": "J3 다음 행동·미확인 사항, J2 다음 행동, 계산 도구의 민감도 표",
     "source": "PDF 331~332쪽 이익·PER·주식수, 310·312쪽 HD한국조선해양 사업 구성",
     "reason": "표시 31.5배로 계산한 106,087.23원을 기준으로 삼고 이익·주식수를 고정해 대안을 비교했다. 중앙값과 HD한국조선해양 제외 시 방향·금액·변화율이 맞다. 제외 이유를 사업 차이에 연결하고, 그 결과를 적정 조정폭이나 적정 공모가로 단정하지 않았다. 하나 이상의 근거 있는 대안을 요구하는 2점 기준을 충족한다.",
     "boundary": "두 대안은 계산상 가정이다. 공시 평가가액 106,113원을 기준으로 한 변화율과 섞지 않는다. 중앙값을 선택한 이유는 더 자세히 설명할 수 있으나, 사업 차이에 근거한 제외 대안이 별도로 성립한다."},
    {"id": "J4", "title": "확인 범위와 다음 행동", "score": 2,
     "quote": "받은 페이지에 한정하면 공시 산식과 선택의 주요 한계를 검토할 수 있다. 이는 독립 원자료 검증이나 투자 승인, 적정 공모가 예측이 아니다.",
     "answer": "확인 범위, J4 결론·미확인 사항·다음 행동, REQ-01·REQ-02와 OPEN·blocking=false 표시",
     "source": "PDF 41~42·298쪽 정정 후 값, 313·331쪽 순이익 차이, 329~330쪽 주가·주식수·환율, 332쪽 평가 결과",
     "reason": "공시 재현과 독립 원자료 검증을 구별했다. REQ-01은 HD한국조선해양의 2023년 두 순이익 값과 차이 원인, 연결 판단 J1·J2를 특정한다. REQ-02는 미반올림 입력·처리 규칙과 정확한 산출 과정 확인 목적을 적었다. 두 요청을 해결한 것으로 꾸미지 않았으며, 제한적 결론을 막지 않는다고 설명했다. 해당 범위에서 READY는 수용 가능하다.",
     "boundary": "공시 329~330쪽의 일별 종가에서 기준시가총액을 직접 재현하는 검산은 실제 답변에 없다. 이 한계는 아래 개선사항으로 남긴다. 기준표는 그 중간 산식을 별도 필수 계산이나 2점의 명시 요건으로 두지 않았고, 요청의 대상·이유·확인할 판단도 특정되어 있어 이번에는 1점 사유로 삼지 않는다."},
]
for row in facts + calculations:
    row.update(score=1, verdict="CORRECT", scorable=True)
for row in judgments:
    row.update(scorable=True)
metrics = {"facts": {"correct": 5, "scorable": 5, "rate": 1.0},
           "calculations": {"correct": 3, "scorable": 3, "rate": 1.0},
           "methodology": {"full_credit_domains": 4, "domains": 4, "rate": 1.0, "formula": "count(J score == 2) / 4"},
           "partial_credit_domains": [], "gold_unresolved": []}
assert sum(x["score"] for x in facts) == metrics["facts"]["correct"]
assert sum(x["score"] for x in calculations) == metrics["calculations"]["correct"]
assert sum(x["score"] == 2 for x in judgments) == metrics["methodology"]["full_credit_domains"]
record = {"grading_id": "R001", "case_id": report["case_id"], "graded_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
          "grader": "Codex AI proxy", "human_rater": None, "human_finalized": False, "blind_grading": False,
          "source_run": RUN.name, "rubric_version": "HDMS v0.3", "source_hashes": hashes,
          "facts": facts, "calculations": calculations, "judgments": judgments, "metrics": metrics,
          "flags": {"material_error": False, "unjustified_warning": False, "completion_error": False},
          "improvements": ["일별 종가·주식수·환율에서 기준시가총액을 재현하는 상류 검산이 빠짐", "독립 원자료 요청에 2024-03-14 평가기준일·추출일·조정항목을 더 구체화할 수 있음", "사업 차이가 배수에 영향을 주는 경로와 중앙값 선택 이유를 더 자세히 설명할 수 있음"],
          "verification": ["원문·기준 대조", "독립 수치 재계산", "독립 기준 재검토와 집계·상태 대조"],
          "human_timing": {"reading_start": None, "reading_end": None, "grading_minutes": None,
                           "reason": "AI 대행 작업이며 사람 평가자의 소요시간을 측정하지 않음"}}
(PRIVATE / "R001_proxy_grade.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Mm(210), Mm(297)
sec.top_margin = sec.bottom_margin = Mm(18)
sec.left_margin = sec.right_margin = Mm(20)
sec.footer_distance = Mm(9)
for name, size in [("Normal", 10), ("Title", 22), ("Heading 1", 15), ("Heading 2", 11.5)]:
    st = doc.styles[name]
    st.font.name, st.font.size, st.font.color.rgb = "Malgun Gothic", Pt(size), RGBColor(0, 0, 0)
    st.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "맑은 고딕")
    st.paragraph_format.line_spacing = 1.18
    st.paragraph_format.space_after = Pt(6)
    if name.startswith("Heading"):
        st.paragraph_format.space_before = Pt(11)
        st.paragraph_format.keep_with_next = True
    if name == "Title":
        st.font.bold = True
        st.paragraph_format.space_after = Pt(13)
    for el in st.element.xpath("./w:pPr/w:pBdr"):
        el.getparent().remove(el)
foot = sec.footer.paragraphs[0]
foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
foot.add_run("R001 대행 채점  |  ").font.size = Pt(8)
field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), "PAGE"); foot._p.append(field)
doc.core_properties.title = "HD현대마린솔루션 R001 대행 채점 결과"
doc.core_properties.author = "Codex 대행 채점"

def p(text, bold=False, size=None):
    out = doc.add_paragraph()
    r = out.add_run(text); r.bold = bold
    if size: r.font.size = Pt(size)
    return out

def h(text, level=1, page=False):
    out = doc.add_paragraph(text, style=f"Heading {level}")
    out.paragraph_format.page_break_before = page
    return out

def table(headers, rows, widths, size=9.3):
    t = doc.add_table(rows=1, cols=len(headers)); t.autofit = False
    for c, w in zip(t.columns, widths): c.width = Mm(w)
    for c, val in zip(t.rows[0].cells, headers): c.text = val
    for values in rows:
        for c, val in zip(t.add_row().cells, values): c.text = str(val)
    for ri, row in enumerate(t.rows):
        trpr = row._tr.get_or_add_trPr()
        no_split = OxmlElement("w:cantSplit"); trpr.append(no_split)
        if ri == 0: trpr.append(OxmlElement("w:tblHeader"))
        for ci, c in enumerate(row.cells):
            c.width = Mm(widths[ci]); c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr = c._tc.get_or_add_tcPr()
            borders = OxmlElement("w:tcBorders")
            for edge in ["top", "bottom", "left", "right"]:
                e = OxmlElement("w:" + edge); e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:color"), "D9D9D9"); borders.append(e)
            tcpr.append(borders)
            margins = OxmlElement("w:tcMar")
            for edge, value in [("top", "90"), ("bottom", "90"), ("left", "100"), ("right", "100")]:
                e = OxmlElement("w:" + edge); e.set(qn("w:w"), value); e.set(qn("w:type"), "dxa"); margins.append(e)
            tcpr.append(margins)
            if ri == 0:
                shade = OxmlElement("w:shd"); shade.set(qn("w:fill"), "E7E6E6"); tcpr.append(shade)
            for par in c.paragraphs:
                par.paragraph_format.space_after = Pt(2); par.paragraph_format.line_spacing = 1.12
                if ci == 0 or ci == len(headers) - 1 and len(c.text) < 25:
                    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in par.runs: r.font.size = Pt(size); r.bold = ri == 0
    p("").paragraph_format.space_after = Pt(0)
    return t

doc.add_paragraph("HD현대마린솔루션\nR001 대행 채점 결과", style="Title")
p("채점일 2026년 11월 13일   평가 대상 R001   채점자 Codex 대행", size=9)
p("사실 5개와 계산 3개는 모두 맞음으로, J1부터 J4까지는 각 2점으로 판정했다. 현재 채점기준표에서 정한 방법론적 검토 충족률은 100%다. 답변의 문장과 공시 위치, 판정 이유를 아래에 기록했다.")
table(["집계 항목", "결과", "계산 기준"], [
    ["사실 정확도", "5 / 5   100%", "맞은 사실 묶음 ÷ 채점 가능한 사실 묶음"],
    ["계산 일치율", "3 / 3   100%", "일치한 계산 ÷ 채점 가능한 계산"],
    ["판단 점수", "J1 2점  J2 2점\nJ3 2점  J4 2점", "각 영역 0점·1점·2점"],
    ["방법론적 검토 충족률", "4 / 4   100%", "2점을 받은 영역 수 ÷ 4"],
    ["부분 충족과 판정 불가", "없음", "1점 영역 없음, 네 영역 모두 채점 가능"],
], [45, 49, 76], 9.5)
h("채점 결과를 읽는 범위", 2)
p("이 점수는 HDMS 개발용 채점기준표 v0.3을 R001 한 편에 적용한 결과다. 공시 재현과 제한적 판단을 평가한 점수이며, 공모가격의 적정성이나 다른 사례의 성능까지 보장하지 않는다.")
p("원본 채점자료와 실제 답변은 보존했다. 이 파일은 사용자의 요청에 따라 AI가 대신 작성한 채점 기록이다. 사람 평가자의 직접 채점이나 확정 서명으로 기록하지 않으며, 실행 맥락을 확인한 상태에서 검토했으므로 눈가림 채점으로 집계하지 않는다.")
h("사용한 기준과 위치 표기", 2)
p("입력 문서의 3절 실제 답변, 4절 추출·계산, 5절 판정 기준을 사용했다. 기준은 HDMS 개발용 채점기준표 v0.3과 실험 실행 프로토콜 v2.0이다. 아래 공시 쪽수는 HDMS-PROS-01의 PDF 물리 페이지이며, 인쇄 쪽수는 2를 뺀 값이다. 모델 입력 밖 참고자료를 새로운 필수 정답으로 추가하지 않았다.")
p("원본 자료  HDMS_R001_답변_채점자료.docx\n사람 채점의 읽기 시작·종료·소요시간  측정하지 않음", size=9)

h("사실 다섯 묶음의 판정", page=True)
p("각 묶음의 핵심 구성요소가 모두 맞으면 1, 누락·불일치가 있으면 0으로 기록한다. 다섯 묶음 모두 채점 가능하며 각각 1점이다.")
table(["항목", "답변과 공시를 대조한 내용", "판정"], [[x["id"], x["value"] + "\n답변  " + x["answer"] + "\n공시  " + x["source"] + "\n이유  " + x["reason"], "맞음\n1"] for x in facts], [15, 137, 18], 9.4)
p("사실 정확도  5 / 5 = 100%", bold=True)

h("계산 세 항목의 판정", page=True)
for x in calculations:
    h(x["id"] + " 맞음", 2)
    p(x["formula"], bold=True)
    p(x["reason"])
    p("답변  " + x["answer"] + "\n공시  " + x["source"], size=8.8)
h("민감도 수치의 추가 대조", 2)
table(["가정", "가격 원", "기준 대비 변화"], [
    ["표시 PER 31.5배 기준", "106,087.23", "기준"],
    ["중앙값 31.95배", "107,602.76", "+1,515.53원   +1.43%"],
    ["HD한국조선해양 제외\n평균 29.833333배", "100,474.15", "-5,613.08원   -5.29%"],
], [65, 40, 65], 9.2)
p("대안 계산의 이익 151,116백만원과 주식수 44,870,190주는 고정했다. 변화율의 분모는 표시배수 기준 가격이다. 계산 일치율은 K1~K3의 3 / 3 = 100%로 집계한다.")

for start, title in [(0, "적용 이익과 비교기업의 판단"), (2, "민감도와 다음 행동의 판단")]:
    h(title, page=True)
    for x in judgments[start:start+2]:
        h(x["id"] + " " + x["title"] + " 2점", 2)
        p("답변 문장  “" + x["quote"] + "”", size=9.4)
        p("답변 위치  " + x["answer"] + "\n공시 위치  " + x["source"], size=8.7)
        p("판정 이유  " + x["reason"])
        p("조건과 남은 점  " + x["boundary"], size=9.3)

h("별도로 남길 문제와 검증 기록", page=True)
table(["확인 항목", "판정", "근거"], [
    ["핵심 결론을 바꿀 오류", "발견 없음", "주식수·이익·평가가액·공모가·정정 전후를 구분했다."],
    ["부당하거나 과장된 경고", "발견 없음", "표시 정밀도 차이를 공시 오류로 단정하지 않았다."],
    ["완료 또는 보류 문제", "발견 없음", "두 요청은 OPEN으로 남겼고, 제공 공시 범위의 한정 결론에 READY를 사용했다."],
    ["기준표 판정 불가", "없음", "F·K와 J1~J4 모두 유효한 기준으로 판정할 수 있다."],
], [51, 29, 90], 9.1)
h("감점과 구분해 남긴 개선사항", 2)
p("공시 PDF 329~330쪽의 일별 종가 20행, 상장주식수와 환율은 입력 안에 있었다. 이 값으로 기준일·1주·1개월 가격 중 최솟값을 선택해 기준시가총액을 직접 검산할 수 있지만, R001은 이미 공시된 시가총액을 이용한 PER 재계산까지만 수행했다. 이번 채점자가 추가 검산한 결과는 아래와 같으며 R001이 수행한 계산으로 소급하지 않는다.")
p("재현한 기준시가총액  단위 백만원", bold=True, size=9.2)
table(["HD한국조선해양", "Alfa Laval", "Kongsberg", "Wärtsilä"], [
    ["8,093,614", "20,837,071", "14,757,028", "11,916,525"],
], [45, 43, 41, 41], 9.2)
p("이 중간 검산을 현 기준의 새 필수 항목으로 추가하지 않았다. 차후 모든 답변에 동일하게 적용할 세부 항목으로 만들려면 기준 개정 이력과 영향 범위를 남겨야 한다. 현재 채점기준은 수정하지 않았다.", size=9.2)
p("독립 원자료 요청에는 2024년 3월 14일 평가기준일의 데이터 추출일·순이익 정의·조정 내역을 더 구체적으로 적을 수 있다. 사업 차이가 배수에 미치는 경로와 중앙값을 고른 이유도 보완할 수 있다.", size=9.2)
h("세 차례 검증", 2)
p("1차 원문과 기준 대조  입력 범위, 정정 후 표, F1~F5·K1~K3·J1~J4의 판정 요건을 대조했다. 핵심 표의 단위와 주석을 이미지로도 확인했다.", size=9.1)
p("2차 독립 수치 재계산  보존된 계산 22개와 본문의 반올림 수치·민감도를 별도 산식으로 확인했다. 추가로 일별 종가에서 네 기준시가총액을 검산했다.", size=9.1)
p("3차 독립 기준 재검토  각 J의 만점 사유와 감점 반론을 다시 검토했다. 특히 J4의 검산 누락을 사후 필수 요건으로 삼는지 점검하고, 점수 집계·미해결 요청·완료 상태를 대조했다. 세 차례는 검증 단계이며 사람 평가자 세 명을 뜻하지 않는다.", size=9.1)

doc.save(DEST)
assert hashes == {str(x.relative_to(REPO)): hashlib.sha256(x.read_bytes()).hexdigest() for x in source_paths}
print(json.dumps({"output": str(DEST), "source_files_preserved": len(hashes), "metrics": metrics}, ensure_ascii=False))
