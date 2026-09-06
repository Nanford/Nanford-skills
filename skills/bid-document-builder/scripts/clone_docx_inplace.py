#!/usr/bin/env python3
"""复制参考 DOCX 并在原结构中安全替换变量。

默认不重建正文，只复制母文件并替换正文、表格、页眉、页脚、文本框及批注中的
等值字段。若替换命中跨 run 文本，合并后沿用首个文本 run 的格式。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from cover_template import prepare_reference_docx
from docx_structure import build_manifest, compare_manifests


XML_PART_PATTERN = re.compile(
    r"word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$"
)
RED = "FF0000"
W_NS = qn("w:p").split("}")[0][1:]
NS = {"w": W_NS}


def _load_replacements(path: str | Path) -> list[dict[str, object]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        items = [
            {"old": str(old), "new": str(new), "red": True}
            for old, new in payload.items()
        ]
    elif isinstance(payload, list):
        items = payload
    else:
        raise RuntimeError("替换数据必须是 JSON 对象或数组")

    normalized: list[dict[str, object]] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or "old" not in item or "new" not in item:
            raise RuntimeError(f"第 {index} 条替换缺少 old/new")
        old = str(item["old"])
        new = str(item["new"])
        if not old:
            raise RuntimeError(f"第 {index} 条替换的 old 不能为空")
        normalized.append({"old": old, "new": new, "red": bool(item.get("red", True))})
    return normalized


def _set_red(run) -> None:
    from lxml import etree

    r_pr_nodes = run.xpath("./w:rPr", namespaces=NS)
    if r_pr_nodes:
        r_pr = r_pr_nodes[0]
    else:
        r_pr = etree.Element(qn("w:rPr"))
        run.insert(0, r_pr)
    color_nodes = r_pr.xpath("./w:color", namespaces=NS)
    color = color_nodes[0] if color_nodes else etree.Element(qn("w:color"))
    color.set(qn("w:val"), RED)
    if not color_nodes:
        r_pr.append(color)


def _replace_in_container(container, old: str, new: str, red: bool) -> int:
    count = 0
    search_start = 0
    while True:
        runs = container.xpath(".//w:r[.//w:t]", namespaces=NS)
        if not runs:
            return count
        texts = ["".join(run.xpath(".//w:t/text()", namespaces=NS)) for run in runs]
        full = "".join(texts)
        match_start = full.find(old, search_start)
        if match_start < 0:
            return count
        match_end = match_start + len(old)

        offsets: list[tuple[int, int]] = []
        cursor = 0
        for text in texts:
            offsets.append((cursor, cursor + len(text)))
            cursor += len(text)
        first_index = next(i for i, (_, end) in enumerate(offsets) if end > match_start)
        last_index = next(i for i, (begin, _) in enumerate(offsets) if begin < match_end <= offsets[i][1])
        first_begin, _ = offsets[first_index]
        last_begin, _ = offsets[last_index]
        first_text = texts[first_index]
        last_text = texts[last_index]
        prefix = first_text[: match_start - first_begin]
        suffix = last_text[match_end - last_begin :]
        replacement = prefix + new + suffix

        first_run = runs[first_index]
        first_nodes = first_run.xpath(".//w:t", namespaces=NS)
        first_nodes[0].text = replacement
        for node in first_nodes[1:]:
            node.text = ""
        if red:
            _set_red(first_run)

        for index in range(first_index + 1, last_index + 1):
            for node in runs[index].xpath(".//w:t", namespaces=NS):
                node.text = ""
        count += 1
        search_start = match_start + len(new)


def _replace_xml(xml: bytes, replacements: list[dict[str, object]]) -> tuple[bytes, dict[str, int]]:
    from lxml import etree

    root = etree.fromstring(xml)
    counts: dict[str, int] = {}
    unique_containers = root.xpath(".//w:p", namespaces=NS)

    for item in replacements:
        old = str(item["old"])
        count = 0
        for container in unique_containers:
            count += _replace_in_container(container, old, str(item["new"]), bool(item["red"]))
        counts[old] = count
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), counts


def clone_and_replace(reference: str | Path, output: str | Path, replacements: list[dict[str, object]]) -> dict[str, object]:
    reference_path = Path(reference).resolve()
    prepared_path = Path(prepare_reference_docx(str(reference_path))).resolve()
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path == reference_path:
        raise RuntimeError("输出路径不得覆盖参考文件")

    with tempfile.TemporaryDirectory(prefix="bid_docx_v15_") as temp_dir:
        temp_output = Path(temp_dir) / output_path.name
        counts = {str(item["old"]): 0 for item in replacements}
        with zipfile.ZipFile(prepared_path, "r") as source, zipfile.ZipFile(
            temp_output, "w", compression=zipfile.ZIP_DEFLATED
        ) as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if XML_PART_PATTERN.fullmatch(info.filename):
                    data, part_counts = _replace_xml(data, replacements)
                    for old, count in part_counts.items():
                        counts[old] += count
                target.writestr(info, data)
        # 用 python-docx 实际打开，防止输出一个 ZIP 正常但 Word 结构损坏的文件。
        Document(temp_output)
        shutil.copy2(temp_output, output_path)

    reference_manifest = build_manifest(prepared_path)
    output_manifest = build_manifest(output_path)
    errors, warnings = compare_manifests(reference_manifest, output_manifest)
    if errors:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("原位克隆破坏结构：" + "；".join(errors))
    return {
        "reference": str(reference_path),
        "prepared_reference": str(prepared_path),
        "output": str(output_path),
        "replacement_counts": counts,
        "structure_warnings": warnings,
    }


def write_checklist(result: dict[str, object], replacements: list[dict[str, object]], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    counts = result["replacement_counts"]
    lines = [
        "# 原位克隆待确认清单",
        "",
        "| # | 参考原值 | 成稿值 | 红字 | 命中处数 | 人工确认 |",
        "|---|---|---|---|---:|---|",
    ]
    for index, item in enumerate(replacements, 1):
        old = str(item["old"]).replace("|", "\\|")
        new = str(item["new"]).replace("|", "\\|")
        red = "是" if item["red"] else "否"
        lines.append(f"| {index} | {old} | {new} | {red} | {counts[str(item['old'])]} | ☐ |")
    lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="V1.5 DOCX 原位克隆与变量替换")
    parser.add_argument("reference", help="参考 .doc/.docx")
    parser.add_argument("output", help="输出 .docx；不得覆盖参考文件")
    parser.add_argument("--replacements", required=True, help="JSON 对象或 [{old,new,red}] 数组")
    parser.add_argument("--report", help="输出替换及结构报告 JSON")
    parser.add_argument("--checklist", help="输出原位替换待确认清单 Markdown")
    parser.add_argument("--require-hit", action="store_true", help="任一替换未命中即失败")
    args = parser.parse_args()

    replacements = _load_replacements(args.replacements)
    result = clone_and_replace(args.reference, args.output, replacements)
    missing = [old for old, count in result["replacement_counts"].items() if count == 0]
    for old, count in result["replacement_counts"].items():
        print(f"替换 {count} 处: {old}")
    if result["structure_warnings"]:
        for warning in result["structure_warnings"]:
            print(f"[结构警告] {warning}")
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK 报告: {report_path.resolve()}")
    if args.checklist:
        write_checklist(result, replacements, args.checklist)
        print(f"OK 待确认清单: {Path(args.checklist).resolve()}")
    if missing and args.require_hit:
        Path(args.output).unlink(missing_ok=True)
        print("FAIL 未命中替换项: " + "、".join(missing), file=sys.stderr)
        sys.exit(1)
    if missing:
        print("[警告] 未命中替换项: " + "、".join(missing))
    print(f"PASS 原位克隆完成: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
