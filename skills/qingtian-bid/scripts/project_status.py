"""Stage tracker and confirmation gates of a qingtian-bid project (stages 0-8).

迁移来源见 CHANGELOG《脚本来源》，按设计稿 v1 第 3 步改造：
- 阶段改为 0～8（初始化、提取、解标定轨、事实卡与资源卡、响应矩阵、逐项撰写、出稿、门禁、
  提交前清单）；不允许跳阶段，只能按顺序开始和完成；
- 阶段 0 只随格式样张确认完成（render_format_sample.py --confirm），这里不能手动完成或重开；
- 完成阶段带条件：阶段 1 要求登记的每个来源都在提取报告里且通过 R9；阶段 2 要求规则卡已确认
  且未失效、评审轨道已定、没有待确认的格式变更、招标文件格式覆盖已确认或规则卡写明无规定（评审注释写了
  扣分而格式规定有"建议"的，格式规定须登记扣分原文）；
  阶段 3 要求规则卡、事实卡、资源卡都已确认且未失效（第 3b 步）；阶段 4 要求大纲（响应矩阵）已确认且
  未失效，阶段 5 要求资源卡没有缺口（R8）、每项中间稿都已按顺序逐项确认（第 3c 步）；--check-item 同时跑
  内容门禁，B 级命中挡住 --confirm-item（第 4a 步）；阶段 6 要求成品由确认过的中间稿按锁定格式出稿、版式
  校验没有阻断项，阶段 7 要求当前成品的门禁没有未放行的阻断项和未处理的提示、初步评审表与施组有关的每行
  都已确认（--confirm-b12）、门禁报告记的是这次的结果（第 4b-2 步）；阶段 8 要求阶段 7 仍成立、output/ 下
  只有一份施组、提交前清单每条适用的条目都已勾选或按规则记不适用（--tick、--not-applicable，第 4c 步）；
- 阶段 5 另有开始条件：大纲有效、资源卡没有缺口，否则不能开始（R8）；
- --add-source 登记开工后才到的补遗、图纸或样本，已完成的阶段 1 起全部自动重开；
- --add-resource 登记开工后才补的公司资源资料（不复制，原地编目；项目里的路径记相对路径），已完成的阶段 3
  起自动重开；
- 进度摘要显示登记处现有的资料文件数；一个都没有、阶段 3 又没完成的，从开工起就提醒往 公司资料/ 里放；
- 状态文件只经 format_state.save_state 写入，不碰格式字段（format_*、document_format）。

INPUT: <project>/project-state.json; analysis/extraction-report.json; analysis/rule-card.json;
       analysis/tender-format.json (when the rule card points to it); analysis/fact-card.json,
       resource-card.json and material-index.json (stage 3); the files under the registered resource
       paths (counted for the summary, through index_materials); analysis/response-matrix.json (stage 4);
       output/实施方案/NN-<评审内容原文>.md drafts, review/gate-notes.json and review/rehearsal/NN.json (shown by
       --check-item, never blocks) (stage 5); output/施工组织设计.docx,
       its .build-report.json, review/page-count.json, final-gate-notes.json and gate-report.json (stages 6-7);
       templates/submission-checklist.json through submission_checklist (stage 8); review/自评/ through
       self_score (the 模拟自评 line of the summary, never a condition).
OUTPUT: stage transitions, source and resource registration, card, per-item, 初步评审对照 (B12) and 提交前清单
        confirmations saved in project-state.json; analysis/资料清单.md after the rule card is confirmed; the card views (rule-card.md, mandatory-checklist.md,
        project-facts.md, company-resources.md, response-matrix.md, review/submission-checklist.md); a progress summary.
POS: the only stage-transition entry point of qingtian-bid. Card validation lives in project_cards.py,
     fact_resource_cards.py and response_matrix.py, the per-item gate in writing_gate.py, the stage 6-7
     conditions in final_gate.py, the stage-8 checklist in submission_checklist.py, the content gates in
     check_qingtian_gates.py and check_qingtian_final.py (which also record dismissal reasons, outside this tracker).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from extract_text import PASSING_STATUSES, SOURCE_KINDS, file_sha256, registered_sources
from fact_resource_cards import (
    check_fact_card,
    check_resource_card,
    confirm_fact_card,
    confirm_resource_card,
    resource_summary,
    stage3_issues,
)
from final_gate import confirm_b12, final_summary, stage6_issues, stage7_issues
from format_state import penalty_issue, save_state
from index_materials import material_file_count, resource_root
from material_list import confirm_and_list
from project_cards import (
    RULE_CARD_FILE,
    SKILL_DIR,
    card_status,
    check_rule_card,
    load_json,
    load_project,
)
from rehearsal import rehearsal_line
from response_matrix import check_matrix, confirm_matrix, stage4_issues
from rule_card_rows import change_lines
from self_score import self_score_summary
from submission_checklist import mark_not_applicable, stage8_issues, submission_summary, tick_item
from writing_gate import check_item, confirm_item, stage5_issues, stage5_start_issues, writing_summary


STAGE_LABELS = {
    0: "初始化", 1: "提取", 2: "解标定轨", 3: "事实卡与资源卡", 4: "响应矩阵",
    5: "逐项撰写", 6: "出稿", 7: "门禁", 8: "提交前清单",
}
STAGE_GUIDES = {
    0: "stage-0-init.md", 1: "stage-1-extract.md", 2: "stage-2-analysis.md", 3: "stage-3-facts-resources.md",
    4: "stage-4-matrix.md", 5: "stage-5-writing.md", 6: "stage-6-assembly.md", 7: "stage-7-gates.md",
    8: "stage-8-submission.md",
}
STATUS_ICONS = {"pending": "○ 待办", "in-progress": "◐ 进行中", "done": "● 完成"}
SOURCE_DIRS = {"tender": "source", "drawing": "source/drawings", "sample": "source/response-samples"}
KIND_LABELS = {"tender": "招标文件", "drawing": "图纸", "sample": "响应样本"}
FORMAT_FLOW = "成品格式随样张确认走：render_format_sample.py --project <项目目录>（改格式）/ --confirm（确认）"
# --check / --confirm 的卡片：(中文名, 校验并重出视图, 用户同意后确认)
CARD_ACTIONS = {
    "rule-card": ("规则卡", check_rule_card, confirm_and_list),  # 确认后顺带出资料清单
    "fact-card": ("事实卡", check_fact_card, confirm_fact_card),
    "resource-card": ("资源卡", check_resource_card, confirm_resource_card),
    "response-matrix": ("响应矩阵", check_matrix, confirm_matrix),
}


def guide_text(stage: int) -> str:
    """阶段 0～8 的细则都已交付；文件缺了（安装不完整）时如实说明，不指向不存在的文件。"""
    path = SKILL_DIR / "references" / STAGE_GUIDES[stage]
    return f"references/{STAGE_GUIDES[stage]}" if path.is_file() else f"细则文件缺失（references/{STAGE_GUIDES[stage]}）"


def check_stage_number(stage: int) -> None:
    if stage not in STAGE_LABELS:
        raise ValueError(f"阶段编号只能是 0～8（当前: {stage}）")
    if stage == 0:
        raise ValueError(f"阶段 0 不能手动开始、完成或重开。{FORMAT_FLOW}")


def require_previous_done(state: dict, stage: int) -> None:
    pending = [str(item) for item in range(stage) if state["stages"].get(str(item)) != "done"]
    if pending:
        raise ValueError(f"阶段 {'、'.join(pending)} 未完成，不能跳到阶段 {stage}（{STAGE_LABELS[stage]}）")


def extraction_issues(project_dir: Path, state: dict) -> list[str]:
    """阶段 1：每个登记来源都提取过、来源没被替换、类别与登记一致、状态通过 R9。"""
    report_path = project_dir / "analysis" / "extraction-report.json"
    if not report_path.is_file():
        return ["还没有提取报告，登记来源都不在提取报告里：运行 extract_text.py --project 整批提取"]
    try:
        sources = registered_sources(project_dir)
        report = load_json(report_path, "提取报告")
    except ValueError as exc:
        return [str(exc)]
    items = {str(Path(item["file"]).resolve()): item for item in report.get("items") or []}
    issues = []
    for path, kind in sources:
        item = items.get(str(path))
        label = f"{KIND_LABELS[kind]} {path.name}"
        if item is None:
            issues.append(f"{label}：不在提取报告里，运行 extract_text.py --project 整批提取")
        elif item.get("kind") != kind:
            issues.append(f"{label}：提取时登记为 {item.get('kind')}，与现在的登记不一致，重新提取")
        elif item.get("status") not in PASSING_STATUSES:
            issues.append(f"{label}：{item.get('status')}，{item.get('reason', '')}（R9 硬停）")
        elif not path.is_file() or file_sha256(path) != item.get("sha256"):
            issues.append(f"{label}：提取后文件被替换或删除，重新提取")
    return issues


def tender_format_issues(project_dir: Path, state: dict, card: dict) -> list[str]:
    value = card["format"]["value"]
    if value.get("no_rules") is True:
        return []
    confirmed = state.get("tender_format")
    pointer = (project_dir / value["tender_format"]).resolve()
    if not confirmed or Path(confirmed["file"]).resolve() != pointer:
        return [f"招标文件格式覆盖未确认：按 stage-6-assembly.md 第二节对 {value['tender_format']} 出差异和样张，用户同意后 --confirm"]
    if not pointer.is_file() or file_sha256(pointer) != confirmed["sha256"]:
        return ["招标文件格式规定在确认后被修改：重新出差异和样张，再请用户确认"]
    issue = penalty_issue(card["review_notes"].get("value"), confirmed)
    return [f"{issue}；改好后重新出差异和样张，再请用户确认"] if issue else []


def analysis_issues(project_dir: Path, state: dict) -> list[str]:
    """阶段 2：规则卡确认且未失效（轨道已定由规则卡校验保证）、格式没有待确认变更、格式覆盖已确认。"""
    status = card_status(project_dir, state, "rule_card")
    if status["status"] != "confirmed":
        return [f"规则卡{status['reason']}：校验用 --check rule-card，用户同意后 --confirm rule-card"]
    issues = []
    if state.get("format_review"):
        issues.append(f"有待确认的格式变更（{state['format_review']['kind']}）：先请用户看样张并确认")
    card = load_json(project_dir / RULE_CARD_FILE, "规则卡")
    return issues + tender_format_issues(project_dir, state, card)


STAGE_GATES = {1: extraction_issues, 2: analysis_issues, 3: stage3_issues, 4: stage4_issues, 5: stage5_issues,
               6: stage6_issues, 7: stage7_issues, 8: stage8_issues}
# 开始条件：资源卡有缺口时连阶段 5 都不能开始，只许停在大纲和缺口清单（R8）
STAGE_START_GATES = {5: stage5_start_issues}


def start_stage(project_dir: Path, stage: int) -> dict:
    project_dir, state = load_project(project_dir)
    check_stage_number(stage)
    if state["stages"][str(stage)] == "done":
        raise ValueError(f"阶段 {stage} 已完成；要重做用 --reopen {stage}")
    require_previous_done(state, stage)
    issues = STAGE_START_GATES[stage](project_dir, state) if stage in STAGE_START_GATES else []
    if issues:
        raise ValueError(f"阶段 {stage} 不能开始：\n" + "\n".join(f"- {item}" for item in issues))
    state["stages"][str(stage)] = "in-progress"
    save_state(project_dir, state)
    return state


def complete_stage(project_dir: Path, stage: int) -> dict:
    project_dir, state = load_project(project_dir)
    check_stage_number(stage)
    require_previous_done(state, stage)
    issues = STAGE_GATES[stage](project_dir, state)
    if issues:
        raise ValueError(f"阶段 {stage} 不能完成：\n" + "\n".join(f"- {item}" for item in issues))
    state["stages"][str(stage)] = "done"
    save_state(project_dir, state)
    return state


def reopen_from(state: dict, stage: int) -> list[int]:
    """重开阶段 N：N 回到进行中，之后已完成的阶段也回到进行中，靠它们的产出要重新核对。"""
    state["stages"][str(stage)] = "in-progress"
    reopened = [stage]
    for item in range(stage + 1, len(STAGE_LABELS)):
        if state["stages"].get(str(item)) == "done":
            state["stages"][str(item)] = "in-progress"
            reopened.append(item)
    return reopened


def reopen_stage(project_dir: Path, stage: int) -> dict:
    project_dir, state = load_project(project_dir)
    check_stage_number(stage)
    reopen_from(state, stage)
    save_state(project_dir, state)
    return state


def stored_path(project_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(project_dir).as_posix()
    except ValueError:
        return str(path)


def copy_source(project_dir: Path, path: Path, kind: str) -> Path:
    target_dir = project_dir / SOURCE_DIRS[kind]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    if target.exists() and file_sha256(target) != file_sha256(path):
        raise ValueError(f"项目里已有同名文件且内容不同: {target}；改名后再登记，不覆盖")
    if not target.exists():
        shutil.copy2(path, target)
    return target


def add_source(project_dir: Path, source: Path, kind: str, copy: bool = True) -> dict:
    """登记开工后才到的补遗、图纸或样本。图纸类别只在用户声明后使用（决策 2A）。"""
    project_dir, state = load_project(project_dir)
    if kind not in SOURCE_KINDS:
        raise ValueError(f"来源类别只能是 {'/'.join(SOURCE_KINDS)}")
    path = source.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"来源文件不存在: {path}")
    registered = copy_source(project_dir, path, kind) if copy else path
    entry = {"path": stored_path(project_dir, registered), "kind": kind}
    sources = state.setdefault("sources", [])
    existing = next((item for item in sources if item["path"] == entry["path"]), None)
    if existing and existing["kind"] != kind:
        raise ValueError(f"{entry['path']} 已登记为 {KIND_LABELS[existing['kind']]}，不能改登为 {KIND_LABELS[kind]}")
    reopened = []
    if existing is None:
        sources.append(entry)
        # 新来源改变了解标依据：已完成的阶段 1 起全部重开，规则卡、事实卡确认随提取文本指纹失效，
        # 资源卡、大纲和中间稿随上游卡片的改动逐级失效
        reopened = [stage for stage in range(1, len(STAGE_LABELS)) if state["stages"].get(str(stage)) == "done"]
        for stage in reopened:
            state["stages"][str(stage)] = "in-progress"
    save_state(project_dir, state)
    return {"registered": entry, "already_registered": existing is not None, "reopened": reopened}


def add_resource(project_dir: Path, resource: Path) -> dict:
    """登记开工后才补的公司资源资料（文件或文件夹）。原地编目、不复制：公司资料不在项目里多存一份。
    项目里的路径记相对路径，和建项目时自动登记的 公司资料/ 一样，项目整体搬走也能编目。"""
    project_dir, state = load_project(project_dir)
    path = resource.expanduser().resolve()
    if not path.exists():
        raise ValueError(f"公司资源资料不存在: {path}")
    resources = state.setdefault("resources", [])
    existing = any(resource_root(project_dir, item.get("path")) == path for item in resources)
    reopened = []
    if not existing:
        resources.append({"path": stored_path(project_dir, path)})
        # 资源变了，资源卡确认随编目指纹失效；已完成的阶段 3 起重开
        if state["stages"].get("3") == "done":
            reopened = reopen_from(state, 3)
    save_state(project_dir, state)
    return {"registered": str(path), "already_registered": existing, "reopened": reopened}


def format_status(state: dict) -> str:
    if state.get("format_review"):
        return f"有待确认的变更（{state['format_review']['kind']}），确认前不能出稿"
    record = state.get("document_format")
    return f"已锁定（{record['preset']}）" if record else "未确认"


COMPANY_REMINDER = ("提醒：公司资料还没放。把这次投标的资料按子目录放进项目的 公司资料/（放什么见各目录的 说明.md），"
                    "阶段 3 要按它填资源卡；缺哪一类，资源卡记缺口，阶段 5 整段不能开始（R8）。")


def company_reminder(state: dict, material_files: int) -> list[str]:
    """开工起就提醒：资料晚到，阶段 3 卡住时离截标往往只剩几天。阶段 3 完成后不再提醒。"""
    return [COMPANY_REMINDER] if material_files == 0 and state["stages"].get("3") != "done" else []


def render_summary(project_dir: Path, state: dict) -> str:
    counts = {kind: sum(1 for item in state.get("sources") or [] if item.get("kind") == kind) for kind in SOURCE_KINDS}
    material_files = material_file_count(project_dir, state)
    has_analysis = (project_dir / "analysis").is_dir()
    rule = card_status(project_dir, state, "rule_card")["reason"] if has_analysis else "—"
    fact = card_status(project_dir, state, "fact_card")["reason"] if has_analysis else "—"
    resource = resource_summary(project_dir, state) if has_analysis else "—"
    matrix = card_status(project_dir, state, "response_matrix")["reason"] if has_analysis else "—"
    writing = writing_summary(project_dir, state) if has_analysis else "—"
    final = final_summary(project_dir, state) if has_analysis else "—"
    submission = submission_summary(project_dir, state) if has_analysis else "—"
    self_score = self_score_summary(project_dir, state) if has_analysis else "—"
    lines = [
        f"项目：{state.get('project_name', '（未命名）')}（qingtian-bid）　最近更新：{state.get('updated_at', '')}",
        f"范围：{state.get('scope', '')}",
        f"成品格式：{format_status(state)}",
        f"规则卡：{rule}",
        f"事实卡：{fact}",
        f"资源卡：{resource}",
        f"响应矩阵：{matrix}",
        f"逐项撰写：{writing}",
        f"成品门禁：{final}",
        f"提交前清单：{submission}",
        f"模拟自评：{self_score}",
        "登记来源：" + "、".join(f"{KIND_LABELS[kind]} {count}" for kind, count in counts.items())
        + f"　公司资源：{len(state.get('resources') or [])} 处，资料文件 {material_files} 个",
        *company_reminder(state, material_files),
        "",
    ]
    for stage, label in STAGE_LABELS.items():
        status = state["stages"].get(str(stage), "pending")
        lines.append(f"  阶段{stage} {label}：{STATUS_ICONS.get(status, status)}　细则：{guide_text(stage)}")
    upcoming = next((stage for stage in STAGE_LABELS if state["stages"].get(str(stage)) != "done"), None)
    lines.append("")
    lines.append("全部阶段已完成。" if upcoming is None
                 else f"下一步 → 阶段{upcoming}（{STAGE_LABELS[upcoming]}），先读细则：{guide_text(upcoming)}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="查看或推进 qingtian-bid 项目阶段，登记来源和公司资源，校验和确认卡片。")
    parser.add_argument("project_dir", type=Path, help="项目目录（bid-projects/ 下）。")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--start", type=int, metavar="N", help="开始阶段 N（前面的阶段须已完成）。")
    action.add_argument("--complete", type=int, metavar="N", help="完成阶段 N（须满足该阶段的完成条件）。")
    action.add_argument("--reopen", type=int, metavar="N", help="重开阶段 N，之后已完成的阶段一并重开。")
    action.add_argument("--add-source", type=Path, metavar="文件", help="登记开工后才到的补遗、图纸或样本。")
    action.add_argument("--add-resource", type=Path, metavar="路径", help="登记开工后才补的公司资源资料（文件或文件夹）。")
    action.add_argument("--check", choices=tuple(CARD_ACTIONS), help="校验卡片并重出 MD 视图，不改状态。")
    action.add_argument("--confirm", choices=tuple(CARD_ACTIONS), help="用户明确同意后确认卡片。")
    action.add_argument("--check-item", type=int, metavar="N", help="自查第 N 项中间稿：结构和内容门禁（第 4a 步），不改状态。")
    action.add_argument("--confirm-item", type=int, metavar="N", help="用户明确同意后确认第 N 项中间稿。")
    action.add_argument("--confirm-b12", type=int, metavar="N",
                        help="用户逐条核对、明确认可后确认初步评审表第 N 行（与施组有关的行，阶段 7）。")
    action.add_argument("--tick", metavar="编号", help="用户逐条核对、明确认可后勾选提交前清单的一条（阶段 8）。")
    action.add_argument("--not-applicable", metavar="编号",
                        help="按需触发的提交前清单条目，用户说明理由后记为不适用（配 --reason）。")
    parser.add_argument("--kind", choices=SOURCE_KINDS, default="tender",
                        help="--add-source 的类别：tender（招标文件、补遗、清单）、drawing（用户声明的图纸）、sample。")
    parser.add_argument("--no-copy", action="store_true", help="--add-source 时只登记路径，不复制进项目。")
    parser.add_argument("--reason", help="--not-applicable 的理由：用户说明的原话。")
    args = parser.parse_args()
    if (args.kind != "tender" or args.no_copy) and args.add_source is None:
        parser.error("--kind、--no-copy 只用于 --add-source")
    if (args.reason is not None) != (args.not_applicable is not None):
        parser.error("--not-applicable 必须配 --reason（用户说明的理由），--reason 只用于 --not-applicable")
    return args


def check_card(project: Path, name: str) -> tuple[str, int]:
    label, check, _ = CARD_ACTIONS[name]
    result = check(project)
    issues = result["issues"]
    if issues:
        return f"{label}还有 {len(issues)} 个问题：\n" + "\n".join(f"- {item}" for item in issues), 1
    if result.get("outline_only"):
        return f"{label}校验通过，但有缺口：确认后只许出大纲和缺口清单（R8），请用户核对确认或先补齐资料。", 0
    return f"{label}校验通过，可以请用户核对确认。", 0


def gate_hint_lines(gates: dict, project: Path, no: int) -> list[str]:
    """阻断项已并入问题清单；这里列提示、已说明和人工核对，并给出记录理由的命令。"""
    lines = [f"提示 {len(gates['warnings'])} 条（W 项不挡确认，阶段 7 逐条改或写明不改的理由）："] if gates["warnings"] else []
    lines += [f"- {entry['gate']} [{entry['id']}] {entry['message']}" for entry in gates["warnings"]]
    lines += [f"已说明：{entry['gate']} [{entry['id']}]（{entry['note']['kind']}：{entry['note']['reason']}）"
              for entry in gates["noted"]]
    if gates["stale_notes"]:
        lines.append(f"另有 {gates['stale_notes']} 条说明因稿件修改失效，命中已重新判定")
    lines += [f"人工核对：{text}" for text in gates["manual"]]
    if any(entry["dismissable"] for entry in gates["blocking"] + gates["warnings"]):
        lines.append(f"B4、B5、B7、B13 经用户复核确属误报，或 W 项用户决定不改的，按用户说明的理由记录："
                     f"check_qingtian_gates.py {project} --item {no} --dismiss <编号> --reason \"<用户的理由>\"")
    return lines


def check_item_text(project: Path, no: int) -> tuple[str, int]:
    result = check_item(project, no)
    budget = f"，预算约 {result['budget_chars']} 字【推断】" if result["budget_chars"] else ""
    length = f"本项约 {result['chars']} 字{budget}"
    issues, hints = result["issues"], gate_hint_lines(result["gates"], project, no)
    # 预演只是提示：两条路径都显示，不影响退出码，也不进 issues
    rehearsal = rehearsal_line(project, no)
    if issues:
        return "\n".join([f"第 {no} 项还有 {len(issues)} 个问题（{length}）：", *[f"- {item}" for item in issues], *hints,
                          rehearsal]), 1
    return "\n".join([f"第 {no} 项自查通过：结构和内容门禁的阻断项已清零（{length}）。", *hints, rehearsal,
                      f"请用户审阅，明确同意后 --confirm-item {no}。"]), 0


def run(args: argparse.Namespace) -> tuple[str, int]:
    """返回 (输出文字, 退出码)；--check、--check-item 有问题时退出码为 1。"""
    project = args.project_dir
    if args.check:
        return check_card(project, args.check)
    if args.check_item is not None:
        return check_item_text(project, args.check_item)
    if args.confirm:
        changes = CARD_ACTIONS[args.confirm][2](project).get("row_changes")
        if changes:
            print("\n".join([f"和上一次确认相比，规则卡有 {len(changes)} 行变化：", *change_lines(changes)]))
    elif args.confirm_item is not None:
        confirm_item(project, args.confirm_item)
    elif args.confirm_b12 is not None:
        confirm_b12(project, args.confirm_b12)
    elif args.tick is not None:
        tick_item(project, args.tick)
    elif args.not_applicable is not None:
        mark_not_applicable(project, args.not_applicable, args.reason)
    elif args.add_source is not None:
        result = add_source(project, args.add_source, args.kind, copy=not args.no_copy)
        if result["reopened"]:
            print(f"已重开阶段 {'、'.join(map(str, result['reopened']))}：重新提取，按新来源依次核对规则卡、"
                  "招标文件格式规定、事实卡、资源卡和大纲后重新确认；失效的中间稿逐项重新确认。")
    elif args.add_resource is not None:
        result = add_resource(project, args.add_resource)
        reopened = f"已重开阶段 {'、'.join(map(str, result['reopened']))}。" if result["reopened"] else ""
        print(f"已登记公司资源资料：重新运行 index_materials.py --project 编目，核对资源卡后重新确认，"
              f"再重新确认大纲；失效的中间稿逐项重新确认。{reopened}")
    elif args.start is not None:
        start_stage(project, args.start)
    elif args.complete is not None:
        complete_stage(project, args.complete)
    elif args.reopen is not None:
        reopen_stage(project, args.reopen)
    project_dir, state = load_project(project)
    return render_summary(project_dir, state), 0


def main() -> int:
    args = parse_args()
    try:
        output, code = run(args)
    except (OSError, ValueError) as exc:
        print(f"项目状态操作失败: {exc}", file=sys.stderr)
        return 2
    print(output)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
