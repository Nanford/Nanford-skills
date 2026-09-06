#!/usr/bin/env python3
"""审计最终 DOCX 中的旧值、黑字占位和必须标红字段。"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from docx.oxml.ns import qn
from lxml import etree


W_NS = qn("w:p").split("}")[0][1:]
NS = {"w": W_NS}
PART_PATTERN = re.compile(r"word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$")
PLACEHOLDERS = [
    ("方括号占位", re.compile(r"\[[^\]\r\n]{2,60}\]"), "error"),
    ("中文括号占位", re.compile(r"【[^】\r\n]*(?:待填|待确认|填写|名称|编号|金额|日期|时间|地址|电话|联系人|设备|产品|项目|采购包)[^】\r\n]*】"), "error"),
    ("年份占位", re.compile(r"(?:20XX|202X|201X|20X{2}|XX年|XX月|XX日)", re.I), "error"),
    ("金额占位", re.compile(r"(?:XXX(?:万元|元)?|0[，,]000(?:\.00)?\s*元?)", re.I), "error"),
    # 响应文件格式中的签字、盖章、供应商填写线通常应保留黑色，因此只警告。
    ("下划线空槽", re.compile(r"_{4,}"), "warning"),
]


def _compact(text: str) -> str:
    return re.sub(r"[\s\u00a0]+", "", text or "")


def _is_red(run) -> bool:
    colors = run.xpath("./w:rPr/w:color/@w:val", namespaces=NS)
    return any(str(color).upper() in {"FF0000", "F00"} for color in colors)


def _paragraph_record(part: str, index: int, paragraph) -> dict[str, Any]:
    runs = paragraph.xpath(".//w:r[.//w:t]", namespaces=NS)
    text = ""
    spans = []
    for run in runs:
        run_text = "".join(run.xpath(".//w:t/text()", namespaces=NS))
        start = len(text)
        text += run_text
        spans.append({"start": start, "end": len(text), "red": _is_red(run), "text": run_text})
    return {"part": part, "paragraph": index, "text": text, "spans": spans}


def extract_records(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as package:
        for part in sorted(name for name in package.namelist() if PART_PATTERN.fullmatch(name)):
            root = etree.fromstring(package.read(part))
            for index, paragraph in enumerate(root.xpath(".//w:p", namespaces=NS), 1):
                record = _paragraph_record(part, index, paragraph)
                if record["text"]:
                    records.append(record)
    return records


def _span_is_red(record: dict[str, Any], start: int, end: int) -> bool:
    overlaps = [span for span in record["spans"] if span["end"] > start and span["start"] < end and span["text"]]
    return bool(overlaps) and all(span["red"] for span in overlaps)


def _flatten_old(payload: Any) -> list[str]:
    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, list):
        result: list[str] = []
        for item in payload:
            result.extend(_flatten_old(item))
        return result
    if isinstance(payload, dict):
        result = []
        for value in payload.values():
            result.extend(_flatten_old(value))
        return result
    return []


def _load_fields(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict) and "fields" in payload:
        payload = payload["fields"]
    elif isinstance(payload, dict):
        payload = [{"name": key, "value": value} for key, value in payload.items()]
    if not isinstance(payload, list):
        raise RuntimeError("project-data 必须是对象、数组或含 fields 的对象")
    fields = []
    for item in payload:
        if not isinstance(item, dict) or "value" not in item:
            continue
        fields.append(
            {
                "name": str(item.get("name", item.get("key", "字段"))),
                "value": str(item["value"]),
                "min_count": int(item.get("min_count", 1)),
                "must_be_red": bool(item.get("must_be_red", False)),
            }
        )
    return fields


def audit(
    docx_path: str | Path,
    fields: list[dict[str, Any]] | None = None,
    old_values: list[str] | None = None,
    must_red_rules: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    records = extract_records(docx_path)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    for record in records:
        text = record["text"]
        for label, pattern, severity in PLACEHOLDERS:
            for match in pattern.finditer(text):
                issue = {
                    "rule": "placeholder",
                    "label": label,
                    "part": record["part"],
                    "paragraph": record["paragraph"],
                    "text": match.group(0),
                }
                if _span_is_red(record, match.start(), match.end()):
                    pending.append(issue)
                elif severity == "warning":
                    warnings.append(issue)
                else:
                    errors.append(issue)

    for old in sorted(set(old_values or []), key=len, reverse=True):
        compact_old = _compact(old)
        if len(compact_old) < 4:
            continue
        for record in records:
            if compact_old in _compact(record["text"]):
                errors.append(
                    {
                        "rule": "old_value",
                        "label": "参考旧值残留",
                        "part": record["part"],
                        "paragraph": record["paragraph"],
                        "text": old,
                    }
                )

    for field in fields or []:
        count = 0
        red_count = 0
        for record in records:
            start = 0
            while (position := record["text"].find(field["value"], start)) >= 0:
                count += 1
                if _span_is_red(record, position, position + len(field["value"])):
                    red_count += 1
                start = position + max(1, len(field["value"]))
        if count < field["min_count"]:
            errors.append(
                {
                    "rule": "field_missing",
                    "label": field["name"],
                    "text": field["value"],
                    "expected": field["min_count"],
                    "actual": count,
                }
            )
        if field["must_be_red"] and red_count != count:
            errors.append(
                {
                    "rule": "field_not_red",
                    "label": field["name"],
                    "text": field["value"],
                    "occurrences": count,
                    "red_occurrences": red_count,
                }
            )

    for rule in must_red_rules or []:
        pattern = re.compile(rule["pattern"], re.I)
        for record in records:
            for match in pattern.finditer(record["text"]):
                if not _span_is_red(record, match.start(), match.end()):
                    errors.append(
                        {
                            "rule": "must_red",
                            "label": rule.get("label", rule["pattern"]),
                            "part": record["part"],
                            "paragraph": record["paragraph"],
                            "text": match.group(0),
                        }
                    )

    report = {
        "schema_version": 1,
        "docx": str(Path(docx_path).resolve()),
        "summary": {"errors": len(errors), "warnings": len(warnings), "pending_red": len(pending)},
        "errors": errors,
        "warnings": warnings,
        "pending_red": pending,
    }
    return report


def _write_markdown(path: str | Path, report: dict[str, Any]) -> None:
    lines = [
        "# DOCX 终审报告",
        "",
        f"错误：{report['summary']['errors']}；警告：{report['summary']['warnings']}；红字待确认：{report['summary']['pending_red']}。",
        "",
        "## 错误",
        "",
    ]
    if report["errors"]:
        for index, item in enumerate(report["errors"], 1):
            location = f"{item.get('part', '')} / 段落{item.get('paragraph', '')}".strip(" /")
            lines.append(f"{index}. {item['label']}：{item.get('text', '')}（{location}）")
    else:
        lines.append("无。")
    lines.extend(["", "## 警告", ""])
    if report["warnings"]:
        for index, item in enumerate(report["warnings"], 1):
            location = f"{item.get('part', '')} / 段落{item.get('paragraph', '')}".strip(" /")
            lines.append(f"{index}. {item['label']}：{item.get('text', '')}（{location}）")
    else:
        lines.append("无。")
    lines.extend(["", "## 红字待确认", ""])
    if report["pending_red"]:
        for index, item in enumerate(report["pending_red"], 1):
            lines.append(f"{index}. {item['text']}（{item['part']} / 段落{item['paragraph']}）")
    else:
        lines.append("无。")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="最终 DOCX 红字、占位和旧值终审")
    parser.add_argument("docx")
    parser.add_argument("--project-data", help="关键字段 JSON")
    parser.add_argument("--old", help="参考旧值 JSON")
    parser.add_argument("--must-red", help="必须标红规则 [{label,pattern}] JSON")
    parser.add_argument("--report", required=True, help="输出 JSON 报告")
    parser.add_argument("--markdown", help="输出 Markdown 报告")
    args = parser.parse_args()

    fields = _load_fields(args.project_data)
    old_values = _flatten_old(json.loads(Path(args.old).read_text(encoding="utf-8-sig"))) if args.old else []
    rules = json.loads(Path(args.must_red).read_text(encoding="utf-8-sig")) if args.must_red else []
    report = audit(args.docx, fields, old_values, rules)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown:
        _write_markdown(args.markdown, report)
    print(
        f"DOCX终审: 错误 {report['summary']['errors']} | 警告 {report['summary']['warnings']} | "
        f"红字待确认 {report['summary']['pending_red']}"
    )
    if report["summary"]["errors"]:
        for item in report["errors"][:20]:
            print(f"[错误] {item['label']}: {item.get('text', '')}")
        sys.exit(1)
    print("PASS DOCX 红字与旧值终审通过")


if __name__ == "__main__":
    main()
