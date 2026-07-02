"""Build a final DOCX bid response from Markdown response files.

INPUT: ordered Markdown response files generated in bid-projects/<project>/output.
OUTPUT: one formatted DOCX response file.
POS: Final delivery builder for the bid-preparation skill.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor


FONT_NAME = "宋体"
BODY_SIZE_PT = 12
HEADING1_SIZE_PT = 14
BLACK = RGBColor(0, 0, 0)
HEADING_STYLE_BY_LEVEL = {
    1: "Heading 1",
    2: "Heading 2",
    3: "Heading 3",
    4: "Heading 4",
}
HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+)$")


def set_run_font(run, size_pt: int, bold: bool = False) -> None:
    run.font.name = FONT_NAME
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = BLACK


def configure_paragraph_format(paragraph_format, before_pt: int = 0, after_pt: int = 0) -> None:
    paragraph_format.line_spacing = 1.5
    paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    paragraph_format.space_before = Pt(before_pt)
    paragraph_format.space_after = Pt(after_pt)


def configure_style(style, size_pt: int, bold: bool, before_pt: int = 0, after_pt: int = 0) -> None:
    style.font.name = FONT_NAME
    style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT_NAME)
    style.font.size = Pt(size_pt)
    style.font.bold = bold
    style.font.color.rgb = BLACK
    configure_paragraph_format(style.paragraph_format, before_pt, after_pt)


def configure_document_styles(document: Document) -> None:
    configure_style(document.styles["Normal"], BODY_SIZE_PT, bold=False)
    configure_style(document.styles["Heading 1"], HEADING1_SIZE_PT, bold=True, before_pt=8, after_pt=8)
    for style_name in ("Heading 2", "Heading 3", "Heading 4"):
        configure_style(document.styles[style_name], BODY_SIZE_PT, bold=True, before_pt=8, after_pt=8)


def next_numbering_id(parent, child_name: str, attr_name: str) -> int:
    values = []
    for child in parent.findall(qn(child_name)):
        value = child.get(qn(attr_name))
        if value is not None and value.isdigit():
            values.append(int(value))
    return (max(values) + 1) if values else 1


def add_heading_numbering(document: Document) -> int:
    numbering = document.part.numbering_part.element
    abstract_id = next_numbering_id(numbering, "w:abstractNum", "w:abstractNumId")
    num_id = next_numbering_id(numbering, "w:num", "w:numId")

    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(abstract_id))
    multi_level = OxmlElement("w:multiLevelType")
    multi_level.set(qn("w:val"), "multilevel")
    abstract.append(multi_level)

    level_texts = ["%1.", "%1.%2", "%1.%2.%3", "%1.%2.%3.%4"]
    for level, level_text in enumerate(level_texts):
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), str(level))
        start = OxmlElement("w:start")
        start.set(qn("w:val"), "1")
        num_fmt = OxmlElement("w:numFmt")
        num_fmt.set(qn("w:val"), "decimal")
        lvl_text_node = OxmlElement("w:lvlText")
        lvl_text_node.set(qn("w:val"), level_text)
        lvl_jc = OxmlElement("w:lvlJc")
        lvl_jc.set(qn("w:val"), "left")
        p_pr = OxmlElement("w:pPr")
        ind = OxmlElement("w:ind")
        ind.set(qn("w:left"), str(360 * (level + 1)))
        ind.set(qn("w:hanging"), "240")
        p_pr.append(ind)
        for node in (start, num_fmt, lvl_text_node, lvl_jc, p_pr):
            lvl.append(node)
        abstract.append(lvl)

    numbering.append(abstract)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abstract_num_id = OxmlElement("w:abstractNumId")
    abstract_num_id.set(qn("w:val"), str(abstract_id))
    num.append(abstract_num_id)
    numbering.append(num)
    return num_id


def apply_numbering(paragraph, num_id: int, level: int) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = p_pr.find(qn("w:numPr"))
    if num_pr is None:
        num_pr = OxmlElement("w:numPr")
        p_pr.append(num_pr)
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), str(level - 1))
    num_id_node = OxmlElement("w:numId")
    num_id_node.set(qn("w:val"), str(num_id))
    num_pr.append(ilvl)
    num_pr.append(num_id_node)


def markdown_table_rows(lines: list[str], start: int) -> tuple[list[list[str]], int] | None:
    if start + 1 >= len(lines) or not lines[start].lstrip().startswith("|"):
        return None
    separator = lines[start + 1].strip()
    if not re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", separator):
        return None
    rows = []
    index = start
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        if index != start + 1:
            cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
            rows.append(cells)
        index += 1
    return rows, index


def add_table(document: Document, rows: list[list[str]]) -> None:
    if not rows:
        return
    column_count = max(len(row) for row in rows)
    table = document.add_table(rows=len(rows), cols=column_count)
    table.style = "Table Grid"
    for row_index, row in enumerate(rows):
        for column_index in range(column_count):
            cell = table.cell(row_index, column_index)
            text = row[column_index] if column_index < len(row) else ""
            paragraph = cell.paragraphs[0]
            paragraph.style = document.styles["Normal"]
            configure_paragraph_format(paragraph.paragraph_format)
            run = paragraph.add_run(text)
            set_run_font(run, BODY_SIZE_PT, bold=(row_index == 0))


def add_body_paragraph(document: Document, text: str) -> None:
    paragraph = document.add_paragraph(style="Normal")
    configure_paragraph_format(paragraph.paragraph_format)
    run = paragraph.add_run(text.strip())
    set_run_font(run, BODY_SIZE_PT)


def add_heading(document: Document, text: str, level: int, num_id: int) -> None:
    paragraph = document.add_paragraph(style=HEADING_STYLE_BY_LEVEL[level])
    apply_numbering(paragraph, num_id, level)
    run = paragraph.add_run(text.strip())
    size = HEADING1_SIZE_PT if level == 1 else BODY_SIZE_PT
    set_run_font(run, size, bold=True)


def add_markdown_file(document: Document, markdown_path: Path, num_id: int) -> None:
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if not line:
            index += 1
            continue
        table_result = markdown_table_rows(lines, index)
        if table_result:
            rows, index = table_result
            add_table(document, rows)
            continue
        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            add_heading(document, heading_match.group(2), level, num_id)
        elif line.startswith("- "):
            add_body_paragraph(document, line[2:])
        else:
            add_body_paragraph(document, line)
        index += 1


def build_response_docx(markdown_files: list[Path], output_path: Path) -> dict:
    document = Document()
    configure_document_styles(document)
    num_id = add_heading_numbering(document)
    for markdown_file in markdown_files:
        resolved = markdown_file.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"响应文件不存在: {resolved}")
        add_markdown_file(document, resolved, num_id)
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)
    return {"output": str(output_path), "source_files": [str(path) for path in markdown_files]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a formatted DOCX bid response.")
    parser.add_argument("--output", type=Path, required=True, help="Final DOCX path.")
    parser.add_argument("markdown_files", type=Path, nargs="+", help="Ordered Markdown source files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_response_docx(args.markdown_files, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
