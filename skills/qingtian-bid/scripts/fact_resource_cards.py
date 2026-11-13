"""Fact card and resource card of qingtian-bid (stage 3): validation, Markdown views and confirmation.

INPUT: <project>/analysis/fact-card.json (scaffold_facts.py 出候选后对照原文核实);
       analysis/resource-card.json (index_materials.py 出骨架后按公司资料填写);
       analysis/material-index.json; project-state.json; templates/fact-card.json, resource-card.json.
OUTPUT: validation issues; analysis/project-facts.md and analysis/company-resources.md views for the
        user; confirmation records cards.fact_card (each row locks the rule rows it cites) and
        cards.resource_card (locks the company materials; each row locks the rule and fact rows it cites;
        outline_only when gaps remain, R8).
POS: stage-3 card layer on top of project_cards.py. JSON is the source of truth (决策 1A). The
     resource card keeps roles, headcounts and certificate categories only, never names or certificate
     numbers (决策 3b-1A), and material quantities come from bill-of-quantities facts (决策 3b-2A).
     Managers, machinery and labour must point to an indexed company file, which keeps the "资料空壳
     禁写" red line (R8, P0-5) without counting files. Each fact and resource row may carry `cites`, the
     rule rows (and, for resources, fact rows) it depends on (决策 D9): missing means all, [] means none.
"""

from __future__ import annotations

import re
from pathlib import Path

from format_state import save_state
from project_cards import (
    FACT_CARD_FILE,
    MATERIAL_INDEX_FILE,
    RESOURCE_CARD_FILE,
    RULE_CARD_FILE,
    SKILL_DIR,
    card_status,
    cell,
    is_empty,
    load_json,
    load_project,
    record_confirmation,
    status_lines,
)
from rule_card_rows import CITES_KEY, cites_issues, rule_rows


FACT_SCHEMA = "qingtian-fact-card/2"
RESOURCE_SCHEMA = "qingtian-resource-card/2"
FACT_CATEGORIES = ("规模与结构", "招标范围", "场地与周边", "工期与节点", "工程量", "技术要求", "其他")
FACT_BASES = ("招标文件", "工程量清单", "图纸", "用户提供")
RESOURCE_BASES = ("公司资料", "用户确认")
FACT_KEYS = {"id", "category", "text", "quantity", "basis", "source", "checked", CITES_KEY}
PROVENANCE_KEYS = {"id", "basis", "file", "locator", "source", "checked"}
# 资源卡每节：(中文名, 编号前缀, 允许的内容键, 必填文字键, 人数或台数键)。只收这些键：姓名、证书
# 编号、电话之类的键名千变万化，白名单比黑名单可靠（决策 3b-1A）
SECTIONS = {
    "managers": ("管理岗位与持证", "P", {"role", "count", "cert_category"}, ("role", "cert_category"), "count"),
    "machinery": ("机械设备", "E", {"name", "model", "count", "ownership"}, ("name",), "count"),
    "labor": ("劳动力", "L", {"trade", "peak_count", "phases"}, ("trade",), "peak_count"),
    "materials": ("主要物资", "S", {"name", "quantity_fact", "quantity", "supply", "batches"},
                  ("name", "supply", "batches"), None),
}
OWNERSHIP = ("自有", "租赁")
# 八位以上连续数字多半是证书编号、电话或身份证号；出处类字段（路径里有日期）不查
LONG_DIGITS = re.compile(r"\d{8,}")


def card_template(name: str) -> dict:
    return load_json(SKILL_DIR / "templates" / name, "卡片模板")


def is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def check_quantity(quantity: object, label: str) -> list[str]:
    if not isinstance(quantity, dict) or not str(quantity.get("item") or "").strip() \
            or not str(quantity.get("unit") or "").strip():
        return [f"{label}：工程量须写成 {{item, amount, unit}}"]
    amount = quantity.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
        return [f"{label}：工程量 amount 应为正数"]
    return []


