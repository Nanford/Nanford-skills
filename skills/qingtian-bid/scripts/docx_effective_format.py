"""Inspect effective OOXML text and paragraph formatting.

迁移来源见 CHANGELOG《脚本来源》，相对来源的改动：
  * 字体、字号、加粗按段落角色分别核对，与 build_response_docx 的取值一一对应：
    一至三级标题分设字体字号（四、五级跟三级），西文槽位（ascii、hAnsi）核对西文字体；
  * 标题加粗双向核对：项目格式要求不加粗（如 F4）时，加粗的标题同样是阻断项；
  * 任何段落出现斜体都判阻断：各预设都不用斜体，而 python-docx 默认模板的 Heading 4 自带斜体；
  * 行距按倍数、固定值、最小值分别核对；
  * 新增嵌入图检查：固定值行距的段落里，图比行高还高就会被裁成窄条（设计稿第九节）；
  * 段落角色按样式名识别，不按样式 ID：中文版 Word 另存时会把样式 ID 改成数字
    （Normal→1、heading 1→3），而终稿要经 Word 更新目录和页码后再校验。

INPUT: document/styles/header/footer XML and the normalized qingtian-bid project format.
OUTPUT: blocker issues for inherited or directly overridden format mismatches.
POS: shared inspection layer for validate_docx_format; no Office dependency.
"""

from __future__ import annotations

from xml.etree import ElementTree

from docx_font_profiles import LINE_RULES, latin_font_for

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
NS = {"w": W[1:-1]}
HEADING_TIERS = {"Heading1": 1, "Heading2": 2, "Heading3": 3, "Heading4": 3, "Heading5": 3}
SPECIAL_ROLES = (*HEADING_TIERS, "BidCoverTitle", "BidCoverInfo", "BidNavigationTitle", "BidSubheading")
WORD_LINE_RULES = {"multiple": "auto", "exact": "exact", "at_least": "atLeast"}
STYLE_NAME_ROLES = {
    "normal": "Normal",
    **{f"heading {level}": f"Heading{level}" for level in range(1, 10)},
    "bid cover title": "BidCoverTitle",
    "bid cover info": "BidCoverInfo",
    "bid navigation title": "BidNavigationTitle",
    "bid subheading": "BidSubheading",
}
EMU_PER_POINT = 12700


def xml_value(node, name="val", default=None):
    return default if node is None else node.get(W + name, default)


def visible_text(node):
    return "".join(child.text or "" for child in node.iter(W + "t"))


def style_chain(styles, style_id):
    """Walk basedOn with cycle protection; return base-to-derived order."""
    chain, seen = [], set()
    while style_id and style_id not in seen:
        seen.add(style_id)
        style = styles.get(style_id)
        if style is None:
            break
        chain.append(style)
        style_id = xml_value(style.find(W + "basedOn"))
    return list(reversed(chain))


def style_roles(styles_root: ElementTree.Element) -> dict[str, str]:
    """样式 ID → 规范角色名（Normal、Heading1、TOC1、BidSubheading…），按 w:name 识别。"""
    roles = {}
    for style in styles_root.findall(W + "style"):
        style_id = xml_value(style, "styleId")
        name = (xml_value(style.find(W + "name"), default="") or "").strip().lower()
        if name.startswith("toc "):
            roles[style_id] = "TOC" + name[4:].strip()
        else:
            roles[style_id] = STYLE_NAME_ROLES.get(name, style_id)
    return roles


def default_paragraph_style_id(styles_root: ElementTree.Element) -> str:
    """没有 pStyle 的段落用默认段落样式；Word 另存后它的 ID 不一定还叫 Normal。"""
    for style in styles_root.findall(W + "style"):
        if xml_value(style, "type") == "paragraph" and xml_value(style, "default") in {"1", "true", "on"}:
            return xml_value(style, "styleId")
    return "Normal"


def merged_properties(nodes):
    result = {}
    for node in nodes:
        if node is None:
            continue
        for child in node:
            key = child.tag.removeprefix(W)
            properties = {name.removeprefix(W): value for name, value in child.attrib.items()}
            if key in {"rFonts", "spacing", "ind"}:
                combined = dict(result.get(key, {}))
                # Explicit literal fonts override an inherited theme slot.
                if key == "rFonts":
                    for slot in ("ascii", "hAnsi", "eastAsia", "cs"):
                        if slot in properties:
                            combined.pop(slot + "Theme", None)
                combined.update(properties)
                result[key] = combined
            else:
                result[key] = properties
    return result


def flag(issues, message, target):
    issues.append({"level": "blocker", "message": message, "target": target})


def property_enabled(properties, key):
    return key in properties and properties[key].get("val", "1") not in {"0", "false", "off"}


