"""Scan the finished 施工组织设计 DOCX for what the Markdown gates cannot see: hidden or invisible content (B6),
identity in document properties, headers, images and the cover (B5), and fonts the reviewer may lack (W8).

INPUT: the finished DOCX (OOXML parts read in memory, never opened in Word); the project's identity list
       (text_gates.load_identity_terms), track (rule card) and locked document_format (blind mode, fonts);
       the font catalog (docx_font_profiles.load_catalog); docx_effective_format for style inheritance.
OUTPUT: scan_docx() / project_scan() → raw hits [{gate, match, message, fixed?}] for the stage-7 gate
        report (第 4b-2 步); clean_properties() blanks the identity-bearing document properties in place
        after a backup; a CLI that prints the hits (exit 1 while a blocking hit remains).
POS: finished-file layer of the stage-7 gates (design v1 §9 第 4b 步). B6 has no 误报 path (决策 4a-1A only
     lets B4, B5, B7, B13 through), so it only matches what never belongs in a 施组 sent to an AI reviewer: hidden
     or same-colour text, sub-6-pt or squeezed text, comments, revisions, document variables, OLE/ActiveX/
     macro objects, content pulled from outside, and instructions addressed to the scoring system. The
     instruction patterns are deliberately narrow 【推断】; 评委、评审专家 stay with B8 (text_gates).
     B5 here covers what the drafts don't carry: document properties (fixed: --clean-properties clears
     them), fields that print the author, the cover and TOC pages, text boxes, notes, image names and alt
     text, hyperlinks, customXml and the file name. The item body was checked in its draft (第 4a 步);
     edit the draft and rebuild instead of editing the body in Word. In blind mode the header and footer
     belong to B3 (validate_docx_format). Hit messages quote a short snippet so the user can find the
     spot; they are printed, never written to a file (决策 4a-1A).
     W8 reads the fonts each text run really resolves to (style chain, theme fonts), not every font
     mentioned in styles.xml 【推断】. --clean-properties edits only docProps/ (决策 4b-1-2A): body, styles and
     settings stay as Word or WPS saved them.
"""

from __future__ import annotations

import argparse
import io
import os
import posixpath
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from docx import Document
from lxml import etree

from docx_effective_format import (
    W,
    default_paragraph_style_id,
    merged_properties,
    property_enabled,
    style_chain,
    style_roles,
    xml_value,
)
from docx_font_profiles import FONT_FIELDS, load_catalog
from project_cards import RULE_CARD_FILE, find_project_dir, load_json, load_project
from text_gates import hit, identity_pattern_hits, identity_term_hits, load_identity_terms

MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
W15 = "{http://schemas.microsoft.com/office/word/2012/wordml}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CORE_NS = {"cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
           "dc": "http://purl.org/dc/elements/1.1/"}
APP = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
CUSTOM = "{http://schemas.openxmlformats.org/officeDocument/2006/custom-properties}"
STORY = re.compile(r"word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml")
HEADER_FOOTER = re.compile(r"word/(?:header|footer)\d+\.xml")

# ---- B6 ----
HEX = re.compile(r"[0-9A-Fa-f]{6}")
HIGHLIGHT = {"black": "000000", "blue": "0000FF", "cyan": "00FFFF", "green": "00FF00", "magenta": "FF00FF",
             "red": "FF0000", "yellow": "FFFF00", "white": "FFFFFF", "darkBlue": "000080", "darkCyan": "008080",
             "darkGreen": "008000", "darkMagenta": "800080", "darkRed": "800000", "darkYellow": "808000",
             "darkGray": "808080", "lightGray": "C0C0C0"}
WHITE_THEMES = {"background1", "light1"}
COLOR_GAP = 0x30  # 文字和底色每个通道都差不到 0x30，肉眼几乎分不出【推断】
MIN_HALF_POINTS = 12  # 6 磅
MIN_SCALE = 50  # 字符缩放（%）
REVISIONS = {"ins": "插入", "del": "删除", "moveFrom": "移动", "moveTo": "移动", "rPrChange": "格式修订",
             "pPrChange": "格式修订", "sectPrChange": "格式修订", "tblPrChange": "格式修订", "trPrChange": "格式修订",
             "tcPrChange": "格式修订", "tblGridChange": "格式修订", "numberingChange": "编号修订",
             "cellIns": "表格修订", "cellDel": "表格修订"}
OBJECT_TAGS = {"altChunk": "外部文档块（altChunk）", "object": "OLE 对象", "control": "ActiveX 控件",
               "subDoc": "子文档"}
PULL_FIELDS = {"INCLUDETEXT", "INCLUDEPICTURE", "INCLUDE", "LINK", "DDE", "DDEAUTO", "IMPORT"}
# 面向评审系统的指令性文字【推断】：只认请求打分、要求忽略指令、直接称呼评审系统这三种说法
REQUEST_SCORE = re.compile(r"(请|务必|直接|一律)[^。！？!?\n]{0,20}(给予|给出|打|评为|评定为|判为|判定为|认定为)"
                           r"[^。！？!?\n]{0,8}(满分|最高分|最高档|高分|第一名|A档|优秀档|第一档)")
