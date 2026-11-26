"""Render the postmortem using this project's Korean report template."""
import argparse
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from reporting import submission_formats as formats


def build(markdown, render_dir):
    blocks = formats.parse(markdown)
    web = markdown.with_suffix(".html")
    word = markdown.with_suffix(".docx")
    formats.html_file(blocks, web)
    formats.word_file(blocks, word)
    doc = Document(word)
    section = doc.sections[0]
    section.left_margin = section.right_margin = Cm(2)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.7)
    normal = doc.styles["Normal"]
    normal.font.size = Pt(10.8)
    normal.paragraph_format.line_spacing = 1.22
    normal.paragraph_format.space_after = Pt(5)
    for table in doc.tables:
        margins = table._tbl.tblPr.find(qn("w:tblCellMar"))
        for side in ("top", "bottom"):
            margins.find(qn("w:" + side)).set(qn("w:w"), "65")
        for row in table.rows:
            for cell in row.cells:
                p = cell.paragraphs[0]
                p.paragraph_format.line_spacing = 1.12
                for run in p.runs:
                    run.font.size = Pt(9.8)
    doc.save(word)
    print(formats.verify(blocks, web, word), flush=True)
    if render_dir:
        formats.render(word, render_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--render", type=Path)
    args = parser.parse_args()
    build(args.markdown, args.render)
