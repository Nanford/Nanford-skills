"""Rule card fields located row by row with a ref: their validation, the lookup back into the text, their views.

INPUT: a rule card dict; analysis/extraction-report.json and the extracted texts it lists, read through tender_text.
OUTPUT: REF_FIELDS for project_cards.RULE_FIELDS; check_ref_entry() for the rules every field shares;
        check_ref_fields() for the rows and their refs (资格条款、勾选框、关键日期、表外致命项、定标规则、最高投标限价);
        ref_sections() for rule-card.md; the small helpers is_empty() and cell(), which project_cards re-exports.
POS: card layer beneath project_cards.py, which imports this module, so nothing here may import project_cards;
     bid_forms_fields.py sits on top of it for the 投标文件格式 fields, whose rows are checked there.
     The rows feed later steps: the trigger table (project_profile), the 商务 stages and the 资料清单.

临时方案（决策 3A）：这些新字段的出处逐行写 ref，老字段还是 entry 级的 source，两种写法并存。
替换路径：v2.1 把老字段迁到 ref，迁完删掉 source 那条分支。

ref 是 {file, page, line, keyword}：回到提取文本里按行号找关键词，查不到就报错。这样出处写错、补遗后文本变了都
过不了校验，不靠人记得回头看。
"""

from __future__ import annotations

import json
import re
from bisect import bisect_left, bisect_right
from datetime import datetime
from pathlib import Path
from typing import Callable

from tender_text import REF_WINDOW, TextIndex, build_index


TENDER_BASIS = "招标文件"
UNSPECIFIED = "招标文件未规定"
REF_BASES = (TENDER_BASIS, UNSPECIFIED)
# (字段, 中文名, 必填规则)，规则的含义同 project_cards.RULE_FIELDS
REF_FIELDS = (
    ("qualification", "资格条款", "required"),
    ("checkboxes", "勾选框原文", "optional"),
    ("key_dates", "关键日期", "required"),
    ("off_table", "表外致命项", "optional"),
    ("award", "定标规则", "optional"),
    ("price_limit", "最高投标限价", "optional"),
    ("bid_forms", "投标文件格式", "required"),  # 这两个的逐行校验在 bid_forms_fields.py
    ("bid_forms_diff", "目录和正文的差异", "optional"),
    ("profile", "项目画像", "required"),  # 逐行校验在 project_profile.py
)
REF_FIELD_LABELS = {name: label for name, label, _ in REF_FIELDS}
REF_FIELD_RULES = {name: rule for name, _, rule in REF_FIELDS}
ROW_PREFIXES = {"qualification": "QU", "checkboxes": "CB", "key_dates": "KD", "off_table": "OT", "award": "AW"}
SUBMIT_DEADLINE = "投标截止"
KEY_DATE_KINDS = (SUBMIT_DEADLINE, "澄清截止", "异议截止", "询标时限")
DEADLINE_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d")
MIN_KEYWORD_CHARS = 2


def is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def cell(value: object) -> str:
    """Markdown 表格单元：竖线转义，换行改 <br>。"""
    if is_empty(value):
        return "—"
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def compact(text: object) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def text_list_ok(value: object) -> bool:
    return isinstance(value, list) and all(has_text(item) for item in value)


# ---------- ref 回查 ----------