def check_fact(fact: object, index: int, seen: set[str], rule_keys: set[str] | None) -> list[str]:
    if not isinstance(fact, dict):
        return [f"事实第 {index} 条应为对象"]
    fact_id = str(fact.get("id") or "")
    label = f"事实 {fact_id or index}"
    issues = [] if re.fullmatch(r"F\d{2,}", fact_id) and fact_id not in seen else \
        [f"事实第 {index} 条的编号须为 F01 这样且不重复（当前: {fact_id or '空'}）"]
    seen.add(fact_id)
    extra = set(fact) - FACT_KEYS - {"candidates"}
    if extra:
        issues.append(f"{label}：未定义的键 {'、'.join(sorted(extra))}")
    if fact.get("category") not in FACT_CATEGORIES:
        issues.append(f"{label}：类别只能是 {'、'.join(FACT_CATEGORIES)}")
    if fact.get("basis") not in FACT_BASES:
        issues.append(f"{label}：依据只能是 {'、'.join(FACT_BASES)}")
    if not str(fact.get("text") or "").strip() or not str(fact.get("source") or "").strip():
        issues.append(f"{label}：须有事实原文 text 和出处 source（图纸写图号）")
    if fact.get("category") == "工程量" or "quantity" in fact:
        issues += check_quantity(fact.get("quantity"), label)
    if fact.get("checked") is not True:
        issues.append(f"{label}：待核对（对照原文核实后把 checked 改为 true）")
    return issues + cites_issues(fact, label, rule_keys)


def validate_fact_card(card: dict, rule_card: dict | None = None) -> list[str]:
    """返回全部问题；空列表才能请用户确认。工期、质量标准以规则卡为准，不在事实卡里重复。
    给了规则卡才能核对 cites 引用的行存不存在。"""
    if card.get("schema") != FACT_SCHEMA:
        return [f"事实卡 schema 应为 {FACT_SCHEMA}"]
    facts = card.get("facts")
    if not isinstance(facts, list) or not facts:
        return ["事实卡没有事实：至少要有工程规模与结构"]
    seen: set[str] = set()
    rule_keys = None if rule_card is None else set(rule_rows(rule_card))
    issues = [issue for index, fact in enumerate(facts, 1) for issue in check_fact(fact, index, seen, rule_keys)]
    if not any(isinstance(fact, dict) and fact.get("category") == "规模与结构" for fact in facts):
        issues.append("事实卡缺少“规模与结构”：工程概况至少要有规模和结构形式")
    return issues


def quantity_facts(fact_card: dict | None) -> dict:
    """可供物资引用的工程量事实：类别为工程量且数量写全。"""
    facts = (fact_card or {}).get("facts") or []
    return {fact["id"]: fact for fact in facts if isinstance(fact, dict) and fact.get("category") == "工程量"
            and fact.get("id") and not check_quantity(fact.get("quantity"), "")}


def file_key(value: object) -> str:
    return str(value or "").strip().replace("\\", "/")


def indexed_files(material_index: dict | None) -> set[str]:
    """资源条目的 file 可以写编目里的相对路径或完整路径，斜杠方向不论。"""
    records = (material_index or {}).get("materials") or []
    return {file_key(record.get(key)) for record in records for key in ("relative_path", "path") if record.get(key)}


def check_provenance(section: str, entry: dict, label: str, files: set[str]) -> list[str]:
    """岗位、机械、劳动力必须指回编目里的公司资料文件（R7、R8）；只有数量取自清单的物资，
    供应方式和批次可以由用户直接确认（决策 3b-2A）。"""
    basis = entry.get("basis")
    if basis not in RESOURCE_BASES:
        return [f"{label}：依据只能是 {'、'.join(RESOURCE_BASES)}"]
    issues = [] if entry.get("checked") is True else [f"{label}：待核对（对照公司资料核实后把 checked 改为 true）"]
    if basis == "公司资料":
        if file_key(entry.get("file")) not in files:
            issues.append(f"{label}：file 须是公司资源编目里的文件（见 analysis/material-index.md）")
        if not str(entry.get("locator") or "").strip():
            issues.append(f"{label}：须写在该文件里的位置 locator（页码、工作表和行号）")
        return issues
    if section != "materials" or not entry.get("quantity_fact"):
        issues.append(f"{label}：只有数量取自工程量清单的物资可以写“用户确认”，其余须指回公司资料文件")
    if not str(entry.get("source") or "").strip():
        issues.append(f"{label}：“用户确认”须在 source 写明谁在何时确认")
    return issues


