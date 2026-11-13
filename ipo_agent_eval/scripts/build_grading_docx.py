"""Create a grading copy from the preserved response and the existing rubric."""
import copy
import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pypdfium2 as pdfium
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
RUN = ROOT / "runs/20261111T233807Z_B_2db53c6b"
OUT = ROOT / "grading_exports"
QA = OUT / "_qa"
DEST = OUT / "HDMS_R001_답변_채점자료.docx"
read = lambda name: json.loads((RUN / name).read_text(encoding="utf-8"))
report, packet = read("review.json"), read("source_packet.json")
request1, request2 = read("01_extract_request.json"), read("02_review_request.json")
PDF_URL = packet["metadata"]["documents"][0]["source_url"]
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Mm(210), Mm(297)
sec.top_margin = sec.bottom_margin = Mm(19)
sec.left_margin = sec.right_margin = Mm(20)
sec.header_distance, sec.footer_distance = Mm(8), Mm(9)


def font_style(style, size, bold=False):
    st = doc.styles[style]
    st.font.name = "Malgun Gothic"
    st.font.size = Pt(size)
    st.font.bold = bold
    st.font.color.rgb = RGBColor(0, 0, 0)
    st.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "맑은 고딕")
    rf=st.element.get_or_add_rPr().rFonts
    for attr in ("asciiTheme","hAnsiTheme","eastAsiaTheme","cstheme"):
        rf.attrib.pop(qn("w:"+attr),None)
    if style=="Title":
        for border in st.element.xpath("./w:pPr/w:pBdr"):
            border.getparent().remove(border)
    snap=OxmlElement("w:snapToGrid"); snap.set(qn("w:val"),"0"); st.element.get_or_add_pPr().append(snap)
    return st


normal = font_style("Normal", 10.5)
normal.paragraph_format.line_spacing = 1.2
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.widow_control = True
font_style("Title", 23, True).paragraph_format.space_after = Pt(14)
for name, size in [("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11.2)]:
    st = font_style(name, size, True)
    st.paragraph_format.space_before = Pt(13)
    st.paragraph_format.space_after = Pt(7)
    st.paragraph_format.keep_with_next = True
for name in ["Caption", "Header", "Footer"]:
    font_style(name, 8.5)

settings = doc.settings.element
upd = OxmlElement("w:updateFields"); upd.set(qn("w:val"), "true"); settings.append(upd)
foot = sec.footer.paragraphs[0]
foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
foot.add_run("R001  |  ")
field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), "PAGE"); foot._p.append(field)
header = sec.header.paragraphs[0]
header.add_run("HD현대마린솔루션 답변 채점 자료  R001")


def rich(p, text):
    # Keep source wording, render emphasis and public source links normally.
    pattern = r"(\*\*.*?\*\*|\[[^\]]+\]\([^\n]+?\)|`[^`]+`)"
    for token in re.split(pattern, str(text)):
        if not token:
            continue
        if token.startswith("**") and token.endswith("**"):
            p.add_run(token[2:-2]).bold = True
        elif token.startswith("["):
            m = re.fullmatch(r"\[([^\]]+)\]\((.+)\)", token)
            if m:
                label, url = m.groups(); url = url.strip("<>")
                if url.startswith(("http://", "https://")):
                    hyperlink(p, label, url)
                else:
                    p.add_run(label)
            else:
                p.add_run(token)
        elif token.startswith("`") and token.endswith("`"):
            p.add_run(token[1:-1])
        else:
            p.add_run(token)
    return p


def hyperlink(p, label, url):
    rel = p.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    el = OxmlElement("w:hyperlink"); el.set(qn("r:id"), rel)
    run = OxmlElement("w:r"); prop = OxmlElement("w:rPr")
    color = OxmlElement("w:color"); color.set(qn("w:val"), "25506B"); prop.append(color)
    run.append(prop); txt = OxmlElement("w:t"); txt.text = label; run.append(txt); el.append(run); p._p.append(el)


def para(text="", bold=False, style=None, size=None):
    p = doc.add_paragraph(style=style)
    rich(p, text)
    if bold:
        for r in p.runs: r.bold = True
        p.paragraph_format.keep_with_next=True
    if size:
        for r in p.runs: r.font.size = Pt(size)
    return p


def heading(text, level=1, page=False):
    p = doc.add_paragraph(text, style=f"Heading {level}")
    if page: p.paragraph_format.page_break_before = True
    return p


