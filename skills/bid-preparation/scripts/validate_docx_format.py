"""Validate final DOCX formatting against bid response requirements.

INPUT: final DOCX response file (built by build_response_docx.py).
OUTPUT: validation result with blocker/warning issues and optional JSON/MD report.
POS: DOCX format gate for the bid-preparation skill (stage 6/7).

Checks (aligned with the 湖北中烟 winning-sample layout):
  * styles: 宋体 / 小四 body / 四号 H1 / bold headings / black / 1.5 line / 8pt spacing
  * page: A4 size declared in sectPr
  * pagination: Heading 1/2 start a new page unless directly following a parent
    heading, and the document contains page breaks at all
  * header/footer: page header text exists, footer carries a PAGE field
  * TOC: document contains a Word TOC field for the 目录 page
  * heading numbering: heading text carries its own number (一、/（一）/1./1.1),
    matching the sample; unnumbered headings are reported as warnings
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"
EXPECTED_FONT = "宋体"
BODY_SIZE = "24"       # 小四 = 12pt = 24 half-points
HEADING1_SIZE = "28"   # 四号 = 14pt
LINE_SPACING = "360"   # 1.5 倍
HEADING_SPACING = "160"  # 8 磅
A4_WIDTH_TWIPS = 11906
A4_HEIGHT_TWIPS = 16838
HEADING_STYLE_LEVELS = {"Heading1": 1, "Heading2": 2, "Heading3": 3, "Heading4": 4}
# 标题文本自带编号（一、 / （一） / 1. / 1.1 / （1） / 附件12-1 / 附：），与中标样本一致
SELF_NUMBERED_PATTERN = re.compile(
    r"^\s*(?:"
    r"[（(][一二三四五六七八九十百]+[）)]"
    r"|[一二三四五六七八九十百]+[、.．]"
    r"|[（(]\d+[）)]"
    r"|\d+(?:[.．]\d+)*[.．、]?"
    r"|附件?\s*\d"
    r"|附[:：]"
    r")"
)


def issue(issues: list[dict], level: str, message: str, target: str) -> None:
    issues.append({"level": level, "message": message, "target": target})


def read_member(package: zipfile.ZipFile, member: str) -> ElementTree.Element | None:
    try:
        return ElementTree.fromstring(package.read(member))
    except KeyError:
        return None


def find_style(styles_root: ElementTree.Element, style_id: str) -> ElementTree.Element | None:
    return styles_root.find(f".//w:style[@w:styleId='{style_id}']", NS)


def attr(node: ElementTree.Element | None, name: str) -> str | None:
    return None if node is None else node.get(f"{W}{name}")


def paragraph_text(paragraph: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))


def check_common_style(
    style: ElementTree.Element | None,
    style_name: str,
    expected_size: str,
    bold: bool,
    heading: bool,
    issues: list[dict],
) -> None:
    if style is None:
        issue(issues, "blocker", f"缺少 Word 样式: {style_name}", style_name)
        return
    r_fonts = style.find(".//w:rFonts", NS)
    east_asia_font = attr(r_fonts, "eastAsia")
    ascii_font = attr(r_fonts, "ascii")
    if EXPECTED_FONT not in {east_asia_font, ascii_font}:
        issue(issues, "blocker", f"{style_name} 未设置为宋体", style_name)
    size = attr(style.find(".//w:sz", NS), "val")
    if size != expected_size:
        issue(issues, "blocker", f"{style_name} 字号不符合要求", style_name)
    color = attr(style.find(".//w:color", NS), "val")
    if color not in {"000000", "auto"}:
        issue(issues, "blocker", f"{style_name} 字体颜色不是黑色", style_name)
    spacing = style.find(".//w:spacing", NS)
    if attr(spacing, "line") != LINE_SPACING:
        issue(issues, "blocker", f"{style_name} 行距不是 1.5 倍", style_name)
    if heading:
        if style.find(".//w:b", NS) is None and bold:
            issue(issues, "blocker", f"{style_name} 未加粗", style_name)
        if attr(spacing, "before") != HEADING_SPACING or attr(spacing, "after") != HEADING_SPACING:
            issue(issues, "blocker", f"{style_name} 段前段后不是 8 磅", style_name)


def check_page_size(document_root: ElementTree.Element, issues: list[dict]) -> None:
    page_size = document_root.find(".//w:sectPr/w:pgSz", NS)
    if page_size is None:
        issue(issues, "blocker", "未声明页面尺寸（应为 A4）", "sectPr")
        return
    width, height = attr(page_size, "w"), attr(page_size, "h")
    if width != str(A4_WIDTH_TWIPS) or height != str(A4_HEIGHT_TWIPS):
        issue(issues, "blocker", f"页面尺寸不是 A4（当前 {width}x{height} twips）", "sectPr")


def check_pagination_and_numbering(document_root: ElementTree.Element, issues: list[dict]) -> None:
    body = document_root.find("w:body", NS)
    if body is None:
        issue(issues, "blocker", "document.xml 缺少 body", "document.xml")
        return
    page_break_count = 0
    previous_heading_level: int | None = None
    seen_any_heading = False
    for element in body:
        if element.tag != f"{W}p":
            previous_heading_level = None  # 表格等其他块打断"紧跟父级标题"关系
            continue
        p_pr = element.find("w:pPr", NS)
        has_break_before = p_pr is not None and p_pr.find("w:pageBreakBefore", NS) is not None
        has_run_break = any(
            br.get(f"{W}type") == "page" for br in element.findall(".//w:br", NS)
        )
        if has_break_before or has_run_break:
            page_break_count += 1
        style_value = attr(None if p_pr is None else p_pr.find("w:pStyle", NS), "val")
        level = HEADING_STYLE_LEVELS.get(style_value or "")
        if level is None:
            previous_heading_level = None
            continue
        text = paragraph_text(element).strip()
        follows_parent = previous_heading_level is not None and previous_heading_level < level
        if level <= 2 and seen_any_heading and not follows_parent and not has_break_before:
            issue(issues, "blocker", f"标题未独立起页: {text[:30]}", style_value)
        if not SELF_NUMBERED_PATTERN.match(text):
            issue(issues, "warning", f"标题文本未携带编号: {text[:30]}", style_value)
        previous_heading_level = level
        seen_any_heading = True
    if page_break_count == 0:
        issue(issues, "blocker", "全文没有任何分页符，章节未独立起页", "document.xml")


def check_toc_field(document_root: ElementTree.Element, issues: list[dict]) -> None:
    instructions = [node.text or "" for node in document_root.findall(".//w:instrText", NS)]
    if not any("TOC" in instruction for instruction in instructions):
        issue(issues, "blocker", "缺少目录域（TOC field），无法在 Word 中生成带页码目录", "document.xml")


def check_header_footer(package: zipfile.ZipFile, issues: list[dict]) -> None:
    members = package.namelist()
    header_members = [name for name in members if re.fullmatch(r"word/header\d+\.xml", name)]
    footer_members = [name for name in members if re.fullmatch(r"word/footer\d+\.xml", name)]
    if not any(
        paragraph_text(read_member(package, member)).strip()
        for member in header_members
        if read_member(package, member) is not None
    ):
        issue(issues, "warning", "页眉为空（样本每页页眉有项目名称）", "header")
    has_page_field = False
    for member in footer_members:
        footer_root = read_member(package, member)
        if footer_root is None:
            continue
        for node in footer_root.findall(".//w:instrText", NS):
            if "PAGE" in (node.text or ""):
                has_page_field = True
    if not has_page_field:
        issue(issues, "blocker", "页脚缺少页码域（PAGE field）", "footer")


def write_report(docx_path: Path, result: dict) -> None:
    json_path = docx_path.with_suffix(".format-report.json")
    md_path = docx_path.with_suffix(".format-report.md")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# DOCX 格式校验报告", "", f"结论：{'通过' if result['ok'] else '未通过'}", ""]
    lines.extend(["| 级别 | 问题 | 位置 |", "|---|---|---|"])
    if result["issues"]:
        for item in result["issues"]:
            lines.append(f"| {item['level']} | {item['message']} | {item['target']} |")
    else:
        lines.append("| ok | 未发现格式阻塞项 |  |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_docx_format(docx_path: Path, write_files: bool = True) -> dict:
    docx_path = docx_path.expanduser().resolve()
    issues: list[dict] = []
    if not docx_path.exists():
        issue(issues, "blocker", "DOCX 文件不存在", str(docx_path))
        return {"file": str(docx_path), "ok": False, "issues": issues}
    with zipfile.ZipFile(docx_path) as package:
        styles_root = read_member(package, "word/styles.xml")
        document_root = read_member(package, "word/document.xml")
        if styles_root is None:
            issue(issues, "blocker", "缺少 styles.xml，无法确认宋体/字号/行距", "styles.xml")
        else:
            check_common_style(find_style(styles_root, "Normal"), "正文", BODY_SIZE, False, False, issues)
            check_common_style(find_style(styles_root, "Heading1"), "一级标题", HEADING1_SIZE, True, True, issues)
            for style_id, label in (("Heading2", "二级标题"), ("Heading3", "三级标题"), ("Heading4", "四级标题")):
                check_common_style(find_style(styles_root, style_id), label, BODY_SIZE, True, True, issues)
        if document_root is None:
            issue(issues, "blocker", "缺少 document.xml", "document.xml")
        else:
            check_page_size(document_root, issues)
            check_pagination_and_numbering(document_root, issues)
            check_toc_field(document_root, issues)
        check_header_footer(package, issues)
    result = {"file": str(docx_path), "ok": not any(item["level"] == "blocker" for item in issues), "issues": issues}
    if write_files:
        write_report(docx_path, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate DOCX bid response formatting.")
    parser.add_argument("docx_path", type=Path, help="Final DOCX file.")
    parser.add_argument("--no-report", action="store_true", help="Do not write report files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_docx_format(args.docx_path, write_files=not args.no_report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