def check_identity(section: str, entry: dict, label: str) -> list[str]:
    """决策 3b-1A：资源卡只记岗位、人数和持证类别，不收姓名、证书编号、电话等。
    cites 只收认得的行键（cites_issues），写不进身份信息。"""
    allowed = SECTIONS[section][2] | PROVENANCE_KEYS | {CITES_KEY}
    issues =[f"{label}：资源卡不收键 {key}（不记姓名、证书编号等身份信息，决策 3b-1A）"
              for key in sorted(set(entry) - allowed)]
    for key in sorted(SECTIONS[section][2] & set(entry)):
        if isinstance(entry[key], str) and LONG_DIGITS.search(entry[key]):
            issues.append(f"{label}：{key} 里有长串数字，疑似证书编号或电话，资源卡不记（决策 3b-1A）")
    return issues


def check_material_quantity(entry: dict, label: str, facts: dict) -> list[str]:
    """数量二选一：引用工程量事实（清单数量），或周转材料等清单外物资自带数量并指回公司资料。"""
    reference, quantity = entry.get("quantity_fact"), entry.get("quantity")
    if bool(reference) == (quantity is not None):
        return [f"{label}：quantity_fact（引用工程量事实）和 quantity（清单外物资自带数量）须二选一"]
    if reference:
        return [] if reference in facts else [f"{label}：quantity_fact {reference} 不是事实卡里写全数量的工程量事实"]
    issues = check_quantity({"item": entry.get("name"), **quantity} if isinstance(quantity, dict) else None, label)
    if entry.get("basis") != "公司资料":
        issues.append(f"{label}：清单外物资的数量须指回公司资料文件")
    return issues


def check_resource_entry(section: str, entry: object, index: int, context: dict) -> list[str]:
    title, prefix, _, required, count_key = SECTIONS[section]
    if not isinstance(entry, dict):
        return [f"{title}第 {index} 条应为对象"]
    entry_id = str(entry.get("id") or "")
    label = f"{title} {entry_id or index}"
    issues = [] if re.fullmatch(rf"{prefix}\d{{2,}}", entry_id) and entry_id not in context["seen"] else \
        [f"{title}第 {index} 条的编号须为 {prefix}01 这样且不重复（当前: {entry_id or '空'}）"]
    context["seen"].add(entry_id)
    issues += [f"{label}：缺少 {key}" for key in required if not str(entry.get(key) or "").strip()]
    if count_key and not is_count(entry.get(count_key)):
        issues.append(f"{label}：{count_key} 应为正整数")
    if section == "machinery" and entry.get("ownership") not in (None, *OWNERSHIP):
        issues.append(f"{label}：ownership 只能是 {'、'.join(OWNERSHIP)}")
    if section == "materials":
        issues += check_material_quantity(entry, label, context["facts"])
    issues += cites_issues(entry, label, context["cite_keys"], "规则卡的行或事实卡的事实")
    return issues + check_identity(section, entry, label) + check_provenance(section, entry, label, context["files"])


def check_gaps(card: dict) -> list[str]:
    gaps = card.get("gaps")
    if not isinstance(gaps, list):
        return ["资源卡 gaps 应为列表"]
    issues = [f"缺口第 {index} 条须含 section（{'/'.join(SECTIONS)}）和缺什么 text"
              for index, gap in enumerate(gaps, 1)
              if not isinstance(gap, dict) or gap.get("section") not in SECTIONS or not str(gap.get("text") or "").strip()]
    covered = {gap.get("section") for gap in gaps if isinstance(gap, dict)}
    for section, (title, *_rest) in SECTIONS.items():
        if not card.get(section) and section not in covered:
            issues.append(f"{title}一条都没有：从公司资料补齐，或在 gaps 写明缺什么（补齐前只许出大纲，R8）")
    return issues