def table(headers, rows, widths, font=9.3, break_long_numbers=False):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for col, width in zip(t.columns, widths): col.width = Mm(width)
    for i, head in enumerate(headers): rich(t.rows[0].cells[i].paragraphs[0], head)
    for row in rows:
        row=list(row)
        if headers[0]=="ID" and row[0]=="F2":
            row[1]="공시의 비교기업별 표시 PER은 다음과 같다.\nHD한국조선해양 36.5배\nAlfa Laval 25.6배\nKongsberg Gruppen 31.8배\nWärtsilä 32.1배\n네 곳의 산술평균을 사용했고, 공시 적용 배수는 31.5배로 표시되어 있다."
        if headers[0]=="ID" and row[0]=="F3":
            row[1]="평가시가총액은 4,761,293백만원이다.\n공모 후 잠재주식수는 44,870,190주다."
        cells = t.add_row().cells
        for cell, value in zip(cells, row): rich(cell.paragraphs[0], str(value))
    for rnum, row in enumerate(t.rows):
        trPr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit"); trPr.append(cant)
        if rnum == 0:
            repeat = OxmlElement("w:tblHeader"); trPr.append(repeat)
        for cnum, cell in enumerate(row.cells):
            cell.width = Mm(widths[cnum])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcPr = cell._tc.get_or_add_tcPr()
            borders = OxmlElement("w:tcBorders")
            for edge in ("top", "left", "bottom", "right"):
                b = OxmlElement("w:"+edge)
                for key, value in [("val", "single"), ("sz", "4"), ("color", "D9D9D9")]: b.set(qn("w:"+key), value)
                borders.append(b)
            tcPr.append(borders)
            margins = OxmlElement("w:tcMar")
            for side, val in [("top", "75"), ("bottom", "75"), ("left", "95"), ("right", "95")]:
                m = OxmlElement("w:"+side); m.set(qn("w:w"), val); m.set(qn("w:type"), "dxa"); margins.append(m)
            tcPr.append(margins)
            sh = OxmlElement("w:shd"); sh.set(qn("w:fill"), "E7EDF2" if rnum == 0 else ("F7F9FA" if rnum%2 == 0 else "FFFFFF")); tcPr.append(sh)
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.line_spacing = 1.12
                wrap=OxmlElement("w:wordWrap"); wrap.set(qn("w:val"),"0" if break_long_numbers else "1"); p._p.get_or_add_pPr().append(wrap)
                for run in p.runs:
                    run.font.size = Pt(font)
                    if rnum == 0: run.bold = True
            if cnum == 0 and len(headers)>1 and widths[0]<25:
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def markdown(text, base_level=2):
    lines = text.splitlines(); i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line: i+=1; continue
        if line.startswith("|") and i+1<len(lines) and re.match(r"^\|[\s:|\-]+\|$",lines[i+1].strip()):
            headers=[v.strip() for v in line.strip("|").split("|")]
            rows=[]; i+=2
            while i<len(lines) and lines[i].strip().startswith("|"):
                rows.append([v.strip() for v in lines[i].strip().strip("|").split("|")]); i+=1
            n=len(headers)
            widths=[17,153] if n==2 and headers[0] in ["점수","ID"] else [68,102] if n==2 and headers[0]=="경계 답변" else [32,138] if n==2 else [16,105,49] if n==3 and headers[0]=="ID" else [38]+[(170-38)/(n-1)]*(n-1)
            table(headers,rows,widths)
            continue
        m=re.match(r"^(#{1,6})\s+(.*)",line)
        if m:
            title=re.sub(r"^[0-9]+(?:\.[0-9]+)*\.?\s*", "",m.group(2))
            title=title.replace("~","에서 ").replace(":"," ").replace("·"," ")
            heading(title,min(3,base_level+max(0,len(m.group(1))-2)))
        elif line.startswith("- "):
            para(line[2:],style="List Bullet")
        elif line.startswith("> "):
            para(line[2:])
        else:
            para(line)
        i+=1


def refs(items, label="근거"):
    if not items:
        para(label+"로 따로 기록한 항목은 없다.",size=9)
        return
    seen=set()
    for ev in items:
        key=(ev["doc_id"],ev["page"],ev["locator"],ev["claim_id"])
        if key in seen: continue
        seen.add(key)
        p=doc.add_paragraph()
        p.paragraph_format.space_after=Pt(3)
        hyperlink(p,f"{ev['doc_id']} PDF {ev['page']}쪽",PDF_URL+f"#page={ev['page']}")
        p.add_run(f"  {ev['locator']}  주장 {ev['claim_id']}")
        for run in p.runs: run.font.size=Pt(8.3)


