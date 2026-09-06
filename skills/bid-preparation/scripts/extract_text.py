"""Extract readable tender text into a project analysis directory.

INPUT: tender files in PDF, DOCX, DOC, TXT, MD, or CSV format.
OUTPUT: extracted TXT files plus extraction-report.md/json.
        Report marks needs_ocr / failed so stage-1 can hard-stop (P0).
POS: Stage 1 extraction helper for the bid-preparation skill.
"""

from __future__ import annotations

import argparse
import html
import importlib
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree


SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".csv"}
# 低于此字数（去空白）视为提取不可靠，可能是扫描件或加密 PDF
MIN_USABLE_CHARS = 200
# 多页 PDF 平均每页有效字数过低 → needs_ocr
MIN_AVG_CHARS_PER_PAGE = 40


def read_plain_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as package:
        xml_bytes = package.read("word/document.xml")
    root = ElementTree.fromstring(xml_bytes)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        texts = [node.text or "" for node in paragraph.iter(f"{namespace}t")]
        if texts:
            paragraphs.append("".join(texts))
    return "\n".join(paragraphs)


def load_pdf_reader():
    for package_name in ("pypdf", "PyPDF2"):
        try:
            return importlib.import_module(package_name).PdfReader
        except (ImportError, AttributeError):
            continue
    raise RuntimeError("缺少 PDF 解析库，请安装 pypdf 或 PyPDF2。")


def count_effective_chars(text: str) -> int:
    """去掉页码分隔与空白后的有效字数，用于判断扫描件。"""
    cleaned = re.sub(r"---\s*第\s*\d+\s*页\s*---", " ", text)
    cleaned = re.sub(r"\s+", "", cleaned)
    return len(cleaned)


def assess_pdf_text_quality(text: str, page_count: int) -> tuple[str, str | None]:
    """返回 (status, reason)。status: ok | needs_ocr。"""
    effective = count_effective_chars(text)
    if effective == 0:
        return "needs_ocr", "PDF 未提取到文字，可能是扫描件，需要 OCR 或提供文字版。"
    if effective < MIN_USABLE_CHARS:
        return (
            "needs_ocr",
            f"PDF 有效文字仅 {effective} 字（<{MIN_USABLE_CHARS}），不足以可靠解标，需 OCR 或文字版。",
        )
    if page_count >= 3:
        avg = effective / page_count
        if avg < MIN_AVG_CHARS_PER_PAGE:
            return (
                "needs_ocr",
                f"PDF 共 {page_count} 页、平均每页约 {avg:.0f} 字（<{MIN_AVG_CHARS_PER_PAGE}），"
                "疑似扫描件/图片页，需 OCR 后才能继续。",
            )
    return "ok", None


def extract_pdf(path: Path) -> tuple[str, str, str | None]:
    """返回 (text, status, reason)。扫描件不抛异常，标记 needs_ocr 供阶段1硬停止。"""
    reader = load_pdf_reader()(str(path))
    pages = []
    page_count = len(reader.pages)
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"\n\n--- 第 {index} 页 ---\n{text}")
    joined = "\n".join(pages).strip()
    status, reason = assess_pdf_text_quality(joined, max(page_count, 1))
    return joined, status, reason


def extract_doc_with_office_or_soffice(path: Path) -> str:
    """旧版 .doc：优先 Word/WPS COM 转文本，其次 LibreOffice soffice。"""
    # 1) Microsoft Word / WPS 文字（Windows 常见，兼容 WPS Office）
    try:
        try:
            from office_bridge import convert_doc_to_txt
        except ImportError:
            import sys

            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from office_bridge import convert_doc_to_txt

        with tempfile.TemporaryDirectory() as temp_dir:
            txt_path = Path(temp_dir) / f"{path.stem}.txt"
            app_label = convert_doc_to_txt(path, txt_path, prefer="auto")
            if app_label and txt_path.exists():
                return read_plain_text(txt_path)
    except Exception:
        pass

    # 2) LibreOffice
    soffice = shutil_which("soffice")
    if not soffice:
        raise RuntimeError(
            "旧版 .doc 需要本机 Microsoft Word、WPS 文字或 LibreOffice/soffice 之一进行转换。"
            "请安装 WPS Office / Office 后重试，或另存为 .docx 再提取。"
        )
    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "txt:Text", "--outdir", temp_dir, str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        txt_path = Path(temp_dir) / f"{path.stem}.txt"
        return read_plain_text(txt_path)


