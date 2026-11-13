"""Response matrix of qingtian-bid (stage 4): validation, the outline view, confirmation and the stage-4
gate, plus the item naming shared with stage 5 and the step-4 gate scripts.

INPUT: <project>/analysis/response-matrix.json (scaffold_matrix.py 出骨架后按规则卡、事实卡、资源卡填写);
       analysis/rule-card.json, fact-card.json, resource-card.json; project-state.json (the locked
       document_format feeds the page estimate); templates/response-matrix.json.
OUTPUT: validation issues; the analysis/response-matrix.md view, which is the outline the user confirms;
        the confirmation record cards.response_matrix (each row locks the rule, fact and resource rows it depends on);
        item_heading() / item_file() naming; page_capacity(); stage4_issues(); writing_inputs() and
        matrix_items(), shared by writing_gate and the step-4 gate scripts.
POS: stage-4 card layer on top of project_cards.py and fact_resource_cards.py. JSON is the source of truth
     (决策 1A). One row per review item, in rule-card wording and order (R3、R4、Q1), so the step-4 gates
     read B1 (titles), B9 (★ landings), B10 (resources), B11 (实施/进度/组织), W1 (facts) and W5 (page
     budget) from here instead of guessing. Control points are free text, prefilled from the category cards
     (决策 3c-1A, 5-4A); the view lists each item's card points and the cards' 参考 hints; W9 compares only
     the ones still in the item's control points (第 6b 步改 5-4A). `cites` names the rule rows a row depends on
     (决策 D9): missing means all, [] means none; facts and resources go through their own lists.
"""

from __future__ import annotations

from pathlib import Path

from category_cards import FOCUS_WORDS, card_hints, card_points, project_cards
from fact_resource_cards import SECTIONS, load_optional, stage3_issues
from format_state import save_state
from project_cards import (
    FACT_CARD_FILE,
    MATRIX_FILE,
    RESOURCE_CARD_FILE,
    RULE_CARD_FILE,
    SUBMISSION_SCOPE,
    TECH_SCOPE,
    UNSPECIFIED,
    card_status,
    cell,
    clause_text,
    load_json,
    load_project,
    record_confirmation,
    scoped_clauses,
    status_lines,
)
from rule_card_rows import CITES_KEY, cites_issues, rule_rows


MATRIX_SCHEMA = "qingtian-response-matrix/2"
MATRIX_VIEW = "analysis/response-matrix.md"
TOP_KEYS = {"schema", "front_pages", "reserve_pages", "items", "coverage"}
ITEM_KEYS = {"no", "title", "source", "points", "facts", "facts_note", "resources", "mandatory",
             "control_points", "pages", CITES_KEY}
# R13：技术文件必含实施、进度、组织；评审内容没有单列时，写明分布在哪几项及依据（B11 按这里核对）
COVERAGE_ASPECTS = ("实施", "进度", "组织")
MIN_FACTS = 2  # 优秀档要素 1：点名本项目至少 2 条具体事实（W1）
DIGITS = "零一二三四五六七八九"
# Windows 文件名不许的字符换成全角，文件名照样读得出评审内容原文
FILENAME_SAFE = str.maketrans('\\/:*?"<>|', "＼／：＊？＂＜＞｜")
CM_TO_PT = 72 / 2.54
# 设计稿 §5.1：F2 一页最多约 34 字 × 32 行 ≈ 1,080 字，扣除首行缩进、标题、段尾空白和图表后约 800 字
PAGE_FILL = 0.74
SINGLE_LINE = 1.3  # 单倍行距约为字号的 1.3 倍，倍数行距按它折算【推断】


def chinese_ordinal(no: int) -> str:
    """一级标题序号一～九十九；评审内容不会到三位数，超出就报错，不乱编序号。"""
    if not isinstance(no, int) or isinstance(no, bool) or not 1 <= no <= 99:
        raise ValueError(f"评审内容序号只支持 1～99（当前: {no}）")
    tens, ones = divmod(no, 10)
    head = "" if tens == 0 else ("十" if tens == 1 else f"{DIGITS[tens]}十")
    return head + (DIGITS[ones] if ones else "")


def item_heading(no: int, title: str) -> str:
    """中间稿的一级标题：编号写进文字（一、），不叠加 Word 自动编号（R19）。"""
    return f"{chinese_ordinal(no)}、{title}"