def blank_lines(count=2):
    for _ in range(count):
        p=para(" ")
        p.paragraph_format.space_after=Pt(10)
        p.paragraph_format.line_spacing=1.4
        pp=p._p.get_or_add_pPr(); borders=OxmlElement("w:pBdr"); b=OxmlElement("w:bottom")
        for k,v in [("val","single"),("sz","3"),("color","D9D9D9")]: b.set(qn("w:"+k),v)
        borders.append(b); pp.append(borders)


OUT.mkdir(exist_ok=True); QA.mkdir(exist_ok=True)
doc.core_properties.title="HD현대마린솔루션 AI 답변 채점 자료"
doc.core_properties.subject="답변 R001의 배경과 질문 실제 답변 채점기준과 기록란"
doc.core_properties.author="IPO 연구"
doc.core_properties.keywords="HDMS R001 채점"

para("HD현대마린솔루션 AI 답변 채점 자료",style="Title")
para("평가 대상 R001",bold=True,size=13)
para("이 문서는 규리가 HD현대마린솔루션의 IPO 공시를 검토한 AI 답변 한 편을 채점할 때 사용하는 자료다. 연구의 목적과 사례의 배경, 모델에게 전달한 질문, 실제 답변, 확인할 정답과 판정 기준을 한곳에 모았다. 마지막 기록란에 항목별 점수와 그 이유를 적으면 된다.")
para("평가 대상은 R001로 표시했다. 점수는 비워 두었다. 답변의 어느 문장이 어떤 공시 근거와 연결되는지 확인하면서, 사실·계산의 정확성과 판단의 타당성을 각각 기록한다.")
para("작성일 2026년 11월 12일   사례 HDMS DEV 01   평가자 규리")
heading("문서를 읽는 순서",2)
for text in ["먼저 연구 목적과 사례의 날짜·용어를 읽어 무엇을 판단할 과제인지 확인한다.","실제 질문과 자료 범위를 확인한 뒤 R001의 답변을 읽는다.","채점기준과 원문을 대조하고 마지막 기록란에 점수·답변 문장·공시 위치·판정 이유를 적는다."]:
    para(text,style="List Number")
table(["부분","담은 내용"],[["1 연구와 사례의 배경","왜 이 답변을 채점하는지와 어떤 공시를 기준으로 읽는지"],["2 모델에게 전달한 과제","실제 지시문과 공통 방법서의 원문"],["3 평가할 실제 답변","모델이 작성한 결론·사실·근거·한계·요청·요약"],["4 계산에 사용한 값과 도구의 결과","모델이 받은 숫자와 계산 결과"],["5 확인할 정답과 판정 기준","F1부터 F5, K1부터 K3, J1부터 J4의 기준"],["6 채점 기록란","점수와 판단 이유를 적는 빈 양식"],["부록 실제로 제공된 공시 페이지","모델에게 전달한 공시 30쪽 전체"]],[43,127])

