"""Stage-5 writing gate of qingtian-bid: one review item at a time, each confirmed by the user.

INPUT: <project>/project-state.json; analysis/response-matrix.json (the confirmed outline), rule-card.json,
       fact-card.json, resource-card.json; the drafts output/实施方案/NN-<评审内容原文>.md.
OUTPUT: per-item checks: structure (prerequisites, order, file, level-1 heading) plus the step-4 content
        gates, with a length hint; confirmation records writing.items.<no> in project-state.json; the
        stage-5 start and completion conditions; a progress summary.
POS: state layer of stage 5 (design v1 §9, 第 3c 步; content gates 第 4a 步). Each confirmation locks the
     draft's sha256 plus its own matrix row and the rule rows, facts and resources that row depends on (决策
     3c-2A, D9), so editing another row leaves it valid. check_item runs check_qingtian_gates on the draft: a B
     hit not dismissed with the user's reason blocks confirmation, W hits are shown as hints until stage 7
     (决策 4a-1A、4a-2A). Enforces 禁止跳章 (R12) and 资料空壳禁写 (R8): a resource card
     confirmed with gaps blocks the whole of stage 5, not item by item.

project-state.json keys owned here:
  writing.items.<no>   {file (relative to output/), sha256, row: digest, confirmed_at}
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from check_qingtian_gates import item_gate_result
from consistency_gates import heading_issues
from format_state import save_state
from project_cards import MATRIX_FILE, card_status, file_sha256, load_project, now_text, sha256_bytes
from response_matrix import (
    item_path,
    matrix_items,
    page_capacity,
    stage4_issues,
    writing_inputs,
)
from row_locks import MATRIX_CARD, cited_contents, row_deps
from rule_card_rows import row_content


def row_digest(inputs: dict, no: int) -> str:
    """这一项依赖的全部内容：矩阵这一行，加上它依赖的规则行、事实和资源此刻的内容（决策 3c-2A、D9）。
    矩阵行没写 cites 时依赖全部规则行（决策 D9-1A）。只比内容，上游改出处不连累已确认的稿子。"""
    item = matrix_items(inputs).get(no)
    if item is None:
        raise ValueError(f"响应矩阵里没有第 {no} 项")
    cited = {name: cited_contents(name, inputs[name], keys) for name, keys in row_deps(MATRIX_CARD, item).items()}
    return sha256_bytes(json.dumps([row_content(item), cited], ensure_ascii=False, sort_keys=True).encode("utf-8"))


def item_records(state: dict) -> dict:
    return (state.get("writing") or {}).get("items") or {}


def item_status(project_dir: Path, state: dict, no: int, inputs: dict) -> dict:
    """confirmed / stale / unconfirmed，附原因。"""
    record = item_records(state).get(str(no))
    if not record:
        return {"status": "unconfirmed", "reason": "未确认"}
    path = project_dir / "output" / record["file"]
    if not path.is_file():
        return {"status": "stale", "reason": f"确认过的中间稿不存在: {record['file']}"}
    if file_sha256(path) != record["sha256"]:
        return {"status": "stale", "reason": "确认后中间稿被修改，须重新自查并请用户确认"}
    try:
        current = row_digest(inputs, no)
    except ValueError as exc:
        return {"status": "stale", "reason": str(exc)}
    if current != record["row"]:
        return {"status": "stale", "reason": "确认后矩阵这一行或它引用的规则、事实、资源有变化，须按新大纲核对"}
    return {"status": "confirmed", "reason": f"已确认（{record['confirmed_at']}）"}


def outline_only_issues(state: dict) -> list[str]:
    record = (state.get("cards") or {}).get("resource_card") or {}
    if record.get("outline_only"):
        return ["资源卡有缺口：只许出大纲和缺口清单，补齐公司资料、重新确认资源卡和大纲后才能逐项撰写（R8）"]
    return []


def writing_issues(project_dir: Path, state: dict) -> list[str]:
    """逐项撰写的前提：阶段 4 已完成、大纲仍有效、资源卡没有缺口（R8）。也是阶段 5 的开始条件。"""
    issues = [] if state["stages"].get("4") == "done" else \
        ["阶段 4 响应矩阵未完成：大纲经用户确认、完成阶段 4 后才能逐项撰写（R12）"]
    issues += outline_only_issues(state)
    status = card_status(project_dir, state, "response_matrix")
    if status["status"] != "confirmed":
        issues.append(f"响应矩阵{status['reason']}：重新校验大纲并请用户确认")
    return issues


def earlier_issues(project_dir: Path, state: dict, inputs: dict, no: int) -> list[str]:
    pending = [str(earlier) for earlier in sorted(matrix_items(inputs)) if earlier < no
               and item_status(project_dir, state, earlier, inputs)["status"] != "confirmed"]
    return [f"第 {'、'.join(pending)} 项未确认或已失效：按顺序一项一确认，不跳项（R12）"] if pending else []


def written_ahead(project_dir: Path, state: dict, items: dict[int, dict], no: int) -> list[str]:
    """一次只写一项（R12）：后面的项有中间稿却从没确认过，就是提前写了。确认过、后来失效的不算，
    否则回头改前面的项时会被后面的项卡住。"""
    records = item_records(state)
    return [f"第 {later} 项的中间稿已经写了，但第 {no} 项还没确认：一次只写一项，先确认本项（R12）"
            for later, item in sorted(items.items()) if later > no and str(later) not in records
            and item_path(project_dir, later, str(item.get("title") or "")).is_file()]


def gate_issue(entry: dict) -> str:
    return f"{entry['gate']} [{entry['id']}] {entry['message']}"


def check_item(project_dir: Path, no: int) -> dict:
    """逐项自查：撰写前提、顺序、文件、一级标题，再跑内容门禁（第 4a 步），附篇幅提示。不改状态。
    B 级命中未经用户说明理由放行的，并入 issues，挡住确认；W 级和人工核对项放在 gates 里另列。"""
    project_dir, state = load_project(project_dir)
    inputs = writing_inputs(project_dir)
    items = matrix_items(inputs)
    if no not in items:
        raise ValueError(f"响应矩阵里没有第 {no} 项（共 {len(items)} 项）")
    item = items[no]
    path = item_path(project_dir, no, str(item.get("title") or ""))
    issues = writing_issues(project_dir, state) + earlier_issues(project_dir, state, inputs, no)
    issues += written_ahead(project_dir, state, items, no)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if text.strip():
        issues += heading_issues(text, no, str(item.get("title") or ""))
    else:
        issues.append(f"中间稿不存在或为空：output/{path.relative_to(project_dir / 'output').as_posix()}")
    gates = item_gate_result(project_dir, inputs, no)
    issues += [gate_issue(entry) for entry in gates["blocking"]]
    capacity, pages = page_capacity(state.get("document_format")), item.get("pages")
    budget = int(pages * capacity) if capacity and isinstance(pages, (int, float)) else None
    return {"issues": issues, "file": str(path), "chars": len(re.sub(r"\s", "", text)), "budget_chars": budget,
            "gates": gates}


def confirm_item(project_dir: Path, no: int) -> dict:
    """用户明确同意这一项后才调用；锁定中间稿和它在矩阵里的那一行（决策 3c-2A）。"""
    result = check_item(project_dir, no)
    if result["issues"]:
        raise ValueError(f"第 {no} 项还有 {len(result['issues'])} 个问题，不能确认：{result['issues'][0]}")
    project_dir, state = load_project(project_dir)
    path = Path(result["file"])
    record = {"file": path.relative_to(project_dir / "output").as_posix(), "sha256": file_sha256(path),
              "row": row_digest(writing_inputs(project_dir), no), "confirmed_at": now_text()}
    state.setdefault("writing", {}).setdefault("items", {})[str(no)] = record
    if state["stages"].get("5") == "pending":
        state["stages"]["5"] = "in-progress"
    save_state(project_dir, state)
    return {"project": str(project_dir), "item": no, "file": record["file"]}


def stage5_start_issues(project_dir: Path, state: dict) -> list[str]:
    return writing_issues(project_dir, state)


def stage5_issues(project_dir: Path, state: dict) -> list[str]:
    """阶段 5 完成条件：资源卡没有缺口；阶段 3、4 的卡片和大纲仍成立；每一项都已确认且未失效。"""
    issues = outline_only_issues(state) + stage4_issues(project_dir, state)
    if issues:
        return issues
    inputs = writing_inputs(project_dir)
    for no in sorted(matrix_items(inputs)):
        status = item_status(project_dir, state, no, inputs)
        if status["status"] != "confirmed":
            issues.append(f"第 {no} 项{status['reason']}：--check-item {no} 自查，用户同意后 --confirm-item {no}")
    return issues


def writing_summary(project_dir: Path, state: dict) -> str:
    if not (project_dir / MATRIX_FILE).is_file():
        return "—"
    try:
        inputs = writing_inputs(project_dir)
    except ValueError as exc:
        return str(exc)
    items = matrix_items(inputs)
    done = sum(1 for no in items if item_status(project_dir, state, no, inputs)["status"] == "confirmed")
    return f"已确认 {done}/{len(items)} 项"