def tender_outputs(project_dir: Path) -> dict[str, Path]:
    """提取报告里的招标文件文本：文件名 -> 提取文本。图纸、响应样本不能当规则的出处。"""
    try:
        report = json.loads((project_dir / "analysis" / "extraction-report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {Path(item["file"]).name: Path(item["output"]) for item in report.get("items") or []
            if item.get("kind", "tender") == "tender" and item.get("status") == "ok" and item.get("output")}


class RefLookup:
    """用到才读提取文本，一次校验里每个文件只读一遍。"""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.outputs: dict[str, Path] | None = None
        self.indexes: dict[str, TextIndex | None] = {}

    def index(self, file_name: str) -> TextIndex | None:
        if self.outputs is None:
            self.outputs = tender_outputs(self.project_dir)
        if file_name not in self.indexes:
            output = self.outputs.get(file_name)
            try:
                self.indexes[file_name] = build_index(file_name, output.read_text(encoding="utf-8")) if output else None
            except OSError:
                self.indexes[file_name] = None
        return self.indexes[file_name]


def keyword_found(index: TextIndex, line_index: int, keyword: str) -> bool:
    """按原始行找，也按连续文本找：一句话被页眉、页码隔开时，只有连续文本里是连着的。"""
    raw = compact("".join(index.lines[line_index:line_index + REF_WINDOW]))
    start = bisect_left(index.offsets, line_index)
    end = bisect_right(index.offsets, line_index + REF_WINDOW - 1)
    return keyword in raw or keyword in index.flat[start:end]


def ref_issues(ref: object, label: str, lookup: RefLookup) -> list[str]:
    if not isinstance(ref, dict):
        return [f"{label}：缺少原文定位 ref（file、page、line、keyword）"]
    file_name, line, keyword = ref.get("file"), ref.get("line"), compact(ref.get("keyword"))
    if not has_text(file_name) or not isinstance(line, int) or isinstance(line, bool) or line < 1 \
            or len(keyword) < MIN_KEYWORD_CHARS:
        return [f"{label}：ref 须含文件名 file、行号 line（1 起）和原文关键词 keyword（至少 {MIN_KEYWORD_CHARS} 个字）"]
    index = lookup.index(file_name)
    if index is None:
        return [f"{label}：定位的文件 {file_name} 不在提取报告的招标文件里"]
    if line > len(index.lines):
        return [f"{label}：定位的第 {line} 行超出 {file_name} 的行数（{len(index.lines)}）"]
    page = index.pages[line - 1] or None
    if (ref.get("page") or None) != page:
        return [f"{label}：定位写的是第 {ref.get('page')} 页，{file_name} 第 {line} 行实际在第 {page} 页"]
    if not keyword_found(index, line - 1, keyword):
        return [f"{label}：在 {file_name} 第 {line} 行起 {REF_WINDOW} 行里查不到“{keyword}”：定位写错了，或提取文本变了，回原文核对"]
    return []


# ---------- 字段的公共规则 ----------

def check_ref_entry(name: str, entry: object) -> list[str]:
    """同 project_cards.check_entry，只是没有 entry 级的 source。这些都是本项目自己的取值，不接受"示范文本默认"。"""
    label = REF_FIELD_LABELS[name]
    if not isinstance(entry, dict) or not {"value", "basis", "checked"} <= set(entry):
        return [f"{label}：字段结构不完整（须含 value、basis、checked）"]
    issues = [] if entry["checked"] is True else [f"{label}：待核对（对照招标文件原文核实后把 checked 改为 true）"]
    if entry["basis"] not in REF_BASES:
        return issues + [f"{label}：是本项目自己的取值，依据只能是 {'、'.join(REF_BASES)}"]
    if entry["basis"] == UNSPECIFIED:
        if REF_FIELD_RULES[name] == "required":
            issues.append(f"{label}：必须从招标文件找到，不能写“招标文件未规定”；确实没有时硬停，问用户")
        elif not is_empty(entry["value"]):
            issues.append(f"{label}：写了“招标文件未规定”就不能再填值")
        return issues
    if is_empty(entry["value"]):
        issues.append(f"{label}：缺少内容")
    return issues


# ---------- 各字段的行 ----------

def qualification_row_issues(row: dict, label: str, lookup: RefLookup) -> list[str]:
    issues = [f"{label}：缺少{name}" for key, name in (("factor", "评审因素 factor"), ("text", "条款原文 text"))
              if not has_text(row.get(key))]
    if not text_list_ok(row.get("pointer_chain")):
        issues.append(f"{label}：pointer_chain 写顺着“见……”一路找到原文的路径，是文字列表；原文就在这里的写空列表")
    if not row.get("requirements") or not text_list_ok(row.get("requirements")):
        issues.append(f"{label}：requirements 把这一条拆成逐项要求，是文字列表，不能为空")
    return issues + ref_issues(row.get("ref"), label, lookup)


def checkbox_row_issues(row: dict, label: str, lookup: RefLookup) -> list[str]:
    issues = [] if has_text(row.get("label")) else [f"{label}：缺少条款名称 label"]
    options = row.get("options")
    if not isinstance(options, list) or not options or not all(
            isinstance(item, dict) and has_text(item.get("text")) and isinstance(item.get("checked"), bool)
            for item in options):
        return issues + [f"{label}：options 每项须含原文 text 和是否勾选 checked"] + ref_issues(row.get("ref"), label, lookup)
    ticked = sum(item["checked"] for item in options)
    if row.get("count") != ticked:
        issues.append(f"{label}：count 写的是 {row.get('count')}，实际勾了 {ticked} 个")
    # 真实招标文件有两个都没勾的：这是招标文件的疑点，不能猜，要留痕
    if ticked != 1 and not has_text(row.get("note")):
        issues.append(f"{label}：勾了 {ticked} 个：对照原文在 note 写明（多选的照录；没勾的是疑点，列给用户）")
    return issues + ref_issues(row.get("ref"), label, lookup)


def deadline_ok(value: object) -> bool:
    if not isinstance(value, str):
        return False
    for pattern in DEADLINE_FORMATS:
        try:
            datetime.strptime(value, pattern)
            return True
        except ValueError:
            continue
    return False


def key_date_row_issues(row: dict, label: str, lookup: RefLookup) -> list[str]:
    kind = row.get("kind")
    issues = [] if kind in KEY_DATE_KINDS else [f"{label}：kind 只能是 {'、'.join(KEY_DATE_KINDS)}"]
    if row.get("basis") == UNSPECIFIED:
        if kind == SUBMIT_DEADLINE:
            issues.append(f"{label}：投标截止时间必须从招标文件找到；确实没有时硬停，问用户")
        elif has_text(row.get("text")) or row.get("ref"):
            issues.append(f"{label}：写了“招标文件未规定”就不能再写 text、ref")
        return issues
    if not has_text(row.get("text")):
        issues.append(f"{label}：缺少原文 text；招标文件确实没写的，这一行的 basis 写“招标文件未规定”")
    if kind == SUBMIT_DEADLINE and not deadline_ok(row.get("deadline")):
        issues.append(f"{label}：投标截止要把 deadline 写成 YYYY-MM-DD HH:MM")
    elif row.get("deadline") and not deadline_ok(row.get("deadline")):
        issues.append(f"{label}：deadline 写成 YYYY-MM-DD HH:MM 或 YYYY-MM-DD，只有相对时限的留空")
    return issues + ref_issues(row.get("ref"), label, lookup)


def off_table_row_issues(row: dict, label: str, lookup: RefLookup) -> list[str]:
    issues = [f"{label}：缺少{name}" for key, name in (("kind", "事项 kind"), ("text", "条款原文 text"))
              if not has_text(row.get(key))]
    return issues + ref_issues(row.get("ref"), label, lookup)


def award_row_issues(row: dict, label: str, lookup: RefLookup) -> list[str]:
    issues = [] if has_text(row.get("text")) else [f"{label}：缺少条款原文 text"]
    return issues + ref_issues(row.get("ref"), label, lookup)


ROW_CHECKS: dict[str, Callable[[dict, str, RefLookup], list[str]]] = {
    "qualification": qualification_row_issues,
    "checkboxes": checkbox_row_issues,
    "key_dates": key_date_row_issues,
    "off_table": off_table_row_issues,
    "award": award_row_issues,
}


def check_rows(name: str, entry: dict, lookup: RefLookup) -> list[str]:
    """逐行查编号和内容。写了未规定或还是空的，check_ref_entry 已经报过，这里不再重复。"""
    rows = entry.get("value")
    if entry.get("basis") == UNSPECIFIED or is_empty(rows):
        return []
    label = REF_FIELD_LABELS[name]
    if not isinstance(rows, list):
        return [f"{label}应为列表"]
    prefix = ROW_PREFIXES[name]
    issues: list[str] = []
    seen: set[str] = set()
    for position, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            issues.append(f"{label}第 {position} 行应为对象")
            continue
        row_id = str(row.get("id") or "")
        if not re.fullmatch(rf"{prefix}\d{{2,}}", row_id) or row_id in seen:
            issues.append(f"{label}第 {position} 行的编号须为 {prefix}01 这样且不重复（当前: {row_id or '空'}）")
        seen.add(row_id)
        issues += ROW_CHECKS[name](row, f"{label} {row_id or position}", lookup)
    return issues


def key_date_coverage(entry: dict) -> list[str]:
    """四个事项每个一行，招标文件没写的也要占一行写明未规定：看不到一行，分不清是没写还是没找。"""
    rows = entry.get("value")
    if not isinstance(rows, list) or not rows:
        return []
    kinds = [row.get("kind") for row in rows if isinstance(row, dict)]
    issues = [f"关键日期缺“{kind}”这一行；招标文件确实没写的，这一行的 basis 写“招标文件未规定”"
              for kind in KEY_DATE_KINDS if kind not in kinds]
    return issues + [f"关键日期“{kind}”重复了" for kind in KEY_DATE_KINDS if kinds.count(kind) > 1]


def check_price_limit(entry: dict, lookup: RefLookup) -> list[str]:
    """招标人公布的限价可以进规则卡；报价墙（B13）只拦投标人自己的金额。"""
    value = entry.get("value")
    if entry.get("basis") == UNSPECIFIED or is_empty(value):
        return []
    if not isinstance(value, dict) or not isinstance(value.get("is_set"), bool):
        return ["最高投标限价应为 {is_set, value, ref}，is_set 写 true 或 false"]
    issues = ref_issues(value.get("ref"), "最高投标限价", lookup)
    has_amount = not is_empty(value.get("value"))
    if value["is_set"] and not has_amount:
        issues.append("最高投标限价：招标文件设了限价，value 照录数字或公布方式（如“通过电子交易系统发布”）")
    if not value["is_set"] and has_amount:
        issues.append("最高投标限价：招标文件没设限价，value 留空")
    return issues


def check_ref_fields(card: dict, project_dir: Path) -> list[str]:
    lookup = RefLookup(project_dir)
    issues = [issue for name in ROW_CHECKS for issue in check_rows(name, card[name], lookup)]
    return issues + key_date_coverage(card["key_dates"]) + check_price_limit(card["price_limit"], lookup)


# ---------- 视图 ----------

def ref_text(ref: object) -> str:
    if not isinstance(ref, dict):
        return "—"
    page = f" 第{ref['page']}页" if ref.get("page") else ""
    return cell(f"{ref.get('file')}{page} 第{ref.get('line')}行")


def rows_of(entry: dict) -> list[dict]:
    rows = entry.get("value")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def field_head(name: str, entry: dict) -> list[str]:
    mark = "✓" if entry.get("checked") is True else "待核对"
    return [f"### {REF_FIELD_LABELS[name]}（依据：{cell(entry.get('basis'))}；{mark}）", ""]


def joined(items: object) -> str:
    return cell("；".join(str(item) for item in items)) if isinstance(items, list) else "—"


def option_text(row: dict) -> str:
    options = row.get("options") if isinstance(row.get("options"), list) else []
    return cell(" ".join(f"{'☑' if item.get('checked') else '□'}{item.get('text')}"
                         for item in options if isinstance(item, dict)))


def table_lines(heads: tuple[str, ...], rows: list[list[str]]) -> list[str]:
    return [f"| {' | '.join(heads)} |", f"|{'---|' * len(heads)}", *[f"| {' | '.join(row)} |" for row in rows], ""]


def ref_sections(card: dict) -> list[str]:
    """rule-card.md 的第六节。每行都带定位，用户能翻回原文。"""
    tables = {
        "qualification": (("编号", "评审因素", "条款原文", "指针路径", "逐项要求", "定位"),
                          lambda row: [cell(row.get("id")), cell(row.get("factor")), cell(row.get("text")),
                                       joined(row.get("pointer_chain")), joined(row.get("requirements")),
                                       ref_text(row.get("ref"))]),
        "key_dates": (("编号", "事项", "原文", "日期", "定位"),
                      lambda row: [cell(row.get("id")), cell(row.get("kind")),
                                   cell(row.get("text") or row.get("basis")), cell(row.get("deadline")),
                                   ref_text(row.get("ref"))]),
        "checkboxes": (("编号", "条款", "选项", "勾了几个", "说明", "定位"),
                       lambda row: [cell(row.get("id")), cell(row.get("label")), option_text(row),
                                    cell(str(row.get("count"))), cell(row.get("note")), ref_text(row.get("ref"))]),
        "off_table": (("编号", "事项", "条款原文", "定位"),
                      lambda row: [cell(row.get("id")), cell(row.get("kind")), cell(row.get("text")),
                                   ref_text(row.get("ref"))]),
        "award": (("编号", "条款原文", "定位"),
                  lambda row: [cell(row.get("id")), cell(row.get("text")), ref_text(row.get("ref"))]),
    }
    lines: list[str] = []
    for name, (heads, cells) in tables.items():
        lines += [*field_head(name, card[name]), *table_lines(heads, [cells(row) for row in rows_of(card[name])])]
    return lines + price_limit_lines(card["price_limit"])


def price_limit_lines(entry: dict) -> list[str]:
    value = entry.get("value") if isinstance(entry.get("value"), dict) else {}
    state = {True: f"设了限价：{cell(value.get('value'))}", False: "没设限价"}.get(value.get("is_set"), "—")
    return [*field_head("price_limit", entry), f"- {state}（{ref_text(value.get('ref'))}）", ""]