heading("1 연구와 사례의 배경",page=True)
heading("어떤 능력을 확인하는 연구인가",2)
para("이 연구는 공개된 IPO 자료를 AI가 검토할 때, 숫자를 제대로 찾고 계산하는지와 그 숫자를 사용하는 이유·한계를 근거에 따라 설명하는지를 확인한다. 검토 대상은 국내 비금융 기업의 실적 기반 PER 평가 사례다. 이미 공개된 가격 산정 근거를 읽는 과제이므로, 이후 주가나 아직 발표되지 않은 공모가격을 예측하는 성과로 해석하지 않는다.")
para("이 파일럿에서 공통으로 사용하는 기본 모델은 GPT-6.1 Terra다. 비교할 실행 방식이 달라도 같은 기본 모델을 사용한다.")
para("전체 연구에서는 정해진 순서를 따르는 방식, 모델이 다음 행동을 고르는 방식, 개발 중 발견한 실패를 확인하는 장치를 추가한 방식을 비교한다. 비교할 때는 같은 기본 모델, 허용 문서, 공통 방법서와 도구, 자원 한도와 제출 양식을 사용한다. 어느 방식이 더 좋다는 결론을 미리 정하지 않는다. 이 문서에서는 한 답변이 검토 방법을 얼마나 충실하게 적용했는지 채점한다.")
para("채점 담당자는 규리 한 명이다. 사실과 계산을 확인한 뒤, 적용 이익·비교기업·민감도·추가 확인의 네 판단 영역에 각각 0점, 1점, 2점을 준다. 계산을 맞혔다는 이유만으로 판단 점수도 자동으로 높아지는 것은 아니다. 각각의 근거와 논리를 읽고 기록한다.")
heading("IPO 평가에서 쓰는 말을 먼저 이해하기",2)
para("IPO는 회사의 주식을 일반 투자자에게 처음 공개적으로 모집하거나 매출하는 절차다. 투자설명서에는 공모 조건, 회사의 사업과 재무정보, 위험과 가격 산정 근거가 들어 있다. 이 사례에서 중심으로 읽을 부분은 인수인의 의견 가운데 공모가격에 대한 의견이다.")
para("PER은 주가가 주당순이익의 몇 배인지 나타내는 숫자다. 회사 전체로 보면 주식의 시장가치를 그 주식의 주주에게 귀속되는 순이익으로 나눈 값이다. 비교기업의 PER을 발행사의 이익에 곱하고, 그 금액을 평가에 사용하는 주식수로 나누면 주당 평가가액이 된다.")
para("주당 평가가액은 가격 산정에 쓰는 계산값이다. 확정 공모가는 수요예측 등을 거쳐 실제 청약에 적용하는 가격이다. 같은 공시에 두 숫자가 함께 나오므로 답변이 무엇을 계산했다고 말하는지 구분해서 읽는다.")
para("연결재무제표는 발행사와 연결 대상 회사를 합쳐 작성한다. 그 이익 중 지배기업의 주주에게 돌아가는 부분이 지배주주 귀속 순이익이다. 새로 발행하는 신주와 기존 주주가 이미 가진 주식을 파는 구주매출도 구분해야 한다. 구주매출만으로 회사의 전체 발행주식수가 늘어나지는 않는다.")
heading("어느 시점의 어떤 자료인가",2)
table(["항목","이 사례의 기준"],[["대상 기업","HD현대마린솔루션  유가증권시장 상장 사례"],["대표 공시","2024년 4월 24일 정정 투자설명서  DART 접수번호 20240424000222"],["사례 자료 마감","2024년 4월 24일 23시 59분 59초 한국시간"],["일반청약 시작","2024년 4월 25일"],["주가와 환율의 기준일","2024년 3월 14일"],["이익 기간","2023년 한 해의 과거 실적"],["문서 ID","HDMS-PROS-01  전체 638쪽"],["쪽 번호 읽는 법","이 문서의 PDF 쪽은 첫 장부터 센 번호다. 인쇄된 본문 쪽은 PDF 쪽에서 2를 뺀 값이다. 예를 들어 PDF 332쪽은 인쇄 330쪽이다."]],[43,127])
para("자료 마감과 주가 기준일은 역할이 다르다. 4월 24일까지 공개된 자료로 검토한다고 해서, 그 내용이 모두 3월 14일에도 같은 정밀도로 공개돼 있었다고 단정할 수는 없다. 공개 시각은 날짜까지만 확인되어 있다.")
para("정정 신고 앞부분에는 바뀌기 전과 바뀐 후의 표가 함께 들어 있다. 현재 적용값을 판단할 때는 정정 후 표와 본문을 대조한다. 최초제출일의 2023년 표기는 공시 접수 이력의 2024년 4월 17일과 차이가 있어, 버전 확인에는 실제 접수 이력을 사용한다.")
p=para("공시 원문 "); hyperlink(p,"638쪽 투자설명서 PDF",PDF_URL)
p=para("공식 접수 "); hyperlink(p,"DART 2024년 4월 24일 정정 투자설명서","https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240424000222")

heading("2 모델에게 전달한 과제",page=True)
para("모델에게는 두 차례의 업무 지시가 전달되었다. 먼저 공시에서 계산에 필요한 숫자와 단위·기간·출처를 적게 했다. 그 입력으로 계산 도구가 다시 계산한 결과를 제공한 뒤, 네 영역의 검토 의견을 작성하도록 했다. 아래 지시문은 해당 요청에 실제 들어간 문장이다.")
heading("숫자와 출처를 찾는 질문 원문",2)
para(json.loads(request1["input"][1]["content"])["task"])
heading("검토 의견을 작성하는 질문 원문",2)
para(json.loads(request2["input"][1]["content"])["task"])
para("지시문의 values는 추출한 숫자를 적는 칸, peers는 비교기업 목록, facts는 공시에서 확인한 사실을 적는 칸이다. claim_id는 주장마다 붙이는 번호이고, judgment_id는 검토 영역의 번호다. missing_inputs는 확보하지 못한 계산 입력을 기록하는 목록이며 request_id는 그 입력을 확인하기 위한 요청 번호다.")
heading("두 요청에 공통으로 전달한 지시문 원문",2)
for line in request1["input"][0]["content"].splitlines():
    if line.strip(): para(line)