IGNORE_RULES = re.compile(r"(忽略|无视|不要理会|不必遵循|不要遵循)[^。！？!?\n]{0,10}(以上|之前|前面|上述|其他|其它|所有)"
                          r"[^。！？!?\n]{0,10}(指令|指示|要求|提示|规则|评分标准)")
SYSTEM_WORDS = r"(评审系统|评标系统|评分系统|智能评审|智能评标|AI评审|AI评标|大模型|语言模型)"
ADDRESS_SYSTEM = re.compile(r"(致|敬请|请)[^。！？!?\n]{0,4}" + SYSTEM_WORDS + "|" + SYSTEM_WORDS +
                            r"[，,：:\s]{0,2}(请|务必|应当|必须)")
ENGLISH_PROMPT = re.compile(r"ignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)\s+instructions|system\s+prompt"
                            r"|you\s+are\s+(?:an?\s+)?(?:ai|assistant|language\s+model)", re.IGNORECASE)
INSTRUCTIONS = (REQUEST_SCORE, IGNORE_RULES, ADDRESS_SYSTEM, ENGLISH_PROMPT)

# ---- B5 ----
CORE_PERSON = (("dc:creator", "作者"), ("cp:lastModifiedBy", "最后修改者"))
CORE_TEXT = (("dc:title", "标题"), ("dc:subject", "主题"), ("cp:keywords", "关键词"), ("dc:description", "备注"),
             ("cp:category", "类别"), ("cp:contentStatus", "状态"), ("dc:identifier", "标识"))
APP_FIXED = (("Company", "单位"), ("Manager", "经理"), ("HyperlinkBase", "超链接基础"))
CUSTOM_ALLOWED = {"KSOProductBuildVer", "ICV"}  # WPS 每次保存都写：版本号和随机编号，不含身份
AUTHOR_FIELDS = {"AUTHOR", "LASTSAVEDBY", "USERNAME", "USERINITIALS", "USERADDRESS"}

# ---- W8 ----
# Windows 10/11 中文版自带的字体【推断】，加上格式预设库的 system、latin 两组
WINDOWS_FONTS = {"宋体", "SimSun", "新宋体", "NSimSun", "黑体", "SimHei", "楷体", "KaiTi", "仿宋", "FangSong",
                 "微软雅黑", "Microsoft YaHei", "微软雅黑 Light", "Microsoft YaHei Light", "等线", "DengXian",
                 "等线 Light", "DengXian Light", "SimSun-ExtB", "Times New Roman", "Arial", "Calibri",
                 "Calibri Light", "Cambria", "Cambria Math", "Symbol", "Wingdings", "Courier New", "Segoe UI",
                 "Consolas", "Tahoma", "Verdana", "Georgia"}
FONT_ALIASES = {"FangSong_GB2312": "仿宋_GB2312", "KaiTi_GB2312": "楷体_GB2312"}

CLEAN_CORE = ("dc:creator", "cp:lastModifiedBy", *(name for name, _ in CORE_TEXT))
CLEAN_HINT = "运行 scan_docx_hygiene.py <成品> --clean-properties 清掉，再重新校验 --final 和门禁"


# ---------- 读包 ----------

def load_parts(data: bytes) -> dict:
    """DOCX 的部件：XML 解析好，嵌入文件留原始字节。"""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            names = package.namelist()
            xml, embedded = {}, {}
            for name in names:
                if name.startswith("word/embeddings/"):
                    embedded[name] = package.read(name)
                elif name.endswith((".xml", ".rels")):
                    xml[name] = ElementTree.fromstring(package.read(name))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"不是有效的 DOCX: {exc}") from exc
    except ElementTree.ParseError as exc:
        raise ValueError(f"DOCX 里有部件不是合法的 XML: {exc}") from exc
    return {"names": names, "xml": xml, "embedded": embedded}


def stories(parts: dict) -> list[tuple[str, ElementTree.Element]]:
    return [(name, root) for name, root in sorted(parts["xml"].items()) if STORY.fullmatch(name)]


def part_label(name: str) -> str:
    base = name.rsplit("/", 1)[-1].removesuffix(".xml")
    labels = {"document": "正文", "footnotes": "脚注", "endnotes": "尾注", "comments": "批注"}
    if base.startswith(("header", "footer")):
        return f"{'页眉' if base.startswith('header') else '页脚'}（{base}）"
    return labels.get(base, name)


