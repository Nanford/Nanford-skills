"""Extract readable tender text into a qingtian-bid project (stage 1).

迁移来源见 CHANGELOG《脚本来源》，按设计稿 v1 第 3 步改造：
- 项目模式（--project）按 project-state.json 的 sources 登记清单整批提取，报告覆盖全部登记文件，
  阶段 1 能核对"每个招标文件和补遗都提取过"；
- 读取 xlsx 工程量清单（只用标准库解析 OOXML，不加依赖）；
- 老式 .xls（合肥的清单、限价普遍是这种，2026-10-30 两个真实项目都是）在临时副本上用 Excel / WPS 表格
  另存为 .xlsx（其次 LibreOffice）再按 xlsx 提取，用户的文件不动；都转不了才判失败，请用户另存；
- 老式 .doc、.xls 两路都转不了时，失败原因附上 Office 那一路的报错，不再吞掉；
- 路径超过 Windows 260 字符上限导致读写失败时，报告写明是路径太长和怎么缩短，不只给 Errno 2；
- 用户逐个声明的图纸（决策 2A，kind=drawing）提取不到文字（含本机读不了的格式）时标 drawing，按图号人工读取，
  不触发 R9 硬停，原因里写明缺什么；招标文件、补遗、清单和样本仍按 R9 判 needs_ocr / failed。
- DWG、DXF 图纸经 dwg_text 读图上的文字（DWG 要本机装 ODA File Converter，两种都要 ezdxf）；读得出足够文字的
  记 ok，事实卡照样按图号写出处。
- 报告逐项记录来源文件的 sha256，文件在提取后被替换时阶段 1 能发现；
- 扫描件提示不再列举 OCR 产品名，只指向本机处理（R26）。

INPUT: tender files in PDF, DOCX, DOC, XLSX, XLS, TXT, MD or CSV format, drawings in DWG or DXF; in project
       mode the sources list of <project>/project-state.json (path + kind: tender / drawing / sample);
       office_bridge (Word / WPS for .doc, Excel / WPS 表格 for .xls) when installed; dwg_text (ODA File
       Converter and ezdxf) for DWG / DXF.
OUTPUT: extracted TXT files plus extraction-report.md/json in the parent of the output directory
        (项目模式为 analysis/). Report marks needs_ocr / failed so stage 1 can hard-stop (R9).
POS: Stage 1 extraction helper for qingtian-bid. Everything stays on the local disk (R26).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import dwg_text
import office_bridge


SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".csv"}
SOURCE_KINDS = ("tender", "drawing", "sample")
PASSING_STATUSES = {"ok", "drawing"}
# 低于此字数（去空白）视为提取不可靠，可能是扫描件或加密 PDF
MIN_USABLE_CHARS = 200
# 多页 PDF 平均每页有效字数过低 → needs_ocr
MIN_AVG_CHARS_PER_PAGE = 40
XLSX_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
XLSX_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
CELL_BREAKS = re.compile(r"\s*[\r\n]+\s*")
# Windows 默认的路径上限（MAX_PATH 含结尾的空字符）；系统开了长路径支持时不受此限，所以只在读写失败后才这样解释
WINDOWS_MAX_PATH = 260
# Office 报错往往带整段 PowerShell 输出，进提取报告的只留开头这么多字，够看出是没装、被占用还是打不开
OFFICE_FAILURE_NOTE_LIMIT = 300


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


def _xlsx_shared_strings(package: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in package.namelist():
        return []
    root = ElementTree.fromstring(package.read("xl/sharedStrings.xml"))
    # 一个共享字符串可能由多段富文本 <r><t> 组成，按顺序拼接
    return ["".join(node.text or "" for node in item.iter(f"{{{XLSX_NS['s']}}}t"))
            for item in root.findall("s:si", XLSX_NS)]


def _xlsx_sheet_paths(package: zipfile.ZipFile) -> list[tuple[str, str]]:
    """按工作簿里的顺序返回 (工作表名, 包内路径)。"""
    workbook = ElementTree.fromstring(package.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(package.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.get("Id"): rel.get("Target", "") for rel in rels}
    sheets = []
    for sheet in workbook.findall("s:sheets/s:sheet", XLSX_NS):
        target = targets.get(sheet.get(XLSX_REL), "").lstrip("/")
        sheets.append((sheet.get("name", ""), target if target.startswith("xl/") else f"xl/{target}"))
    return sheets


def _xlsx_cell_text(cell: ElementTree.Element, shared: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{XLSX_NS['s']}}}t"))
    value = cell.findtext("s:v", default="", namespaces=XLSX_NS)
    if cell_type == "s" and value.isdigit() and int(value) < len(shared):
        return shared[int(value)]
    return value  # 数字、布尔、公式缓存值原样输出，工程量按清单原值核对


def extract_xlsx(path: Path) -> str:
    """工程量清单：每个工作表一段，每行单元格用制表符分隔。"""
    with zipfile.ZipFile(path) as package:
        shared = _xlsx_shared_strings(package)
        blocks = []
        for name, sheet_path in _xlsx_sheet_paths(package):
            root = ElementTree.fromstring(package.read(sheet_path))
            rows = []
            for row in root.iter(f"{{{XLSX_NS['s']}}}row"):
                # 单元格内换行（清单的项目特征描述常是"1．……2．……"多行）压成空格：一行清单留在一行文本里，
                # 事实卡才能在同一行认出编码、单位和工程量
                cells = [CELL_BREAKS.sub(" ", _xlsx_cell_text(cell, shared).strip())
                         for cell in row.findall("s:c", XLSX_NS)]
                if any(cells):
                    rows.append("\t".join(cells))
            blocks.append(f"--- 工作表：{name} ---\n" + "\n".join(rows))
    return "\n\n".join(blocks)


def load_pdf_reader() -> type:
    # 动态导入，pypdf 与 PyPDF2 的 PdfReader 没有共同的静态类型，只能标成 type
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


def office_failure_note(error: Exception | None) -> str:
    """Office 那一路失败的原因，附在最后的报错后面进提取报告；没有失败过就不附。

    Office 失败后仍要转去 LibreOffice，所以原因不能当场抛出；但两路都不成时只报"转不了"，
    用户分不清是没装、被占用还是文件打不开，这里把它留下来。
    """
    if error is None:
        return ""
    detail = " ".join(str(error).split()) or type(error).__name__
    return f" Office 转换失败的原因：{detail[:OFFICE_FAILURE_NOTE_LIMIT]}"


def extract_doc_with_office_or_soffice(path: Path) -> str:
    """旧版 .doc：优先 Word/WPS COM 转文本，其次 LibreOffice soffice。"""
    # 1) Microsoft Word / WPS 文字（Windows 常见，兼容 WPS Office）
    office_error: Exception | None = None
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            txt_path = Path(temp_dir) / f"{path.stem}.txt"
            app_label = office_bridge.convert_doc_to_txt(path, txt_path, prefer="auto")
            if app_label and txt_path.exists():
                return read_plain_text(txt_path)
    except Exception as error:  # Office 自动化的任何失败都转去 LibreOffice，原因留到最后的报错里
        office_error = error

    # 2) LibreOffice
    soffice = shutil_which("soffice")
    if not soffice:
        raise RuntimeError(
            "旧版 .doc 需要本机 Microsoft Word、WPS 文字或 LibreOffice/soffice 之一进行转换。"
            "请安装 WPS Office / Office 后重试，或另存为 .docx 再提取。" + office_failure_note(office_error)
        )
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "txt:Text", "--outdir", temp_dir, str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
            return read_plain_text(Path(temp_dir) / f"{path.stem}.txt")
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(
                "旧版 .doc 用 LibreOffice 也没有转成功，请另存为 .docx 再提取。"
                f" LibreOffice 的报错：{' '.join(str(error).split())[:OFFICE_FAILURE_NOTE_LIMIT]}"
                + office_failure_note(office_error)
            ) from error


def extract_xls_with_office_or_soffice(path: Path) -> str:
    """老式 .xls：先另存为 .xlsx（Excel / WPS 表格，其次 LibreOffice），再按 xlsx 提取。"""
    office_error: Exception | None = None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        converted = Path(temp_dir) / "source.xlsx"
        try:
            office_bridge.convert_xls_to_xlsx(path, converted)
        except Exception as error:  # Office 自动化的任何失败都转去 LibreOffice，原因留到最后的报错里
            office_error = error
        if not converted.is_file():
            soffice = shutil_which("soffice")
            if soffice:
                copy = Path(temp_dir) / "source.xls"
                shutil.copy2(path, copy)
                try:
                    subprocess.run([soffice, "--headless", "--convert-to", "xlsx", "--outdir", temp_dir, str(copy)],
                                   capture_output=True, text=True, timeout=300)
                except (OSError, subprocess.SubprocessError):
                    pass  # 转不出来就落到下面的统一提示
        if not converted.is_file():
            raise RuntimeError(
                "老式 .xls 要靠本机的 Excel、WPS 表格或 LibreOffice 另存为 .xlsx 才能提取，这次没有转成功。"
                "请在 Excel 或 WPS 里另存为 .xlsx 或 PDF 后重新提取。" + office_failure_note(office_error)
            )
        return extract_xlsx(converted)


def shutil_which(command: str) -> str | None:
    # Local helper keeps the import surface obvious for Windows environments.
    import shutil

    return shutil.which(command)


def thin_text_status(text: str, label: str) -> tuple[str, str, str | None]:
    if count_effective_chars(text) < MIN_USABLE_CHARS:
        return text, "needs_ocr", f"{label} 有效字数不足 {MIN_USABLE_CHARS}，请核对文件是否完整。"
    return text, "ok", None


class UnsupportedFileTypeError(RuntimeError):
    """格式本身读不了，和文件损坏、加密这类读取失败分开，只有这一种能按声明的图纸放行。"""


def extract_one(path: Path) -> tuple[str, str, str | None]:
    """返回 (text, status, reason)。status: ok | needs_ocr | failed。"""
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_TEXT_EXTENSIONS:
        return thin_text_status(read_plain_text(path), "文本")
    if suffix == ".docx":
        return thin_text_status(html.unescape(extract_docx(path)), "DOCX")
    if suffix == ".xlsx":
        return thin_text_status(extract_xlsx(path), "XLSX")
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".doc":
        return thin_text_status(extract_doc_with_office_or_soffice(path), "DOC 转换后")
    if suffix == ".xls":
        return thin_text_status(extract_xls_with_office_or_soffice(path), "XLS 转换后")
    if suffix in dwg_text.DRAWING_SUFFIXES:
        try:
            return thin_text_status(dwg_text.read_drawing_text(path), "图纸文字")
        except dwg_text.DrawingUnreadable as exc:
            # 工具没装、转换失败都算"这个格式在本机读不了"：声明过的图纸放行，其他类别照旧判 failed（R9）
            raise UnsupportedFileTypeError(str(exc)) from exc
    raise UnsupportedFileTypeError(f"暂不支持的文件类型: {suffix or '无扩展名'}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def output_name(path: Path, used: set[str]) -> str:
    """同名不同扩展名的文件（招标文件.pdf 与 招标文件.docx）不能互相覆盖。"""
    name = f"{path.stem}.txt"
    if name in used:
        name = f"{path.stem}-{path.suffix.lstrip('.').lower()}.txt"
    used.add(name)
    return name


def extract_by_kind(path: Path, kind: str) -> tuple[str, str, str | None]:
    """声明过的图纸格式读不了（如 DWG）也算提取不到文字；其他类别照旧抛异常、判 failed（R9）。"""
    try:
        return extract_one(path)
    except UnsupportedFileTypeError as exc:
        if kind != "drawing":
            raise
        # 原因留着：DWG 读不了时要告诉用户缺什么工具、怎么补
        return "", "drawing", f"图纸，{exc}；图上的事实按图号人工读取（不触发 R9 硬停）"


def extract_entry(path: Path, kind: str, target: Path) -> dict:
    text, status, reason = extract_by_kind(path, kind)
    if kind == "drawing" and status == "needs_ocr":
        # 决策 2A：只有用户声明过的图纸放宽，图上的事实按图号人工读取并在事实卡里写图号
        status, reason = "drawing", "图纸，提取不到足够文字，按图号人工读取（不触发 R9 硬停）"
    # 即使 needs_ocr 也落盘已提取片段，便于用户判断是否补 OCR
    target.write_text((text or "").strip() + "\n", encoding="utf-8")
    entry = {
        "file": str(path),
        "kind": kind,
        "sha256": file_sha256(path),
        "status": status,
        "output": str(target),
        "effective_chars": count_effective_chars(text or ""),
    }
    if reason:
        entry["reason"] = reason
    return entry


def failure_reason(exc: Exception, paths: list[Path], windows: bool = os.name == "nt") -> str:
    """读写失败而路径又超过 Windows 上限的，说清是路径太长、怎么缩短；其余原样给出异常信息。"""
    too_long = [path for path in paths if len(str(path)) >= WINDOWS_MAX_PATH]
    if not (windows and isinstance(exc, OSError) and too_long):
        return str(exc)
    longest = max(len(str(path)) for path in too_long)
    return (f"路径太长：最长的一个有 {longest} 个字符，超过 Windows 默认的 {WINDOWS_MAX_PATH - 1} 字符上限，"
            f"文件读写失败（{exc.strerror or exc}）。把项目目录放到更短的位置，或把来源文件改成短一些的文件名、"
            "用 project_status.py --add-source 重新登记，再提取。")


def extract_files(paths: list[Path], output_dir: Path, kinds: dict[Path, str] | None = None) -> list[dict]:
    """kinds 按解析后的路径给出 tender / drawing / sample，没给的按 tender 处理。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    kinds = kinds or {}
    used: set[str] = set()
    report = []
    for path in [item.expanduser().resolve() for item in paths]:
        kind = kinds.get(path, "tender")
        target = output_dir / output_name(path, used)
        try:
            report.append(extract_entry(path, kind, target))
        except Exception as exc:
            report.append({"file": str(path), "kind": kind, "status": "failed",
                           "reason": failure_reason(exc, [path, target])})
    write_report(report, output_dir)
    return report