heading("실제로 제공된 자료의 범위",2)
para("공시 전체는 638쪽이지만, 이번 응답에 실제로 전달된 페이지는 30쪽이다. PDF 번호로 40~42쪽, 227~232쪽, 297~299쪽, 308~313쪽, 329~333쪽, 420~426쪽이다. 이 30쪽 전체를 부록에 넣었다. 계산 입력과 계산 도구의 결과는 4절에 별도로 실었다.")
para("채점기준표가 참고하는 다른 페이지나 외부 자료도 있다. 예를 들어 PDF 302쪽과 314~315쪽은 평가자가 원문을 확인할 수 있는 참고 위치지만 이번 모델 입력에는 없었다. 답변은 입력 안의 다른 표·문단으로도 같은 사실을 정확히 뒷받침할 수 있다. 입력 밖 자료에서만 알 수 있는 내용을 새로운 필수 정답으로 추가하지 않는다.")
heading("함께 제공한 공통 검토 방법서 원문",2)
markdown(packet["manual"],2)

heading("3 평가할 실제 답변",page=True)
para("이 절의 문장은 모델이 제출한 답변 그대로다. 읽기 편하도록 필드 이름을 한글 소제목으로 표시하고 출처를 문장 뒤에 배치했다. 채점자의 해설이나 점수는 섞지 않았다. 4절의 수치는 계산 도구가 반환한 결과이며 모델의 자유 서술과 구분해 읽는다.")
heading("모델이 밝힌 확인 범위",2)
for text in report["scope"]["verification_limits"]: para(text,style="List Bullet")
names={"J1":"J1 적용 이익에 관한 답변","J2":"J2 비교기업에 관한 답변","J3":"J3 계산과 민감도에 관한 답변","J4":"J4 현재 가능한 검토와 다음 행동에 관한 답변"}
for j in report["judgments"]:
    heading(names[j["domain"]],2)
    para("모델이 선택한 처리  "+{"ACCEPT":"수용","CONDITIONAL":"조건부 수용","REQUEST_INFO":"추가 정보 요청","ESCALATE":"사람 검토 요청"}[j["disposition"]],bold=True)
    para("결론",bold=True); para(j["conclusion"])
    para("공시에서 확인했다고 적은 사실",bold=True)
    for n,f in enumerate(j["facts"],1):
        para(f"사실 {n}  {f['claim_id']}",bold=True,size=9.5)
        para(f["text"]); refs(f["evidence"])
    para("판단의 근거로 연결한 위치",bold=True); refs(j["evidence"])
    para("반대 근거로 함께 검토한 위치",bold=True); refs(j["counter_evidence"])
    para("확인하지 못했다고 적은 점",bold=True)
    for text in j["unknowns"]: para(text,style="List Bullet")
    para("다음 행동",bold=True); para(j["next_action"])
heading("모델이 남긴 추가 확인 요청",2)
for r in report["requests"]:
    heading("요청 "+r["request_id"].replace("-"," "),3)
    para("질문",bold=True); para(r["question"])
    para("필요한 이유",bold=True); para(r["why_needed"])
    para("관련 판단  "+", ".join(r["related_judgment_ids"])+"   완료를 막는 문제로 표시  "+("예" if r["blocking"] else "아니요")+"   해결 상태  "+r["resolution_status"])
    para("해결 근거로 기록한 항목은 없다.",size=9)
heading("모델이 제출한 핵심 메모",2)
for text in report["memo"]: para(text,style="List Bullet")
table(["표시 항목","제출된 값"],[["모델이 보고한 상태",report["model_reported_status"]],["추가 사람 검토 요청","0개"],["확보하지 못한 계산 입력","0개"]],[55,115])
para("READY는 모델이 현재 자료 범위에서 검토를 마쳤다고 표시한 상태다. 완료를 막는 미해결 요청이 없다고 표시한 근거가 타당한지도 J4에서 채점한다. 정보 요청은 기록만 했으며 회사나 사람이 답변한 것으로 처리하지 않았다.")

heading("4 계산에 사용한 값과 도구의 결과",page=True)
para("아래는 최종 의견 작성 전에 모델에게 제공한 추출값과 계산 결과다. 계산은 프로그램 도구가 수행했다. 값 옆의 기간·단위·출처를 함께 읽어야 어떤 숫자로 어떤 결과를 얻었는지 알 수 있다. 추가 소수점 자릿수는 계산상의 정밀도이며 원래 공시가 그만큼 정확한 값을 공개했다는 뜻은 아니다.")
labels={"earnings_million_krw":"적용 순이익","applied_per":"공시 적용 PER","reported_equity_million_krw":"공시 평가시가총액","reported_price_krw":"공시 주당 평가가액","share_count":"공시 적용 주식수","existing_shares":"공모 전 주식수","new_shares":"신주","dilutive_shares":"희석가능 주식수","secondary_sale_shares":"구주매출"}
heading("숫자 추출 단계에서 남긴 설명",2)
for label,key in [("문서 버전 설명","document_version_notes"),("추출 단계의 확인 한계","extraction_limits")]:
    para(label,bold=True)
    for value in report["extracted_inputs"][key]: para(value,style="List Bullet")
