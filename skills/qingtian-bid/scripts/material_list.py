"""Stage-2 资料清单初版 of qingtian-bid: what to ask the company for and what to check, from the confirmed rule card.

INPUT: analysis/rule-card.json once confirmed (qualification, bid_forms, checkboxes, off_table, profile), through
       project_cards. Nothing else: no fact card, no resource card, no company data.
OUTPUT: material_rows() for the 对账表 of step 3; analysis/资料清单.md (a generated view, never edited by hand);
        confirm_and_list() for project_status --confirm rule-card; a CLI that writes the list again.
POS: stage-2 output, on top of project_cards.py, which must not import it. Every row cites the rule card rows it came
     from. The list holds no amounts and no personal data: an amount in a clause becomes a pointer to the card row.
     Row-by-row reconciliation against the 初步评审表 and the local file names belong to the 对账表 (step 3).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bid_forms_fields import FILLED_FIELDS, NOT_REQUIRED
from project_cards import RULE_CARD_FILE, card_status, confirm_rule_card, load_json, load_project
from project_profile import CERTIFICATE_CHECK, OPTION_CLOSED, SUBMISSION, Facts, ticked_options
from rule_card_fields import cell, compact, ref_text, rows_of, table_lines
from scan_bid_forms import CONDITIONAL_TITLE


MATERIAL_LIST_FILE = "analysis/资料清单.md"
REQUIRED, CONDITIONAL, SELF_CHECK, NOT_NEEDED = "向公司要的资料", "按需才要的", "公司自查，不进投标文件", "不用要的"
# 分组和说明，按这个顺序出
GROUPS = ((REQUIRED, "公司给齐，再按“校验什么”核一遍。"),
          (CONDITIONAL, "先定要不要：招标文件写了“如有”“如要求”，或勾选框打开了这一项。"),
          (SELF_CHECK, "这些不交，但查出问题可能废标或不被推荐。"),
          (NOT_NEEDED, "招标文件有这一节，依据写在“校验什么”里，不用向公司要。"))
TECH_FILE, PRICE_FILE = "技术", "报价"
BODY_KIND, ATTACHMENT_KIND = "正文", "附件"
# 勾选框打开后才要的材料。"是否要求"是为了不把"免缴""履约保证金"那几行算进来
BOX_MATERIALS = ((r"分包", "分包计划"), (r"联合体", "联合体协议"), (r"是否要求.*投标保证金", "投标保证金凭证"))

CN_DIGITS = "零壹贰叁肆伍陆柒捌玖拾佰仟一二三四五六七八九十百千两"
AMOUNT = re.compile(
    rf"(?:人民币|[￥¥])\s*[\d,，.{CN_DIGITS}万亿]+\s*元?"
    rf"|(?:[\d,，.]+\s*[-~～至到]\s*)?[\d,，.]+\s*(?:(?:亿|万)?元|(?:亿|万)(?![平方米人吨㎡]))"
    rf"|[{CN_DIGITS}][{CN_DIGITS}万亿]*元")  # 至少一个数字："单位：万元"不是金额
PERSONAL = re.compile(r"(?<![\d])(?:1[3-9]\d{9}|\d{17}[\dXx]|0\d{2,3}-?\d{7,8})(?![\d])|[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass
class MaterialRow:
    group: str
    item: str
    check: str
    used_in: str
    cites: list[str]
    where: str = "—"


def scrubbed(text: str, cite: str) -> str:
    """清单会传给公司不同的人，金额和个人信息不跟着走；门槛金额到规则卡这一行查。"""
    return PERSONAL.sub("【个人信息已略】", AMOUNT.sub(f"【金额见规则卡 {cite}】", text))


# ---------- 从规则卡各字段出行 ----------

def qualification_rows(card: dict) -> list[MaterialRow]:
    """资格条款一项要求一行：资料是证明这个评审因素的材料，校验的就是这项要求。"""
    return [MaterialRow(REQUIRED, str(row.get("factor")), str(requirement), "资格评审", [str(row.get("id"))],
                        ref_text(row.get("ref")))
            for row in rows_of(card["qualification"]) for requirement in row.get("requirements") or []]


def section_label(row: dict) -> str:
    number = f"{row['number']}、" if row.get("number") else ""
    return f"{row.get('file')}文件 {number}{row.get('title')}"


def part_check(row: dict, part: dict) -> str | None:
    """这个小节本身要什么；None 表示只要它列出的附件。技术文件的正文是施组线的事，向公司要素材走资源卡。"""
    kind, attachments = part.get("kind"), part.get("attachments")
    if kind == FILLED_FIELDS:
        return f"要填：{'、'.join(str(name) for name in part.get('fields') or [])}"
    if kind == BODY_KIND and row.get("file") != TECH_FILE:
        return "正文要写，内容问公司"
    return "按这一节的要求附上" if kind == ATTACHMENT_KIND and not attachments else None


def part_rows(row: dict, part: dict) -> list[MaterialRow]:
    title, part_id, used_in = str(part.get("title")), str(part.get("id")), section_label(row)
    where = ref_text(part.get("ref") or row.get("ref"))
    if part.get("kind") == NOT_REQUIRED:
        return [MaterialRow(NOT_NEEDED, title, f"依据：{part.get('not_required_basis')}", used_in, [part_id], where)]
    group = CONDITIONAL if CONDITIONAL_TITLE.search(title) else REQUIRED
    own = part_check(row, part)
    rows = [MaterialRow(group, title, own, used_in, [part_id], where)] if own else []
    return rows + [MaterialRow(group, str(attachment), "按这一节的要求附上", used_in, [part_id], where)
                   for attachment in part.get("attachments") or []]


def parts_of(row: dict) -> list[dict]:
    parts = row.get("parts")
    return [part for part in parts if isinstance(part, dict)] if isinstance(parts, list) else []


def form_material_rows(card: dict) -> list[MaterialRow]:
    """报价文件的表是造价软件出的，向公司要不到一张张表，也不该在这里露金额，所以合成一行。"""
    rows: list[MaterialRow] = []
    priced: list[dict] = []
    for row in rows_of(card["bid_forms"]):
        is_price = row.get("file") == PRICE_FILE
        needed = [part for part in parts_of(row) if part.get("kind") != NOT_REQUIRED]
        if is_price and needed:
            priced.append(row)
        for part in parts_of(row):
            if not is_price or part.get("kind") == NOT_REQUIRED:
                rows += part_rows(row, part)
    if priced:
        total = sum(1 for row in priced for part in parts_of(row) if part.get("kind") != NOT_REQUIRED)
        rows.append(MaterialRow(REQUIRED, "报价文件（造价软件出）", f"按投标文件格式的 {total} 个小节出全，金额不进这份清单",
                                "报价文件", [str(row.get("id")) for row in priced], ref_text(priced[0].get("ref"))))
    return rows


def box_rows(card: dict) -> list[MaterialRow]:
    """勾"不允许""不要求"的没有这份材料；投标文件格式还有这一节的，那一节自己写无需提供和依据。"""
    rows: list[MaterialRow] = []
    for row in rows_of(card["checkboxes"]):
        label = str(row.get("label"))
        ticked = ticked_options(row)
        if len(ticked) == 1 and ticked[0].startswith(OPTION_CLOSED):
            continue
        state = ticked[0] if len(ticked) == 1 else f"勾了 {len(ticked)} 个，先问清楚"
        rows += [MaterialRow(CONDITIONAL, material, f"{label}：{state}", "按投标文件格式", [str(row.get("id"))],
                             ref_text(row.get("ref")))
                 for pattern, material in BOX_MATERIALS if re.search(pattern, label)]
    return rows


def profile_rows(card: dict) -> list[MaterialRow]:
    facts = Facts(card, None, datetime.now())
    rows: list[MaterialRow] = []
    certificate = facts.profile_text(CERTIFICATE_CHECK)
    if certificate:
        row = facts.profile_row(CERTIFICATE_CHECK) or {}
        rows.append(MaterialRow(CONDITIONAL, "证书查询验证结果", certificate, "其他材料窗口", [str(row.get("id"))],
                                ref_text(row.get("ref"))))
    submission = facts.profile_text(SUBMISSION)
    if "电子" in submission:
        row = facts.profile_row(SUBMISSION) or {}
        rows.append(MaterialRow(REQUIRED, "数字证书、电子印章和制作工具", f"有效期盖住投标截止；递交方式：{submission}", "全部盖章处和加密",
                                [str(row.get("id"))], ref_text(row.get("ref"))))
    return rows


def off_table_rows(card: dict) -> list[MaterialRow]:
    return [MaterialRow(SELF_CHECK, str(row.get("kind")), str(row.get("text")), "不进投标文件", [str(row.get("id"))],
                        ref_text(row.get("ref")))
            for row in rows_of(card["off_table"])]


def merged(rows: list[MaterialRow]) -> list[MaterialRow]:
    """同一份资料用在几处，要一次就够，所以合成一行，出处都留着。"""
    kept: dict[tuple[str, str, str], MaterialRow] = {}
    for row in rows:
        key = (row.group, compact(row.item), compact(row.check))
        if key not in kept:
            kept[key] = row
            continue
        into = kept[key]
        into.cites += [cite for cite in row.cites if cite not in into.cites]
        if row.used_in not in into.used_in:
            into.used_in = f"{into.used_in}；{row.used_in}"
    return list(kept.values())


def material_rows(card: dict) -> list[MaterialRow]:
    """按分组排好；同组内保持规则卡的顺序。"""
    rows = merged(qualification_rows(card) + form_material_rows(card) + box_rows(card) + profile_rows(card)
                  + off_table_rows(card))
    for row in rows:
        row.item = scrubbed(row.item, row.cites[0])
        row.check = scrubbed(row.check, row.cites[0])
        row.used_in = scrubbed(row.used_in, row.cites[0])
    order = {name: at for at, (name, _) in enumerate(GROUPS)}
    return sorted(rows, key=lambda row: order[row.group])


# ---------- 视图 ----------

def group_lines(rows: list[MaterialRow], start: int) -> list[str]:
    cells = [[f"M{at:02d}", cell(row.item), cell(row.check), cell(row.used_in), cell("、".join(row.cites)), row.where]
             for at, row in enumerate(rows, start)]
    return table_lines(("编号", "资料", "校验什么", "用在哪", "规则卡的行", "原文定位"), cells) if cells else ["无。", ""]


def render_material_list(rows: list[MaterialRow], project_name: str, confirmed_at: str) -> str:
    lines = [f"# 资料清单初版（{project_name}）", "",
             f"> 由规则卡生成（规则卡确认于 {confirmed_at}），改清单请改规则卡，重新确认后会重出。规则卡失效了，这份也作废。",
             "> 只说向公司要什么、校验什么。逐行对账和回填文件名在第 3 步的对账表。",
             "> 不含金额和个人信息：条款里的金额换成了指向规则卡的记号，到 `rule-card.md` 查这一行。", ""]
    start = 1
    for at, (name, note) in enumerate(GROUPS, 1):
        chosen = [row for row in rows if row.group == name]
        lines += [f"## {'一二三四'[at - 1]}、{name}（{len(chosen)} 项）", "", note, "", *group_lines(chosen, start)]
        start += len(chosen)
    return "\n".join(lines)


def write_material_list(project_dir: Path) -> Path:
    """规则卡确认后才出：没确认的卡里有草稿和候选，不能拿去向公司要资料。"""
    project_dir, state = load_project(project_dir)
    status = card_status(project_dir, state)
    if status["status"] != "confirmed":
        raise ValueError(f"规则卡{status['reason']}，确认后才出资料清单")
    card = load_json(project_dir / RULE_CARD_FILE, "规则卡")
    path = project_dir / MATERIAL_LIST_FILE
    confirmed_at = state["cards"]["rule_card"]["confirmed_at"]
    path.write_text(render_material_list(material_rows(card), state.get("project_name", ""), confirmed_at),
                    encoding="utf-8")
    return path


def confirm_and_list(project_dir: Path) -> dict:
    """用户明确同意规则卡后调用（project_status --confirm rule-card）：确认一次，清单就跟着新卡重出一次。"""
    result = confirm_rule_card(project_dir)
    return {**result, "material_list": str(write_material_list(project_dir))}


def main() -> int:
    parser = argparse.ArgumentParser(description="按已确认的规则卡重出 analysis/资料清单.md。")
    parser.add_argument("project_dir", type=Path, help="项目目录")
    args = parser.parse_args()
    try:
        print(f"已生成: {write_material_list(args.project_dir)}")
    except (OSError, ValueError) as exc:
        print(f"资料清单生成失败: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
