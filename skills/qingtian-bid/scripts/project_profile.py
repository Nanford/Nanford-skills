"""Project profile and trigger table of qingtian-bid: what a tender turns on, worked out from the rule card.

INPUT: a rule card dict (profile, evaluation_method, track, blind_clause, checkboxes, key_dates, bid_forms,
       project_category); analysis/extraction-report.json for response samples; the clock for the 澄清 window.
OUTPUT: PROFILE_KINDS for the scaffold; check_profile() for validate_rule_card; trigger_rows() and profile_sections()
        for rule-card.md.
POS: card layer beside rule_card_fields.py, imported by project_cards.py and scaffold_rule_fields.py. It only lists what
     a tender turns on; the work lands in the matching stage. The four "须告知用户" rows are the exception: this Skill's
     rules do not cover them, so stage 2 stops until the user's own words are written down (不代写，决策 4c-3A).
     地区 is not repeated here: qingtian.rule_scope already holds it (决策 D11).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from rule_card_fields import (
    DEADLINE_FORMATS,
    UNSPECIFIED,
    RefLookup,
    cell,
    field_head,
    has_text,
    is_empty,
    ref_issues,
    ref_text,
    rows_of,
    table_lines,
)


AWARD_MODE, SUBMISSION, PROCUREMENT_SYSTEM, PROCUREMENT_METHOD = "定标方式", "递交方式", "采购体系", "采购方式"
SME_ONLY, ENERGY_SAVING, CERTIFICATE_CHECK, SITE_LIMIT = "专门面向中小企业", "节能产品", "证书查询验证", "现场限制"
# 后四项招标文件没提到是常态：写了原文就算命中，所以每个都占一行，分得清是没写还是没找
PROFILE_KINDS = (AWARD_MODE, SUBMISSION, PROCUREMENT_SYSTEM, PROCUREMENT_METHOD,
                 SME_ONLY, ENERGY_SAVING, CERTIFICATE_CHECK, SITE_LIMIT)
CLARIFY_DEADLINE = "澄清截止"
RETROFIT_SCENARIO = "既有设施改造"
HIT, UNCLEAR = "命中", "判不清"
OPTION_CLOSED = ("不", "否", "无")
Outcome = tuple[str, str] | None


@dataclass
class Facts:
    """算触发项要读的东西。project_dir 为 None 时不看响应样本（只出视图的调用没有项目目录）。"""

    card: dict
    project_dir: Path | None
    now: datetime

    def value(self, name: str) -> object:
        entry = self.card.get(name)
        return entry.get("value") if isinstance(entry, dict) else None

    def profile_row(self, kind: str) -> dict | None:
        return next((row for row in rows_of(self.card.get("profile") or {}) if row.get("kind") == kind), None)

    def profile_text(self, kind: str) -> str:
        """写了"招标文件未规定"的行，text 不算数。"""
        row = self.profile_row(kind)
        if not row or row.get("basis") == UNSPECIFIED or not has_text(row.get("text")):
            return ""
        return str(row["text"])


@dataclass(frozen=True)
class Trigger:
    name: str
    action: str
    check: Callable[[Facts], Outcome]
    notice_kind: str | None = None  # 须告知用户的触发项：用户的决定写在画像这一行


# ---------- 各触发项怎么算 ----------

def method_is(*names: str) -> Callable[[Facts], Outcome]:
    def check(facts: Facts) -> Outcome:
        method = facts.value("evaluation_method")
        return (HIT, f"评标办法：{method}") if method in names else None
    return check


def blind_bid(facts: Facts) -> Outcome:
    if facts.value("track") == "T-暗标":
        return HIT, "评审轨道 T-暗标"
    return (HIT, "规则卡有暗标条款") if not is_empty(facts.value("blind_clause")) else None


def deviation_table(facts: Facts) -> Outcome:
    for row in rows_of(facts.card.get("bid_forms") or {}):
        parts = row.get("parts") if isinstance(row.get("parts"), list) else []
        titles = [row.get("title"), *[part.get("title") for part in parts if isinstance(part, dict)]]
        if any("偏离表" in str(title) for title in titles):
            return HIT, f"投标文件格式 {row.get('id')}“{row.get('title')}”"
    return None


def ticked_options(row: dict) -> list[str]:
    options = row.get("options") if isinstance(row.get("options"), list) else []
    return [str(item.get("text")) for item in options if isinstance(item, dict) and item.get("checked")]


def subcontract_or_joint(facts: Facts) -> Outcome:
    """勾"允许""接受"的算有；两项里有读不到、没勾或多勾的，不猜，列出来核对。"""
    rows = rows_of(facts.card.get("checkboxes") or {})
    found = {name: [row for row in rows if name in str(row.get("label"))] for name in ("分包", "联合体")}
    opened = [row for group in found.values() for row in group
              if len(ticked_options(row)) == 1 and not ticked_options(row)[0].startswith(OPTION_CLOSED)]
    if opened:
        return HIT, "；".join(f"{row.get('id')} {row.get('label')}：{ticked_options(row)[0]}" for row in opened)
    missing = [name for name, group in found.items() if not group]
    unclear = [str(row.get("id")) for group in found.values() for row in group if len(ticked_options(row)) != 1]
    if missing or unclear:
        return UNCLEAR, f"勾选框里没读到：{'、'.join(missing) or '无'}；没勾或多勾：{'、'.join(unclear) or '无'}"
    return None


def profile_says(kind: str, pattern: str = "") -> Callable[[Facts], Outcome]:
    """画像这一行写了原文就算命中；给了 pattern 的，原文里要有这些字。"""
    def check(facts: Facts) -> Outcome:
        text = facts.profile_text(kind)
        if not text or (pattern and not re.search(pattern, text)):
            return None
        return HIT, f"{kind}：{text}"
    return check


def clarify_deadline(facts: Facts) -> tuple[datetime | None, str]:
    """只写到日的，算到当天结束。"""
    row = next((row for row in rows_of(facts.card.get("key_dates") or {}) if row.get("kind") == CLARIFY_DEADLINE), None)
    deadline = str((row or {}).get("deadline") or "")
    for pattern in DEADLINE_FORMATS:
        try:
            parsed = datetime.strptime(deadline, pattern)
        except ValueError:
            continue
        return (parsed if " " in deadline else parsed.replace(hour=23, minute=59)), deadline
    return None, deadline


def clarify_open(facts: Facts) -> Outcome:
    deadline, text = clarify_deadline(facts)
    if deadline is None:
        return UNCLEAR, "规则卡没有澄清截止时间：招标文件没写的，问用户窗口开没开"
    return (HIT, f"澄清截止 {text}") if facts.now <= deadline else None


def clarify_closed(facts: Facts) -> Outcome:
    deadline, text = clarify_deadline(facts)
    return (HIT, f"澄清截止 {text} 已过") if deadline is not None and facts.now > deadline else None


def response_sample(facts: Facts) -> Outcome:
    if facts.project_dir is None:
        return None
    try:
        report = json.loads((facts.project_dir / "analysis" / "extraction-report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    samples = [str(item.get("file")) for item in report.get("items") or []
               if item.get("kind") == "sample" and item.get("status") == "ok"]
    return (HIT, f"响应样本 {len(samples)} 份") if samples else None


def site_limit(facts: Facts) -> Outcome:
    category = facts.value("project_category")
    scenarios = category.get("scenarios") if isinstance(category, dict) else None
    if isinstance(scenarios, list) and RETROFIT_SCENARIO in scenarios:
        return HIT, f"工程场景：{RETROFIT_SCENARIO}"
    return profile_says(SITE_LIMIT)(facts)


NOT_COVERED = "本 Skill 的规则按招标投标体系写，这一项没有覆盖。硬停告知用户，用户决定怎么继续"
TRIGGERS = (
    Trigger("技术评分合理价格法（T-AI）、动态合理价格法（T-合格）", "默认全流程，v2.0 完整覆盖",
            method_is("技术评分合理价格法", "动态合理价格法")),
    Trigger("综合评估法", "施组和初评对账照做；商务评分资料由第 5b 步覆盖", method_is("综合评估法")),
    Trigger("定性定量（T-定档）", "施组和初评对账照做；定级和定标部分由第 5b 步覆盖", method_is("定性定量评审法")),
    Trigger("暗标条款（T-暗标）", "身份词表必填；按暗标条款统一格式；暗标部分与商务物理分开", blind_bid),
    Trigger("投标文件格式有偏离表", "偏离表不留空项", deviation_table),
    Trigger("有分包或联合体", "分包表、联合体协议按投标文件格式做；拟分包“预计造价”转待确认", subcontract_or_joint),
    Trigger("证书需要查询验证", "自行查询的结果进“其他材料”窗口清单", profile_says(CERTIFICATE_CHECK)),
    Trigger("澄清窗口开着", "把差异和疑点列出，提醒在线提出，给出截止时间", clarify_open),
    Trigger("澄清窗口已关", "电话咨询记录在案，标【推断】，用户决定；提交前刷新系统", clarify_closed),
    Trigger("有响应样本", "写对照要点，不抄事实", response_sample),
    Trigger("现场有限制（改造、多现场）", "限制写入事实卡，正文不得违反（W10）", site_limit),
    Trigger("政府采购", NOT_COVERED, profile_says(PROCUREMENT_SYSTEM, "政府采购"), PROCUREMENT_SYSTEM),
    Trigger("专门面向中小企业", NOT_COVERED, profile_says(SME_ONLY), SME_ONLY),
    Trigger("节能产品", NOT_COVERED, profile_says(ENERGY_SAVING), ENERGY_SAVING),
    Trigger("竞争性磋商", NOT_COVERED, profile_says(PROCUREMENT_METHOD, "磋商"), PROCUREMENT_METHOD),
)


def trigger_rows(card: dict, project_dir: Path | None = None, now: datetime | None = None) -> list[dict]:
    """命中和判不清的才列；没命中的不占地方。"""
    facts = Facts(card, project_dir, now or datetime.now())
    rows: list[dict] = []
    for trigger in TRIGGERS:
        outcome = trigger.check(facts)
        if outcome:
            rows.append({"name": trigger.name, "state": outcome[0], "evidence": outcome[1], "action": trigger.action,
                         "notice_kind": trigger.notice_kind})
    return rows


# ---------- 校验 ----------

def profile_row_issues(row: dict, label: str, lookup: RefLookup) -> list[str]:
    issues = [] if row.get("kind") in PROFILE_KINDS else [f"{label}：kind 只能是 {'、'.join(PROFILE_KINDS)}"]
    if row.get("basis") == UNSPECIFIED:
        return issues + ([f"{label}：写了“招标文件未规定”就不能再写 text、ref"]
                         if has_text(row.get("text")) or row.get("ref") else [])
    if not has_text(row.get("text")):
        issues.append(f"{label}：缺少原文 text；招标文件确实没写的，这一行的 basis 写“招标文件未规定”")
    return issues + ref_issues(row.get("ref"), label, lookup)


def profile_rows_issues(rows: list[object], lookup: RefLookup) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    for position, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            issues.append(f"项目画像第 {position} 行应为对象")
            continue
        row_id = str(row.get("id") or "")
        if not re.fullmatch(r"PF\d{2,}", row_id) or row_id in seen:
            issues.append(f"项目画像第 {position} 行的编号须为 PF01 这样且不重复（当前: {row_id or '空'}）")
        seen.add(row_id)
        issues += profile_row_issues(row, f"项目画像 {row_id or position}", lookup)
    kinds = [row.get("kind") for row in rows if isinstance(row, dict)]
    issues += [f"项目画像缺“{kind}”这一行；招标文件确实没写的，这一行的 basis 写“招标文件未规定”"
               for kind in PROFILE_KINDS if kind not in kinds]
    return issues + [f"项目画像“{kind}”重复了" for kind in PROFILE_KINDS if kinds.count(kind) > 1]


def notice_issues(card: dict) -> list[str]:
    """须告知用户的命中了，要有用户的原话才能往下走。"""
    facts = Facts(card, None, datetime.now())
    issues: list[str] = []
    for trigger in TRIGGERS:
        if trigger.notice_kind and trigger.check(facts) \
                and not has_text((facts.profile_row(trigger.notice_kind) or {}).get("user_decision")):
            issues.append(f"项目画像：招标文件命中“{trigger.name}”。硬停：{NOT_COVERED}；用户原话写进“{trigger.notice_kind}”"
                          "这一行的 user_decision")
    return issues


def check_profile(card: dict, project_dir: Path) -> list[str]:
    """写了未规定或还是空的，check_ref_entry 已经报过。"""
    rows = card["profile"].get("value")
    if card["profile"].get("basis") == UNSPECIFIED or is_empty(rows):
        return []
    if not isinstance(rows, list):
        return ["项目画像应为列表"]
    return profile_rows_issues(rows, RefLookup(project_dir)) + notice_issues(card)


# ---------- 视图 ----------

def profile_cells(row: dict) -> list[str]:
    return [cell(row.get("id")), cell(row.get("kind")), cell(row.get("text") or row.get("basis")),
            ref_text(row.get("ref")), cell(row.get("user_decision"))]


def trigger_cells(row: dict) -> list[str]:
    return [cell(row["name"]), cell(row["state"]), cell(row["evidence"]), cell(row["action"])]


def profile_sections(card: dict, project_dir: Path | None = None, now: datetime | None = None) -> list[str]:
    """rule-card.md 的第八节。只列命中项，做法在对应步骤落地。"""
    rows = trigger_rows(card, project_dir, now)
    notices = [f"- **{row['name']}**：{row['evidence']}。{row['action']}" for row in rows if row["notice_kind"]]
    return [*field_head("profile", card["profile"]),
            *table_lines(("编号", "事项", "原文", "定位", "用户决定"),
                         [profile_cells(row) for row in rows_of(card["profile"])]),
            *(["### 须告知用户", "", *notices, ""] if notices else []),
            "### 这个项目命中的触发项", "",
            *table_lines(("触发项", "状态", "依据", "必做"), [trigger_cells(row) for row in rows])]
