# -*- coding: utf-8 -*-
"""参考封面克隆与字段替换工具。"""
from __future__ import annotations

import json
import re
import tempfile
import uuid
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from lxml.etree import QName


WORD_DOCX_FORMAT = 16
WPS_PROG_ID = "KWPS.Application"
WORD_PROG_ID = "Word.Application"
PAGE_BREAK = "\x0c"


def convert_legacy_doc(path: str, cache_dir: str | None = None) -> str:
    """用 Word/WPS COM 只读打开旧 .doc，并另存为临时 .docx。"""
    source = Path(path).resolve()
    target_dir = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "bid-document-builder"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}-{uuid.uuid4().hex}.docx"

    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("解析旧 .doc 需要 pywin32；请安装依赖或先另存为 .docx。") from exc

    pythoncom.CoInitialize()
    app = document = None
    last_error: Exception | None = None
    try:
        # WPS 对其生成的旧式中文 .doc 兼容性更稳定；不可用时再回退 Word。
        for prog_id in (WPS_PROG_ID, WORD_PROG_ID):
            try:
                app = win32com.client.DispatchEx(prog_id)
                break
            except Exception as exc:  # pragma: no cover - 取决于本机 Office/WPS
                last_error = exc
        if app is None:
            raise RuntimeError(
                "未检测到可用的 Microsoft Word 或 WPS COM。请先把参考 .doc 另存为 .docx。"
            ) from last_error
        app.Visible = False
        app.DisplayAlerts = 0
        # 让 COM 接收系统真实路径对象，避免中文文件名在部分宿主中经 UTF-8/ANSI 往返损坏。
        document = app.Documents.Open(str(source), ReadOnly=True)
        document.SaveAs2(str(target), FileFormat=WORD_DOCX_FORMAT)
        document.Close(False)
        document = None
        return str(target)
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def prepare_reference_docx(path: str | None, cache_dir: str | None = None) -> str | None:
    if not path:
        return None
    suffix = Path(path).suffix.lower()
    if suffix == ".docx":
        return str(Path(path).resolve())
    if suffix == ".doc":
        return convert_legacy_doc(path, cache_dir)
    raise RuntimeError(f"封面克隆仅支持 .doc/.docx 参考文件，当前格式为 {suffix or '未知'}。")


def _body_children(doc: Document) -> list:
    return [child for child in doc.element.body if child.tag != qn("w:sectPr")]


def _has_explicit_page_break(element) -> bool:
    for br in element.iter(qn("w:br")):
        if br.get(qn("w:type")) == "page":
            return True
    for text in element.iter(qn("w:t")):
        if text.text and PAGE_BREAK in text.text:
            return True
    return False


def _text(element) -> str:
    return "".join(node.text or "" for node in element.iter(qn("w:t"))).strip()


def _attr(node, name: str):
    return node.get(qn(name)) if node is not None else None


def _half_points(value: str | None) -> float | None:
    return round(int(value) / 2, 2) if value and value.isdigit() else None


def _run_style(run) -> dict:
    r_pr = run.find(qn("w:rPr"))
    fonts = r_pr.find(qn("w:rFonts")) if r_pr is not None else None
    size = r_pr.find(qn("w:sz")) if r_pr is not None else None
    color = r_pr.find(qn("w:color")) if r_pr is not None else None
    spacing = r_pr.find(qn("w:spacing")) if r_pr is not None else None
    return {
        "text": _text(run),
        "font_ascii": _attr(fonts, "w:ascii"),
        "font_east_asia": _attr(fonts, "w:eastAsia"),
        "font_hansi": _attr(fonts, "w:hAnsi"),
        "size_pt": _half_points(_attr(size, "w:val")),
        "bold": r_pr.find(qn("w:b")) is not None if r_pr is not None else None,
        "italic": r_pr.find(qn("w:i")) is not None if r_pr is not None else None,
        "color": _attr(color, "w:val"),
        "character_spacing_twips": _attr(spacing, "w:val"),
    }


