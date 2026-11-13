"""Validate the final 施工组织设计 DOCX against the locked project format (gate B3).

迁移来源见 CHANGELOG《脚本来源》，相对来源的改动：
  * 格式取自 qingtian-bid 的格式记录：样式按级别核对字体、西文字体、字号、加粗，
    行距按倍数、固定值、最小值核对；
  * 项目格式未确认或有变更待确认时直接判不通过（格式锁，见 format_state）；
  * 暗标模式：页眉页脚不得有任何文字、域或图片，正文不得有页码域；
  * 嵌入图在固定值行距下会被裁切的，判阻断（docx_effective_format.check_inline_images）；
  * 命令行用 --preset/--set 指定独立文件的格式，取代原来的 --font-profile；
  * 样式按样式名识别（docx_effective_format.style_roles）：中文版 Word 另存后样式 ID
    会变成数字，按 ID 找 Normal、Heading1 会误报缺样式。

INPUT: DOCX file; project-state.json found above it (locked document_format), else --preset/--set,
       else preset F1; optional final-delivery mode.
OUTPUT: effective-format issues, DOCX SHA-256, format snapshot, and optional JSON/MD report
        (<docx>.format-report.json / .md).
POS: DOCX format gate for qingtian-bid (stage 6 self-check, stage 7 gate B3). Checks OOXML
     properties only; rendered page counts belong to report_page_numbers (gate B2).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from docx_effective_format import (
    check_effective_format,
    check_inline_images,
    check_section_layout,
    describe_line_spacing,
    expected_line_spacing,
    role_spec,
    style_roles,
)
from docx_font_profiles import (
    apply_format_settings,
    latin_font_for,
    load_catalog,
    parse_assignment,
    preset_format,
    resolve_document_format,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"
HEADING_STYLE_LEVELS = {
    "Heading1": 1,
    "Heading2": 2,
    "Heading3": 3,
    "Heading4": 4,
    "Heading5": 5,
}
ANNOTATION_KEYWORDS = (
    "此处附", "待补充", "待回填", "待核查",
    "待确认", "需人工", "图片插入失败",
    "目录域",
)
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
# 最终 DOCX 正文中不应出现的 Markdown 泄漏痕迹
MARKDOWN_LEAK_IN_DOCX = (
    (re.compile(r"`"), "正文残留反引号`"),
    (re.compile(r"\*\*"), "正文残留加粗标记**"),
    (re.compile(r"^#{1,6}\s"), "正文残留Markdown标题#"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), "正文残留Markdown链接"),
    (re.compile(r"^>\s"), "正文残留引用块>"),
)


def issue(issues: list[dict], level: str, message: str, target: str) -> None:
    issues.append({"level": level, "message": message, "target": target})


def read_member(package: zipfile.ZipFile, member: str) -> ElementTree.Element | None:
    try:
        return ElementTree.fromstring(package.read(member))
    except KeyError:
        return None


def find_style(styles_root: ElementTree.Element, role: str) -> ElementTree.Element | None:
    roles = style_roles(styles_root)
    return next((style for style in styles_root.findall("w:style", NS)
                 if roles.get(style.get(f"{W}styleId")) == role), None)


def heading_level(p_pr: ElementTree.Element | None, roles: dict[str, str]) -> tuple[str | None, int | None]:
    style_id = attr(None if p_pr is None else p_pr.find("w:pStyle", NS), "val")
    role = roles.get(style_id or "", style_id)
    return role, HEADING_STYLE_LEVELS.get(role or "")


def attr(node: ElementTree.Element | None, name: str) -> str | None:
    return None if node is None else node.get(f"{W}{name}")


def paragraph_text(paragraph: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))


def is_annotation_text(text: str) -> bool:
    """Recognize manual-review placeholders emitted by the DOCX builder."""
    stripped = text.strip()
    return (
        stripped.startswith("（此处附")
        or (stripped.startswith("【") and any(keyword in stripped for keyword in ANNOTATION_KEYWORDS))
    )


def check_heading_indent(document_root: ElementTree.Element, issues: list[dict], roles: dict[str, str]) -> None:
    """Keep every Heading 1-5 paragraph flush left, independent of style inheritance."""
    body = document_root.find("w:body", NS)
    if body is None:
        return
    for paragraph in body.findall("w:p", NS):
        p_pr = paragraph.find("w:pPr", NS)
        style_id, level = heading_level(p_pr, roles)
        if level is None:
            continue
        indent = None if p_pr is None else p_pr.find("w:ind", NS)
        if indent is None:
            continue
        indent_values = ("firstLineChars", "firstLine", "hangingChars", "hanging", "leftChars", "left")
        if any((attr(indent, name) or "0") != "0" for name in indent_values):
            issue(issues, "blocker", f"标题未顶格: {paragraph_text(paragraph).strip()[:40]}", style_id)


def check_delivery_placeholders(document_root: ElementTree.Element, issues: list[dict], final: bool) -> None:
    """排版检查允许待补标记，正式交付不能携带缺件、页码或模板占位。"""
    for paragraph in document_root.findall(".//w:p", NS):
        text = paragraph_text(paragraph).strip()
        if is_annotation_text(text) or "P__" in text or re.search(r"\{\{.+?\}\}", text):
            issue(issues, "blocker" if final else "warning", f"成品仍有待补占位内容: {text[:60]}", "document.xml")


def check_common_style(
    style: ElementTree.Element | None,
    style_name: str,
    spec: tuple[str, float, bool | None],
    heading: bool,
    issues: list[dict],
    config: dict,
) -> None:
    """Style definitions must already carry the project format, so Word's own edits inherit it."""
    if style is None:
        issue(issues, "blocker", f"缺少 Word 样式: {style_name}", style_name)
        return
    east_asian_font, size_pt, bold = spec
    latin_font = latin_font_for(config, east_asian_font)
    r_fonts = style.find(".//w:rFonts", NS)
    if attr(r_fonts, "eastAsia") != east_asian_font or attr(r_fonts, "ascii") != latin_font:
        issue(issues, "blocker", f"{style_name} 字体不是 {east_asian_font}（西文 {latin_font}）", style_name)
    if attr(style.find(".//w:sz", NS), "val") != str(round(size_pt * 2)):
        issue(issues, "blocker", f"{style_name} 字号不是 {size_pt:g} 磅", style_name)
    color = attr(style.find(".//w:color", NS), "val")
    if color not in {"000000", "auto"}:
        issue(issues, "blocker", f"{style_name} 字体颜色不是黑色", style_name)
    spacing = style.find(".//w:spacing", NS)
    line, rule = expected_line_spacing(config)
    if attr(spacing, "line") != line or (attr(spacing, "lineRule") or "auto") != rule:
        issue(issues, "blocker", f"{style_name} 行距不是{describe_line_spacing(config)}", style_name)
    if heading:
        bold_node = style.find(".//w:b", NS)
        is_bold = bold_node is not None and attr(bold_node, "val") not in {"0", "false", "off"}
        if bold is not None and is_bold != bold:
            issue(issues, "blocker", f"{style_name} {'未加粗' if bold else '加粗了，项目格式要求标题不加粗'}", style_name)
        if (
            attr(spacing, "before") != str(round(config["heading_space_before_pt"] * 20))
            or attr(spacing, "after") != str(round(config["heading_space_after_pt"] * 20))
        ):
            issue(issues, "blocker", f"{style_name} 段前/段后不符合项目配置", style_name)


