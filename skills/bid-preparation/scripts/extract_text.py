"""Extract readable tender text into a project analysis directory.

INPUT: tender files in PDF, DOCX, DOC, TXT, MD, or CSV format.
OUTPUT: extracted TXT files plus extraction-report.md/json.
POS: Stage 1 extraction helper for the bid-preparation skill.
"""

from __future__ import annotations

import argparse
import html
import importlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree


SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".csv"}


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


def extract_pdf(path: Path) -> str:
    reader = load_pdf_reader()(str(path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"\n\n--- 第 {index} 页 ---\n{text}")
    joined = "\n".join(pages).strip()
    if not joined:
        raise RuntimeError("PDF 未提取到文字，可能是扫描件，需要 OCR 或人工确认。")
    return joined


def extract_doc_with_soffice(path: Path) -> str:
    soffice = shutil_which("soffice")
    if not soffice:
        raise RuntimeError("旧版 .doc 需要 LibreOffice/soffice 转换后再提取。")
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


def extract_one(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_TEXT_EXTENSIONS:
        return read_plain_text(path), "ok"
    if suffix == ".docx":
        return html.unescape(extract_docx(path)), "ok"
    if suffix == ".pdf":
        return extract_pdf(path), "ok"
    if suffix == ".doc":
        return extract_doc_with_soffice(path), "ok"
    raise RuntimeError(f"暂不支持的文件类型: {suffix or '无扩展名'}")


def extract_files(paths: list[Path], output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for path in [item.expanduser().resolve() for item in paths]:
        try:
            text, status = extract_one(path)
            target = output_dir / f"{path.stem}.txt"
            target.write_text(text.strip() + "\n", encoding="utf-8")
            report.append({"file": str(path), "status": status, "output": str(target)})
        except Exception as exc:
            report.append({"file": str(path), "status": "failed", "reason": str(exc)})
    write_report(report, output_dir)
    return report


def write_report(report: list[dict], output_dir: Path) -> None:
    lines = ["# 文本提取报告", "", "| 文件 | 状态 | 输出/原因 |", "|---|---|---|"]
    for item in report:
        detail = item.get("output") or item.get("reason", "")
        lines.append(f"| `{item['file']}` | {item['status']} | {detail} |")
    (output_dir.parent / "extraction-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir.parent / "extraction-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
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
    return 0 if all(item["status"] == "ok" for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