def _image_style(doc: Document, element, paragraph_index: int) -> list[dict]:
    images: list[dict] = []
    for node in element.iter():
        local = QName(node).localname
        if local not in ("drawing", "pict"):
            continue
        rel_id = None
        for descendant in node.iter():
            rel_id = descendant.get(qn("r:embed")) or descendant.get(qn("r:id"))
            if rel_id:
                break
        target = None
        if rel_id and rel_id in doc.part.rels:
            target = doc.part.rels[rel_id].target_ref
        extent = next((item for item in node.iter() if QName(item).localname == "extent"), None)
        shape = next((item for item in node.iter() if QName(item).localname == "shape"), None)
        crop = next((item for item in node.iter() if QName(item).localname == "imagedata"), None)
        item = {
            "paragraph_index": paragraph_index,
            "kind": local,
            "relationship_id": rel_id,
            "target": target,
        }
        if extent is not None:
            item["width_pt"] = round(int(extent.get("cx")) / 12700, 2)
            item["height_pt"] = round(int(extent.get("cy")) / 12700, 2)
        if shape is not None:
            item["vml_style"] = shape.get("style")
            item["alt"] = shape.get("alt")
        if crop is not None:
            item["crop_left"] = crop.get("cropleft")
            item["crop_right"] = crop.get("cropright")
            item["crop_top"] = crop.get("croptop")
            item["crop_bottom"] = crop.get("cropbottom")
        images.append(item)
    return images


def _first_page_count_by_com(path: str) -> int | None:
    """返回第一页包含的 body 顶层元素数；COM 不可用时交由启发式兜底。"""
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return None

    pythoncom.CoInitialize()
    app = document = None
    try:
        for prog_id in (WPS_PROG_ID, WORD_PROG_ID):
            try:
                app = win32com.client.DispatchEx(prog_id)
                break
            except Exception:
                continue
        if app is None:
            return None
        app.Visible = False
        app.DisplayAlerts = 0
        document = app.Documents.Open(str(Path(path).resolve()), ReadOnly=True)
        paragraph_count = 0
        for index in range(1, document.Paragraphs.Count + 1):
            paragraph = document.Paragraphs.Item(index)
            if paragraph.Range.Information(3) != 1:  # wdActiveEndPageNumber
                break
            paragraph_count += 1
        return paragraph_count or None
    except Exception:
        return None
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def detect_cover_element_count(doc: Document, source_path: str | None = None) -> tuple[int, str]:
    children = _body_children(doc)
    if source_path:
        by_com = _first_page_count_by_com(source_path)
        if by_com and by_com <= len(children):
            return by_com, "com-page"

    for index, child in enumerate(children, 1):
        if _has_explicit_page_break(child):
            return index, "explicit-page-break"

    for index, child in enumerate(children):
        text = _text(child)
        if index >= 3 and re.fullmatch(r"目\s*录", text):
            return index, "toc-heading"
        if index >= 3 and re.match(r"^(特别提醒|重要提示|温馨提示)", text):
            return index, "post-cover-heading"

    # 兜底只保留到日期/编制单位附近，避免把整篇参考正文带入新文件。
    last_signal = 0
    signal = re.compile(r"(?:20\d{2}|202[\dXx]|年.{0,6}月.{0,6}日|招标|采购).{0,12}(?:公司|中心|单位|日)?$")
    for index, child in enumerate(children[:30], 1):
        if signal.search(_text(child)):
            last_signal = index
    return max(last_signal, min(14, len(children))), "content-heuristic"


def clone_cover(source: Document, target: Document, count: int) -> None:
    """把参考首页完整复制到空目标，包括段落、图片、表格及引用关系。"""
    target_part = target.part
    source_part = source.part
    relationship_map: dict[str, str] = {}

    def remap_relationships(element) -> None:
        for node in element.iter():
            for attr in (qn("r:id"), qn("r:embed"), qn("r:link")):
                old_id = node.get(attr)
                if not old_id or old_id not in source_part.rels:
                    continue
                if old_id not in relationship_map:
                    rel = source_part.rels[old_id]
                    if old_id in target_part.rels:
                        existing = target_part.rels[old_id]
                        if existing.reltype == rel.reltype and existing.target_ref == rel.target_ref:
                            relationship_map[old_id] = old_id
                            node.set(attr, old_id)
                            continue
                    if rel.is_external:
                        new_id = target_part.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
                    else:
                        new_id = target_part.relate_to(rel.target_part, rel.reltype)
                    relationship_map[old_id] = new_id
                node.set(attr, relationship_map[old_id])

    target_body = target.element.body
    insert_at = len(target_body) - 1 if target_body.sectPr is not None else len(target_body)
    for child in _body_children(source)[:count]:
        copied = deepcopy(child)
        remap_relationships(copied)
        target_body.insert(insert_at, copied)
        insert_at += 1


