"""Validate final DOCX formatting against bid response requirements.

INPUT: final DOCX response file.
OUTPUT: validation result with blocker/warning issues and optional JSON report.
POS: DOCX format gate for the bid-preparation skill.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"
EXPECTED_FONT = "宋体"
BODY_SIZE = "24"
HEADING1_SIZE = "28"
LINE_SPACING = "360"
HEADING_SPACING = "160"


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


def check_numbering(numbering_root: ElementTree.Element | None, issues: list[dict]) -> None:
    if numbering_root is None:
        issue(issues, "blocker", "缺少 numbering.xml，标题未使用真实编号", "numbering.xml")
        return
    required_patterns = ["%1.", "%1.%2", "%1.%2.%3", "%1.%2.%3.%4"]
    existing = {attr(node, "val") for node in numbering_root.findall(".//w:lvlText", NS)}
    for pattern in required_patterns:
        if pattern not in existing:
            issue(issues, "blocker", f"缺少标题编号格式 {pattern}", "numbering.xml")


def check_heading_paragraphs(document_root: ElementTree.Element | None, issues: list[dict]) -> None:
    if document_root is None:
        issue(issues, "blocker", "缺少 document.xml", "document.xml")
        return
    for paragraph in document_root.findall(".//w:p", NS):
        style_value = attr(paragraph.find("./w:pPr/w:pStyle", NS), "val")
        if style_value in {"Heading1", "Heading2", "Heading3", "Heading4"}:
            if paragraph.find("./w:pPr/w:numPr", NS) is None:
                issue(issues, "blocker", f"{style_value} 段落未设置真实编号", style_value)
            spacing = paragraph.find("./w:pPr/w:spacing", NS)
            if spacing is not None and attr(spacing, "line") not in {None, LINE_SPACING}:
                issue(issues, "blocker", f"{style_value} 段落行距覆盖不符合要求", style_value)


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
        result = {"file": str(docx_path), "ok": False, "issues": issues}
        return result
    with zipfile.ZipFile(docx_path) as package:
        styles_root = read_member(package, "word/styles.xml")
        document_root = read_member(package, "word/document.xml")
        numbering_root = read_member(package, "word/numbering.xml")
    if styles_root is None:
        issue(issues, "blocker", "缺少 styles.xml，无法确认宋体/字号/行距", "styles.xml")
    else:
        check_common_style(find_style(styles_root, "Normal"), "正文", BODY_SIZE, False, False, issues)
        check_common_style(find_style(styles_root, "Heading1"), "一级标题", HEADING1_SIZE, True, True, issues)
        for style_id, label in (("Heading2", "二级标题"), ("Heading3", "三级标题"), ("Heading4", "四级标题")):
            check_common_style(find_style(styles_root, style_id), label, BODY_SIZE, True, True, issues)
    check_numbering(numbering_root, issues)
    check_heading_paragraphs(document_root, issues)
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