def snippet(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= 12 else text[:12] + "…"


def attributes(node: ElementTree.Element | None) -> dict:
    return {} if node is None else {key.removeprefix(W): value for key, value in node.attrib.items()}


def text_runs(node: ElementTree.Element, paragraph=None, cell_fill: str | None = None):
    """(段落, run, 文字, 单元格底色)：含表格、文本框、超链接里的 run；mc:Fallback 是同一内容的旧格式副本，跳过。"""
    for child in node:
        if child.tag == MC + "Fallback":
            continue
        if child.tag == W + "tc":
            yield from text_runs(child, paragraph, fill_of(attributes(child.find(f"{W}tcPr/{W}shd"))) or cell_fill)
        elif child.tag == W + "txbxContent":
            yield from text_runs(child, None, None)
        elif child.tag == W + "p":
            yield from text_runs(child, child, cell_fill)
        else:
            if child.tag == W + "r" and paragraph is not None:
                text = "".join(piece.text or "" for piece in child.findall(W + "t"))
                if text:
                    yield paragraph, child, text, cell_fill
            yield from text_runs(child, paragraph, cell_fill)


def style_context(parts: dict) -> dict:
    styles_root = parts["xml"].get("word/styles.xml")
    if styles_root is None:
        return {"styles": {}, "defaults": None, "default_id": "Normal", "roles": {}}
    return {"styles": {xml_value(style, "styleId"): style for style in styles_root.findall(W + "style")},
            "defaults": styles_root.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr"),
            "default_id": default_paragraph_style_id(styles_root), "roles": style_roles(styles_root)}


def paragraph_style(paragraph: ElementTree.Element, context: dict) -> str:
    return xml_value(paragraph.find(f"{W}pPr/{W}pStyle")) or context["default_id"]


def run_properties(run: ElementTree.Element, paragraph: ElementTree.Element, context: dict) -> dict:
    """run 实际生效的字符格式：文档默认 → 段落样式链 → 字符样式链 → 直接格式。"""
    styles = context["styles"]
    nodes = [context["defaults"]]
    nodes += [style.find(W + "rPr") for style in style_chain(styles, paragraph_style(paragraph, context))]
    direct = run.find(W + "rPr")
    char_style = xml_value(direct.find(W + "rStyle")) if direct is not None else None
    if char_style:
        nodes += [style.find(W + "rPr") for style in style_chain(styles, char_style)]
    return merged_properties([*nodes, direct])


def paragraph_fill(paragraph: ElementTree.Element, context: dict) -> str | None:
    chain = style_chain(context["styles"], paragraph_style(paragraph, context))
    merged = merged_properties([*(style.find(W + "pPr") for style in chain), paragraph.find(W + "pPr")])
    return fill_of(merged.get("shd"))


# ---------- B6：看不见的文字 ----------

def fill_of(shading: dict | None) -> str | None:
    if not shading:
        return None
    if shading.get("val") == "solid" and HEX.fullmatch(shading.get("color", "")):
        return shading["color"].upper()
    fill = shading.get("fill", "")
    return fill.upper() if HEX.fullmatch(fill) else None


def text_color(props: dict) -> str | None:
    """auto 由 Word 按底色自动取反差色，不算。"""
    color = props.get("color") or {}
    if color.get("themeColor") in WHITE_THEMES and "themeShade" not in color:
        return "FFFFFF"
    value = color.get("val", "")
    return value.upper() if HEX.fullmatch(value) else None


def close_colors(first: str, second: str) -> bool:
    return all(abs(int(first[i:i + 2], 16) - int(second[i:i + 2], 16)) <= COLOR_GAP for i in (0, 2, 4))


def number_value(props: dict, key: str) -> int | None:
    match = re.match(r"\d+", (props.get(key) or {}).get("val", ""))
    return int(match.group()) if match else None


def run_problems(props: dict, background: str) -> list[tuple[str, str]]:
    problems = []
    if property_enabled(props, "vanish") or property_enabled(props, "specVanish"):
        problems.append(("hidden", "有隐藏文字"))
    color = text_color(props)
    if color and close_colors(color, background):
        problems.append(("invisible", f"文字颜色 #{color} 和底色 #{background} 几乎一样"))
    size = number_value(props, "sz")
    if size is not None and size < MIN_HALF_POINTS:
        problems.append(("tiny", f"字号 {size / 2:g} 磅，小于 6 磅"))
    scale = number_value(props, "w")
    if scale is not None and scale < MIN_SCALE:
        problems.append(("squeezed", f"字符缩放 {scale}%，小于 50%"))
    return problems


def run_format_hits(name: str, root: ElementTree.Element, context: dict) -> list[dict]:
    """隐藏、同色、过小、过窄的文字；底色依次看 run 的突出显示和底纹、段落底纹、单元格底纹、页面颜色。"""
    page = fill_of({"fill": (attributes(root.find(W + "background")) or {}).get("color", "")}) or "FFFFFF"
    index = {id(paragraph): number for number, paragraph in enumerate(root.iter(W + "p"), 1)}
    hits = []
    for paragraph, run, text, cell_fill in text_runs(root):
        if not text.strip():
            continue
        props = run_properties(run, paragraph, context)
        background = (HIGHLIGHT.get((props.get("highlight") or {}).get("val", "")) or fill_of(props.get("shd"))
                      or paragraph_fill(paragraph, context) or cell_fill or page)
        for kind, problem in run_problems(props, background):
            number = index[id(paragraph)]
            hits.append(hit("B6", f"{kind}|{name}|{number}",
                            f"{part_label(name)}第 {number} 段{problem}（“{snippet(text)}”）：删掉，或改成正常的可见文字",
                            fixed=True))
    return hits


def paragraph_texts(root: ElementTree.Element) -> list[tuple[int, str]]:
    """每段自己的文字（文本框里的段落单独成段），带段号。"""
    index = {id(paragraph): number for number, paragraph in enumerate(root.iter(W + "p"), 1)}
    texts: dict[int, list[str]] = {}
    for paragraph, _, text, _ in text_runs(root):
        texts.setdefault(index[id(paragraph)], []).append(text)
    return [(number, "".join(parts)) for number, parts in sorted(texts.items())]


def instruction_hits(text: str, where: str, key: str) -> list[dict]:
    for pattern in INSTRUCTIONS:
        found = pattern.search(text)
        if found:
            return [hit("B6", f"instruction|{key}", f"{where}有面向评审系统的指令性文字（“{snippet(found.group())}”）："
                        "施组只写施工内容，删掉（Q13）", fixed=True)]
    return []


def story_instruction_hits(name: str, root: ElementTree.Element) -> list[dict]:
    hits = []
    for number, text in paragraph_texts(root):
        hits += instruction_hits(text, f"{part_label(name)}第 {number} 段", f"{name}|{number}")
    return hits


# ---------- B6：批注、修订、嵌入、外部内容 ----------

def field_codes(root: ElementTree.Element) -> list[str]:
    """域代码：复杂域按 begin/separate/end 配对拼起 instrText（可以嵌套），再加简单域。"""
    codes, stack = [], []
    for node in root.iter():
        if node.tag == W + "fldChar":
            kind = node.get(W + "fldCharType")
            if kind == "begin":
                stack.append([])
            elif kind == "separate" and stack and stack[-1] is not None:
                codes.append("".join(stack[-1]))
                stack[-1] = None
            elif kind == "end" and stack:
                top = stack.pop()
                if top is not None:
                    codes.append("".join(top))
        elif node.tag == W + "instrText" and stack and stack[-1] is not None:
            stack[-1].append(node.text or "")
    codes += [node.get(W + "instr", "") for node in root.iter(W + "fldSimple")]
    return [code.strip() for code in codes if code.strip()]


def field_names(parts: dict) -> list[tuple[str, str]]:
    return [(name, code.split()[0].upper()) for name, root in stories(parts) for code in field_codes(root)]


def markup_hits(parts: dict) -> list[dict]:
    """批注、修订、修订模式、文档变量、域里引用的外部内容。"""
    hits = []
    comments = parts["xml"].get("word/comments.xml")
    count = len(comments.findall(W + "comment")) if comments is not None else 0
    references = sum(1 for _, root in stories(parts) for _ in root.iter(W + "commentReference"))
    if count or references:
        hits.append(hit("B6", "comments", f"有 {max(count, references)} 条批注：在 Word 或 WPS 的审阅里全部删除后保存",
                        fixed=True))
    revised: dict[str, int] = {}
    for name, root in [*stories(parts), *((n, parts["xml"][n]) for n in ("word/styles.xml", "word/numbering.xml")
                                          if n in parts["xml"])]:
        for node in root.iter():
            label = REVISIONS.get(node.tag.removeprefix(W)) if node.tag.startswith(W) else None
            if label:
                revised[label] = revised.get(label, 0) + 1
    if revised:
        detail = "、".join(f"{label} {count}" for label, count in revised.items())
        hits.append(hit("B6", "revisions", f"有修订痕迹（{detail} 处）：在审阅里全部接受或拒绝，关掉修订后保存", fixed=True))
    settings = parts["xml"].get("word/settings.xml")
    tracking = None if settings is None else settings.find(W + "trackRevisions")
    if tracking is not None and property_enabled({"trackRevisions": attributes(tracking)}, "trackRevisions"):
        hits.append(hit("B6", "track-revisions", "修订模式开着，再改就会留下修订痕迹：在审阅里关掉修订后保存", fixed=True))
    if settings is not None and settings.findall(f"{W}docVars/{W}docVar"):
        hits.append(hit("B6", "doc-vars", "文档里存着文档变量（docVars，看不见的数据）：删掉后保存", fixed=True))
    for name, field in field_names(parts):
        if field in PULL_FIELDS:
            hits.append(hit("B6", f"field|{field}", f"{part_label(name)}有 {field} 域，内容从文档外读取："
                            "在 Word 里选中按 Ctrl+Shift+F9 转成普通内容", fixed=True))
    return hits


def relationship_targets(parts: dict, rels_name: str) -> list[ElementTree.Element]:
    root = parts["xml"].get(rels_name)
    return [] if root is None else root.findall(REL + "Relationship")


def resolve_target(rels_name: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    source_dir = posixpath.dirname(posixpath.dirname(rels_name))  # word/charts/_rels/x.rels → word/charts
    return posixpath.normpath(posixpath.join(source_dir, target))


def chart_workbooks(parts: dict) -> set[str]:
    """图表背后的 Excel 工作簿：Word 图表的数据源，不是可疑嵌入。"""
    books = set()
    for rels_name in parts["xml"]:
        if rels_name.startswith("word/charts/_rels/"):
            books |= {resolve_target(rels_name, rel.get("Target", "")) for rel in relationship_targets(parts, rels_name)
                      if rel.get("TargetMode") != "External" and rel.get("Type", "").endswith("/package")}
    return books


def object_hits(parts: dict) -> list[dict]:
    """嵌入的 OLE 对象、ActiveX、宏、外部文档块、子文档（图表的数据工作簿除外，它归 B5 查作者）。"""
    hits, books = [], chart_workbooks(parts)
    for name in parts["names"]:
        if name.startswith("word/embeddings/") and name not in books:
            hits.append(hit("B6", f"embedded|{name}", f"嵌着对象 {posixpath.basename(name)}：删掉，图表、表格改成图片或普通表格",
                            fixed=True))
        elif name.startswith("word/activeX/") or name.endswith(("vbaProject.bin", "vbaData.xml")):
            hits.append(hit("B6", f"active|{name}", f"带宏或 ActiveX 控件（{name}）：另存为不含宏的 .docx", fixed=True))
    for name, root in stories(parts):
        for tag, label in OBJECT_TAGS.items():
            if root.find(f".//{W}{tag}") is not None:
                hits.append(hit("B6", f"object|{name}|{tag}", f"{part_label(name)}有{label}：删掉或转成普通内容", fixed=True))
    return hits


def external_hits(parts: dict) -> tuple[list[dict], list[str]]:
    """指向文档外的关系：超链接交给 B5 查网址；附加模板的路径可能带电脑用户名，归 B5；其余归 B6。"""
    hits, links = [], []
    for rels_name in sorted(name for name in parts["xml"] if name.endswith(".rels")):
        for rel in relationship_targets(parts, rels_name):
            if rel.get("TargetMode") != "External":
                continue
            kind = rel.get("Type", "").rsplit("/", 1)[-1]
            if kind == "hyperlink":
                links.append(rel.get("Target", ""))
            elif kind == "attachedTemplate":
                hits.append(hit("B5", "attached-template", "附加了外部模板，模板路径可能带电脑用户名：在 Word 的"
                                "开发工具 → 文档模板里改回 Normal 后保存", fixed=True))
            else:
                hits.append(hit("B6", f"external|{rels_name}|{kind}", f"{rels_name} 有指向文档外的 {kind} 链接，"
                                "打开时会从别处读内容：改成嵌入或删掉", fixed=True))
    return hits, links


# ---------- B5：属性、封面、文本框、图片、链接 ----------

def element_text(root: ElementTree.Element | None, path: str, namespaces: dict | None = None) -> str:
    node = None if root is None else root.find(path, namespaces or {})
    return "" if node is None else "".join(node.itertext()).strip()


def custom_names(root: ElementTree.Element | None) -> list[str]:
    return [] if root is None else [prop.get("name", "") for prop in root.findall(CUSTOM + "property")]


def property_hits(parts: dict) -> list[dict]:
    """必须清空的属性（作者、单位等）判固定命中，--clean-properties 能清；可以有内容的属性查身份词。"""
    core, app = parts["xml"].get("docProps/core.xml"), parts["xml"].get("docProps/app.xml")
    hits = [hit("B5", f"core|{path}", f"文档属性“{label}”不为空：{CLEAN_HINT}", fixed=True)
            for path, label in CORE_PERSON if element_text(core, path, CORE_NS)]
    hits += [hit("B5", f"app|{tag}", f"文档属性“{label}”不为空：{CLEAN_HINT}", fixed=True)
             for tag, label in APP_FIXED if element_text(app, APP + tag)]
    extra = [name for name in custom_names(parts["xml"].get("docProps/custom.xml")) if name not in CUSTOM_ALLOWED]
    if extra:
        hits.append(hit("B5", "custom-properties", f"有自定义文档属性 {'、'.join(extra)}：{CLEAN_HINT}", fixed=True))
    people = parts["xml"].get("word/people.xml")
    if people is not None and people.findall(W15 + "person"):
        hits.append(hit("B5", "people", "word/people.xml 留着批注、修订作者的名单：删掉批注、处理完修订后，"
                        "在 Word 里勾选“保存时从文件属性中删除个人信息”再保存", fixed=True))
    for name, field in field_names(parts):
        if field in AUTHOR_FIELDS:
            hits.append(hit("B5", f"author-field|{name}|{field}", f"{part_label(name)}有 {field} 域，会显示作者或用户名："
                            "删掉这个域", fixed=True))
    return hits


def property_texts(parts: dict) -> list[tuple[str, str]]:
    """可以有内容、但不该带身份的属性：标题、主题、备注等，和模板名、各部分标题。"""
    core, app = parts["xml"].get("docProps/core.xml"), parts["xml"].get("docProps/app.xml")
    texts = [(f"文档属性“{label}”", element_text(core, path, CORE_NS)) for path, label in CORE_TEXT]
    texts.append(("文档属性“模板”", element_text(app, APP + "Template")))
    texts.append(("文档属性“各部分标题”", element_text(app, APP + "TitlesOfParts")))
    return [(where, text) for where, text in texts if text]


def is_heading1(paragraph: ElementTree.Element, context: dict) -> bool:
    if context["roles"].get(paragraph_style(paragraph, context)) == "Heading1":
        return True
    return xml_value(paragraph.find(f"{W}pPr/{W}outlineLvl")) == "0"


def front_matter(document: ElementTree.Element, context: dict) -> str:
    """第一个一级标题之前的正文：封面和目录页。目录条目是各项标题，不查。"""
    body = document.find(W + "body")
    lines = []
    for paragraph in [] if body is None else body.iter(W + "p"):
        if is_heading1(paragraph, context):
            break
        if not context["roles"].get(paragraph_style(paragraph, context), "").startswith("TOC"):
            lines.append("".join(node.text or "" for node in paragraph.iter(W + "t")))
    return "\n".join(lines)


def text_box_text(root: ElementTree.Element) -> str:
    lines = []
    for node in root.iter(W + "txbxContent"):
        lines += [text for _, text in paragraph_texts(node)]
    return "\n".join(dict.fromkeys(lines))  # 新旧两种格式各存一份时只算一次


def image_labels(parts: dict, headers: bool = True) -> list[tuple[str, str]]:
    """图片的名称、说明文字（Word 叫可选文字）：评审系统能读到，人看不见。headers=False 时不看页眉页脚的图片。"""
    labels = []
    for name, root in stories(parts):
        if not headers and HEADER_FOOTER.fullmatch(name):
            continue
        for node in root.iter():
            local = node.tag.rsplit("}", 1)[-1]
            if local in {"docPr", "cNvPr"}:
                labels += [(f"{part_label(name)}的图片{key}", node.get(key, "")) for key in ("name", "descr", "title")]
            elif local == "imagedata":
                labels.append((f"{part_label(name)}的图片标题", node.get("{urn:schemas-microsoft-com:office:office}title", "")))
    return [(where, text) for where, text in labels if text.strip()]


def located(hits: list[dict], where: str) -> list[dict]:
    return [{**entry, "match": f"{where}|{entry['match']}", "message": f"{where}：{entry['message']}"} for entry in hits]


def identity_scan(text: str, where: str, terms: list[dict] | None, patterns: bool = True) -> list[dict]:
    if not text.strip():
        return []
    found = identity_term_hits(text, terms or [], "")
    return located(found + (identity_pattern_hits(text) if patterns else []), where)


def header_hits(parts: dict, terms: list[dict] | None) -> list[dict]:
    """非暗标时页眉页脚可以有字，查身份词；有图片多半是公司标志，请用户确认。暗标的页眉页脚归 B3。"""
    hits = []
    for name, root in stories(parts):
        if not HEADER_FOOTER.fullmatch(name):
            continue
        hits += identity_scan("\n".join(text for _, text in paragraph_texts(root)), part_label(name), terms)
        if root.find(f".//{W}drawing") is not None or root.find(f".//{W}pict") is not None:
            hits.append(hit("B5", f"header-image|{name}", f"{part_label(name)}有图片，多半是公司标志：不是的，"
                            "向用户确认后说明理由放行"))
    return hits


def chart_book_hits(parts: dict) -> list[dict]:
    """图表的数据工作簿是个独立的 Excel 文件，它自己的作者、单位属性 --clean-properties 清不到。"""
    hits = []
    for name in sorted(chart_workbooks(parts)):
        try:
            book = load_parts(parts["embedded"].get(name, b""))
        except ValueError:
            continue
        if property_hits(book):
            hits.append(hit("B5", f"chart-book|{name}", f"图表的数据工作簿 {posixpath.basename(name)} 带作者或单位："
                            "在 Word 里右键图表 → 编辑数据，在 Excel 里清掉文件属性后保存，或把图表粘贴为图片", fixed=True))
    return hits


def identity_hits(parts: dict, docx_name: str, terms: list[dict] | None, blind: bool, links: list[str]) -> list[dict]:
    context = style_context(parts)
    document = parts["xml"].get("word/document.xml")
    hits = property_hits(parts) + chart_book_hits(parts)
    for where, text in property_texts(parts) + image_labels(parts, headers=not blind):  # 暗标页眉图片归 B3
        hits += identity_scan(text, where, terms)
    if document is not None:
        hits += identity_scan(front_matter(document, context), "封面和目录页", terms)
        hits += identity_scan(text_box_text(document), "正文的文本框", terms)
    for note in ("word/footnotes.xml", "word/endnotes.xml"):
        if note in parts["xml"]:
            hits += identity_scan("\n".join(text for _, text in paragraph_texts(parts["xml"][note])), part_label(note), terms)
    hits += [] if blind else header_hits(parts, terms)
    hits += identity_scan("\n".join(links), "超链接网址", terms, patterns=False)
    for name in sorted(n for n in parts["xml"] if re.fullmatch(r"customXml/item\d+\.xml", n)):
        hits += identity_scan(" ".join(parts["xml"][name].itertext()), f"自定义 XML（{name}）", terms)
    return hits + identity_scan(docx_name, "文件名", terms, patterns=False)


# ---------- W8：字体 ----------

def typeface(node: ElementTree.Element, tag: str) -> str:
    child = node.find(A + tag)
    return "" if child is None else child.get("typeface", "")


def theme_fonts(theme: ElementTree.Element | None) -> dict[str, str]:
    """主题字体槽 → 字体名：minorHAnsi → 正文西文字体，minorEastAsia → 正文中文字体（ea 为空时取简体中文的）。"""
    fonts: dict[str, str] = {}
    for scheme, prefix in (("majorFont", "major"), ("minorFont", "minor")):
        node = None if theme is None else theme.find(f".//{A}{scheme}")
        if node is None:
            continue
        latin = typeface(node, "latin")
        hans = next((font.get("typeface", "") for font in node.findall(A + "font") if font.get("script") == "Hans"), "")
        fonts.update({f"{prefix}Ascii": latin, f"{prefix}HAnsi": latin, f"{prefix}EastAsia": typeface(node, "ea") or hans})
    return fonts


def is_east_asian(char: str) -> bool:
    code = ord(char)
    return 0x2E80 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF or 0xFF00 <= code <= 0xFFEF


def run_fonts(props: dict, text: str, theme: dict[str, str]) -> set[str]:
    """按 run 里实际有的字符取字体槽：汉字用 eastAsia，ASCII 用 ascii，其他西文用 hAnsi。"""
    fonts = props.get("rFonts") or {}
    slots = [slot for slot, present in (
        ("ascii", any(ord(char) < 0x80 and not char.isspace() for char in text)),
        ("hAnsi", any(0x80 <= ord(char) < 0x2E80 for char in text)),
        ("eastAsia", any(is_east_asian(char) for char in text))) if present]
    names = {fonts.get(slot) or theme.get(fonts.get(slot + "Theme", ""), "") for slot in slots}
    return {FONT_ALIASES.get(name.strip(), name.strip()) for name in names if name and name.strip()}


def used_fonts(parts: dict) -> set[str]:
    context, theme = style_context(parts), theme_fonts(parts["xml"].get("word/theme/theme1.xml"))
    fonts: set[str] = set()
    for _, root in stories(parts):
        for paragraph, run, text, _ in text_runs(root):
            if text.strip():
                fonts |= run_fonts(run_properties(run, paragraph, context), text, theme)
    return fonts


def font_hits(parts: dict, format_fonts: set[str]) -> list[dict]:
    catalog = load_catalog().get("fonts", {})
    install = set(catalog.get("needs_install", []))
    bundled = WINDOWS_FONTS | set(catalog.get("system", [])) | set(catalog.get("latin", []))
    hits = []
    for font in sorted(used_fonts(parts)):
        if font in bundled:
            continue
        reason = "格式预设库标为需安装" if font in install else "不在 Windows 自带字体之列【推断】"
        chosen = "；这是项目确认的格式所用字体，招标文件要求的就写明不改理由" if font in format_fonts else ""
        hits.append(hit("W8", font, f"用了字体“{font}”（{reason}）：评审端没装会换成别的字体，版式和页数跟着变（Q8）{chosen}"))
    return hits


# ---------- 汇总 ----------

def scan_docx(docx_path: Path, *, terms: list[dict] | None, list_error: str = "", blind: bool = False,
              format_fonts: set[str] | None = None) -> list[dict]:
    """成品的 B6、B5、W8 原始命中；级别、编号由 check_qingtian_gates.finalize 统一补（第 0 项＝整份）。"""
    docx_path = docx_path.expanduser().resolve()
    parts = load_parts(docx_path.read_bytes())
    context = style_context(parts)
    hits = []
    for name, root in stories(parts):
        if name != "word/comments.xml":  # 批注整条删，不逐段查
            hits += run_format_hits(name, root, context) + story_instruction_hits(name, root)
    for where, text in property_texts(parts) + image_labels(parts):
        hits += instruction_hits(text, where, where)
    external, links = external_hits(parts)
    hits += markup_hits(parts) + object_hits(parts) + external
    if list_error or terms is None:
        hits += identity_term_hits("", terms, list_error)  # 清单缺失或有误只报一次
    hits += identity_hits(parts, docx_path.name, terms, blind, links)
    return hits + font_hits(parts, format_fonts or set())


def format_font_names(document_format: dict) -> set[str]:
    names = {str(document_format.get(field) or "") for field in (*FONT_FIELDS, "latin_font")}
    return {name for name in names if name}


def project_scan(project_dir: Path, docx_path: Path) -> dict:
    """按项目的身份词清单、轨道和锁定格式扫成品：{hits, track}。"""
    project_dir, state = load_project(project_dir)
    try:
        terms, list_error = load_identity_terms(project_dir), ""
    except ValueError as exc:
        terms, list_error = None, str(exc)
    document_format = state.get("document_format") or {}
    track = str((load_json(project_dir / RULE_CARD_FILE, "规则卡").get("track") or {}).get("value") or "")
    hits = scan_docx(docx_path, terms=terms, list_error=list_error, blind=bool(document_format.get("blind_mode")),
                     format_fonts=format_font_names(document_format))
    return {"hits": hits, "track": track}


# ---------- 清理文档属性 ----------

def blank_elements(data: bytes, paths: tuple[str, ...], namespaces: dict) -> bytes:
    root = etree.fromstring(data)
    for path in paths:
        for node in root.findall(path, namespaces):
            for child in list(node):
                node.remove(child)
            node.text = None
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def drop_custom_properties(data: bytes) -> bytes:
    root = etree.fromstring(data)
    for prop in root.findall(CUSTOM + "property"):
        if prop.get("name") not in CUSTOM_ALLOWED:
            root.remove(prop)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def cleaned_member(name: str, data: bytes) -> bytes:
    if name == "docProps/core.xml":
        return blank_elements(data, CLEAN_CORE, CORE_NS)
    if name == "docProps/app.xml":
        return blank_elements(data, tuple(f"app:{tag}" for tag, _ in APP_FIXED), {"app": APP[1:-1]})
    if name == "docProps/custom.xml":
        return drop_custom_properties(data)
    return data


def clean_properties(docx_path: Path) -> dict:
    """清空作者、单位等文档属性，只改 docProps/ 下三个部件，其余部件逐字节照搬（顺序、压缩方式不变）。

    已签名文件拒绝修改。先备份成 <成品>.clean-<时间>.bak；新文件写到同目录的临时文件，python-docx 能打开、属性确实清空才替换。
    """
    docx_path = docx_path.expanduser().resolve()
    if not docx_path.is_file():
        raise ValueError(f"成品不存在: {docx_path}")
    if docx_path.with_name(f"~${docx_path.name}").exists():
        raise ValueError("成品正在 Word 或 WPS 里打开：关掉后再清理")
    try:
        with zipfile.ZipFile(docx_path) as package:
            if any(name.lower().startswith("_xmlsignatures/") for name in package.namelist()):
                raise ValueError("DOCX 已有数字签名，请使用签章前的终稿清理属性")
    except zipfile.BadZipFile as exc:
        raise ValueError("DOCX 文件无法读取，请确认文件完整") from exc
    backup = docx_path.with_name(f"{docx_path.name}.clean-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak")
    shutil.copy2(docx_path, backup)
    temporary = docx_path.with_name(f".{docx_path.stem}.cleaning.docx")
    try:
        with zipfile.ZipFile(docx_path) as source, zipfile.ZipFile(temporary, "w") as target:
            for info in source.infolist():
                target.writestr(info, cleaned_member(info.filename, source.read(info.filename)))
        Document(str(temporary))
        left = property_hits(load_parts(temporary.read_bytes()))
        left = [entry for entry in left if entry["match"].startswith(("core|", "app|", "custom-"))]
        if left:
            raise ValueError(f"清理后仍有属性没清掉: {'；'.join(entry['message'] for entry in left)}")
        os.replace(temporary, docx_path)
    except Exception as exc:  # python-docx 打不开时抛的异常类型不固定；任何失败都不能动成品
        temporary.unlink(missing_ok=True)
        raise ValueError(f"清理失败，成品没动（备份 {backup.name}）: {exc}") from exc
    return {"docx": str(docx_path), "backup": str(backup)}


# ---------- 命令行 ----------

def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="qingtian-bid 门禁 B6/B5/W8：扫成品 DOCX 的隐藏内容、身份信息和字体。")
    parser.add_argument("docx_path", type=Path, help="成品 DOCX（output/施工组织设计.docx）。")
    parser.add_argument("--project", type=Path, help="项目目录；不给时从成品所在位置往上找。")
    parser.add_argument("--clean-properties", action="store_true",
                        help="清空作者、单位、自定义属性等文档属性（先备份），然后重新扫。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # 在函数里导入：编排脚本以后会反过来调用本模块，模块级互相导入会成环
    from check_qingtian_gates import finalize

    args = parse_args(argv)
    try:
        project = args.project or find_project_dir(args.docx_path)
        if project is None:
            raise ValueError(f"成品不在 qingtian-bid 项目里，用 --project 指定: {args.docx_path}")
        if args.clean_properties:
            cleaned = clean_properties(args.docx_path)
            print(f"已清空文档属性，备份在 {cleaned['backup']}。清理会改变成品的 sha256：重新运行 "
                  "validate_docx_format.py --final 和全部门禁。")
        result = project_scan(project, args.docx_path)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    hits = finalize(result["hits"], 0, result["track"])
    blocking = [entry for entry in hits if entry["level"] == "block"]
    for entry in hits:
        level = "阻断" if entry["level"] == "block" else "提示"
        print(f"- {level} {entry['gate']} [{entry['id']}] {entry['message']}"
              + (f"（{entry['count']} 处）" if entry["count"] > 1 else ""))
    print(f"阻断 {len(blocking)} 条。" if blocking else "成品清洁检查没有阻断项。")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