def copy_first_section_page_setup(source: Document, target: Document) -> None:
    src_section = source.sections[0]
    dst_section = target.sections[0]
    for attr in (
        "page_width", "page_height", "orientation", "left_margin", "right_margin",
        "top_margin", "bottom_margin", "gutter", "header_distance", "footer_distance",
    ):
        setattr(dst_section, attr, getattr(src_section, attr))
    dst_section.different_first_page_header_footer = True


def _iter_runs(doc: Document, count: int):
    for child in _body_children(doc)[:count]:
        if child.tag == qn("w:p"):
            for run in child.iter(qn("w:r")):
                yield run
        elif child.tag == qn("w:tbl"):
            for run in child.iter(qn("w:r")):
                yield run


def collect_cover_slot_values(doc: Document, count: int) -> list[str]:
    """收集封面上适合展示给用户确认的原始字段值。"""
    candidates: list[str] = []
    patterns = (
        re.compile(r"[\[【][^\]】]{1,40}[\]】]"),
        re.compile(r"(?:项目|采购|招标)(?:编号|名称)[：:].{1,60}"),
        re.compile(r"20(?:\d{2}|2[Xx])年.{0,12}月.{0,12}日"),
    )
    for child in _body_children(doc)[:count]:
        text = _text(child)
        for pattern in patterns:
            for match in pattern.findall(text):
                value = match.strip()
                if value and value not in candidates:
                    candidates.append(value)
    return candidates


def replace_cover_fields(doc: Document, count: int, values: dict[str, str]) -> dict[str, str]:
    """仅在首页按旧值/槽位做等值替换；不重建 run，从而保留原字体和段落布局。"""
    replacements: dict[str, str] = {}
    normalized = {str(key).strip(): str(value) for key, value in values.items() if str(value).strip()}
    aliases = {
        "document_title": ["[文件名称]", "【文件名称】", "竞争性磋商文件", "招标文件", "采购文件"],
        "project_code": ["[项目编号]", "【项目编号】"],
        "project_name": ["[项目名称]", "【项目名称】"],
        "issuer": ["[编制单位]", "【编制单位】", "[采购代理机构]", "【采购代理机构】"],
        "date": ["202X年XX月XX日", "202x年xx月xx日", "[日期]", "【日期】"],
    }
    for key, candidates in aliases.items():
        if key in normalized:
            for old in candidates:
                replacements.setdefault(old, normalized[key])
    for key, value in normalized.items():
        if key not in aliases:
            replacements[key] = value

    # 对没有显式槽位的参考封面，按语义识别整行旧值。
    cover_lines = [_text(child) for child in _body_children(doc)[:count] if child.tag == qn("w:p")]
    if "issuer" in normalized:
        for line in reversed(cover_lines):
            if re.search(r"(?:公司|中心|委员会|研究院|大学|采购人|招标人)$", line) and not re.search(
                r"(?:项目编号|项目名称|招标文件|采购文件|磋商文件)", line
            ):
                replacements.setdefault(line, normalized["issuer"])
                break
    if "date" in normalized:
        for line in cover_lines:
            if re.fullmatch(r"20(?:\d{2}|2[Xx])年.{0,12}月.{0,12}日", line):
                replacements.setdefault(line, normalized["date"])
    if "document_title" in normalized:
        for line in cover_lines:
            if re.fullmatch(r".{0,12}(?:招标文件|采购文件|磋商文件)", line):
                replacements.setdefault(line, normalized["document_title"])

    hits: dict[str, str] = {}
    for run in _iter_runs(doc, count):
        text_nodes = list(run.iter(qn("w:t")))
        for text_node in text_nodes:
            original = text_node.text or ""
            updated = original
            for old, new in replacements.items():
                if old in updated:
                    updated = updated.replace(old, new)
                    hits[old] = new
            text_node.text = updated

    # 有些封面值被 Word 拆成多个 run；用段落级替换补齐，并沿用首个文本 run 的格式。
    for child in _body_children(doc)[:count]:
        if child.tag != qn("w:p"):
            continue
        full_text = _text(child)
        if not full_text:
            continue
        updated = full_text
        for old, new in replacements.items():
            if old in updated:
                updated = updated.replace(old, new)
                hits[old] = new
        if updated == full_text:
            continue
        text_nodes = list(child.iter(qn("w:t")))
        if text_nodes:
            text_nodes[0].text = updated
            for text_node in text_nodes[1:]:
                text_node.text = ""
    return hits