def gate_passes(report: list[dict]) -> bool:
    return bool(report) and all(item.get("status") in PASSING_STATUSES for item in report)


def write_report(report: list[dict], output_dir: Path) -> None:
    gate_ok = gate_passes(report)
    kind_labels = {"tender": "招标文件", "drawing": "图纸", "sample": "响应样本"}
    lines = [
        "# 文本提取报告",
        "",
        f"**阶段1硬停止门禁**：{'通过（可进入阶段2）' if gate_ok else '未通过——存在 failed/needs_ocr，禁止解标与写作'}",
        "",
        # 这里不列 OCR 产品名：有的产品会上传文件，与 R26 本机处理冲突
        "> 扫描件处理：向用户索取可复制文字的电子版，或经用户同意由用户在本机用 OCR 软件转成文字版，"
        "用 project_status.py --add-source 换上后重新提取；强制条款或官方格式表所在文件不可读时，不得靠猜继续。",
        "> 状态为 drawing 的是用户声明过的图纸：提取不到文字不阻断，图上的事实按图号人工读取。",
        "",
        "| 文件 | 类别 | 状态 | 有效字数 | 输出/原因 |",
        "|---|---|---|---:|---|",
    ]
    for item in report:
        detail = item.get("reason") or item.get("output") or ""
        chars = item.get("effective_chars", "")
        kind = kind_labels.get(item.get("kind", "tender"), item.get("kind", ""))
        lines.append(f"| `{item['file']}` | {kind} | {item['status']} | {chars} | {detail} |")
    if not gate_ok:
        lines.extend([
            "",
            "## 未通过时的动作",
            "1. 对 needs_ocr / failed 文件向用户索取可复制文字版，或经用户同意在本机 OCR",
            "2. 重新运行 extract_text.py",
            "3. 本报告全部为 ok（图纸可为 drawing）后，才可 `--complete 1` 并进入阶段2",
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


def registered_sources(project_dir: Path) -> list[tuple[Path, str]]:
    """读 project-state.json 的 sources；相对路径相对于项目目录。"""
    state_file = project_dir / "project-state.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"项目状态无法读取: {state_file} ({exc})") from exc
    sources = state.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("项目状态没有登记招标文件清单（sources），先用 project_status.py --add-source 补登")
    resolved = []
    for entry in sources:
        kind = entry.get("kind")
        if kind not in SOURCE_KINDS:
            raise ValueError(f"来源类别只能是 {'/'.join(SOURCE_KINDS)}（当前: {kind}）")
        path = Path(entry["path"])
        resolved.append(((path if path.is_absolute() else project_dir / path).resolve(), kind))
    return resolved


def extract_project(project_dir: Path) -> list[dict]:
    project_dir = project_dir.expanduser().resolve()
    sources = registered_sources(project_dir)
    return extract_files([path for path, _ in sources], project_dir / "analysis" / "extracted-text",
                         {path: kind for path, kind in sources})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="提取招标文件文本；--project 时按项目登记清单整批提取。")
    parser.add_argument("--project", type=Path, help="项目目录：按 project-state.json 的 sources 整批提取到 analysis/。")
    parser.add_argument("--output-dir", type=Path, help="不在项目里提取时的输出目录。")
    parser.add_argument("--drawing", type=Path, action="append", default=[],
                        help="不在项目里提取时：用户声明为图纸的文件；可重复。")
    parser.add_argument("files", type=Path, nargs="*", help="不在项目里提取时的招标文件。")
    args = parser.parse_args()
    if args.project is not None and (args.output_dir or args.files or args.drawing):
        parser.error("--project 按登记清单提取，不能再给 --output-dir、--drawing 或文件")
    if args.project is None and (args.output_dir is None or not (args.files or args.drawing)):
        parser.error("不在项目里提取时须给 --output-dir 和至少一个文件")
    return args


def main() -> int:
    args = parse_args()
    try:
        if args.project is not None:
            report = extract_project(args.project)
        else:
            drawings = [path.expanduser().resolve() for path in args.drawing]
            report = extract_files([*args.files, *drawings], args.output_dir,
                                   {path: "drawing" for path in drawings})
    except (OSError, ValueError) as exc:
        print(f"文本提取失败: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if gate_passes(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
