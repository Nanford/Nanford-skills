"""Validate bid project files before final delivery.

INPUT: bid-projects/<project> directory.
OUTPUT: review/validation-report.md/json and process exit code. The report ends
        with a 人工核查清单 section that consolidates every item still needing
        human action: blank attachment placeholders（此处附：XXX）, missing
        images from the DOCX build report, P__ page-number placeholders in the
        navigation tables, unresolved material gaps, and standing sign/seal +
        TOC-field reminders.
POS: Stage 7 compliance gate for the bid-preparation skill.
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

# 留空待补材料的占位写法（阶段4规则：资料库暂缺的材料写"（此处附：XXX）"独立一页）
BLANK_ATTACHMENT_PATTERN = re.compile(r"（此处附[:：][^）]{1,60}）")
# 导航表页码占位符（DOCX 定稿后按 page-map.md 对照表回填）
PAGE_PLACEHOLDER = "P__"
# 中间稿中不应出现的 Markdown 泄漏（**加粗** 为合法语法，不拦截）
MARKDOWN_LEAK_IN_MD = (
    (re.compile(r"`"), "反引号`"),
    (re.compile(r"^>\s+", re.MULTILINE), "引用块>"),
    (re.compile(r"\[([^\]]+)\]\((?!https?://)([^)]+)\)"), "非图片Markdown链接"),
    (re.compile(r"^---+\s*$", re.MULTILINE), "水平分割线---"),
)
# 技术文件必含模块关键词（项目管理/实施方案）
PM_KEYWORDS = ("项目管理", "实施方案", "实施计划", "施工方案", "项目实施", "进度计划", "组织保障")
OUTLINE_FILES = {
    "full": ("business-writing-outline.md", "technical-writing-outline.md"),
    "technical-only": ("technical-writing-outline.md",),
}


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


def check_markdown_leaks_in_output(project_dir: Path, issues: list[dict]) -> None:
    """扫描 output 下中间稿，拦截易泄漏进 DOCX 的 Markdown 语法。"""
    output_dir = project_dir / "output"
    if not output_dir.exists():
        return
    for path in sorted(output_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, label in MARKDOWN_LEAK_IN_MD:
            if pattern.search(text):
                add_issue(issues, "warning", f"输出稿存在 Markdown 痕迹（{label}），组装前请改写", path)


def check_writing_outline(project_dir: Path, issues: list[dict]) -> None:
    """写作大纲闸：有对应输出时，应存在已确认的大纲文件。"""
    analysis_dir = project_dir / "analysis"
    scope = "full"
    state_path = project_dir / "project-state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            scope = state.get("scope", "full")
        except (OSError, json.JSONDecodeError):
            pass
    expected = OUTLINE_FILES.get(scope, OUTLINE_FILES["full"])
    for filename in expected:
        path = analysis_dir / filename
        if not path.exists():
            add_issue(issues, "warning", f"缺少写作大纲: {filename}（阶段4/5大纲闸）", path)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "用户确认" not in text and "已确认" not in text:
            add_issue(issues, "warning", f"大纲尚未标注用户确认: {filename}", path)


def check_project_management_section(project_dir: Path, issues: list[dict]) -> None:
    """技术文件应包含项目管理/实施方案类专章（除非大纲已标注不适用）。"""
    tech_dir = project_dir / "output" / "技术文件"
    if not tech_dir.exists():
        return
    tech_files = list(tech_dir.rglob("*.md"))
    if not tech_files:
        return
    combined = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in tech_files)
    outline = project_dir / "analysis" / "technical-writing-outline.md"
    if outline.exists():
        outline_text = outline.read_text(encoding="utf-8", errors="replace")
        if re.search(r"项目管理|实施方案|施工方案", outline_text) and "不适用" in outline_text:
            # 大纲已声明不适用时不强制
            if not any(keyword in combined for keyword in PM_KEYWORDS):
                return
    if not any(keyword in combined for keyword in PM_KEYWORDS):
        add_issue(
            issues,
            "warning",
            "技术文件未检出项目管理/实施方案/进度计划等专章关键词，请核对大纲与正文",
            tech_dir,
        )


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


def relative_display_path(path: Path, project_dir: Path) -> str:
    try:
        return str(path.relative_to(project_dir))
    except ValueError:
        return str(path)


def collect_blank_attachments(project_dir: Path, actions: list[dict]) -> None:
    """扫描输出稿中的"（此处附：XXX）"留空页占位——每一处都是需人工补扫描件的材料。"""
    output_dir = project_dir / "output"
    if not output_dir.exists():
        return
    for path in sorted(output_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in BLANK_ATTACHMENT_PATTERN.findall(text):
            actions.append({
                "type": "留空待补材料",
                "item": f"{match} — 定稿前放入扫描件或确认以空页交付",
                "file": relative_display_path(path, project_dir),
            })


def collect_build_warnings(project_dir: Path, actions: list[dict]) -> None:
    """读取 DOCX 构建报告中的警告（图片缺失/插入失败等）。"""
    report_path = project_dir / "output" / FINAL_DOCX_NAME
    report_path = report_path.with_suffix(".build-report.json")
    if not report_path.exists():
        return
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        actions.append({
            "type": "构建报告异常",
            "item": f"构建报告无法读取（{exc}），需重新运行 build_response_docx.py",
            "file": relative_display_path(report_path, project_dir),
        })
        return
    for warning in report.get("warnings", []):
        actions.append({
            "type": "构建警告",
            "item": str(warning),
            "file": relative_display_path(report_path, project_dir),
        })


def collect_page_placeholders(project_dir: Path, actions: list[dict]) -> None:
    """统计导航表等文件中的 P__ 页码占位——DOCX 定稿后按 page-map.md 回填。"""
    output_dir = project_dir / "output"
    if not output_dir.exists():
        return
    for path in sorted(output_dir.rglob("*.md")):
        count = path.read_text(encoding="utf-8", errors="replace").count(PAGE_PLACEHOLDER)
        if count:
            actions.append({
                "type": "页码待回填",
                "item": f"{PAGE_PLACEHOLDER} 占位 {count} 处 — 运行 report_page_numbers.py 后按对照表回填并抽查",
                "file": relative_display_path(path, project_dir),
            })


def collect_material_gaps(project_dir: Path, actions: list[dict]) -> None:
    """从资料匹配表中提取仍未闭环的缺口行。"""
    status_file = project_dir / "analysis" / "material-match-status.md"
    if not status_file.exists():
        return
    for line in status_file.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and any(status in stripped for status in UNRESOLVED_STATUSES):
            summary = stripped.strip("|").replace("|", " / ").strip()
            actions.append({
                "type": "资料缺口",
                "item": summary[:120],
                "file": relative_display_path(status_file, project_dir),
            })


def collect_manual_actions(project_dir: Path) -> list[dict]:
    """汇总交付前必须人工核查/填写的全部事项（生成流程最后一步的输出）。"""
    actions: list[dict] = []
    collect_blank_attachments(project_dir, actions)
    collect_build_warnings(project_dir, actions)
    collect_page_placeholders(project_dir, actions)
    collect_material_gaps(project_dir, actions)
    if (project_dir / "output" / FINAL_DOCX_NAME).exists():
        actions.append({
            "type": "人工确认",
            "item": "在 Word 或 WPS 文字中更新目录域，并按 page-map.md 抽查 3-5 条导航表页码",
            "file": f"output/{FINAL_DOCX_NAME}",
        })
        actions.append({
            "type": "人工确认",
            "item": "投标函/承诺书/偏离表等落款处逐一签字盖章（打印后确认位置齐全）",
            "file": f"output/{FINAL_DOCX_NAME}",
        })
    return actions


def write_validation_report(project_dir: Path, result: dict) -> None:
    review_dir = project_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# 投标文件质量门禁报告", "", f"结论：{'通过' if result['ok'] else '未通过'}", ""]
    lines.extend(["| 级别 | 问题 | 文件 |", "|---|---|---|"])
    for issue in result["issues"]:
        lines.append(f"| {issue['level']} | {issue['message']} | `{issue['file']}` |")
    if not result["issues"]:
        lines.append("| ok | 未发现阻塞项 |  |")
    lines.extend(["", "## 人工核查清单（交付前逐项处理）", ""])
    manual_actions = result.get("manual_actions", [])
    if manual_actions:
        lines.extend(["| 类型 | 事项 | 位置 |", "|---|---|---|"])
        for action in manual_actions:
            lines.append(f"| {action['type']} | {action['item']} | `{action['file']}` |")
    else:
        lines.append("无需人工处理的遗留事项。")
    (review_dir / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (review_dir / "validation-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_sibling(module_name: str):
    """加载 scripts 同目录模块（兼容 importlib 单文件加载）。"""
    try:
        return __import__(module_name)
    except ImportError:
        import importlib.util

        sibling = Path(__file__).resolve().parent / f"{module_name}.py"
        if not sibling.exists():
            return None
        spec = importlib.util.spec_from_file_location(module_name, sibling)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module


def run_p0_gates(project_dir: Path, issues: list[dict]) -> None:
    """合并 P0 五项硬门禁（提取/硬参数/格式克隆/★三角/资料空壳禁写）与 P1 警告。"""
    module = _load_sibling("check_p0_gates")
    if module is None:
        add_issue(issues, "warning", "未找到 check_p0_gates.py，跳过 P0 门禁", project_dir)
        return
    p0 = module.check_all_p0(project_dir)
    module.write_report(project_dir, p0)
    for item in p0.get("issues", []):
        issues.append(item)


def run_p2_content_quality(project_dir: Path, issues: list[dict]) -> None:
    """P2：章内深度 + ★/需求覆盖率（有技术输出时）。"""
    tech = project_dir / "output" / "技术文件"
    if not tech.exists() or not any(tech.rglob("*.md")):
        return
    module = _load_sibling("check_content_quality")
    if module is None:
        add_issue(issues, "warning", "未找到 check_content_quality.py，跳过 P2 内容质量", project_dir)
        return
    result = module.check_content_quality(project_dir)
    module.write_report(project_dir, result)
    for item in result.get("issues", []):
        issues.append(item)


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
        check_markdown_leaks_in_output(project_dir, issues)
        check_writing_outline(project_dir, issues)
        check_project_management_section(project_dir, issues)
        run_p0_gates(project_dir, issues)
        run_p2_content_quality(project_dir, issues)
    ok = not any(issue["level"] == "blocker" for issue in issues)
    manual_actions = collect_manual_actions(project_dir) if project_dir.exists() else []
    result = {
        "project_dir": str(project_dir),
        "ok": ok,
        "issues": issues,
        "manual_actions": manual_actions,
    }
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
