"""Rule card fields for the 投标文件格式 chapter (bid_forms, bid_forms_diff): their validation and their views.

INPUT: a rule card dict; the extracted tender texts, through rule_card_fields.RefLookup and scan_bid_forms.scan_project.
OUTPUT: check_bid_forms() for validate_rule_card; bid_forms_sections() for rule-card.md.
POS: card layer beside rule_card_fields.py, imported by project_cards.py. Three things stop stage 2 here: a tender whose
     chapter cannot be found, a section the re-scan sees but the card dropped, and a 目录 vs 正文 difference with no decision
     from the user. Kind and field names must be written by a person; the script's hints do not count.
"""

from __future__ import annotations

import re
from pathlib import Path

from rule_card_fields import (
    UNSPECIFIED,
    RefLookup,
    cell,
    compact,
    field_head,
    has_text,
    is_empty,
    ref_issues,
    ref_text,
    rows_of,
    table_lines,
    text_list_ok,
)
from scan_bid_forms import FORM_FILES, forms_diff, same_title, scan_project


NOT_REQUIRED = "无需提供"
FILLED_FIELDS = "字段值"
PART_KINDS = (FILLED_FIELDS, "正文", "附件", NOT_REQUIRED)
LIST_KEYS = (("attachments", "attachments 要附的材料"), ("protected", "protected 不得改动处"))


def part_issues(part: object, row_id: str, label: str, lookup: RefLookup) -> list[str]:
    if not isinstance(part, dict):
        return [f"{label}：小节应为对象"]
    part_id = str(part.get("id") or "")
    name = f"{label} 小节 {part_id or '空'}"
    issues = [] if re.fullmatch(rf"{re.escape(row_id)}-\d+", part_id) else [f"{name}：编号须为 {row_id}-1 这样"]
    if not has_text(part.get("title")):
        issues.append(f"{name}：缺少小节名称 title")
    kind = part.get("kind")
    if kind not in PART_KINDS:
        issues.append(f"{name}：类型 kind 只能是 {'、'.join(PART_KINDS)}；对照原文写，脚本的 hints 只是提示")
    issues += kind_issues(part, kind, name)
    issues += [f"{name}：{key_label} 应为文字列表" for key, key_label in LIST_KEYS
               if not text_list_ok(part.get(key, []))]
    return issues + (ref_issues(part["ref"], name, lookup) if part.get("ref") else [])


def kind_issues(part: dict, kind: object, name: str) -> list[str]:
    """不提供要有依据；要填的要列字段，下游照这份逐项填。"""
    basis, fields = part.get("not_required_basis"), part.get("fields")
    if kind == NOT_REQUIRED:
        if not has_text(basis):
            return [f"{name}：无需提供要在 not_required_basis 写招标文件的依据（如勾选框 CB04）；没有依据的写用户原话，不代写"]
        return [f"{name}：无需提供就不用写字段 fields"] if not is_empty(fields) else []
    issues = [f"{name}：要提供的小节不写 not_required_basis"] if not is_empty(basis) else []
    if kind == FILLED_FIELDS and (not fields or not text_list_ok(fields)):
        issues.append(f"{name}：字段值类型要在 fields 列出字段名（文字列表）；hints.fields 是候选，对照原文核过再抄")
    return issues


def row_issues(row: dict, label: str, lookup: RefLookup) -> list[str]:
    issues = [] if has_text(row.get("title")) else [f"{label}：缺少节名 title"]
    if row.get("file") not in FORM_FILES:
        issues.append(f"{label}：file 只能是 {'、'.join(FORM_FILES)}")
    if row.get("in_toc") not in (True, False, None):
        issues.append(f"{label}：in_toc 写 true、false，封面或这个文件没有目录的写 null")
    parts = row.get("parts")
    if not isinstance(parts, list) or not parts:
        issues.append(f"{label}：parts 至少一个小节；没有小节的，列一个同名小节")
    else:
        issues += [issue for part in parts for issue in part_issues(part, str(row.get("id")), label, lookup)]
        ids = [part.get("id") for part in parts if isinstance(part, dict)]
        if len(ids) != len(set(ids)):
            issues.append(f"{label}：小节编号重复")
    return issues + ref_issues(row.get("ref"), label, lookup)