def resource_cite_keys(rule_card: dict | None, fact_card: dict | None) -> set[str] | None:
    """资源行的 cites 可以写规则卡的行键，也可以写事实编号（F07）。两者不重名：规则卡没有 F 开头的编号。"""
    if rule_card is None:
        return None
    facts = (fact_card or {}).get("facts") or []
    return set(rule_rows(rule_card)) | {fact["id"] for fact in facts if isinstance(fact, dict)
                                        and isinstance(fact.get("id"), str)}


def validate_resource_card(card: dict, fact_card: dict | None, material_index: dict | None,
                           rule_card: dict | None = None) -> list[str]:
    """返回全部问题；空列表才能请用户确认。物资引用的工程量按当前事实卡核对；给了规则卡才能核对 cites。"""
    if card.get("schema") != RESOURCE_SCHEMA:
        return [f"资源卡 schema 应为 {RESOURCE_SCHEMA}"]
    extra = set(card) - {"schema", "gaps", *SECTIONS}
    issues = [f"资源卡不收顶层键 {key}" for key in sorted(extra)]
    context = {"seen": set(), "facts": quantity_facts(fact_card), "files": indexed_files(material_index),
               "cite_keys": resource_cite_keys(rule_card, fact_card)}
    for section in SECTIONS:
        entries = card.get(section)
        if not isinstance(entries, list):
            issues.append(f"{SECTIONS[section][0]}应为列表")
            continue
        issues += [issue for index, entry in enumerate(entries, 1)
                   for issue in check_resource_entry(section, entry, index, context)]
    return issues + check_gaps(card)


def quantity_text(quantity: object) -> str:
    if not isinstance(quantity, dict):
        return "—"
    return f"{cell(quantity.get('item'))} {cell(quantity.get('amount'))} {cell(quantity.get('unit'))}"


def mark(entry: dict) -> str:
    return "✓" if entry.get("checked") is True else "待核对"


def render_facts(card: dict, project_name: str, issues: list[str]) -> str:
    lines = [f"# 项目事实卡（{project_name}）", "", *status_lines(issues, "fact-card"), "",
             "> 由 `analysis/fact-card.json` 生成，改事实请改 JSON。工期、质量标准、安全目标以规则卡为准。", "",
             "| 编号 | 类别 | 事实 | 工程量 | 依据 | 出处 | 核对 |", "|---|---|---|---|---|---|---|"]
    facts = [fact for fact in card.get("facts") or [] if isinstance(fact, dict)]
    order = {category: rank for rank, category in enumerate(FACT_CATEGORIES)}
    for fact in sorted(facts, key=lambda item: order.get(item.get("category"), len(order))):
        lines.append(f"| {cell(fact.get('id'))} | {cell(fact.get('category'))} | {cell(fact.get('text'))} | "
                     f"{quantity_text(fact.get('quantity'))} | {cell(fact.get('basis'))} | "
                     f"{cell(fact.get('source'))} | {mark(fact)} |")
    return "\n".join(lines) + "\n"


def provenance_text(entry: dict) -> str:
    if entry.get("basis") == "公司资料":
        return f"{cell(entry.get('file'))} {cell(entry.get('locator'))}"
    return f"用户确认：{cell(entry.get('source'))}"


def material_amount(entry: dict, facts: dict) -> str:
    fact = facts.get(entry.get("quantity_fact"))
    if fact:
        return f"{quantity_text(fact['quantity'])}（{fact['id']}，{cell(fact.get('basis'))}）"
    quantity = entry.get("quantity")
    return quantity_text({"item": entry.get("name"), **quantity}) if isinstance(quantity, dict) else "—"


