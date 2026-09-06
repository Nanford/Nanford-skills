"""Report actual page numbers of every heading in the final DOCX.

INPUT: final DOCX built by build_response_docx.py (optionally a pre-exported PDF).
OUTPUT: <docx>.page-map.md / .json — 标题→实际页码对照表，供回填三张导航表页码；
        Word/WPS 可用时同时更新文档内目录域/页码域并保存（自动留 .bak 备份）。
POS: Stage 6/7 helper for the bid-preparation skill — 页码回填半自动化。

页码获取策略（按顺序降级）：
1. 本机 Microsoft Word 或 WPS 文字（COM，见 office_bridge.py）：更新域 → 备份并保存 →
   读取每个标题段落真实页码（OutlineLevel 或 标题/Heading 样式）
2. Word/WPS 导出 PDF 后再文本匹配（次优）
3. --pdf 显式提供已定稿 PDF：文本匹配
4. LibreOffice soffice 转 PDF 后文本匹配
5. 均不可用：报错并给出在 WPS/Word 中手动导出 PDF 的指引

对照表生成后，导航表中的 `P__` 占位按表中页码人工回填并抽查。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from pypdf import PdfReader

try:
    from office_bridge import (
        collect_page_map_via_office,
        describe_office_support,
        export_pdf_via_office,
    )
except ImportError:  # 被 importlib 按文件加载时补 scripts 目录
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from office_bridge import (
        collect_page_map_via_office,
        describe_office_support,
        export_pdf_via_office,
    )


HEADING_STYLES = {"Heading 1": 1, "Heading 2": 2, "Heading 3": 3, "Heading 4": 4}


def normalize(text: str) -> str:
    """去除空白差异：PDF 提取会在中英文间插入空格并断行。"""
    return re.sub(r"[\s　]+", "", text)


def collect_headings(docx_path: Path) -> list[dict]:
    document = Document(docx_path)
    headings = []
    for paragraph in document.paragraphs:
        level = HEADING_STYLES.get(paragraph.style.name)
        text = paragraph.text.strip()
        if level and text:
            headings.append({"level": level, "text": text})
    return headings


def export_pdf_via_soffice(docx_path: Path, pdf_dir: Path) -> Path | None:
    soffice = shutil.which("soffice")
    if not soffice:
        return None
    try:
        completed = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf_dir), str(docx_path)],
            capture_output=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    candidate = pdf_dir / (docx_path.stem + ".pdf")
    if completed.returncode != 0 or not candidate.exists():
        return None
    print("已用 LibreOffice 导出 PDF（注意：soffice 不更新目录域，目录页码仍需在 Word/WPS 中更新）")
    return candidate


def strip_toc_lines(page_text: str) -> str:
    """去掉目录条目行（点线引导符+页码结尾），避免标题被错误定位到目录页。"""
    kept = [
        line for line in page_text.splitlines()
        if not re.search(r"[.．…]{4,}\s*\d+\s*$", line.strip())
    ]
    return "\n".join(kept)


def map_headings_to_pages(headings: list[dict], pages_text: list[str]) -> list[dict]:
    """按文档顺序把标题映射到首次出现的 PDF 页码（从上一命中页起向后搜索）。"""
    normalized_pages = [normalize(strip_toc_lines(page)) for page in pages_text]
    results = []
    search_from = 0
    for heading in headings:
        needle = normalize(heading["text"])
        page_number = None
        for index in range(search_from, len(normalized_pages)):
            if needle and needle in normalized_pages[index]:
                page_number = index + 1
                search_from = index
                break
        results.append({**heading, "page": page_number})
    return results


def write_reports(docx_path: Path, mapping: list[dict], total_pages: int) -> None:
    json_path = docx_path.with_suffix(".page-map.json")
    md_path = docx_path.with_suffix(".page-map.md")
    json_path.write_text(
        json.dumps({"total_pages": total_pages, "headings": mapping}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# 标题页码对照表",
        "",
        f"文档：{docx_path.name}　总页数：{total_pages}",
        "",
        "> 用途：按本表回填三张导航表的\"投标文件对应页码\"列（`P__` 占位）。",
        "> 回填后请在 **Word 或 WPS 文字** 中抽查 3-5 条确认无偏差。",
        "> WPS：选中目录 → 右键「更新域」；或 Ctrl+A 后 F9（部分版本为「工具→更新域」）。",
        "",
        "| 级别 | 标题 | 页码 |",
        "|---|---|---|",
    ]
    for item in mapping:
        page = item["page"] if item["page"] else "未定位"
        indent = "　" * (item["level"] - 1)
        lines.append(f"| {item['level']} | {indent}{item['text']} | {page} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"页码对照表已输出：{md_path}")


def map_via_pdf(docx_path: Path, pdf_path: Path) -> tuple[list[dict], int]:
    """降级路径：按 PDF 文本匹配定位标题页码。"""
    headings = collect_headings(docx_path)
    if not headings:
        raise SystemExit("文档中未发现任何标题段落")
    reader = PdfReader(str(pdf_path))
    pages_text = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:
            pages_text.append("")
    print("注意：当前为 PDF 文本匹配模式，标题文本若在导航表/正文中重复出现可能错位，请务必抽查。")
    return map_headings_to_pages(headings, pages_text), len(pages_text)


def report_page_numbers(
    docx_path: Path,
    pdf_path: Path | None,
    prefer: str = "auto",
) -> dict:
    docx_path = docx_path.expanduser().resolve()
    if not docx_path.exists():
        raise SystemExit(f"DOCX 不存在: {docx_path}")

    if pdf_path is not None:
        mapping, total_pages = map_via_pdf(docx_path, pdf_path.expanduser().resolve())
    else:
        backup_path = docx_path.with_suffix(".docx.bak")
        shutil.copy2(docx_path, backup_path)
        office_result = collect_page_map_via_office(docx_path, prefer=prefer)
        if office_result is not None:
            mapping, total_pages, app_label = office_result
            print(
                f"已用 {app_label} 更新目录域并读取标题页码"
                f"（原文件备份于 {backup_path.name}）"
            )
        else:
            # 次优：Office 导出 PDF 再匹配
            with tempfile.TemporaryDirectory() as temp_name:
                temp_dir = Path(temp_name)
                office_pdf = temp_dir / f"{docx_path.stem}.pdf"
                app_label = export_pdf_via_office(docx_path, office_pdf, prefer=prefer)
                if app_label and office_pdf.exists():
                    print(f"已用 {app_label} 导出 PDF 并做文本匹配（精度低于直接读页码）")
                    mapping, total_pages = map_via_pdf(docx_path, office_pdf)
                else:
                    soffice_pdf = export_pdf_via_soffice(docx_path, temp_dir)
                    if soffice_pdf is None:
                        raise SystemExit(
                            "本机没有可用的 Microsoft Word / WPS 文字 / LibreOffice。\n"
                            f"{describe_office_support()}\n"
                            "请任选其一：\n"
                            "  1) 安装 WPS Office 或 Microsoft Office 后重跑本脚本\n"
                            "  2) 在 WPS/Word 中打开文档 → 更新目录域 → 导出 PDF，再运行：\n"
                            f"     python report_page_numbers.py \"{docx_path}\" --pdf <导出的PDF路径>\n"
                            "  仅 WPS 时也可指定：  --office wps"
                        )
                    mapping, total_pages = map_via_pdf(docx_path, soffice_pdf)

    write_reports(docx_path, mapping, total_pages)
    missing = [item["text"] for item in mapping if item["page"] is None]
    if missing:
        print(f"警告：{len(missing)} 个标题未定位到页码：")
        for text in missing[:10]:
            print(f"  - {text}")
    return {"total_pages": total_pages, "headings": mapping, "missing": missing}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report heading page numbers of the final DOCX (Word/WPS compatible)."
    )
    parser.add_argument(
        "docx_path",
        type=Path,
        nargs="?",
        default=None,
        help="Final DOCX file（--probe 时可省略）.",
    )
    parser.add_argument("--pdf", type=Path, default=None, help="已定稿导出的 PDF（跳过自动 COM）.")
    parser.add_argument(
        "--office",
        choices=("auto", "word", "wps"),
        default="auto",
        help="COM 优先引擎：auto=先 Word 后 WPS；word=仅 Word；wps=仅 WPS 文字.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="仅探测本机 Word/WPS COM 是否可用，不处理文档.",
    )
    args = parser.parse_args()
    if not args.probe and args.docx_path is None:
        parser.error("请提供 docx_path，或使用 --probe 仅探测 Office")
    return args


def main() -> int:
    args = parse_args()
    if args.probe:
        try:
            from office_bridge import probe_office_apps
        except ImportError:
            import sys

            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from office_bridge import probe_office_apps

        probes = probe_office_apps(args.office)
        print(json.dumps({"support": describe_office_support(), "apps": probes}, ensure_ascii=False, indent=2))
        return 0 if any(p["available"] for p in probes) else 1
    result = report_page_numbers(args.docx_path, args.pdf, prefer=args.office)
    return 0 if not result["missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