def check_pagination_and_numbering(document_root: ElementTree.Element, issues: list[dict], config: dict,
                                   roles: dict[str, str]) -> None:
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
        style_value, level = heading_level(p_pr, roles)
        if level is None:
            previous_heading_level = None
            continue
        text = paragraph_text(element).strip()
        follows_parent = previous_heading_level is not None and previous_heading_level < level
        if config["heading_page_breaks"] and level <= 2 and seen_any_heading and not follows_parent and not has_break_before:
            issue(issues, "blocker", f"标题未独立起页: {text[:30]}", style_value)
        if not SELF_NUMBERED_PATTERN.match(text):
            issue(issues, "warning", f"标题文本未携带编号: {text[:30]}", style_value)
        previous_heading_level = level
        seen_any_heading = True
    if config["heading_page_breaks"] and page_break_count == 0:
        issue(issues, "blocker", "全文没有任何分页符，章节未独立起页", "document.xml")


def check_toc_field(document_root: ElementTree.Element, issues: list[dict]) -> None:
    instructions = [node.text or "" for node in document_root.findall(".//w:instrText", NS)]
    if not any("TOC" in instruction for instruction in instructions):
        issue(issues, "blocker", "缺少目录域（TOC field），无法在 Word 中生成带页码目录", "document.xml")


