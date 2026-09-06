"""Show or update bid project stage progress for resumable work.

INPUT: bid-projects/<project> directory containing project-state.json
       (created by prepare_project.py), optional --start/--complete/--reopen N,
       and writing-gate flags (--confirm-outline / --confirm-section).
OUTPUT: console summary (per-stage status, writing outline/section progress,
        next actionable stage, its guide file) and the updated project-state.json
        when a transition is applied.
POS: cross-stage progress tracker for the bid-preparation skill —
     断点续作入口：新会话先运行本脚本即可知道"做到哪、下一步干什么、读哪份细则"。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


STATE_FILENAME = "project-state.json"
VALID_STATUSES = {"pending", "in-progress", "done", "skipped"}
VALID_OUTLINE_KINDS = {"business", "technical"}

STAGE_LABELS = {
    0: "项目初始化",
    1: "文本提取",
    2: "解标分析",
    3: "资料收集与匹配",
    4: "编制商务文件",
    5: "编制技术文件",
    6: "生成导航表并组装成品DOCX",
    7: "合规审查与交付",
}

STAGE_GUIDES = {
    0: "references/stage-0-init.md",
    1: "references/stage-1-extract.md",
    2: "references/stage-2-analysis.md",
    3: "references/stage-3-materials.md",
    4: "references/stage-4-business.md",
    5: "references/stage-5-technical.md",
    6: "references/stage-6-assembly.md",
    7: "references/stage-7-review.md",
}

STATUS_ICONS = {
    "pending": "○ 待办",
    "in-progress": "◐ 进行中",
    "done": "● 完成",
    "skipped": "— 跳过",
}


def default_writing_state(scope: str = "full") -> dict:
    """写作闸状态：大纲确认 + 逐章确认进度（阶段4/5硬门禁）。"""
    return {
        "business_outline_confirmed": scope == "technical-only",
        "technical_outline_confirmed": False,
        "business_sections_done": [],
        "technical_sections_done": [],
        "current_part": None,  # business | technical
        "current_section": None,
    }


def ensure_writing_state(state: dict) -> dict:
    """兼容旧版 project-state.json：缺 writing 字段时补齐。"""
    scope = state.get("scope", "full")
    writing = state.get("writing")
    if not isinstance(writing, dict):
        state["writing"] = default_writing_state(scope)
        return state["writing"]
    defaults = default_writing_state(scope)
    for key, value in defaults.items():
        if key not in writing:
            writing[key] = value
    return writing


def load_state(project_dir: Path) -> dict:
    state_path = project_dir / STATE_FILENAME
    if not state_path.exists():
        raise SystemExit(
            f"状态文件不存在: {state_path}\n"
            "该项目可能创建于旧版本。重建方法：运行 prepare_project.py 新建项目，"
            "或手动创建 project-state.json（结构见 prepare_project.py 的 write_initial_state）。"
        )
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"状态文件无法解析: {state_path} ({exc})，请修复或重建后重试。")
    if not isinstance(state.get("stages"), dict):
        raise SystemExit(f"状态文件缺少 stages 字段: {state_path}")
    ensure_writing_state(state)
    return state


def save_state(project_dir: Path, state: dict) -> None:
    ensure_writing_state(state)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    (project_dir / STATE_FILENAME).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def apply_transition(state: dict, stage: int, new_status: str) -> None:
    key = str(stage)
    if key not in state["stages"]:
        raise SystemExit(f"未知阶段编号: {stage}（有效范围 0-7）")
    if state["stages"][key] == "skipped" and new_status == "done":
        raise SystemExit(
            f"阶段{stage}（{STAGE_LABELS[stage]}）已按生成范围标记为跳过，无需完成；"
            "如需执行请先 --reopen 该阶段。"
        )
    state["stages"][key] = new_status


def confirm_outline(state: dict, kind: str) -> None:
    if kind not in VALID_OUTLINE_KINDS:
        raise SystemExit(f"大纲类型无效: {kind}（可选: business / technical）")
    writing = ensure_writing_state(state)
    if kind == "business":
        writing["business_outline_confirmed"] = True
    else:
        writing["technical_outline_confirmed"] = True
    writing["current_part"] = kind
    writing["current_section"] = None


def confirm_section(state: dict, kind: str, section: str) -> None:
    if kind not in VALID_OUTLINE_KINDS:
        raise SystemExit(f"大纲类型无效: {kind}（可选: business / technical）")
    section = section.strip()
    if not section:
        raise SystemExit("章节名称不能为空")
    writing = ensure_writing_state(state)
    key = "business_sections_done" if kind == "business" else "technical_sections_done"
    done = writing.setdefault(key, [])
    if section not in done:
        done.append(section)
    writing["current_part"] = kind
    writing["current_section"] = section


def next_actionable_stage(state: dict) -> int | None:
    for stage in range(8):
        if state["stages"].get(str(stage)) in {"pending", "in-progress"}:
            return stage
    return None


def render_writing_progress(state: dict) -> list[str]:
    writing = ensure_writing_state(state)
    scope = state.get("scope", "full")
    lines = ["写作闸进度："]
    if scope == "full":
        biz = "已确认" if writing.get("business_outline_confirmed") else "待确认"
        lines.append(f"  商务大纲：{biz}")
        biz_done = writing.get("business_sections_done") or []
        if biz_done:
            lines.append(f"  商务已确认章节（{len(biz_done)}）：{'；'.join(biz_done)}")
        else:
            lines.append("  商务已确认章节：无")
    tech = "已确认" if writing.get("technical_outline_confirmed") else "待确认"
    lines.append(f"  技术大纲：{tech}")
    tech_done = writing.get("technical_sections_done") or []
    if tech_done:
        lines.append(f"  技术已确认章节（{len(tech_done)}）：{'；'.join(tech_done)}")
    else:
        lines.append("  技术已确认章节：无")
    current_part = writing.get("current_part")
    current_section = writing.get("current_section")
    if current_part or current_section:
        lines.append(f"  最近写作：{current_part or '-'} / {current_section or '-'}")
    return lines


def render_procurement_reminders(state: dict) -> list[str]:
    """P3：按采购体系/方式提醒本项目必做的核对表，避免新会话接手时漏掉政采得分项。"""
    system = state.get("procurement_system", "unset")
    mode = state.get("procurement_mode", "unset")
    reminders: list[str] = []
    if system == "gov":
        reminders.append("  ⚠ 政府采购：须有 analysis/gov-policy-checklist.md（价格扣除/强制节能/信用查询）")
    if mode in {"competitive_consultation", "competitive_negotiation", "inquiry_single"}:
        reminders.append("  ⚠ 磋商/谈判类：须有 analysis/consultation-strategy.md；全文用「响应文件/供应商/成交」")
    if state.get("award_mode") == "evaluation_separated":
        reminders.append(
            "  ⚠ 评定分离：投标文件须拆「评标部分」「定标部分」两本分别编制上传；答辩人缺席即弃权"
        )
    if state.get("project_type") == "construction_epc":
        reminders.append("  ⚠ 工程总承包：建造师/安全B证/注册建筑师人证绑定；接受联合体时填 consortium-plan.md")
    if system == "unset" or mode == "unset":
        reminders.append("  ⚠ 采购体系/方式未判定：阶段2 须判定并请用户确认，否则可能漏掉政采专属得分项")
    return reminders


def render_summary(state: dict) -> str:
    ptype = state.get("project_type", "unset")
    delivery = state.get("delivery_mode", "unset")
    system = state.get("procurement_system", "unset")
    mode = state.get("procurement_mode", "unset")
    lines = [
        f"项目：{state.get('project_name', '（未命名）')}",
        f"生成范围：{state.get('scope', 'full')}　最近更新：{state.get('updated_at', '')}",
        f"采购体系：{system}　采购方式：{mode}",
        f"项目类型：{ptype}　递交方式：{delivery}",
        *render_procurement_reminders(state),
        "",
    ]
    for stage in range(8):
        status = state["stages"].get(str(stage), "pending")
        icon = STATUS_ICONS.get(status, status)
        lines.append(f"  阶段{stage} {STAGE_LABELS[stage]}：{icon}")
    lines.append("")
    lines.extend(render_writing_progress(state))
    lines.append("")
    upcoming = next_actionable_stage(state)
    if upcoming is None:
        lines.append("全部阶段已完成/跳过。交付前确认人工核查清单已逐项处理。")
    else:
        lines.append(
            f"下一步 → 阶段{upcoming}（{STAGE_LABELS[upcoming]}），"
            f"先读细则: {STAGE_GUIDES[upcoming]}"
        )
        if upcoming in {4, 5}:
            writing = ensure_writing_state(state)
            if upcoming == 4 and not writing.get("business_outline_confirmed"):
                lines.append("  提示：阶段4须先输出商务大纲并经用户确认，再逐件套编制。")
            if upcoming == 5 and not writing.get("technical_outline_confirmed"):
                lines.append("  提示：阶段5须先输出技术大纲并经用户确认，再逐章编制。")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show or update bid project stage progress.")
    parser.add_argument("project_dir", type=Path, help="Project directory under bid-projects.")
    transition = parser.add_mutually_exclusive_group()
    transition.add_argument("--start", type=int, metavar="N", help="标记阶段N为进行中.")
    transition.add_argument("--complete", type=int, metavar="N", help="标记阶段N为完成.")
    transition.add_argument("--reopen", type=int, metavar="N", help="重开阶段N（回到待办）.")
    transition.add_argument(
        "--confirm-outline",
        choices=sorted(VALID_OUTLINE_KINDS),
        help="标记商务/技术大纲已获用户确认.",
    )
    transition.add_argument(
        "--confirm-section",
        choices=sorted(VALID_OUTLINE_KINDS),
        help="标记某章/件套已获用户确认（须配合 --section）.",
    )
    parser.add_argument(
        "--section",
        default="",
        help="与 --confirm-section 联用：章节或件套名称（与大纲表一致）.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()
    if not project_dir.exists():
        raise SystemExit(f"项目目录不存在: {project_dir}")
    state = load_state(project_dir)
    if args.start is not None:
        apply_transition(state, args.start, "in-progress")
        save_state(project_dir, state)
    elif args.complete is not None:
        apply_transition(state, args.complete, "done")
        save_state(project_dir, state)
    elif args.reopen is not None:
        apply_transition(state, args.reopen, "pending")
        save_state(project_dir, state)
    elif args.confirm_outline is not None:
        confirm_outline(state, args.confirm_outline)
        save_state(project_dir, state)
    elif args.confirm_section is not None:
        if not args.section.strip():
            raise SystemExit("--confirm-section 必须同时提供 --section 章节名称")
        confirm_section(state, args.confirm_section, args.section)
        save_state(project_dir, state)
    print(render_summary(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