SECTION_COLUMNS = {
    "managers": (("岗位", "role"), ("人数", "count"), ("持证类别", "cert_category")),
    "machinery": (("名称", "name"), ("型号", "model"), ("台数", "count"), ("自有/租赁", "ownership")),
    "labor": (("工种", "trade"), ("高峰人数", "peak_count"), ("阶段", "phases")),
    "materials": (("物资", "name"), ("数量", None), ("供应方式", "supply"), ("进场批次", "batches")),
}


def section_rows(section: str, entries: list, facts: dict) -> list[str]:
    columns = SECTION_COLUMNS[section]
    lines = [f"| 编号 | {' | '.join(title for title, _ in columns)} | 出处 | 核对 |", "|---" * (len(columns) + 3) + "|"]
    for entry in [item for item in entries if isinstance(item, dict)]:
        # 物资的数量列不在条目里：引用事实时取清单数量
        cells = [cell(entry.get(key)) if key else material_amount(entry, facts) for _, key in columns]
        lines.append(f"| {cell(entry.get('id'))} | {' | '.join(cells)} | {provenance_text(entry)} | {mark(entry)} |")
    return lines


def render_resources(card: dict, fact_card: dict | None, project_name: str, issues: list[str]) -> str:
    facts = quantity_facts(fact_card)
    lines = [f"# 公司资源卡（{project_name}）", "", *status_lines(issues, "resource-card"), "",
             "> 由 `analysis/resource-card.json` 生成。只记岗位、人数和持证类别，不记姓名和证书编号（决策 3b-1A）；"
             "物资数量取自工程量清单事实（决策 3b-2A）。阶段 5 写作只引用本卡。", ""]
    gaps = [gap for gap in card.get("gaps") or [] if isinstance(gap, dict)]
    if gaps:
        lines += ["> **有缺口：确认后也只许出大纲和缺口清单，补齐后才能逐项撰写（R8）。**", ""]
    for section, (title, *_rest) in SECTIONS.items():
        entries = card.get(section) if isinstance(card.get(section), list) else []
        lines += [f"## {title}", "", *section_rows(section, entries, facts), ""]
    lines += ["## 缺口清单", ""]
    lines += [f"- {SECTIONS.get(gap.get('section'), ('?',))[0]}：{cell(gap.get('text'))}" for gap in gaps] or ["- 无"]
    return "\n".join(lines) + "\n"


def load_optional(project_dir: Path, relative: str, label: str) -> dict | None:
    path = project_dir / relative
    return load_json(path, label) if path.is_file() else None


def check_fact_card(project_dir: Path) -> dict:
    """校验并重出 MD 视图，不改状态。"""
    project_dir, state = load_project(project_dir)
    card = load_json(project_dir / FACT_CARD_FILE, "事实卡")
    issues = validate_fact_card(card, load_optional(project_dir, RULE_CARD_FILE, "规则卡"))
    view = project_dir / "analysis" / "project-facts.md"
    view.write_text(render_facts(card, state.get("project_name", ""), issues), encoding="utf-8")
    return {"issues": issues, "views": [str(view)]}


def check_resource_card(project_dir: Path) -> dict:
    """校验并重出 MD 视图，不改状态；物资引用按当前事实卡核对。"""
    project_dir, state = load_project(project_dir)
    card = load_json(project_dir / RESOURCE_CARD_FILE, "资源卡")
    fact_card = load_optional(project_dir, FACT_CARD_FILE, "事实卡")
    material_index = load_optional(project_dir, MATERIAL_INDEX_FILE, "公司资源编目")
    issues = validate_resource_card(card, fact_card, material_index, load_optional(project_dir, RULE_CARD_FILE, "规则卡"))
    if material_index is None:
        issues.insert(0, "还没有公司资源编目：先运行 index_materials.py --project")
    view = project_dir / "analysis" / "company-resources.md"
    view.write_text(render_resources(card, fact_card, state.get("project_name", ""), issues), encoding="utf-8")
    return {"issues": issues, "views": [str(view)], "outline_only": bool(card.get("gaps"))}