def check_markdown_leaks(document_root: ElementTree.Element, issues: list[dict]) -> None:
    """扫描最终 DOCX 正文，拦截未清洗干净的 Markdown 标记（格式不标准的常见原因）。"""
    body = document_root.find("w:body", NS)
    if body is None:
        return
    seen: set[str] = set()
    for paragraph in body.findall(".//w:p", NS):
        text = paragraph_text(paragraph)
        if not text or not text.strip():
            continue
        for pattern, label in MARKDOWN_LEAK_IN_DOCX:
            if pattern.search(text):
                key = f"{label}:{text[:40]}"
                if key in seen:
                    continue
                seen.add(key)
                issue(
                    issues,
                    "blocker",
                    f"DOCX 存在 Markdown 泄漏（{label}）: {text.strip()[:40]}",
                    "document.xml",
                )
                if len(seen) >= 20:
                    return


def field_instructions(root: ElementTree.Element) -> list[str]:
    """Complex fields (w:instrText) and simple fields (w:fldSimple) alike."""
    complex_fields = [node.text or "" for node in root.iter(f"{W}instrText")]
    simple_fields = [node.get(f"{W}instr", "") for node in root.iter(f"{W}fldSimple")]
    return complex_fields + simple_fields


def header_footer_members(package: zipfile.ZipFile) -> list[str]:
    return [name for name in package.namelist() if re.fullmatch(r"word/(?:header|footer)\d+\.xml", name)]


def check_blind_mode(package: zipfile.ZipFile, document_root: ElementTree.Element, issues: list[dict]) -> None:
    """暗标：不设页眉、页脚、页码（导则 3.7、暗标通知；决策 2A）。空的页眉页脚部件可以接受。"""
    for member in header_footer_members(package):
        root = read_member(package, member)
        if root is None:
            continue
        if paragraph_text(root).strip():
            issue(issues, "blocker", f"暗标模式页眉页脚须为空，现有文字: {paragraph_text(root).strip()[:30]}", member)
        if field_instructions(root):
            issue(issues, "blocker", "暗标模式页眉页脚不得有域（页码等）", member)
        if any(True for _ in root.iter(f"{W}drawing")) or any(True for _ in root.iter(f"{W}pict")):
            issue(issues, "blocker", "暗标模式页眉页脚不得有图片或标志", member)
    if any("PAGE" in instruction.upper() for instruction in field_instructions(document_root)):
        issue(issues, "blocker", "暗标模式正文不得有页码域", "document.xml")


def check_header_footer(package: zipfile.ZipFile, issues: list[dict], config: dict) -> None:
    header_members = [name for name in package.namelist() if re.fullmatch(r"word/header\d+\.xml", name)]
    footer_members = [name for name in package.namelist() if re.fullmatch(r"word/footer\d+\.xml", name)]
    if not any(
        paragraph_text(read_member(package, member)).strip()
        for member in header_members
        if read_member(package, member) is not None
    ):
        issue(issues, "warning", "页眉为空；招标文件没有页眉要求时可忽略", "header")
    has_page_field = False
    for member in footer_members:
        footer_root = read_member(package, member)
        if footer_root is not None and any("PAGE" in item.upper() for item in field_instructions(footer_root)):
            has_page_field = True
    if config["require_page_numbers"] and not has_page_field:
        issue(issues, "blocker", "页脚缺少页码域（PAGE field）", "footer")


