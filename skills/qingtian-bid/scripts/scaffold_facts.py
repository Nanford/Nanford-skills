"""Draft the fact card from the extracted tender texts, readable drawings and xlsx bills of quantities.

INPUT: <project>/analysis/extraction-report.json and its extracted texts: tender files with status ok
       (招标文件; .xlsx 和转换后提取的 .xls 按工程量清单读), user-declared drawings that still yielded text (图纸);
       analysis/rule-card.json when present (project_category picks the category cards whose boq prefixes
       say which bill rows are main items; no category yet → no bill items); templates/fact-card.json;
       project-state.json.
OUTPUT: analysis/fact-card.json with candidate facts F01… (each with 出处, checked=false; 补遗、答疑里的
        现场限制句和紧邻、深基坑这类现场条件句也作为 场地与周边 候选) and the
        analysis/project-facts.md view; analysis/清单未进候选.md lists the bill items left out, so a miss can be seen.
        An existing fact-card.json is never overwritten: the draft goes
        to analysis/fact-card-候选-<时间>.json. JSON summary of what was located (bill items per card,
        categories whose card is not delivered yet) on stdout.
POS: stage-3 helper of qingtian-bid (design v1 §9, 第 3b 步). It only proposes: every fact must be
     checked against the original before the user confirms. 工期、质量标准、安全目标 belong to the rule
     card and are not copied here. Quantities come only from .xlsx / .xls bills (决策 3b-2A); a PDF bill is
     read by hand and entered with basis 工程量清单. Drawings that yielded no text are read by drawing
     number and entered by hand (决策 2A). Every category card keeps a few bill items (决策 5-5A), so an 安装 or 智能化
     bill is not crowded out by civil keywords; the rest of a total budget is shared, rows matching no card included.
     Only 编码、名称、特征、单位、工程量 are read: a priced bill's 单价 and 合价 never reach a candidate, or the 施组 (gate B13).
     Bill rows start with `cites: []` (决策 D9): a quantity does not depend on any rule row. The other candidates have no
     `cites`, so they count as depending on all rule rows until they are checked (决策 D9-1A).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from category_cards import (
    BOQ_CODE,
    MAIN,
    MODULE,
    SCENARIO,
    boq_card,
    boq_digits,
    no_card_names,
    project_cards,
    selected_names,
)
from fact_resource_cards import FACT_CARD_FILE, card_template, render_facts, validate_fact_card
from project_cards import RULE_CARD_FILE, cell, load_json, load_project
from scaffold_rule_card import ADDENDA_FILE, BILL_SUFFIXES, SHEET_MARK, TextIndex, build_index, find_all


# 示范文本和合同条款里的"见招标公告""符合……"不是取值；合同空白处提取出来是 U+FFFF 占位符
TEMPLATE_BLANK = chr(0xFFFF)  # 写成码位：源码里直接放这个字符看不见
SKIP_VALUE = rf"^(见|符合)|.*{TEMPLATE_BLANK}"
# 招标范围常是一整段多句，取整段到下一条条款，不按句号截
WHOLE_CLAUSE = "整段"
# 日期只取"2026年10月21日"和紧跟的括注，后面常粘着节点工期表的表头
DATE_VALUE = r"\d{4}年\d{1,2}月\d{1,2}日(?:（[^）]{0,30}）)?"
# (类别, 标签, 连续文本里的标签正则, 最多取几个字, 取值形状)。取值常跨行，按连续文本取到下一条条款编号
# 或第一个句号；取值形状是正则的，只取开头符合形状的部分。工期、质量标准、安全目标以规则卡为准，不在这里重复
LABELLED_FACTS = (
    ("场地与周边", "建设地点", r"(?:建设|工程)地点[:：]", 120, None),
    ("规模与结构", "建设规模", r"(?:建设|工程)规模[:：]", 200, None),
    ("规模与结构", "建筑面积", r"建筑面积[:：]", 80, None),
    ("规模与结构", "结构形式", r"结构(?:形式|类型|体系)[:：]", 80, None),
    ("规模与结构", "建筑层数", r"层数[:：]", 80, None),
    ("招标范围", "招标范围", r"招标范围[:：]", 300, WHOLE_CLAUSE),
    ("工期与节点", "计划开工日期", r"计划开工日期[:：]", 80, DATE_VALUE),
    ("工期与节点", "计划竣工日期", r"计划竣工日期[:：]", 80, DATE_VALUE),
)
# 下一条条款："2.10 招标范围："（编号后跟 2～16 个字的标签和冒号），或"1.4.1 投标人资质"这种三级编号。
# 两级编号不带冒号的不算，否则"13.78亩"会被当成条款
NEXT_CLAUSE = re.compile(r"\d{1,2}\.\d{1,2}(?:\.\d+)?(?=[一-龥（）()、]{2,16}[:：])"
                         r"|\d{1,2}\.\d{1,2}\.\d{1,2}(?=[一-龥])")
# 清单单位。认不出单位的行整行取不到：2026-11-06 量的两份真实清单各丢了 16 行和 35 行，苗木的"株"全在里面，所以这种行
# 还要列进 LEFT_OUT_FILE。有的清单一格写两个单位："台(套)"、"个（组）"、"节、个"。工日、台班是计日工，不是分项，不收
UNIT_WORDS = (r"m[23²³]?|㎡|㎥|km|t|kg|吨|公里|米|立方米|平方米|延长米|个|件|樘|根|套|台|项|座|处|块|只|组|支|副|付|对|张|条|架|节"
              r"|点|批|部|盏|株|棵|丛|缸|段|道|口|孔|眼|榀|片|卷|袋|间|户|面|回路|系统")
BOQ_UNIT = re.compile(rf"^(?:{UNIT_WORDS})(?:[（(](?:{UNIT_WORDS})[）)]|[、/](?:{UNIT_WORDS}))?$", re.IGNORECASE)
# 施组要写进物资计划和施工方法的分项进候选；总数封顶，避免事实卡被几百行清单淹没。每张类别知识卡先保几条（boq 的
# 编码前缀和名称关键词，决策 5-5A）：只按总数截断时，排在前面的单位工程（常是土建）会把安装、智能化的分项挤掉。
# 剩下的名额不分卡，对不上卡的行也在内。只按卡平分时大卡吃亏：2026-11-06 量的真实清单 200 多行、一百多个名称，
# 每卡 8 条只有四十多条候选，造价覆盖约三成，同一 9 位编码下的铺装、台阶大项都进不来；总名额 150 时全部进来。
# 取的时候按 6 位编码（分部分项）轮流，免得几十行门窗占满名额；同组工程量大的在前，同一分部的单位多半相同，比得上
BOQ_CARD_FLOOR = 8
MAX_BOQ_TOTAL = 150
BOQ_SECTION_DIGITS = 6
OTHER_ITEMS = "其他分项（没对上类别知识卡）"
LUMP_SUM_UNIT = "项"  # 对不上卡又按项计的是总价措施（安全文明施工这类），不是要写进物资计划的分项
LEFT_OUT_FILE = "analysis/清单未进候选.md"
# 一行清单归哪张卡：场景卡先认（拆除、加固类行不论编在哪个专业下都算改造），再到专业卡，最后主类别卡
CARD_ORDER = (SCENARIO, MODULE, MAIN)
# 补遗、答疑里的现场限制，施工总平面和临时设施不得与之矛盾。2026-10-30 核对的真实合肥项目：补疑写了"严禁在室外
# 堆放""现场不具备且不允许设置办公区、生活区"，答疑写了"现场不具备材料堆场、搭设加工区……条件"。招标文件正文里的
# "☑不允许""严禁工程转包"多是程序条款，所以只读文件名像补遗的文件，整句作候选，由人删掉不是现场条件的。
# 只认禁止类词会漏掉不带否定词的现场条件（2026-10-31 真实项目："紧邻居民区……夜间施工管控""沟槽开挖存在深基坑
# 作业……钢板桩"，后者是补危大清单的主要依据），所以再加现场条件词；两个真实项目各出 10、8 条候选
SITE_LIMIT = re.compile(r"严禁|不允许|不具备|禁止|紧邻|夜间|袋装|成品保护|深基坑|专家论证|交通疏导|交通封闭|全密闭|"
                        r"二次搬运|狭窄|临时用地|围挡|进场路线")
SENTENCE_END = "。；！？"
SITE_LIMIT_CHARS = 200
MAX_SITE_LIMIT_FACTS = 20


def text_groups(project_dir: Path) -> tuple[list[tuple[str, list[TextIndex]]], list[tuple[str, list[str]]]]:
    """按依据分组：招标文件文本、读得出字的图纸；表格（.xlsx、.xls）招标文件另按工程量清单读。"""
    report = load_json(project_dir / "analysis" / "extraction-report.json", "提取报告")
    if not report.get("gate_ok"):
        raise ValueError("提取报告未通过（R9）：先完成阶段 1")
    groups: dict[str, list[TextIndex]] = {"招标文件": [], "图纸": []}
    bills = []
    for item in report.get("items") or []:
        if item.get("status") != "ok" or item.get("kind") not in ("tender", "drawing"):
            continue
        name, text = Path(item["file"]).name, Path(item["output"]).read_text(encoding="utf-8")
        if item["kind"] == "tender" and Path(item["file"]).suffix.lower() in BILL_SUFFIXES:
            bills.append((name, text.splitlines()))
        else:
            groups["招标文件" if item["kind"] == "tender" else "图纸"].append(build_index(name, text))
    if not groups["招标文件"] and not bills:
        raise ValueError("提取报告里没有可用的招标文件文本")
    return [(basis, indexes) for basis, indexes in groups.items() if indexes], bills


def new_fact(category: str, text: str, basis: str, source: str, found: list[dict] | None = None) -> dict:
    fact = {"id": "", "category": category, "text": text, "basis": basis, "source": source, "checked": False}
    if found:
        fact["candidates"] = found
    return fact


def clause_value(index: TextIndex, match: re.Match, limit: int, shape: str | None) -> str:
    rest = index.flat[match.end():match.end() + limit]
    stop = NEXT_CLAUSE.search(rest)
    rest = rest[:stop.start()] if stop else rest
    if shape and shape != WHOLE_CLAUSE:
        shaped = re.match(shape, rest)
        return shaped.group(0) if shaped else ""
    if shape is None and "。" in rest:
        rest = rest[:rest.index("。")]
    return rest.strip("，。；,;")


def labelled_fact(groups: list[tuple[str, list[TextIndex]]], spec: tuple) -> dict | None:
    """招标文件优先；招标文件没写的（如结构形式、层数），再到读得出字的图纸说明里找。
    命中的原文全列进 candidates，公告和前附表写法不一时由人对照。"""
    category, label, pattern, limit, shape = spec
    for basis, indexes in groups:
        hits = find_all(indexes, pattern)
        for index, match in hits:
            value = clause_value(index, match, limit, shape)
            if value and not re.match(SKIP_VALUE, value):
                found = [hit_index.hit(hit.start()) for hit_index, hit in hits]
                return new_fact(category, f"{label}：{value}", basis, index.source(index.offsets[match.start()]), found)
    return None


def labelled_facts(groups: list[tuple[str, list[TextIndex]]]) -> list[dict]:
    return [fact for fact in (labelled_fact(groups, spec) for spec in LABELLED_FACTS) if fact]


def sentence_span(flat: str, start: int, end: int) -> tuple[int, int]:
    """命中词所在的整句：前后各找到句号、分号为止，过长的以命中词为中心截到 SITE_LIMIT_CHARS 字。"""
    begin = max((flat.rfind(mark, 0, start) for mark in SENTENCE_END), default=-1) + 1
    stops = [at for at in (flat.find(mark, end) for mark in SENTENCE_END) if at >= 0]
    stop = min(stops) + 1 if stops else len(flat)
    begin = max(begin, start - SITE_LIMIT_CHARS // 2)
    return begin, min(stop, begin + SITE_LIMIT_CHARS)


def site_limit_facts(groups: list[tuple[str, list[TextIndex]]]) -> list[dict]:
    """补遗、答疑里含 SITE_LIMIT 禁止类词或现场条件词的句子，作为场地与周边的候选；同一句只收一次。"""
    facts, seen = [], set()
    for basis, indexes in groups:
        if basis != "招标文件":
            continue
        for index in (index for index in indexes if ADDENDA_FILE.search(index.name)):
            covered = -1
            for match in SITE_LIMIT.finditer(index.flat):
                if match.start() < covered:
                    continue  # 同一句里第二个限制词
                begin, stop = sentence_span(index.flat, match.start(), match.end())
                covered = stop
                text = index.flat[begin:stop].strip("，。；,;")
                if text in seen:
                    continue
                seen.add(text)
                facts.append(new_fact("场地与周边", text, basis, index.source(index.offsets[begin])))
                if len(facts) >= MAX_SITE_LIMIT_FACTS:
                    return facts
    return facts


def number(text: str) -> int | float | None:
    try:
        value = float(text.replace(",", ""))
    except ValueError:
        return None
    if value <= 0:
        return None
    return int(value) if value.is_integer() else value


def boq_row(cells: list[str]) -> dict | None:
    """清单行：编码、名称、特征、单位、工程量。按"编码在前、单位后跟数量"认，不按列号。

    空单元格先去掉：有的空单元格没导出，有的合并单元格导出成空列（2026-10-30 真实合肥清单里，编码与名称、
    单位与工程量之间各隔一个空列），去掉后两种排法一样认。
    """
    cells = [value for value in cells if value]
    code_at = next((at for at, value in enumerate(cells) if BOQ_CODE.match(value)), None)
    if code_at is None or code_at + 1 >= len(cells):
        return None
    for at in range(code_at + 2, len(cells) - 1):
        amount = number(cells[at + 1]) if BOQ_UNIT.match(cells[at]) else None
        if amount is not None:
            code = cells[code_at]
            # 编码存成数字时 12 位的会丢掉前导零；带字母前缀的补充项编码不补
            return {"code": code.zfill(12) if len(code) == 11 and code.isdigit() else code, "name": cells[code_at + 1],
                    "unit": cells[at], "amount": amount,
                    # 只取到工程量：限价表登记成招标文件时，后面几列是单价和合价，进了候选就可能写进施组（门禁 B13）
                    "text": " ".join(value for value in cells[code_at:at + 2] if value)}
    return None


def bill_rows(bills: list[tuple[str, list[str]]]) -> list[tuple[dict, str]]:
    """全部清单里认得出的分项行和出处，按清单原顺序。"""
    rows = []
    for name, lines in bills:
        sheet = ""
        for line_index, line in enumerate(lines):
            mark = SHEET_MARK.match(line.strip())
            if mark:
                sheet = mark.group(1).strip()
                continue
            row = boq_row([value.strip() for value in line.split("\t")])
            if row is not None:
                rows.append((row, f"{name} 工作表「{sheet}」（提取文本第{line_index + 1}行）"))
    return rows


def unpicked_names(entries: list[tuple[int, dict, str]], picked_names: set[str]) -> list[tuple[int, dict, str]]:
    """同名分项只留第一次出现的，已经取过的名称不再取。"""
    seen = set(picked_names)
    kept = []
    for entry in entries:
        if entry[1]["name"] not in seen:
            seen.add(entry[1]["name"])
            kept.append(entry)
    return kept


def take_by_section(entries: list[tuple[int, dict, str]], limit: int) -> list[tuple[int, dict, str]]:
    """按 6 位编码分组，每组工程量大的在前，先取每组第一条、再取第二条……直到取满。"""
    sections: dict[str, list[tuple[int, dict, str]]] = {}
    for entry in entries:
        sections.setdefault(boq_digits(entry[1]["code"])[:BOQ_SECTION_DIGITS], []).append(entry)
    for group in sections.values():
        group.sort(key=lambda entry: -entry[1]["amount"])
    picked, depth = [], 0
    while len(picked) < limit and any(depth < len(group) for group in sections.values()):
        picked += [group[depth] for group in sections.values() if depth < len(group)][:limit - len(picked)]
        depth += 1
    return picked


def pick_bill_rows(entries: list[tuple[int, dict, str]], owners: dict[int, str]) -> list[tuple[int, dict, str]]:
    """每张卡先保底；保底取完还有名额，剩下的行不分卡，一起轮流取。保底不受总名额限制：卡多时宁可多几条。"""
    picked: list[tuple[int, dict, str]] = []
    names: set[str] = set()
    for card_name in dict.fromkeys(owners.values()):
        if card_name != OTHER_ITEMS:
            own = [entry for entry in entries if owners[entry[0]] == card_name]
            floor = take_by_section(unpicked_names(own, names), BOQ_CARD_FLOOR)
            picked += floor
            names.update(entry[1]["name"] for entry in floor)
    return picked + take_by_section(unpicked_names(entries, names), max(MAX_BOQ_TOTAL - len(picked), 0))


def bill_facts(bills: list[tuple[str, list[str]]], cards: list[dict],
               include_other: bool = False) -> tuple[list[dict], dict[str, int]]:
    """清单分项候选（按清单原顺序）和每张卡取了几条。include_other：类别定了才取对不上卡的行，没定时一条不取。"""
    ordered = sorted(cards, key=lambda card: CARD_ORDER.index(card["kind"]))
    entries: list[tuple[int, dict, str]] = []
    owners: dict[int, str] = {}
    for at, (row, source) in enumerate(bill_rows(bills)):
        owner = boq_card(row["code"], row["name"], ordered)
        if owner is None and include_other and row["unit"] != LUMP_SUM_UNIT:
            owner = OTHER_ITEMS
        if owner is not None:
            owners[at] = owner
            entries.append((at, row, source))
    picked = pick_bill_rows(entries, owners)
    facts = []
    for _, row, source in sorted(picked, key=lambda entry: entry[0]):
        fact = new_fact("工程量", row["text"][:200], "工程量清单", source)
        fact["quantity"] = {"item": row["name"], "amount": row["amount"], "unit": row["unit"]}
        fact["cites"] = []  # 清单数量不随规则卡变；清单文件换了由变更单判断（决策 D9-2A）
        facts.append(fact)
    return facts, dict(Counter(owners[entry[0]] for entry in picked))


def unread_rows(bills: list[tuple[str, list[str]]]) -> list[str]:
    """带编码却没认成清单行的表格行（单位不认识，或没有工程量）。只列编码和名称：后面几列可能是金额。"""
    rows = []
    for name, lines in bills:
        for line_index, line in enumerate(lines):
            cells = [value.strip() for value in line.split("\t") if value.strip()]
            code_at = next((at for at, value in enumerate(cells) if BOQ_CODE.match(value)), None)
            if code_at is None or code_at + 1 >= len(cells) or boq_row(cells) is not None:
                continue
            label = "" if number(cells[code_at + 1]) is not None else cells[code_at + 1]  # 没写名称时，下一列可能就是金额
            rows.append(f"| {cell(cells[code_at])} | {cell(label)} | {cell(f'{name}（提取文本第{line_index + 1}行）')} |")
    return rows


def write_left_out(project_dir: Path, bills: list[tuple[str, list[str]]], bill: list[dict], project_name: str) -> int:
    """没进候选的分项写成一份清单，同名只列一次：候选有上限，漏了什么要看得见。只有工程量，没有金额。"""
    seen = {fact["quantity"]["item"] for fact in bill}
    rows = []
    for row, source in bill_rows(bills):
        if row["name"] not in seen:
            seen.add(row["name"])
            rows.append(f"| {cell(row['code'])} | {cell(row['name'])} | {cell(row['unit'])} | {row['amount']} | {cell(source)} |")
    unread = unread_rows(bills)
    lines = [f"# 清单没进候选的分项（{project_name}）", "",
             f"> 事实卡的清单候选最多 {MAX_BOQ_TOTAL} 条（每张类别知识卡保底 {BOQ_CARD_FLOOR} 条）。这里是其余的，同名只列一次。"
             "施组要用的，照清单原件录入事实卡。", "",
             *(["| 编码 | 名称 | 单位 | 工程量 | 出处 |", "|---|---|---|---|---|", *rows] if rows else ["认得出的分项都进了候选。"]), ""]
    if unread:
        lines += ["## 带编码但没认出来的行", "", "> 单位不认识或没有工程量，上面的取法碰不到这些行。只列编码和名称，单位和工程量看原件。", "",
                  "| 编码 | 名称 | 出处 |", "|---|---|---|", *unread, ""]
    (project_dir / LEFT_OUT_FILE).write_text("\n".join(lines), encoding="utf-8")
    return len(rows) + len(unread)


def bill_note(rule_card: dict, undelivered: list[str]) -> str:
    selected = selected_names(rule_card)
    if not selected and not no_card_names(rule_card):
        return "；规则卡还没定工程类别，清单分项没取：阶段 2 确认规则卡后重跑本脚本"
    # 定了类别但名录里都没有的（决策 D11），不按卡分，也照样取
    how = f"每张类别知识卡保底 {BOQ_CARD_FLOOR} 条" if selected else "本项目的工程类别没有类别知识卡，清单分项不按卡分"
    skipped = f"；类别知识卡尚未交付的（{'、'.join(undelivered)}），这些分项算在其他分项里" if undelivered else ""
    return f"；{how}，总数最多 {MAX_BOQ_TOTAL} 条；没进候选的列在 {LEFT_OUT_FILE}，施组要用的照原件补{skipped}"


def scaffold_facts(project_dir: Path) -> dict:
    project_dir, state = load_project(project_dir)
    groups, bills = text_groups(project_dir)
    rule_path = project_dir / RULE_CARD_FILE
    # 阶段 2 没做完也能先出候选，只是还不知道工程类别：清单分项先不取，结果里写明
    rule_card = load_json(rule_path, "规则卡") if rule_path.is_file() else {}
    chosen, undelivered = project_cards(rule_card)
    category_set = bool(selected_names(rule_card) or no_card_names(rule_card))
    bill, per_card = bill_facts(bills, chosen, include_other=category_set)
    left_out = write_left_out(project_dir, bills, bill, state.get("project_name", "")) if category_set and bills else None
    card = card_template("fact-card.json")
    facts = labelled_facts(groups) + site_limit_facts(groups) + bill
    for number_at, fact in enumerate(facts, start=1):
        fact["id"] = f"F{number_at:02d}"
    card["facts"] = facts
    target = project_dir / FACT_CARD_FILE
    if target.exists():
        # 已有事实卡里有核实过的内容，不覆盖；候选另存，由人对照合并
        target = target.with_name(f"fact-card-候选-{datetime.now():%Y%m%d-%H%M%S}.json")
    target.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    views = []
    if target.name == "fact-card.json":
        view = project_dir / "analysis" / "project-facts.md"
        view.write_text(render_facts(card, state.get("project_name", ""), validate_fact_card(card)), encoding="utf-8")
        views.append(str(view))
    located = {category: sum(1 for fact in facts if fact["category"] == category)
               for category in dict.fromkeys(fact["category"] for fact in facts)}
    return {"fact_card": str(target), "views": views, "located": located, "boq_by_card": per_card,
            "boq_left_out": left_out, "undelivered_cards": undelivered,
            "note": "全部是候选：对照原文逐条核实、补齐规模结构和周边环境，改 checked 后再请用户确认；"
                    "补遗、答疑里的限制句逐句看是不是现场条件，不是的删掉；PDF 清单和读不出字的图纸按原件手工录入"
                    + bill_note(rule_card, undelivered)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从提取文本和 xlsx 工程量清单出事实卡候选（每条带出处，全部待核对）。")
    parser.add_argument("project", type=Path, help="项目目录。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = scaffold_facts(args.project)
    except (OSError, ValueError) as exc:
        print(f"事实卡候选生成失败: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