def role_spec(role: str, config: dict) -> tuple[str, float, bool | None]:
    """(中文字体, 字号, 应否加粗)；None 表示不核对加粗（正文行内加粗、表头加粗都合法）。

    必须与 build_response_docx.configure_document_styles 及各 add_* 函数保持一致。
    """
    if role in HEADING_TIERS:
        tier = HEADING_TIERS[role]
        return config[f"heading{tier}_font"], config[f"heading{tier}_size_pt"], config["heading_bold"]
    if role == "BidNavigationTitle":
        return config["heading1_font"], config["heading1_size_pt"], config["heading_bold"]
    if role == "BidSubheading":
        return config["heading3_font"], config["heading3_size_pt"], True
    if role == "BidCoverTitle":
        return config["heading1_font"], config["cover_title_size_pt"], True
    if role == "BidCoverInfo":
        return config["body_font"], config["cover_info_size_pt"], None
    return config["body_font"], config["body_size_pt"], None


def expected_line_spacing(config: dict) -> tuple[str, str]:
    """OOXML 的 w:line 与 w:lineRule：倍数按 240 计，固定值和最小值按 1/20 磅计。"""
    rule = config["line_spacing_rule"]
    unit = 240 if rule == "multiple" else 20
    return str(round(config["line_spacing"] * unit)), WORD_LINE_RULES[rule]


def describe_line_spacing(config: dict) -> str:
    unit = "倍" if config["line_spacing_rule"] == "multiple" else "磅"
    return f"{LINE_RULES[config['line_spacing_rule']]} {config['line_spacing']:g} {unit}"


def check_run_properties(properties, spec, config, issues, target):
    east_asian_font, size_pt, bold = spec
    latin_font = latin_font_for(config, east_asian_font)
    fonts = properties.get("rFonts", {})
    for slot, expected in (("ascii", latin_font), ("hAnsi", latin_font), ("eastAsia", east_asian_font)):
        if fonts.get(slot) != expected or slot + "Theme" in fonts:
            flag(issues, f"实际字体未设置为{expected}（{slot}）", target)
    expected_size = str(round(size_pt * 2))
    if properties.get("sz", {}).get("val") != expected_size:
        flag(issues, f"实际字号不符合要求（应为{size_pt:g}磅）", target)
    color = properties.get("color", {})
    if color.get("val", "auto").upper() not in {"000000", "AUTO"} or "themeColor" in color:
        flag(issues, "实际字体颜色不是黑色", target)
    if bold is True and not property_enabled(properties, "b"):
        flag(issues, "实际标题未加粗", target)
    if bold is False and property_enabled(properties, "b"):
        flag(issues, "实际标题加粗，项目格式要求标题不加粗", target)
    if property_enabled(properties, "i"):
        flag(issues, "实际字形为斜体，各预设均不用斜体", target)


def check_paragraph_properties(properties, config, issues, target, heading=False, body=False):
    spacing = properties.get("spacing", {})
    line, rule = expected_line_spacing(config)
    if spacing.get("line") != line or spacing.get("lineRule", "auto") != rule:
        flag(issues, f"实际行距不是{describe_line_spacing(config)}", target)
    if heading:
        for attribute, key in (("before", "heading_space_before_pt"), ("after", "heading_space_after_pt")):
            if (spacing.get(attribute, "0") != str(round(config[key] * 20))
                    or spacing.get(attribute + "Autospacing", "0") not in {"0", "false", "off"}
                    or spacing.get(attribute + "Lines", "0") != "0"):
                flag(issues, "实际标题段前/段后距离不符合项目配置", target)
    indent = properties.get("ind", {})
    if heading and any(indent.get(key, "0") != "0" for key in ("firstLine", "firstLineChars", "left", "leftChars", "hanging", "hangingChars")):
        flag(issues, "实际标题未顶格", target)
    if body:
        chars = indent.get("firstLineChars")
        expected = str(round(config["first_line_indent_chars"] * 100))
        points = str(round(config["first_line_indent_chars"] * config["body_size_pt"] * 20))
        if (chars is not None and chars != expected) or (chars is None and indent.get("firstLine", "0") != points):
            flag(issues, "实际正文首行缩进不符合项目配置", target)
        if any(indent.get(key, "0") != "0" for key in ("hanging", "hangingChars")):
            flag(issues, "正文存在冲突的悬挂缩进", target)


def paragraph_context(paragraph, styles, roles, default_id):
    p_pr = paragraph.find(W + "pPr")
    style_id = xml_value(None if p_pr is None else p_pr.find(W + "pStyle"), default=default_id)
    chain = style_chain(styles, style_id)
    chain_roles = [roles.get(xml_value(s, "styleId"), xml_value(s, "styleId")) for s in chain]
    default_role = "TOC" if any(str(role).startswith("TOC") for role in chain_roles) else "Normal"
    role = next((role for role in reversed(chain_roles) if role in SPECIAL_ROLES), default_role)
    heading = role in SPECIAL_ROLES and role != "BidCoverInfo"
    return p_pr, chain, role, heading


