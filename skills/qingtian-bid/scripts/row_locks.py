"""Row-level confirmation locks of the fact card, the resource card and the response matrix (决策 D9, 第 2L 步).

INPUT: card dicts handed in by the caller; rule row keys and content comparison from rule_card_rows.py.
OUTPUT: card_rows() splits a card into {row key: row}; row_deps() says which upstream rows a row depends on, None meaning
        all of them; locked_rows() is what a confirmation records for its own rows; upstream_digests() is what the cards
        below lock; cited_contents() gives a writing item the content it depends on; affected_rows() and own_changes() say
        which rows a change voids.
POS: leaf module beneath project_cards.py and writing_gate.py, so nothing here reads files or imports the card layer.
     A row is voided only by what it depends on, so one changed rule row no longer sends a user back through every
     confirmation. The price of that is a wrong `cites: []` cannot be detected here: the change order's affected list and
     the stage-7 rerun are the backstops. When unsure the rules here void more rather than less: a row without `cites`
     depends on everything (决策 D9-1A).
"""

from __future__ import annotations

import re

from rule_card_rows import CITES_KEY, REVIEW_PREFIX, content_digest, row_content, rule_rows

RULE_INPUT = "rule_card"
FACT_INPUT = "fact_card"
RESOURCE_INPUT = "resource_card"
MATRIX_CARD = "response_matrix"
# 与 fact_resource_cards.SECTIONS 的键一致，测试核对；这里不能导入它（卡片层在上面）
RESOURCE_SECTIONS = ("managers", "machinery", "labor", "materials")
ROW_SECTIONS = {FACT_INPUT: ("facts",), RESOURCE_INPUT: RESOURCE_SECTIONS, MATRIX_CARD: ("items",)}
LOCKED_CARDS = tuple(ROW_SECTIONS)
FACT_ID = re.compile(r"F\d{2,}")


def card_rows(name: str, card: dict) -> dict[str, dict]:
    """{行键: 这一行}。事实、资源用编号，矩阵用序号。缺口、篇幅这些不是行，改了只算卡片本身被修改。"""
    key_name = "no" if name == MATRIX_CARD else "id"
    rows: dict[str, dict] = {}
    for section in ROW_SECTIONS[name]:
        values = card.get(section)
        for row in values if isinstance(values, list) else []:
            if isinstance(row, dict) and row.get(key_name) is not None:
                rows[str(row[key_name])] = row
    return rows


def text_keys(row: dict, key: str) -> list[str]:
    values = row.get(key)
    return [value for value in values if isinstance(value, str)] if isinstance(values, list) else []


def resource_deps(row: dict, cites: list[str] | None) -> dict[str, list[str] | None]:
    """物资引用的工程量事实总算依赖，写不写 cites 都一样。"""
    if cites is None:
        return {RULE_INPUT: None, FACT_INPUT: None}
    facts = [key for key in cites if FACT_ID.fullmatch(key)]
    quantity = [row["quantity_fact"]] if isinstance(row.get("quantity_fact"), str) else []
    return {RULE_INPUT: [key for key in cites if key not in facts], FACT_INPUT: list(dict.fromkeys([*facts, *quantity]))}


def matrix_deps(row: dict, cites: list[str] | None) -> dict[str, list[str] | None]:
    """本项的评审内容和落在本项的条款总算依赖：矩阵这一行就是为它们写的。"""
    own = [f"{REVIEW_PREFIX}{row.get('no')}", *text_keys(row, "mandatory")]
    return {RULE_INPUT: None if cites is None else list(dict.fromkeys([*own, *cites])),
            FACT_INPUT: text_keys(row, "facts"), RESOURCE_INPUT: text_keys(row, "resources")}


def row_deps(name: str, row: dict) -> dict[str, list[str] | None]:
    """{上游卡片: 依赖的行键}，None 是依赖全部。没写 cites 算依赖全部，[] 才是不依赖（决策 D9-1A）。"""
    cites = text_keys(row, CITES_KEY) if CITES_KEY in row else None
    if name == FACT_INPUT:
        return {RULE_INPUT: cites}
    return resource_deps(row, cites) if name == RESOURCE_INPUT else matrix_deps(row, cites)


def locked_rows(name: str, card: dict) -> dict[str, dict]:
    """确认时记下的每一行：自身内容的指纹和它的依赖。"""
    return {key: {"digest": content_digest(row_content(row)), "deps": row_deps(name, row)}
            for key, row in card_rows(name, card).items()}


def upstream_contents(name: str, card: dict | None) -> dict[str, object]:
    """下游能锁的上游内容。上游行里的 cites 是它自己的依赖声明，改了不该连累引用它的行。"""
    if card is None:
        return {}
    if name == RULE_INPUT:
        return rule_rows(card)
    return {key: {field: value for field, value in row_content(row).items() if field != CITES_KEY}
            for key, row in card_rows(name, card).items()}


def upstream_digests(name: str, card: dict | None) -> dict[str, str]:
    return {key: content_digest(content) for key, content in upstream_contents(name, card).items()}


def cited_contents(name: str, card: dict | None, keys: list[str] | None) -> dict[str, object]:
    contents = upstream_contents(name, card)
    return contents if keys is None else {key: contents.get(key) for key in keys}


def changed_keys(recorded: dict[str, str], current: dict[str, str]) -> set[str]:
    """改了、加了、删了的行都算变。"""
    return {key for key in recorded.keys() | current.keys() if recorded.get(key) != current.get(key)}


def affected_rows(rows: dict[str, dict], input_name: str, recorded: dict[str, str], current: dict[str, str]) -> list[str]:
    """上游这张卡变了之后，下游失效的行。没人引用的上游行变了，一行也不失效。"""
    changed = changed_keys(recorded, current)
    if not changed:
        return []
    hit = []
    for key, lock in rows.items():
        deps = lock["deps"].get(input_name, [])
        if deps is None or changed & set(deps):
            hit.append(key)
    return hit


def own_changes(name: str, card: dict, rows: dict[str, dict]) -> list[str]:
    """卡片自身改动过的行，含删掉的。"""
    current = locked_rows(name, card)
    changed = [key for key, lock in current.items() if (rows.get(key) or {}).get("digest") != lock["digest"]]
    return changed + [key for key in rows if key not in current]
