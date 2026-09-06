"""P2 content quality gates: chapter depth + requirement coverage.

INPUT: bid-projects/<project> directory (analysis + output markdown).
OUTPUT: analysis/content-quality-report.md/json and exit code.
POS: Stage 5/7 quality helper — 章内深度与采购需求/★覆盖率统计。

Depth rules (technical markdown under output/技术文件):
  - Each H2/H3 section (## / ###) body should reach min effective chars
    (default 400 for H2, 200 for H3) unless marked 不适用
  - Fragment list density: too many short "- " lines → warning
  - PM/implementation keywords when project type needs them

Coverage rules:
  - From mandatory-checklist: 废标/★ rows must have 正文/方案位置 that appears
    in technical (or business) output text
  - Optional: analysis/requirement-index.md rows with 需求编号 must appear in output
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


HEADING_RE = re.compile(r"^(#{2,4})\s+(.+)$")
LIST_LINE_RE = re.compile(r"^[-*+]\s+\S")
EFFECTIVE_RE = re.compile(r"\s+")
# 行首「**引导词：**」+ 正文，如 `**保密承诺：** 我方承诺……`
# 它不是列表行，会被当成正文段，从而绕过碎片清单检测——实为伪装的碎片清单文风，
# 且一旦离开本 Skill 的渲染器（直接粘进 Word / 别的工具），星号会原样漏出。
LEAD_IN_BOLD_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.、]\s*)?\*\*[^*]{1,20}[:：]\*\*\s*\S")


def add_issue(issues: list[dict], level: str, message: str, file_path: str = "") -> None:
    issues.append({"level": level, "message": message, "file": file_path})


def effective_len(text: str) -> int:
    return len(EFFECTIVE_RE.sub("", text))


def collect_output_text(project_dir: Path, folders: tuple[str, ...]) -> tuple[str, list[Path]]:
    chunks: list[str] = []
    files: list[Path] = []
    for folder in folders:
        root = project_dir / "output" / folder
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            files.append(path)
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks), files


def parse_sections(md_text: str) -> list[dict]:
    """Split markdown into sections by ## / ### / #### headings."""
    lines = md_text.splitlines()
    sections: list[dict] = []
    current: dict | None = None
    for line in lines:
        match = HEADING_RE.match(line.strip())
        if match:
            if current is not None:
                sections.append(current)
            level = len(match.group(1))
            title = match.group(2).strip()
            current = {"level": level, "title": title, "body_lines": []}
        elif current is not None:
            current["body_lines"].append(line)
    if current is not None:
        sections.append(current)
    for section in sections:
        body = "\n".join(section["body_lines"])
        section["body"] = body
        section["chars"] = effective_len(body)
        section["list_lines"] = sum(1 for ln in section["body_lines"] if LIST_LINE_RE.match(ln.strip()))
        section["lead_in_bold_lines"] = sum(
            1 for ln in section["body_lines"] if LEAD_IN_BOLD_RE.match(ln)
        )
        # 「**引导词：** 正文」不算成段论述，从 paragraph_lines 中剔除，否则会掩盖碎片文风
        section["paragraph_lines"] = sum(
            1
            for ln in section["body_lines"]
            if ln.strip()
            and not LIST_LINE_RE.match(ln.strip())
            and not LEAD_IN_BOLD_RE.match(ln)
            and not ln.strip().startswith("|")
            and not ln.strip().startswith("#")
            and not ln.strip().startswith("!")
        )
    return sections