def item_file(no: int, title: str) -> str:
    """相对 output/ 的中间稿路径，与 stage-6-assembly.md 组装清单的命名一致。"""
    return f"实施方案/{no:02d}-{title.strip().translate(FILENAME_SAFE)}.md"


def item_path(project_dir: Path, no: int, title: str) -> Path:
    return project_dir / "output" / item_file(no, title)


def expected_items(rule_card: dict) -> list[dict] | None:
    """规则卡的评审内容；"招标文件未规定"（只有 T-合格 允许）时返回 None，章节由用户给出。"""
    entry = rule_card.get("review_items") or {}
    if entry.get("basis") == UNSPECIFIED:
        return None
    return [item for item in entry.get("value") or [] if isinstance(item, dict)]


def card_ids(card: dict | None, sections: tuple[str, ...]) -> dict[str, dict]:
    return {entry["id"]: entry for section in sections for entry in (card or {}).get(section) or []
            if isinstance(entry, dict) and entry.get("id")}


def matrix_context(rule_card: dict, fact_card: dict | None, resource_card: dict | None) -> dict:
    """矩阵能引用的编号：事实 F、资源 P/E/L/S、去处为施组的强制条款 M。去处为提交前清单的 M 单列，
    只用来指出引错了（决策 4c-4A）。"""
    tech = {"mandatory": scoped_clauses(rule_card, TECH_SCOPE)}
    submission = {"mandatory": scoped_clauses(rule_card, SUBMISSION_SCOPE)}
    return {"facts": card_ids(fact_card, ("facts",)), "resources": card_ids(resource_card, tuple(SECTIONS)),
            "mandatory": card_ids(tech, ("mandatory",)), "submission": card_ids(submission, ("mandatory",))}


def is_text_list(value: object, allow_empty: bool) -> bool:
    return isinstance(value, list) and (allow_empty or bool(value)) and \
        all(isinstance(item, str) and item.strip() for item in value)


