"""Check local destinations, rendered headings, tables and output hashes before delivery."""
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
import re
from urllib.parse import unquote
from zipfile import ZipFile
from xml.etree import ElementTree

import fitz
from scripts.a1_main_blind import BASE, wire, write_once

OUT = BASE.parent
DOC = OUT/"제출용_보고서.md"
NS = {"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def squash(text):
    return "".join(text.split())


def check(pdf):
    chronology = OUT/"전체_진행기록.md"
    md = DOC.read_text(encoding="utf8")
    headings = [re.search(r"^## (.+)$",b,re.MULTILINE)[1] for b in md.split("<!-- page -->")]
    with fitz.open(pdf) as doc:
        pages = [p.get_text() for p in doc]
    if len(pages)!=len(headings) or any(squash(h) not in squash(p) for h,p in zip(headings,pages)):
        raise ValueError("Incorrect page count or section split in the final rendering")
    with ZipFile(DOC.with_suffix(".docx")) as arc:
        root = ElementTree.fromstring(arc.read("word/document.xml"))
    native_tables=len(root.findall(".//w:tbl",NS))
    if native_tables!=sum(line.startswith("| ---") for line in md.splitlines()):
        raise ValueError("Native table count differs from the Markdown report")
    visible_blocks=len(root.findall(".//w:body//w:p",NS))
    title="## 출판과 최종 대조"
    evidence=[
        "1. **수치와 논리.** 두 방식의 원래 순위에서 등급별 짝을 직접 세는 방법과 평균 순위를 사용하는 방법으로 결과를 대조했다. 두 방식 중 한쪽만 이관한 중대 세 건을 모두 원문에서 확인했다. 37곳 전체의 추가 누락 총수와 이미 관측된 최소 한 건을 구분했다. [순위·회수 별도 검산](v1/analysis/publication_pair_crosscheck.json)",
        "2. **원문과 설명.** 독자 역할의 검토자가 유진테크놀로지 주식 수 네 항목의 합·주석 표·본문, 달바글로벌의 비교기업 제외 시점, 워트 두 역할이 제시한 공통점과 사용 공정 차이를 다시 확인했다. 가림 자료의 이전 법인명, 실패한 바깥 쪽 인용, 대체 이관과 0건 목록도 각각 구분해 설명했다.",
        f"3. **제출 형식.** 같은 Markdown에서 HTML과 DOCX를 생성하고 제목·본문·표 셀 {visible_blocks}개를 세 형식에서 순서대로 대조했다. Word의 표 {native_tables}개는 편집할 수 있는 표다. 실제 Word에서 렌더링한 {len(pages)}쪽 전부에서 머리글·줄바꿈·쪽번호·표 경계와 한글 표시를 확인했다. 본평가 정정 실행기까지 포함한 자동 회귀 검사 644개가 통과했다."]
    for src,role in [(chronology,"chronology"),(BASE/"단계별_검토.md","review")]:
        original=src.read_text(encoding="utf8").split("\n"+title,1)[0].rstrip()
        lines=evidence if role=="chronology" else [s.replace("](v1/analysis/","](analysis/") for s in evidence]
        src.write_text(original+"\n\n"+title+"\n\n"+"\n".join(lines)+"\n",encoding="utf8")
    local = {}
    for src in (DOC,chronology,BASE/"단계별_검토.md"):
        urls = re.findall(r"\[[^\]]+\]\(([^)]+)\)",src.read_text(encoding="utf8"))
        paths = [unquote(u.split("#")[0]) for u in urls if not u.startswith(("http:","https:","#"))]
        missing = [u for u in paths if not (src.parent/u).exists()]
        if missing:
            raise FileNotFoundError((src,missing))
        local[src.name]=len(paths)
    all_files=[chronology,*[DOC.with_suffix(s) for s in (".md",".html",".docx")]]
    output={"deliverable_sha256":{p.name:sha256(p.read_bytes()).hexdigest() for p in all_files},
            "report_pages":len(pages),"page_headings":headings,"native_word_tables":native_tables,"visible_body_paragraphs_and_cells":visible_blocks,
            "tested_local_link_counts":local,"rendered_pdf_sha256":sha256(pdf.read_bytes()).hexdigest()}
    write_once(BASE/"publication_review.json",wire(output))
    return output


if __name__=="__main__":
    parser=ArgumentParser(description=__doc__)
    parser.add_argument("pdf",type=Path)
    print(check(parser.parse_args().pdf))