rows=[]
for k,f in report["extracted_inputs"]["values"].items():
    rows.append([labels[k],f["value"] or "확보 못함",f["unit"],f["period"],", ".join(str(e["page"]) for e in f["evidence"])])
table(["항목","추출값","단위","기간과 기준","PDF 쪽"],rows,[38,33,15,60,24],8.8)
rows=[]
for p in report["extracted_inputs"]["peers"]:
    rows.append([p["name"],p["per"]["value"],p["market_cap_million_krw"]["value"],p["earnings_million_krw"]["value"]])
table(["비교기업","표시 PER 배","시가총액 백만원","순이익 백만원"],rows,[62,28,40,40])
for f in [*report["extracted_inputs"]["values"].values(),*[p[k] for p in report["extracted_inputs"]["peers"] for k in ["per","market_cap_million_krw","earnings_million_krw"]]]:
    para(f["claim_id"]+"  "+f["description"]+"  기간 "+f["period"],size=8.3)
    refs(f["evidence"])
heading("기본 재계산 결과",2)
calc=read("calculations.json")
units={"KRW/share":"원 1주당","shares":"주","multiple":"배"}
formulas={"share_sum":"기존 주식 + 신주 + 희석가능 주식  구주는 더하지 않음","share_count_difference":"주식수 합계 - 공시 적용 주식수","price_from_reported_equity":"공시 평가시가총액 백만원 × 1,000,000 ÷ 적용 주식수","price_from_displayed_per":"적용 순이익 백만원 × 1,000,000 × 표시 배수 ÷ 적용 주식수","reported_price_difference":"공시 평가시가총액에서 계산한 가격 - 공시 주당 평가가액","displayed_price_difference":"표시 배수에서 계산한 가격 - 공시 주당 평가가액","implied_per":"공시 평가시가총액 ÷ 적용 순이익  같은 금액 단위","peer_displayed_mean":"비교기업 표시 PER의 합계 ÷ 기업 수","peer_displayed_median":"표시 PER을 정렬한 뒤 가운데 두 값의 평균","peer_recomputed_mean":"각 기업 시가총액을 이익으로 나눈 배수의 평균","price_from_recomputed_peer_mean":"적용 순이익 백만원 × 1,000,000 × 다시 구한 평균 배수 ÷ 적용 주식수"}
table(["계산 항목과 산식","도구가 반환한 값","단위"],[[r["label"]+"\n"+formulas.get(r['id'],"해당 비교기업의 시가총액 ÷ 해당 비교기업의 순이익"),r["result"] or r["reason"],units.get(r["unit"],r["unit"])] for r in calc["recalculation"]["calculations"]],[76,71,23],8.8,True)
heading("가정을 바꾼 계산 결과",2)
para("이 표의 변화는 공시에 표시된 31.5배로 재계산한 가격을 기준으로 한다. 공시의 주당 평가가액 자체와 비교한 차이가 아니다. 각 대안은 계산상 가정이며 그 배수를 반드시 적용해야 한다는 결론을 담지 않는다.")
sc=calc["sensitivity"]
para("기준 가격  "+sc["baseline"]["result"]+"원")
para("비교할 때 보기 쉽도록 먼저 소수점 두 자리의 표시값을 정리했다. 바로 다음 표에는 도구가 반환한 계산상 원값을 모두 보존했다. 두 표는 같은 계산이며 표시 자릿수만 다르다.")
round2=lambda value: format(Decimal(value).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP),',.2f') if value is not None else '해당 없음'
table(["계산상 대안","PER 배","가격 원","차이 원","변화율 퍼센트"],[[r["label"],round2(r.get("applied_per")),round2(r.get("result")),round2(r.get("difference_krw")),round2(r.get("difference_percent"))] for r in sc['scenarios']],[65,22,30,28,25],8.8)
para("아래는 같은 결과의 계산상 원값이다.",bold=True)
table(["계산상 대안","가정한 PER 배","가격 원","기준 대비 차이 원","변화율 퍼센트"],[[r["label"],r.get("applied_per") or "해당 없음",r["result"] or "계산 불가",r.get("difference_krw") or "해당 없음",r.get("difference_percent") or "해당 없음"] for r in sc["scenarios"]],[42,28,34,34,32],8.2,True)
for text in calc["recalculation"]["notes"]+sc["notes"]: para(text,style="List Bullet")

