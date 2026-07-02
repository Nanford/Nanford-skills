"""Validate bid project files before final delivery.

INPUT: bid-projects/<project> directory.
OUTPUT: review/validation-report.md/json and process exit code.
POS: Stage 6 compliance gate for the bid-preparation skill.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED_ANALYSIS_FILES = [
    "bid-analysis.md",
    "scoring-matrix.md",
    "mandatory-checklist.md",
]

UNRESOLVED_STATUSES = ["需补材料", "需用户确认", "存在偏离", "无法判断", "需确认"]
FINAL_DOCX_NAME = "投标响应文件.docx"


def add_issue(issues: list[dict], level: str, message: str, file_path: Path | None = None) -> None:
    issues.append({"level": level, "message": message, "file": str(file_path) if file_path else ""})


def check_required_analysis(project_dir: Path, issues: list[dict]) -> None:
    analysis_dir = project_dir / "analysis"
    for filename in REQUIRED_ANALYSIS_FILES:
        path = analysis_dir / filename
        if not path.exists():
            add_issue(issues, "blocker", f"缺少解标分析文件: {filename}", path)


def check_mandatory_status(project_dir: Path, issues: list[dict]) -> None:
    checklist = project_dir / "analysis" / "mandatory-checklist.md"
    if not checklist.exists():
        return
    text = checklist.read_text(encoding="utf-8", errors="replace")
    for status in UNRESOLVED_STATUSES:
        if status in text:
            add_issue(issues, "blocker", f"强制条款仍存在未闭环状态: {status}", checklist)


def check_placeholders(project_dir: Path, issues: list[dict]) -> None:
    for path in project_dir.rglob("*.md"):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "{{" in text or "}}" in text:
            add_issue(issues, "warning", "文件中仍存在模板占位符", path)
        if re.search(r"\[[^\]]*(公司全称|项目名称|姓名|填写|待补)[^\]]*\]", text):
            add_issue(issues, "warning", "文件中仍存在待填写占位内容", path)


def check_output_presence(project_dir: Path, issues: list[dict]) -> None:
    output_dir = project_dir / "output"
    if not output_dir.exists():
        add_issue(issues, "warning", "尚未生成 output 目录", output_dir)
        return
    for folder_name in ("商务文件", "技术文件", "资格证明文件"):
        folder = output_dir / folder_name
        if not folder.exists():
            add_issue(issues, "warning", f"缺少输出目录: {folder_name}", folder)


def check_final_docx(project_dir: Path, issues: list[dict]) -> None:
    final_docx = project_dir / "output" / FINAL_DOCX_NAME
    if not final_docx.exists():
        add_issue(issues, "blocker", f"缺少最终 DOCX 响应文件: {FINAL_DOCX_NAME}", final_docx)
        return
    report_path = final_docx.with_suffix(".format-report.json")
    if not report_path.exists():
        add_issue(issues, "blocker", "最终 DOCX 尚未完成格式校验", report_path)
        return
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        add_issue(issues, "blocker", f"DOCX 格式校验报告无法解析: {exc}", report_path)
        return
    if not report.get("ok"):
        add_issue(issues, "blocker", "最终 DOCX 格式校验未通过", report_path)


def write_validation_report(project_dir: Path, result: dict) -> None:
    review_dir = project_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# 投标文件质量门禁报告", "", f"结论：{'通过' if result['ok'] else '未通过'}", ""]
    lines.extend(["| 级别 | 问题 | 文件 |", "|---|---|---|"])
    for issue in result["issues"]:
        lines.append(f"| {issue['level']} | {issue['message']} | `{issue['file']}` |")
    if not result["issues"]:
        lines.append("| ok | 未发现阻塞项 |  |")
    (review_dir / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (review_dir / "validation-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def validate_project(project_dir: Path) -> dict:
    project_dir = project_dir.expanduser().resolve()
    issues: list[dict] = []
    if not project_dir.exists():
        add_issue(issues, "blocker", "项目目录不存在", project_dir)
    else:
        check_required_analysis(project_dir, issues)
        check_mandatory_status(project_dir, issues)
        check_output_presence(project_dir, issues)
        check_final_docx(project_dir, issues)
        check_placeholders(project_dir, issues)
    ok = not any(issue["level"] == "blocker" for issue in issues)
    result = {"project_dir": str(project_dir), "ok": ok, "issues": issues}
    write_validation_report(project_dir, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a bid project package.")
    parser.add_argument("project_dir", type=Path, help="Project directory under bid-projects.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_project(args.project_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