def write_report(docx_path: Path, result: dict) -> None:
    json_path = docx_path.with_suffix(".format-report.json")
    md_path = docx_path.with_suffix(".format-report.md")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# DOCX 格式校验报告",
        "",
        f"结论：{'通过' if result['ok'] else '未通过'}",
        f"格式：{result.get('preset', '未知')} {result.get('preset_name', '')}",
        f"检查模式：{result.get('mode', 'layout')}；范围：OOXML结构和实际格式属性，未验证页面渲染",
        f"文档SHA-256：{result.get('docx_sha256', '')}",
        "",
    ]
    lines.extend(["| 级别 | 问题 | 位置 |", "|---|---|---|"])
    if result["issues"]:
        for item in result["issues"]:
            lines.append(f"| {item['level']} | {item['message']} | {item['target']} |")
    else:
        lines.append("| ok | 未发现格式阻塞项 |  |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_styles(styles: ElementTree.Element, config: dict, issues: list[dict]) -> None:
    check_common_style(find_style(styles, "Normal"), "Normal", role_spec("Normal", config), False, issues, config)
    for level in range(1, 6):
        style_id = f"Heading{level}"
        check_common_style(find_style(styles, style_id), style_id, role_spec(style_id, config), True, issues, config)


def check_package_format(package: zipfile.ZipFile, config: dict, issues: list[dict], final: bool) -> None:
    styles = read_member(package, "word/styles.xml")
    document = read_member(package, "word/document.xml")
    if styles is None or document is None:
        issue(issues, "blocker", "缺少 styles.xml 或 document.xml，无法确认实际格式", "DOCX")
        return
    roles = style_roles(styles)
    check_styles(styles, config, issues)
    check_section_layout(document, config, issues)
    check_pagination_and_numbering(document, issues, config, roles)
    check_heading_indent(document, issues, roles)
    if config["require_toc"]:
        check_toc_field(document, issues)
    check_markdown_leaks(document, issues)
    if config["blind_mode"]:
        check_blind_mode(package, document, issues)
    else:
        check_header_footer(package, issues, config)
    for member in package.namelist():
        if not re.fullmatch(r"word/(?:document|header\d+|footer\d+|footnotes|endnotes)\.xml", member):
            continue
        root = read_member(package, member)
        if root is not None:
            check_effective_format(root, styles, config, issues, member)
            check_inline_images(root, styles, issues, member)
            check_delivery_placeholders(root, issues, final)


def validate_docx_format(
    docx_path: Path,
    write_files: bool = True,
    document_format: dict | None = None,
    final: bool = False,
) -> dict:
    docx_path = docx_path.expanduser().resolve()
    issues: list[dict] = []
    if not docx_path.exists():
        issue(issues, "blocker", "DOCX 文件不存在", str(docx_path))
        return {"file": str(docx_path), "ok": False, "issues": issues}
    try:
        config = resolve_document_format(docx_path, document_format)
        # Hash and inspection use the same immutable bytes, even if Word saves concurrently.
        contents = docx_path.read_bytes()
        digest = hashlib.sha256(contents).hexdigest()
        with zipfile.ZipFile(io.BytesIO(contents)) as package:
            check_package_format(package, config, issues, final)
    except (ValueError, OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        issue(issues, "blocker", str(exc), "DOCX / document_format")
        return {"file": str(docx_path), "ok": False, "issues": issues}
    result = {
        "file": str(docx_path),
        "skill": "qingtian-bid",
        "preset": config["preset"],
        "preset_name": load_catalog()["presets"][config["preset"]]["name"],
        "document_format": config,
        "docx_sha256": digest,
        "mode": "final" if final else "layout",
        "schema_version": 1,
        "verification_scope": "ooxml-properties; no visual rendering",
        "ok": not any(item["level"] == "blocker" for item in issues),
        "issues": issues,
    }
    if write_files:
        try:
            write_report(docx_path, result)
        except OSError as exc:
            issue(issues, "blocker", f"格式报告保存失败: {exc}", str(docx_path))
            result["ok"] = False
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验施组 DOCX 的格式是否与项目锁定的格式一致（门禁 B3）。")
    parser.add_argument("docx_path", type=Path, help="待校验的 DOCX。")
    parser.add_argument("--preset", help="独立文件的格式预设；项目内必须与 project-state.json 一致。")
    parser.add_argument("--set", dest="settings", action="append", default=[], metavar="字段=值",
                        help="独立文件在预设上改的字段；可重复。")
    parser.add_argument("--no-report", action="store_true", help="不写报告文件。")
    parser.add_argument("--final", action="store_true", help="正式交付检查：阻止待补材料、目录和页码占位。")
    return parser.parse_args()


def explicit_format(preset: str | None, settings: list[str]) -> dict | None:
    if preset is None and not settings:
        return None
    record = preset_format(preset)
    if settings:
        record = apply_format_settings(record, dict(parse_assignment(item) for item in settings), "命令行指定")
    return record


def main() -> int:
    args = parse_args()
    try:
        selected = explicit_format(args.preset, args.settings)
    except ValueError as exc:
        print(f"格式参数无效: {exc}", file=sys.stderr)
        return 2
    result = validate_docx_format(args.docx_path, write_files=not args.no_report,
                                  document_format=selected, final=args.final)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
