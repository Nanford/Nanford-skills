"""Stage-8 submission checklist of qingtian-bid: the items, the user's ticks, the automatic checks and the stage-8
completion condition.

INPUT: templates/submission-checklist.json (fixed items); <project>/analysis/rule-card.json (track, the 初步评审表
       rows with tech_related false, mandatory clauses routed to 提交前清单 (including 商务文件 and 报价文件 until step 5),
       the 工期 / 质量标准 / 入围与推荐规则 wording); project-state.json; output/施工组织设计.docx and review/gate-report.json; final_gate for the
       stage-7 condition and verified PDF delivery record for new projects.
OUTPUT: checklist_items(); tick_item() and mark_not_applicable() record submission.items.<id> in project-state.json;
        review/submission-checklist.md (a generated view); stage8_issues() for project_status --complete 8;
        submission_summary() for the progress summary; a CLI that writes the view (exit 1 while anything is open).
POS: state layer of stage 8 (design v1 §9 第 4c 步), next to final_gate (stages 6-7). The list is computed from the
     template, the rule card and the track on every call and is never stored as an editable file; the Markdown
     file is a view (决策 4c-1A). A tick locks the item's own wording, so a rule-card edit voids only the rows whose
     text changed; items marked locks_docx (S01, S02) also lock the finished DOCX's sha256 (决策 4c-2A). Only
     skippable items take 不适用 with the user's stated reason; red-line items can only be ticked (决策 4c-3A).
     The script records what the user confirmed; it never decides on the user's behalf.

project-state.json keys owned here:
  submission.items.<id>  {status: checked|not_applicable, digest, reason?, docx_sha256?, recorded_at}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from check_qingtian_final import FINISHED_DOCX
from export_response_pdf import pdf_delivery_issues
from final_gate import report_issues, stage7_issues
from format_state import save_state
from project_cards import (
    RULE_CARD_FILE,
    SKILL_DIR,
    SUBMISSION_SCOPE,
    UNSPECIFIED,
    cell,
    clause_scope,
    file_sha256,
    load_json,
    load_project,
    now_text,
    scoped_clauses,
    sha256_bytes,
)
from response_matrix import chinese_ordinal

TEMPLATE_FILE = SKILL_DIR / "templates" / "submission-checklist.json"
TEMPLATE_SCHEMA = "qingtian-submission-checklist/1"
VIEW_FILE = "review/submission-checklist.md"
# 成品以外还在 output/ 里的 Word 类文件：可能被当成第二份施组上传（示范文本 3.6.3 视为备选方案，否决）
WORD_SUFFIXES = {".docx", ".doc", ".docm", ".dotx", ".wps"}
# 规则卡里替换进条目文字的取值
RULE_VALUES = {"{schedule}": "schedule", "{quality_standard}": "quality_standard", "{shortlist_rule}": "shortlist_rule"}
CHECKED, NOT_APPLICABLE = "checked", "not_applicable"
TICK_HINT = "用户逐条核对、明确认可后才运行"


# ---------- 清单条目 ----------

def load_template() -> dict:
    template = load_json(TEMPLATE_FILE, "提交前清单模板")
    if template.get("schema") != TEMPLATE_SCHEMA:
        raise ValueError(f"提交前清单模板 schema 应为 {TEMPLATE_SCHEMA}")
    return template


def rule_text(rule_card: dict, name: str) -> str:
    entry = rule_card.get(name) or {}
    value = entry.get("value")
    if value not in (None, ""):
        return str(value).strip()
    # 四种以外的评标办法，入围规则招标文件可能真没写（决策 2A）；写明了就不算"规则卡未写"
    return UNSPECIFIED if entry.get("basis") == UNSPECIFIED else "（规则卡未写）"


def fill_values(text: str, rule_card: dict) -> str:
    for placeholder, name in RULE_VALUES.items():
        text = text.replace(placeholder, rule_text(rule_card, name))
    return text


def static_items(template: dict, rule_card: dict, track: str) -> list[dict]:
    """模板里的固定条目：按轨道筛选（tracks 为空即所有轨道），填上规则卡原文。"""
    return [{**item, "text": fill_values(item["text"], rule_card)} for item in template["items"]
            if not item.get("tracks") or track in item["tracks"]]


def preliminary_items(rule_card: dict) -> list[dict]:
    """初步评审表里与施组无关的行，一行一条；编号用行在全表里的位置，与 B12 的行号一致。"""
    entry = rule_card.get("preliminary_review") or {}
    rows = entry.get("value") or []
    return [{"id": f"R{row:02d}", "group": "R", "skippable": False, "locks_docx": False, "label": "招标文件",
             "text": f"{line.get('stage')} {line.get('factor')}：{line.get('standard')}（由{line.get('file') or '商务'}文件满足，"
                     f"用户对照{line.get('file') or '商务'}文件核对）",
             "source": f"规则卡初步评审表第 {row} 行；{entry.get('source') or '招标文件'}"}
            for row, line in enumerate(rows, 1) if isinstance(line, dict) and line.get("tech_related") is False]


def clause_note(clause: dict) -> str:
    """去商务文件、报价文件的条款现在并入这张清单（临时方案，第 5 步替换），写明该对照哪个文件。"""
    scope = clause_scope(clause)
    return "" if scope == SUBMISSION_SCOPE else f"（落实在{scope}，用户对照{scope}核对）"


def clause_items(rule_card: dict) -> list[dict]:
    """在提交前清单核对的★、实质性、否决条款，一条一项，只能勾（决策 4c-4A）。"""
    return [{"id": str(clause.get("id")), "group": "M", "skippable": False, "locks_docx": False, "label": "招标文件",
             "text": f"{clause.get('type')} {clause.get('text')}{clause_note(clause)}",
             "source": str(clause.get("source") or "")}
            for clause in scoped_clauses(rule_card, SUBMISSION_SCOPE)]


def item_digest(item: dict) -> str:
    """勾选锁定的条目内容：编号、文字、出处和规则。规则卡里这一行变了，只有这一条的勾选作废。"""
    fields = [item["id"], item["text"], item["source"], item["skippable"], item["locks_docx"]]
    return sha256_bytes(json.dumps(fields, ensure_ascii=False).encode("utf-8"))


def checklist(project_dir: Path) -> tuple[dict, list[dict]]:
    """(模板, 条目)。每次按模板、规则卡和轨道现算，不存可手改的清单（决策 4c-1A）。"""
    template = load_template()
    rule_card = load_json(project_dir / RULE_CARD_FILE, "规则卡")
    track = rule_text(rule_card, "track")
    items = static_items(template, rule_card, track) + preliminary_items(rule_card) + clause_items(rule_card)
    return template, [{**item, "digest": item_digest(item)} for item in items]


def checklist_items(project_dir: Path) -> list[dict]:
    return checklist(project_dir)[1]


# ---------- 自动核对 ----------

def extra_word_files(project_dir: Path) -> list[Path]:
    """output/ 下成品以外的 Word 类文件（Word、WPS 打开时的 ~$ 临时文件不算）。"""
    output = project_dir / "output"
    finished = (project_dir / FINISHED_DOCX).resolve()
    if not output.is_dir():
        return []
    return sorted(path for path in output.rglob("*") if path.is_file() and path.suffix.lower() in WORD_SUFFIXES
                  and not path.name.startswith("~$") and path.resolve() != finished)


def extra_files_issue(project_dir: Path) -> list[str]:
    extra = extra_word_files(project_dir)
    if not extra:
        return []
    return [f"output/ 下除成品外还有 {len(extra)} 个 Word 文件：移出 output/，只留一份施组（示范文本 3.6.3，两份以上视为备选方案）"]


def docx_sha(project_dir: Path) -> str | None:
    docx = project_dir / FINISHED_DOCX
    return file_sha256(docx) if docx.is_file() else None


def automatic_issues(project_dir: Path, sha: str | None) -> list[str]:
    """勾 S01、S02 的证据：门禁报告是当前成品放行后的结果，output/ 下只有这一份施组。"""
    if sha is None:
        return [f"还没有成品 {FINISHED_DOCX}"]
    _, state = load_project(project_dir)
    pdf_issues = pdf_delivery_issues(project_dir, sha) if state.get("require_pdf_delivery") else []
    return report_issues(project_dir, sha) + extra_files_issue(project_dir) + pdf_issues


# ---------- 勾选状态 ----------

def records_of(state: dict) -> dict:
    return (state.get("submission") or {}).get("items") or {}


def item_status(item: dict, record: dict | None, sha: str | None) -> tuple[str, str]:
    """(open | checked | not_applicable | stale, 说明)。"""
    if not record:
        return "open", "未勾选"
    if record.get("digest") != item["digest"]:
        return "stale", "勾选后条目内容变了（规则卡改过），重新核对"
    if item["locks_docx"] and record.get("docx_sha256") != sha:
        return "stale", "勾选后成品又保存过，重新核对"
    if record.get("status") == NOT_APPLICABLE:
        return NOT_APPLICABLE, f"不适用：{record.get('reason')}"
    return CHECKED, f"已核对（{record.get('recorded_at')}）"


def item_statuses(project_dir: Path, state: dict, items: list[dict]) -> list[tuple[dict, str, str]]:
    sha, records = docx_sha(project_dir), records_of(state)
    return [(item, *item_status(item, records.get(item["id"]), sha)) for item in items]


# ---------- 记录 ----------

def find_item(items: list[dict], item_id: str) -> dict:
    found = next((item for item in items if item["id"] == item_id), None)
    if found is None:
        raise ValueError(f"提交前清单没有 {item_id}；编号见 {VIEW_FILE}（运行 submission_checklist.py <项目目录> 重出）")
    return found


def prepare_record(project_dir: Path, item_id: str) -> tuple[Path, dict, dict]:
    project_dir, state = load_project(project_dir)
    if state["stages"].get("7") != "done":
        raise ValueError("阶段 7 还没完成：门禁全部处理完、完成阶段 7 后才核对提交前清单")
    return project_dir, state, find_item(checklist_items(project_dir), item_id)


def save_record(project_dir: Path, state: dict, item: dict, record: dict) -> dict:
    state.setdefault("submission", {}).setdefault("items", {})[item["id"]] = {
        **record, "digest": item["digest"], "recorded_at": now_text()}
    if state["stages"].get("8") == "pending":
        state["stages"]["8"] = "in-progress"
    save_state(project_dir, state)
    write_view(project_dir)
    return {"project": str(project_dir), "id": item["id"], **state["submission"]["items"][item["id"]]}


def tick_item(project_dir: Path, item_id: str) -> dict:
    """用户逐条核对、明确认可后才调用。S01、S02 还要证据成立：门禁报告是当前成品的，output/ 下只有一份施组。"""
    project_dir, state, item = prepare_record(project_dir, item_id)
    record: dict = {"status": CHECKED}
    if item["locks_docx"]:
        sha = docx_sha(project_dir)
        issues = automatic_issues(project_dir, sha)
        if issues:
            raise ValueError(f"{item_id} 的证据不成立，先处理：{issues[0]}")
        record["docx_sha256"] = sha
    return save_record(project_dir, state, item, record)


def mark_not_applicable(project_dir: Path, item_id: str, reason: str) -> dict:
    """只有按需触发的条目可记不适用，理由是用户说明的原话（决策 4c-3A）。"""
    project_dir, state, item = prepare_record(project_dir, item_id)
    if not item["skippable"]:
        raise ValueError(f"{item_id} 是红线条目，只能核对后勾选，不能记不适用（决策 4c-3A）")
    if not reason.strip():
        raise ValueError("记不适用要写用户说明的理由（--reason）")
    return save_record(project_dir, state, item, {"status": NOT_APPLICABLE, "reason": reason.strip()})


# ---------- 阶段 8 ----------

def open_item_issues(statuses: list[tuple[dict, str, str]]) -> list[str]:
    return [f"{item['id']} {note}：{item['text'][:40]}" for item, status, note in statuses
            if status not in (CHECKED, NOT_APPLICABLE)]


def stage8_issues(project_dir: Path, state: dict) -> list[str]:
    """阶段 8 完成条件：阶段 7 仍成立；output/ 下只有一份施组；每条适用的条目已勾选或已按规则记不适用，且没失效。"""
    issues = stage7_issues(project_dir, state)
    if issues:
        return [f"阶段 7 的条件不再成立：{issue}" for issue in issues]
    statuses = item_statuses(project_dir, state, checklist_items(project_dir))
    return automatic_issues(project_dir, docx_sha(project_dir)) + open_item_issues(statuses)


def submission_summary(project_dir: Path, state: dict) -> str:
    if state["stages"].get("7") != "done":
        return "—（阶段 7 完成后核对）"
    try:
        statuses = item_statuses(project_dir, state, checklist_items(project_dir))
    except ValueError as exc:
        return str(exc)
    done = sum(1 for _, status, _ in statuses if status in (CHECKED, NOT_APPLICABLE))
    return f"已处理 {done}/{len(statuses)} 条"


# ---------- 视图 ----------

STATUS_MARKS = {"open": "☐", CHECKED: "☑", NOT_APPLICABLE: "—", "stale": "⚠"}


def group_lines(no: int, title: str, rows: list[tuple[dict, str, str]]) -> list[str]:
    lines = [f"## {chinese_ordinal(no)}、{title}", "", "| 编号 | 核对内容 | 出处 | 可记不适用 | 状态 |", "|---|---|---|---|---|"]
    for item, status, note in rows:
        lines.append(f"| {item['id']} | {cell(item['text'])} | {cell(item['source'])}（{item['label']}） | "
                     f"{'是' if item['skippable'] else '否，只能勾'} | {STATUS_MARKS[status]} {cell(note)} |")
    return lines + [""]


def head_lines(state: dict, sha: str | None, auto: list[str], open_count: int) -> list[str]:
    conclusion = ("可以完成阶段 8：运行 `project_status.py <项目目录> --complete 8`" if not auto and not open_count
                  else f"还有 {open_count} 条没处理、{len(auto)} 个自动核对问题")
    return [f"# 提交前清单（{state.get('project_name', '')}）", "",
            "> 由 `submission_checklist.py` 按模板、规则卡和评审轨道现算生成，不手改（决策 4c-1A）。"
            f"{TICK_HINT} `project_status.py <项目目录> --tick <编号>`；“可记不适用”为是的条目，用户说明理由后 "
            "`project_status.py <项目目录> --not-applicable <编号> --reason \"<用户的理由>\"`。", "",
            f"- 状态：{conclusion}",
            f"- 成品：`{FINISHED_DOCX}`（sha256 {sha[:12] if sha else '—'}）",
            *[f"- 自动核对：{issue}" for issue in auto], ""]


def render_view(project_dir: Path, state: dict) -> str:
    template, items = checklist(project_dir)
    sha = docx_sha(project_dir)
    statuses = item_statuses(project_dir, state, items)
    open_count = len(open_item_issues(statuses))
    lines = head_lines(state, sha, automatic_issues(project_dir, sha), open_count)
    groups = [(group, [row for row in statuses if row[0]["group"] == group["id"]]) for group in template["groups"]]
    for no, (group, rows) in enumerate([pair for pair in groups if pair[1]], 1):
        lines += group_lines(no, group["title"], rows)
    return "\n".join(lines)


def write_view(project_dir: Path) -> Path:
    project_dir, state = load_project(project_dir)
    path = project_dir / VIEW_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_view(project_dir, state), encoding="utf-8")
    return path


# ---------- 命令行 ----------

def result_text(project_dir: Path) -> tuple[str, int]:
    """写视图并汇总；有未处理条目或自动核对问题时退出码为 1。另有的 Word 文件名只显示，不落盘。"""
    path = write_view(project_dir)
    project_dir, state = load_project(project_dir)
    statuses = item_statuses(project_dir, state, checklist_items(project_dir))
    pending = open_item_issues(statuses)
    auto = automatic_issues(project_dir, docx_sha(project_dir))
    lines = [f"提交前清单：{path}", f"共 {len(statuses)} 条，未处理 {len(pending)} 条，自动核对问题 {len(auto)} 个。"]
    lines += [f"- {issue}" for issue in auto] + [f"  另有：{extra.relative_to(project_dir).as_posix()}"
                                                 for extra in extra_word_files(project_dir)]
    lines += [f"- {issue}" for issue in pending]
    if state["stages"].get("7") != "done":
        lines.append("阶段 7 还没完成：完成后才能勾选。")
    return "\n".join(lines), 1 if pending or auto else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 qingtian-bid 项目的提交前清单视图（阶段 8），列出未处理的条目。")
    parser.add_argument("project_dir", type=Path, help="项目目录（bid-projects/ 下）。")
    args = parser.parse_args(argv)
    try:
        text, code = result_text(args.project_dir)
    except (OSError, ValueError) as exc:
        print(f"提交前清单生成失败: {exc}", file=sys.stderr)
        return 2
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