def require_confirmable(state: dict, project_dir: Path, needed: tuple[tuple[str, str], ...]) -> None:
    if state["stages"].get("2") != "done":
        raise ValueError("阶段 2 解标定轨未完成，阶段 3 的卡片不能确认")
    for name, label in needed:
        status = card_status(project_dir, state, name)
        if status["status"] != "confirmed":
            raise ValueError(f"{label}{status['reason']}，先处理{label}再确认本卡")


def confirm_card(project_dir: Path, state: dict, name: str, file: str, inputs: tuple[str, ...],
                 extra: dict | None = None) -> None:
    record_confirmation(project_dir, state, name, file, inputs, extra)
    if state["stages"].get("3") == "pending":
        state["stages"]["3"] = "in-progress"
    save_state(project_dir, state)


def confirm_fact_card(project_dir: Path) -> dict:
    """用户明确同意事实卡后才调用；每行连带锁定它引用的规则行（决策 D9）。提取文本不再锁：
    新文件对事实的影响由变更单判断，文件一变规则卡就失效，阶段闸照样挡住（决策 D9-2A）。"""
    project_dir, state = load_project(project_dir)
    require_confirmable(state, project_dir, (("rule_card", "规则卡"),))
    result = check_fact_card(project_dir)
    if result["issues"]:
        raise ValueError(f"事实卡还有 {len(result['issues'])} 个问题，不能确认：{result['issues'][0]}")
    confirm_card(project_dir, state, "fact_card", FACT_CARD_FILE, ("rule_card",))
    return {"project": str(project_dir), "fact_card": "confirmed", "views": result["views"]}


def confirm_resource_card(project_dir: Path) -> dict:
    """用户明确同意资源卡后才调用；规则卡、事实卡须先确认（事实行不引用变了的规则行时，事实卡不会连带失效，
    所以规则卡要单独查）。每行连带锁定它引用的行，物资引用的工程量事实总算在内。有缺口时记 outline_only。"""
    project_dir, state = load_project(project_dir)
    require_confirmable(state, project_dir, (("rule_card", "规则卡"), ("fact_card", "事实卡")))
    result = check_resource_card(project_dir)
    if result["issues"]:
        raise ValueError(f"资源卡还有 {len(result['issues'])} 个问题，不能确认：{result['issues'][0]}")
    confirm_card(project_dir, state, "resource_card", RESOURCE_CARD_FILE, ("materials", "rule_card", "fact_card"),
                 {"outline_only": result["outline_only"]})
    return {"project": str(project_dir), "resource_card": "confirmed", "outline_only": result["outline_only"],
            "views": result["views"]}


def stage3_issues(project_dir: Path, state: dict) -> list[str]:
    """阶段 3 完成条件：规则卡、事实卡、资源卡都确认且未失效；资源卡对当前事实卡的引用仍成立。"""
    issues = []
    for name, label, arg in (("rule_card", "规则卡", "rule-card"), ("fact_card", "事实卡", "fact-card"),
                             ("resource_card", "资源卡", "resource-card")):
        status = card_status(project_dir, state, name)
        if status["status"] != "confirmed":
            issues.append(f"{label}{status['reason']}：校验用 --check {arg}，用户同意后 --confirm {arg}")
    if issues:
        return issues
    card = load_json(project_dir / RESOURCE_CARD_FILE, "资源卡")
    current = validate_resource_card(card, load_optional(project_dir, FACT_CARD_FILE, "事实卡"),
                                     load_optional(project_dir, MATERIAL_INDEX_FILE, "公司资源编目"),
                                     load_optional(project_dir, RULE_CARD_FILE, "规则卡"))
    # 输入都已锁定；这里按当前规则再核一次，Skill 升级收紧校验后，旧规则下确认的卡也要过新规则
    return [f"资源卡按当前事实卡和编目复核不通过：{issue}" for issue in current]


def resource_summary(project_dir: Path, state: dict) -> str:
    status = card_status(project_dir, state, "resource_card")
    record = (state.get("cards") or {}).get("resource_card") or {}
    if status["status"] == "confirmed" and record.get("outline_only"):
        return f"{status['reason']}，有缺口：只许出大纲和缺口清单（R8）"
    return status["reason"]