def is_half_pages(value: object, minimum: float) -> bool:
    """页数以 0.5 页为单位：预算只是给写作分篇幅，不需要更细。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= minimum \
        and float(value * 2).is_integer()


def is_item_no(value: object, count: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= count


def check_refs(item: dict, key: str, known: dict, label: str, what: str) -> list[str]:
    refs = item.get(key)
    if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
        return [f"{label}：{key} 应为{what}编号列表"]
    return [f"{label}：{key} 里的 {ref} 不在{what}里" for ref in refs if ref not in known]


def check_landing_refs(item: dict, label: str, context: dict) -> list[str]:
    """强制条款落点只引去处为施组的；其余在阶段 8 核对（含暂时并入的商务文件、报价文件），不在施组里落点。"""
    issues = check_refs(item, "mandatory", {**context["mandatory"], **context["submission"]}, label, "强制条款清单")
    refs = item.get("mandatory") if isinstance(item.get("mandatory"), list) else []
    return issues + [f"{label}：mandatory 里的 {ref} 去处是提交前清单（阶段 8 逐条核对），不在施组里落点"
                     for ref in refs if ref in context["submission"]]


def check_item(item: dict, label: str, context: dict) -> list[str]:
    issues = [f"{label}：未定义的键 {key}" for key in sorted(set(item) - ITEM_KEYS)]
    if not is_text_list(item.get("points"), allow_empty=False):
        issues.append(f"{label}：points 写这一项必须写到的要点，至少一条（Q2）")
    if not is_text_list(item.get("control_points", []), allow_empty=True):
        issues.append(f"{label}：control_points 应为文字列表（骨架按类别知识卡预填，按本项目删改，可以留空）")
    issues += check_refs(item, "facts", context["facts"], label, "事实卡")
    issues += check_refs(item, "resources", context["resources"], label, "资源卡")
    issues += check_landing_refs(item, label, context)
    facts = item.get("facts") if isinstance(item.get("facts"), list) else []
    if len(set(facts)) < MIN_FACTS and not str(item.get("facts_note") or "").strip():
        issues.append(f"{label}：引用的事实少于 {MIN_FACTS} 条，补事实或在 facts_note 写明原因（W1）")
    if not is_half_pages(item.get("pages"), 0.5):
        issues.append(f"{label}：pages 应为正数页数，以 0.5 页为单位")
    return issues


def check_item_titles(items: list, expected: list[dict] | None) -> list[str]:
    """B1 的前置：与规则卡评审内容一一对应，序号、原文、顺序都一致；T-合格未规定时须写章节出处。"""
    issues = []
    if expected is not None and len(items) != len(expected):
        issues.append(f"矩阵有 {len(items)} 项，规则卡评审内容有 {len(expected)} 项：一项对应一项，不合并、不拆散、"
                      "不缺项（Q1）")
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or item.get("no") != index or not str(item.get("title") or "").strip():
            issues.append(f"矩阵第 {index} 项须含 no={index} 和评审内容原文 title")
        elif expected is None and not str(item.get("source") or "").strip():
            issues.append(f"矩阵第 {index} 项：评审内容招标文件未规定，章节由用户给出，须在 source 写明出处")
        elif expected is not None and index <= len(expected) and item["title"] != expected[index - 1].get("title"):
            issues.append(f"矩阵第 {index} 项标题与规则卡评审内容原文不一致，应为“{expected[index - 1].get('title')}”"
                          "（R3、R4）")
    return issues


def check_landing(items: list[dict], context: dict) -> list[str]:
    """R5：去处为施组的每一条强制条款都要在某一项里有落点（B9 按这里核对）。"""
    landed = {ref for item in items if isinstance(item.get("mandatory"), list) for ref in item["mandatory"]}
    return [f"强制条款 {clause_id} 没有落点：在落实它的那一项的 mandatory 写上（R5）"
            for clause_id in context["mandatory"] if clause_id not in landed]


def page_total(matrix: dict, items: list[dict]) -> float:
    pages = [item.get("pages") for item in items if is_half_pages(item.get("pages"), 0.5)]
    fixed = [matrix.get(key) for key in ("front_pages", "reserve_pages") if is_half_pages(matrix.get(key), 0)]
    return sum(pages) + sum(fixed)


def check_pages(matrix: dict, items: list[dict], rule_card: dict) -> list[str]:
    """封面目录 + 各项 + 余量不超过篇幅上限；"建议"也照做（D7），偏离须用户同意后改规则卡。"""
    issues = [f"{key} 应为不小于 0 的页数，以 0.5 页为单位" for key in ("front_pages", "reserve_pages")
              if not is_half_pages(matrix.get(key), 0)]
    limit = rule_card.get("page_limit") or {}
    value = limit.get("value")
    total = page_total(matrix, items)
    if isinstance(value, int) and not isinstance(value, bool) and total > value:
        issues.append(f"篇幅预算 {total:g} 页超过上限 {value} 页（{limit.get('kind')}）：压缩各项页数或余量；"
                      "压缩会删掉评审内容要求的要点时硬停，请用户取舍")
    return issues


def check_coverage(matrix: dict, count: int) -> list[str]:
    coverage = matrix.get("coverage")
    if not isinstance(coverage, dict) or set(coverage) != set(COVERAGE_ASPECTS):
        return [f"coverage 须且只须含 {'、'.join(COVERAGE_ASPECTS)} 三方面（R13）"]
    issues = []
    for aspect in COVERAGE_ASPECTS:
        entry = coverage[aspect] if isinstance(coverage[aspect], dict) else {}
        nos = entry.get("items")
        if set(entry) - {"items", "note"}:
            issues.append(f"coverage.{aspect}：只收 items 和 note")
        if not isinstance(nos, list) or not nos or not all(is_item_no(no, count) for no in nos):
            issues.append(f"coverage.{aspect}：items 写落在哪几项（矩阵序号），至少一项（R13）")
        elif len(nos) > 1 and not str(entry.get("note") or "").strip():
            issues.append(f"coverage.{aspect}：分布在多项，须在 note 写明已分布覆盖及依据（R13）")
    return issues


def validate_matrix(matrix: dict, rule_card: dict, fact_card: dict | None, resource_card: dict | None) -> list[str]:
    """返回全部问题；空列表才能请用户确认大纲。引用按当前的规则卡、事实卡、资源卡核对。"""
    if matrix.get("schema") != MATRIX_SCHEMA:
        return [f"响应矩阵 schema 应为 {MATRIX_SCHEMA}"]
    items = matrix.get("items")
    if not isinstance(items, list) or not items:
        return ["响应矩阵没有评审内容项：先运行 scaffold_matrix.py 出骨架"]
    issues = [f"响应矩阵不收顶层键 {key}" for key in sorted(set(matrix) - TOP_KEYS)]
    issues += check_item_titles(items, expected_items(rule_card))
    context = matrix_context(rule_card, fact_card, resource_card)
    rows = [item for item in items if isinstance(item, dict)]
    rule_keys = set(rule_rows(rule_card))
    for item in rows:
        label = f"第 {item.get('no')} 项"
        issues += check_item(item, label, context) + cites_issues(item, label, rule_keys)
    return issues + check_landing(rows, context) + check_pages(matrix, rows, rule_card) + \
        check_coverage(matrix, len(items))


def page_capacity(document_format: dict | None) -> int | None:
    """按锁定格式估算一页正文约多少字【推断】，只用来分篇幅；真实页数以第 4 步渲染计页为准。"""
    try:
        size, spacing = float(document_format["body_size_pt"]), float(document_format["line_spacing"])
        width = (document_format["page_width_cm"] - document_format["margin_left_cm"]
                 - document_format["margin_right_cm"]) * CM_TO_PT
        height = (document_format["page_height_cm"] - document_format["margin_top_cm"]
                  - document_format["margin_bottom_cm"]) * CM_TO_PT
        rule = document_format["line_spacing_rule"]
    except (KeyError, TypeError, ValueError):
        return None
    pitch = {"exact": spacing, "at_least": max(spacing, size * SINGLE_LINE)}.get(rule, size * SINGLE_LINE * spacing)
    if min(size, pitch, width, height) <= 0:
        return None
    return int(int(width // size) * int(height // pitch) * PAGE_FILL)


def joined(value: object, separator: str = "；") -> str:
    return separator.join(str(part) for part in value) if isinstance(value, list) and value else "—"


def resource_label(entry: dict) -> str:
    return f"{entry.get('id')} {entry.get('role') or entry.get('name') or entry.get('trade') or ''}".strip()


def item_row(item: dict, context: dict, capacity: int | None) -> str:
    no, title, pages = item.get("no"), str(item.get("title") or ""), item.get("pages")
    file = item_file(no, title) if is_item_no(no, 99) and title.strip() else "—"
    facts = joined(item.get("facts"), "、") + (f"（{item['facts_note']}）" if item.get("facts_note") else "")
    resources = [resource_label(context["resources"].get(ref, {"id": ref})) for ref in item.get("resources") or []
                 if isinstance(ref, str)]
    controls = joined(item.get("control_points"))
    words = str(int(pages * capacity)) if capacity and is_half_pages(pages, 0.5) else "—"
    return (f"| {cell(no)} | {cell(title)} | {cell(file)} | {cell(joined(item.get('points')))} | {cell(facts)} | "
            f"{cell(joined(resources, '、'))} | {cell(joined(item.get('mandatory'), '、'))} | {cell(controls)} | "
            f"{cell(pages)} | {words} |")


def landing_rows(items: list[dict], context: dict) -> list[str]:
    lines = ["| 编号 | 类型 | 条款原文 | 落在 |", "|---|---|---|---|"]
    for clause_id, clause in context["mandatory"].items():
        places = [f"第 {item.get('no')} 项" for item in items
                  if isinstance(item.get("mandatory"), list) and clause_id in item["mandatory"]]
        lines.append(f"| {cell(clause_id)} | {cell(clause.get('type'))} | {cell(clause_text(clause))} | "
                     f"{'、'.join(places) or '**没有落点**'} |")
    lines += [f"| {cell(clause_id)} | {cell(clause.get('type'))} | {cell(clause.get('text'))} | 阶段 8 提交前清单 |"
              for clause_id, clause in context["submission"].items()]
    return lines


def coverage_rows(matrix: dict) -> list[str]:
    coverage = matrix.get("coverage") if isinstance(matrix.get("coverage"), dict) else {}
    lines = ["| 方面 | 落在 | 依据 |", "|---|---|---|"]
    for aspect in COVERAGE_ASPECTS:
        entry = coverage.get(aspect) if isinstance(coverage.get(aspect), dict) else {}
        nos = entry.get("items") if isinstance(entry.get("items"), list) else []
        lines.append(f"| {aspect} | {'、'.join(f'第 {no} 项' for no in nos) or '—'} | {cell(entry.get('note'))} |")
    return lines


def budget_lines(matrix: dict, items: list[dict], rule_card: dict, capacity: int | None) -> list[str]:
    item_pages = sum(item["pages"] for item in items if is_half_pages(item.get("pages"), 0.5))
    limit = rule_card.get("page_limit") or {}
    ceiling = f"上限 {limit['value']} 页（{limit.get('kind')}）" if isinstance(limit.get("value"), int) \
        else "招标文件未规定篇幅上限"
    return [f"- 封面与目录 {cell(matrix.get('front_pages'))} 页 + 各项合计 {item_pages:g} 页 + 余量 "
            f"{cell(matrix.get('reserve_pages'))} 页 = {page_total(matrix, items):g} 页；{ceiling}",
            f"- 一页约 {capacity} 字（按锁定格式估算【推断】）" if capacity else "- 格式未锁定，不估字数"]


def card_section(rule_card: dict, items: list[dict]) -> list[str]:
    """类别知识卡给各项的必备要点（W9 按此比对）和参考；卡片是通用施工知识【推断】，不是招标文件的规则。"""
    cards, missing = project_cards(rule_card)
    skipped = f"；尚未交付、先跳过：{'、'.join(missing)}" if missing else ""
    lines = ["## 五、类别知识卡要点【推断】", "",
             f"> 按规则卡的工程类别用卡：{'、'.join(card['name'] for card in cards) or '无'}{skipped}。"
             "卡片是通用施工知识，不是招标文件的规则：不适用本项目的控制点从上表删掉，写作时不再提示；留下的"
             "（原文或改写后带它的叫法）正文没写到，W9 提示，可以说明理由不写。参考只用来查资源卡缺什么，"
             "不直接写进施组（R7）。", ""]
    if not cards:
        return lines
    lines += ["| 序号 | 评审内容（原文） | 必备要点 | 参考 |", "|---|---|---|---|"]
    for item in items:
        no, title = item.get("no"), str(item.get("title") or "")
        if any(word in title for word in FOCUS_WORDS):
            lines.append(f"| {cell(no)} | {cell(title)} | 招标文件点名的重点难点优先，不套卡片要点 | — |")
            continue
        points = [f"{point['text']}（{name}）" for name, point in card_points(cards, title)]
        hints = [f"{hint}（{name}）" for name, hint in card_hints(cards, title)]
        lines.append(f"| {cell(no)} | {cell(title)} | {cell(joined(points))} | {cell(joined(hints))} |")
    return lines


def render_matrix(matrix: dict, inputs: dict, project_name: str, issues: list[str]) -> str:
    context = matrix_context(inputs["rule_card"], inputs["fact_card"], inputs["resource_card"])
    items = [item for item in matrix.get("items") or [] if isinstance(item, dict)]
    lines = [f"# 响应矩阵与大纲（{project_name}）", "", *status_lines(issues, "response-matrix"), "",
             "> 由 `analysis/response-matrix.json` 生成，改大纲请改 JSON。一项评审内容对应一个中间稿，标题用原文，顺序与规则卡"
             "一致。页数是预算，真实页数以第 4 步渲染计页为准；控制点由类别知识卡预填（第五节），按本项目删改。", ""]
    if inputs.get("outline_only"):
        lines += ["> **资源卡有缺口：大纲可以确认，补齐资料、重新确认资源卡之前不能逐项撰写（R8）。**", ""]
    lines += ["## 一、逐项矩阵", "",
              "| 序号 | 评审内容（原文） | 中间稿 | 要点 | 事实 | 资源 | ★/实质性 | 控制点 | 页数 | 约字数 |",
              "|---|---|---|---|---|---|---|---|---|---|", *[item_row(item, context, inputs.get("capacity")) for item in items],
              "", "## 二、强制条款落点（R5）", "", *landing_rows(items, context), "",
              "## 三、实施、进度、组织（R13）", "", *coverage_rows(matrix), "",
              "## 四、篇幅预算", "", *budget_lines(matrix, items, inputs["rule_card"], inputs.get("capacity")), "",
              *card_section(inputs["rule_card"], items)]
    return "\n".join(lines) + "\n"


def load_inputs(project_dir: Path, state: dict) -> dict:
    record = (state.get("cards") or {}).get("resource_card") or {}
    return {"rule_card": load_json(project_dir / RULE_CARD_FILE, "规则卡"),
            "fact_card": load_optional(project_dir, FACT_CARD_FILE, "事实卡"),
            "resource_card": load_optional(project_dir, RESOURCE_CARD_FILE, "资源卡"),
            "capacity": page_capacity(state.get("document_format")),
            "outline_only": bool(record.get("outline_only"))}


def writing_inputs(project_dir: Path) -> dict:
    """阶段 5 写作闸和第 4 步门禁共用的输入：确认过的大纲加三张卡。"""
    return {"matrix": load_json(project_dir / MATRIX_FILE, "响应矩阵"),
            "rule_card": load_json(project_dir / RULE_CARD_FILE, "规则卡"),
            "fact_card": load_optional(project_dir, FACT_CARD_FILE, "事实卡"),
            "resource_card": load_optional(project_dir, RESOURCE_CARD_FILE, "资源卡")}


def matrix_items(inputs: dict) -> dict[int, dict]:
    return {item["no"]: item for item in inputs["matrix"].get("items") or []
            if isinstance(item, dict) and isinstance(item.get("no"), int) and not isinstance(item.get("no"), bool)}


def check_matrix(project_dir: Path) -> dict:
    """校验并重出大纲视图，不改状态。"""
    project_dir, state = load_project(project_dir)
    matrix = load_json(project_dir / MATRIX_FILE, "响应矩阵")
    inputs = load_inputs(project_dir, state)
    issues = validate_matrix(matrix, inputs["rule_card"], inputs["fact_card"], inputs["resource_card"])
    view = project_dir / MATRIX_VIEW
    view.write_text(render_matrix(matrix, inputs, state.get("project_name", ""), issues), encoding="utf-8")
    return {"issues": issues, "views": [str(view)], "outline_only": inputs["outline_only"]}


def confirm_matrix(project_dir: Path) -> dict:
    """用户明确同意大纲后才调用；阶段 3 须已完成且仍成立，矩阵每行连带锁定它依赖的规则行、事实和资源。"""
    project_dir, state = load_project(project_dir)
    if state["stages"].get("3") != "done":
        raise ValueError("阶段 3 事实卡与资源卡未完成，大纲不能确认")
    upstream = stage3_issues(project_dir, state)
    if upstream:
        raise ValueError(f"阶段 3 的卡片不再成立，先处理再确认大纲：{upstream[0]}")
    result = check_matrix(project_dir)
    if result["issues"]:
        raise ValueError(f"响应矩阵还有 {len(result['issues'])} 个问题，不能确认：{result['issues'][0]}")
    record_confirmation(project_dir, state, "response_matrix", MATRIX_FILE, ("rule_card", "fact_card", "resource_card"))
    if state["stages"].get("4") == "pending":
        state["stages"]["4"] = "in-progress"
    save_state(project_dir, state)
    return {"project": str(project_dir), "response_matrix": "confirmed", "outline_only": result["outline_only"],
            "views": result["views"]}


def stage4_issues(project_dir: Path, state: dict) -> list[str]:
    """阶段 4 完成条件：阶段 3 的卡片仍成立；大纲已确认且未失效；按当前规则复核仍通过。"""
    issues = stage3_issues(project_dir, state)
    status = card_status(project_dir, state, "response_matrix")
    if status["status"] != "confirmed":
        return issues + [f"响应矩阵{status['reason']}：校验用 --check response-matrix，用户同意后 --confirm response-matrix"]
    if issues:
        return issues
    matrix = load_json(project_dir / MATRIX_FILE, "响应矩阵")
    inputs = load_inputs(project_dir, state)
    current = validate_matrix(matrix, inputs["rule_card"], inputs["fact_card"], inputs["resource_card"])
    # 输入都已锁定；按当前规则再核一次，Skill 升级收紧校验后，旧规则下确认的大纲也要过新规则
    return [f"响应矩阵按当前规则复核不通过：{issue}" for issue in current]
