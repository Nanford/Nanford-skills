"""Consistency gates of qingtian-bid: B1, B4, B9, B10, B11 and W1, checked against the cards and the outline.

INPUT: item drafts (Markdown text) and the confirmed response matrix; the rule card (titles, 工期, ★ clauses
       whose 去处 is 施组; 提交前清单 clauses go to stage 8, 决策 4c-4A),
       the fact card (dates, cited facts) and the resource card (roles, machines, trades, materials); text
       helpers from text_gates.
OUTPUT: hit lists [{gate, match, message}]; heading_issues() (the per-item B1 check, also used by
        writing_gate); b1_hits() and b9_landing_hits() for a full run; b9_manual() for clauses with no value
        to compare.
POS: card-comparison layer of the step-4 gates (design v1 §9 第 4a 步). Patterns are heuristics 【推断】.
     One span is reported by one gate only: B4 owns counts of names that are on the resource card (it can be
     dismissed after review), B10 owns names that are not on the card at all, matched narrowly because it
     cannot be dismissed. B9 checks clauses that carry a value (number＋unit, or a short standard after
     a colon) and every keyword a clause lists (招标指定 clauses such as the tender's 重点难点 are checked by
     keywords only); clauses with neither, like a format clause, stay landed by the matrix and are listed for
     the stage-7 manual check (B12). Numbers in tables are not compared (phase-by-phase plans differ by design).
"""

from __future__ import annotations

import re
from pathlib import Path

from project_cards import TECH_SCOPE, TENDER_SPECIFIED, clause_keywords, scoped_clauses
from response_matrix import COVERAGE_ASPECTS, item_file, item_heading
from text_gates import body_lines, fact_used, hit, number_tokens, visible_lines

CHINESE_COUNTS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
COUNT = r"(\d+|[一二两三四五六七八九十]{1,3})"
PEOPLE_UNITS, MACHINE_UNITS = "人|名", "台|套|部|辆|座"
# 名称后面别把"项目经理部""钢筋工程"当成岗位、工种
NAME_END = r"(?![部程])"
SYNONYMS = (("塔式起重机", "塔吊"), ("施工电梯", "施工升降机"), ("汽车吊", "汽车起重机"),
            ("混凝土输送泵", "地泵", "拖泵"), ("电焊工", "焊工"))
# B10 认得的岗位、工种、机械【推断】：带了人数台数、资源卡里又没有的，才报
VOCAB_PEOPLE = ("项目经理", "项目负责人", "技术负责人", "项目总工", "施工员", "质量员", "安全员", "材料员", "资料员",
                "机械员", "劳务员", "标准员", "预算员", "测量员", "试验员", "钢筋工", "木工", "模板工", "混凝土工",
                "瓦工", "砌筑工", "抹灰工", "架子工", "电工", "焊工", "电焊工", "油漆工", "防水工", "水暖工", "管道工",
                "起重工", "信号工", "司索工", "普工", "装饰工")
VOCAB_MACHINES = ("塔式起重机", "塔吊", "施工电梯", "施工升降机", "物料提升机", "汽车吊", "汽车起重机", "履带吊",
                  "挖掘机", "装载机", "推土机", "压路机", "混凝土泵车", "泵车", "混凝土输送泵", "地泵", "混凝土搅拌机",
                  "砂浆搅拌机", "钢筋切断机", "钢筋弯曲机", "钢筋调直机", "电焊机", "对焊机", "木工圆锯", "打桩机",
                  "旋挖钻机", "发电机", "空压机", "自卸汽车")