def check_section_depth(
    project_dir: Path,
    issues: list[dict],
    stats: dict,
    min_h2: int = 400,
    min_h3: int = 200,
) -> None:
    tech_dir = project_dir / "output" / "技术文件"
    if not tech_dir.exists():
        stats["depth"] = {"sections": 0, "thin": 0, "skipped": True}
        return

    thin: list[dict] = []
    total_sections = 0
    all_sections: list[dict] = []
    for path in sorted(tech_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        sections = parse_sections(text)
        for section in sections:
            # 只考核 H2/H3 主体节；H4 多为小节
            if section["level"] not in {2, 3}:
                continue
            title = section["title"]
            if any(skip in title for skip in ("目录", "封面", "导航", "不适用")):
                continue
            if "不适用" in section["body"][:80]:
                continue
            total_sections += 1
            threshold = min_h2 if section["level"] == 2 else min_h3
            record = {
                "file": str(path.relative_to(project_dir)),
                "level": section["level"],
                "title": title[:60],
                "chars": section["chars"],
                "threshold": threshold,
                "list_lines": section["list_lines"],
                "paragraph_lines": section["paragraph_lines"],
            }
            all_sections.append(record)
            if section["chars"] < threshold:
                thin.append(record)
                add_issue(
                    issues,
                    "warning",
                    f"章内偏薄（有效字数 {section['chars']}<{threshold}）: {title[:40]}",
                    record["file"],
                )
            # 碎片列表：列表行多且段落少
            if section["list_lines"] >= 5 and section["paragraph_lines"] < 2:
                add_issue(
                    issues,
                    "warning",
                    f"疑似碎片清单文风（列表{section['list_lines']}行/正文段{section['paragraph_lines']}）: {title[:40]}",
                    record["file"],
                )
            # 「**引导词：** 一句话」堆砌：伪装成段落的碎片清单，且跨工具会漏出星号
            if section["lead_in_bold_lines"] >= 4:
                add_issue(
                    issues,
                    "warning",
                    f"「**引导词：**」式碎片文风（{section['lead_in_bold_lines']}处）: {title[:40]}"
                    "——改为「（1）（2）」成段论述，或提升为独立小节标题",
                    record["file"],
                )

    stats["depth"] = {
        "sections": total_sections,
        "thin": len(thin),
        "thin_sections": thin[:30],
        "min_h2": min_h2,
        "min_h3": min_h3,
    }
    if total_sections == 0 and any(tech_dir.rglob("*.md")):
        add_issue(
            issues,
            "warning",
            "技术文件有 Markdown 但未解析到 ##/### 章节（请用二级/三级标题组织）",
            str(tech_dir),
        )


def _parse_md_tables(text: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].strip().startswith("|"):
            index += 1
            continue
        block: list[list[str]] = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            raw = lines[index].strip()
            cells = [c.strip() for c in raw.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells if c):
                if not re.fullmatch(r"[\s|:\-]+", raw):
                    block.append(cells)
            index += 1
        if block:
            tables.append(block)
    return tables


def check_mandatory_coverage(project_dir: Path, issues: list[dict], stats: dict) -> None:
    checklist = project_dir / "analysis" / "mandatory-checklist.md"
    output_text, _ = collect_output_text(project_dir, ("技术文件", "商务文件"))
    norm_output = EFFECTIVE_RE.sub("", output_text)

    if not checklist.exists():
        stats["coverage"] = {"mandatory_rows": 0, "covered": 0, "missing": []}
        return

    text = checklist.read_text(encoding="utf-8", errors="replace")
    tables = _parse_md_tables(text)
    main = None
    for table in tables:
        if table and ("编号" in "".join(table[0]) or "条款" in "".join(table[0])):
            main = table
            break
    if main is None:
        stats["coverage"] = {"mandatory_rows": 0, "covered": 0, "missing": [], "note": "no table"}
        return

    header = main[0]

    def col(*names: str) -> int | None:
        for i, cell in enumerate(header):
            for name in names:
                if name in cell:
                    return i
        return None

    idx_risk = col("风险")
    idx_body = col("正文", "方案位置", "响应位置")
    idx_id = col("编号")
    idx_clause = col("条款", "原文")

    checked = 0
    covered = 0
    missing: list[dict] = []
    for row in main[1:]:
        risk = row[idx_risk] if idx_risk is not None and idx_risk < len(row) else ""
        if idx_risk is not None and risk and not any(k in risk for k in ("废标", "★", "强制")):
            continue
        body_loc = row[idx_body] if idx_body is not None and idx_body < len(row) else ""
        row_id = row[idx_id] if idx_id is not None and idx_id < len(row) else ""
        clause = row[idx_clause] if idx_clause is not None and idx_clause < len(row) else ""
        if not body_loc or body_loc in {"—", "-", "待填", "/"} or "{{" in body_loc:
            continue
        checked += 1
        # 正文位置关键词是否出现在 output（取位置字段中的连续中文/数字片段）
        needles = re.findall(r"[\u4e00-\u9fffA-Za-z0-9.·]{2,}", body_loc)
        hit = False
        for needle in needles:
            if needle in ("见", "详见", "完全满足", "无偏离", "技术方案", "商务文件"):
                continue
            if EFFECTIVE_RE.sub("", needle) in norm_output or needle in output_text:
                hit = True
                break
        # 也尝试条款原文截取
        if not hit and clause:
            snippet = EFFECTIVE_RE.sub("", clause)[:12]
            if len(snippet) >= 6 and snippet in norm_output:
                hit = True
        if hit:
            covered += 1
        else:
            missing.append({"id": row_id, "body_loc": body_loc[:80], "clause": clause[:40]})
            add_issue(
                issues,
                "warning",
                f"★/强制条款正文位置未在输出中命中: {row_id or body_loc[:30]}",
                "analysis/mandatory-checklist.md",
            )

    rate = (covered / checked) if checked else 1.0
    stats["coverage"] = {
        "mandatory_rows": checked,
        "covered": covered,
        "rate": round(rate, 3),
        "missing": missing[:40],
    }
    if checked and rate < 0.8:
        add_issue(
            issues,
            "warning",
            f"强制条款正文覆盖率 {covered}/{checked}={rate:.0%}（建议≥80%）",
            "analysis/mandatory-checklist.md",
        )


def check_requirement_index(project_dir: Path, issues: list[dict], stats: dict) -> None:
    """可选 requirement-index.md：需求编号列须在技术输出中出现。"""
    path = project_dir / "analysis" / "requirement-index.md"
    if not path.exists():
        stats["requirements"] = {"skipped": True}
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    output_text, _ = collect_output_text(project_dir, ("技术文件",))
    # 抓取类似 2.1.1 / 需求3.2 / ★2.1 的编号
    ids = set(re.findall(r"(?:采购需求|需求|条款)?\s*([★▲]?\d+(?:\.\d+){0,3})", text))
    ids = {i for i in ids if len(i) >= 2}
    missing = []
    for req_id in sorted(ids):
        if req_id not in output_text and f"（对应采购需求{req_id}）" not in output_text:
            # 宽松：编号本身出现即可
            if req_id not in output_text.replace(" ", ""):
                missing.append(req_id)
    covered = len(ids) - len(missing)
    rate = (covered / len(ids)) if ids else 1.0
    stats["requirements"] = {
        "total": len(ids),
        "covered": covered,
        "rate": round(rate, 3),
        "missing": missing[:50],
    }
    if ids and rate < 0.7:
        add_issue(
            issues,
            "warning",
            f"采购需求编号覆盖率 {covered}/{len(ids)}={rate:.0%}（建议≥70%，见 requirement-index）",
            str(path),
        )
    for req_id in missing[:15]:
        add_issue(issues, "warning", f"需求编号未在技术输出中检出: {req_id}", str(path))


def check_content_quality(project_dir: Path, min_h2: int = 400, min_h3: int = 200) -> dict:
    project_dir = project_dir.expanduser().resolve()
    issues: list[dict] = []
    stats: dict = {}
    if not project_dir.exists():
        add_issue(issues, "blocker", "项目目录不存在")
        return {"project_dir": str(project_dir), "ok": False, "issues": issues, "stats": stats}

    tech_exists = (project_dir / "output" / "技术文件").exists() and any(
        (project_dir / "output" / "技术文件").rglob("*.md")
    )
    if not tech_exists:
        add_issue(issues, "warning", "尚无技术文件输出，跳过深度与覆盖率硬统计")
        stats["skipped"] = True
    else:
        check_section_depth(project_dir, issues, stats, min_h2=min_h2, min_h3=min_h3)
        check_mandatory_coverage(project_dir, issues, stats)
        check_requirement_index(project_dir, issues, stats)

    ok = not any(i["level"] == "blocker" for i in issues)
    return {
        "project_dir": str(project_dir),
        "ok": ok,
        "issues": issues,
        "stats": stats,
        "gate": "p2-content-quality",
    }


def write_report(project_dir: Path, result: dict) -> None:
    analysis = project_dir / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    stats = result.get("stats") or {}
    cov = stats.get("coverage") or {}
    depth = stats.get("depth") or {}
    req = stats.get("requirements") or {}
    lines = [
        "# 内容质量报告（P2：深度 + 覆盖率）",
        "",
        f"结论：{'通过' if result['ok'] else '未通过'}（blocker 决定通过；warning 应处理）",
        "",
        "## 章内深度",
        f"- 考核章节数：{depth.get('sections', 0)}",
        f"- 偏薄章节数：{depth.get('thin', 0)}（H2≥{depth.get('min_h2', 400)}字 / H3≥{depth.get('min_h3', 200)}字）",
        "",
        "## ★/强制条款正文覆盖",
        f"- 检查行数：{cov.get('mandatory_rows', 0)}",
        f"- 命中：{cov.get('covered', 0)}",
        f"- 覆盖率：{cov.get('rate', '—')}",
        "",
        "## 采购需求编号覆盖（requirement-index，可选）",
    ]
    if req.get("skipped"):
        lines.append("- 未提供 analysis/requirement-index.md（可选）")
    else:
        lines.append(f"- 编号数：{req.get('total', 0)}；命中：{req.get('covered', 0)}；覆盖率：{req.get('rate', '—')}")
    lines.extend(["", "| 级别 | 问题 | 文件 |", "|---|---|---|"])
    if result["issues"]:
        for item in result["issues"]:
            lines.append(f"| {item['level']} | {item['message']} | `{item.get('file', '')}` |")
    else:
        lines.append("| ok | 未发现问题 |  |")
    lines.append("")
    (analysis / "content-quality-report.md").write_text("\n".join(lines), encoding="utf-8")
    (analysis / "content-quality-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check chapter depth and requirement coverage.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--min-h2", type=int, default=400, help="H2 章节最低有效字数")
    parser.add_argument("--min-h3", type=int, default=200, help="H3 章节最低有效字数")
    parser.add_argument("--no-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()
    result = check_content_quality(project_dir, min_h2=args.min_h2, min_h3=args.min_h3)
    if not args.no_report and project_dir.exists():
        write_report(project_dir, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # warning-only 仍 exit 0，便于 CI 汇总；有 blocker 才非 0
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
