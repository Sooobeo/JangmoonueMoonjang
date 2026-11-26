"""Produce HTML and Word from one Korean report and compare the visible text."""
import argparse
import html
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Cm, Pt, RGBColor
from lxml import html as html_tree

ROOT = Path(__file__).resolve().parents[1]
HOME_RUNTIME = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"
SKILL = Path.home() / ".codex/plugins/cache/openai-primary-runtime/documents/26.1123.11515/skills/documents"


def parse(path):
    result = []
    for raw in path.read_text(encoding="utf8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "<!-- page -->":
            result.append(("break", ""))
        elif line.startswith("|"):
            cells = [s.strip() for s in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", s) for s in cells):
                continue
            if not result or result[-1][0] != "table":
                result.append(("table", []))
            result[-1][1].append(cells)
        elif line.startswith("#"):
            level, label = line.split(" ", 1)
            result.append((f"h{len(level)}", label))
        else:
            result.append(("p", line))
    return result


CSS = """
body{background:#edf1f4;color:#18232d;font:17px/1.7 'Malgun Gothic',sans-serif;margin:0;word-break:keep-all}
main{max-width:880px;margin:30px auto;background:white;padding:50px 64px 65px}
h1,h2,h3{line-height:1.35;color:#101820}h1{font-size:2.15rem;margin:0 0 1.1rem}
h2{font-size:1.5rem;margin:2rem 0 .85rem}h3{font-size:1.1rem;margin:1.25rem 0 .4rem}
p{margin:.7rem 0}table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.94rem}
td,th{border:1px solid #d9d9d9;padding:.48rem .66rem;vertical-align:middle;text-align:left}
th{background:#28465c;color:white}tr:nth-child(odd) td{background:#eff4f7}
@media(max-width:700px){body{font-size:15px}main{margin:0;padding:22px 16px}
td,th{padding:.35rem;font-size:.88rem}}
@media print{main{max-width:none;margin:0;padding:0}body{background:white}.split{break-before:page}
tr{break-inside:avoid}th{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""


LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def segments(text):
    pos=0
    for m in LINK.finditer(text):
        yield text[pos:m.start()], None
        yield m[1], m[2]
        pos=m.end()
    yield text[pos:], None


def web_inline(text):
    return "".join(html.escape(s) if url is None else
                   f'<a href="{html.escape(url,quote=True)}">{html.escape(s)}</a>' for s,url in segments(text))


def html_file(blocks, path):
    out = ['<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" '
           'content="width=device-width,initial-scale=1"><title>'+html.escape(blocks[0][1])+
           '</title><style>'+CSS+'</style></head><body><main>']
    next_page = False
    for kind, value in blocks:
        if kind == "break":
            next_page = True
        elif kind == "table":
            out.append("<table>")
            for i, row in enumerate(value):
                tag = "td" if i else "th"
                out.append("<tr>"+"".join(f"<{tag}>{html.escape(s)}</{tag}>" for s in row)+"</tr>")
            out.append("</table>")
        else:
            attr = ' class="split"' if next_page else ""
            out.append(f"<{kind}{attr}>{web_inline(value)}</{kind}>")
            next_page = False
    path.write_text("\n".join(out)+"</main></body></html>", encoding="utf8")


def font(style, size, bold=False):
    style.font.name = "Malgun Gothic"
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "맑은 고딕")


def element(tag, **attrs):
    node = OxmlElement("w:"+tag)
    for key, value in attrs.items():
        node.set(qn("w:"+key), str(value))
    return node


def add_table(doc, matrix):
    count = len(matrix[0])
    if any(len(row) != count for row in matrix):
        raise ValueError("Inconsistent Markdown table column count")
    table = doc.add_table(rows=0, cols=count)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    maxlens = [max(len(row[c]) for row in matrix) for c in range(count)]
    weights = [max(5, val)**.58 for val in maxlens]
    widths = [Cm(16.6*w/sum(weights)) for w in weights]
    for col, width in zip(table.columns, widths):
        col.width = width
    margins = element("tblCellMar")
    for side, size in [("top",80),("bottom",80),("start",95),("end",95)]:
        margins.append(element(side, w=size, type="dxa"))
    borders = element("tblBorders")
    for side in ("top","left","bottom","right","insideH","insideV"):
        borders.append(element(side, val="single", sz=5, color="D9D9D9"))
    table._tbl.tblPr.append(margins)
    table._tbl.tblPr.append(borders)
    for i, values in enumerate(matrix):
        row = table.add_row()
        trpr = row._tr.get_or_add_trPr()
        trpr.append(element("cantSplit"))
        if not i:
            trpr.append(element("tblHeader",val="true"))
        for j, (s, cell) in enumerate(zip(values, row.cells)):
            cell.width = widths[j]
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            color = "294B61" if i == 0 else "EFF4F7" if i%2 == 0 else "FFFFFF"
            cell._tc.get_or_add_tcPr().append(element("shd",fill=color))
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.line_spacing = 1.18
            p.paragraph_format.keep_with_next = i == 0
            if j and len(s) < 14:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(s)
            run.font.size = Pt(10)
            run.bold = not i
            if not i:
                run.font.color.rgb = RGBColor(255,255,255)
            elif re.fullmatch("[■□]+",s):
                run.font.color.rgb = RGBColor.from_string("255E70")


def word_file(blocks, path):
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2.2)
    section.top_margin = Cm(1.9)
    section.bottom_margin = Cm(1.8)
    section.footer_distance = Cm(.85)
    folio = section.footer.paragraphs[0]
    folio.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    page = element("fldSimple", instr="PAGE")
    folio._p.append(page)
    for name, size, bold, before, after in [
            ("Normal",11.2,False,0,7),("Title",22,True,0,12),("Heading 1",17,True,12,7),
            ("Heading 2",12.4,True,9,4)]:
        style = doc.styles[name]
        font(style,size,bold)
        style.paragraph_format.line_spacing = 1.34
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.space_before = Pt(before)
        if name != "Normal":
            ppr = style.element.get_or_add_pPr()
            for node in list(ppr.findall(qn("w:pBdr"))):
                ppr.remove(node)
    next_page = False
    for kind,value in blocks:
        if kind == "break":
            next_page = True
        elif kind == "table":
            add_table(doc,value)
        else:
            p = doc.add_paragraph(style={"h1":"Title","h2":"Heading 1","h3":"Heading 2","p":"Normal"}[kind])
            for s,url in segments(value):
                if not s:
                    continue
                if url is None:
                    p.add_run(s)
                else:
                    link=OxmlElement("w:hyperlink")
                    link.set(qn("r:id"),p.part.relate_to(url,RT.HYPERLINK,is_external=True))
                    run=p.add_run(s)
                    run.font.color.rgb=RGBColor.from_string("244F69")
                    run.font.underline=True
                    link.append(run._r)
                    p._p.append(link)
            if next_page:
                p.paragraph_format.page_break_before = True
                p.paragraph_format.space_before = Pt(0)
                next_page = False
    doc.core_properties.title = blocks[0][1]
    doc.core_properties.subject = "최초 증권신고서의 공모가 산정 검토 실험"
    doc.core_properties.author = "IPO 공시 검토 프로젝트"
    doc.save(path)


def verify(blocks, html_path, word_path):
    expected = []
    for kind,val in blocks:
        if kind == "table":
            expected.extend(c for row in val for c in row)
        elif kind != "break":
            expected.append("".join(s for s,_ in segments(val)))
    web = html_tree.parse(str(html_path),parser=html_tree.HTMLParser(encoding="utf8"))
    html_text = [n.text_content() for n in web.xpath("//main//*[self::h1 or self::h2 or self::h3 or self::p or self::td or self::th]")]
    doc = Document(word_path)
    doc_text = ["".join(p.xpath(".//w:t/text()")) for p in doc.element.body.xpath(".//w:p")]
    if expected != html_text or expected != doc_text:
        raise ValueError("Visible heading, body or table contents differ across publication formats")
    return {"paragraphs_and_cells_verified":len(expected),"native_word_tables":len(doc.tables)}


def render(path, out):
    # This managed Windows runtime ships Poppler and Word is available on the host.
    # Use the project's tested Word exporter as the PDF stage for the packaged rasterizer.
    spec=importlib.util.spec_from_file_location("document_renderer",SKILL/"render_docx.py")
    renderer=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    os.environ["PATH"]=str(HOME_RUNTIME/"native/poppler/Library/bin")+os.pathsep+os.environ["PATH"]
    def word_pdf(doc_path,user_profile,convert_tmp_dir,stem,verbose=False):
        dest=Path(convert_tmp_dir)/(stem+".pdf")
        subprocess.run([str(HOME_RUNTIME/"native/powershell/pwsh.exe"),"-NoProfile","-File",
                        str(ROOT/"scripts/word_export_pdf.ps1"),"-InputPath",str(Path(doc_path).resolve()),
                        "-OutputPath",str(dest)],check=True,timeout=180,capture_output=True)
        return str(dest),"Word PDF export"
    renderer.convert_to_pdf=word_pdf
    sys.argv=["render_docx.py",str(path.resolve()),"--output_dir",str(out.resolve()),"--emit_pdf"]
    renderer.main()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("markdown",type=Path)
    parser.add_argument("--render",type=Path)
    args=parser.parse_args()
    blocks=parse(args.markdown)
    web,word=(args.markdown.with_suffix(s) for s in (".html",".docx"))
    html_file(blocks,web)
    word_file(blocks,word)
    print(json.dumps(verify(blocks,web,word)),flush=True)
    if args.render:
        render(word,args.render)