SCHEDULE = re.compile(r"(?:总工期|计划工期|合同工期|工期)([^。；;，,\n]{0,10}?)(\d+)\s*个?(?:日历天|天)")
SCHEDULE_SKIP = ("提前", "缩短", "延", "阶段", "节点")  # 这些是分段工期或提前量，不是总工期
DATE_AFTER = re.compile(r"(开工|竣工)(?:日期|时间)?[^。；;\n]{0,6}?(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
DATE_BEFORE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(?:正式|计划)?(开工|竣工)")
CLAUSE_VALUE = re.compile(r"^\s*([^：:]{2,8})[：:]\s*([^：:]{1,30}?)[。；;]?\s*$")
DRAFT_NAME = re.compile(r"^(?!00-)\d{2}-")
ASPECT_WORDS = {"实施": ("施工方法", "施工工艺", "工艺流程", "施工顺序", "施工流程", "施工方案", "做法"),
                "进度": ("进度", "工期", "节点", "横道图", "网络图"),
                "组织": ("组织", "管理机构", "项目部", "岗位", "职责", "劳动力", "人员")}


def heading_issues(text: str, no: int, title: str) -> list[str]:
    """B1（逐项）：第一行是这一项的一级标题，原文照写；全文只有这一个一级标题。版式标记注释不算。"""
    lines = [line.rstrip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("<!--")]
    expected = f"# {item_heading(no, title)}"
    issues = [] if lines and lines[0] == expected else [f"第一行应为一级标题“{expected}”（标题用评审内容原文，R3、R4）"]
    extra = [line for line in lines[1:] if re.match(r"#\s", line)]
    if extra:
        issues.append(f"只能有一个一级标题，多出“{extra[0]}”：下级标题从 ## 起")
    return issues


def b1_hits(project_dir: Path, items: dict[int, dict], texts: dict[int, str]) -> list[dict]:
    """B1（整份）：每项都有中间稿、标题照原文、顺序照矩阵；没有矩阵以外的中间稿（不合并、不拆散）。"""
    hits, expected = [], set()
    for no, item in sorted(items.items()):
        title = str(item.get("title") or "")
        expected.add(item_file(no, title))
        if not texts.get(no, "").strip():
            hits.append(hit("B1", f"missing|{no}", f"第 {no} 项“{title}”没有中间稿：评审内容须全覆盖（Q1）"))
            continue
        hits += [hit("B1", f"{no}|{issue}", f"第 {no} 项：{issue}") for issue in heading_issues(texts[no], no, title)]
    folder = project_dir / "output" / "实施方案"
    for path in (sorted(folder.glob("*.md")) if folder.is_dir() else []):
        # 只有 01 起编号的才是评审内容中间稿；00- 是封面和目录（stage-6-assembly.md 第三节），由成品扫描查身份
        if not DRAFT_NAME.match(path.name):
            continue
        if f"实施方案/{path.name}" not in expected:
            hits.append(hit("B1", f"extra|{path.name}", f"多出中间稿“{path.name}”：不是矩阵里的评审内容，"
                            "一项评审内容一个中间稿，不拆散"))
    return hits


def count_value(token: str) -> int:
    if token.isdigit():
        return int(token)
    if "十" not in token:
        return CHINESE_COUNTS.get(token, 0)
    tens, _, ones = token.partition("十")
    return CHINESE_COUNTS.get(tens, 1) * 10 + CHINESE_COUNTS.get(ones, 0)


def prose(text: str) -> str:
    """数字比对只看正文段落：表格按阶段列人数、台数，和资源卡的总数本来就不同。"""
    return "\n".join(body_lines(text))


def counts_after(name: str, text: str, units: str, gap: str) -> list[tuple[int, str, tuple[int, int]]]:
    pattern = re.compile(re.escape(name) + NAME_END + gap + COUNT + r"\s*(" + units + ")")
    return [(count_value(m.group(1)), m.group(2), m.span()) for m in pattern.finditer(text)]


def aliases(name: str) -> set[str]:
    return {name}.union(*(set(group) for group in SYNONYMS if name in group))


def card_counts(resource_card: dict | None) -> list[tuple[str, int, str, bool]]:
    """(名称, 资源卡数量, 单位, 是否只许不超过)：劳动力是高峰人数，各阶段可以少于它。"""
    card = resource_card or {}
    rows = [(entry.get("role"), entry.get("count"), PEOPLE_UNITS, False) for entry in card.get("managers") or []]
    rows += [(entry.get("name"), entry.get("count"), MACHINE_UNITS, False) for entry in card.get("machinery") or []]
    rows += [(entry.get("trade"), entry.get("peak_count"), PEOPLE_UNITS, True) for entry in card.get("labor") or []]
    return [(str(name), count, units, ceiling) for name, count, units, ceiling in rows
            if isinstance(name, str) and name.strip() and isinstance(count, int)]


def resource_count_hits(text: str, resource_card: dict | None) -> list[dict]:
    hits = []
    for name, expected, units, ceiling in card_counts(resource_card):
        for alias in aliases(name):
            for value, unit, _ in counts_after(alias, text, units, r"[^，,。；;：:\n|]{0,12}?"):
                if (value > expected) if ceiling else (value != expected):
                    rule = "超过资源卡的高峰人数" if ceiling else "与资源卡不一致"
                    hits.append(hit("B4", f"{alias}|{value}|{expected}",
                                    f"“{alias}”写了 {value}{unit}，资源卡为 {expected}：{rule}（R7、R15）"))
    return hits


def material_quantity(entry: dict, facts: dict[str, dict]) -> tuple[str, str] | None:
    quantity = entry.get("quantity") or (facts.get(str(entry.get("quantity_fact"))) or {}).get("quantity") or {}
    tokens = number_tokens(f"{quantity.get('amount')}{quantity.get('unit')}") if quantity.get("unit") else []
    return tokens[0] if tokens else None


def material_hits(text: str, resource_card: dict | None, facts: dict[str, dict]) -> list[dict]:
    """物资名称后面紧跟的数量，与资源卡（或它引用的清单工程量）同单位却不同数时报。"""
    hits = []
    for entry in (resource_card or {}).get("materials") or []:
        name, expected = str(entry.get("name") or ""), material_quantity(entry, facts)
        if not name or expected is None:
            continue
        for m in re.finditer(re.escape(name) + r"([^，,。；;\n|]{0,16})", text):
            same = [number for number, unit in number_tokens(m.group(1)) if unit == expected[1]]
            if same and same[0] != expected[0]:
                hits.append(hit("B4", f"{name}|{same[0]}|{expected[0]}", f"“{name}”写了 {same[0]}{expected[1]}，"
                                f"资源卡为 {expected[0]}{expected[1]}（R15）"))
    return hits


def schedule_values(text: str) -> list[int]:
    return [int(m.group(2)) for m in SCHEDULE.finditer(text) if not any(word in m.group(1) for word in SCHEDULE_SKIP)]


def date_values(text: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {"开工": set(), "竣工": set()}
    for m in DATE_AFTER.finditer(text):
        found[m.group(1)].add(f"{m.group(2)}-{int(m.group(3)):02d}-{int(m.group(4)):02d}")
    for m in DATE_BEFORE.finditer(text):
        found[m.group(4)].add(f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
    return found


def keyed_values(text: str) -> dict[str, set[str]]:
    """跨项比对用的键值：总工期天数、开工和竣工日期。"""
    values = {key: dates for key, dates in date_values(text).items()}
    values["工期"] = {str(days) for days in schedule_values(text)}
    return values


def references(rule_card: dict, fact_card: dict | None) -> dict[str, str]:
    """有出处的参照值：工期取规则卡，开工、竣工日期取事实卡。没有参照的键，才在各项之间互相比。"""
    refs = {}
    days = re.search(r"(\d+)\s*个?(?:日历天|天)", str((rule_card.get("schedule") or {}).get("value") or ""))
    if days:
        refs["工期"] = days.group(1)
    for fact in (fact_card or {}).get("facts") or []:
        for key, dates in date_values(str(fact.get("text") or "") if isinstance(fact, dict) else "").items():
            if dates and key not in refs:
                refs[key] = sorted(dates)[0]
    return refs


def b4_value_hits(text: str, rule_card: dict, fact_card: dict | None, others: dict[int, str]) -> list[dict]:
    refs, own = references(rule_card, fact_card), keyed_values(text)
    hits = []
    for key, values in own.items():
        for value in sorted(values):
            if key in refs and value != refs[key]:
                source = "规则卡" if key == "工期" else "事实卡"
                hits.append(hit("B4", f"{key}|{value}|{refs[key]}", f"{key}写作 {value}，{source}为 {refs[key]}（R15、R22）"))
            elif key not in refs:
                hits += [hit("B4", f"{key}|{value}|{other_no}:{other}", f"{key}本项写 {value}，第 {other_no} 项写 {other}")
                         for other_no, other_text in sorted(others.items())
                         for other in sorted(keyed_values(prose(other_text))[key]) if other != value]
    return hits


def b4_hits(text: str, inputs: dict, others: dict[int, str]) -> list[dict]:
    """数值一致（R15、R22）：工期、开工竣工日期、人数台数、物资数量。可能误报，人工复核后可说明理由放行。"""
    body = prose(text)
    facts = {fact["id"]: fact for fact in (inputs["fact_card"] or {}).get("facts") or []
             if isinstance(fact, dict) and fact.get("id")}
    return b4_value_hits(body, inputs["rule_card"], inputs["fact_card"], others) + \
        resource_count_hits(body, inputs["resource_card"]) + material_hits(body, inputs["resource_card"], facts)


def card_names(resource_card: dict | None) -> set[str]:
    card = resource_card or {}
    names = {entry.get(key) for section, key in (("managers", "role"), ("machinery", "name"), ("labor", "trade"))
             for entry in card.get(section) or [] if isinstance(entry, dict)}
    return {alias for name in names if isinstance(name, str) and name for alias in aliases(name)}


def on_card(word: str, names: set[str]) -> bool:
    return any(word in name or name in word for name in names)


def b10_hits(text: str, resource_card: dict | None) -> list[dict]:
    """资源卡里没有的岗位、工种、机械写了人数台数（R7）。只认名称紧跟数量，套在更长名称里的不重复报。"""
    names, found = card_names(resource_card), []
    for vocab, units in ((VOCAB_PEOPLE, PEOPLE_UNITS), (VOCAB_MACHINES, MACHINE_UNITS)):
        for word in vocab:
            found += [(span, word, value, unit) for value, unit, span in counts_after(word, prose(text), units, "[各共约计]{0,2}")
                      if not on_card(word, names)]
    inner = {index for index, (span, *_) in enumerate(found)
             for other, *_ in found if other != span and other[0] <= span[0] and span[1] <= other[1]}
    return [hit("B10", f"{word}|{value}", f"“{word}”写了 {value}{unit}，资源卡里没有：只写资源卡里有的（R7）。"
                "确实要投入的，先补公司资料、重新确认资源卡和大纲")
            for index, (_, word, value, unit) in enumerate(found) if index not in inner]


def clause_value(text: str) -> tuple[list[tuple[str, str]], tuple[str, str] | None]:
    """★条款里能在正文核对的值：数字＋单位；没有数字时取"关键词：短语"（如质量标准：合格），正文须有一句
    同时写到关键词和短语，叫法照条款原文。"""
    numbers = [token for token in number_tokens(text) if token[1] not in {"年", "月", "日"}]
    if numbers:
        return numbers, None
    m = CLAUSE_VALUE.match(text)
    return [], ((m.group(1).strip(), m.group(2).strip()) if m and not re.search(r"\d", m.group(2)) else None)


def b9_hits(text: str, clauses: list[dict]) -> list[dict]:
    """落在本项的★条款和实质性要求，正文里写出条款原文的值（R5）；登记了关键词的，每个关键词都要写到。
    招标指定的内容（重点难点、危大清单）只按关键词核对：原文里的序号、运距这类数字不是要照抄的值。不能放行。"""
    visible = "\n".join(visible_lines(text))
    draft_numbers, hits = set(number_tokens(visible)), []
    for clause in clauses:
        label = f"{clause.get('id')}“{str(clause.get('text') or '')[:30]}”"
        hits += [hit("B9", f"{clause.get('id')}|{word}", f"{label}要求写到的“{word}”在本项正文里没有：照招标文件的叫法写（R5、R15）")
                 for word in clause_keywords(clause) if word not in visible]
        if clause.get("type") == TENDER_SPECIFIED:
            continue
        numbers, phrase = clause_value(str(clause.get("text") or ""))
        hits += [hit("B9", f"{clause.get('id')}|{number}{unit}", f"{label}的“{number}{unit}”在本项正文里没有：照条款原文写（R5）")
                 for number, unit in numbers if (number, unit) not in draft_numbers]
        if phrase and not any(phrase[1] in sentence and phrase[0] in sentence
                              for sentence in re.split(r"[。；;\n]", visible)):
            hits.append(hit("B9", f"{clause.get('id')}|{phrase[1]}", f"{label}：正文里没有一句同时写到“{phrase[0]}”"
                            f"和“{phrase[1]}”，照条款原文的叫法写（R5、R15）"))
    return hits


def b9_manual(clauses: list[dict]) -> list[str]:
    return [f"{clause.get('id')}“{str(clause.get('text') or '')[:30]}”没有可比对的数值或标准：落点由阶段 7 人工核对（B12）"
            for clause in clauses
            if not clause_keywords(clause) and clause_value(str(clause.get("text") or "")) == ([], None)]


def b9_landing_hits(rule_card: dict, items: dict[int, dict]) -> list[dict]:
    """B9（整份）：去处为施组的每一条强制条款都落在某一项；去处为提交前清单的在阶段 8 核对（决策 4c-4A）。"""
    landed = {ref for item in items.values() for ref in item.get("mandatory") or []}
    return [hit("B9", f"unlanded|{clause.get('id')}", f"{clause.get('id')}“{str(clause.get('text') or '')[:30]}”没有落在任何一项（R5）")
            for clause in scoped_clauses(rule_card, TECH_SCOPE) if clause.get("id") not in landed]


def b11_hits(text: str, no: int, matrix: dict) -> list[dict]:
    """大纲把实施、进度或组织落在本项的，正文里要写到（R13）。标题也算。"""
    visible = "\n".join(visible_lines(text))
    coverage = matrix.get("coverage") or {}
    return [hit("B11", aspect, f"大纲把“{aspect}”落在本项，正文里没写到（{'、'.join(ASPECT_WORDS[aspect][:3])}等）（R13）")
            for aspect in COVERAGE_ASPECTS if no in ((coverage.get(aspect) or {}).get("items") or [])
            and not any(word in visible for word in ASPECT_WORDS[aspect])]


def w1_hits(text: str, item: dict, cited: list[dict]) -> list[dict]:
    """矩阵引用的事实，正文里真用上了几条（Q3、Q4）。少于 2 条（写了原因的按引用数）报警。"""
    flat = "\n".join(visible_lines(text))
    used = [fact for fact in cited if fact_used(fact, flat)]
    needed = min(2, len(cited)) if str(item.get("facts_note") or "").strip() else 2
    if len(used) >= needed:
        return []
    unused = "、".join(str(fact.get("id")) for fact in cited if fact not in used) or "无"
    return [hit("W1", "facts-used", f"正文只用上了 {len(used)} 条项目事实（矩阵引用的 {unused} 没写进正文）（Q3、Q4）")]
