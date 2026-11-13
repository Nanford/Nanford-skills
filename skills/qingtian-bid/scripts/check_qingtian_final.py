"""Stage-7 gates of qingtian-bid on the finished DOCX: run every gate, apply the user's reasons, write the gate report.

INPUT: <project>/project-state.json; output/施工组织设计.docx; the drafts, cards and identity-terms.json that
       check_qingtian_gates reads; review/page-count.json (report_page_numbers); review/final-gate-notes.json;
       review/rehearsal/final.json (rehearsal: shown as one line, never counted); build-report image hashes.
OUTPUT: final_run() → {docx_sha256, blocking, warnings, noted, b12, page_count, format, manual, rehearsal, ...};
        review/gate-report.json and review/gate-report.md (gate, id, level and place only); dismiss_final()
        records a user-stated reason for a hit on the finished DOCX, locked to its sha256; b12_rows() and
        b12_status() for final_gate; a CLI (exit 1 while blocking hits remain).
POS: orchestrator of stage 7 (design v1 §9 第 4b-2 步，选项 A), next to check_qingtian_gates (drafts only). One run
     gathers: the whole-draft gates (check_qingtian_gates.full_run, each note locked to its draft); B3 (the --final
     format check on the current file, so Word save → property clean → check can only happen in that order); B1 on
     the finished file's 一级标题 (catches headings edited, dropped or moved in Word; the builder gives the cover
     and TOC title their own styles, so only item headings are Heading 1); B2/W5 (a stored count of the same
     sha256 is reused, so a manual or PDF count is never overwritten by another failing automatic count); B6, B5
     and W8 (scan_docx_hygiene); a leftover --clean-properties backup in output/ (B5: it still holds the cleaned
     properties); B12, one hit per unconfirmed row of the 初步评审表 that concerns the 施组. Notes for hits on the
     finished file live in review/final-gate-notes.json, apart from the draft notes: a save in Word changes the
     DOCX sha256 and voids them without touching the draft notes. Files keep no matched text and no messages
     (决策 4a-1A: B5 messages quote what they found); messages are printed only.

review/final-gate-notes.json:
  {"schema": "qingtian-final-gate-notes/1",
   "notes": [{id, gate, kind: 误报|不改理由, reason, docx_sha256, recorded_at}]}
review/gate-report.json:
  {"schema": "qingtian-gate-report/1", docx, docx_sha256, checked_at, track, ready, summary, page_count, format,
   hits: [{id, gate, level, place, item, count, dismissable, status: open|noted, note?: {kind, reason}}],
   b12: [{row, stage, factor, status}], manual: [...]}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, NoReturn

from check_qingtian_gates import finalize, full_run, hit_id, read_notes_file, split_hits, track_of, write_notes_file
from docx_effective_format import W
from project_cards import FINISHED_DOCX, file_sha256, load_json, load_project, now_text
from rehearsal import FINAL_TARGET, rehearsal_line
from report_page_numbers import count_automatic, load_page_count, page_gate, page_limit, project_items, record_gate
from response_matrix import item_heading, matrix_items, writing_inputs
from rule_card_rows import content_digest, row_content
from scan_docx_hygiene import is_heading1, load_parts, project_scan, style_context
from text_gates import compact, hit
from validate_docx_format import validate_docx_format

FINAL_NOTES_FILE = "review/final-gate-notes.json"
FINAL_NOTES_SCHEMA = "qingtian-final-gate-notes/1"
REPORT_FILE = "review/gate-report.json"
REPORT_VIEW = "review/gate-report.md"
REPORT_SCHEMA = "qingtian-gate-report/1"
FINISHED_PLACE = "成品"
# B12 的证据；这三项还有阻断时，初步评审对照不能确认（决策 4b-3A）
B12_EVIDENCE = {"B3": "格式校验", "B4": "数值一致", "B9": "★和实质性要求落点"}
GATE_TITLES = {
    "B1": "评审内容全覆盖", "B2": "篇幅上限", "B3": "格式", "B4": "数值一致", "B5": "身份泄露", "B6": "文档清洁",
    "B7": "残留", "B8": "条款号与过程用语", "B9": "★与实质性要求落点", "B10": "资源卡对得上", "B11": "实施进度组织覆盖",
    "B12": "初步评审对照", "B13": "报价内容", "W1": "项目事实偏少", "W2": "缺量化指标", "W3": "套话", "W4": "疑似抄录",
    "W5": "页数偏离预算", "W6": "碎片与表格化", "W7": "第一段没直接回答", "W8": "评审端可能没有的字体",
    "W9": "类别知识卡要点没写到", "W10": "与现场限制矛盾",
}
Counter = Callable[[Path, str], dict]


def finished_docx(project_dir: Path) -> Path:
    docx = project_dir / FINISHED_DOCX
    if not docx.is_file():
        raise ValueError(f"还没有成品 {FINISHED_DOCX}：先按 stage-6-assembly.md 第三节出稿")
    return docx


def gate_order(entry: dict) -> tuple:
    gate = entry["gate"]
    return gate[0] != "B", int(gate[1:]), entry.get("item", 0)


# ---------- 成品上的门禁 ----------

def format_check(docx: Path, write_files: bool) -> tuple[list[dict], dict]:
    """B3 终稿：在当前成品上跑 --final 校验。只有阻断项进门禁，提示只计数（细节见成品旁的格式报告）。"""
    result = validate_docx_format(docx, write_files=write_files, final=True)
    issues = result.get("issues") or []
    blockers = [item for item in issues if item.get("level") == "blocker"]
    hits = [hit("B3", f"final|{item.get('target')}|{item.get('message')}",
                f"格式校验 --final：{item.get('message')}（{item.get('target')}）", fixed=True) for item in blockers]
    return hits, {"ok": bool(result.get("ok")), "blockers": len(blockers), "warnings": len(issues) - len(blockers)}


def finished_headings(docx: Path) -> list[str]:
    """成品正文里的一级标题，按出现顺序，去掉空白。"""
    parts = load_parts(docx.read_bytes())
    context = style_context(parts)
    document = parts["xml"].get("word/document.xml")
    body = None if document is None else document.find(W + "body")
    return [compact("".join(node.text or "" for node in paragraph.iter(W + "t")))
            for paragraph in ([] if body is None else body.iter(W + "p")) if is_heading1(paragraph, context)]


def b1_final_hits(headings: list[str], items: dict[int, dict]) -> list[dict]:
    """B1 在成品上：在 Word 里改过、删过、挪过的标题，中间稿门禁看不到。"""
    expected = {no: compact(item_heading(no, str(item.get("title") or ""))) for no, item in sorted(items.items())}
    wanted = set(expected.values())
    hits = [hit("B1", f"final|missing|{no}", f"成品里找不到第 {no} 项的一级标题“{text}”：标题须与评审内容原文一致，"
                "在 Word 里改过的改回去，或改中间稿后重新出稿（Q1）", fixed=True)
            for no, text in expected.items() if text not in headings]
    hits += [hit("B1", f"final|extra|{index}", f"成品第 {index} 个一级标题“{text}”不是评审内容：一级标题只放评审内容原文，"
                 "其他标题降一级（R4）", fixed=True) for index, text in enumerate(headings, 1) if text not in wanted]
    present = [text for text in headings if text in wanted]
    if present != [text for text in expected.values() if text in present] or len(present) != len(set(present)):
        hits.append(hit("B1", "final|order", "成品里各项一级标题的顺序与评审内容不一致，或有重复的标题（R3）", fixed=True))
    return hits


def backup_hits(docx: Path) -> list[dict]:
    """--clean-properties 留下的备份还带着清掉的作者、单位：放在 output/ 里容易被一起交出去。"""
    return [hit("B5", f"backup|{path.name}", f"output/ 下有清理文档属性前的备份 {path.name}：里面还有清掉的作者、单位等"
                "属性；其余门禁都处理完后删掉，不要随标书交出去", fixed=True)
            for path in sorted(docx.parent.glob(f"{docx.name}.clean-*.bak"))]


def page_result(project_dir: Path, docx: Path, rule_card: dict, prefer: str, counter: Counter | None) -> dict:
    """同一份成品已有计页（PDF、人工页数也算）就复用，只按当前规则卡的上限重判；没有才计页。上次自动计页失败的
    再试一次（失败记录被新结果覆盖不丢东西）。counter 为 None 时不调 Word/WPS（完成条件、确认 B12、记录理由）。"""
    items = project_items(project_dir)
    record = load_page_count(project_dir, docx)
    if record is not None and (record.get("method") != "failed" or counter is None):
        return record_gate({**record, "page_limit": page_limit(rule_card)}, items)
    if counter is None:
        return {"record": None, "notes": [], "hits": [hit("B2", "uncounted", "这份成品还没计页：运行 "
                                                          "check_qingtian_final.py <项目目录> 计页", fixed=True)]}
    return page_gate(project_dir, docx, prefer=prefer, counter=counter)


def visual_build_hits(docx: Path) -> list[dict]:
    """Check visual dependencies in the final gate too, even when stage 6 was completed earlier."""
    from visual_assets import visual_dependency_issues
    report_path = docx.with_suffix(".build-report.json")
    if not report_path.is_file():
        return []  # Legacy/external documents are handled by the existing stage-6 source checks.
    try:
        report = load_json(report_path, "构建报告")
        issues = visual_dependency_issues(report, docx)
    except (OSError, ValueError, TypeError) as exc:
        issues = [f"图片构建记录无法读取：{exc}"]
    return [hit("B3", f"visual|{message}", message, fixed=True) for message in issues]


def finished_hits(project_dir: Path, docx: Path, inputs: dict, *, prefer: str = "auto", counter: Counter | None = None,
                  write_files: bool = False) -> tuple[list[dict], dict]:
    """成品上的全部命中（已补编号和级别，第 0 项＝整份）和计页、格式校验的摘要。"""
    format_hits, format_summary = format_check(docx, write_files)
    pages = page_result(project_dir, docx, inputs["rule_card"], prefer, counter)
    raw = format_hits + b1_final_hits(finished_headings(docx), matrix_items(inputs)) + pages["hits"]
    raw += project_scan(project_dir, docx)["hits"] + backup_hits(docx)
    raw += visual_build_hits(docx)
    hits = [{**entry, "place": FINISHED_PLACE} for entry in finalize(raw, 0, track_of(inputs))]
    return hits, {"format": format_summary, "page_count": pages["record"], "page_notes": pages["notes"]}


def final_notes(project_dir: Path) -> list[dict]:
    return read_notes_file(project_dir, FINAL_NOTES_FILE, FINAL_NOTES_SCHEMA)


# ---------- 中间稿与初步评审对照 ----------

def draft_results(project_dir: Path) -> tuple[dict, int, list[str]]:
    """整份中间稿的门禁：逐项结果已按中间稿的说明分好，整份的命中（B1、B9 落点）不能放行。"""
    run = full_run(project_dir)
    whole = [{**entry, "place": "整份中间稿"} for entry in run["whole"]]
    groups = {"blocking": [entry for entry in whole if entry["level"] == "block"],
              "warnings": [entry for entry in whole if entry["level"] == "warn"], "noted": []}
    stale, manual = 0, []
    for no, result in run["items"].items():
        for key in groups:
            groups[key] += [{**entry, "place": f"第 {no} 项中间稿"} for entry in result[key]]
        stale += result["stale_notes"]
        manual += result["manual"]
    return groups, stale, list(dict.fromkeys(manual))


def b12_rows(rule_card: dict) -> list[dict]:
    """初步评审表里与施组有关的行；行号是它在表里的位置（从 1 起，与 rule-card.md 第三节的顺序一致）。
    digest 只比内容，改出处不算这一行变了。"""
    rows = (rule_card.get("preliminary_review") or {}).get("value") or []
    return [{"row": index, "stage": str(row.get("stage") or ""), "factor": str(row.get("factor") or ""),
             "requirement": str(row.get("requirement") or ""), "digest": content_digest(row_content(row))}
            for index, row in enumerate(rows, 1) if isinstance(row, dict) and row.get("tech_related") is True]


def b12_status(state: dict, rule_card: dict, docx_sha: str) -> list[dict]:
    """每行 confirmed / stale / unconfirmed：确认锁定成品和这一行（决策 4b-3A、D9）。规则卡别的行变了，这一行不失效。"""
    records = (state.get("final") or {}).get("b12") or {}
    rows = []
    for row in b12_rows(rule_card):
        record = records.get(str(row["row"]))
        if not record:
            status, reason = "unconfirmed", "未确认"
        elif record.get("docx_sha256") != docx_sha:
            status, reason = "stale", "确认后成品有改动，须按新成品重新核对"
        elif record.get("rule_row") != row["digest"]:
            status, reason = "stale", "确认后初步评审表这一行有改动，须重新核对"
        else:
            status, reason = "confirmed", f"已确认（{record.get('confirmed_at')}）"
        rows.append({**row, "status": status, "reason": reason})
    return rows


def evidence_text(blocking: list[dict], manual: list[str]) -> str:
    parts = []
    for gate, label in B12_EVIDENCE.items():
        count = sum(1 for entry in blocking if entry["gate"] == gate)
        parts.append(f"{label}（{gate}）" + (f"阻断 {count} 条" if count else "无阻断"))
    return "证据：" + "，".join(parts) + f"；人工核对 {len(manual)} 条"


def b12_hits(rows: list[dict], evidence: str, project_dir: Path, track: str) -> list[dict]:
    raw = [hit("B12", f"row|{row['row']}", f"初步评审第 {row['row']} 行（{row['stage']}·{row['factor']}）{row['reason']}："
               f"对施组的要求“{row['requirement']}”。{evidence}。用户逐条核对、明确认可后运行 project_status.py "
               f"{project_dir} --confirm-b12 {row['row']}", fixed=True) for row in rows if row["status"] != "confirmed"]
    return [{**entry, "place": "初步评审表"} for entry in finalize(raw, 0, track)]


# ---------- 编排 ----------

def final_run(project_dir: Path, *, prefer: str = "auto", counter: Counter | None = count_automatic,
              write_files: bool = False) -> dict:
    """阶段 7 的全部门禁。不改阶段状态；counter 不为 None 且这份成品还没计页时会计页（写 page-count.json），
    write_files 时更新成品旁的格式报告并写门禁报告。"""
    project_dir, state = load_project(project_dir)
    docx = finished_docx(project_dir)
    sha = file_sha256(docx)
    inputs = writing_inputs(project_dir)
    groups, stale, manual = draft_results(project_dir)
    hits, extra = finished_hits(project_dir, docx, inputs, prefer=prefer, counter=counter, write_files=write_files)
    notes = final_notes(project_dir)
    finished = split_hits(hits, {note.get("id"): note for note in notes if note.get("docx_sha256") == sha})
    for key in groups:
        groups[key] += finished[key]
    rows = b12_status(state, inputs["rule_card"], sha)
    groups["blocking"] += b12_hits(rows, evidence_text(groups["blocking"], manual), project_dir, track_of(inputs))
    if file_sha256(docx) != sha:
        raise ValueError("检查过程中成品被改动（Word 或 WPS 里保存过？）：关掉成品后重新运行")
    result = {"project": str(project_dir), "docx": FINISHED_DOCX, "docx_sha256": sha, "checked_at": now_text(),
              "track": track_of(inputs), **{key: sorted(value, key=gate_order) for key, value in groups.items()},
              "stale_notes": stale + sum(1 for note in notes if note.get("docx_sha256") != sha),
              "b12": rows, "manual": manual, "rehearsal": rehearsal_line(project_dir, FINAL_TARGET), **extra}
    # 预演只是提示，不算进 ready，也不写进门禁报告
    result["ready"] = not result["blocking"] and not result["warnings"]
    if write_files:
        write_report(project_dir, result)
    return result


def refuse_unowned(project_dir: Path, identifier: str, rule_card: dict) -> NoReturn:
    """不是成品上的命中：B12 只能逐行确认，中间稿的命中回到中间稿记录，都不在就是编号过期了。"""
    row = next((entry["row"] for entry in b12_rows(rule_card) if hit_id("B12", 0, f"row|{entry['row']}") == identifier), None)
    if row is not None:
        raise ValueError(f"{identifier} 是初步评审对照（B12）第 {row} 行，不能放行：用户逐条核对、明确认可后运行 "
                         f"project_status.py {project_dir} --confirm-b12 {row}")
    run = full_run(project_dir)
    if any(entry["id"] == identifier for entry in run["whole"]):
        raise ValueError(f"{identifier} 是整份中间稿的命中（B1 全覆盖或 B9 落点），不能放行：改中间稿后重新出稿")
    owner = next((no for no, result in run["items"].items()
                  if any(entry["id"] == identifier for key in ("blocking", "warnings") for entry in result[key])), None)
    if owner is not None:
        raise ValueError(f"{identifier} 是第 {owner} 项中间稿的命中：用 check_qingtian_gates.py {project_dir} --item "
                         f"{owner} --dismiss {identifier} --reason \"<用户的理由>\"")
    raise ValueError(f"成品当前没有编号为 {identifier} 的命中：先运行 check_qingtian_final.py 看最新结果")


def dismiss_final(project_dir: Path, identifier: str, reason: str) -> dict:
    """记下用户对成品上一条命中的判断和理由，锁定此刻成品的 sha256。只在用户明确说明理由后调用。"""
    if not reason.strip():
        raise ValueError("理由不能为空：写用户说明的理由")
    project_dir, _ = load_project(project_dir)
    docx = finished_docx(project_dir)
    sha = file_sha256(docx)
    inputs = writing_inputs(project_dir)
    hits, _ = finished_hits(project_dir, docx, inputs)
    target = next((entry for entry in hits if entry["id"] == identifier), None)
    if target is None:
        refuse_unowned(project_dir, identifier, inputs["rule_card"])
    if not target["dismissable"]:
        raise ValueError(f"{target['gate']} 的这条命中不能放行，只能改：{target['message']}")
    note = {"id": identifier, "gate": target["gate"], "kind": "误报" if target["level"] == "block" else "不改理由",
            "reason": reason.strip(), "docx_sha256": sha, "recorded_at": now_text()}
    notes = [entry for entry in final_notes(project_dir) if entry.get("id") != identifier]
    write_notes_file(project_dir, FINAL_NOTES_FILE, FINAL_NOTES_SCHEMA, notes + [note])
    return note


# ---------- 门禁报告与输出 ----------

def report_entry(entry: dict) -> dict:
    """报告里的一条命中：不存命中原文和提示文字（B5 的提示会引用找到的名称，决策 4a-1A）。"""
    row = {key: entry.get(key) for key in ("id", "gate", "level", "place", "item", "count", "dismissable")}
    note = entry.get("note")
    return {**row, "status": "noted" if note else "open",
            **({"note": {"kind": note.get("kind"), "reason": note.get("reason")}} if note else {})}


def page_summary(record: dict | None) -> dict | None:
    if record is None:
        return None
    return {key: record.get(key) for key in ("method", "total_pages", "page_limit", "precision", "counted_at")}


def summary_of(result: dict) -> dict:
    return {"blocking": len(result["blocking"]), "warnings": len(result["warnings"]), "noted": len(result["noted"]),
            "b12_confirmed": sum(1 for row in result["b12"] if row["status"] == "confirmed"), "b12_rows": len(result["b12"])}


def write_report(project_dir: Path, result: dict) -> None:
    report = {"schema": REPORT_SCHEMA, **{key: result[key] for key in ("docx", "docx_sha256", "checked_at", "track", "ready")},
              "summary": summary_of(result), "page_count": page_summary(result["page_count"]), "format": result["format"],
              "hits": [report_entry(entry) for key in ("blocking", "warnings", "noted") for entry in result[key]],
              "b12": [{key: row[key] for key in ("row", "stage", "factor", "status")} for row in result["b12"]],
              "manual": result["manual"]}
    path = project_dir / REPORT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (project_dir / REPORT_VIEW).write_text(render_report(report), encoding="utf-8")


def hit_rows(entries: list[dict]) -> list[str]:
    rows = ["| 门禁 | 编号 | 位置 | 处理 |", "|---|---|---|---|"]
    for entry in entries:
        note = entry.get("note")
        action = f"{note['kind']}：{note['reason']}" if note else ("可说明理由放行" if entry["dismissable"] else "只能改")
        rows.append(f"| {entry['gate']} {GATE_TITLES.get(entry['gate'], '')} | {entry['id']} | {entry['place']} | {action} |")
    return rows


def render_report(report: dict) -> str:
    """门禁报告的 MD 视图：只列门禁、编号和位置；命中的具体内容运行 check_qingtian_final.py 看。"""
    summary, pages = report["summary"], report["page_count"]
    groups = {status: [entry for entry in report["hits"] if (entry["status"], entry["level"]) == status]
              for status in (("open", "block"), ("open", "warn"))}
    noted = [entry for entry in report["hits"] if entry["status"] == "noted"]
    lines = ["# 门禁报告（阶段 7）", "", f"成品：{report['docx']}　sha256：{report['docx_sha256'][:12]}　检查时间：{report['checked_at']}",
             f"结论：{'可以完成阶段 7' if report['ready'] else '还不能完成阶段 7'}（阻断 {summary['blocking']} 条，未处理提示 "
             f"{summary['warnings']} 条，已说明 {summary['noted']} 条；初步评审对照已确认 {summary['b12_confirmed']}/"
             f"{summary['b12_rows']} 行）", "",
             "> 本报告只记门禁、编号和位置，不记命中原文；具体内容运行 check_qingtian_final.py 查看。"
             "成品再保存过，本报告即作废。", "",
             "## 计页与格式", "",
             f"- {page_text(pages)}", f"- 格式校验 --final：阻断 {report['format']['blockers']} 条，提示 "
             f"{report['format']['warnings']} 条（细节见成品旁的 .format-report.md）"]
    for title, entries in (("阻断", groups[("open", "block")]), ("未处理的提示", groups[("open", "warn")]), ("已说明", noted)):
        lines += ["", f"## {title}（{len(entries)} 条）", ""] + (hit_rows(entries) if entries else ["无。"])
    lines += ["", "## 初步评审对照（B12）", "", "| 行 | 环节 | 评审因素 | 状态 |", "|---|---|---|---|"]
    lines += [f"| {row['row']} | {row['stage']} | {row['factor']} | {row['status']} |" for row in report["b12"]]
    lines += ["", "## 人工核对", ""] + ([f"- {text}" for text in report["manual"]] or ["无。"])
    return "\n".join(lines) + "\n"


def hit_line(entry: dict) -> str:
    times = f"（{entry['count']} 处）" if entry.get("count", 1) > 1 else ""
    note = f"（{entry['note']['kind']}：{entry['note']['reason']}）" if entry.get("note") else ""
    return f"- {entry['gate']} [{entry['id']}] {entry['message']}{times}【{entry['place']}】{note}"


def page_text(record: dict | None) -> str:
    """计页一行（完整的计页记录或报告里的摘要都行）。"""
    if record is None:
        return "计页：还没计页"
    limit = record.get("page_limit")
    pages = f"计页：{record['total_pages']} 页（{record.get('method')}）" if record.get("total_pages") else "计页：没能计页"
    return pages + (f"，篇幅上限 {limit['value']} 页（{limit['kind']}）" if limit else "，招标文件没有规定篇幅上限")


def result_text(result: dict) -> tuple[str, int]:
    form = result["format"]
    lines = [f"成品门禁：{result['project']}/{result['docx']}（sha256 {result['docx_sha256'][:12]}）",
             page_text(result["page_count"])]
    lines += [f"- {note}" for note in result["page_notes"]]
    lines.append(f"格式校验 --final：阻断 {form['blockers']} 条，提示 {form['warnings']} 条（见成品旁的 .format-report.md）")
    for title, key in (("阻断", "blocking"), ("提示（逐条改，或按用户说明的理由记下不改的理由）", "warnings"), ("已说明", "noted")):
        if result[key]:
            lines += [f"{title} {len(result[key])} 条："] + [hit_line(entry) for entry in result[key]]
    if result["stale_notes"]:
        lines.append(f"另有 {result['stale_notes']} 条说明因中间稿或成品修改失效，命中已重新判定")
    lines += [f"人工核对：{text}" for text in result["manual"]]
    lines.append(result["rehearsal"])
    lines += ["记录理由（只写用户说明的理由）：成品上的命中用 check_qingtian_final.py <项目目录> --dismiss <编号> --reason "
              "\"<理由>\"；中间稿的命中用 check_qingtian_gates.py <项目目录> --item <N> --dismiss <编号> --reason \"<理由>\"",
              f"门禁报告：{REPORT_VIEW}",
              "结论：可以完成阶段 7（project_status.py <项目目录> --complete 7）。" if result["ready"]
              else f"结论：还不能完成阶段 7（阻断 {len(result['blocking'])} 条，未处理提示 {len(result['warnings'])} 条）。"]
    return "\n".join(lines), 1 if result["blocking"] else 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="qingtian-bid 阶段 7 成品门禁：全部门禁跑一遍，写门禁报告，记录理由。")
    parser.add_argument("project_dir", type=Path, help="项目目录（bid-projects/ 下）。")
    parser.add_argument("--office", choices=("auto", "word", "wps"), default="auto", help="这份成品还没计页时用的程序。")
    parser.add_argument("--dismiss", metavar="编号", help="记下用户对成品上这条命中的判断（误报或不改理由）。")
    parser.add_argument("--reason", default="", help="--dismiss 的理由，写用户说明的原话。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.dismiss:
            note = dismiss_final(args.project_dir, args.dismiss, args.reason)
            print(f"已记下成品上的 {note['gate']} [{note['id']}]（{note['kind']}）：{note['reason']}")
            return 0
        text, code = result_text(final_run(args.project_dir, prefer=args.office, write_files=True))
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