heading("5 확인할 정답과 판정 기준",page=True)
para("이 절은 평가자가 사용할 정답과 판정 기준이다. 모델에 제공한 입력이 아니다. 기준은 기존 개발용 채점기준표 v0.3과 실험 실행 프로토콜 v2.0을 따른다. 아래 예시는 타당한 답을 이해하기 위한 것으로, 예시의 문구를 그대로 썼는지로 점수를 주지 않는다.")
gold=(REPO/"phase1/HDMS_DEV_01_채점기준표.md").read_text(encoding="utf-8")
gold=gold.replace("그런 대안의 실제 계산은 7절에서 확인한다", "그런 대안의 실제 계산은 이 문서 4절에서 확인한다")
gold=gold.replace("3절에서 적용 PER", "이 문서 4절에서 적용 PER")
gold=gold.replace("4.4절에서 설명한 일별 종가", "부록 PDF 329~330쪽에 있는 일별 종가")
gold=gold.replace("329 / 331, 평가 시가총액 산출 내역과 주석", "329~330 / 331~332, 평가 시가총액 산출 내역과 주석")
start=gold.index("## 3."); end=gold.index("## 7.")
markdown(gold[start:end],2)
heading("판정이 달라질 수 있는 답변 예시",2)
example=gold[gold.index("| 경계 답변 |"):]
markdown(example,2)
heading("참고 위치와 실제 입력을 구분해서 읽기",2)
para("공시 PDF 329~330쪽의 일별 종가·상장주식수·환율은 이번 입력 안에 있다. 따라서 그 자료로 가능한 재계산과 거래소·공급자 원자료를 새로 확인하는 일을 구분해 J4를 읽는다. 기준표가 언급하는 외부 감사보고서·사업보고서·해외 실적자료는 평가자 참고 자료이며 이번 모델 입력에 포함하지 않았다.")
para("기준표의 PDF 302쪽과 314~315쪽은 이번 30쪽 입력에 포함하지 않았다. 같은 내용이 입력 안 다른 표나 문단에 있으면 그 근거를 인정한다. 공시 안에 이미 있는 값을 다시 요청해 가능한 검토까지 보류했는지, 실제로 없는 독립 자료를 미확인으로 남겼는지를 문장과 함께 판정한다.")

heading("6 채점 기록란",page=True)
para("평가 대상 R001   평가자 ____________________   채점일 ____________________")
para("읽기 시작 ____________________   읽기 종료 ____________________   채점에 걸린 시간 ____________________")
heading("사실과 계산을 확인한 기록",2)
para("각 항목에서 맞음·틀림·기준표 판정 불가 중 하나를 표시한다. 근거 칸에는 답변의 문장 또는 항목과 공시 쪽·표를 적는다. 답변이 없거나 틀린 경우와 기준표 자체가 판정할 수 없는 경우를 구분한다.")
items=[("F1","적용 이익의 값·기간·귀속 범위"),("F2","비교기업별 PER·평균 방식·적용 배수"),("F3","평가시가총액과 적용 주식수"),("F4","기존 주식·신주·희석가능분·구주의 처리"),("F5","주당 평가가액"),("K1","적용 주식수의 합계"),("K2","평가시가총액을 주식수로 나눈 계산"),("K3","표시 배수 계산의 차이와 정밀도 설명")]
table(["항목","확인 내용","판정과 근거"],[[k,t,"□ 맞음  □ 틀림  □ 기준표 판정 불가\n답변 위치\n공시 위치\n이유"] for k,t in items],[15,58,97],9)
for number in (1,2):
    heading("판단 점수와 이유를 적는 기록 "+str(number),page=True)
    for key in (["J1","J2"] if number==1 else ["J3","J4"]):
        heading({"J1":"J1 적용 이익의 비교 가능성","J2":"J2 비교기업을 사용하는 판단","J3":"J3 대안 계산과 결과 해석","J4":"J4 확인 범위와 다음 행동"}[key],2)
        para("점수  □ 0점  □ 1점  □ 2점  □ 기준표 판정 불가")
        para("답변에서 판단한 문장과 위치")
        blank_lines(1)
        para("확인한 공시 쪽과 표 또는 문단")
        blank_lines(1)
        para("이 점수를 준 이유와 조건 또는 빠진 내용")
        blank_lines(2)
