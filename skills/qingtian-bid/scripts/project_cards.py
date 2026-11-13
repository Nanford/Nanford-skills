"""Project cards of qingtian-bid: rule card validation, Markdown views and confirmation locks.

INPUT: <project>/analysis/rule-card.json (骨架见 templates/rule-card.json，阶段 2 由
       scaffold_rule_card.py 出候选、对照原文核实后填写); <project>/project-state.json;
       analysis/extraction-report.json and the extracted texts it lists; category_cards for the
       project_category check and for which category knowledge cards are delivered yet.
OUTPUT: validation issues; analysis/rule-card.md and analysis/mandatory-checklist.md for the user to
        review; a confirmation record in project-state.json that chains the card's sha256 to the
        extracted-text digest, so a 补遗 or any edit after confirmation makes the card stale;
        find_project_dir() for the stage-7 scripts that start from the finished DOCX; scoped_clauses() splits
        the mandatory clauses by where they go (施组 for stage 4 and B9, 提交前清单 for stage 8, 决策 4c-4A);
        clause_keywords() / clause_text() for the "招标指定" clauses (tender-named 重点难点, 危大清单) whose
        keywords B9 checks; the optional addenda_changes candidates (答疑、补遗更正) must be checked off;
        the qingtian field says whether the tender enables 青天 and how far the 导则 and 示范文本 reach (决策 D11);
        is_other_method() for an 评标办法 outside Hefei's four, which is recorded as written (决策 2A);
        the fields located row by row with a ref are checked and rendered by rule_card_fields.py (决策 3A), the
        投标文件格式 fields by bid_forms_fields.py, the 项目画像 and its triggers by project_profile.py; 初步评审表
        rows carry id and file; mandatory clauses may go to 商务文件 or 报价文件, routed to 提交前清单 until step 5;
        confirm_rule_card() saves analysis/rule-card.confirmed.json and reports the rows changed since the last
        confirmation (row keys and comparison live in rule_card_rows.py).
POS: card layer behind project_status.py. JSON is the source of truth (决策 1A); the Markdown files
     are generated views and are never parsed back. Step 4 gate scripts import the validators and
     card_status() from here instead of re-implementing them. The confirmation record and its input
     digests (extraction, rule card, fact card, company materials, resource card) are shared by every card;
     the fact and resource cards live in fact_resource_cards.py, the response matrix in response_matrix.py.
     Upstream cards are locked row by row (row_locks.py, 决策 D9): a change voids only the rows depending on it, and
     card_status() names them. It does not follow the chain: a stale rule card leaves a fact card with no affected row
     confirmed, and the stage gates, which check every card above them, are what stop the work.

project-state.json keys owned here:
  cards.<name>   {file, sha256, inputs: {input: digest}, confirmed_at, ...}。确认后卡片本身或任一输入有变化即失效。
                 extraction、materials 的指纹是一个值；rule_card、fact_card、resource_card 是 {行键: 指纹}，
                 下游卡片另有 rows: {行键: {digest, deps}}，变了的上游行只让依赖它的行失效。
                 cards.rule_card 的输入是 extraction
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from bid_forms_fields import bid_forms_sections, check_bid_forms
from category_cards import CATEGORY_FIELD, card_path, category_value, check_category, no_card_names, selected_names
from format_state import load_state, save_state
from project_profile import check_profile, profile_sections
from rule_card_fields import (
    REF_FIELDS,
    REF_FIELD_LABELS,
    UNSPECIFIED,
    cell,
    check_ref_entry,
    check_ref_fields,
    is_empty,
    ref_sections,
)
from row_locks import (
    FACT_INPUT,
    LOCKED_CARDS,
    RESOURCE_INPUT,
    affected_rows,
    locked_rows,
    own_changes,
    upstream_digests,
)
from rule_card_rows import row_changes, rule_row_digests


SKILL_DIR = Path(__file__).resolve().parents[1]
RULE_CARD_TEMPLATE = SKILL_DIR / "templates" / "rule-card.json"
RULE_CARD_FILE = "analysis/rule-card.json"
# 每次确认时存的那一版：变更单靠它列出每行的旧值和新值
RULE_SNAPSHOT_FILE = "analysis/rule-card.confirmed.json"
# 连接号的各种写法：真实招标文件的附件把公告里的"——"写成"--"或"-"（2026-10-31）
DASH_RUN = re.compile(r"[-－—–―─]+")
FACT_CARD_FILE = "analysis/fact-card.json"
RESOURCE_CARD_FILE = "analysis/resource-card.json"
MATRIX_FILE = "analysis/response-matrix.json"
MATERIAL_INDEX_FILE = "analysis/material-index.json"
FINISHED_DOCX = "output/施工组织设计.docx"
# /3 加了 qingtian（决策 D11、2A）和带 ref 的新字段（决策 3A）。开发版不兼容旧项目（决策 D10）：旧规则卡按 schema 不符报出，
# 在阶段 2 重出候选后核实
RULE_CARD_SCHEMA = "qingtian-rule-card/3"
MODEL_TEXT_DEFAULT = "示范文本默认"
BASES = ("招标文件", MODEL_TEXT_DEFAULT, UNSPECIFIED)
TRACKS = ("T-AI", "T-暗标", "T-合格", "T-定档")
METHOD_TRACKS = {
    "技术评分合理价格法": ("T-AI",),
    "综合评估法": ("T-AI", "T-暗标"),
    "动态合理价格法": ("T-合格",),
    "定性定量评审法": ("T-定档",),
}
# 招标文件启没启用青天，按原文信号判（hefei-rules 第一节）；判不清硬停，问用户
QINGTIAN_FIELD = "qingtian"
QINGTIAN_ON, QINGTIAN_OFF, QINGTIAN_UNCLEAR = "启用", "未启用", "判不清"
QINGTIAN_VALUES = (QINGTIAN_ON, QINGTIAN_OFF, QINGTIAN_UNCLEAR)
# 导则和示范文本管不管得到这个项目（决策 D11）：只有合肥房建市政能把示范文本当规则，其余只作参考，招标文件没写就是没写
HEFEI_CIVIL, HEFEI_OTHER, OUTSIDE_HEFEI = "合肥房建市政", "合肥其他", "合肥以外"
RULE_SCOPES = (HEFEI_CIVIL, HEFEI_OTHER, OUTSIDE_HEFEI)
MANDATORY_TYPES = ("★", "实质性", "否决", "招标指定")
# 招标指定：招标文件点名要施组阐述的内容，如前附表 3.7.1 的本项目重点难点、危大工程清单（"必须在施工组织设计
# 中全面重点阐述"）。它没有可比对的数值，靠 keywords（摘自条款原文、正文必须写到的叫法）由 B9 逐个核对
TENDER_SPECIFIED = "招标指定"
# 强制条款的去处（决策 4c-4A）：施组（默认，不写即是）在阶段 4 找落点、B9 核对；提交前清单（投标保证金、
# 投标有效期、备选方案这类商务或递交条款）不在施组里落点，进阶段 8 逐条勾选
TECH_SCOPE = "施组"
SUBMISSION_SCOPE = "提交前清单"
BUSINESS_SCOPE, PRICE_SCOPE = "商务文件", "报价文件"
MANDATORY_SCOPES = (TECH_SCOPE, SUBMISSION_SCOPE, BUSINESS_SCOPE, PRICE_SCOPE)
# 临时方案（第 2d 步）：商务线还没做，去商务文件、报价文件的条款先并入提交前清单，阶段 8 逐条核对，一条也不丢。
# 替换路径：第 5 步合龙时改成在商务线、报价线落点，删掉这张表
SCOPE_ROUTES = {BUSINESS_SCOPE: SUBMISSION_SCOPE, PRICE_SCOPE: SUBMISSION_SCOPE}
# 初步评审表每行由哪个文件满足
PRELIMINARY_FILES = ("商务", "技术", "报价")
TECH_FILE = "技术"
PAGE_LIMIT_KINDS = ("要求", "建议")
# (字段, 中文名, 必填规则)。required：不能写"招标文件未规定"；scored：T-合格（动态合理价格法，
# 技术文件不打分）以外必填；optional：招标文件没写时可写"招标文件未规定"。
RULE_FIELDS = (
    ("project_name", "项目名称", "required"),
    # 没提到青天的招标文件写"未启用"，出处写查过哪几章，不写"招标文件未规定"
    (QINGTIAN_FIELD, "青天启用情况", "required"),
    # 主类别、涉及专业、场景，决定阶段 4、5 用哪几张类别知识卡；取值由 category_cards.check_category 把关
    (CATEGORY_FIELD, "工程类别", "required"),
    ("evaluation_method", "评标办法", "required"),
    ("track", "评审轨道", "required"),
    ("ai_clause", "AI 类人评审条款", "optional"),
    ("blind_clause", "暗标条款", "optional"),
    ("review_items", "评审内容", "scored"),
    ("grading", "档次与评分区间", "scored"),
    ("review_notes", "评审注释（含编制建议）", "optional"),
    ("page_limit", "篇幅上限", "optional"),
    ("schedule", "工期", "required"),
    ("quality_standard", "质量标准", "required"),
    ("safety_target", "安全目标", "optional"),
    ("shortlist_rule", "入围与推荐规则", "required"),
    ("preliminary_review", "初步评审表", "required"),
    ("mandatory", "强制条款清单", "required"),
    # 格式可以是"招标文件未规定"，但必须二选一写明，由 check_format 把关
    ("format", "成品格式", "optional"),
    # 出处逐行写 ref，校验在 rule_card_fields.py（决策 3A）
    *REF_FIELDS,
)
FIELD_NAMES = {name: label for name, label, _ in RULE_FIELDS}
# 本项目自己的取值：示范文本只是模板，不可能替招标文件给出这些值，所以不接受"示范文本默认"
PROJECT_OWN_FIELDS = ("project_name", QINGTIAN_FIELD, CATEGORY_FIELD, "evaluation_method", "track", "schedule",
                      "quality_standard", "safety_target", "mandatory")


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_project(project_dir: Path) -> tuple[Path, dict]:
    """项目目录和状态；只认 qingtian-bid 建的项目，避免误改别的工具建的项目。"""
    project_dir = project_dir.expanduser().resolve()
    state = load_state(project_dir)
    if state.get("skill") != "qingtian-bid":
        raise ValueError(f"不是 qingtian-bid 项目（skill: {state.get('skill')}）: {project_dir}")
    return project_dir, state


def find_project_dir(artifact_path: Path) -> Path | None:
    """成品等文件所在的项目：往上找 project-state.json；不在项目里返回 None。"""
    for parent in artifact_path.expanduser().resolve().parents:
        if (parent / "project-state.json").is_file():
            return parent
    return None


def load_json(path: Path, label: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}无法读取: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label}应为 JSON 对象: {path}")
    return data


def rule_card_template() -> dict:
    return load_json(RULE_CARD_TEMPLATE, "规则卡模板")


def field_rule(name: str) -> str:
    return next(rule for field, _, rule in RULE_FIELDS if field == name)


def is_other_method(method: object) -> bool:
    """招标文件写了评标办法，但不在合肥四种之内（决策 2A）：不硬停，照录原文，轨道按条款信号由用户确认。"""
    return isinstance(method, str) and bool(method.strip()) and method not in METHOD_TRACKS


def field_required(name: str, track: str | None, method: object) -> bool:
    # 四种以外的办法没有示范文本的入围规则，招标文件可能真没写（决策 2A）
    if name == "shortlist_rule" and is_other_method(method):
        return False
    rule = field_rule(name)
    return rule == "required" or (rule == "scored" and track != "T-合格")


def check_entry(name: str, entry: object, track: str | None, method: object = None) -> list[str]:
    """每个字段的公共规则：已核对、依据合法、有值就有出处、未规定只能用于非必填字段。"""
    if name in REF_FIELD_LABELS:
        return check_ref_entry(name, entry)
    label = FIELD_NAMES[name]
    if not isinstance(entry, dict) or not {"value", "basis", "source", "checked"} <= set(entry):
        return [f"{label}：字段结构不完整（须含 value、basis、source、checked）"]
    issues = [] if entry["checked"] is True else [f"{label}：待核对（对照招标文件原文核实后把 checked 改为 true）"]
    if entry["basis"] not in BASES:
        return issues + [f"{label}：依据只能是 {'、'.join(BASES)}"]
    if entry["basis"] == MODEL_TEXT_DEFAULT and name in PROJECT_OWN_FIELDS:
        issues.append(f"{label}：是本项目自己的取值，只能来自招标文件，不能写“示范文本默认”")
    if entry["basis"] == UNSPECIFIED:
        if field_required(name, track, method):
            issues.append(f"{label}：必须从招标文件找到，不能写“招标文件未规定”；确实没有时硬停，问用户")
        elif name != "format" and not is_empty(entry["value"]):
            issues.append(f"{label}：写了“招标文件未规定”就不能再填值")
        return issues
    if is_empty(entry["value"]) and name != "format":
        issues.append(f"{label}：缺少内容")
    if not str(entry.get("source") or "").strip():
        issues.append(f"{label}：缺少出处（文件、章节、页码）")
    return issues


def signals_complete(signals: object) -> bool:
    return isinstance(signals, list) and bool(signals) and all(
        isinstance(item, dict) and item.get("text") and item.get("source") for item in signals)


def check_track(card: dict) -> list[str]:
    method = card["evaluation_method"].get("value")
    track_entry = card["track"]
    track = track_entry.get("value")
    issues = []
    if not is_empty(method) and not isinstance(method, str):
        issues.append("评标办法写招标文件原文的名称（文字）")
    if track not in TRACKS:
        return issues + [f"评审轨道只能是 {'、'.join(TRACKS)}"]
    allowed = METHOD_TRACKS.get(method, ()) if isinstance(method, str) else ()
    if allowed and track not in allowed:
        issues.append(f"{method}只能判为 {'或'.join(allowed)}（当前 {track}）")
    has_ai = not is_empty(card["ai_clause"].get("value"))
    has_blind = not is_empty(card["blind_clause"].get("value"))
    if has_ai and has_blind:
        issues.append("AI 条款与暗标条款同时出现：硬停，请用户向招标人澄清")
    # 综合评估法和四种以外的办法，轨道只能靠条款原文判，没有原文就没有依据（决策 2A）
    needs_clause = method == "综合评估法" or is_other_method(method)
    if needs_clause and track == "T-AI" and not has_ai:
        issues.append(f"{method}判 T-AI 须有招标文件的 AI 类人评审条款原文")
    if needs_clause and track == "T-暗标" and not has_blind:
        issues.append(f"{method}判 T-暗标 须有招标文件的暗标条款原文")
    if track == "T-定档" and not str(track_entry.get("handoff") or "").strip():
        issues.append("T-定档 须在 track.handoff 写明定标部分由用户另行编制（R24）")
    if not signals_complete(track_entry.get("signals")):
        issues.append("评审轨道须列出判定信号原文和出处（track.signals，每条含 text、source）")
    return issues


def qingtian_off_issues(card: dict, entry: dict) -> list[str]:
    """判了未启用，又和别的字段对不上；既没启用也不在合肥的，规则不保证适用，要用户本人决定（SKILL.md《适用范围》）。"""
    issues = []
    if card["track"].get("value") == "T-AI":
        issues.append("青天判未启用，轨道却是 T-AI：对照招标文件原文核实")
    if not is_empty(card["ai_clause"].get("value")):
        issues.append("青天判未启用，却照录了 AI 类人评审条款：对照招标文件原文核实")
    if entry.get("rule_scope") == OUTSIDE_HEFEI and not str(entry.get("user_decision") or "").strip():
        issues.append("没启用青天，也不在合肥：先告诉用户规则不保证适用，把用户决定（停下，或只借用红线和格式能力）的"
                      "原话写进 qingtian.user_decision")
    return issues


def check_qingtian(card: dict) -> list[str]:
    """招标文件启没启用青天、导则和示范文本管不管得到（决策 D11）。Skill 适不适用看前者，依据够不够看后者。"""
    entry = card[QINGTIAN_FIELD]
    value, scope = entry.get("value"), entry.get("rule_scope")
    issues = []
    if value == QINGTIAN_UNCLEAR:
        issues.append("招标文件有没有启用青天判不清：硬停，问用户")
    elif value not in QINGTIAN_VALUES:
        issues.append(f"青天启用情况只能是 {'、'.join(QINGTIAN_VALUES)}")
    if scope not in RULE_SCOPES:
        issues.append(f"规则依据范围 qingtian.rule_scope 只能是 {'、'.join(RULE_SCOPES)}")
    if value == QINGTIAN_ON and not signals_complete(entry.get("signals")):
        issues.append("青天判启用须列出信号原文和出处（qingtian.signals，每条含 text、source）")
    if value == QINGTIAN_OFF:
        issues += qingtian_off_issues(card, entry)
    if scope in (HEFEI_OTHER, OUTSIDE_HEFEI):
        issues += [f"{label}：本项目是“{scope}”，示范文本只作参考，不能当依据；招标文件没写就写“招标文件未规定”"
                   for name, label in FIELD_NAMES.items() if card[name].get("basis") == MODEL_TEXT_DEFAULT]
    return issues


def check_review_items(entry: dict) -> list[str]:
    items = entry.get("value") or []
    if not isinstance(items, list):
        return ["评审内容应为列表"]
    issues = []
    titles = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or item.get("no") != index or not str(item.get("title") or "").strip():
            issues.append(f"评审内容第 {index} 项须含 no={index} 和评审内容原文 title")
            continue
        titles.append(item["title"].strip())
    if len(set(titles)) != len(titles):
        issues.append("评审内容有重复的标题")
    return issues


def preliminary_row_issues(row: dict, index: int, seen: set[str]) -> list[str]:
    """每行的编号和去处：编号给后面的行级锁和对账表用，file 说明这一行由哪个文件满足。"""
    issues = []
    row_id = str(row.get("id") or "")
    if not re.fullmatch(r"PR\d{2,}", row_id) or row_id in seen:
        issues.append(f"初步评审表第 {index} 行的编号须为 PR01 这样且不重复（当前: {row_id or '空'}）")
    seen.add(row_id)
    if row.get("file") not in PRELIMINARY_FILES:
        issues.append(f"初步评审表第 {index} 行须标明由哪个文件满足 file（{'、'.join(PRELIMINARY_FILES)}）")
    elif row["file"] == TECH_FILE and row.get("tech_related") is False:
        issues.append(f"初步评审表第 {index} 行由技术文件满足，tech_related 应为 true")
    return issues


def check_preliminary(entry: dict) -> list[str]:
    rows = entry.get("value") or []
    if not isinstance(rows, list):
        return ["初步评审表应为列表"]
    issues = []
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not all(str(row.get(key) or "").strip()
                                                for key in ("stage", "factor", "standard")):
            issues.append(f"初步评审表第 {index} 行须含环节 stage、评审因素 factor、评审标准原文 standard")
            continue
        issues += preliminary_row_issues(row, index, seen)
        if not isinstance(row.get("tech_related"), bool):
            issues.append(f"初步评审表第 {index} 行须标明 tech_related（与施组有关为 true）")
        elif row["tech_related"] and not str(row.get("requirement") or "").strip():
            issues.append(f"初步评审表第 {index} 行与施组有关，须写对施组的要求 requirement")
    if rows and not any(isinstance(row, dict) and row.get("tech_related") is True for row in rows):
        issues.append("初步评审表没有一行标为与施组有关：至少投标文件格式、工期、质量标准与施组有关（Q0）")
    return issues


def clause_scope(clause: dict) -> str:
    return clause["scope"] if "scope" in clause else TECH_SCOPE


def clause_route(clause: dict) -> str:
    """条款实际在哪里核对：现在商务文件、报价文件的都并入提交前清单（SCOPE_ROUTES，第 5 步替换）。"""
    scope = clause_scope(clause)
    return SCOPE_ROUTES.get(scope, scope)


def scoped_clauses(rule_card: dict, scope: str) -> list[dict]:
    """规则卡里在 scope 核对的强制条款；阶段 4、B9 只看施组的，阶段 8 看提交前清单的（含暂时并入的）。"""
    return [clause for clause in (rule_card.get("mandatory") or {}).get("value") or []
            if isinstance(clause, dict) and clause_route(clause) == scope]


def clause_keywords(clause: dict) -> list[str]:
    """条款登记的关键词（正文须写到的叫法）；格式不对的由 check_keywords 报，这里只取能用的。"""
    words = clause.get("keywords")
    return [word.strip() for word in words if isinstance(word, str) and word.strip()] if isinstance(words, list) else []


def check_keywords(item: dict, label: str) -> list[str]:
    """keywords 每个都要出自条款原文（叫法不另起，R15）；招标指定的条款至少一个，而且只能去施组。"""
    words = item.get("keywords", [])
    if not isinstance(words, list) or not all(isinstance(word, str) and word.strip() for word in words):
        return [f"强制条款 {label} 的 keywords 应为非空字符串列表"]
    text = str(item.get("text") or "")
    issues = [f"强制条款 {label} 的关键词“{word.strip()}”不在条款原文里：叫法照原文摘（R15）"
              for word in words if word.strip() not in text]
    if item.get("type") == TENDER_SPECIFIED:
        if not words:
            issues.append(f"强制条款 {label} 是招标指定内容：用 keywords 列出正文必须写到的叫法（摘自条款原文），B9 逐个核对")
        if clause_scope(item) != TECH_SCOPE:
            issues.append(f"强制条款 {label} 是招标指定的施组内容，去处只能是施组")
    return issues


def check_mandatory(entry: dict) -> list[str]:
    items = entry.get("value") or []
    if not isinstance(items, list):
        return ["强制条款清单应为列表"]
    issues = []
    seen: set[str] = set()
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            issues.append(f"强制条款第 {index} 条应为对象")
            continue
        item_id = str(item.get("id") or "")
        if not re.fullmatch(r"M\d{2,}", item_id) or item_id in seen:
            issues.append(f"强制条款第 {index} 条的编号须为 M01 这样且不重复（当前: {item_id or '空'}）")
        seen.add(item_id)
        if item.get("type") not in MANDATORY_TYPES:
            issues.append(f"强制条款 {item_id or index} 的类型只能是 {'、'.join(MANDATORY_TYPES)}")
        if not str(item.get("text") or "").strip() or not str(item.get("source") or "").strip():
            issues.append(f"强制条款 {item_id or index} 须有条款原文 text 和出处 source")
        if clause_scope(item) not in MANDATORY_SCOPES:
            issues.append(f"强制条款 {item_id or index} 的去处 scope 只能是 {'、'.join(MANDATORY_SCOPES)}（不写即施组）")
        issues += check_keywords(item, item_id or str(index))
    # 工期、质量标准是施组必须落点的实质性要求（R5、R22），全部移去提交前清单说明登记错了
    if items and all(isinstance(item, dict) and clause_route(item) == SUBMISSION_SCOPE for item in items):
        issues.append("强制条款没有一条去施组：工期、质量标准等实质性要求必须在施组里落点（R5、R22）")
    return issues


def check_page_limit(entry: dict) -> list[str]:
    if entry.get("basis") == UNSPECIFIED:
        return []
    value = entry.get("value")
    issues = []
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        issues.append("篇幅上限应为正整数页数")
    if entry.get("kind") not in PAGE_LIMIT_KINDS:
        issues.append("篇幅上限须标明招标文件写的是“要求”还是“建议”（kind）")
    return issues


def check_format(entry: dict, project_dir: Path) -> list[str]:
    """格式只记指针：tender-format.json 或"招标文件对格式无规定"，规定本身不在规则卡里重复。"""
    value = entry.get("value")
    if not isinstance(value, dict):
        return ["成品格式应为对象（tender_format、no_rules、other_rules）"]
    pointer = value.get("tender_format")
    no_rules = value.get("no_rules") is True
    if bool(pointer) == no_rules:
        return ["成品格式须二选一：tender_format 指向 analysis/tender-format.json，或 no_rules 为 true"]
    if no_rules and entry.get("basis") != UNSPECIFIED:
        return ["招标文件对格式无规定时，依据写“招标文件未规定”"]
    if pointer and not (project_dir / pointer).is_file():
        return [f"成品格式指向的文件不存在: {pointer}（写法见 stage-6-assembly.md 第二节）"]
    return []


ADDENDA_FIELD = "addenda_changes"
ADDENDA_LABEL = "答疑、补遗里的更正（以更正后的为准）"


def check_addenda(card: dict) -> list[str]:
    """答疑、补遗的更正候选（scaffold_rule_card.py 找的，可选字段）：有就要逐条核对完，把更正落到相应字段。
    真实招标文件里答疑会改前附表（如危大工程清单改成"/"），漏看就照原内容写错。"""
    entry = card.get(ADDENDA_FIELD)
    if not isinstance(entry, dict) or not entry.get("candidates") or entry.get("checked") is True:
        return []
    return [f"{ADDENDA_LABEL}：待核对（逐条把更正落到相应字段；核对完把 {ADDENDA_FIELD}.checked 改为 true）"]


def validate_rule_card(card: dict, project_dir: Path, state: dict) -> list[str]:
    """返回全部问题；空列表才能请用户确认。"""
    if card.get("schema") != RULE_CARD_SCHEMA:
        return [f"规则卡 schema 应为 {RULE_CARD_SCHEMA}"]
    missing = [label for name, label, _ in RULE_FIELDS if name not in card]
    if missing:
        return [f"规则卡缺少字段：{'、'.join(missing)}"]
    track = card["track"].get("value") if isinstance(card["track"], dict) else None
    method = card["evaluation_method"].get("value") if isinstance(card["evaluation_method"], dict) else None
    issues = [issue for name, _, _ in RULE_FIELDS for issue in check_entry(name, card[name], track, method)]
    if issues and any("字段结构不完整" in issue for issue in issues):
        return issues
    issues += check_qingtian(card)
    issues += check_track(card)
    issues += check_review_items(card["review_items"])
    issues += check_preliminary(card["preliminary_review"])
    issues += check_mandatory(card["mandatory"])
    issues += check_page_limit(card["page_limit"])
    issues += check_format(card["format"], project_dir)
    issues += check_addenda(card)
    issues += check_ref_fields(card, project_dir)
    issues += check_bid_forms(card, project_dir)
    issues += check_profile(card, project_dir)
    if card[CATEGORY_FIELD].get("basis") != UNSPECIFIED:  # 写了未规定的，check_entry 已按必填报出
        issues += check_category(card[CATEGORY_FIELD].get("value"))
    mismatch = name_mismatch(card["project_name"].get("value"), state.get("project_name") or "")
    return issues + ([mismatch] if mismatch else [])


def name_mismatch(name: str | None, registered: str) -> str | None:
    """封面项目名称须与招标文件一字不差（硬停）。只差连接号写法（"--""—""——"）时点明，免得逐字比对。"""
    if not name or name == registered:
        return None
    dashes_only = DASH_RUN.sub("-", name) == DASH_RUN.sub("-", registered)
    hint = "（只差连接号写法，以招标公告原文为准，改规则卡或开工登记）" if dashes_only else ""
    return f"规则卡项目名称“{name}”与开工登记“{registered}”不一致{hint}：硬停，请用户核实封面"


def basis_text(entry: dict) -> str:
    mark = "✓" if entry.get("checked") is True else "待核对"
    return f"{cell(entry.get('basis'))} | {cell(entry.get('source'))} | {mark}"


def name_list(names: object) -> str:
    return "、".join(str(name) for name in names) if isinstance(names, list) and names else "无"


def category_text(card: dict) -> str:
    """工程类别一格：主类别、涉及专业、场景；选到但卡片还没交付的写明，阶段 4、5 先跳过它们。"""
    value = category_value(card)
    if not any(value.get(key) for key in ("main", "modules", "scenarios")):
        return ""
    text = (f"主类别 {value.get('main') or '—'}；涉及专业 {name_list(value.get('modules'))}；"
            f"场景 {name_list(value.get('scenarios'))}")
    missing = [name for name in selected_names(card) if not card_path(name).is_file()]
    no_card = no_card_names(card)
    return text + (f"（类别知识卡尚未交付：{'、'.join(missing)}，阶段 4、5 先跳过）" if missing else "") + \
        (f"（没有类别知识卡：{'、'.join(no_card)}，只按招标文件和红线写，不编规则）" if no_card else "")


def qingtian_text(entry: dict) -> str:
    """青天一格：启用情况、规则依据范围；依据不足和用户的决定都写明，用户确认时看得到。"""
    if is_empty(entry.get("value")):
        return ""
    scope = entry.get("rule_scope") or "规则依据范围未判"
    note = "" if scope == HEFEI_CIVIL else "；导则和示范文本只作参考，以招标文件为准"
    decision = str(entry.get("user_decision") or "").strip()
    return f"{entry['value']}；{scope}{note}" + (f"；用户决定：{decision}" if decision else "")


def method_note(card: dict) -> list[str]:
    """四种以外的评标办法：确认时明说没有规则依据（决策 2A）。"""
    method = card["evaluation_method"].get("value")
    if not is_other_method(method):
        return []
    return [f"> 评标办法“{method}”不在合肥四种之内：评审轨道由用户确认，没有导则依据；入围规则招标文件没写的就写“招标文件未规定”。",
            ""]


def text_rows(card: dict, names: tuple[str, ...]) -> list[str]:
    rows = ["| 项 | 内容 | 依据 | 出处 | 核对 |", "|---|---|---|---|---|"]
    for name in names:
        entry = card[name]
        value = entry.get("value")
        if name == "page_limit" and value:
            value = f"{value} 页（招标文件写的是“{entry.get('kind') or '?'}”）"
        if name == "track" and value:
            value = f"{value}{'；' + entry['handoff'] if entry.get('handoff') else ''}"
        if name == CATEGORY_FIELD:
            value = category_text(card)
        if name == QINGTIAN_FIELD:
            value = qingtian_text(entry)
        rows.append(f"| {FIELD_NAMES[name]} | {cell(value)} | {basis_text(entry)} |")
    return rows


def candidate_lines(card: dict) -> list[str]:
    lines = []
    for name, label in [*((name, label) for name, label, _ in RULE_FIELDS), (ADDENDA_FIELD, ADDENDA_LABEL)]:
        entry = card.get(name)
        if not isinstance(entry, dict) or entry.get("checked") is True or not entry.get("candidates"):
            continue
        lines.append(f"### {label}")
        lines.extend(f"- {cell(item.get('text'))}（{cell(item.get('source'))}）" for item in entry["candidates"])
        lines.append("")
    return lines


def review_section(card: dict) -> list[str]:
    entry = card["review_items"]
    lines = ["## 二、评审内容（一级标题照此原文，顺序不改，一项不缺）", "",
             f"依据：{basis_text(entry).replace(' | ', '；')}", "", "| 序号 | 评审内容原文 |", "|---|---|"]
    lines += [f"| {item.get('no')} | {cell(item.get('title'))} |" for item in entry.get("value") or []]
    return lines


def preliminary_section(card: dict) -> list[str]:
    entry = card["preliminary_review"]
    lines = ["## 三、初步评审表（原文）", "", f"依据：{basis_text(entry).replace(' | ', '；')}", "",
             "| 编号 | 环节 | 评审因素 | 评审标准原文 | 由哪个文件满足 | 与施组有关 | 对施组的要求 |",
             "|---|---|---|---|---|---|---|"]
    for row in entry.get("value") or []:
        related = "是" if row.get("tech_related") is True else "否"
        lines.append(f"| {cell(row.get('id'))} | {cell(row.get('stage'))} | {cell(row.get('factor'))} | "
                     f"{cell(row.get('standard'))} | {cell(row.get('file'))} | {related} | {cell(row.get('requirement'))} |")
    return lines


SCOPE_PLACES = {TECH_SCOPE: "施组：阶段 4 响应矩阵填落点", SUBMISSION_SCOPE: "提交前清单：阶段 8 逐条核对",
                BUSINESS_SCOPE: "商务文件：现阶段并入提交前清单，阶段 8 逐条核对",
                PRICE_SCOPE: "报价文件：现阶段并入提交前清单，阶段 8 逐条核对"}


def clause_text(clause: dict) -> str:
    """条款原文，登记了关键词的附上"正文须写到"，用户确认规则卡、大纲时看得到 B9 要核对什么。"""
    words = clause_keywords(clause)
    return str(clause.get("text") or "") + (f"（正文须写到：{'、'.join(words)}）" if words else "")


def mandatory_rows(card: dict) -> list[str]:
    rows = ["| 编号 | 类型 | 条款原文 | 出处 | 去处 |", "|---|---|---|---|---|"]
    for item in card["mandatory"].get("value") or []:
        if not isinstance(item, dict):
            continue
        scope = clause_scope(item)
        rows.append(f"| {cell(item.get('id'))} | {cell(item.get('type'))} | {cell(clause_text(item))} | "
                    f"{cell(item.get('source'))} | {cell(SCOPE_PLACES.get(scope, scope))} |")
    return rows


def format_section(card: dict) -> list[str]:
    entry = card["format"]
    value = entry.get("value") if isinstance(entry.get("value"), dict) else {}
    pointer = value.get("tender_format")
    summary = (f"按 `{pointer}` 覆盖开工所选（stage-6-assembly.md 第二节）" if pointer
               else "招标文件对格式无规定，沿用开工所选" if value.get("no_rules") else "—")
    return ["## 五、成品格式", "", f"- {summary}", f"- 格式记录装不下的规定（颜色、装订、份数、图表）：{cell(value.get('other_rules'))}",
            f"- 依据：{basis_text(entry).replace(' | ', '；')}"]


def status_lines(issues: list[str], confirm_arg: str = "rule-card") -> list[str]:
    if not issues:
        return [f"> 状态：校验通过。请用户逐节核对，明确同意后才运行 `project_status.py <项目目录> --confirm {confirm_arg}`。"]
    return [f"> 状态：还有 {len(issues)} 个问题，不能请用户确认。", "", *[f"- {item}" for item in issues]]


def render_rule_card(card: dict, project_name: str, issues: list[str], project_dir: Path | None = None) -> str:
    general = ("project_name", QINGTIAN_FIELD, CATEGORY_FIELD, "evaluation_method", "track", "ai_clause", "blind_clause")
    scoring = ("grading", "review_notes", "page_limit", "schedule", "quality_standard", "safety_target",
               "shortlist_rule")
    lines = [f"# 规则卡（{project_name}）", "", *status_lines(issues), "",
             "## 一、评标办法与评审轨道", "", *method_note(card), *text_rows(card, general), "",
             *[f"- 青天信号：{cell(item.get('text'))}（{cell(item.get('source'))}）"
               for item in card[QINGTIAN_FIELD].get("signals") or [] if isinstance(item, dict)],
             *[f"- 判定信号：{cell(item.get('text'))}（{cell(item.get('source'))}）"
               for item in card["track"].get("signals") or [] if isinstance(item, dict)], "",
             *review_section(card), "", "## 评分、篇幅与实质性要求", "", *text_rows(card, scoring), "",
             *preliminary_section(card), "", f"## 四、强制条款清单（{'、'.join(MANDATORY_TYPES)}）", "", *mandatory_rows(card), "",
             *format_section(card), "", "## 六、资格、日期与表外事项（每行带原文定位）", "", *ref_sections(card),
             "## 七、投标文件格式（按一级节确认）", "", *bid_forms_sections(card),
             "## 八、项目画像和触发项", "", *profile_sections(card, project_dir)]
    candidates = candidate_lines(card)
    if candidates:
        lines += ["## 待核对的候选（scaffold_rule_card.py 按文字规则找到，不是结论）", "", *candidates]
    return "\n".join(lines)


def render_mandatory(card: dict, project_name: str) -> str:
    return "\n".join([f"# 强制条款清单（{project_name}）", "",
                      "> 由规则卡 `analysis/rule-card.json` 生成，改清单请改规则卡。去处为施组的，落点在阶段 4 响应矩阵填写；"
                      "去处为提交前清单、商务文件、报价文件的（商务、递交类条款），阶段 8 逐条核对。",
                      "", *mandatory_rows(card), ""])


def renderable(card: dict) -> dict:
    """结构不完整的字段用模板补位，只为出 MD 视图；问题清单照样列出缺失。"""
    template = rule_card_template()
    view = {name: card[name] if isinstance(card.get(name), dict) else template[name] for name in template}
    if isinstance(card.get(ADDENDA_FIELD), dict):  # 可选字段，模板里没有
        view[ADDENDA_FIELD] = card[ADDENDA_FIELD]
    return view


def write_rule_card_views(project_dir: Path, card: dict, project_name: str, issues: list[str]) -> list[Path]:
    analysis = project_dir / "analysis"
    card = renderable(card)
    views = [(analysis / "rule-card.md", render_rule_card(card, project_name, issues, project_dir)),
             (analysis / "mandatory-checklist.md", render_mandatory(card, project_name))]
    for path, text in views:
        path.write_text(text, encoding="utf-8")
    return [path for path, _ in views]


def extraction_digest(project_dir: Path) -> str:
    """提取报告里每个文件的来源指纹加上提取文本的指纹；补遗进来或重新提取后会变。"""
    report = load_json(project_dir / "analysis" / "extraction-report.json", "提取报告")
    parts = []
    for item in sorted(report.get("items") or [], key=lambda entry: entry.get("file", "")):
        output = Path(item["output"]) if item.get("output") else None
        text_sha = file_sha256(output) if output and output.is_file() else "missing"
        parts.append([item.get("file"), item.get("kind"), item.get("sha256"), text_sha])
    return sha256_bytes(json.dumps(parts, ensure_ascii=False).encode("utf-8"))


def materials_digest(project_dir: Path, state: dict) -> str:
    """登记的资源路径加上编目里每个文件此刻在磁盘上的指纹：补登、改文件、重新编目都会变。"""
    roots = sorted(str(item.get("path")) for item in state.get("resources") or [])
    index = load_json(project_dir / MATERIAL_INDEX_FILE, "公司资源编目")
    files = sorted(str(record.get("path")) for record in index.get("materials") or [])
    hashed = [[path, file_sha256(Path(path)) if Path(path).is_file() else "missing"] for path in files]
    return sha256_bytes(json.dumps([roots, hashed], ensure_ascii=False).encode("utf-8"))


# 确认时记下的输入指纹：(计算函数, 变化后的失效原因)
INPUT_DIGESTS = {
    "extraction": (lambda project_dir, state: extraction_digest(project_dir),
                   "确认后提取文本有变化（补遗或重新提取），须重新核对"),
    "rule_card": (lambda project_dir, state: rule_row_digests(load_json(project_dir / RULE_CARD_FILE, "规则卡")),
                  "确认后规则卡有变化，须按新规则卡重新核对"),
    "fact_card": (lambda project_dir, state: upstream_digests(FACT_INPUT, load_json(project_dir / FACT_CARD_FILE, "事实卡")),
                  "确认后事实卡有变化，引用的事实和清单数量须重新核对"),
    "materials": (materials_digest, "确认后公司资源资料有变化（补登、文件改动或重新编目），须重新核对"),
    "resource_card": (lambda project_dir, state: upstream_digests(RESOURCE_INPUT,
                                                                  load_json(project_dir / RESOURCE_CARD_FILE, "资源卡")),
                      "确认后资源卡有变化，引用的资源须重新核对"),
}
AFFECTED_SHOWN = 10  # 没写 cites 的行可能上百条，原因里只点前几行，全部在 affected


def input_digests(project_dir: Path, state: dict, names: tuple[str, ...]) -> dict:
    return {name: INPUT_DIGESTS[name][0](project_dir, state) for name in names}


def record_confirmation(project_dir: Path, state: dict, name: str, file: str, inputs: tuple[str, ...],
                        extra: dict | None = None) -> dict:
    """把卡片和它依赖的输入一起锁定；下游卡片另记每一行的指纹和依赖。"""
    record = {"file": file, "sha256": file_sha256(project_dir / file),
              "inputs": input_digests(project_dir, state, inputs), "confirmed_at": now_text(), **(extra or {})}
    if name in LOCKED_CARDS:
        record["rows"] = locked_rows(name, load_json(project_dir / file, "确认的卡片"))
    state.setdefault("cards", {})[name] = record
    return record


def stale_result(reason: str, affected: list[str]) -> dict:
    if not affected:
        return {"status": "stale", "reason": reason, "affected": []}
    shown = "、".join(affected[:AFFECTED_SHOWN])
    more = f" 等 {len(affected)} 行" if len(affected) > AFFECTED_SHOWN else ""
    return {"status": "stale", "reason": f"{reason}（涉及 {shown}{more}）", "affected": affected}


def edited_rows(project_dir: Path, name: str, record: dict) -> list[str]:
    """卡片读不出来时列不出行，失效照样成立。"""
    if name not in LOCKED_CARDS:
        return []
    try:
        return own_changes(name, load_json(project_dir / record["file"], "确认的卡片"), record.get("rows") or {})
    except ValueError:
        return []


def card_status(project_dir: Path, state: dict, name: str = "rule_card") -> dict:
    """confirmed / stale / unconfirmed，附原因；失效时 affected 列出受影响的行。门禁和阶段闸都按它判断。"""
    record = (state.get("cards") or {}).get(name)
    if not record:
        return {"status": "unconfirmed", "reason": "未确认"}
    path = project_dir / record["file"]
    if not path.is_file():
        return {"status": "stale", "reason": f"确认过的文件不存在: {record['file']}"}
    if file_sha256(path) != record["sha256"]:
        return stale_result("确认后被修改，须重新核对并请用户确认", edited_rows(project_dir, name, record))
    reasons, affected = [], []
    for input_name, recorded in record["inputs"].items():
        compute, reason = INPUT_DIGESTS[input_name]
        try:
            current = compute(project_dir, state)
        except ValueError as exc:
            return {"status": "stale", "reason": str(exc)}
        if isinstance(recorded, dict) and isinstance(current, dict):
            hit = affected_rows(record.get("rows") or {}, input_name, recorded, current)
            if hit:
                reasons.append(reason)
                affected += hit
        elif current != recorded:
            reasons.append(reason)
    if reasons:
        return stale_result("；".join(reasons), list(dict.fromkeys(affected)))
    return {"status": "confirmed", "reason": f"已确认（{record['confirmed_at']}）"}


def check_rule_card(project_dir: Path) -> dict:
    """校验并重出 MD 视图，不改状态。"""
    project_dir, state = load_project(project_dir)
    card = load_json(project_dir / RULE_CARD_FILE, "规则卡")
    issues = validate_rule_card(card, project_dir, state)
    views = write_rule_card_views(project_dir, card, state.get("project_name", ""), issues)
    return {"issues": issues, "views": [str(path) for path in views]}


def save_rule_snapshot(project_dir: Path) -> list[dict]:
    """把这次确认的规则卡存成快照，返回和上一次确认相比的逐行差异；第一次确认没有差异。"""
    card = load_json(project_dir / RULE_CARD_FILE, "规则卡")
    path = project_dir / RULE_SNAPSHOT_FILE
    changes = row_changes(load_json(path, "规则卡快照"), card) if path.is_file() else []
    path.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes


def confirm_rule_card(project_dir: Path) -> dict:
    """用户明确同意规则卡后才调用；有问题或阶段 1 未完成时拒绝。"""
    project_dir, state = load_project(project_dir)
    if state["stages"].get("1") != "done":
        raise ValueError("阶段 1 提取未完成，规则卡不能确认")
    result = check_rule_card(project_dir)
    if result["issues"]:
        raise ValueError(f"规则卡还有 {len(result['issues'])} 个问题，不能确认：{result['issues'][0]}")
    changes = save_rule_snapshot(project_dir)
    record_confirmation(project_dir, state, "rule_card", RULE_CARD_FILE, ("extraction",))
    if state["stages"].get("2") == "pending":
        state["stages"]["2"] = "in-progress"
    save_state(project_dir, state)
    return {"project": str(project_dir), "rule_card": "confirmed", "views": result["views"], "row_changes": changes}
