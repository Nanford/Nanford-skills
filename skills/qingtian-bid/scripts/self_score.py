"""模拟青天的自评：评分标准、评审材料、评分记录和自评报告（2026-11-09 用户定 1A、2A、3A、4A）。

INPUT: <project>/project-state.json；analysis/rule-card.json（评审内容、档次原文）；analysis/extraction-report.json 和
       它列出的招标文件提取文本（ref 回查）；output/施工组织设计.docx；review/gate-report.json（经
       final_gate.report_issues）；review/自评/评分标准.json；--record 指向的评分表 JSON。
OUTPUT: review/自评/评分标准.json（--init-standard 出候选）；评审材料.md 和 评分-待填.json（--packet）；
        自评记录.json 和 自评报告.md（--record）；self_score_summary() 给进度摘要的一行；命令行。
POS: 阶段 7 之后可选的一步，不是门禁：不进任何阶段的完成条件，不进门禁的 ready，也不挡任何确认。分数是模拟的
     【推断】：脚本只按招标文件的评分标准和导则 2.2.2 的打分规则核对格式和边界，总分由脚本算；稿子好不好由独立
     评审人（新会话或子代理）判断，做法见 references/self-score.md。只评本 Skill 出的、过了阶段 7 的成品（2A、3A）；
     评外来标书、拿真实得分校准是以后的事（3B）。类人评审预演（rehearsal.py）仍然不出分数。

review/自评/评分标准.json（招标文件怎么打分，对照原文核实后 checked 改 true）:
  {"schema": "qingtian-self-score-standard/1",
   "units": [{"id": "U1", "name": 评审因素原文, "points": 分值, "items": [评审内容编号, ...],
              "method": 区间|固定分值, "bands": [{"name", "low", "high", "low_closed", "high_closed"}]（区间），
              "values": [分值, ...]（固定分值）, "criteria_text": 评分标准原文,
              "points_ref": ref, "criteria_ref": ref, "checked": bool}]}
  示范文本是一个评审因素（施工组织设计 100 分）整体打分，各项评审内容都归它；逐项给分值的招标文件拆成多个。
评分表（--record 的输入，--packet 出空表）:
  {"docx_sha256", "reviewer": 新会话|子代理,
   "items": [{"no", "title"?, "provided", "band", "score", "evidence": [成品原文], "reason", "full_reason",
              "lost": [失分点], "fix": [怎么改]}],
   "units": [{"id", "band", "score", "reason", "full_reason"}]（只写含多项评审内容、整体打分的评审因素）}
review/自评/自评记录.json:
  {"schema": "qingtian-self-score/1", "docx_sha256", "standard_sha256", "recorded_at", "reviewer", "items",
   "units": [{"id", "name", "points", "band", "score", "reason", "full_reason"}], "total", "total_points"}
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

from docx_effective_format import W
from final_gate import report_issues
from project_cards import FINISHED_DOCX, RULE_CARD_FILE, file_sha256, load_json, load_project, now_text
from response_matrix import item_heading
from rule_card_fields import RefLookup, cell, has_text, ref_issues, ref_text, tender_outputs
from scan_docx_hygiene import is_heading1, load_parts, style_context
from tender_text import TextIndex, build_index, find_all, ref_at
from text_gates import compact

SELF_SCORE_DIR = "review/自评"
STANDARD_FILE = f"{SELF_SCORE_DIR}/评分标准.json"
PACKET_FILE = f"{SELF_SCORE_DIR}/评审材料.md"
BLANK_FILE = f"{SELF_SCORE_DIR}/评分-待填.json"
RECORD_FILE = f"{SELF_SCORE_DIR}/自评记录.json"
REPORT_FILE = f"{SELF_SCORE_DIR}/自评报告.md"
FACT_VIEW = "analysis/project-facts.md"
GUIDE = "references/self-score.md"
STANDARD_SCHEMA = "qingtian-self-score-standard/1"
RECORD_SCHEMA = "qingtian-self-score/1"
# 写稿的会话看过矩阵和中间稿，评自己的稿有盲区；分数比预演的薄弱点更容易被带偏，所以只认独立的评审人
REVIEWERS = ("新会话", "子代理")
RANGE_METHOD, VALUE_METHOD = "区间", "固定分值"  # 导则 2.2.2 方法 1、方法 2
METHODS = (RANGE_METHOD, VALUE_METHOD)
NOT_PROVIDED = "未提供"
SIMULATED = "模拟，不是青天的评分"
# 导则 2.2.2 方法 1：评分在该项分值 60% 及以下、90% 及以上的，须提出充足理由；方法 2：100% 和 0 分须写明充足理由
LOW_SHARE, HIGH_SHARE = 0.6, 0.9
EPSILON = 1e-9
MIN_QUOTE_CHARS, MAX_QUOTE_CHARS = 6, 200
MAX_REASON_CHARS = 400
MAX_ENTRY_CHARS = 200
# 自评只说得分理由和失分点，不预测入围和中标（不承诺分数）。只抓肯定式的说法，"入围后复核""中标后进场"不算
PROMISE_WORDS = re.compile(
    r"稳了|稳拿|稳进|稳中|必中|必进|包中|十拿九稳"
    r"|(?:能|可以|可|肯定|一定|准能|保证)(?:中标|入围|进入?前\s*[0-9一二三四五六七八九十]+\s*名?)"
    r"|保证(?:得分|高分|优秀)")
SHEET_FIELDS = {"docx_sha256", "reviewer", "items", "units"}
RECORD_ITEM_FIELDS = ("no", "provided", "band", "score", "evidence", "reason", "full_reason", "lost", "fix")
ITEM_FIELDS = {"title", *RECORD_ITEM_FIELDS}
UNIT_FIELDS = {"id", "band", "score", "reason", "full_reason"}
LIST_LABELS = {"lost": "失分点", "fix": "怎么改"}
DONE, STALE, UNREADABLE, NOT_DONE = "已做", "要重评", "记录读不出", "未做"
# 示范文本的档次写法"一般得0分＜F≤60分"；只用来出候选，核实靠人对原文
BAND_TEXT = re.compile(r"(?P<name>[一-鿿]{2,4}?)得?(?P<low>\d+(?:\.\d+)?)分?(?P<lo>[＜<≤])F"
                       r"(?P<hi>[＜<≤])(?P<high>\d+(?:\.\d+)?)分?")
POINTS_TEXT = r"施工组织设计[：:，,（(]?(\d+(?:\.\d+)?)分"
MAX_FACTOR_CHARS = 1200  # 评审因素那句到档次那句之间，示范文本是十项评审内容加一句"包括但不限于"


# ---------- 数字和档次 ----------

def is_number(value: object) -> bool:
    """分值和得分：不收 true/false，最多两位小数（示范文本 3.2.2：技术得分保留小数点后两位）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    return abs(round(value, 2) - value) < EPSILON


