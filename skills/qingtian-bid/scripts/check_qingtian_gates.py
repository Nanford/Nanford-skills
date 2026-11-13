"""Step-4 draft gates of qingtian-bid: run the content gates on one item or on every item, apply the reasons
the user gave for dismissing a hit, and report.

INPUT: <project>/project-state.json; analysis/response-matrix.json, rule-card.json, fact-card.json,
       resource-card.json and identity-terms.json; output/实施方案/NN-<评审内容原文>.md; review/gate-notes.json;
       the category knowledge cards the rule card selects (category_cards, for W9); the fact card's site
       limits (site_limits, for W10).
OUTPUT: item_gate_result() for writing_gate.check_item (--check-item / --confirm-item); full_run() for a
        whole-draft pass (check_qingtian_final runs it at stage 7); dismiss() records a user-stated reason in
        review/gate-notes.json; read_notes_file() / write_notes_file() / split_hits(), shared with the stage-7
        notes on the finished DOCX; a CLI that prints the hits (exit 1 while blocking hits remain).
POS: orchestrator of the step-4 Markdown gates (design v1 §9 第 4a 步) over text_gates, consistency_gates,
     check_content_quality and category_cards (W9, 第 5 步); W10 (第 6b 步) sits in text_gates. Levels follow gate-catalog.md: B blocks, W only
     hints until stage 7 (决策 4a-2A); B5 blocks on T-暗标 and hints elsewhere (D3). A blocking hit is fixed
     in the draft, except B4, B5, B7 and B13, whose catalog entry says 人工复核: the user may judge such a
     hit a false positive and give a reason (决策 4a-1A; B13 blocks on every track, an amount unrelated to
     the bid price takes a reason).
     W hits take a 不改理由 the same way. Each note is locked to the draft's sha256, so an edited draft is
     judged again. Notes keep no matched text, so names that B5 finds never land in a file.

review/gate-notes.json:
  {"schema": "qingtian-gate-notes/1",
   "notes": [{id, gate, item, kind: 误报|不改理由, reason, draft_sha256, recorded_at}]}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from category_cards import project_cards, w9_hits
from check_content_quality import w6_hits
from consistency_gates import (
    b1_hits,
    b4_hits,
    b9_hits,
    b9_landing_hits,
    b9_manual,
    b10_hits,
    b11_hits,
    w1_hits,
)
from project_cards import file_sha256, load_project, now_text
from response_matrix import item_path, matrix_context, matrix_items, writing_inputs
from text_gates import (b5_hits, b7_hits, b8_hits, b13_hits, load_identity_terms, w2_hits, w3_hits, w4_hits, w7_hits,
                        w10_hits)

NOTES_FILE = "review/gate-notes.json"
NOTES_SCHEMA = "qingtian-gate-notes/1"
# 门禁目录里判定方式写了"人工复核"的阻断项：误报可以说明理由放行（决策 4a-1A）
REVIEWED_BLOCKS = ("B4", "B5", "B7", "B13")
W4_LIMIT = "W4 只在本机比对规范写法和各项之间的整句，查不到网络文本（R26）"


def hit_id(gate: str, no: int, match: str) -> str:
    """门禁、项号、命中文字定出编号：同一处稿件不改，编号就不变；B4 的参照值也在 match 里。"""
    return hashlib.sha256(f"{gate}|{no}|{match}".encode("utf-8")).hexdigest()[:10]


def finalize(raw: list[dict], no: int, track: str) -> list[dict]:
    """补上编号、级别和能否放行；同一处多次命中合并计数。"""
    hits: dict[str, dict] = {}
    for entry in raw:
        identifier = hit_id(entry["gate"], no, entry["match"])
        if identifier in hits:
            hits[identifier]["count"] += 1
            continue
        gate = entry["gate"]
        warn = gate.startswith("W") or (gate == "B5" and track != "T-暗标")
        dismissable = not entry.get("fixed") and (gate.startswith("W") or gate in REVIEWED_BLOCKS)
        hits[identifier] = {**entry, "id": identifier, "item": no, "level": "warn" if warn else "block",
                            "dismissable": dismissable, "count": 1}
    return list(hits.values())


def identity_terms(project_dir: Path) -> tuple[list[dict] | None, str]:
    try:
        return load_identity_terms(project_dir), ""
    except ValueError as exc:
        return None, str(exc)


def other_drafts(project_dir: Path, items: dict[int, dict], no: int) -> dict[int, str]:
    texts = {}
    for other, item in items.items():
        path = item_path(project_dir, other, str(item.get("title") or ""))
        if other != no and path.is_file():
            texts[other] = path.read_text(encoding="utf-8")
    return texts


def raw_item_hits(project_dir: Path, inputs: dict, no: int, text: str) -> tuple[list[dict], list[str]]:
    items = matrix_items(inputs)
    item, rule_card = items[no], inputs["rule_card"]
    context = matrix_context(rule_card, inputs["fact_card"], inputs["resource_card"])
    cited = [context["facts"][ref] for ref in item.get("facts") or [] if ref in context["facts"]]
    clauses = [context["mandatory"][ref] for ref in item.get("mandatory") or [] if ref in context["mandatory"]]
    others = other_drafts(project_dir, items, no)
    terms, list_error = identity_terms(project_dir)
    hits = b5_hits(text, terms, list_error) + b7_hits(text, rule_card, inputs["fact_card"], terms) + b8_hits(text)
    hits += b4_hits(text, inputs, others) + b9_hits(text, clauses) + b10_hits(text, inputs["resource_card"])
    hits += b11_hits(text, no, inputs["matrix"]) + b13_hits(text) + w1_hits(text, item, cited) + w2_hits(text)
    title = str(item.get("title") or "")
    hits += w3_hits(text) + w4_hits(text, others) + w6_hits(text) + w7_hits(text, title, cited)
    # 类别知识卡的必备要点：只提示，矩阵里删掉的不再提示（决策 5-4A，第 6b 步改）
    hits += w9_hits(text, title, project_cards(rule_card)[0], list(item.get("control_points") or []))
    hits += w10_hits(text, inputs["fact_card"])  # 与确认过的现场限制矛盾：只提示（第 6b 步）
    return hits, b9_manual(clauses) + [W4_LIMIT]


def track_of(inputs: dict) -> str:
    return str((inputs["rule_card"].get("track") or {}).get("value") or "")


def read_notes_file(project_dir: Path, relative: str, schema: str) -> list[dict]:
    """说明文件（中间稿的 gate-notes.json、成品的 final-gate-notes.json）：没有就是空的，格式不对就报错。"""
    path = project_dir / relative
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{relative} 读不出来: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != schema or not isinstance(data.get("notes"), list):
        raise ValueError(f"{relative} 须是 schema {schema}，notes 为列表")
    return [note for note in data["notes"] if isinstance(note, dict)]


def write_notes_file(project_dir: Path, relative: str, schema: str, notes: list[dict]) -> None:
    path = project_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": schema, "notes": notes}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def split_hits(hits: list[dict], valid: dict) -> dict:
    """按此刻有效的说明（编号 → 说明）把命中分成阻断、提示、已说明；不能放行的命中写了说明也不算。"""
    noted = [{**entry, "note": valid[entry["id"]]} for entry in hits if entry["dismissable"] and entry["id"] in valid]
    rest = [entry for entry in hits if not (entry["dismissable"] and entry["id"] in valid)]
    return {"blocking": [entry for entry in rest if entry["level"] == "block"],
            "warnings": [entry for entry in rest if entry["level"] == "warn"], "noted": noted}


def load_notes(project_dir: Path) -> list[dict]:
    return read_notes_file(project_dir, NOTES_FILE, NOTES_SCHEMA)


def apply_notes(hits: list[dict], notes: list[dict], no: int, sha: str) -> dict:
    """说明只对写下它时的那版稿件有效（决策 4a-1A）。"""
    valid = {note.get("id"): note for note in notes if note.get("item") == no and note.get("draft_sha256") == sha}
    stale = sum(1 for note in notes if note.get("item") == no and note.get("draft_sha256") != sha)
    return {**split_hits(hits, valid), "stale_notes": stale}


def empty_result() -> dict:
    return {"blocking": [], "warnings": [], "noted": [], "stale_notes": 0, "manual": []}


def item_hits(project_dir: Path, inputs: dict, no: int) -> tuple[list[dict], list[str], Path]:
    item = matrix_items(inputs)[no]
    path = item_path(project_dir, no, str(item.get("title") or ""))
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not text.strip():
        return [], [], path
    raw, manual = raw_item_hits(project_dir, inputs, no, text)
    return finalize(raw, no, track_of(inputs)), manual, path


def item_gate_result(project_dir: Path, inputs: dict, no: int) -> dict:
    """一项中间稿的内容门禁。B 级未放行的命中挡住 --confirm-item；W 级只提示，阶段 7 统一处理（决策 4a-2A）。"""
    hits, manual, path = item_hits(project_dir, inputs, no)
    if not hits and not manual:  # 中间稿缺失或为空：结构检查已经报了，这里不再跑
        return empty_result()
    return {**apply_notes(hits, load_notes(project_dir), no, file_sha256(path)), "manual": manual}


def save_notes(project_dir: Path, notes: list[dict]) -> None:
    write_notes_file(project_dir, NOTES_FILE, NOTES_SCHEMA, notes)


def dismiss(project_dir: Path, no: int, identifier: str, reason: str) -> dict:
    """记下用户对一条命中的判断和理由。只在用户明确说明理由后调用，不得替用户编理由。"""
    if not reason.strip():
        raise ValueError("理由不能为空：写用户说明的理由")
    project_dir, _ = load_project(project_dir)
    inputs = writing_inputs(project_dir)
    if no not in matrix_items(inputs):
        raise ValueError(f"响应矩阵里没有第 {no} 项")
    hits, _, path = item_hits(project_dir, inputs, no)
    target = next((entry for entry in hits if entry["id"] == identifier), None)
    if target is None:
        raise ValueError(f"第 {no} 项当前没有编号为 {identifier} 的命中：先 --check-item {no} 看最新结果")
    if not target["dismissable"]:
        raise ValueError(f"{target['gate']} 的这条命中不能放行，只能改稿：{target['message']}")
    note = {"id": identifier, "gate": target["gate"], "item": no,
            "kind": "误报" if target["level"] == "block" else "不改理由", "reason": reason.strip(),
            "draft_sha256": file_sha256(path), "recorded_at": now_text()}
    notes = [entry for entry in load_notes(project_dir) if not (entry.get("item") == no and entry.get("id") == identifier)]
    save_notes(project_dir, notes + [note])
    return note


def full_run(project_dir: Path) -> dict:
    """整份中间稿：逐项门禁，加 B1 全覆盖和 B9 全部落点。不改状态。"""
    project_dir, _ = load_project(project_dir)
    inputs = writing_inputs(project_dir)
    items = matrix_items(inputs)
    texts = {no: (path.read_text(encoding="utf-8") if path.is_file() else "")
             for no, path in ((no, item_path(project_dir, no, str(item.get("title") or ""))) for no, item in items.items())}
    whole = finalize(b1_hits(project_dir, items, texts) + b9_landing_hits(inputs["rule_card"], items), 0, track_of(inputs))
    return {"project": str(project_dir), "whole": whole,
            "items": {no: item_gate_result(project_dir, inputs, no) for no in sorted(items) if texts[no].strip()}}


def hit_line(entry: dict) -> str:
    times = f"（{entry['count']} 处）" if entry.get("count", 1) > 1 else ""
    return f"- {entry['gate']} [{entry['id']}] {entry['message']}{times}"


def result_lines(result: dict) -> list[str]:
    """一项的门禁结果：阻断、提示、已说明、人工核对。"""
    lines = []
    if result["blocking"]:
        lines += [f"阻断 {len(result['blocking'])} 条（改稿；B4、B5、B7、B13 经用户复核确属误报的，按用户说明的理由记录后放行）："]
        lines += [hit_line(entry) for entry in result["blocking"]]
    if result["warnings"]:
        lines += [f"提示 {len(result['warnings'])} 条（W 项不挡确认，阶段 7 逐条改或写明不改的理由）："]
        lines += [hit_line(entry) for entry in result["warnings"]]
    if result["noted"]:
        lines += [f"已说明 {len(result['noted'])} 条："]
        lines += [f"{hit_line(entry)}（{entry['note']['kind']}：{entry['note']['reason']}）" for entry in result["noted"]]
    if result["stale_notes"]:
        lines.append(f"另有 {result['stale_notes']} 条说明因稿件修改失效，命中已重新判定")
    lines += [f"人工核对：{text}" for text in result["manual"]]
    return lines


def full_run_text(result: dict) -> tuple[str, int]:
    lines = [f"门禁全量检查：{result['project']}"]
    if result["whole"]:
        lines += ["整份："] + [hit_line(entry) for entry in result["whole"]]
    for no, item_result in result["items"].items():
        lines += [f"第 {no} 项："] + (result_lines(item_result) or ["- 无命中"])
    blocking = len(result["whole"]) + sum(len(item["blocking"]) for item in result["items"].values())
    lines.append(f"合计阻断 {blocking} 条。" if blocking else "没有阻断项。")
    return "\n".join(lines), 1 if blocking else 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="qingtian-bid 第 4 步稿件门禁：逐项或整份检查，记录误报和不改理由。")
    parser.add_argument("project_dir", type=Path, help="项目目录（bid-projects/ 下）。")
    parser.add_argument("--item", type=int, metavar="N", help="只查第 N 项；--dismiss 时必填。")
    parser.add_argument("--dismiss", metavar="编号", help="记下用户对这条命中的判断（B4/B5/B7/B13 误报或 W 不改理由）。")
    parser.add_argument("--reason", default="", help="--dismiss 的理由，写用户说明的原话。")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> tuple[str, int]:
    if args.dismiss:
        if args.item is None:
            raise ValueError("--dismiss 须同时给 --item N")
        note = dismiss(args.project_dir, args.item, args.dismiss, args.reason)
        return f"已记下第 {args.item} 项 {note['gate']} [{note['id']}]（{note['kind']}）：{note['reason']}", 0
    if args.item is not None:
        project_dir, _ = load_project(args.project_dir)
        inputs = writing_inputs(project_dir)
        if args.item not in matrix_items(inputs):
            raise ValueError(f"响应矩阵里没有第 {args.item} 项")
        result = item_gate_result(project_dir, inputs, args.item)
        return "\n".join(result_lines(result) or [f"第 {args.item} 项没有命中。"]), 1 if result["blocking"] else 0
    return full_run_text(full_run(args.project_dir))


def main(argv: list[str] | None = None) -> int:
    try:
        text, code = run(parse_args(argv))
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
