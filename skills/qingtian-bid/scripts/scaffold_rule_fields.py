"""Candidates for the rule card fields located by ref: 勾选框、关键日期、限价 as draft rows, the rest as excerpts.

INPUT: TextIndex objects of the tender texts (tender_text); a rule card dict from templates/rule-card.json.
OUTPUT: fill_ref_fields() writes draft rows and candidates into the card, always checked=false, and returns a summary;
        find_checkboxes() (outside the 投标文件格式 chapter), find_key_dates(), find_price_limit() and find_profile()
        do the reading.
POS: stage-2 helper called by scaffold_rule_card.py. It reads layouts seen in Hefei tenders (前附表的勾选框、"时间：……前"、
     "投标截止时间 N 日前"), so everything here is a suggestion to check against the original (R1, R3). 资格条款、表外致命项、
     定标规则 need a person to read them, so they only get excerpts with a ready-made ref.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from datetime import datetime, timedelta

from project_profile import AWARD_MODE, PROFILE_KINDS
from rule_card_fields import KEY_DATE_KINDS, SUBMIT_DEADLINE, compact
from scan_bid_forms import chapter_span
from tender_text import MAX_CANDIDATES, TOC_LEADER, TextIndex, find_all, ref_at, ref_hit


BOX_TICKED = "☑☒■"
BOX_EMPTY = "□☐"
BOX = re.compile(f"[{BOX_TICKED}{BOX_EMPTY}]")
# 新条款的开头："1.4.2""3.2.4 最高投标限价""（4）是否随机发放签号"
CLAUSE_START = re.compile(r"^(?:\d{1,2}(?:\.\d{1,2})+|[（(]\d{1,2}[）)])")
MAX_OPTION_GAP = 6  # 两个选项之间隔的行数上限：选项正文会折行，真实招标文件里见过隔 5 行的
LABEL_REACH = 3  # 条款名称往上最多找几行：前附表的名称列常被折成两三行
OPTION_KEYWORD_CHARS = 10
MAX_SCAN = 60  # 候选落在上一条摘录里会被跳过，所以多扫一些

DATE_TEXT = r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})[时:：](\d{1,2})分?"
SUBMIT_PATTERN = rf"(?:投标文件递交的?截止时间|投标截止时间)[^。；\d]{{0,30}}?{DATE_TEXT}"
CLARIFY_PATTERN = rf"投标人要求澄清招标文件(?:的截止)?时间[：:]?{DATE_TEXT}"
OBJECTION_PATTERN = r"对招标文件有异议的，?应在投标截止时间(\d{1,3})(?:个)?日前"
INQUIRY_PATTERN = r"询标[^。；]{0,60}?\d+分钟(?:[^。；）)]{0,20}?\d+分钟)?"

QUALIFICATION_PATTERN = (r"投标人资质要求|项目经理要求|投标人业绩要求|项目经理业绩要求|财务要求|信誉要求|资质条件[：:]|"
                         r"业绩要求[：:]|项目经理资格|资格评审标准")
OFF_TABLE_PATTERN = r"注册建造师专业、数量|入围[^。；]{0,6}复核|复核通过|解密时间|询标时间|询标至询标结束|智慧信息库"
AWARD_PATTERN = r"(?<!规)定标(?!准)|是否授权评标委员会|授权评标委员会"  # "规定标准"不算
PRICE_LIMIT_PATTERN = r"最高投标限价[：:为]"
PRICE_VALUE = re.compile(r"最高投标限价[：:为]?(.+)$")
LIMIT_LABEL = "最高投标限价"
# 前附表每页重复的表头和"第 4 页 共 240 页"：页数少时够不上页眉的判定，还留在连续文本里
TABLE_HEADER = re.compile(r"^(?:第\d+页(?:共\d+页)?|条款号条款名称.*)$")


def ref_hits(indexes: list[TextIndex], pattern: str, chars: int = 160) -> list[dict]:
    """原文片段加一份现成的 ref。落在上一条摘录里的不再另列，目录行不算。"""
    found, covered = [], {}
    for index, match in find_all(indexes, pattern, limit=MAX_SCAN):
        if match.start() < covered.get(index.name, 0) or TOC_LEADER.match(index.flat, match.end()):
            continue
        covered[index.name] = match.start() + chars
        found.append(ref_hit(index, match.start(), covered[index.name]))
        if len(found) >= MAX_CANDIDATES:
            break
    return found


# ---------- 勾选框 ----------

def option_clause(line: str) -> str | None:
    """勾选框后面紧跟的条款号："☑（6）公布投标人名称"是"（6）"。"""
    match = CLAUSE_START.match(compact(line[BOX.search(line).end():]))
    return match.group() if match else None


def starts_new_group(index: TextIndex, lines: list[int], last: int, position: int) -> bool:
    """这一行的勾选框是不是另一组：离上一个选项太远、中间隔着新条款，或者这一行自己就是新条款。
    "□（6）……""☑（6）……"是同一款的两种写法，算一组；上一行不是这一款的，算另一组。"""
    if position - last > MAX_OPTION_GAP:
        return True
    between = [compact(index.lines[lines[at]]) for at in range(last + 1, position)]
    if any(CLAUSE_START.match(text) for text in between):
        return True
    text = index.lines[lines[position]]
    if CLAUSE_START.match(compact(text[:BOX.search(text).start()])):
        return True
    clause = option_clause(text)
    return clause is not None and clause != option_clause(index.lines[lines[last]])


def box_groups(index: TextIndex, lines: list[int]) -> list[list[int]]:
    groups: list[list[int]] = []
    for position, line_index in enumerate(lines):
        if not BOX.search(index.lines[line_index]):
            continue
        if groups and not starts_new_group(index, lines, groups[-1][-1], position):
            groups[-1].append(position)
        else:
            groups.append([position])
    return groups


def line_options(line: str) -> list[dict]:
    """一行里的选项："□是☑否"是两项；选项文字到下一个勾选框或行尾。"""
    marks = list(BOX.finditer(line))
    ends = [mark.start() for mark in marks[1:]] + [len(line)]
    options = [{"text": compact(line[mark.end():end]), "checked": mark.group() in BOX_TICKED}
               for mark, end in zip(marks, ends)]
    return [option for option in options if option["text"]]


def group_label(index: TextIndex, lines: list[int], first: int) -> str:
    """条款名称：勾选框前面的字，不够再往上找，到条款号、句尾或别的勾选框为止。"""
    text = index.lines[lines[first]]
    parts = [compact(text[:BOX.search(text).start()])]
    for position in range(first - 1, max(first - 1 - LABEL_REACH, -1), -1):
        if CLAUSE_START.match(parts[0]):
            break
        previous = compact(index.lines[lines[position]])
        if TABLE_HEADER.match(previous):
            continue
        if BOX.search(previous) or previous.endswith(("。", "；", ";")):
            break
        parts.insert(0, previous)
    return "".join(parts).rstrip("：:")


def group_row(index: TextIndex, lines: list[int], group: list[int]) -> dict | None:
    options = [option for position in group for option in line_options(index.lines[lines[position]])]
    if not options:
        return None
    # 关键词取第一个选项的字：在连续文本里定位到它，生成的 ref 才一定查得回来
    line_start = bisect_left(index.offsets, lines[group[0]])
    found = index.flat.find(options[0]["text"][:OPTION_KEYWORD_CHARS], line_start)
    return {"label": group_label(index, lines, group[0]), "options": options,
            "count": sum(option["checked"] for option in options),
            "ref": ref_at(index, found if found >= 0 else line_start, OPTION_KEYWORD_CHARS)}


def outside_forms(index: TextIndex) -> list[int]:
    """投标文件格式一章里的勾选框是留给投标人填的（如"目前未在其他项目上任职"），不是招标人的选择。"""
    span = chapter_span(index)
    return [line for line in index.content_lines() if not (span and span[0] <= line < span[1])]


def find_checkboxes(indexes: list[TextIndex]) -> list[dict]:
    """前附表的勾选框，一组一行，勾没勾照原文。分包、联合体、保证金、备选方案都从这里读。"""
    rows: list[dict] = []
    for index in indexes:
        lines = outside_forms(index)
        for group in box_groups(index, lines):
            row = group_row(index, lines, group)
            if row:
                rows.append({"id": f"CB{len(rows) + 1:02d}", **row})
    return rows


# ---------- 关键日期 ----------

def deadline_of(match: re.Match) -> str | None:
    """正则里的年月日时分转成 YYYY-MM-DD HH:MM；招标文件写错日期（如 13 月）的不转，留给人看。"""
    try:
        return datetime(*(int(part) for part in match.groups()[:5])).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return None


def days_before(deadline: str | None, days: int) -> str | None:
    if not deadline:
        return None
    return (datetime.strptime(deadline, "%Y-%m-%d %H:%M") - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")


def date_row(kind: str, index: TextIndex, match: re.Match, deadline: str | None) -> dict:
    return {"kind": kind, "text": index.flat[match.start():match.end()], "deadline": deadline,
            "ref": ref_at(index, match.start())}


def first_date(indexes: list[TextIndex], kind: str, pattern: str) -> dict | None:
    for index, match in find_all(indexes, pattern, limit=1):
        return date_row(kind, index, match, deadline_of(match))
    return None


def objection_row(indexes: list[TextIndex], submit: dict | None) -> dict | None:
    """异议截止写的是"投标截止时间 N 日前"，按投标截止倒推一个日期，出处还是原句。"""
    for index, match in find_all(indexes, OBJECTION_PATTERN, limit=1):
        return date_row("异议截止", index, match, days_before((submit or {}).get("deadline"), int(match.group(1))))
    return None


def inquiry_row(indexes: list[TextIndex]) -> dict | None:
    for index, match in find_all(indexes, INQUIRY_PATTERN, limit=1):
        return date_row("询标时限", index, match, None)
    return None


def find_key_dates(indexes: list[TextIndex]) -> list[dict]:
    """四个事项各占一行；找不到的 text、ref 留空，由人读原文补上，或写明未规定。"""
    submit = first_date(indexes, SUBMIT_DEADLINE, SUBMIT_PATTERN)
    found = {SUBMIT_DEADLINE: submit, "澄清截止": first_date(indexes, "澄清截止", CLARIFY_PATTERN),
             "异议截止": objection_row(indexes, submit), "询标时限": inquiry_row(indexes)}
    blank = {"text": None, "deadline": None, "ref": None}
    return [{"id": f"KD{at:02d}", **(found[kind] or {"kind": kind, **blank})}
            for at, kind in enumerate(KEY_DATE_KINDS, 1)]


# ---------- 最高投标限价 ----------

def find_price_limit(rows: list[dict]) -> dict | None:
    """有勾选框的按勾选框判：勾"有"是设了限价，勾"无"是没设。两个都没勾的判不了，不给建议。"""
    for row in rows:
        if LIMIT_LABEL not in row["label"]:
            continue
        ticked = [option["text"] for option in row["options"] if option["checked"]]
        if len(ticked) != 1:
            return None
        if ticked[0].startswith("无"):
            return {"is_set": False, "value": None, "ref": row["ref"]}
        amount = PRICE_VALUE.search(ticked[0])
        return {"is_set": True, "value": amount.group(1) if amount else ticked[0], "ref": row["ref"]}
    return None


# ---------- 项目画像 ----------

# 一项可以有几个写法，排在前面的先找：磋商文件里也可能提到"招标公告"
PROFILE_PATTERNS = {
    "递交方式": (r"[^。；]{0,30}递交电子投标",),
    "采购体系": (r"政府采购",),
    "采购方式": (r"竞争性磋商|磋商文件", r"竞争性谈判", r"邀请招标|投标邀请书", r"招标公告"),
    "专门面向中小企业": (r"专门面向中小企业",),
    "节能产品": (r"节能产品",),
    "证书查询验证": (r"查询验证|扫描证书上的二维码",),
    "现场限制": (r"多个现场|多现场|不停业|不停工|不停产|边使用边施工|同一楼层局部区域",),
}
AWARD_BOX_LABEL = "授权评标委员会确定中标人"
AWARD_MODE_PATTERN = r"定标按照|授权评标委员会"
PROFILE_EXCERPT_CHARS = 80


def award_mode_row(indexes: list[TextIndex], boxes: list[dict]) -> dict | None:
    """定标方式先看前附表的勾选框。勾选框提取时常丢一个，选项写成"是否"，要对照原文改。"""
    for row in boxes:
        if AWARD_BOX_LABEL in row["label"]:
            ticked = "、".join(option["text"] for option in row["options"] if option["checked"])
            return {"kind": AWARD_MODE, "text": f"{row['label']}：{ticked or '没勾'}", "ref": row["ref"]}
    return excerpt_row(AWARD_MODE, indexes, (AWARD_MODE_PATTERN,))


def excerpt_row(kind: str, indexes: list[TextIndex], patterns: tuple[str, ...]) -> dict | None:
    for pattern in patterns:
        hits = ref_hits(indexes, pattern, PROFILE_EXCERPT_CHARS)
        if hits:
            return {"kind": kind, "text": hits[0]["text"], "ref": hits[0]["ref"]}
    return None


def find_profile(indexes: list[TextIndex], boxes: list[dict]) -> list[dict]:
    """每项一行。找不到的 text、ref 留空，由人读原文补上，或写明未规定：脚本没找到不等于招标文件没写。"""
    found = {AWARD_MODE: award_mode_row(indexes, boxes),
             **{kind: excerpt_row(kind, indexes, patterns) for kind, patterns in PROFILE_PATTERNS.items()}}
    blank = {"text": None, "ref": None}
    return [{"id": f"PF{at:02d}", **(found[kind] or {"kind": kind, **blank})} for at, kind in enumerate(PROFILE_KINDS, 1)]


# ---------- 写进规则卡 ----------

def propose(entry: dict, value: object, found: list[dict]) -> None:
    entry.update({"value": value, "checked": False})
    if found:
        entry["candidates"] = found


def fill_ref_fields(card: dict, indexes: list[TextIndex]) -> dict:
    boxes = find_checkboxes(indexes)
    dates = find_key_dates(indexes)
    limit = find_price_limit(boxes)
    qualification = ref_hits(indexes, QUALIFICATION_PATTERN)
    off_table = ref_hits(indexes, OFF_TABLE_PATTERN)
    award = ref_hits(indexes, AWARD_PATTERN)
    propose(card["checkboxes"], boxes, [])
    propose(card["key_dates"], dates, [])
    propose(card["price_limit"], limit, ref_hits(indexes, PRICE_LIMIT_PATTERN))
    propose(card["qualification"], [], qualification)
    propose(card["off_table"], [], off_table)
    propose(card["award"], [], award)
    profile = find_profile(indexes, boxes)
    propose(card["profile"], profile, [])
    return {"勾选框": len(boxes), "关键日期": [row["kind"] for row in dates if row["ref"]],
            "设了最高投标限价": limit["is_set"] if limit else None, "资格条款候选": len(qualification),
            "表外事项候选": len(off_table), "定标规则候选": len(award),
            "项目画像": [row["kind"] for row in profile if row["ref"]]}