def part_role_spec(role: str, config: dict, part_name: str) -> tuple[str, float, bool | None]:
    if part_name.startswith(("word/header", "word/footer")):
        return config["body_font"], config["header_footer_size_pt"], None
    return role_spec(role, config)


def check_effective_format(root, styles_root, config, issues, part_name):
    styles = {xml_value(style, "styleId"): style for style in styles_root.findall(W + "style")}
    roles = style_roles(styles_root)
    default_id = default_paragraph_style_id(styles_root)
    default_p = styles_root.find("w:docDefaults/w:pPrDefault/w:pPr", NS)
    default_r = styles_root.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
    direct_body = set(root.findall("w:body/w:p", NS))
    for paragraph in root.iter(W + "p"):
        text = visible_text(paragraph).strip()
        if not text:
            continue
        p_pr, chain, role, heading = paragraph_context(paragraph, styles, roles, default_id)
        p_props = merged_properties([default_p, *(s.find(W + "pPr") for s in chain), p_pr])
        target = f"{part_name}: {text[:45]}"
        is_body = (paragraph in direct_body and role == "Normal"
                   and not text.startswith(("【", "（此处附"))
                   and p_props.get("jc", {}).get("val") != "center")
        check_paragraph_properties(p_props, config, issues, target, heading, is_body)
        spec = part_role_spec(role, config, part_name)
        for run in paragraph.findall(".//w:r", NS):
            if not visible_text(run).strip():
                continue
            r_pr = run.find(W + "rPr")
            char_id = xml_value(None if r_pr is None else r_pr.find(W + "rStyle"))
            char_chain = style_chain(styles, char_id)
            r_props = merged_properties([default_r, *(s.find(W + "rPr") for s in chain),
                                         *(s.find(W + "rPr") for s in char_chain), r_pr])
            check_run_properties(r_props, spec, config, issues, target)


def check_inline_images(root: ElementTree.Element, styles_root: ElementTree.Element, issues: list[dict],
                        part_name: str) -> None:
    """固定值行距会把高于行高的嵌入图裁成窄条；浮动图（anchor）和倍数、最小值行距不受影响。

    只含图片的段落没有可见文字，check_effective_format 会跳过，所以单独核对合并后的行距。
    """
    styles = {xml_value(style, "styleId"): style for style in styles_root.findall(W + "style")}
    roles = style_roles(styles_root)
    default_id = default_paragraph_style_id(styles_root)
    default_p = styles_root.find("w:docDefaults/w:pPrDefault/w:pPr", NS)
    for paragraph in root.iter(W + "p"):
        inlines = list(paragraph.iter(WP + "inline"))
        if not inlines:
            continue
        p_pr, chain, _, _ = paragraph_context(paragraph, styles, roles, default_id)
        spacing = merged_properties([default_p, *(s.find(W + "pPr") for s in chain), p_pr]).get("spacing", {})
        if spacing.get("lineRule") != "exact":
            continue
        line_pt = int(spacing.get("line", "240")) / 20
        for inline in inlines:
            extent = inline.find(WP + "extent")
            height_pt = int("0" if extent is None else extent.get("cy", "0")) / EMU_PER_POINT
            if height_pt > line_pt:
                flag(issues, f"图片所在段落为固定值行距 {line_pt:g} 磅，图高约 {height_pt:.0f} 磅，会被裁成窄条；"
                             "只含图片的段落须用单倍行距", f"{part_name}: 图片段落")


def cm_twips(value):
    return round(value * 1440 / 2.54)


def check_section_layout(root, config, issues):
    sections = list(root.iter(W + "sectPr"))
    if not sections:
        flag(issues, "文档未声明页面与分节格式", "document.xml")
    for index, section in enumerate(sections, 1):
        target = f"sectPr[{index}]"
        size = section.find(W + "pgSz")
        margins = section.find(W + "pgMar")
        for attribute, key in (("w", "page_width_cm"), ("h", "page_height_cm")):
            if xml_value(size, attribute) != str(cm_twips(config[key])):
                flag(issues, "页面尺寸不符合项目配置", target)
        for side in ("top", "bottom", "left", "right"):
            if xml_value(margins, side) != str(cm_twips(config[f"margin_{side}_cm"])):
                flag(issues, f"{side}页边距不符合项目配置", target)
        if xml_value(margins, "gutter", "0") != "0":
            flag(issues, "存在项目配置未声明的装订线", target)
