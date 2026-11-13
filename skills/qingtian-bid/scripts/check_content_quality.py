"""W6 prose-style gate of qingtian-bid: fragment lists, bracket stacking and tabularised body text.

迁移来源见 CHANGELOG《脚本来源》，相对来源的改动：
  * 只留碎片清单、「**引导词：**」堆砌、括号编号连续起段、单段多重括号四条文风规则（R16、R20），
    章内深度和★覆盖率去掉：篇幅由矩阵预算管（W5），★落点由 B9 管；
  * 原 HEADING_RE 只认 ## 到 ####，施组中间稿的开头段落在一级标题下面，这里从 # 起分节；
  * 新增正文表格化：表头和表题都不属于 R16 允许的表（机械设备、劳动力、物资、进度计划、
    质量控制点、危大工程、风险矩阵）时报警；
  * 不再自己读目录、写报告：check_qingtian_gates 逐项传入 output/实施方案/ 的中间稿文字，
    返回命中列表，命令行入口去掉。

INPUT: one item draft's Markdown text.
OUTPUT: w6_hits(text) -> [{gate: "W6", match, message}].
POS: style layer of the step-4 gates (design v1 §9 第 4a 步); thresholds are carried over unchanged, heuristics
     【推断】, hints only (W items never block, 决策 4a-2A).
"""

from __future__ import annotations

import re

from text_gates import LAYOUT_MARKER, TABLE_RULE, hit

HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$")
LIST_LINE_RE = re.compile(r"^[-*+]\s+\S")
# 行首「**引导词：**」+ 正文，如 `**保密承诺：** 我方承诺……`：不是列表行，会被当成正文段，从而绕过碎片
# 清单检测；一旦离开本 Skill 的渲染器（直接粘进 Word / 别的工具），星号会原样漏出。
LEAD_IN_BOLD_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.、]\s*)?\*\*[^*]{1,20}[:：]\*\*\s*\S")
# 连续用「（1）（2）（3）」起段，或在同一段塞入多组括号补充，容易形成机械说明书文风。
PAREN_NUMBER_PREFIX_RE = re.compile(r"^\s*[（(]\d{1,2}[）)]\s*")
FORMULA_LIKE_RE = re.compile(r"[=≥≤<>＋+*/×÷]")
# R16 允许做成表的内容：表头或表题里出现其中一个词才算【推断】
ALLOWED_TABLE_WORDS = ("机械", "设备", "劳动力", "工种", "物资", "材料", "进度", "横道", "网络", "控制点", "危大",
                       "危险性较大", "风险")


def is_prose_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped and not LIST_LINE_RE.match(stripped)
                and not stripped.startswith(("|", "#", "!", "<!--")))


def chinese_parenthesis_pairs(line: str) -> int:
    """只统计中文全角括号；英文公式和函数调用不纳入此文风检查。"""
    return min(line.count("（"), line.count("）"))


def parse_sections(md_text: str) -> list[dict]:
    """按 # 到 #### 标题分节，统计每节的列表行、引导词行和正文段。"""
    sections: list[dict] = []
    for line in md_text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            sections.append({"title": match.group(2).strip(), "body_lines": []})
        elif sections:
            sections[-1]["body_lines"].append(line)
    for section in sections:
        lines = section["body_lines"]
        section["list_lines"] = sum(1 for ln in lines if LIST_LINE_RE.match(ln.strip()))
        section["lead_in_bold_lines"] = sum(1 for ln in lines if LEAD_IN_BOLD_RE.match(ln))
        # 「**引导词：** 正文」不算成段论述，从 paragraph_lines 中剔除，否则会掩盖碎片文风
        section["paragraph_lines"] = sum(
            1 for ln in lines
            if ln.strip() and not LIST_LINE_RE.match(ln.strip()) and not LEAD_IN_BOLD_RE.match(ln)
            and not ln.strip().startswith(("|", "#", "!")) and not LAYOUT_MARKER.match(ln.strip()))
    return sections


def section_hits(md_text: str) -> list[dict]:
    hits = []
    for section in parse_sections(md_text):
        title = section["title"][:40]
        if section["list_lines"] >= 5 and section["paragraph_lines"] < 2:
            hits.append(hit("W6", f"fragment|{title}", f"疑似碎片清单文风（列表{section['list_lines']}行/正文段"
                            f"{section['paragraph_lines']}）：{title}——措施成段写（R16）"))
        if section["lead_in_bold_lines"] >= 4:
            hits.append(hit("W6", f"lead-in|{title}", f"「**引导词：**」式碎片文风（{section['lead_in_bold_lines']}处）："
                            f"{title}——改为自然段，或提升为独立小节标题"))
    return hits


def parenthesis_hits(md_text: str) -> list[dict]:
    lines = md_text.splitlines()
    numbered = sum(1 for line in lines if is_prose_line(line) and PAREN_NUMBER_PREFIX_RE.match(line))
    heavy = sum(1 for line in lines if is_prose_line(line) and chinese_parenthesis_pairs(line) >= 2
                and not FORMULA_LIKE_RE.search(line))
    hits = []
    if numbered >= 2:
        hits.append(hit("W6", "paren-number", f"括号编号连续起段（{numbered}处）——按主题拆成自然段或独立小节（R20）"))
    if heavy >= 1:
        hits.append(hit("W6", "paren-heavy", f"单段多重括号补充（{heavy}处）——把枚举直接写入句子、拆段或改用必要表格（R20）"))
    return hits


def table_blocks(md_text: str) -> list[tuple[str, str]]:
    """(表题, 表头)：表题取表格上方最近一个非空行。"""
    blocks, caption, in_table = [], "", False
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            if not in_table and not TABLE_RULE.match(stripped):
                blocks.append((caption, stripped))
            in_table = True
        else:
            in_table = False
            caption = stripped or caption
    return blocks


def table_hits(md_text: str) -> list[dict]:
    """正文表格化（R16）：只有天然表格化的内容可以做成表，措施一律成段写。"""
    return [hit("W6", f"table|{header[:40]}", f"表格“{header[:40]}”不属于可以做成表的内容（机械设备、劳动力、物资、"
                "进度计划、质量控制点、危大工程、风险矩阵）：措施成段写，不做措施控制表（R16）")
            for caption, header in table_blocks(md_text)
            if not any(word in caption + header for word in ALLOWED_TABLE_WORDS)]


def w6_hits(md_text: str) -> list[dict]:
    return section_hits(md_text) + parenthesis_hits(md_text) + table_hits(md_text)
