"""类人评审预演的记录和状态（第 1c 步，决策 D13、2B）。

INPUT: <project>/project-state.json；analysis/response-matrix.json（找中间稿）；output/实施方案/NN-<评审内容原文>.md；
       output/施工组织设计.docx；--record 指向的 JSON；review/rehearsal/*.json。
OUTPUT: review/rehearsal/NN.json、final.json；rehearsal_line() 给阶段 5 自查和阶段 7 门禁显示的一行；命令行的记录和总览。
POS: 只记"做没做、稿子改没改、记下了哪些薄弱点"，不判断做得好不好，不出分数和档次。预演本身由 agent 按
     references/rehearsal.md 做。不是门禁：不进 check_item 的 issues、final_run 的 ready，也不是任何阶段的完成
     条件。只依赖 project_cards 和 response_matrix，免得和状态闸、门禁循环引用。

review/rehearsal/NN.json:
  {"schema": "qingtian-rehearsal/1", "item": N, "draft_sha256", "recorded_at", "reviewer": 同一会话|新会话|子代理,
   "weak_points": {"locate": [...], "extract": [...], "reason": [...]}}
review/rehearsal/final.json 结构相同："item" 是 "final"，sha 字段是 "docx_sha256"。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from project_cards import FINISHED_DOCX, file_sha256, load_json, load_project, now_text
from response_matrix import item_path, matrix_items, writing_inputs

REHEARSAL_DIR = "review/rehearsal"
RECORD_SCHEMA = "qingtian-rehearsal/1"
FINAL_TARGET = "final"
Target = int | str  # 第 N 项，或 FINAL_TARGET
REVIEWERS = ("同一会话", "新会话", "子代理")
WEAK_POINT_LABELS = {"locate": "定位不到", "extract": "摘不出", "reason": "写不出理由"}
INPUT_FIELDS = {"reviewer", "weak_points"}
# 放不下一段稿件原文的长度：记录只写薄弱点在哪、缺什么，不把稿件贴进来
MAX_ENTRY_CHARS = 200
DONE, STALE, UNREADABLE, NOT_DONE = "已做", "稿件已改要重做", "记录读不出", "未做"
# 分数和档次判断。没有人见过青天的真实分数，预演写出来的分没有依据。用肯定式的后缀来判断：数字加"分"后面要是
# 标点、结尾或"以上"一类的词，优秀、良好、一般后面要是标点、结尾或"档"，这样 70分贝、30分钟、取得分部验收、
# 达到良好效果、属于一般性描述都不会误报
SCORE_WORDS = re.compile(
    r"优秀档|良好档|一般档|档次|打分|估分|(?<!百)分数|得分(?![部项包期段])"
    r"|(?:评为|评到|够得上|够不上|达不到|达到|属于|算得上|能拿)(?:优秀|良好|一般)(?=$|[\s，。；、,.;:：）)]|档|水平|等级)"
    r"|\d+(?:\.\d+)?\s*分(?=$|[\s，。；、,.;:：）)]|以上|以下|左右|上下|及以上|及以下|的|档)")


def record_name(target: Target) -> str:
    return "final.json" if target == FINAL_TARGET else f"{target:02d}.json"


def sha_key(target: Target) -> str:
    return "docx_sha256" if target == FINAL_TARGET else "draft_sha256"


def target_label(target: Target) -> str:
    return "成品" if target == FINAL_TARGET else f"第 {target} 项"


def not_blocking(target: Target) -> str:
    return "不挡阶段 7" if target == FINAL_TARGET else "不挡确认"


def target_source(project_dir: Path, target: Target) -> Path:
    """预演看的那份稿：第 N 项的中间稿，或成品。"""
    if target == FINAL_TARGET:
        return project_dir / FINISHED_DOCX
    items = matrix_items(writing_inputs(project_dir))
    if target not in items:
        raise ValueError(f"响应矩阵里没有第 {target} 项（共 {len(items)} 项）")
    return item_path(project_dir, target, str(items[target].get("title") or ""))


# ---------- 记录 ----------

def entry_issues(entries: object, label: str) -> list[str]:
    if not isinstance(entries, list):
        return [f"{label}：要写成列表，没有就写空列表"]
    issues = []
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, str) or not entry.strip():
            issues.append(f"{label}第 {index} 条是空的")
            continue
        if len(entry) > MAX_ENTRY_CHARS:
            issues.append(f"{label}第 {index} 条超过 {MAX_ENTRY_CHARS} 字：只写薄弱点在哪、缺什么，不贴稿件原文")
        found = SCORE_WORDS.search(entry)
        if found:
            issues.append(f"{label}第 {index} 条写了分数或档次判断（“{found.group()}”）：预演不出分数和档次，改成写缺什么")
    return issues


def record_issues(record: dict) -> list[str]:
    """预演记录的问题。多余的字段也拒绝，免得 score 之类的字段被悄悄丢掉、以为记下了。"""
    issues = [f"不记这个字段：{name}" for name in sorted(set(record) - INPUT_FIELDS)]
    if record.get("reviewer") not in REVIEWERS:
        issues.append(f"reviewer 只能是 {'、'.join(REVIEWERS)}")
    weak = record.get("weak_points")
    if not isinstance(weak, dict) or set(weak) != set(WEAK_POINT_LABELS):
        return issues + [f"weak_points 要有且只有 {'、'.join(WEAK_POINT_LABELS)} 三个列表"]
    for key, label in WEAK_POINT_LABELS.items():
        issues += entry_issues(weak[key], label)
    return issues


def record_rehearsal(project_dir: Path, target: Target, source_json: Path) -> dict:
    """把一次预演存下来，锁定此刻稿件的 sha256。稿件一改，这条记录就显示要重做。"""
    project_dir, _ = load_project(project_dir)
    record = load_json(source_json, "预演记录")
    issues = record_issues(record)
    if issues:
        raise ValueError("预演记录不符合要求：\n" + "\n".join(f"- {item}" for item in issues))
    source = target_source(project_dir, target)
    if not source.is_file():
        raise ValueError(f"{target_label(target)}还没有稿件：{source}")
    saved = {"schema": RECORD_SCHEMA, "item": target, sha_key(target): file_sha256(source), "recorded_at": now_text(),
             "reviewer": record["reviewer"],
             "weak_points": {key: [entry.strip() for entry in record["weak_points"][key]] for key in WEAK_POINT_LABELS}}
    path = project_dir / REHEARSAL_DIR / record_name(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return saved


# ---------- 状态 ----------

def read_record(path: Path) -> dict | None:
    """读不出、格式不对或手改得不符合要求的都返回 None：记录坏了不能拖累自查和门禁。"""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("schema") != RECORD_SCHEMA:
        return None
    return None if record_issues({key: record.get(key) for key in INPUT_FIELDS}) else record


def rehearsal_status(project_dir: Path, target: Target) -> dict:
    """{status: 已做 / 稿件已改要重做 / 记录读不出 / 未做, record?}。"""
    path = project_dir / REHEARSAL_DIR / record_name(target)
    if not path.is_file():
        return {"status": NOT_DONE}
    record = read_record(path)
    if record is None:
        return {"status": UNREADABLE}
    source = target_source(project_dir, target)
    if not source.is_file() or file_sha256(source) != record.get(sha_key(target)):
        return {"status": STALE, "record": record}
    return {"status": DONE, "record": record}


def done_text(record: dict, target: Target) -> str:
    weak = record["weak_points"]
    total = sum(len(entries) for entries in weak.values())
    counts = "，".join(f"{label} {len(weak[key])}" for key, label in WEAK_POINT_LABELS.items())
    blind_spot = "；同一会话有盲区，最好换新会话或子代理" if record["reviewer"] == "同一会话" else ""
    who = f"{record['reviewer']}，{record['recorded_at']}{blind_spot}"
    if not total:
        return f"已做（{who}），没有记下薄弱点。没记下不等于稿子没问题。"
    return (f"已做（{who}），薄弱点 {total} 条（{counts}），见 {REHEARSAL_DIR}/{record_name(target)}。"
            "只是提示，不是分数；原文告诉用户，改不改由用户定。")


def rehearsal_line(project_dir: Path, target: Target) -> str:
    """阶段 5 自查和阶段 7 门禁结果里显示的一行。"""
    status = rehearsal_status(project_dir, target)
    prefix = f"类人评审预演（{target_label(target)}）："
    if status["status"] == DONE:
        return prefix + done_text(status["record"], target)
    if status["status"] == STALE:
        return prefix + f"记录是旧稿上的，稿件已改，要重做才算数（{not_blocking(target)}）。"
    if status["status"] == UNREADABLE:
        return prefix + f"记录读不出或不符合要求，按没做算，要重做（{not_blocking(target)}）。"
    return prefix + f"还没做。按 references/rehearsal.md 做一遍，不做也{not_blocking(target)}。"


# ---------- 命令行 ----------

def detail_text(project_dir: Path, target: Target) -> str:
    record = rehearsal_status(project_dir, target).get("record")
    lines = [rehearsal_line(project_dir, target)]
    for key, label in WEAK_POINT_LABELS.items():
        lines += [f"- {label}：{entry}" for entry in (record["weak_points"][key] if record else [])]
    return "\n".join(lines)


def overview_text(project_dir: Path) -> str:
    targets = [*sorted(matrix_items(writing_inputs(project_dir))), FINAL_TARGET]
    return "\n".join(["类人评审预演总览：只是提示，不是门禁，不出分数。",
                      *[rehearsal_line(project_dir, target) for target in targets]])


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="qingtian-bid 类人评审预演：存记录、看状态。只是提示，不是门禁，不出分数。"
                                                 "做法见 references/rehearsal.md。")
    parser.add_argument("project_dir", type=Path, help="项目目录（bid-projects/ 下）。")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--item", type=int, metavar="N", help="第 N 项中间稿。")
    target.add_argument("--final", action="store_true", help="成品。")
    parser.add_argument("--record", type=Path, metavar="JSON", help="把这份预演记录存下来，要配 --item 或 --final。")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> str:
    project_dir, _ = load_project(args.project_dir)
    target: Target | None = FINAL_TARGET if args.final else args.item
    if target is None:
        if args.record:
            raise ValueError("--record 要配 --item N 或 --final，说明这是哪一份稿的预演")
        return overview_text(project_dir)
    target_source(project_dir, target)  # 项号不对的，查看和记录都要报错
    if args.record:
        record_rehearsal(project_dir, target, args.record)
    return detail_text(project_dir, target)


def main(argv: list[str] | None = None) -> int:
    try:
        print(run(parse_args(argv)))
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
