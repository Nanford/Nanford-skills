"""Draft a rule card from the extracted tender texts: candidates with sources, never conclusions.

INPUT: <project>/analysis/extraction-report.json and the extracted texts of tender files (图纸和
       响应样本不参与; .xlsx/.xls 工程量清单 included); templates/rule-card.json as the card skeleton;
       project-state.json; the delivered category knowledge cards (category_cards) for 工程类别 clues.
OUTPUT: analysis/rule-card.json with suggested values and candidates (each with 文件、页码、提取
        文本行号), every field checked=false — the project name comes from "项目名称：" labels (招标文件
        first, every other spelling listed as a candidate, the cover title only when no label exists);
        project_category gets 资质、招标范围、清单工作表名 and the bill rows per card as clues, never a
        main category (决策 5-2A); qingtian gets an enabled suggestion from the AI clause and the method, and a
        rule_scope candidate from 建设地点 and 资质 (决策 D11); an 评标办法 outside Hefei's four is picked up from
        "评标办法采用××法" and gets no track suggestion (决策 2A); mandatory candidates include the tender-named 施组 contents
        (前附表 3.7.1 重点难点、危大清单), shortlist candidates include the 中标候选人推荐规则 text,
        and 答疑/补遗 corrections go to the optional addenda_changes; the fields located by ref come from
        scaffold_rule_fields.py, the 投标文件格式 outline from scan_bid_forms.py;
        analysis/rule-card.md and mandatory-checklist.md views.
        An existing rule-card.json is never overwritten: the draft goes to
        analysis/rule-card-候选-<时间>.json instead. JSON summary of what was located on stdout,
        including the notes' 扣分 sentence (阶段 2 照抄进 tender-format.json 的 penalty).
POS: stage-2 helper of qingtian-bid (design v1 §9). Patterns follow the 技术评分合理价格法 示范文本
     layout; tenders differ, so every suggestion must be checked against the original text before
     the user confirms (R1, R3). Searching runs on the flattened text from tender_text.py.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from category_cards import BOQ_CODE, CATALOG, CATEGORY_FIELD, boq_card, load_card
from format_state import penalty_sentence
from project_cards import (
    HEFEI_CIVIL,
    HEFEI_OTHER,
    METHOD_TRACKS,
    OUTSIDE_HEFEI,
    QINGTIAN_FIELD,
    QINGTIAN_ON,
    RULE_CARD_FILE,
    is_other_method,
    load_json,
    load_project,
    rule_card_template,
    validate_rule_card,
    write_rule_card_views,
)
from scaffold_rule_fields import fill_ref_fields
from scan_bid_forms import fill_bid_forms
from tender_text import EXCERPT_CHARS, MAX_CANDIDATES, TOC_LEADER, TextIndex, build_index, candidates, find_all


# 合肥四种以外的评标办法（决策 2A）：不硬停，照录名称，脚本不给轨道建议
OTHER_METHOD_PATTERN = r"评标(?:办法|方法)(?:采用|为|是|[:：])[:：]?([^\s，。；;、（(：:]{2,20}?法)"
OTHER_METHOD_NOTE = "不在合肥四种之内：脚本不给轨道建议，按 AI、暗标条款等信号提出轨道，请用户确认，并说明没有导则依据"
GUIDE_REQUIRES_QINGTIAN = "技术评分合理价格法"  # 导则 1.3.1：这种办法须运用 AI 类人评审
QINGTIAN_NOTE = ("启用看详细评审有没有写 AI 类人评审，只写了人工智能初步筛查或初步评审辅助的不算启用；招标文件没提到写未启用，"
                 "判不清写判不清（硬停）。rule_scope 是候选：建设地点在合肥、资质是房建市政的才是合肥房建市政")
# 建设地点常只写县市名，所以把合肥下辖的县市也列上
HEFEI_PLACES = ("合肥", "长丰", "肥东", "肥西", "庐江", "巢湖")
# 导则 1.3.2 那 9 类工程对应的常见资质（总承包和专业承包）；对不上的给"合肥其他"，由人核实
CIVIL_QUALIFICATIONS = ("建筑工程", "市政公用", "建筑装修装饰", "建筑幕墙", "园林绿化")
PLACE_PATTERN = rf"(?:建设地点|工程地点|工程地址|项目地点)[：:]([^。；;{chr(0xFFFF)}]{{2,60}})"  # 合同格式的空白处是这个占位符
# 临时措辞（v2.0-dev）：第 3～5 步接入商务文件和定标部分后改写，改动范围全文搜“本版本暂不生成”。
HANDOFF_TEXT = "定标部分（定标文件与答辩预案）由用户另行编制，本版本暂不生成（R24）"
# 招标文件点名要施组阐述的内容（类型"招标指定"）：前附表 3.7.1"施工组织设计编制的特殊要求"列本项目重点难点和
# 危大工程清单，第七章另有"重点难点及危险性较大的分部分项工程"一节（2026-10-30 两个真实合肥招标文件都这样写）
TENDER_SPECIFIED_PATTERN = r"施工组织设计编制的特殊要求|重点难点及危险性较大的分部分项工程|危险性较大的分部分项工程清单"
SECTION_CHARS = 900  # 真实招标文件的 3.7.1 列了 4 条重点难点，约 520 字
NEXT_SUBCLAUSE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{1,2}")
SECTION_NUMBER = re.compile(r"(?<![\d\.．])(\d{1,2})[\.．、]$")
# 答疑、补遗的更正写法："第 X 页原内容“……”，现澄清更正为“……”"，摘录从提示词前 40 字取起
ADDENDA_PATTERN = r"原内容|现澄清|现更正|现修改|更正为|修改为|删除招标文件"
# 更正后内容的后引号；删除类写作"删除招标文件第 X 页“……”中的“……”"
CORRECTED_QUOTE = re.compile(r"(?:更正|修改)为[“\"][^”\"]{0,400}[”\"]|删除[^”]{0,300}”(?:中的[“\"][^”\"]{0,60}[”\"])?")
ADDENDA_BEFORE = 40
ADDENDA_CHARS = 300
MAX_ADDENDA = 60  # 提示词命中数（一处更正常命中两三个），不是更正条数
# 工程类别的线索（决策 5-2A）：资质要求、招标范围的原文，清单的工作表名和各张卡编码前缀对上的行数。
# 行数不是造价占比，主类别按导则 1.3.3（1）由用户判断，脚本不填 main
QUALIFICATION_PATTERN = r"施工总承包|专业承包"
SCOPE_PATTERN = r"招标范围[：:]"
MAX_CATEGORY_HITS = 3
# 工程量清单：.xls 在阶段 1 已另存为 .xlsx 再提取，提取文本格式相同；每张工作表前有一行工作表名
BILL_SUFFIXES = (".xlsx", ".xls")
SHEET_MARK = re.compile(r"^---\s*工作表：(.*)\s*---$")
# 项目名称按"1.1 项目名称：""2.1 招标项目名称："这类标签取，取到下一条条款编号、冒号、"项目编号""标段"或"一、"
# 为止（NAME_CHARS 个字内没碰到就不算），取值须以项目、工程、施工结尾（可带括注）。格式页里的"工程名称：____""立项批复名称+施工"、合同空白处（U+FFFF）
# 和"见招标公告"不是取值
NAME_LABEL = re.compile(r"(?:招标)?(?:项目|工程)名称[：:]")
NAME_STOP = re.compile(r"\d{1,2}\.\d{1,2}|[，。；;：:]|项目编号|招标编号|序号|标段|[一二三四五六七八九十][、．]")
NAME_ENDING = re.compile(r"(?:项目|工程|施工)(?:[（(][^）)]{1,20}[）)])?$")
NAME_PLACEHOLDER = re.compile(rf"[_＿+＋{chr(0xFFFF)}]|^见")
NAME_CHARS = 80
# 文件名：补遗答疑（scaffold_facts 也用它认现场限制的来源）、招标文件正文
ADDENDA_FILE = re.compile(r"补疑|补遗|答疑|澄清|答复")
TENDER_FILE = re.compile(r"招标文件|招标公告")


def sentence_hits(indexes: list[TextIndex], pattern: str) -> list[dict]:
    """命中所在的整句：起点退到上一个句号、分号或"2."这类注释编号之后，终点到下一个句号。"""
    found = []
    for index, match in find_all(indexes, pattern):
        back = index.flat[max(match.start() - 120, 0):match.start()]
        marks = list(re.finditer(r"[。；]|\d[\.．、](?=\D)", back))
        start = match.start() - len(back) + marks[-1].end() if marks else max(match.start() - 30, 0)
        end = index.flat.find("。", match.end())
        found.append(index.hit(start, end + 1 if end >= 0 else None))
    return found


def section_end(index: TextIndex, match: re.Match) -> int:
    """整条条款的结尾：前附表的取到下一个三级条款编号（如 3.7.4）；第七章"4.重点难点……"这种带序号的节
    取到下一节"5."；命中在引号里的（答疑引的原内容、更正后的内容）取到引号为止；都没有就取 SECTION_CHARS 个字。"""
    limit = match.end() + SECTION_CHARS
    found = [NEXT_SUBCLAUSE.search(index.flat, match.end(), limit)]
    number = SECTION_NUMBER.search(index.flat, max(match.start() - 4, 0), match.start())
    if number:
        found.append(re.compile(rf"(?<!\d){int(number.group(1)) + 1}[\.．、]").search(index.flat, match.end(), limit))
    stops = [stop.start() for stop in found if stop]
    close = index.flat.find("”", match.end(), limit)
    if close >= 0 and "“" not in index.flat[match.end():close]:
        stops.append(close)
    return min(stops or [limit])


def section_hits(indexes: list[TextIndex], pattern: str) -> list[dict]:
    """招标文件点名要施组阐述的整条条款。目录行（标题后跟一串点）不算；落在上一条摘录里的不再另列。"""
    found, covered = [], {}
    for index, match in find_all(indexes, pattern):
        if TOC_LEADER.match(index.flat, match.end()) or match.start() < covered.get(index.name, 0):
            continue
        covered[index.name] = section_end(index, match)
        found.append(index.hit(match.start(), covered[index.name]))
    return found


def addenda_hits(indexes: list[TextIndex]) -> list[dict]:
    """答疑、补遗里的"原内容……现澄清更正为……"：一处更正常有好几个提示词，落在上一条摘录里的不再另列。
    摘录从提示词前 ADDENDA_BEFORE 字（"第 78 页……第 3.7 条"）取到更正后内容的后引号，找不到引号取 ADDENDA_CHARS 字。"""
    found, covered = [], {}
    for index, match in find_all(indexes, ADDENDA_PATTERN, limit=MAX_ADDENDA):
        done = covered.get(index.name, 0)
        if match.start() < done:
            continue
        start = max(match.start() - ADDENDA_BEFORE, done)
        corrected = CORRECTED_QUOTE.search(index.flat, match.start(), match.start() + 2 * ADDENDA_CHARS)
        covered[index.name] = corrected.end() if corrected else start + ADDENDA_CHARS
        found.append(index.hit(start, covered[index.name]))
    return found


def suggest(entry: dict, value: object, source: str, found: list[dict]) -> dict:
    """写入建议值；checked 永远是 false，核实后才改。"""
    entry = copy.deepcopy(entry)
    entry.update({"value": value, "source": source, "checked": False})
    if found:
        entry["candidates"] = found
    return entry


def name_source_rank(index: TextIndex) -> int:
    """项目名称按哪个文件取：招标文件、招标公告在前，补遗答疑在后，工程量清单最后（清单的工程名称带单位工程后缀）。"""
    if Path(index.name).suffix.lower() in BILL_SUFFIXES:
        return 3
    if ADDENDA_FILE.search(index.name):
        return 2
    return 0 if TENDER_FILE.search(index.name) else 1


def labelled_names(indexes: list[TextIndex]) -> list[tuple[str, dict]]:
    """"1.1 项目名称：""2.1 招标项目名称："的取值，按 name_source_rank 的文件先后去重；取值常跨行，在连续文本里
    按 NAME_STOP 截断。"""
    found, seen = [], set()
    for index in sorted(indexes, key=name_source_rank):
        for match in NAME_LABEL.finditer(index.flat):
            rest = index.flat[match.end():match.end() + NAME_CHARS + 1]
            stop = NAME_STOP.search(rest)
            # 到上限还没截断的，是格式页里串起来的表头；文本到头了（清单表头行）就取到末尾
            value = rest[:stop.start()] if stop else (rest if len(rest) <= NAME_CHARS else "")
            if NAME_ENDING.search(value) and not NAME_PLACEHOLDER.search(value) and value not in seen:
                seen.add(value)
                found.append((value, index.hit(match.start(), match.end() + len(value))))
    return found


def title_name(indexes: list[TextIndex]) -> tuple[str, dict] | None:
    """封面标题（没有标签行时用）：前 60 行里第一行以"项目""工程"结尾的；工程量清单的行是分部名称，不算。"""
    for index in sorted(indexes, key=name_source_rank):
        if name_source_rank(index) == 3:
            continue
        for line_index, line in enumerate(index.lines[:60]):
            text = re.sub(r"\s+", "", line)
            if NAME_LABEL.search(text):
                continue  # 带"项目名称："标签的行已按标签取过
            if re.search(r"(项目|工程)$", text) and "示范文本" not in text and "编号" not in text:
                return text, {"text": text, "source": index.source(line_index)}
    return None


def find_project_name(indexes: list[TextIndex]) -> tuple[str | None, list[dict]]:
    """标签行优先，标签的不同写法都列进候选，由人对照招标公告核实；一处标签都没有才退回封面标题。
    2026-10-31 真实项目：封面标题折行，按标题取到的是图纸答疑附件的标题，把"——"写成了"--"。"""
    found = labelled_names(indexes)
    if not found:
        title = title_name(indexes)
        found = [title] if title else []
    if not found:
        return None, []
    return found[0][0], [hit for _, hit in found[:MAX_CANDIDATES]]


def find_other_method(indexes: list[TextIndex]) -> tuple[str | None, list[dict]]:
    """合肥四种以外的评标办法（决策 2A）：只认"评标办法采用××法"的句式，转引句（"见第三章评标办法"）不算。"""
    for index, match in find_all(indexes, OTHER_METHOD_PATTERN):
        if not re.search(r"[第章见本]", match.group(1)):
            return match.group(1), [index.hit(match.start())]
    return None, []


def find_method(indexes: list[TextIndex]) -> tuple[str | None, list[dict]]:
    names = "|".join(METHOD_TRACKS)
    explicit = find_all(indexes, rf"评标办法采用({names})")
    if explicit:
        index, match = explicit[0]
        return match.group(1), [index.hit(match.start()) for index, match in explicit]
    other, other_hits = find_other_method(indexes)
    if other:
        return other, other_hits
    counts = Counter(name for index in indexes for name in re.findall(names, index.flat))
    if not counts:
        return None, []
    method = counts.most_common(1)[0][0]
    return method, candidates(indexes, re.escape(method))[:3]


def split_review_items(block: str) -> list[dict]:
    parts = re.split(r"(\d{1,2})[）)]", block)
    items = []
    for number, title in zip(parts[1::2], parts[2::2]):
        title = title.strip("；;。，,、 ")
        if int(number) != len(items) + 1 or not title:
            break  # 编号不连续就停，宁可少列也不乱列
        items.append({"no": int(number), "title": title})
    return items


def find_review_items(indexes: list[TextIndex]) -> tuple[list[dict], str, list[dict]]:
    for index, match in find_all(indexes, r"包括但不限于以下内容[：:]"):
        rest = index.flat[match.end():match.end() + 600]
        stop = re.search(r"一般得?|未提供的|注[：:]|评审标准|优秀", rest)
        items = split_review_items(rest[:stop.start()] if stop else rest)
        if len(items) >= 3:
            return items, index.source(index.offsets[match.start()]), [index.hit(match.start(), match.end() + 300)]
    return [], "", candidates(indexes, r"工程概况")[:3]


def find_grading(indexes: list[TextIndex]) -> tuple[str | None, str, list[dict]]:
    hits = find_all(indexes, r"一般得?[^。]{0,80}?优秀得?[^。]{0,60}。(未提供的，?不得分。)?")
    if not hits:
        return None, "", candidates(indexes, r"优秀")[:3]
    index, match = hits[0]
    return match.group(0), index.source(index.offsets[match.start()]), [index.hit(match.start(), match.end())]


def find_notes(indexes: list[TextIndex]) -> tuple[str | None, str | None, str, list[dict]]:
    """评审注释（含编制建议或编制要求）原文；kind 供篇幅上限沿用。"""
    hits = find_all(indexes, r"施工组织设计编制(建议|要求)")
    if not hits:
        return None, None, "", []
    index, match = hits[0]
    start = index.flat.rfind("注", max(match.start() - 6, 0), match.start())
    start = start if start >= 0 else match.start()
    tail = index.flat[match.end():match.end() + 800]
    stop = re.search(r"\d[\.．、]对于|[一二三四五六七八九十]、|附件", tail)
    end = match.end() + (stop.start() if stop else len(tail))
    return index.flat[start:end], match.group(1), index.source(index.offsets[start]), [index.hit(start, end)]


def first_value(indexes: list[TextIndex], pattern: str, skip: str = r"^(见|符合)") -> tuple[str | None, str, list[dict]]:
    """"标签：取值"按行找：连续文本里取值会和下一行粘在一起（"合格2.12……"）。"""
    found = []
    for index in indexes:
        for line_index, line in enumerate(index.lines):
            match = re.search(pattern, re.sub(r"\s+", "", line))
            if not match:
                continue
            found.append({"text": line.strip(), "source": index.source(line_index)})
            value = match.group(1).strip("，。；,;")
            if value and not re.match(skip, value):
                return value, index.source(line_index), found[-MAX_CANDIDATES:]
            if len(found) >= MAX_CANDIDATES:
                return None, "", found
    return None, "", found


def find_page_limit(indexes: list[TextIndex]) -> tuple[int | None, str, list[dict]]:
    hits = find_all(indexes, r"(?:不超过|不得超过|不超出|控制在)(\d{1,3})页")
    if not hits:
        return None, "", []
    index, match = hits[0]
    return int(match.group(1)), index.source(index.offsets[match.start()]), [index.hit(max(match.start() - 30, 0))]


def suggest_track(method: str | None, ai_hits: list[dict], blind_hits: list[dict]) -> tuple[str | None, list[dict]]:
    """按 hefei-rules 第二节判定规则给建议；AI 与暗标同时出现不给建议（硬停）。"""
    if ai_hits and blind_hits:
        return None, [{"text": "AI 条款与暗标条款同时出现：硬停，请用户向招标人澄清", "source": "scaffold"}]
    if is_other_method(method):
        return None, [{"text": OTHER_METHOD_NOTE, "source": "scaffold"}]
    allowed = METHOD_TRACKS.get(method or "", ())
    if len(allowed) == 1:
        return allowed[0], []
    if method == "综合评估法" and (ai_hits or blind_hits):
        return ("T-AI" if ai_hits else "T-暗标"), []
    return None, [{"text": "评标办法或 AI、暗标条款没找到，轨道判不清：核对原文，仍不清就硬停", "source": "scaffold"}]


def fill_identity(card: dict, indexes: list[TextIndex]) -> dict:
    name, name_hits = find_project_name(indexes)
    method, method_hits = find_method(indexes)
    ai_hits = sentence_hits(indexes, r"类人[”\"]?评审")
    blind_hits = sentence_hits(indexes, r"暗标")
    track, notes = suggest_track(method, ai_hits, blind_hits)
    card["project_name"] = suggest(card["project_name"], name, name_hits[0]["source"] if name_hits else "", name_hits)
    card["evaluation_method"] = suggest(card["evaluation_method"], method,
                                        method_hits[0]["source"] if method_hits else "", method_hits)
    track_entry = suggest(card["track"], track, method_hits[0]["source"] if method_hits else "", notes)
    track_entry["signals"] = [*method_hits[:1], *ai_hits[:1], *blind_hits[:1]]
    track_entry["handoff"] = HANDOFF_TEXT if track == "T-定档" else ""
    card["track"] = track_entry
    card["ai_clause"] = suggest(card["ai_clause"], ai_hits[0]["text"] if ai_hits else None,
                                ai_hits[0]["source"] if ai_hits else "", ai_hits)
    card["blind_clause"] = suggest(card["blind_clause"], blind_hits[0]["text"] if blind_hits else None,
                                   blind_hits[0]["source"] if blind_hits else "", blind_hits)
    return {"项目名称": bool(name), "评标办法": method, "评审轨道建议": track,
            "AI 条款": len(ai_hits), "暗标条款": len(blind_hits)}


def suggest_rule_scope(indexes: list[TextIndex]) -> tuple[str | None, list[dict]]:
    """规则依据范围的候选：不在合肥的看建设地点，在合肥的再看资质。缺一项就不猜。"""
    place, _, place_hits = first_value(indexes, PLACE_PATTERN)
    if not place:
        return None, place_hits
    if not any(word in place for word in HEFEI_PLACES):
        return OUTSIDE_HEFEI, place_hits
    qualification = clue_hits(indexes, QUALIFICATION_PATTERN, before=30)
    if not qualification:
        return None, place_hits
    text = " ".join(hit["text"] for hit in qualification)
    civil = any(word in text for word in CIVIL_QUALIFICATIONS)
    return (HEFEI_CIVIL if civil else HEFEI_OTHER), [*place_hits, *qualification[:2]]


def fill_qingtian(card: dict, indexes: list[TextIndex]) -> dict:
    """启用情况看 AI 类人评审条款和评标办法（hefei-rules 第一节），只给候选。没找到信号不写"未启用"：条款可能换了说法，
    由人读过原文再定。要在 fill_identity 之后调用，信号从那里取。"""
    method_entry, ai_entry = card["evaluation_method"], card["ai_clause"]
    ai_hits = ai_entry.get("candidates") or []
    method_hits = method_entry.get("candidates") or []
    enabled = bool(ai_hits) or method_entry["value"] == GUIDE_REQUIRES_QINGTIAN
    signals = [*ai_hits[:1], *method_hits[:1]] if enabled else []
    scope, scope_hits = suggest_rule_scope(indexes)
    entry = suggest(card[QINGTIAN_FIELD], QINGTIAN_ON if enabled else None, signals[0]["source"] if signals else "",
                    [*signals, *scope_hits, {"text": QINGTIAN_NOTE, "source": "scaffold"}])
    entry.update(rule_scope=scope, signals=signals)
    card[QINGTIAN_FIELD] = entry
    return {"青天启用": entry["value"], "规则依据范围": scope}


def fill_scoring(card: dict, indexes: list[TextIndex]) -> dict:
    items, items_source, item_hits = find_review_items(indexes)
    grading, grading_source, grading_hits = find_grading(indexes)
    notes, kind, notes_source, notes_hits = find_notes(indexes)
    pages, pages_source, page_hits = find_page_limit(indexes)
    card["review_items"] = suggest(card["review_items"], items, items_source, item_hits)
    card["grading"] = suggest(card["grading"], grading, grading_source, grading_hits)
    card["review_notes"] = suggest(card["review_notes"], notes, notes_source, notes_hits)
    card["page_limit"] = suggest(card["page_limit"], pages, pages_source, page_hits)
    card["page_limit"]["kind"] = kind if pages else None
    # 扣分句留在评审注释原文里；摘要单列出来，提醒阶段 2 照抄进招标文件格式规定的 penalty
    return {"评审内容": len(items), "档次": bool(grading), "评审注释": kind, "扣分原文": penalty_sentence(notes),
            "篇幅上限": pages}


def fill_requirements(card: dict, indexes: list[TextIndex]) -> dict:
    schedule, schedule_source, schedule_hits = first_value(indexes, r"计划工期[：:]?(\d{1,4}(?:个)?日历天)")
    quality, quality_source, quality_hits = first_value(indexes, r"质量标准[：:]([^，。；,;：:]{1,30})")
    safety, safety_source, safety_hits = first_value(indexes, r"安全(?:生产|文明施工)?目标[：:]([^。；;]{1,40})")
    # 推荐规则各招标文件写法不一（居中、次低），P03 要用户看过原文，所以连同入围规则一起列候选
    shortlist = candidates(indexes, r"前\d+家入围", before=60) + candidates(indexes, r"中标候选人推荐规则")
    preliminary = candidates(indexes, r"初步评审标准")
    specified = section_hits(indexes, TENDER_SPECIFIED_PATTERN)
    mandatory = [*candidates(indexes, r"[★▲]"), *candidates(indexes, r"实质性要求", before=20), *specified]
    card["schedule"] = suggest(card["schedule"], schedule, schedule_source, schedule_hits)
    card["quality_standard"] = suggest(card["quality_standard"], quality, quality_source, quality_hits)
    card["safety_target"] = suggest(card["safety_target"], safety, safety_source, safety_hits)
    card["shortlist_rule"] = suggest(card["shortlist_rule"], None, "", shortlist)
    card["preliminary_review"] = suggest(card["preliminary_review"], [], "", preliminary)
    card["mandatory"] = suggest(card["mandatory"], [], "", mandatory)
    card["format"] = suggest(card["format"], card["format"]["value"], "",
                             candidates(indexes, r"(?:字体|字号|行距|页边距)[：:]", before=10))
    addenda = addenda_hits(indexes)
    if addenda:
        # 可选字段：没有答疑更正就不出现；有就要逐条核对、落到相应字段（project_cards.check_addenda）
        card["addenda_changes"] = {"candidates": addenda, "checked": False}
    return {"工期": schedule, "质量标准": quality, "安全目标": safety, "入围规则候选": len(shortlist),
            "初步评审表候选": len(preliminary), "强制条款候选": len(mandatory), "招标指定候选": len(specified),
            "答疑更正候选": len(addenda)}


def clue_hits(indexes: list[TextIndex], pattern: str, before: int = 0) -> list[dict]:
    """工程类别的原文线索。真实招标文件的资质要求一段里"施工总承包"出现好几次，落在上一条摘录里的不再另列；
    须知正文的"招标范围：见招标公告"是转引，不是线索。"""
    found, covered = [], {}
    for index, match in find_all(indexes, pattern):
        if match.start() < covered.get(index.name, 0) or index.flat.startswith("见", match.end()):
            continue
        start = max(match.start() - before, 0)
        covered[index.name] = start + EXCERPT_CHARS
        found.append(index.hit(start))
        if len(found) >= MAX_CATEGORY_HITS:
            break
    return found


def bill_scan(indexes: list[TextIndex], cards: list[dict]) -> tuple[list[dict], str, Counter]:
    """清单文件的工作表名，和每张卡的编码前缀对上的行数（每张卡单独数，一行可以同时算进几张卡）。"""
    found, names, counts = [], [], Counter()
    for index in indexes:
        if Path(index.name).suffix.lower() not in BILL_SUFFIXES:
            continue
        sheets, rows = [], Counter()
        for line in index.lines:
            mark = SHEET_MARK.match(line.strip())
            if mark:
                sheets.append(mark.group(1).strip())
                continue
            cells = [value.strip() for value in line.split("\t") if value.strip()]
            at = next((at for at, value in enumerate(cells) if BOQ_CODE.match(value)), None)
            if at is not None:
                item = cells[at + 1] if at + 1 < len(cells) else ""
                rows.update(card["name"] for card in cards if boq_card(cells[at], item, [card]))
        names += [index.name, *sheets]
        counts += rows
        if sheets:
            found.append({"text": f"工作表：{'、'.join(sheets)}", "source": index.name})
        if rows:
            listed = "、".join(f"{name} {count} 行" for name, count in rows.most_common())
            found.append({"text": f"清单编码对上各类别知识卡的行数：{listed}（行数不是造价占比）", "source": index.name})
    return found, " ".join(names), counts


def likely_categories(cards: list[dict], texts: dict[str, str], counts: Counter) -> list[str]:
    """按卡片的线索词（资质、招标范围、清单名称）和清单编码，列出可能涉及的类别及对上的线索。"""
    likely = []
    for card in cards:
        groups = [label for label, key in (("资质", "qualification"), ("招标范围", "scope"), ("清单名称", "bill"))
                  if any(word in texts[key] for word in card["signals"][key])]
        groups += ["清单编码"] if counts.get(card["name"]) else []
        if groups:
            likely.append(f"{card['name']}（{'、'.join(groups)}）")
    return likely


def fill_category(card: dict, indexes: list[TextIndex]) -> dict:
    """只列线索，value 保持模板的空值：占比最大的主类别由用户按清单金额和招标范围判断。"""
    delivered = [loaded for name in CATALOG if (loaded := load_card(name)) is not None]
    qualification = clue_hits(indexes, QUALIFICATION_PATTERN, before=30)
    scope = clue_hits(indexes, SCOPE_PATTERN)
    bill_hits, bill_names, counts = bill_scan(indexes, delivered)
    texts = {"qualification": " ".join(hit["text"] for hit in qualification),
             "scope": " ".join(hit["text"] for hit in scope), "bill": bill_names}
    likely = likely_categories(delivered, texts, counts)
    summary = ("按已交付的类别知识卡，可能涉及：" + "、".join(likely)) if likely else "已交付的类别知识卡线索都没对上"
    note = {"text": f"{summary}。主类别按占比最大的工程类型由用户判断（导则 1.3.3（1）），其余选进涉及专业或场景；"
                    "名录里没有的工程类型照招标文件的叫法写，没有知识卡，只按招标文件和红线写",
            "source": "scaffold"}
    entry = card[CATEGORY_FIELD]
    card[CATEGORY_FIELD] = suggest(entry, entry["value"], "", [*qualification, *scope, *bill_hits, note])
    return {"工程类别线索": likely}


def tender_indexes(project_dir: Path) -> list[TextIndex]:
    report = load_json(project_dir / "analysis" / "extraction-report.json", "提取报告")
    if not report.get("gate_ok"):
        raise ValueError("提取报告未通过（R9）：先处理 needs_ocr / failed 文件，再解标")
    indexes = []
    for item in report.get("items") or []:
        if item.get("kind", "tender") == "tender" and item.get("status") == "ok":
            output = Path(item["output"])
            indexes.append(build_index(Path(item["file"]).name, output.read_text(encoding="utf-8")))
    if not indexes:
        raise ValueError("提取报告里没有可用的招标文件文本")
    return indexes


def scaffold_rule_card(project_dir: Path) -> dict:
    project_dir, state = load_project(project_dir)
    indexes = tender_indexes(project_dir)
    card = rule_card_template()
    located = {**fill_identity(card, indexes), **fill_qingtian(card, indexes), **fill_category(card, indexes),
               **fill_scoring(card, indexes), **fill_requirements(card, indexes), **fill_ref_fields(card, indexes),
               **fill_bid_forms(card, indexes)}
    target = project_dir / RULE_CARD_FILE
    if target.exists():
        # 已有规则卡里有核实过的内容，不覆盖；候选另存，由人对照合并
        target = target.with_name(f"rule-card-候选-{datetime.now():%Y%m%d-%H%M%S}.json")
    target.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    issues = validate_rule_card(card, project_dir, state)
    views = write_rule_card_views(project_dir, card, state.get("project_name", ""), issues) \
        if target.name == "rule-card.json" else []
    return {"rule_card": str(target), "views": [str(path) for path in views], "located": located,
            "issues": len(issues), "note": "全部是候选：对照招标文件原文逐项核实，改 checked 后再请用户确认"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从提取文本出规则卡候选（每条带出处，全部待核对）。")
    parser.add_argument("project", type=Path, help="项目目录。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = scaffold_rule_card(args.project)
    except (OSError, ValueError) as exc:
        print(f"规则卡候选生成失败: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
