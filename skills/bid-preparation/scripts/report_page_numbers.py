"""Report actual page numbers of every heading in the final DOCX.

INPUT: final DOCX built by build_response_docx.py (optionally a pre-exported PDF).
OUTPUT: <docx>.page-map.md / .json — 标题→实际页码对照表，供回填三张导航表页码；
        Word 可用时同时更新文档内目录域/页码域并保存（自动留 .bak 备份）。
POS: Stage 6/7 helper for the bid-preparation skill — 页码回填半自动化。

页码获取策略（按顺序降级）：
1. 本机 Microsoft Word 或 WPS 文字（COM 自动化）：更新域 → 备份并保存 →
   直接读取每个标题段落的真实页码（Range.Information，精确，无匹配歧义）
2. --pdf 显式提供已定稿导出的 PDF：按文本匹配定位（过滤目录点线行；
   标题文本若在导航表/正文中重复出现可能错位，输出后需人工抽查）
3. LibreOffice soffice：转换 PDF 后同上文本匹配（不更新目录域）
4. 均不可用：报错并给出手动导出 PDF 后重跑的指引

对照表生成后，导航表中的 `P__` 占位按表中页码人工回填——这是半自动方案：
标题定位全自动，落表仍由人工确认，避免错填导致的废标风险。
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


# Word 与 WPS 文字的 COM 对象模型兼容（Documents/Fields/TablesOfContents/ExportAsFixedFormat）
OFFICE_COM_APPS = [
    ("Word.Application", "Microsoft Word"),
    ("KWPS.Application", "WPS 文字"),
    ("WPS.Application", "WPS 文字（旧版）"),
]


def collect_page_map_via_office(docx_path: Path) -> tuple[list[dict], int] | None:
    """用本机 Word/WPS 更新域并直接读取每个标题段落的真实页码。

    返回 (标题页码列表, 总页数)；Word 和 WPS 均不可用时返回 None。
    比 PDF 文本匹配精确：标题文本在目录页/导航表中重复出现不会造成错位。
    """
    backup_path = docx_path.with_suffix(".docx.bak")
    shutil.copy2(docx_path, backup_path)
    for prog_id, app_label in OFFICE_COM_APPS:
        with tempfile.TemporaryDirectory() as temp_name:
            map_file = Path(temp_name) / "page-map.tsv"
            # 更新域后必须 Save：目录域展开会改变后续内容的页码，保存后 DOCX 分页才与对照表一致。
            # OutlineLevel 1-4 即 Heading 1-4（正文为 10）；Information(3) = 当前页码。
            # 旧版 Word（如 12.0）在 Close 后 Quit 可能抛 RPC 断开异常，属正常退出，不作为失败。
            script = f"""
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject {prog_id}
$app.Visible = $false
try {{ $app.DisplayAlerts = 0 }} catch {{}}
try {{
  $doc = $app.Documents.Open('{docx_path}')
  $doc.Fields.Update() | Out-Null
  foreach ($toc in $doc.TablesOfContents) {{ $toc.Update() | Out-Null }}
  $doc.Save()
  $lines = New-Object System.Collections.Generic.List[string]
  $total = $doc.ComputeStatistics(2)
  $lines.Add("#total`t$total")
  foreach ($para in $doc.Paragraphs) {{
    $level = [int]$para.OutlineLevel
    if ($level -ge 1 -and $level -le 4) {{
      $text = $para.Range.Text.Trim()
      if ($text) {{
        $page = $para.Range.Information(3)
        $lines.Add("$level`t$page`t$text")
      }}
    }}
  }}
  [System.IO.File]::WriteAllLines('{map_file}', $lines, (New-Object System.Text.UTF8Encoding($false)))
  $doc.Close(0)
}} finally {{
  try {{ $app.Quit() }} catch {{}}
}}
"""
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", script],
                    capture_output=True,
                    timeout=600,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if not map_file.exists():
                continue
            mapping = []
            total_pages = 0
            for line in map_file.read_text(encoding="utf-8").splitlines():
                parts = line.split("\t")
                if parts[0] == "#total" and len(parts) == 2:
                    total_pages = int(parts[1])
                elif len(parts) >= 3:
                    mapping.append({
                        "level": int(parts[0]),
                        "page": int(parts[1]),
                        "text": "\t".join(parts[2:]).strip(),
                    })
            if mapping:
                print(f"已用 {app_label} 更新目录域并读取标题页码（原文件备份于 {backup_path.name}）")
                return mapping, total_pages
    return None


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
    print("已用 LibreOffice 导出 PDF（注意：soffice 不更新目录域，目录页码仍需在 Word 中更新）")
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
                search_from = index  # 后续标题不会早于当前页
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
        "> 回填后请在 Word 中抽查 3-5 条确认无偏差。",
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


def report_page_numbers(docx_path: Path, pdf_path: Path | None) -> dict:
    docx_path = docx_path.expanduser().resolve()
    if not docx_path.exists():
        raise SystemExit(f"DOCX 不存在: {docx_path}")

    if pdf_path is not None:
        mapping, total_pages = map_via_pdf(docx_path, pdf_path.expanduser().resolve())
    else:
        office_result = collect_page_map_via_office(docx_path)
        if office_result is not None:
            mapping, total_pages = office_result
        else:
            with tempfile.TemporaryDirectory() as temp_name:
                soffice_pdf = export_pdf_via_soffice(docx_path, Path(temp_name))
                if soffice_pdf is None:
                    raise SystemExit(
                        "本机没有可用的 Word / WPS / LibreOffice。请在 Word 或 WPS 中打开文档，"
                        "更新目录域后导出 PDF，再运行：\n"
                        f"  python report_page_numbers.py \"{docx_path}\" --pdf <导出的PDF路径>"
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
    parser = argparse.ArgumentParser(description="Report heading page numbers of the final DOCX.")
    parser.add_argument("docx_path", type=Path, help="Final DOCX file.")
    parser.add_argument("--pdf", type=Path, default=None, help="已定稿导出的 PDF（跳过自动导出）.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = report_page_numbers(args.docx_path, args.pdf)
    return 0 if not result["missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