def number_text(value: float) -> str:
    """100.0 写成 100，85.50 写成 85.5。"""
    text = format(round(value, 2), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def to_number(text: str) -> int | float:
    value = float(text)
    return int(value) if value.is_integer() else value


def band_text(band: dict) -> str:
    low_mark = "≤" if band["low_closed"] else "＜"
    high_mark = "≤" if band["high_closed"] else "＜"
    return f"{number_text(band['low'])}{low_mark}F{high_mark}{number_text(band['high'])}"


def in_band(band: dict, score: float) -> bool:
    above = score >= band["low"] if band["low_closed"] else score > band["low"]
    below = score <= band["high"] if band["high_closed"] else score < band["high"]
    return above and below


def needs_full_reason(unit: dict, score: float) -> bool:
    points = unit["points"]
    if unit["method"] == VALUE_METHOD:
        return abs(score - points) < EPSILON or abs(score) < EPSILON
    return score <= points * LOW_SHARE + EPSILON or score >= points * HIGH_SHARE - EPSILON


def full_reason_rule(unit: dict) -> str:
    if unit["method"] == VALUE_METHOD:
        return "评为满分或 0 分，要写充足理由 full_reason（导则 2.2.2 方法 2）"
    return "评分在分值的 60% 及以下或 90% 及以上，要写充足理由 full_reason（导则 2.2.2 方法 1）"


def scale_text(unit: dict) -> str:
    if unit["method"] == VALUE_METHOD:
        return "、".join(number_text(value) for value in unit["values"]) + " 分（未提供的 0 分）"
    return "；".join(f"{band['name']} {band_text(band)}" for band in unit["bands"])


# ---------- 评分标准 ----------

def band_entry_issues(band: object, index: int, label: str) -> list[str]:
    if not isinstance(band, dict) or not has_text(band.get("name")) or band.get("name") == NOT_PROVIDED \
            or not is_number(band.get("low")) or not is_number(band.get("high")) \
            or not isinstance(band.get("low_closed"), bool) or not isinstance(band.get("high_closed"), bool):
        return [f"{label}第 {index} 档要有 name、low、high、low_closed、high_closed（name 不能叫“{NOT_PROVIDED}”）"]
    if band["low"] >= band["high"]:
        return [f"{label}第 {index} 档“{band['name']}”的下限要小于上限"]
    return []


def band_issues(bands: object, points: float, label: str) -> list[str]:
    """档次要从 0 连到分值，相邻两档的边界只归一边：导则 1.3.3（2）要求打分区间连续不间断。"""
    if not isinstance(bands, list) or not bands:
        return [f"{label}：区间法要按原文列出各档次 bands"]
    issues = [issue for index, band in enumerate(bands, 1) for issue in band_entry_issues(band, index, label)]
    if issues:
        return issues
    names = [band["name"] for band in bands]
    if len(set(names)) != len(names):
        issues.append(f"{label}：档次名称重复")
    if bands[0]["low"] != 0 or bands[-1]["high"] != points:
        issues.append(f"{label}：档次要从 0 分连到分值 {number_text(points)} 分，核对抄录")
    for left, right in zip(bands, bands[1:]):
        if left["high"] != right["low"] or left["high_closed"] == right["low_closed"]:
            issues.append(f"{label}：“{left['name']}”和“{right['name']}”之间断开或重叠，核对抄录；"
                          "招标文件原文确实如此的，告诉用户")
    return issues


def value_issues(values: object, points: float, label: str) -> list[str]:
    if not isinstance(values, list) or not values or not all(is_number(value) for value in values):
        return [f"{label}：固定分值法要按原文列出可取的分值 values"]
    if values != sorted(set(values)) or values[0] <= 0 or values[-1] != points:
        return [f"{label}：values 要从小到大、不重复、都大于 0，最大的等于分值 {number_text(points)} 分（0 分只给未提供的）"]
    return []


def scale_issues_of(unit: dict, label: str) -> list[str]:
    method = unit.get("method")
    if method not in METHODS:
        return [f"{label}：method 只能是 {'、'.join(METHODS)}"]
    unused = "values" if method == RANGE_METHOD else "bands"
    issues = [] if not unit.get(unused) else [f"{label}：{method}不用 {unused}，留空列表"]
    if method == RANGE_METHOD:
        return issues + band_issues(unit.get("bands"), unit["points"], label)
    return issues + value_issues(unit.get("values"), unit["points"], label)


def unit_issues(unit: object, index: int, lookup: RefLookup) -> list[str]:
    label = f"评分标准第 {index} 个评审因素"
    if not isinstance(unit, dict) or unit.get("id") != f"U{index}":
        return [f"{label}：id 要按顺序写 U{index}"]
    issues = [] if has_text(unit.get("name")) else [f"{label}：要写评审因素原文 name"]
    if not is_number(unit.get("points")) or unit["points"] <= 0:
        return issues + [f"{label}：分值 points 要写大于 0 的数字"]
    numbers = unit.get("items")
    if not isinstance(numbers, list) or not numbers or not all(isinstance(no, int) and not isinstance(no, bool)
                                                               for no in numbers):
        issues.append(f"{label}：items 要列出它打分的评审内容编号")
    issues += scale_issues_of(unit, label)
    if not has_text(unit.get("criteria_text")):
        issues.append(f"{label}：要照抄评分标准原文 criteria_text")
    issues += ref_issues(unit.get("points_ref"), f"{label}的分值出处", lookup)
    issues += ref_issues(unit.get("criteria_ref"), f"{label}的评分标准出处", lookup)
    if unit.get("checked") is not True:
        issues.append(f"{label}：待核对（对照招标文件原文核实分值、档次和覆盖哪几项后，把 checked 改为 true）")
    return issues


def coverage_issues(units: list, items: dict[int, str]) -> list[str]:
    """每项评审内容都要归到一个评审因素，只归一个：未提供的，不得分，漏一项就是总分算错。"""
    owners: dict[int, list[str]] = {}
    for unit in units:
        if not isinstance(unit, dict) or not isinstance(unit.get("items"), list):
            continue  # 结构问题由 unit_issues 报
        for no in unit["items"]:
            owners.setdefault(no, []).append(str(unit.get("id")))
    issues = [f"评分标准没有覆盖第 {no} 项“{title}”" for no, title in items.items() if no not in owners]
    issues += [f"第 {no} 项归到了 {'、'.join(ids)} 几个评审因素，只能归一个" for no, ids in owners.items() if len(ids) > 1]
    issues += [f"规则卡没有第 {no} 项评审内容" for no in owners if no not in items]
    return issues


def standard_issues(standard: dict, items: dict[int, str], lookup: RefLookup) -> list[str]:
    if standard.get("schema") != STANDARD_SCHEMA:
        return [f"评分标准的 schema 应为 {STANDARD_SCHEMA}"]
    units = standard.get("units")
    if not isinstance(units, list) or not units:
        return ["评分标准至少要有一个评审因素 units"]
    issues = [issue for index, unit in enumerate(units, 1) for issue in unit_issues(unit, index, lookup)]
    return issues + coverage_issues(units, items)


def rule_items(project_dir: Path) -> dict[int, str]:
    card = load_json(project_dir / RULE_CARD_FILE, "规则卡")
    entries = (card.get("review_items") or {}).get("value") or []
    items = {entry["no"]: str(entry.get("title") or "").strip() for entry in entries
             if isinstance(entry, dict) and isinstance(entry.get("no"), int)}
    if not items:
        raise ValueError("规则卡里没有评审内容，先完成阶段 2")
    return dict(sorted(items.items()))


def load_standard(project_dir: Path) -> dict:
    path = project_dir / STANDARD_FILE
    if not path.is_file():
        raise ValueError(f"还没有评分标准 {STANDARD_FILE}：先运行 --init-standard 出候选，再对照招标文件核实")
    return load_json(path, "评分标准")


# ---------- 评分标准的候选 ----------

def tender_indexes(project_dir: Path) -> list[TextIndex]:
    indexes = []
    for name, output in tender_outputs(project_dir).items():
        try:
            indexes.append(build_index(name, output.read_text(encoding="utf-8")))
        except OSError:
            continue
    return indexes


def first_hit(indexes: list[TextIndex], pattern: str) -> tuple[TextIndex, re.Match] | None:
    hits = find_all(indexes, pattern, limit=1)
    return hits[0] if hits else None


def hit_ref(hit: tuple[TextIndex, re.Match] | None) -> dict | None:
    return ref_at(hit[0], hit[1].start()) if hit else None


def criteria_candidate(points_hit: tuple[TextIndex, re.Match] | None,
                       grading_hit: tuple[TextIndex, re.Match] | None, grading: str) -> str | None:
    """评分标准原文的候选：从"施工组织设计 100 分"连到档次那句；两处离得远或不在一个文件里，只取档次那句。"""
    if points_hit and grading_hit and points_hit[0] is grading_hit[0] \
            and 0 <= grading_hit[1].start() - points_hit[1].start() <= MAX_FACTOR_CHARS:
        return points_hit[0].flat[points_hit[1].start():grading_hit[1].end()]
    return grading or None


def candidate_bands(text: str) -> list[dict]:
    return [{"name": match["name"], "low": to_number(match["low"]), "high": to_number(match["high"]),
             "low_closed": match["lo"] == "≤", "high_closed": match["hi"] == "≤"}
            for match in BAND_TEXT.finditer(compact(text))]


def candidate_unit(project_dir: Path, items: dict[int, str]) -> dict:
    """按示范文本的结构出一个候选：施工组织设计整体打分，各项都归它。逐项给分值的招标文件，核实时按原文拆开。"""
    card = load_json(project_dir / RULE_CARD_FILE, "规则卡")
    grading = str((card.get("grading") or {}).get("value") or "")
    indexes = tender_indexes(project_dir)
    bands = candidate_bands(grading)
    points_hit = first_hit(indexes, POINTS_TEXT)
    grading_hit = first_hit(indexes, re.escape(compact(grading))) if grading else None
    points = to_number(points_hit[1].group(1)) if points_hit else (bands[-1]["high"] if bands else None)
    return {"id": "U1", "name": "施工组织设计", "points": points, "items": list(items),
            "method": RANGE_METHOD if bands else None, "bands": bands, "values": [],
            "criteria_text": criteria_candidate(points_hit, grading_hit, grading),
            "points_ref": hit_ref(points_hit), "criteria_ref": hit_ref(grading_hit), "checked": False}


def init_standard(project_dir: Path) -> dict:
    """出评分标准的候选，不覆盖已有的：核实过的标准被重出一遍，用户的核对就白做了。"""
    project_dir, _ = load_project(project_dir)
    path = project_dir / STANDARD_FILE
    if path.exists():
        raise ValueError(f"已有评分标准 {STANDARD_FILE}，不覆盖；确实要重出，先把它删掉")
    items = rule_items(project_dir)
    standard = {"schema": STANDARD_SCHEMA, "units": [candidate_unit(project_dir, items)]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(standard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"file": str(path), "issues": standard_issues(standard, items, RefLookup(project_dir))}


def check_standard(project_dir: Path) -> list[str]:
    project_dir, _ = load_project(project_dir)
    return standard_issues(load_standard(project_dir), rule_items(project_dir), RefLookup(project_dir))


# ---------- 成品和评审前提 ----------

def paragraph_text(paragraph: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(W + "t")).strip()


def finished_sections(docx: Path, items: dict[int, str]) -> dict[int, list[str]]:
    """成品正文按一级标题分节：评审内容编号 -> 各段文字。第一个一级标题之前是封面和目录，不归哪一项。"""
    parts = load_parts(docx.read_bytes())
    context = style_context(parts)
    document = parts["xml"].get("word/document.xml")
    body = None if document is None else document.find(W + "body")
    numbers = {compact(item_heading(no, title)): no for no, title in items.items()}
    sections: dict[int, list[str]] = {no: [] for no in items}
    current: int | None = None
    for paragraph in [] if body is None else body.iter(W + "p"):
        text = paragraph_text(paragraph)
        if is_heading1(paragraph, context):
            current = numbers.get(compact(text))
        elif current is not None and text:
            sections[current].append(text)
    return sections


def precondition_issues(project_dir: Path, state: dict) -> list[str]:
    """只评过了阶段 7 的成品（2A）：阶段 7 已完成，门禁报告记的就是现在这份成品。"""
    if state["stages"].get("7") != "done":
        return ["阶段 7 还没完成：模拟自评只评过了门禁的成品"]
    docx = project_dir / FINISHED_DOCX
    if not docx.is_file():
        return [f"没有成品 {FINISHED_DOCX}"]
    return [f"阶段 7 之后成品有变化：{issue}" for issue in report_issues(project_dir, file_sha256(docx))]


def bullets(issues: list[str]) -> str:
    return "\n".join(f"- {issue}" for issue in issues)


def scoring_context(project_dir: Path, state: dict) -> dict:
    """出评审材料和存评分都要的东西：前提成立、评分标准核实过，再读成品分节。"""
    issues = precondition_issues(project_dir, state)
    if issues:
        raise ValueError("还不能模拟自评：\n" + bullets(issues))
    items = rule_items(project_dir)
    standard = load_standard(project_dir)
    issues = standard_issues(standard, items, RefLookup(project_dir))
    if issues:
        raise ValueError("评分标准不符合要求：\n" + bullets(issues))
    docx = project_dir / FINISHED_DOCX
    return {"items": items, "standard": standard, "standard_sha256": file_sha256(project_dir / STANDARD_FILE),
            "docx_sha256": file_sha256(docx), "sections": finished_sections(docx, items)}


# ---------- 评审材料 ----------

def unit_lines(unit: dict) -> list[str]:
    covered = "、".join(f"第 {no} 项" for no in unit["items"])
    how = "所列评审内容整体打一个分" if len(unit["items"]) > 1 else "单独打分"
    return [f"### {unit['id']}　{unit['name']}（{number_text(unit['points'])} 分，{unit['method']}，{how}）", "",
            f"- 覆盖：{covered}", f"- 可打的分：{scale_text(unit)}", f"- 原文：{unit['criteria_text']}",
            f"- 出处：{ref_text(unit['criteria_ref'])}", ""]


def packet_text(context: dict) -> str:
    lines = ["# 模拟自评的评审材料", "",
             f"> {SIMULATED}。评审人只看这份材料和事实卡 {FACT_VIEW}，不看响应矩阵、中间稿、门禁报告和写稿时的对话。",
             f"> 成品 {FINISHED_DOCX}，sha256 {context['docx_sha256']}。成品再存过，这份材料作废。", "",
             "## 一、评分标准（招标文件原文）", ""]
    for unit in context["standard"]["units"]:
        lines += unit_lines(unit)
    lines += ["## 二、成品正文（按一级标题分节）", ""]
    for no, title in context["items"].items():
        lines += [f"### 第 {no} 项　{title}", ""]
        for text in context["sections"][no] or ["（这一节没有正文）"]:
            lines += [text, ""]
    return "\n".join(lines)


def blank_sheet(context: dict) -> dict:
    multi = [unit for unit in context["standard"]["units"] if len(unit["items"]) > 1]
    return {"docx_sha256": context["docx_sha256"], "reviewer": "",
            "items": [{"no": no, "title": title, "provided": True, "band": None, "score": None, "evidence": [],
                       "reason": "", "full_reason": "", "lost": [], "fix": []}
                      for no, title in context["items"].items()],
            "units": [{"id": unit["id"], "band": None, "score": None, "reason": "", "full_reason": ""}
                      for unit in multi]}


def write_packet(project_dir: Path) -> dict:
    """给独立评审人的材料和空评分表。评审人只看这两样和事实卡，评完的表用 --record 存。"""
    project_dir, state = load_project(project_dir)
    context = scoring_context(project_dir, state)
    packet, blank = project_dir / PACKET_FILE, project_dir / BLANK_FILE
    packet.parent.mkdir(parents=True, exist_ok=True)
    packet.write_text(packet_text(context), encoding="utf-8")
    blank.write_text(json.dumps(blank_sheet(context), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"packet": str(packet), "blank": str(blank)}


# ---------- 评分表 ----------

def scale_issues(unit: dict, band: object, score: float, label: str) -> list[str]:
    points = unit["points"]
    if score < 0 or score > points:
        return [f"{label}：score 要在 0～{number_text(points)} 分之间"]
    if unit["method"] == VALUE_METHOD:
        issues = [] if score in unit["values"] else [f"{label}：固定分值只能取 {scale_text(unit)}"]
        return issues + ([] if band in (None, "") else [f"{label}：固定分值不分档次，band 留空"])
    named = next((entry for entry in unit["bands"] if entry["name"] == band), None)
    if named is None:
        return [f"{label}：band 只能是 {'、'.join(entry['name'] for entry in unit['bands'])}"]
    if not in_band(named, score):
        return [f"{label}：{number_text(score)} 分不在“{band}”档（{band_text(named)}）里；0 分只给未提供的"]
    return []


def judged_issues(judged: dict, unit: dict, label: str) -> list[str]:
    """档次和分数对得上评分标准；该写充足理由的写了。未提供的，不得分。"""
    score = judged.get("score")
    if not is_number(score):
        return [f"{label}：score 要写数字，最多两位小数"]
    if judged.get("provided") is False:
        issues = [] if score == 0 else [f"{label}：未提供的，不得分，score 只能是 0"]
        if judged.get("band") not in (None, "", NOT_PROVIDED):
            issues.append(f"{label}：未提供的，band 写“{NOT_PROVIDED}”或留空")
    else:
        issues = scale_issues(unit, judged.get("band"), score, label)
    if needs_full_reason(unit, score) and not has_text(judged.get("full_reason")):
        issues.append(f"{label}：{full_reason_rule(unit)}")
    return issues


def evidence_issues(entry: dict, no: int, sections: dict[int, list[str]], label: str) -> list[str]:
    """出处要逐字摘自本项的章节：给分理由要能溯源到成品（导则 1.3.1 溯源解析），写在别处的不算本项的。"""
    quotes = entry.get("evidence")
    if not isinstance(quotes, list) or not all(isinstance(quote, str) for quote in quotes):
        return [f"{label}：evidence 要写成列表，逐字摘成品原文"]
    if entry.get("provided") is not False and not quotes:
        return [f"{label}：至少摘一句本项章节里的成品原文作出处 evidence"]
    own = compact("".join(sections[no]))
    whole = compact("".join(text for section in sections.values() for text in section))
    issues = []
    for index, quote in enumerate(quotes, 1):
        text = compact(quote)
        if not MIN_QUOTE_CHARS <= len(text) <= MAX_QUOTE_CHARS:
            issues.append(f"{label}出处第 {index} 条要 {MIN_QUOTE_CHARS}～{MAX_QUOTE_CHARS} 个字：摘能定位的一句，不贴整段")
        elif text not in own:
            where = "在别的项的章节里，不在本项；写在别处的内容记进失分点" if text in whole else "在成品里查不到"
            issues.append(f"{label}出处第 {index} 条{where}：照成品原文逐字摘")
    return issues


def loss_issues(entry: dict, unit: dict, label: str) -> list[str]:
    """没给满分就要说清扣在哪；说了扣在哪，就要给怎么改。"""
    lost, fix, score = entry.get("lost"), entry.get("fix"), entry.get("score")
    if not isinstance(lost, list) or not isinstance(fix, list) or not is_number(score):
        return []  # 格式问题由 text_issues 和 judged_issues 报
    issues = []
    if score < unit["points"] - EPSILON and not lost:
        issues.append(f"{label}：没给满分，要在 lost 里写失分点")
    if lost and not fix:
        issues.append(f"{label}：写了失分点，要在 fix 里写怎么改")
    return issues


def text_value_issues(name: str, text: object, label: str) -> list[str]:
    if text in (None, ""):
        return []
    if not isinstance(text, str):
        return [f"{label}的{name}要写文字"]
    limit = MAX_REASON_CHARS if name in ("理由", "充足理由") else MAX_ENTRY_CHARS
    issues = [] if len(text) <= limit else [f"{label}的{name}超过 {limit} 字：写判断和依据，不贴成品原文"]
    found = PROMISE_WORDS.search(text)
    if found:
        issues.append(f"{label}的{name}写了“{found.group()}”：模拟自评不预测入围和中标，只写得分理由和失分点")
    return issues


def text_issues(entry: dict, label: str, lists: tuple[str, ...] = tuple(LIST_LABELS)) -> list[str]:
    issues = [] if has_text(entry.get("reason")) else [f"{label}：要写理由 reason"]
    texts: list[tuple[str, object]] = [("理由", entry.get("reason")), ("充足理由", entry.get("full_reason"))]
    for key in lists:
        values = entry.get(key)
        if not isinstance(values, list) or not all(has_text(value) for value in values):
            issues.append(f"{label}：{LIST_LABELS[key]} {key} 要写成列表，没有就写空列表，不留空条目")
            continue
        texts += [(LIST_LABELS[key], value) for value in values]
    for name, text in texts:
        issues += text_value_issues(name, text, label)
    return issues


def item_issues(entry: dict, unit: dict, context: dict) -> list[str]:
    no = entry["no"]
    label = f"第 {no} 项"
    issues = [f"{label}：不记这个字段：{name}" for name in sorted(set(entry) - ITEM_FIELDS)]
    if "title" in entry and entry["title"] != context["items"][no]:
        issues.append(f"{label}：title 和规则卡的评审内容原文不一致")
    if not isinstance(entry.get("provided"), bool):
        return issues + [f"{label}：provided 写 true 或 false（成品里有没有这一项的内容）"]
    issues += judged_issues(entry, unit, label)
    issues += evidence_issues(entry, no, context["sections"], label)
    issues += text_issues(entry, label)
    return issues + loss_issues(entry, unit, label)


def items_issues(entries: object, context: dict, unit_of: dict[int, dict]) -> list[str]:
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        return ["items 要写成列表，每项评审内容一条"]
    if [entry.get("no") for entry in entries] != list(context["items"]):
        return [f"items 要按顺序逐项写第 1～{len(context['items'])} 项，一项不缺、不重复（未提供的也写一条）"]
    return [issue for entry in entries for issue in item_issues(entry, unit_of[entry["no"]], context)]


def spread_issues(entry: dict, unit: dict, scores: dict[int, float], label: str) -> list[str]:
    """整体分不能比最好的一项还高，也不能比最差的一项还低：否则说不清这个分是怎么来的。"""
    own = [scores[no] for no in unit["items"] if no in scores]
    score = entry.get("score")
    if len(own) != len(unit["items"]) or not is_number(score):
        return []
    if not min(own) - EPSILON <= score <= max(own) + EPSILON:
        return [f"{label}：整体分 {number_text(score)} 不在各项分 {number_text(min(own))}～{number_text(max(own))} 之间"]
    return []


def item_scores(item_entries: object) -> dict[int, float]:
    if not isinstance(item_entries, list):
        return {}
    return {entry["no"]: entry["score"] for entry in item_entries
            if isinstance(entry, dict) and "no" in entry and is_number(entry.get("score"))}


def units_issues(entries: object, context: dict, item_entries: object) -> list[str]:
    multi = [unit for unit in context["standard"]["units"] if len(unit["items"]) > 1]
    ids = None
    if isinstance(entries, list):
        ids = [entry.get("id") if isinstance(entry, dict) else None for entry in entries]
    if ids != [unit["id"] for unit in multi]:
        expected = "、".join(unit["id"] for unit in multi) or "没有，写空列表"
        return [f"units 只写整体打分的评审因素（{expected}），按顺序各一条；单独打分的评审因素用该项的分"]
    scores = item_scores(item_entries)
    issues = []
    for entry, unit in zip(entries, multi):
        label = f"{unit['id']} {unit['name']}"
        issues += [f"{label}：不记这个字段：{name}" for name in sorted(set(entry) - UNIT_FIELDS)]
        issues += judged_issues(entry, unit, label)
        issues += text_issues(entry, label, lists=())
        issues += spread_issues(entry, unit, scores, label)
    return issues


def sheet_issues(sheet: dict, context: dict) -> list[str]:
    """评分表的问题。多余的字段也拒绝，免得写进去的东西被悄悄丢掉、以为记下了。"""
    issues = [f"评分表不记这个字段：{name}" for name in sorted(set(sheet) - SHEET_FIELDS)]
    if sheet.get("docx_sha256") != context["docx_sha256"]:
        issues.append("评分表不是现在这份成品的（docx_sha256 对不上）：重新运行 --packet，按新材料重评")
    if sheet.get("reviewer") not in REVIEWERS:
        issues.append(f"reviewer 只能是 {'、'.join(REVIEWERS)}：写稿的会话评自己的稿有盲区")
    unit_of = {no: unit for unit in context["standard"]["units"] for no in unit["items"]}
    issues += items_issues(sheet.get("items"), context, unit_of)
    return issues + units_issues(sheet.get("units"), context, sheet.get("items"))


# ---------- 记录和报告 ----------

def cleaned(entry: dict) -> dict:
    """存进记录的一项：按固定顺序，去掉首尾空白；title 不存，以规则卡为准。"""
    result = {}
    for key in RECORD_ITEM_FIELDS:
        value = entry.get(key)
        if isinstance(value, str):
            value = value.strip()
        elif isinstance(value, list):
            value = [text.strip() for text in value]
        result[key] = value
    return result


def scored_units(sheet: dict, standard: dict) -> list[dict]:
    """每个评审因素的模拟得分：单独打分的就是该项的分，整体打分的是评审人给的整体分。"""
    items = {entry["no"]: entry for entry in sheet["items"]}
    entries = {entry["id"]: entry for entry in sheet["units"]}
    result = []
    for unit in standard["units"]:
        source = entries[unit["id"]] if len(unit["items"]) > 1 else items[unit["items"][0]]
        band = NOT_PROVIDED if source.get("provided") is False else (source.get("band") or None)
        result.append({"id": unit["id"], "name": unit["name"], "points": unit["points"], "band": band,
                       "score": source["score"], "reason": source["reason"].strip(),
                       "full_reason": (source.get("full_reason") or "").strip()})
    return result


def record_self_score(project_dir: Path, source_json: Path) -> dict:
    """核对评分表，存记录、出报告，锁定此刻成品和评分标准的 sha256。哪个一改，记录就显示要重评。"""
    project_dir, state = load_project(project_dir)
    context = scoring_context(project_dir, state)
    sheet = load_json(source_json, "评分表")
    issues = sheet_issues(sheet, context)
    if issues:
        raise ValueError("评分表不符合要求：\n" + bullets(issues))
    units = scored_units(sheet, context["standard"])
    saved = {"schema": RECORD_SCHEMA, "docx_sha256": context["docx_sha256"],
             "standard_sha256": context["standard_sha256"], "recorded_at": now_text(), "reviewer": sheet["reviewer"],
             "items": [cleaned(entry) for entry in sheet["items"]], "units": units,
             "total": round(sum(unit["score"] for unit in units), 2),
             "total_points": round(sum(unit["points"] for unit in units), 2)}
    path = project_dir / RECORD_FILE
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (project_dir / REPORT_FILE).write_text(render_report(saved, context["standard"], context["items"]),
                                           encoding="utf-8")
    return saved


def band_cell(unit: dict, band: object) -> str:
    if band == NOT_PROVIDED:
        return NOT_PROVIDED
    return cell(band) if unit["method"] == RANGE_METHOD else "固定分值"


def reason_cell(entry: dict) -> str:
    parts = [entry["reason"]]
    if entry.get("full_reason"):
        parts.append(f"充足理由：{entry['full_reason']}")
    if entry.get("evidence"):
        parts.append("出处：" + "；".join(f"“{quote}”" for quote in entry["evidence"]))
    return cell("\n".join(parts))


def item_row(entry: dict, unit: dict, title: str) -> str:
    whole = len(unit["items"]) > 1
    points = f"整体 {number_text(unit['points'])} 分" if whole else number_text(unit["points"])
    criteria = f"见 {unit['id']}" if whole else cell(unit["criteria_text"])
    band = NOT_PROVIDED if entry["provided"] is False else entry.get("band")
    return (f"| {entry['no']}. {cell(title)} | {points} | {criteria} | {band_cell(unit, band)} | "
            f"{number_text(entry['score'])} | {reason_cell(entry)} | {cell('；'.join(entry['lost']))} | "
            f"{cell('；'.join(entry['fix']))} |")


def summary_lines(record: dict, standard: dict) -> list[str]:
    units = {unit["id"]: unit for unit in standard["units"]}
    lines = ["## 一、总表", "", "| 评审因素 | 分值 | 评分方法 | 模拟档次 | 模拟得分 |", "|---|---|---|---|---|"]
    for scored in record["units"]:
        unit = units[scored["id"]]
        lines.append(f"| {scored['id']} {cell(scored['name'])} | {number_text(scored['points'])} | {unit['method']} | "
                     f"{band_cell(unit, scored['band'])} | {number_text(scored['score'])} |")
    lines.append(f"| 合计 | {number_text(record['total_points'])} | | | {number_text(record['total'])} |")
    return lines + ["", *whole_lines(record, units)]


def whole_lines(record: dict, units: dict[str, dict]) -> list[str]:
    """整体打分的评审因素：评审人给的整体分和理由，接在总表下面。"""
    lines = []
    for scored in record["units"]:
        if len(units[scored["id"]]["items"]) > 1:
            extra = f"　充足理由：{scored['full_reason']}" if scored["full_reason"] else ""
            lines.append(f"- {scored['id']} {scored['name']}整体打分：{number_text(scored['score'])} 分。"
                         f"{scored['reason']}{extra}")
    return lines + [""] if lines else []


USAGE_LINES = [
    "## 四、怎么用", "",
    "- 失分点和怎么改是评审人的推断。原文告诉用户，改不改、改哪几项由用户定。",
    "- 要改的：回阶段 5 改对应的中间稿（project_status.py <项目目录> --reopen 5），逐项重新确认，"
    "再出稿、过阶段 7 的门禁，按 references/self-score.md 重评。",
    "- 分数只在同一个项目前后两次自评之间比较才有参考意义，不能跟别的项目、别家的标书比。", "",
]


def render_report(record: dict, standard: dict, items: dict[int, str]) -> str:
    units = {no: unit for unit in standard["units"] for no in unit["items"]}
    lines = ["# 模拟自评报告", "",
             f"> **{SIMULATED}。** 青天和评委怎么打分没有公开。这份报告按招标文件的评分标准和导则 2.2.2 的打分规则，"
             "由独立评审人模拟打分【推断】，只用来找失分点、决定改哪里；不能当预期得分，也不能据此判断能否入围、中标。", "",
             f"- 成品：{FINISHED_DOCX}（sha256 {record['docx_sha256'][:12]}…）。成品再存过，这份报告作废",
             f"- 评审人：{record['reviewer']}；时间：{record['recorded_at']}",
             f"- 模拟总分：**{number_text(record['total'])} / {number_text(record['total_points'])}**"
             "（脚本按各评审因素的模拟得分相加）", "",
             *summary_lines(record, standard), "## 二、评分标准原文", ""]
    for unit in standard["units"]:
        lines.append(f"- {unit['id']} {unit['name']}（{number_text(unit['points'])} 分；{scale_text(unit)}）："
                     f"{unit['criteria_text']}（出处：{ref_text(unit['criteria_ref'])}）")
    lines += ["", "## 三、逐项", "",
              "| 评审内容 | 分值 | 评分标准原文 | 模拟档次 | 模拟得分 | 理由和成稿出处 | 失分点 | 怎么改 |",
              "|---|---|---|---|---|---|---|---|",
              *[item_row(entry, units[entry["no"]], items[entry["no"]]) for entry in record["items"]], ""]
    return "\n".join(lines + USAGE_LINES)


# ---------- 状态 ----------

def read_record(path: Path) -> dict | None:
    """读不出、格式不对的都返回 None：记录坏了不能拖累进度摘要。"""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    keys = {"docx_sha256", "standard_sha256", "recorded_at", "reviewer", "units", "total", "total_points"}
    if not isinstance(record, dict) or record.get("schema") != RECORD_SCHEMA or not keys <= set(record):
        return None
    if record["reviewer"] not in REVIEWERS or not is_number(record["total"]) or not is_number(record["total_points"]):
        return None
    return record


def self_score_status(project_dir: Path, state: dict) -> dict:
    """{status: 已做 / 要重评 / 记录读不出 / 未做, why?, record?}。成品、评分标准一改，或阶段 7 重开，分数就作废。"""
    path = project_dir / RECORD_FILE
    if not path.is_file():
        return {"status": NOT_DONE}
    record = read_record(path)
    if record is None:
        return {"status": UNREADABLE}
    docx, standard = project_dir / FINISHED_DOCX, project_dir / STANDARD_FILE
    if not docx.is_file() or file_sha256(docx) != record["docx_sha256"]:
        return {"status": STALE, "why": "成品在自评之后改过", "record": record}
    if not standard.is_file() or file_sha256(standard) != record["standard_sha256"]:
        return {"status": STALE, "why": "评分标准在自评之后改过", "record": record}
    if state["stages"].get("7") != "done":
        return {"status": STALE, "why": "阶段 7 重开了", "record": record}
    return {"status": DONE, "record": record}


def self_score_summary(project_dir: Path, state: dict) -> str:
    """进度摘要里"模拟自评："后面的一句。"""
    status = self_score_status(project_dir, state)
    if status["status"] == DONE:
        record = status["record"]
        return (f"模拟总分 {number_text(record['total'])}/{number_text(record['total_points'])}"
                f"（{record['reviewer']}，{record['recorded_at']}），见 {REPORT_FILE}；{SIMULATED}，不是门禁")
    if status["status"] == STALE:
        return f"{status['why']}，分数作废，要重评（可选，不挡任何阶段）"
    if status["status"] == UNREADABLE:
        return f"{RECORD_FILE} 读不出或不符合要求，按没做算（可选，不挡任何阶段）"
    if state["stages"].get("7") != "done":
        return "—（阶段 7 完成后可选）"
    return f"还没做。可选，做法见 {GUIDE}，不做也不挡阶段 8"


# ---------- 命令行 ----------

def status_text(project_dir: Path, state: dict) -> str:
    lines = [f"模拟自评：{self_score_summary(project_dir, state)}"]
    record = self_score_status(project_dir, state).get("record")
    for unit in record["units"] if record else []:
        band = f"{unit['band']}，" if unit.get("band") else ""
        lines.append(f"- {unit['id']} {unit['name']}：{band}{number_text(unit['score'])}/{number_text(unit['points'])}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"qingtian-bid 模拟自评（{SIMULATED}）：阶段 7 之后可选，不是门禁。"
                                                 f"做法见 {GUIDE}。")
    parser.add_argument("project_dir", type=Path, help="项目目录（bid-projects/ 下）。")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--init-standard", action="store_true", help="按规则卡和招标文件出评分标准的候选，不覆盖已有的。")
    action.add_argument("--check-standard", action="store_true", help="校验评分标准（分值、档次、出处、覆盖）。")
    action.add_argument("--packet", action="store_true", help="给独立评审人出评审材料和空评分表（阶段 7 完成后）。")
    action.add_argument("--record", type=Path, metavar="JSON", help="核对评审人填好的评分表，存记录、出自评报告。")
    return parser.parse_args(argv)


def issues_text(title: str, issues: list[str]) -> str:
    return f"{title}：没有问题。" if not issues else f"{title}还有 {len(issues)} 个问题：\n" + bullets(issues)


def run(args: argparse.Namespace) -> tuple[str, int]:
    project_dir, state = load_project(args.project_dir)
    if args.init_standard:
        result = init_standard(project_dir)
        text = issues_text(f"已出评分标准候选 {result['file']}，对照招标文件原文核实", result["issues"])
        return text, 0
    if args.check_standard:
        issues = check_standard(project_dir)
        return issues_text("评分标准", issues), 1 if issues else 0
    if args.packet:
        result = write_packet(project_dir)
        return (f"评审材料：{result['packet']}\n空评分表：{result['blank']}\n"
                f"交给新会话或子代理，按 {GUIDE} 第三节评；评完用 --record 存。"), 0
    if args.record:
        record_self_score(project_dir, args.record)
    return status_text(project_dir, state), 0


def main(argv: list[str] | None = None) -> int:
    try:
        text, code = run(parse_args(argv))
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