def shutil_which(command: str) -> str | None:
    # Local helper keeps the import surface obvious for Windows environments.
    import shutil

    return shutil.which(command)


def extract_one(path: Path) -> tuple[str, str, str | None]:
    """返回 (text, status, reason)。status: ok | needs_ocr | failed。"""
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_TEXT_EXTENSIONS:
        text = read_plain_text(path)
        if count_effective_chars(text) < MIN_USABLE_CHARS:
            return text, "needs_ocr", f"文本有效字数不足 {MIN_USABLE_CHARS}，请核对文件是否完整。"
        return text, "ok", None
    if suffix == ".docx":
        text = html.unescape(extract_docx(path))
        if count_effective_chars(text) < MIN_USABLE_CHARS:
            return text, "needs_ocr", f"DOCX 有效字数不足 {MIN_USABLE_CHARS}，可能为空模板或损坏。"
        return text, "ok", None
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".doc":
        text = extract_doc_with_office_or_soffice(path)
        if count_effective_chars(text) < MIN_USABLE_CHARS:
            return text, "needs_ocr", f"DOC 转换后有效字数不足 {MIN_USABLE_CHARS}。"
        return text, "ok", None
    raise RuntimeError(f"暂不支持的文件类型: {suffix or '无扩展名'}")


def extract_files(paths: list[Path], output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for path in [item.expanduser().resolve() for item in paths]:
        try:
            text, status, reason = extract_one(path)
            target = output_dir / f"{path.stem}.txt"
            # 即使 needs_ocr 也落盘已提取片段，便于用户判断是否补 OCR
            target.write_text((text or "").strip() + "\n", encoding="utf-8")
            entry = {
                "file": str(path),
                "status": status,
                "output": str(target),
                "effective_chars": count_effective_chars(text or ""),
            }
            if reason:
                entry["reason"] = reason
            report.append(entry)
        except Exception as exc:
            report.append({"file": str(path), "status": "failed", "reason": str(exc)})
    write_report(report, output_dir)
    return report


def write_report(report: list[dict], output_dir: Path) -> None:
    gate_ok = all(item.get("status") == "ok" for item in report)
    lines = [
        "# 文本提取报告",
        "",
        f"**阶段1硬停止门禁**：{'通过（可进入阶段2）' if gate_ok else '未通过——存在 failed/needs_ocr，禁止解标与写作'}",
        "",
        "> 扫描件处理：使用 OCR（如 ABBYY / 天若 / Adobe / 微软 Lens）生成文字版 PDF/DOCX 后重新运行本脚本；"
        "强制条款或官方格式表所在文件不可读时，不得靠猜继续。",
        "",
        "| 文件 | 状态 | 有效字数 | 输出/原因 |",
        "|---|---|---:|---|",
    ]
    for item in report:
        detail = item.get("reason") or item.get("output") or ""
        chars = item.get("effective_chars", "")
        lines.append(f"| `{item['file']}` | {item['status']} | {chars} | {detail} |")
    if not gate_ok:
        lines.extend([
            "",
            "## 未通过时的动作",
            "1. 对 needs_ocr / failed 文件做 OCR 或向用户索取可复制文字版",
            "2. 重新运行 extract_text.py",
            "3. 本报告全部 status=ok 后，才可 `--complete 1` 并进入阶段2",
        ])
    report_parent = output_dir.parent
    (report_parent / "extraction-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "gate_ok": gate_ok,
        "items": report,
        "hard_stop": not gate_ok,
        "message": (
            "全部文件提取成功"
            if gate_ok
            else "存在提取失败或疑似扫描件，阶段1硬停止：禁止进入解标/写作"
        ),
    }
    (report_parent / "extraction-report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract tender text files.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output text directory.")
    parser.add_argument("files", type=Path, nargs="+", help="Tender files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = extract_files(args.files, args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item.get("status") == "ok" for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