def extract_cover_style(reference_path: str, output_json: str | None = None) -> dict:
    prepared = prepare_reference_docx(reference_path)
    doc = Document(prepared)
    count, boundary = detect_cover_element_count(doc, prepared)
    children = _body_children(doc)[:count]
    paragraphs = []
    images: list[dict] = []
    for index, child in enumerate(children, 1):
        if child.tag == qn("w:p"):
            p_pr = child.find(qn("w:pPr"))
            spacing = p_pr.find(qn("w:spacing")) if p_pr is not None else None
            jc = p_pr.find(qn("w:jc")) if p_pr is not None else None
            indent = p_pr.find(qn("w:ind")) if p_pr is not None else None
            paragraphs.append({
                "index": index,
                "text": _text(child),
                "alignment": jc.get(qn("w:val")) if jc is not None else None,
                "line": spacing.get(qn("w:line")) if spacing is not None else None,
                "line_rule": spacing.get(qn("w:lineRule")) if spacing is not None else None,
                "space_before_twips": _attr(spacing, "w:before"),
                "space_after_twips": _attr(spacing, "w:after"),
                "left_indent_twips": _attr(indent, "w:left"),
                "right_indent_twips": _attr(indent, "w:right"),
                "first_line_twips": _attr(indent, "w:firstLine"),
                "hanging_twips": _attr(indent, "w:hanging"),
                "runs": [_run_style(run) for run in child.findall(qn("w:r"))],
            })
            images.extend(_image_style(doc, child, index))
    section = doc.sections[0]
    report = {
        "reference": str(Path(reference_path).resolve()),
        "prepared_docx": prepared,
        "boundary_method": boundary,
        "cover_element_count": count,
        "page": {
            "width_pt": round(section.page_width.pt, 2),
            "height_pt": round(section.page_height.pt, 2),
            "left_margin_pt": round(section.left_margin.pt, 2),
            "right_margin_pt": round(section.right_margin.pt, 2),
            "top_margin_pt": round(section.top_margin.pt, 2),
            "bottom_margin_pt": round(section.bottom_margin.pt, 2),
        },
        "paragraphs": paragraphs,
        "images": images,
        "image_count": len(images),
        "first_page_header_footer": {
            "different_first_page": bool(section.different_first_page_header_footer),
            "header_text": "\n".join(p.text for p in section.first_page_header.paragraphs).strip(),
            "footer_text": "\n".join(p.text for p in section.first_page_footer.paragraphs).strip(),
        },
        "cover_slots": collect_cover_slot_values(doc, count),
    }
    if output_json:
        output = Path(output_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def save_reference_cover_template(reference_path: str, output_docx: str) -> dict:
    prepared = prepare_reference_docx(reference_path)
    source = Document(prepared)
    target = Document()
    for child in list(target.element.body):
        if child.tag != qn("w:sectPr"):
            target.element.body.remove(child)
    count, boundary = detect_cover_element_count(source, prepared)
    copy_first_section_page_setup(source, target)
    clone_cover(source, target, count)
    output = Path(output_docx)
    output.parent.mkdir(parents=True, exist_ok=True)
    target.save(output)
    return {"output": str(output.resolve()), "cover_element_count": count, "boundary_method": boundary}


def load_cover_values(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise RuntimeError("--cover-data 必须是 JSON 对象。")
    return {str(key): str(value) for key, value in payload.items()}
