"""Count the rendered pages of the finished 施工组织设计 DOCX (gate B2) and how long each item runs (W5).

迁移来源见 CHANGELOG《脚本来源》，改造：
  * 只计页，不回填导航表页码（施组没有导航表）；保留按 PDF 文字找标题所在页的做法；
  * 计页一律在临时副本上做（office_bridge.collect_positions_via_office）：成品不更新、不保存、不留 .bak；
  * 本机 Word 和 WPS 都在时两边都计，按较大的页数判 B2（决策 4b-1A）；同一个程序只计一次
    （WPS 接管 Word.Application 时两个入口是同一个 wps.exe）；
  * 退路依次是：Word/WPS 在副本上导出 PDF 后计页；用户导出的 PDF（--pdf）；用户给出的页数
    （--manual-pages，写明怎么数的）。后两条只在自动计页失败过之后才收，免得绕过渲染计页；
  * 去掉 LibreOffice 退路：它不更新目录域，页数不准；
  * 结果写 review/page-count.json，锁定成品 sha256；不存标题原文。

INPUT: the finished DOCX (output/施工组织设计.docx) and its project (project-state.json above it): the rule
       card's 篇幅上限 and the response matrix's per-item page budget; office_bridge for COM; optionally a PDF
       the user exported (pypdf).
OUTPUT: page_gate() → {record, hits, notes}; review/page-count.json; load_page_count() and record_gate() for the
        stage-7 run (check_qingtian_final reuses the stored count of the same DOCX, so a manual or PDF count is
        never overwritten by another failing automatic one); a CLI that prints the result (exit 1 while B2 blocks).
POS: gate B2 (渲染页数不超篇幅上限, R23、Q8) and W5 (各项页数偏离预算超过 30%, Q5) of qingtian-bid stage 7.
     The count includes the cover and TOC (redlines.md 第五节：目录按计入估算【推断】); "建议"的上限也照做
     (D7)。Item lengths come from where each 一级标题 starts and where the previous item's text ends 【推断】:
     to the line when Word/WPS reports vertical positions, to whole pages otherwise (W5 then ignores gaps
     within 1 page).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable

from pypdf import PdfReader

from office_bridge import collect_positions_via_office, export_pdf_copy_via_office, office_engines
from project_cards import RULE_CARD_FILE, UNSPECIFIED, file_sha256, find_project_dir, load_json, load_project, now_text
from response_matrix import item_heading, matrix_items, writing_inputs
from text_gates import hit

PAGE_COUNT_FILE = "review/page-count.json"
PAGE_COUNT_SCHEMA = "qingtian-page-count/1"
W5_RATIO = 0.30
# 目录条目：标题后面紧跟引导符和页码，不算标题所在页。没有引导符的目录认不出，本项起始页会算在目录页上【推断】
TOC_TAIL = re.compile(r"[.．…·_\-]{2,}\d+")
MANUAL_HINT = ("在 WPS 或 Word 里打开成品，更新目录后导出 PDF，再运行 --pdf <PDF>；"
               "或者看状态栏的总页数，用 --manual-pages <页数> --reason \"<怎么数的>\" 记下")


def normalize(text: str) -> str:
    """去掉空白差异：PDF 提取会在中英文之间插空格、断行。"""
    return re.sub(r"[\s　]+", "", text)


def page_limit(rule_card: dict) -> dict | None:
    """规则卡的篇幅上限；招标文件未规定时为 None。"""
    entry = rule_card.get("page_limit") or {}
    value = entry.get("value")
    if entry.get("basis") == UNSPECIFIED or not isinstance(value, int) or isinstance(value, bool):
        return None
    return {"value": value, "kind": entry.get("kind")}


def project_items(project_dir: Path) -> dict[int, dict]:
    """响应矩阵的各项（标题、页数预算）；矩阵读不出时不算 W5，B2 照算。"""
    try:
        return matrix_items(writing_inputs(project_dir))
    except ValueError:
        return {}


# ---------- 计页 ----------

def count_automatic(docx_path: Path, prefer: str = "auto") -> dict:
    """Word/WPS 在副本上计页；都读不出就在副本上导出 PDF 计页。返回 {method, runs, best | pdf_texts, error}。"""
    engines = office_engines(prefer)
    runs = [{"engine": engine, **collect_positions_via_office(docx_path, engine)} for engine in engines]
    ok = [run for run in runs if run["ok"]]
    if ok:
        return {"method": "office", "runs": runs, "best": max(ok, key=lambda run: run["total_pages"])}
    for engine in engines:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_name:
            pdf_path = Path(temp_name) / "count.pdf"
            if export_pdf_copy_via_office(docx_path, pdf_path, engine):
                return {"method": "office-pdf", "runs": runs, "pdf_texts": pdf_page_texts(pdf_path),
                        "pdf_engine": engine}
    reason = "本机没有可用的 Word 或 WPS" if not engines else "；".join(
        f"{run['engine']['label']}: {run['error']}" for run in runs)
    return {"method": "failed", "runs": runs, "error": reason}


def pdf_page_texts(pdf_path: Path) -> list[str]:
    texts = []
    for page in PdfReader(str(pdf_path)).pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:  # 个别页提取失败不影响计页
            texts.append("")
    return texts


def engine_rows(runs: list[dict]) -> list[dict]:
    return [{"label": run["engine"]["label"], "prog_id": run["engine"]["prog_id"],
             "aliases": run["engine"].get("aliases", []), "ok": run["ok"],
             "total_pages": run.get("total_pages") if run["ok"] else None, "error": run.get("error", "")}
            for run in runs]


# ---------- 各项页数（W5） ----------

def match_headings(headings: list[dict], items: dict[int, dict]) -> dict[int, int]:
    """评审内容 → 第几个一级标题（按原文比对，各取第一次出现）。"""
    wanted = {normalize(item_heading(no, str(item.get("title") or ""))): no for no, item in items.items()}
    matched: dict[int, int] = {}
    for index, heading in enumerate(headings):
        no = wanted.get(normalize(heading["text"]))
        if no is not None and no not in matched:
            matched[no] = index
    return matched


def page_position(page_no: int, y: float, page: dict) -> float:
    """页内位置换成"第几页"：按版心高度算，满一页正文为 1。"""
    usable = page["height"] - page["top"] - page["bottom"]
    usable = usable if usable > 0 else page["height"]
    return (page_no - 1) + min(max((y - page["top"]) / usable, 0.0), 1.0)


def office_lengths(result: dict, items: dict[int, dict]) -> tuple[dict[int, dict], str]:
    """每项从一级标题开始，到下一个一级标题前一个字（最后一项到全文末尾）结束。"""
    headings, lengths, precision = result["headings"], {}, "line"
    for no, index in match_headings(headings, items).items():
        start = headings[index]
        following = headings[index + 1] if index + 1 < len(headings) else None
        end_page = following["prev_page"] if following else (result.get("end") or {}).get("page", result["total_pages"])
        end_y = following["prev_y"] if following else (result.get("end") or {}).get("y", -1)
        if result.get("page") and start["y"] >= 0 and end_y >= 0:
            length = page_position(end_page, end_y, result["page"]) - page_position(start["page"], start["y"], result["page"])
        else:  # 读不到纵向位置：按占了几页算
            length, precision = float(end_page - start["page"] + 1), "page"
        lengths[no] = {"start_page": start["page"], "length": round(max(length, 0.0), 2)}
    return lengths, precision


def heading_on_page(needle: str, page_text: str) -> bool:
    return any(not TOC_TAIL.match(page_text[found.end():]) for found in re.finditer(re.escape(needle), page_text))


def pdf_lengths(texts: list[str], items: dict[int, dict]) -> tuple[dict[int, dict], str]:
    """PDF 只有整页：本项占到下一项标题所在页之前，最后一项占到末页。"""
    pages = [normalize(text) for text in texts]
    starts: dict[int, int] = {}
    search_from = 0
    for no in sorted(items):
        needle = normalize(item_heading(no, str(items[no].get("title") or "")))
        found = next((index for index in range(search_from, len(pages)) if heading_on_page(needle, pages[index])), None)
        if found is not None:
            starts[no], search_from = found + 1, found
    ordered = sorted(starts.items(), key=lambda pair: pair[1])
    lengths = {}
    for position, (no, page_no) in enumerate(ordered):
        end = ordered[position + 1][1] if position + 1 < len(ordered) else len(pages) + 1
        lengths[no] = {"start_page": page_no, "length": float(max(end - page_no, 0))}
    return lengths, "page"


def w5_hits(lengths: dict[int, dict], items: dict[int, dict], precision: str) -> list[dict]:
    """实际页数偏离矩阵预算超过 30%；整页精度时差在 1 页以内不报【推断】。"""
    hits = []
    for no, entry in sorted(lengths.items()):
        budget = items.get(no, {}).get("pages")
        if not isinstance(budget, (int, float)) or isinstance(budget, bool) or budget <= 0:
            continue
        gap = abs(entry["length"] - budget)
        allowed = W5_RATIO * budget if precision == "line" else max(W5_RATIO * budget, 1.0)
        if gap > allowed:
            accuracy = "精确到行" if precision == "line" else "只精确到整页，差 1 页以内不报"
            hits.append({**hit("W5", str(no),
                               f"第 {no} 项实际约 {entry['length']:.1f} 页，预算 {budget:g} 页，偏离 {gap / budget:.0%}"
                               f"（超过 30%，Q5）：长了压缩，短了补本项的针对性做法（{accuracy}【推断】）"), "item": no})
    return hits


# ---------- B2 与结果记录 ----------

def b2_hits(record: dict) -> list[dict]:
    total, limit = record.get("total_pages"), record.get("page_limit")
    if total is None:
        return [{**hit("B2", "uncounted", f"没能计页（{record.get('failure') or '原因不明'}）：{MANUAL_HINT}", fixed=True),
                 "item": 0}]
    if limit and total > limit["value"]:
        return [{**hit("B2", f"over|{total}|{limit['value']}",
                       f"成品 {total} 页，超过篇幅上限 {limit['value']} 页（招标文件写的是“{limit['kind']}”，"
                       "建议也照做，D7）：压缩各项；压缩会删掉评审内容要求的要点时停下来请用户取舍", fixed=True),
                 "item": 0}]
    return []


def count_notes(record: dict) -> list[str]:
    """计页方式的说明：同一程序只计一次、两边页数不同、只有 WPS 等。"""
    notes = []
    ok = [row for row in record["engines"] if row["ok"]]
    for row in record["engines"]:
        if row["aliases"]:
            notes.append(f"{'、'.join(row['aliases'])} 启动的也是 {row['label']}，只计一次")
    if len({row["total_pages"] for row in ok}) > 1:
        counts = "、".join(f"{row['label']} {row['total_pages']} 页" for row in ok)
        notes.append(f"{counts}，按较大的 {record['total_pages']} 页判 B2（决策 4b-1A）")
    if ok and all(row["label"] != "Microsoft Word" for row in ok):
        notes.append("本机没有 Microsoft Word，只用 WPS 计页；评审端如用 Word 排版，页数可能不同【推断】")
    if record["method"] in {"office-pdf", "pdf"}:
        notes.append("按 PDF 计页，各项页数只精确到整页")
    if record["method"] == "manual":
        notes.append(f"用户给出的页数：{record['manual']['reason']}；各项页数（W5）没法算，请人工核对")
    return notes


def build_record(project_dir: Path, docx_path: Path, counted: dict, items: dict[int, dict], limit: dict | None) -> dict:
    record = {"schema": PAGE_COUNT_SCHEMA, "docx": stored_docx(project_dir, docx_path),
              "docx_sha256": file_sha256(docx_path), "counted_at": now_text(), "method": counted["method"],
              "engines": engine_rows(counted.get("runs", [])), "total_pages": None, "precision": None,
              "page_limit": limit, "items": [], "unmatched_items": [], "manual": counted.get("manual"),
              "failure": counted.get("error", ""),
              "pdf_engine": (counted.get("pdf_engine") or {}).get("label")}
    if counted["method"] == "office":
        record["total_pages"] = counted["best"]["total_pages"]
        lengths, record["precision"] = office_lengths(counted["best"], items)
    elif counted["method"] in {"office-pdf", "pdf"}:
        record["total_pages"] = len(counted["pdf_texts"])
        lengths, record["precision"] = pdf_lengths(counted["pdf_texts"], items)
    else:
        record["total_pages"] = (counted.get("manual") or {}).get("pages")
        lengths = {}
    record["items"] = [{"no": no, **entry, "budget": items[no].get("pages")} for no, entry in sorted(lengths.items())]
    record["unmatched_items"] = [no for no in sorted(items) if no not in lengths] if record["method"] != "manual" else []
    return record


def stored_docx(project_dir: Path, docx_path: Path) -> str:
    try:
        return docx_path.resolve().relative_to(project_dir).as_posix()
    except ValueError:
        return str(docx_path.resolve())


def save_record(project_dir: Path, record: dict) -> None:
    path = project_dir / PAGE_COUNT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_record(project_dir: Path) -> dict | None:
    path = project_dir / PAGE_COUNT_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{PAGE_COUNT_FILE} 读不出来: {exc}") from exc
    return data if isinstance(data, dict) and data.get("schema") == PAGE_COUNT_SCHEMA else None


def load_page_count(project_dir: Path, docx_path: Path) -> dict | None:
    """当前成品的计页结果；成品换过（sha256 不同）或换了文件就失效，返回 None。"""
    record = read_record(project_dir)
    if record is None or record.get("docx") != stored_docx(project_dir, docx_path):
        return None
    return record if record.get("docx_sha256") == file_sha256(docx_path) else None


def require_failed_attempt(project_dir: Path, docx_path: Path, what: str) -> None:
    """--pdf 和 --manual-pages 只在这份成品自动计页失败过之后才收（B2 以渲染页数为准）。"""
    record = load_page_count(project_dir, docx_path)
    if record is None or record.get("method") != "failed":
        raise ValueError(f"先不带参数自动计页；这份成品自动计页失败后，才收{what}")


def page_gate(project_dir: Path, docx_path: Path, *, prefer: str = "auto", pdf: Path | None = None,
              manual_pages: int | None = None, reason: str = "",
              counter: Callable[[Path, str], dict] = count_automatic) -> dict:
    """计页并判 B2、W5，结果写 review/page-count.json。不改阶段状态。"""
    project_dir, _ = load_project(project_dir)
    docx_path = docx_path.expanduser().resolve()
    if not docx_path.is_file():
        raise ValueError(f"成品不存在: {docx_path}")
    if pdf is not None:
        require_failed_attempt(project_dir, docx_path, "用户导出的 PDF")
        counted = {"method": "pdf", "pdf_texts": pdf_page_texts(pdf.expanduser().resolve())}
    elif manual_pages is not None:
        if manual_pages <= 0 or not reason.strip():
            raise ValueError("--manual-pages 须是正整数，并用 --reason 写明用户是怎么数的")
        require_failed_attempt(project_dir, docx_path, "用户给出的页数")
        counted = {"method": "manual", "manual": {"pages": manual_pages, "reason": reason.strip(), "recorded_at": now_text()}}
    else:
        counted = counter(docx_path, prefer)
    items = project_items(project_dir)
    record = build_record(project_dir, docx_path, counted, items, page_limit(load_json(project_dir / RULE_CARD_FILE, "规则卡")))
    save_record(project_dir, record)
    return record_gate(record, items)


def record_gate(record: dict, items: dict[int, dict]) -> dict:
    """按一份计页记录判 B2、W5（刚计的，或存下的同一份成品的计页）。"""
    lengths = {entry["no"]: entry for entry in record["items"]}
    precision = record["precision"] or "page"
    return {"record": record, "hits": b2_hits(record) + w5_hits(lengths, items, precision), "notes": count_notes(record)}


# ---------- 命令行 ----------

def result_text(result: dict) -> str:
    record = result["record"]
    limit = record["page_limit"]
    ceiling = f"上限 {limit['value']} 页（{limit['kind']}）" if limit else "招标文件未规定篇幅上限"
    total = record["total_pages"]
    lines = [f"计页：{'失败' if total is None else f'{total} 页'}（{record['method']}），{ceiling}"]
    lines += [f"- {row['label']}：{row['total_pages']} 页" if row["ok"] else f"- {row['label']}：失败（{row['error']}）"
              for row in record["engines"]]
    lines += [f"说明：{note}" for note in result["notes"]]
    lines += [f"第 {entry['no']} 项：约 {entry['length']:.1f} 页 / 预算 {entry['budget']} 页" for entry in record["items"]]
    if record["unmatched_items"]:
        lines.append(f"人工核对：第 {'、'.join(map(str, record['unmatched_items']))} 项没找到一级标题，页数没算（标题缺失归 B1）")
    lines += [f"- {entry['gate']} {entry['message']}" for entry in result["hits"]]
    blocking = [entry for entry in result["hits"] if entry["gate"] == "B2"]
    lines.append(f"B2 阻断 {len(blocking)} 条。" if blocking else "B2 通过。")
    return "\n".join(lines)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="qingtian-bid 门禁 B2/W5：在副本上计成品页数，判篇幅上限和各项页数。")
    parser.add_argument("docx_path", type=Path, nargs="?", help="成品 DOCX（output/施工组织设计.docx）。")
    parser.add_argument("--project", type=Path, help="项目目录；不给时从成品所在位置往上找。")
    parser.add_argument("--office", choices=("auto", "word", "wps"), default="auto", help="计页用的程序。")
    parser.add_argument("--pdf", type=Path, help="用户在 Word/WPS 里导出的 PDF（自动计页失败后才收）。")
    parser.add_argument("--manual-pages", type=int, help="用户数出的总页数（自动计页失败后才收）。")
    parser.add_argument("--reason", default="", help="--manual-pages 的说明：用户是怎么数的。")
    parser.add_argument("--probe", action="store_true", help="只列出能计页的程序（按实际程序去重），不处理文档。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.probe:
        print(json.dumps(office_engines(args.office), ensure_ascii=False, indent=2))
        return 0
    try:
        if args.docx_path is None:
            raise ValueError("请给出成品 DOCX，或用 --probe 只看本机能用的程序")
        project = args.project or find_project_dir(args.docx_path)
        if project is None:
            raise ValueError(f"成品不在 qingtian-bid 项目里，用 --project 指定: {args.docx_path}")
        result = page_gate(project, args.docx_path, prefer=args.office, pdf=args.pdf,
                           manual_pages=args.manual_pages, reason=args.reason)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(result_text(result))
    return 1 if any(entry["gate"] == "B2" for entry in result["hits"]) else 0


if __name__ == "__main__":
    sys.exit(main())