heading("점수 집계와 별도로 남길 문제",page=True)
para("맞은 사실 묶음 ______ / 채점 가능한 사실 묶음 ______  기본 항목 수 5")
para("일치한 계산 항목 ______ / 채점 가능한 계산 항목 ______  기본 항목 수 3")
para("2점을 받은 판단 영역 ______ / 4   방법론적 검토 충족률 ______ 퍼센트")
para("1점을 받은 영역과 사유 __________________________________________________________")
para("네 영역 모두 채점 가능할 때만 2점을 받은 영역 수를 4로 나눈다. 예를 들어 2점·1점·2점·0점이면 50퍼센트다. 점수를 더해 8점 만점으로 환산한 값과 혼동하지 않는다. 어느 영역이든 기준표에서 유효한 항목이 없어 판정할 수 없다면 주지표는 NA로 기록하고 이유를 남긴다.")
para("기준표 판정 불가에 해당하는 영역과 이유")
blank_lines(2)
para("핵심 결론을 바꿀 수 있는 오류  □ 없음  □ 있음\n해당 답변 문장과 영향")
blank_lines(2)
para("부당하거나 과장된 경고  □ 없음  □ 있음\n해당 경고와 그렇게 판정한 근거")
blank_lines(1)
para("완료 또는 보류 판단의 문제  □ 없음  □ 있음\n중요한 미해결 쟁점을 지나쳤는지 또는 가능한 검토까지 불필요하게 보류했는지")
blank_lines(1)
para("기존 기준표에 없지만 타당하다고 본 지적과 그 근거")
blank_lines(1)
para("채점기준을 수정해야 한다면 수정 이유와 적용 범위를 남기고, 같은 사례의 모든 답변에 동일하게 적용한다. 점수 원본과 변경 이유를 보존한다.")

appendix=doc.add_section(WD_SECTION_START.NEW_PAGE)
appendix.top_margin=Mm(12); appendix.bottom_margin=Mm(10)
appendix.left_margin=appendix.right_margin=Mm(10)
heading("부록 실제로 제공된 공시 페이지")
para("다음은 모델에게 실제로 제공한 공시 30쪽 전체다. 원문의 표·주석·정정 전후 표시를 함께 볼 수 있도록 페이지 모습 그대로 넣었다. PDF 첫 장부터 센 쪽 번호와 문서에 인쇄된 쪽 번호를 함께 적었다. 평가자는 이 페이지와 앞의 채점기준을 오가며 답변의 인용을 확인할 수 있다.")
table(["PDF 쪽","주로 확인할 내용"],[["40~42","정정 전과 정정 후 가격 산정 요약"],["227~232","비교기업 선정과 PER 비교의 한계"],["297~299","본문 공모가 산정 요약"],["308~313","비교기업의 사업·매출 구성과 재무정보"],["329~333","종가·주식수·환율·PER·주당 평가가액"],["420~426","발행사의 연결·별도 재무정보와 이익 귀속"]],[35,135])
pdf=pdfium.PdfDocument(str(ROOT/"data/public/raw/HDMS-PROS-01.pdf"))
source_images=QA/"source_images"; source_images.mkdir(exist_ok=True)
for chunk in packet["sources"]:
    page=chunk["page"]
    p=para(f"HDMS PROS 01  PDF {page}쪽  인쇄 {chunk['printed_page']}쪽",bold=True,size=9)
    p.paragraph_format.page_break_before=True
    p.paragraph_format.space_before=Pt(0); p.paragraph_format.space_after=Pt(3)
    path=source_images/f"source_{page:04}.png"
    if not path.exists(): pdf[page-1].render(scale=3).to_pil().save(path)
    p=doc.add_paragraph(); p.paragraph_format.space_after=Pt(0); p.paragraph_format.line_spacing=1
    p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    from PIL import Image
    with Image.open(path) as im: ratio=im.width/im.height
    height=min(257,190/ratio); p.add_run().add_picture(str(path),height=Mm(height))
pdf.close()
for section in doc.sections:
    for grid in section._sectPr.xpath("./w:docGrid"):
        section._sectPr.remove(grid)
doc.save(DEST)

private=ROOT/"data/private"; private.mkdir(exist_ok=True)
(private/"grading_export_map_R001.json").write_text(json.dumps({"grading_id":"R001","case_id":report["case_id"],"source_run":str(RUN.relative_to(ROOT)),"condition":"B","output":str(DEST.relative_to(ROOT)),"source_review_sha256":hashlib.sha256((RUN/"review.json").read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"output":str(DEST),"source_pages":len(packet["sources"]),"paragraphs":len(doc.paragraphs),"tables":len(doc.tables)},ensure_ascii=True))