def form_row_issues(entry: dict, lookup: RefLookup) -> list[str]:
    rows = entry.get("value")
    if is_empty(rows):
        return ["投标文件格式：招标文件里没找到这一章（按标题找的，不限第几章）。硬停：告诉用户，查招标文件是否完整；"
                "这一章叫别的名字或脚本读不出来的，照原文逐节填 value"]
    if not isinstance(rows, list):
        return ["投标文件格式应为列表"]
    issues: list[str] = []
    seen: set[str] = set()
    for position, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            issues.append(f"投标文件格式第 {position} 行应为对象")
            continue
        row_id = str(row.get("id") or "")
        if not re.fullmatch(r"S\d{2,}", row_id) or row_id in seen:
            issues.append(f"投标文件格式第 {position} 行的编号须为 S01 这样且不重复（当前: {row_id or '空'}）")
        seen.add(row_id)
        issues += row_issues(row, f"投标文件格式 {row_id or position}", lookup)
    return issues


def diff_row_issues(entry: dict) -> list[str]:
    """用户的决定不代写（决策 4c-3A）。这里只查写了没有，写什么由用户说。"""
    rows = entry.get("value")
    if entry.get("basis") == UNSPECIFIED or is_empty(rows):
        return []
    if not isinstance(rows, list):
        return ["目录和正文的差异应为列表"]
    issues: list[str] = []
    seen: set[str] = set()
    for position, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            issues.append(f"目录和正文的差异第 {position} 行应为对象")
            continue
        row_id = str(row.get("id") or "")
        if not re.fullmatch(r"SD\d{2,}", row_id) or row_id in seen:
            issues.append(f"目录和正文的差异第 {position} 行的编号须为 SD01 这样且不重复（当前: {row_id or '空'}）")
        seen.add(row_id)
        if not has_text(row.get("decision")):
            issues.append(f"目录和正文的差异 {row_id}“{row.get('title')}”：还没有用户的决定。硬停：把差异和默认做法告诉用户，"
                          "用户说了才写进 decision")
    return issues


def has_row(rows: list[dict], file_name: str | None, title: str) -> bool:
    """文件名和节名都对上才算；节名允许人修过提取时断开的字，互相包含就算一节。"""
    return any((file_name is None or row.get("file") == file_name)
               and same_title(compact(row.get("title")), compact(title)) for row in rows)


def coverage_issues(card: dict, project_dir: Path) -> list[str]:
    """重扫一遍：节不能从表里消失，差异也不能，否则删一行就绕过了硬停。扫不出来的（人手填的）不比。"""
    rows = rows_of(card["bid_forms"])
    scan = scan_project(project_dir) if rows else None
    if scan is None:
        return []
    issues = [f"投标文件格式少了{form.name or ''}文件的“{section.title}”：招标文件正文有这一节，不能漏；不提供的写成无需提供"
              for form in scan.files for section in form.sections if not has_row(rows, form.name, section.title)]
    recorded = rows_of(card["bid_forms_diff"])
    issues += [f"目录和正文的差异少了{gap['file'] or ''}文件的“{gap['title']}”：招标文件的目录和正文确实不一致，要用户决定"
               for gap in forms_diff(scan) if not has_row(recorded, gap["file"], gap["title"])]
    return issues


def check_bid_forms(card: dict, project_dir: Path) -> list[str]:
    lookup = RefLookup(project_dir)
    return form_row_issues(card["bid_forms"], lookup) + diff_row_issues(card["bid_forms_diff"]) \
        + coverage_issues(card, project_dir)


# ---------- 视图 ----------

def part_text(part: object) -> str:
    if not isinstance(part, dict):
        return "—"
    return f"{part.get('title')}（{part.get('kind') or '类型待定'}）"


def row_cells(row: dict) -> list[str]:
    parts = row.get("parts") if isinstance(row.get("parts"), list) else []
    in_toc = {True: f"有（{row.get('toc_number')}）", False: "没有"}.get(row.get("in_toc"), "—")
    number = f"{row.get('number')}、" if row.get("number") else ""
    return [cell(row.get("id")), cell(row.get("file")), cell(f"{number}{row.get('title')}"), in_toc,
            cell("；".join(part_text(part) for part in parts)), ref_text(row.get("ref"))]


def diff_cells(row: dict) -> list[str]:
    return [cell(row.get("id")), cell(row.get("file")), cell(row.get("title")), cell(row.get("toc_number")),
            cell(row.get("body_number")), cell(row.get("default")), cell(row.get("decision") or "待用户决定")]


def bid_forms_sections(card: dict) -> list[str]:
    """rule-card.md 的第七节。按一级节列，用户按节确认（决策 D7）。"""
    return [*field_head("bid_forms", card["bid_forms"]),
            *table_lines(("编号", "文件", "节", "目录", "小节和类型", "定位"),
                         [row_cells(row) for row in rows_of(card["bid_forms"])]),
            *field_head("bid_forms_diff", card["bid_forms_diff"]),
            *table_lines(("编号", "文件", "节", "目录编号", "正文编号", "默认做法", "用户决定"),
                         [diff_cells(row) for row in rows_of(card["bid_forms_diff"])])]
