"""Stable row keys, content-only digests and old/new differences of a rule card (决策 D9, 第 2L 步).

INPUT: a rule card dict (analysis/rule-card.json or its confirmed snapshot analysis/rule-card.confirmed.json).
OUTPUT: rule_rows() splits a card into {row key: content}; rule_row_digests() gives each row a digest;
        row_content() and content_digest() for rows of other cards; row_changes() lists old and new values;
        change_lines() prints them; cites_issues() checks the `cites` of a downstream row.
POS: leaf module beneath project_cards.py, so nothing here may import the card layer. Downstream rows cite these keys
     through `cites`, and the change order reads the differences. Every value of a card must land in some row: a value
     no row carries could change without voiding anything, which is the one failure this module must not have.

行键：列表行用现有编号（QU01、CB01、KD01、OT01、AW01、PR01、M01、S01、SD01、PF01），投标文件格式的小节另有一行
（S01-1），评审内容用序号（review_items.3），单值字段用字段名（schedule）。列表字段自己也占一行（键是字段名），
存 basis 这类不属于任何一行的内容。
"""

from __future__ import annotations

import hashlib
import json
import re

REVIEW_FIELD = "review_items"
REVIEW_PREFIX = f"{REVIEW_FIELD}."
FORMS_FIELD = "bid_forms"
CITES_KEY = "cites"
# 行键只由编号、字段名和序号组成。资源卡的白名单收了 cites，手上没有规则卡时靠这条挡住姓名（决策 3b-1A）
ROW_KEY_SHAPE = re.compile(r"[A-Za-z0-9_.#-]+")
# 这些字段的 value 是一行一行的列表，每行带编号
ID_LIST_FIELDS = ("qualification", "checkboxes", "key_dates", "off_table", "award", "preliminary_review", "mandatory",
                  FORMS_FIELD, "bid_forms_diff", "profile")
# 不是规则内容：schema 是格式版本；addenda_changes 是核对更正用的候选，更正本身要落到相应字段
NOT_ROWS = ("schema", "addenda_changes")
# 出处和候选，哪一层都不算内容：招标文件换了定位、代理勾了核对，规则本身没变
IGNORED_KEYS = ("ref", "source", "candidates", "hints")
# checked 只在字段和行这一层表示"核对过"；勾选框 options 里的 checked 是原文勾没勾，属于内容
ROW_ONLY_IGNORED = "checked"
CHANGE_ADDED, CHANGE_REMOVED, CHANGE_EDITED = "新增", "删除", "修改"
TEXT_LIMIT = 120


def without_ignored(value: object) -> object:
    if isinstance(value, dict):
        return {key: without_ignored(item) for key, item in value.items() if key not in IGNORED_KEYS}
    if isinstance(value, list):
        return [without_ignored(item) for item in value]
    return value


def row_content(row: object) -> object:
    """一行里参与比较的内容。只有最外层的 checked 算核对标记。"""
    if not isinstance(row, dict):
        return row
    return without_ignored({key: item for key, item in row.items() if key != ROW_ONLY_IGNORED})


def content_digest(content: object) -> str:
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def add_row(rows: dict[str, object], key: str, row: object, fallback: str) -> None:
    """编号重复或没有编号的卡过不了校验，这里只保证不互相覆盖：覆盖了就有内容变了也看不出来。"""
    rows[fallback if not key or key in rows else key] = row_content(row)


def form_part_rows(rows: dict[str, object], row: dict) -> None:
    """小节单独一行，引用可以精确到小节；节这一行仍含全部小节，引用节就是引用整节。"""
    parts = row.get("parts")
    for position, part in enumerate(parts if isinstance(parts, list) else [], 1):
        key = str(part.get("id") or "") if isinstance(part, dict) else ""
        add_row(rows, key, part, f"{row.get('id')}#part{position}")


def list_rows(rows: dict[str, object], field: str, entry: dict) -> None:
    values = entry.get("value")
    if not isinstance(values, list):
        add_row(rows, field, entry, f"{field}#head")  # value 不是列表（留空、未规定）时整个字段算一行
        return
    add_row(rows, field, {key: item for key, item in entry.items() if key != "value"}, f"{field}#head")
    for position, row in enumerate(values, 1):
        fallback = f"{field}#{position}"
        if field == REVIEW_FIELD:
            key = f"{REVIEW_PREFIX}{row.get('no')}" if isinstance(row, dict) and row.get("no") is not None else ""
        else:
            key = str(row.get("id") or "") if isinstance(row, dict) else ""
        add_row(rows, key, row, fallback)
        if field == FORMS_FIELD and isinstance(row, dict):
            form_part_rows(rows, row)


def rule_rows(card: dict) -> dict[str, object]:
    """{行键: 内容}，按卡片里的顺序。没见过的字段也算一行：宁可多失效，不能漏失效。"""
    rows: dict[str, object] = {}
    for field, entry in card.items():
        if field in NOT_ROWS:
            continue
        if isinstance(entry, dict) and (field == REVIEW_FIELD or field in ID_LIST_FIELDS):
            list_rows(rows, field, entry)
        else:
            add_row(rows, field, entry, f"{field}#head")
    return rows


def rule_row_digests(card: dict) -> dict[str, str]:
    return {key: content_digest(content) for key, content in rule_rows(card).items()}


def row_changes(old_card: dict, new_card: dict) -> list[dict]:
    """两版规则卡的逐行差异：[{key, change, old, new}]，先按新卡的顺序列新增和修改，再列删除。"""
    before, after = rule_rows(old_card), rule_rows(new_card)
    changes = []
    for key, content in after.items():
        if key not in before:
            changes.append({"key": key, "change": CHANGE_ADDED, "old": None, "new": content})
        elif before[key] != content:
            changes.append({"key": key, "change": CHANGE_EDITED, "old": before[key], "new": content})
    return changes + [{"key": key, "change": CHANGE_REMOVED, "old": content, "new": None}
                      for key, content in before.items() if key not in after]


def cites_issues(row: dict, label: str, known: set[str] | None, what: str = "规则卡的行") -> list[str]:
    """下游一行的 cites（决策 D9-1A）：没写算依赖全部规则行，[] 才是不依赖，写了就必须认得。
    known 为 None 是手上还没有规则卡，只能查形状。"""
    if CITES_KEY not in row:
        return []
    cites = row[CITES_KEY]
    if not isinstance(cites, list) or not all(isinstance(key, str) and ROW_KEY_SHAPE.fullmatch(key) for key in cites):
        return [f"{label}：cites 应为行键列表（不依赖任何规则行写 []，没写算依赖全部）"]
    return [] if known is None else [f"{label}：cites 里的 {key} 不是{what}" for key in cites if key not in known]


def content_text(content: object, limit: int = TEXT_LIMIT) -> str:
    """一行内容的简短文字。单值字段只显示 value，basis 这些没变时不用看。"""
    shown = content.get("value") if isinstance(content, dict) and "value" in content else content
    text = shown if isinstance(shown, str) else json.dumps(shown, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[:limit] + "…"


def change_lines(changes: list[dict]) -> list[str]:
    return [f"- {entry['key']}（{entry['change']}）：{content_text(entry['old'])} → {content_text(entry['new'])}"
            for entry in changes]
