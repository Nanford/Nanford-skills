"""Show or update bid project stage progress for resumable work.

INPUT: bid-projects/<project> directory containing project-state.json
       (created by prepare_project.py), optional --start/--complete/--reopen N.
OUTPUT: console summary (per-stage status, next actionable stage, its guide
        file) and the updated project-state.json when a transition is applied.
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

STATUS_ICONS = {"pending": "○ 待办", "in-progress": "◐ 进行中", "done": "● 完成", "skipped": "— 跳过"}


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
    return state


def save_state(project_dir: Path, state: dict) -> None:
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


def next_actionable_stage(state: dict) -> int | None:
    for stage in range(8):
        if state["stages"].get(str(stage)) in {"pending", "in-progress"}:
            return stage
    return None


def render_summary(state: dict) -> str:
    lines = [
        f"项目：{state.get('project_name', '（未命名）')}",
        f"生成范围：{state.get('scope', 'full')}　最近更新：{state.get('updated_at', '')}",
        "",
    ]
    for stage in range(8):
        status = state["stages"].get(str(stage), "pending")
        icon = STATUS_ICONS.get(status, status)
        lines.append(f"  阶段{stage} {STAGE_LABELS[stage]}：{icon}")
    lines.append("")
    upcoming = next_actionable_stage(state)
    if upcoming is None:
        lines.append("全部阶段已完成/跳过。交付前确认人工核查清单已逐项处理。")
    else:
        lines.append(
            f"下一步 → 阶段{upcoming}（{STAGE_LABELS[upcoming]}），"
            f"先读细则: {STAGE_GUIDES[upcoming]}"
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show or update bid project stage progress.")
    parser.add_argument("project_dir", type=Path, help="Project directory under bid-projects.")
    transition = parser.add_mutually_exclusive_group()
    transition.add_argument("--start", type=int, metavar="N", help="标记阶段N为进行中.")
    transition.add_argument("--complete", type=int, metavar="N", help="标记阶段N为完成.")
    transition.add_argument("--reopen", type=int, metavar="N", help="重开阶段N（回到待办）.")
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
    print(render_summary(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
