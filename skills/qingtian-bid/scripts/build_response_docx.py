"""Build the final 施工组织设计 DOCX from Markdown files (qingtian-bid stage 6).

迁移来源见 CHANGELOG《脚本来源》，相对来源的改动：
  * 格式取自 qingtian-bid 的格式预设库（docx_font_profiles）：正文与一至三级标题分设字体、
    字号（四、五级跟三级），西文字体可选，标题是否加粗可设；
  * 行距支持倍数、固定值、最小值；只含图片的段落固定用单倍行距，避免固定值行距
    把嵌入图裁成窄条（施工总平面布置图、横道图都会受影响）；
  * heading_page_breaks 为否时，新文件不再强制另起一页（施组有篇幅上限）；
  * 暗标模式不生成页眉页脚，也不接受页眉文字；
  * 标题只靠样式定格式，文字不加直接格式，Word 更新目录时条目才按目录样式排；
    所有样式显式关闭斜体（默认模板的 Heading 4 自带斜体）；
  * 可直接传入格式，有 project-state.json 时必须与项目已确认的格式一致；项目格式未确认
    或有变更待确认时拒绝出稿。格式样张走 format_preview（只供 render_format_sample 调用，
    命令行不开放），不受项目格式锁限制，构建报告标明是预览；
  * 成品不带身份（门禁 B5，第 4b 步）：清空 python-docx 默认模板留下的作者、备注等文档属性，
    打开 Word 的"保存时从文件属性中删除个人信息"（w:removePersonalInformation，WPS 也认），
    用户在 Word/WPS 里更新目录再保存时不会把电脑账户名写回作者；图片名称改成"图片N"，
    不再是原文件名（文件名可能带公司名）；
  * 构建报告记下每个来源文件出稿时的 sha256（sources），阶段 6 据此核对成品用的就是确认过的中间稿
    （第 4b-2 步）。

INPUT: ordered Markdown files under bid-projects/<project>/output, optional page-header text,
       optional explicit document format (otherwise project-state.json, else preset F1).
OUTPUT: one formatted DOCX (document properties blank, personal-info removal on save) plus
        <output>.build-report.json (format record, source list with each file's sha256 at build time, and
        warnings such as missing images, image hashes and optional visual-manifest hash); native framed modules.
POS: Final delivery builder for the qingtian-bid skill (stage 6) and the format-sample renderer.

Markdown layout markers (HTML comments, invisible in Markdown preview):
  <!-- cover -->              file top: render this file as the centered cover page
  <!-- toc -->                insert 目录 title + Word TOC field (update in Word to fill)
  <!-- notoc -->              next heading renders as a centered bold title outside TOC
                              (used for the three navigation tables)
  <!-- break-all-headings --> file top: every heading in this file starts a new page
                              (commercial documents: 每一章节/小节独立起页)
  <!-- pagebreak -->          force a page break before the next block
  <!-- panel-start --> / <!-- panel-end --> black, unfilled module borders
  <!-- panel-grid-start --> / <!-- panel-end --> continuous frames with paragraph dividers
  <!-- chapter-center -->     center the next native level-one heading
  <!-- gallery-start --> / <!-- gallery-end --> two or three image lines, native cells
  <!-- table-widths: 1,2,3 --> relative widths for the immediately following table
  <!-- table-caption: 表 2-1 检验记录 --> searchable caption above the next table

Page-break rules (mirrors the 湖北中烟 winning sample):
  * each new source file starts on a new page while heading_page_breaks is on
  * Heading 1/2 start a new page while heading_page_breaks is on; Heading 3/4 too when
    break-all-headings is on
  * exception: a heading that directly follows its parent heading stays on the same
    page (e.g. "一、商务文件" + "（一）投标函" share a page, as in the sample)

Heading numbering is expected to be embedded in the heading text itself
(一、 / （一） / 1. / 1.1), exactly as the winning sample does; no Word auto
numbering is stacked on top, so the TOC field renders clean entries.

Images: a standalone Markdown image line `![说明](路径)` inserts the picture
centered and auto-scaled to fit the printable area (relative paths resolve
against the Markdown file's directory). Missing files degrade to a visible
placeholder paragraph instead of crashing, and are listed in the JSON result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from visual_assets import digest, load_visual_assets

from docx_font_profiles import (
    file_sha256,
    heading_font,
    heading_size,
    latin_font_for,
    normalize_document_format,
    preset_format,
    resolve_document_format,
)
from project_cards import find_project_dir, load_json


# 同一进程可能连续生成不同项目；不让一次项目格式污染下一次构建。
# 默认值留空，首次读取时再取默认预设，避免一导入就读预设库。
_ACTIVE_FORMAT: ContextVar[dict | None] = ContextVar("docx_format", default=None)
BLACK = RGBColor(0, 0, 0)
HEADING_STYLE_BY_LEVEL = {
    1: "Heading 1",
    2: "Heading 2",
    3: "Heading 3",
    4: "Heading 4",
    5: "Heading 5",
}
HEADING_PATTERN = re.compile(r"^(#{1,5})\s+(.+)$")
MARKER_PATTERN = re.compile(r"^<!--\s*([a-z-]+)\s*-->$")
# 贪婪匹配到行尾右括号，兼容含括号的文件名（如 ISO9001_00(1).jpg）
IMAGE_PATTERN = re.compile(r"^!\[([^\]]*)\]\((.+)\)$")
TABLE_WIDTHS_PATTERN = re.compile(r"^<!--\s*table-widths:\s*([\d.,\s]+)\s*-->$")
TABLE_CAPTION_PATTERN = re.compile(r"^<!--\s*table-caption:\s*(.+?)\s*-->$")
# 整行加粗（**……**）：用于比五级标题更深的小节题（如 1.4.2.1.1），不进目录
BOLD_LINE_PATTERN = re.compile(r"^\*\*(.+)\*\*$")
# 行内加粗（段落/表格单元格中混排的 **……** 片段）：拆分为加粗 run 渲染
INLINE_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
# 行内代码反引号、删除线等：渲染时剥掉标记，避免 Markdown 泄漏进 DOCX
INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
STRIKETHROUGH_PATTERN = re.compile(r"~~(.+?)~~")
# 水平分割线（Markdown 语法，成品中应忽略）
HORIZONTAL_RULE_PATTERN = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")
# 待补内容进入报告，保持正文格式；最终交付校验会阻止占位内容流出。
ANNOTATION_BRACKET_PATTERN = re.compile(r"^（此处附[:：][^）]{0,60}）$|^【[^】]{1,80}】$")
ANNOTATION_KEYWORDS = ("此处附", "待补充", "待回填", "待核查", "待确认", "需人工", "说明")
# 单星号斜体 `*文字*`：渲染时剥掉星号（成对才剥，避免误伤乘号等孤立星号）
EMPHASIS_PATTERN = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
# 行首「**引导词：**」+ 正文：碎片化清单文风，且离开本渲染器就会漏出星号
LEAD_IN_BOLD_PATTERN = re.compile(r"^\s*(?:[-*+]\s+|\d+[.、]\s*)?\*\*[^*]{1,20}[:：]\*\*\s*\S")
# 中间稿中应避免的 Markdown 痕迹（**加粗** 为合法语法，由渲染器消化，不列入）
# 「不成对的**」改用计数判定（见 has_unpaired_bold）：正则版会把合法整行加粗误报。
MARKDOWN_LEAK_PATTERNS = (
    (re.compile(r"`"), "行内代码反引号`"),
    (re.compile(r"~~.+?~~"), "删除线~~"),
    (re.compile(r"^>\s+", re.MULTILINE), "引用块>"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), "Markdown链接语法"),
    (EMPHASIS_PATTERN, "单星号斜体*"),
)
def active_format() -> dict:
    return _ACTIVE_FORMAT.get() or preset_format()


def format_value(key: str) -> str | float | bool | None:
    return active_format()[key]


def set_run_font(run, size_pt: float, bold: bool = False, font: str | None = None) -> None:
    east_asian_font = font or format_value("body_font")
    latin_font = latin_font_for(active_format(), east_asian_font)
    run.font.name = latin_font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east_asian_font)
    run._element.rPr.rFonts.set(qn("w:cs"), latin_font)
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = BLACK


def set_annotation_font(run) -> None:
    """占位提醒通过报告识别，不以红字破坏全文格式。"""
    set_run_font(run, format_value("body_size_pt"))
    run.font.italic = False


def is_annotation_line(text: str) -> bool:
    """整行被（此处附：…）或【…】包裹且含说明类关键词的，判定为说明性文字。"""
    if not ANNOTATION_BRACKET_PATTERN.match(text):
        return False
    return any(keyword in text for keyword in ANNOTATION_KEYWORDS)


def set_first_line_indent(paragraph) -> None:
    """设置正文首行缩进 2 字符，并保留 twips 回退值以兼容 Word/WPS。"""
    p_pr = paragraph._p.get_or_add_pPr()
    indent = p_pr.find(qn("w:ind"))
    if indent is None:
        indent = OxmlElement("w:ind")
        p_pr.append(indent)
    chars = format_value("first_line_indent_chars")
    indent.set(qn("w:firstLineChars"), str(round(chars * 100)))
    indent.set(qn("w:firstLine"), str(round(chars * format_value("body_size_pt") * 20)))


LINE_RULE_TO_WORD = {
    "multiple": WD_LINE_SPACING.MULTIPLE,
    "exact": WD_LINE_SPACING.EXACTLY,
    "at_least": WD_LINE_SPACING.AT_LEAST,
}


def configure_paragraph_format(
    paragraph_format, before_pt: float = 0, after_pt: float = 0, single: bool = False
) -> None:
    """single=True 用于只含图片的段落：固定值行距会把嵌入图裁成一行高的窄条。"""
    rule = "multiple" if single else format_value("line_spacing_rule")
    value = 1.0 if single else format_value("line_spacing")
    paragraph_format.line_spacing = value if rule == "multiple" else Pt(value)
    paragraph_format.line_spacing_rule = LINE_RULE_TO_WORD[rule]
    paragraph_format.space_before = Pt(before_pt)
    paragraph_format.space_after = Pt(after_pt)


def configure_style(
    style, size_pt: float, bold: bool, before_pt: float = 0, after_pt: float = 0, font: str | None = None
) -> None:
    east_asian_font = font or format_value("body_font")
    latin_font = latin_font_for(active_format(), east_asian_font)
    style.font.name = latin_font
    style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), east_asian_font)
    style._element.rPr.rFonts.set(qn("w:cs"), latin_font)
    for key in list(style._element.rPr.rFonts.attrib):
        if key.endswith("Theme"):
            del style._element.rPr.rFonts.attrib[key]
    style.font.size = Pt(size_pt)
    style.font.bold = bold
    # python-docx 默认模板的 Heading 4 自带斜体，任何预设都不用斜体，显式关掉。
    style.font.italic = False
    style.font.color.rgb = BLACK
    for key in list(style._element.rPr.color.attrib):
        if "theme" in key:
            del style._element.rPr.color.attrib[key]
    configure_paragraph_format(style.paragraph_format, before_pt, after_pt)


def configure_document_styles(document: Document) -> None:
    record = active_format()
    configure_style(document.styles["Normal"], record["body_size_pt"], bold=False)
    for level in range(1, 6):
        configure_style(
            document.styles[f"Heading {level}"], heading_size(record, level), bold=record["heading_bold"],
            before_pt=record["heading_space_before_pt"], after_pt=record["heading_space_after_pt"],
            font=heading_font(record, level),
        )
    # 专用样式让校验器能区分封面/导航题与正文，无须凭文字内容猜用途。
    for name, size_pt, bold, font in (
        ("Bid Cover Title", record["cover_title_size_pt"], True, heading_font(record, 1)),
        ("Bid Cover Info", record["cover_info_size_pt"], False, record["body_font"]),
        ("Bid Navigation Title", heading_size(record, 1), record["heading_bold"], heading_font(record, 1)),
        ("Bid Subheading", heading_size(record, 3), True, heading_font(record, 3)),
    ):
        style = document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style.base_style = document.styles["Normal"]
        # 标题类样式不论是否加粗都保留段前段后；只有封面信息行不留。
        spaced = name != "Bid Cover Info"
        configure_style(style, size_pt, bold,
                        record["heading_space_before_pt"] if spaced else 0,
                        record["heading_space_after_pt"] if spaced else 0, font=font)
    for name in ("Header", "Footer", *(f"TOC {level}" for level in range(1, 6))):
        style = document.styles[name] if name in document.styles else document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        configure_style(style, format_value("header_footer_size_pt" if name in {"Header", "Footer"} else "body_size_pt"), False)
    caption = document.styles.add_style("Bid Figure Caption", WD_STYLE_TYPE.PARAGRAPH)
    caption.base_style = document.styles["Normal"]
    configure_style(caption, record["body_size_pt"], False)
    caption.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER


def configure_page_layout(document: Document) -> None:
    # 不沿用 python-docx 默认的 Letter 页面；页面和图片可打印区域使用同一配置。
    for section in document.sections:
        section.page_width = Cm(format_value("page_width_cm"))
        section.page_height = Cm(format_value("page_height_cm"))
        for side in ("top", "bottom", "left", "right"):
            setattr(section, f"{side}_margin", Cm(format_value(f"margin_{side}_cm")))


def set_page_break_before(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    if p_pr.find(qn("w:pageBreakBefore")) is None:
        p_pr.append(OxmlElement("w:pageBreakBefore"))


def add_field_runs(
    paragraph, instruction: str, placeholder: str, size_pt: int,
    annotation_placeholder: bool = False,
) -> None:
    """Insert a Word field (e.g. PAGE / TOC) marked dirty so Word refreshes it on open."""
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin.set(qn("w:dirty"), "true")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")

    for element in (begin, instr, separate):
        run = paragraph.add_run()
        set_run_font(run, size_pt)
        run._element.append(element)
    if placeholder:
        placeholder_run = paragraph.add_run(placeholder)
        if annotation_placeholder:
            set_annotation_font(placeholder_run)
        else:
            set_run_font(placeholder_run, size_pt)
    end_run = paragraph.add_run()
    set_run_font(end_run, size_pt)
    end_run._element.append(end)


def configure_header_footer(document: Document, header_text: str) -> None:
    if format_value("blind_mode"):
        # 暗标不设页眉、页脚、页码；不访问 header/footer，以免生成空的页眉页脚部件。
        if header_text:
            raise ValueError("暗标模式不得设置页眉文字")
        return
    section = document.sections[0]
    if header_text:
        header_paragraph = section.header.paragraphs[0]
        header_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        header_paragraph.paragraph_format.space_before = Pt(0)
        header_paragraph.paragraph_format.space_after = Pt(0)
        run = header_paragraph.add_run(header_text)
        configure_paragraph_format(header_paragraph.paragraph_format)
        set_run_font(run, format_value("header_footer_size_pt"))
    footer_paragraph = section.footer.paragraphs[0]
    footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_paragraph.paragraph_format.space_before = Pt(0)
    footer_paragraph.paragraph_format.space_after = Pt(0)
    configure_paragraph_format(footer_paragraph.paragraph_format)
    if format_value("require_page_numbers"):
        add_field_runs(footer_paragraph, "PAGE", "1", format_value("header_footer_size_pt"))


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


def add_inline_runs(
    paragraph, text: str, size_pt: float, base_bold: bool = False, font: str | None = None
) -> None:
    """按行内 **加粗** 标记拆分为多个 run；顺带清洗反引号/删除线/链接等泄漏标记。"""
    text = clean_inline_markdown(text)
    position = 0
    for match in INLINE_BOLD_PATTERN.finditer(text):
        if match.start() > position:
            run = paragraph.add_run(text[position:match.start()])
            set_run_font(run, size_pt, bold=base_bold, font=font)
        run = paragraph.add_run(match.group(1))
        set_run_font(run, size_pt, bold=True, font=font)
        position = match.end()
    if position < len(text):
        run = paragraph.add_run(text[position:])
        set_run_font(run, size_pt, bold=base_bold, font=font)


def set_table_geometry(table, widths: list[float], *, repeat_header: bool = True) -> None:
    """Fix grid and cell widths together: Word otherwise reflows long Chinese columns."""
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    total = format_value("page_width_cm") - format_value("margin_left_cm") - format_value("margin_right_cm")
    for column, weight in zip(table.columns, widths):
        column.width = Cm(total * weight / sum(widths))
    for row in table.rows:
        for cell, weight in zip(row.cells, widths):
            cell.width = Cm(total * weight / sum(widths))
            for shade in list(cell._tc.get_or_add_tcPr().findall(qn("w:shd"))):
                shade.getparent().remove(shade)
        # A single exceptionally long data row must be able to span pages; galleries
        # are bounded in height separately and must keep picture and caption together.
    if repeat_header:
        table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        edge = OxmlElement(f"w:{side}")
        for key, value in (("val", "single"), ("sz", "4"), ("color", "000000")):
            edge.set(qn(f"w:{key}"), value)
        borders.append(edge)
    table._tbl.tblPr.append(borders)


def add_table(document: Document, rows: list[list[str]], widths: list[float] | None = None) -> None:
    if not rows:
        return
    column_count = max(len(row) for row in rows)
    if widths is not None and (len(widths) != column_count or any(x <= 0 for x in widths)):
        raise ValueError("table-widths 的列数须与表格一致，且每列权重必须大于零")
    table = document.add_table(rows=len(rows), cols=column_count)
    table.style = "Table Grid"
    set_table_geometry(table, widths or [1.0] * column_count)
    for row_index, row in enumerate(rows):
        for column_index in range(column_count):
            cell = table.cell(row_index, column_index)
            text = row[column_index] if column_index < len(row) else ""
            paragraph = cell.paragraphs[0]
            paragraph.style = document.styles["Normal"]
            configure_paragraph_format(paragraph.paragraph_format)
            add_inline_runs(paragraph, text, format_value("body_size_pt"), base_bold=(row_index == 0))


def add_caption(container, text: str, *, keep_next: bool = False):
    paragraph = container.add_paragraph(style="Bid Figure Caption")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    configure_paragraph_format(paragraph.paragraph_format)
    paragraph.paragraph_format.keep_together = True
    paragraph.paragraph_format.keep_with_next = keep_next
    add_inline_runs(paragraph, text, format_value("body_size_pt"))
    return paragraph


def decorate_panel(elements, *, grid: bool = False) -> None:
    """Borders leave Heading paragraphs in the document body, preserving TOC/gate discovery."""
    for element in elements:
        if element.tag != qn("w:p"):
            continue
        p_pr = element.get_or_add_pPr()
        borders = OxmlElement("w:pBdr")
        # Keep the paragraph indents from the selected format. Zero border spacing
        # keeps adjoining frames continuous and aligned with full-width tables.
        for side in ("top", "left", "bottom", "right", "between"):
            edge = OxmlElement(f"w:{side}")
            for key, value in (("val", "nil" if side == "between" and not grid else "single"),
                               ("sz", "4"), ("space", "0"), ("color", "000000")):
                edge.set(qn(f"w:{key}"), value)
            borders.append(edge)
        p_pr.append(borders)


def add_body_paragraph(
    document: Document, text: str, page_break_before: bool = False, bold: bool = False
):
    paragraph = document.add_paragraph(style="Bid Subheading" if bold else "Normal")
    if not bold:
        configure_paragraph_format(paragraph.paragraph_format)
    # 仅常规正文缩进；整行加粗的小节题、表格、标题和占位说明均顶格。
    if not bold:
        set_first_line_indent(paragraph)
    if page_break_before:
        set_page_break_before(paragraph)
    if bold:
        # 整行加粗的小节题按三级标题的字体和字号排。
        record = active_format()
        add_inline_runs(paragraph, text.strip(), heading_size(record, 3), base_bold=True,
                        font=heading_font(record, 3))
    else:
        add_inline_runs(paragraph, text.strip(), format_value("body_size_pt"))
    return paragraph


def add_annotation_paragraph(document: Document, text: str, page_break_before: bool = False):
    """待补占位段保持正文格式，由最终交付校验阻止遗漏。"""
    paragraph = document.add_paragraph(style="Normal")
    configure_paragraph_format(paragraph.paragraph_format)
    if page_break_before:
        set_page_break_before(paragraph)
    run = paragraph.add_run(text.strip())
    set_annotation_font(run)
    return paragraph


def add_heading(document: Document, text: str, level: int, page_break_before: bool):
    paragraph = document.add_paragraph(style=HEADING_STYLE_BY_LEVEL[level])
    if page_break_before:
        set_page_break_before(paragraph)
    # 字体、字号、加粗只放在标题样式里，不加直接格式：Word 更新目录时会把标题文字直接设的字体
    # 复制进目录条目（实测字号、加粗不复制），标题字体与正文不同的预设（F3～F5）目录会排成标题字体。
    paragraph.add_run(strip_markdown_marks(text))
    return paragraph
    return paragraph


def add_plain_title(document: Document, text: str, page_break_before: bool) -> None:
    """导航表标题使用专用样式，不进入目录域。"""
    paragraph = document.add_paragraph(style="Bid Navigation Title")
    configure_paragraph_format(
        paragraph.paragraph_format,
        before_pt=format_value("heading_space_before_pt"),
        after_pt=format_value("heading_space_after_pt"),
    )
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if page_break_before:
        set_page_break_before(paragraph)
    run = paragraph.add_run(strip_markdown_marks(text))
    set_run_font(run, format_value("heading1_size_pt"), bold=format_value("heading_bold"),
                 font=format_value("heading1_font"))


def add_image(
    document: Document,
    image_path: Path,
    caption: str,
    page_break_before: bool,
    warnings: list[str],
    image_bytes: bytes | None = None,
) -> bool:
    """居中插入图片并按可打印区域等比缩放；文件缺失时降级为占位段落。"""
    paragraph = document.add_paragraph(style="Normal")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    configure_paragraph_format(paragraph.paragraph_format, before_pt=6, after_pt=6)
    if page_break_before:
        set_page_break_before(paragraph)
    if not image_path.exists():
        warnings.append(f"图片未找到: {image_path}")
        run = paragraph.add_run(f"【图片待补充：{caption or image_path.name}】")
        set_annotation_font(run)
        return False
    try:
        run = paragraph.add_run()
        width = format_value("page_width_cm") - format_value("margin_left_cm") - format_value("margin_right_cm")
        # Reserve room for the caption; keep the image and its searchable caption together.
        height = format_value("page_height_cm") - format_value("margin_top_cm") - format_value("margin_bottom_cm") - 2.5
        picture = run.add_picture(BytesIO(image_bytes) if image_bytes is not None else str(image_path), width=Cm(width))
        neutral_picture_name(picture)
        max_height = Cm(height)
        if picture.height > max_height:
            scale = max_height / picture.height
            picture.width = int(picture.width * scale)
            picture.height = max_height
        configure_paragraph_format(paragraph.paragraph_format, before_pt=6, after_pt=6, single=True)
        if caption:
            paragraph.paragraph_format.keep_with_next = True
            add_caption(document, caption)
        return True
    except Exception as exc:  # 图片损坏/格式不支持时不中断整份文档生成
        warnings.append(f"图片插入失败: {image_path} ({exc})")
        run = paragraph.add_run(f"【图片插入失败，请在 Word 中手动插入：{image_path.name}】")
        set_annotation_font(run)
        return False


def neutral_picture_name(picture) -> None:
    """python-docx 把原文件名写进图片名称（pic:cNvPr），评审系统读得到；改成"图片N"。没有公开接口，只能走 _inline。"""
    inline = picture._inline
    name = f"图片{inline.docPr.get('id')}"
    inline.docPr.set("name", name)
    for node in inline.xpath(".//pic:cNvPr"):
        node.set("name", name)


def scrub_document_properties(document: Document) -> None:
    """清空默认模板的作者（python-docx）、备注（generated by python-docx）等属性，并打开保存时删除个人信息。

    w:removePersonalInformation 按 CT_Settings 的顺序放在 writeProtection、view、zoom 之后。
    """
    core = document.core_properties
    for name in ("author", "last_modified_by", "title", "subject", "keywords", "comments", "category",
                 "content_status", "identifier"):
        setattr(core, name, "")
    settings = document.settings.element
    if settings.find(qn("w:removePersonalInformation")) is not None:
        return
    flag = OxmlElement("w:removePersonalInformation")
    anchor = next((settings.find(qn(tag)) for tag in ("w:zoom", "w:view", "w:writeProtection")
                   if settings.find(qn(tag)) is not None), None)
    if anchor is None:
        settings.insert(0, flag)
    else:
        anchor.addnext(flag)


def add_page_break_paragraph(document: Document) -> None:
    paragraph = document.add_paragraph(style="Normal")
    configure_paragraph_format(paragraph.paragraph_format)
    run = paragraph.add_run()
    set_run_font(run, format_value("body_size_pt"))
    run.add_break(WD_BREAK.PAGE)


def strip_markdown_marks(text: str) -> str:
    """去掉常见 Markdown 标记，避免封面/标题/直排文本原样漏出。

    正文段落的 **加粗** 由 add_inline_runs 单独处理；本函数用于封面、标题
    等整段直排文本，以及最终兜底清洗。
    """
    text = re.sub(r"^\s*#{1,6}\s+", "", text)
    text = INLINE_CODE_PATTERN.sub(r"\1", text)
    text = STRIKETHROUGH_PATTERN.sub(r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    return text.strip()


def clean_inline_markdown(text: str) -> str:
    """清洗正文/表格单元格中除 **加粗** 以外的 Markdown 痕迹。

    单星号斜体 `*文字*` 此前未清洗，会把星号原样带进 DOCX（如 `*保密承诺：*`）。
    加粗由 add_inline_runs 拆 run 处理，故此处只剥单星号，不动 `**`。
    """
    text = INLINE_CODE_PATTERN.sub(r"\1", text)
    text = STRIKETHROUGH_PATTERN.sub(r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = EMPHASIS_PATTERN.sub(r"\1", text)
    return text


def has_unpaired_bold(text: str) -> bool:
    """行内 `**` 个数为奇数即不成对，会导致加粗渲染错位、星号外漏。

    注意：整行加粗 `**小节题**` 是合法写法（两个标记，偶数），不得误报。
    """
    return text.count("**") % 2 == 1


def detect_markdown_leaks(text: str) -> list[str]:
    """检测成品正文中不应残留的 Markdown 痕迹，返回命中说明列表。"""
    hits: list[str] = []
    for pattern, label in MARKDOWN_LEAK_PATTERNS:
        if pattern.search(text):
            hits.append(label)
    if has_unpaired_bold(text):
        hits.append("不成对的**标记")
    return hits


def add_cover_page(document: Document, lines: list[str]) -> None:
    """封面采用项目配置，避免历史样本大字号覆盖采购格式。"""
    for line in lines:
        text = strip_markdown_marks(line)
        if not text:
            continue
        paragraph = document.add_paragraph(style="Normal")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        compact = text.replace("　", "").replace(" ", "")
        # 主标题：以"投标文件"开头且非"XX：YY"信息项（如"投标文件""投标文件（技术部分）"）
        is_cover_title = (
            compact.startswith("投标文件") and "：" not in compact and ":" not in compact
        )
        if is_cover_title:
            paragraph.style = document.styles["Bid Cover Title"]
            run = paragraph.add_run(text)
            set_run_font(run, format_value("cover_title_size_pt"), bold=True,
                         font=format_value("heading1_font"))
        else:
            paragraph.style = document.styles["Bid Cover Info"]
            run = paragraph.add_run(text)
            set_run_font(run, format_value("cover_info_size_pt"), bold=False)


def add_toc_block(document: Document, page_break_before: bool) -> None:
    add_plain_title(document, "目　录", page_break_before)
    paragraph = document.add_paragraph(style="Normal")
    configure_paragraph_format(paragraph.paragraph_format)
    add_field_runs(
        paragraph,
        'TOC \\o "1-5" \\h \\z \\u',
        "【目录域：在 Word/WPS 中全选后按 F9 或右键「更新域」生成带页码目录】",
        format_value("body_size_pt"),
        annotation_placeholder=True,
    )


class MarkdownRenderer:
    """把一组 Markdown 文件渲染进同一个 Document，维护跨文件的分页状态。"""

    def __init__(self, document: Document, visual_manifest: Path | None = None):
        self.document = document
        self.pending_break = False
        self.last_heading_level: int | None = None  # 上一个渲染块若是标题则记录级别
        self.rendered_any_block = False
        self.warnings: list[str] = []
        self.assets = load_visual_assets(visual_manifest) if visual_manifest else None
        self.image_sources: list[dict] = []
        self.active_heading: str | None = None

    def _image_input(self, markdown_path: Path, line: str) -> tuple[Path, str, bytes | None]:
        match = IMAGE_PATTERN.fullmatch(line.strip())
        if match is None:
            raise ValueError("组图内只允许独立的 Markdown 图片行")
        caption, raw_path = match.group(1), match.group(2).strip()
        path = (markdown_path.parent / raw_path).resolve()
        data = path.read_bytes() if path.is_file() else None
        sha = hashlib.sha256(data).hexdigest() if data is not None else None
        if self.assets is not None:
            asset = self.assets.get(path)
            if asset is None or asset["caption"] != caption or asset["sha256"] != sha:
                raise ValueError(f"图片未登记、图题不一致或检查后被替换：{path.name}")
            required_section = asset["required_section"]
            if required_section and self.active_heading != required_section:
                raise ValueError(f"图片未放在计划小节“{required_section}”：{path.name}")
            if required_section and any(entry["file"] == str(path) for entry in self.image_sources):
                raise ValueError(f"同一必需配图重复插入：{path.name}")
        if data is not None:
            self.image_sources.append({"file": str(path), "sha256": sha, "caption": caption})
        return path, caption, data

    def _gallery(self, markdown_path: Path, lines: list[str]) -> None:
        if self.assets is None:
            raise ValueError("组图须提供 visual_manifest，完成图片登记与检查")
        images = [self._image_input(markdown_path, line) for line in lines if line.strip()]
        if len(images) not in (2, 3):
            raise ValueError("一组图片须为 2 或 3 张；更多图片拆成多组")
        table = self.document.add_table(rows=1, cols=len(images))
        set_table_geometry(table, [1.0] * len(images), repeat_header=False)
        table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        pending_break = self._consume_break()
        for cell, (path, caption, data) in zip(table.rows[0].cells, images):
            paragraph = cell.paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            configure_paragraph_format(paragraph.paragraph_format, single=True)
            if pending_break:
                set_page_break_before(paragraph)
            paragraph.paragraph_format.keep_with_next = True
            picture = paragraph.add_run().add_picture(BytesIO(data), width=cell.width - Cm(0.4))
            neutral_picture_name(picture)
            if picture.height > Cm(4.2):
                picture.width = round(picture.width * Cm(4.2) / picture.height)
                picture.height = Cm(4.2)
            add_caption(cell, caption)
        self.rendered_any_block = True
        self.last_heading_level = None

    def _consume_break(self) -> bool:
        pending = self.pending_break
        self.pending_break = False
        return pending

    def _heading_needs_break(self, level: int, break_all: bool) -> bool:
        # 紧跟父级标题的子标题与父级同页（样本："一、商务文件"+"（一）投标函"同页）
        follows_parent = (
            self.last_heading_level is not None and self.last_heading_level < level
        )
        default_break = (level <= 2 and format_value("heading_page_breaks")) or break_all
        return default_break and not follows_parent

    def render_file(self, markdown_path: Path, is_first_file: bool) -> None:
        self.active_heading = None
        lines = markdown_path.read_text(encoding="utf-8").splitlines()
        markers = {
            MARKER_PATTERN.match(line.strip()).group(1)
            for line in lines[:5]
            if MARKER_PATTERN.match(line.strip())
        }
        if "cover" in markers:
            add_cover_page(self.document, [
                line for line in lines if not MARKER_PATTERN.match(line.strip())
            ])
            self.rendered_any_block = True
            self.last_heading_level = None
            self.pending_break = True
            return

        break_all = "break-all-headings" in markers
        # 施组有篇幅上限：关闭标题分页时，新文件接着排，不另起一页。
        if not is_first_file and (format_value("heading_page_breaks") or break_all):
            self.pending_break = True
        notoc_next_heading = False
        center_chapter = False
        panel_start = None
        panel_grid = False
        table_widths = None
        table_caption = None

        index = 0
        while index < len(lines):
            line = lines[index].rstrip()
            stripped = line.strip()
            if not stripped:
                index += 1
                continue

            if stripped == "<!-- chapter-center -->":
                center_chapter = True
                index += 1
                continue

            if stripped == "<!-- gallery-start -->":
                end = next((n for n in range(index + 1, len(lines))
                            if lines[n].strip() == "<!-- gallery-end -->"), None)
                if end is None:
                    raise ValueError("gallery-start 缺少 gallery-end")
                self._gallery(markdown_path, lines[index + 1:end])
                index = end + 1
                continue
            if stripped == "<!-- gallery-end -->":
                raise ValueError("gallery-end 缺少 gallery-start")
            if stripped in {"<!-- panel-start -->", "<!-- panel-grid-start -->"}:
                if panel_start is not None:
                    raise ValueError("panel 不支持嵌套")
                panel_start = len(self.document._element.body) - 1
                panel_grid = stripped == "<!-- panel-grid-start -->"
                index += 1
                continue
            if stripped == "<!-- panel-end -->":
                if panel_start is None:
                    raise ValueError("panel-end 缺少 panel-start")
                decorate_panel(list(self.document._element.body)[panel_start:-1], grid=panel_grid)
                panel_start = None
                index += 1
                continue
            width_match = TABLE_WIDTHS_PATTERN.fullmatch(stripped)
            if width_match:
                table_widths = [float(x.strip()) for x in width_match.group(1).split(",")]
                index += 1
                continue
            caption_match = TABLE_CAPTION_PATTERN.fullmatch(stripped)
            if caption_match:
                table_caption = caption_match.group(1)
                index += 1
                continue
            if stripped.startswith(("<!-- table-widths", "<!-- table-caption")):
                raise ValueError("表格版式标记格式错误")
            if (table_widths is not None or table_caption is not None) and markdown_table_rows(lines, index) is None:
                raise ValueError("表题与列宽标记后必须紧跟表格")

            # Markdown 水平分割线不进入成品
            if HORIZONTAL_RULE_PATTERN.match(stripped):
                index += 1
                continue

            # 引用块 > 前缀剥掉后按正文渲染，并记入泄漏警告
            if stripped.startswith(">"):
                stripped = stripped.lstrip(">").strip()
                line = stripped
                self.warnings.append(
                    f"Markdown引用块已降级为正文（请改写成标书段落）: {markdown_path.name}"
                )
                if not stripped:
                    index += 1
                    continue

            marker_match = MARKER_PATTERN.match(stripped)
            if marker_match:
                marker = marker_match.group(1)
                if marker == "pagebreak":
                    self.pending_break = True
                elif marker == "notoc":
                    notoc_next_heading = True
                elif marker == "toc":
                    if format_value("require_toc"):
                        add_toc_block(self.document, self._consume_break())
                        self.rendered_any_block = True
                        self.last_heading_level = None
                # cover/break-all-headings 已在文件级处理
                index += 1
                continue

            table_result = markdown_table_rows(lines, index)
            if table_result:
                rows, index = table_result
                pending_break = self._consume_break()
                if table_caption:
                    paragraph = add_caption(self.document, table_caption, keep_next=True)
                    if pending_break:
                        set_page_break_before(paragraph)
                elif pending_break:
                    add_page_break_paragraph(self.document)
                add_table(self.document, rows, table_widths)
                table_widths, table_caption = None, None
                self.rendered_any_block = True
                self.last_heading_level = None
                continue

            image_match = IMAGE_PATTERN.match(stripped)
            if image_match:
                image_path, caption, image_bytes = self._image_input(markdown_path, stripped)
                added = add_image(
                    self.document,
                    image_path,
                    caption,
                    page_break_before=self._consume_break(),
                    warnings=self.warnings,
                    image_bytes=image_bytes,
                )
                if self.assets is not None and not added:
                    raise ValueError(f"已登记的图片无法嵌入：{image_path.name}")
                self.rendered_any_block = True
                self.last_heading_level = None
                index += 1
                continue

            heading_match = HEADING_PATTERN.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2)
                needs_break = self._consume_break() or (
                    self.rendered_any_block and self._heading_needs_break(level, break_all)
                )
                if notoc_next_heading:
                    add_plain_title(self.document, text, needs_break)
                    notoc_next_heading = False
                    self.last_heading_level = None
                else:
                    paragraph = add_heading(self.document, text, level, needs_break)
                    self.active_heading = strip_markdown_marks(text)
                    if center_chapter and level == 1:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        center_chapter = False
                    self.last_heading_level = level
                self.rendered_any_block = True
            else:
                # 无序列表标记剥掉后按正文渲染（写作规则要求成段论述，列表应改写为（1）（2））
                if re.match(r"^[-*+]\s+", line):
                    text = re.sub(r"^[-*+]\s+", "", line)
                    warning = (
                        f"Markdown列表标记已降级为正文（请改写成（1）（2）成段论述）: "
                        f"{markdown_path.name}"
                    )
                    if warning not in self.warnings:
                        self.warnings.append(warning)
                else:
                    text = line
                bold_match = BOLD_LINE_PATTERN.match(stripped)
                # 对即将写入的正文做泄漏检测（清洗前），便于作者回改中间稿
                for leak in detect_markdown_leaks(text):
                    warning = f"Markdown痕迹[{leak}]: {markdown_path.name}"
                    if warning not in self.warnings:
                        self.warnings.append(warning)
                if is_annotation_line(stripped):
                    add_annotation_paragraph(
                        self.document,
                        strip_markdown_marks(stripped),
                        page_break_before=self._consume_break(),
                    )
                elif bold_match:
                    add_body_paragraph(
                        self.document,
                        bold_match.group(1),
                        page_break_before=self._consume_break(),
                        bold=True,
                    )
                else:
                    add_body_paragraph(
                        self.document, text, page_break_before=self._consume_break()
                    )
                self.rendered_any_block = True
                self.last_heading_level = None
            index += 1
        if panel_start is not None or table_widths is not None or table_caption is not None or center_chapter:
            raise ValueError("版式标记未闭合或表格缺失")


def save_document_version(document: Document, output_path: Path) -> Path:
    """先完整写入临时文件，再替换；保留备份，Word/WPS 占用时另存版本。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    if output_path.exists():
        backup = output_path.with_name(f"{output_path.stem}.backup-{stamp}.docx")
        shutil.copy2(output_path, backup)
    lock = output_path.with_name(f"~${output_path.name}")
    if lock.exists():
        output_path = output_path.with_name(f"{output_path.stem}-更新版-{stamp}.docx")
    with tempfile.NamedTemporaryFile(dir=output_path.parent, suffix=".docx", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        document.save(temporary)
        try:
            os.replace(temporary, output_path)
        except PermissionError:
            output_path = output_path.with_name(f"{output_path.stem}-更新版-{stamp}.docx")
            os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path


def build_response_docx(
    markdown_files: list[Path],
    output_path: Path,
    header_text: str = "",
    document_format: dict | None = None,
    *,
    format_preview: bool = False,
    visual_manifest: Path | None = None,
) -> dict:
    output_path = output_path.expanduser().resolve()
    if format_preview:
        # 样张在格式确认前生成，必须绕开项目格式锁；只接受显式传入的格式。
        if document_format is None:
            raise ValueError("格式预览必须显式传入格式")
        selected_format = normalize_document_format(document_format)
    else:
        selected_format = resolve_document_format(output_path, document_format)
        project = find_project_dir(output_path)
        if project is not None:
            planned = project / "analysis" / "visual-assets.json"
            if planned.is_file() and load_json(planned, "图片清单").get("required_jobs"):
                if visual_manifest is not None and visual_manifest.resolve() != planned:
                    raise ValueError("必需配图须采用项目的 analysis/visual-assets.json")
                visual_manifest = planned
    format_token = _ACTIVE_FORMAT.set(selected_format)
    try:
        document = Document()
        scrub_document_properties(document)
        configure_document_styles(document)
        configure_page_layout(document)
        configure_header_footer(document, header_text)
        visual_manifest = visual_manifest.resolve() if visual_manifest else None
        visual_manifest_sha = digest(visual_manifest) if visual_manifest else None
        renderer = MarkdownRenderer(document, visual_manifest)
        for position, markdown_file in enumerate(markdown_files):
            resolved = markdown_file.expanduser().resolve()
            if not resolved.exists():
                raise FileNotFoundError(f"响应文件不存在: {resolved}")
            renderer.render_file(resolved, is_first_file=(position == 0))
        if renderer.assets is not None:
            used = {Path(entry["file"]) for entry in renderer.image_sources}
            if used != set(renderer.assets):
                raise ValueError("图文清单含未插入正文的图片，须核对组装清单与图片落点")
            if digest(visual_manifest) != visual_manifest_sha:
                raise ValueError("构建期间图文清单发生变化，须重新检查")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path = save_document_version(document, output_path)
        result = {
            "output": str(output_path),
            "header": header_text,
            "preset": selected_format["preset"],
            "format_preview": format_preview,
            "document_format": selected_format,
            "docx_sha256": file_sha256(output_path),
            "source_files": [str(path) for path in markdown_files],
            "sources": [{"file": str(path.expanduser().resolve()), "sha256": file_sha256(path.expanduser().resolve())}
                        for path in markdown_files],
            "warnings": renderer.warnings,
            "image_sources": renderer.image_sources,
            "visual_manifest": ({"file": str(visual_manifest), "sha256": visual_manifest_sha}
                                if visual_manifest else None),
        }
        # 构建结果落盘：图片待补等警告供 validate_bid_package.py 汇总进"人工核查清单"
        report_path = output_path.with_suffix(".build-report.json")
        try:
            report_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            renderer.warnings.append(f"构建报告写入失败: {report_path} ({exc})")
        return result
    finally:
        _ACTIVE_FORMAT.reset(format_token)


def load_manifest(manifest_path: Path) -> tuple[list[Path], str]:
    """读取 JSON 组装清单：{"header": "...", "files": ["相对/绝对路径", ...]}。

    files 中的相对路径相对于清单文件所在目录解析，保证清单可随项目目录整体移动。
    """
    manifest_path = manifest_path.expanduser().resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"组装清单读取失败: {manifest_path} ({exc})")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit(f"组装清单缺少非空 files 列表: {manifest_path}")
    base_dir = manifest_path.parent
    resolved_files = []
    for entry in files:
        entry_path = Path(entry)
        resolved_files.append(entry_path if entry_path.is_absolute() else base_dir / entry_path)
    return resolved_files, str(manifest.get("header", ""))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the formatted 施工组织设计 DOCX (format from project-state.json, else preset F1)."
    )
    parser.add_argument("--output", type=Path, required=True, help="Final DOCX path.")
    parser.add_argument("--visual-manifest", type=Path, help="已检查的 visual-assets.json；组图必需。")
    parser.add_argument(
        "--header",
        default="",
        help="Page-header text shown on every page (usually 项目名称+投标文件).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="JSON 组装清单（含 header 与按序 files），与直接列出 Markdown 文件二选一.",
    )
    parser.add_argument("markdown_files", type=Path, nargs="*", help="Ordered Markdown source files.")
    args = parser.parse_args()
    if bool(args.manifest) == bool(args.markdown_files):
        parser.error("--manifest 与 Markdown 文件列表必须二选一")
    return args


def main() -> int:
    args = parse_args()
    visual_manifest = args.visual_manifest
    if args.manifest:
        args.manifest = args.manifest.expanduser().resolve()
        markdown_files, manifest_header = load_manifest(args.manifest)
        header_text = args.header or manifest_header
        if visual_manifest is None:
            entry = json.loads(args.manifest.read_text(encoding="utf-8")).get("visual_manifest")
            if entry is not None:
                if not isinstance(entry, str) or not entry.strip():
                    raise SystemExit("组装清单 visual_manifest 必须是非空路径字符串")
                visual_manifest = args.manifest.parent / entry
    else:
        markdown_files, header_text = args.markdown_files, args.header
    try:
        result = build_response_docx(
            markdown_files, args.output, header_text, visual_manifest=visual_manifest
        )
    except (OSError, ValueError) as exc:
        print(f"DOCX 生成失败: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
