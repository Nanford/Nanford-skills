"""Windows Office automation bridge: Microsoft Word + WPS 文字 (Kingsoft).

INPUT: absolute file paths to DOCX/DOC; optional preferred app (auto|word|wps).
OUTPUT: helpers for COM automation used by report_page_numbers / extract_text.
POS: Shared Office compatibility layer for the bid-preparation skill.

ProgID 说明（Windows 注册表，本机装了哪个用哪个）:
  Word.Application          Microsoft Word
  KWPS.Application          WPS 文字（近年默认 ProgID）
  wps.Application           WPS 文字（部分安装）
  WPS.Application           WPS 文字（旧版）

WPS 与 Word 的对象模型大体兼容（Documents / Fields / TablesOfContents /
Range.Information / SaveAs），但部分版本 OutlineLevel 不可靠，故同时按
样式名（Heading 1–4 / 标题 1–4）识别标题。
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path


# 顺序：auto 时 Word 优先，其次各 WPS ProgID
WORD_PROG_IDS: list[tuple[str, str]] = [
    ("Word.Application", "Microsoft Word"),
]

WPS_PROG_IDS: list[tuple[str, str]] = [
    ("KWPS.Application", "WPS 文字"),
    ("wps.Application", "WPS 文字"),
    ("WPS.Application", "WPS 文字（旧版）"),
]

# SaveAs2 FileFormat: 12 = wdFormatXMLDocument (.docx), 2 = wdFormatText
WD_FORMAT_XML_DOCUMENT = 12
WD_FORMAT_TEXT = 2


def powershell_literal(path: Path | str) -> str:
    """把路径编码为 PowerShell 单引号字符串字面量（内嵌 ' 翻倍）。"""
    text = str(Path(path).resolve())
    return "'" + text.replace("'", "''") + "'"


def office_app_candidates(prefer: str = "auto") -> list[tuple[str, str]]:
    """返回 (ProgID, 显示名) 列表；prefer: auto | word | wps。"""
    prefer = (prefer or "auto").lower().strip()
    if prefer in {"word", "msword", "microsoft"}:
        return list(WORD_PROG_IDS)
    if prefer in {"wps", "kingsoft", "金山"}:
        return list(WPS_PROG_IDS)
    # auto：先 Word 后 WPS（装了 Word 时优先用 Word；仅 WPS 时会落到 WPS）
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for item in WORD_PROG_IDS + WPS_PROG_IDS:
        if item[0].lower() not in seen:
            seen.add(item[0].lower())
            ordered.append(item)
    return ordered


def run_office_powershell(script: str, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """执行 PowerShell 脚本；不抛异常，由调用方看 returncode/stdout。"""
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def probe_office_apps(prefer: str = "auto") -> list[dict]:
    """探测本机可创建的 Office COM 对象（不打开文档）。"""
    results = []
    for prog_id, label in office_app_candidates(prefer):
        script = f"""
$ErrorActionPreference = 'Stop'
try {{
  $app = New-Object -ComObject {prog_id}
  try {{ $app.Quit() }} catch {{}}
  Write-Output 'OK'
}} catch {{
  Write-Output ('FAIL:' + $_.Exception.Message)
  exit 1
}}
"""
        try:
            completed = run_office_powershell(script, timeout=60)
            ok = completed.returncode == 0 and "OK" in (completed.stdout or "")
            results.append({
                "prog_id": prog_id,
                "label": label,
                "available": ok,
                "detail": (completed.stdout or completed.stderr or "").strip()[:200],
            })
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append({
                "prog_id": prog_id,
                "label": label,
                "available": False,
                "detail": str(exc),
            })
    return results


def build_heading_page_map_script(docx_path: Path, map_file: Path, prog_id: str) -> str:
    """生成：打开 DOCX → 更新域 → 保存 → 导出 级别/页码/标题 TSV 的 PowerShell。"""
    docx_lit = powershell_literal(docx_path)
    map_lit = powershell_literal(map_file)
    # 标题识别：OutlineLevel 1-4，或样式名 Heading N / 标题 N（WPS 中文界面）
    return f"""
$ErrorActionPreference = 'Stop'
$app = $null
$doc = $null
try {{
  $app = New-Object -ComObject {prog_id}
  try {{ $app.Visible = $false }} catch {{}}
  try {{ $app.DisplayAlerts = 0 }} catch {{}}
  try {{ $app.ScreenUpdating = $false }} catch {{}}
  $doc = $app.Documents.Open({docx_lit}, $false, $false)
  try {{ $doc.Fields.Update() | Out-Null }} catch {{}}
  try {{
    foreach ($toc in $doc.TablesOfContents) {{
      try {{ $toc.Update() | Out-Null }} catch {{}}
    }}
  }} catch {{}}
  try {{ $doc.Save() }} catch {{}}
  $lines = New-Object System.Collections.Generic.List[string]
  $total = 0
  try {{ $total = $doc.ComputeStatistics(2) }} catch {{
    try {{ $total = $doc.ComputeStatistics(2, $false) }} catch {{ $total = 0 }}
  }}
  $lines.Add("#total`t$total")
  foreach ($para in $doc.Paragraphs) {{
    $level = 0
    try {{
      $ol = [int]$para.OutlineLevel
      if ($ol -ge 1 -and $ol -le 4) {{ $level = $ol }}
    }} catch {{}}
    if ($level -eq 0) {{
      $styleName = ''
      try {{ $styleName = [string]$para.Style.NameLocal }} catch {{
        try {{ $styleName = [string]$para.Range.Style.NameLocal }} catch {{
          try {{ $styleName = [string]$para.Style }} catch {{ $styleName = '' }}
        }}
      }}
      if ($styleName -match '^(Heading|标题)\\s*([1-4])') {{
        $level = [int]$Matches[2]
      }} elseif ($styleName -match '^(Heading|标题)([1-4])$') {{
        $level = [int]$Matches[2]
      }}
    }}
    if ($level -ge 1 -and $level -le 4) {{
      $text = ''
      try {{ $text = $para.Range.Text }} catch {{ $text = '' }}
      $text = ($text -replace '[\\r\\n\\x07]','').Trim()
      if ($text) {{
        $page = 0
        try {{ $page = [int]$para.Range.Information(3) }} catch {{ $page = 0 }}
        if ($page -gt 0) {{
          $lines.Add("$level`t$page`t$text")
        }}
      }}
    }}
  }}
  $utf8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllLines({map_lit}, $lines, $utf8)
  try {{ $doc.Close(0) }} catch {{}}
  $doc = $null
  Write-Output 'OK'
}} catch {{
  Write-Output ('ERR:' + $_.Exception.Message)
  exit 1
}} finally {{
  if ($doc -ne $null) {{ try {{ $doc.Close(0) }} catch {{}} }}
  if ($app -ne $null) {{ try {{ $app.Quit() }} catch {{}} }}
  try {{ [System.Runtime.Interopservices.Marshal]::ReleaseComObject($app) | Out-Null }} catch {{}}
}}
"""


def build_convert_doc_script(
    source_path: Path,
    target_path: Path,
    prog_id: str,
    file_format: int,
) -> str:
    """生成：用 Word/WPS 将 .doc 另存为 docx 或 txt。"""
    src = powershell_literal(source_path)
    dst = powershell_literal(target_path)
    return f"""
$ErrorActionPreference = 'Stop'
$app = $null
$doc = $null
try {{
  $app = New-Object -ComObject {prog_id}
  try {{ $app.Visible = $false }} catch {{}}
  try {{ $app.DisplayAlerts = 0 }} catch {{}}
  $doc = $app.Documents.Open({src}, $false, $true)
  # SaveAs2 / SaveAs — Word 与 WPS 参数细节略有差异，逐级回退
  $saved = $false
  try {{ $doc.SaveAs2({dst}, {file_format}); $saved = $true }} catch {{}}
  if (-not $saved) {{
    try {{ $doc.SaveAs({dst}, {file_format}); $saved = $true }} catch {{}}
  }}
  if (-not $saved) {{
    try {{ $doc.SaveAs([string]{dst}); $saved = $true }} catch {{}}
  }}
  if (-not $saved) {{ throw 'SaveAs/SaveAs2 均失败' }}
  try {{ $doc.Close(0) }} catch {{}}
  $doc = $null
  if (-not (Test-Path -LiteralPath {dst})) {{ throw '另存失败：目标文件不存在' }}
  Write-Output 'OK'
}} catch {{
  Write-Output ('ERR:' + $_.Exception.Message)
  exit 1
}} finally {{
  if ($doc -ne $null) {{ try {{ $doc.Close(0) }} catch {{}} }}
  if ($app -ne $null) {{ try {{ $app.Quit() }} catch {{}} }}
}}
"""


def collect_page_map_via_office(
    docx_path: Path,
    prefer: str = "auto",
) -> tuple[list[dict], int, str] | None:
    """用 Word 或 WPS 更新域并读取标题页码。

    成功返回 (mapping, total_pages, app_label)；全部失败返回 None。
    """
    docx_path = docx_path.expanduser().resolve()
    last_errors: list[str] = []
    for prog_id, app_label in office_app_candidates(prefer):
        with tempfile.TemporaryDirectory() as temp_name:
            map_file = Path(temp_name) / "page-map.tsv"
            script = build_heading_page_map_script(docx_path, map_file, prog_id)
            try:
                completed = run_office_powershell(script, timeout=600)
            except (OSError, subprocess.TimeoutExpired) as exc:
                last_errors.append(f"{app_label}: {exc}")
                continue
            if not map_file.exists():
                detail = (completed.stdout or completed.stderr or "").strip()[:300]
                last_errors.append(f"{app_label}: 无输出 ({detail})")
                continue
            mapping: list[dict] = []
            total_pages = 0
            for line in map_file.read_text(encoding="utf-8").splitlines():
                parts = line.split("\t")
                if parts[0] == "#total" and len(parts) >= 2:
                    try:
                        total_pages = int(parts[1])
                    except ValueError:
                        total_pages = 0
                elif len(parts) >= 3:
                    try:
                        level = int(parts[0])
                        page = int(parts[1])
                    except ValueError:
                        continue
                    mapping.append({
                        "level": level,
                        "page": page,
                        "text": "\t".join(parts[2:]).strip(),
                    })
            if mapping:
                return mapping, total_pages, app_label
            detail = (completed.stdout or completed.stderr or "").strip()[:300]
            last_errors.append(f"{app_label}: 未解析到标题 ({detail})")
    if last_errors:
        print("Office COM 未成功读取页码：")
        for err in last_errors[:6]:
            print(f"  - {err}")
    return None


def convert_with_office(
    source_path: Path,
    target_path: Path,
    file_format: int,
    prefer: str = "auto",
) -> str | None:
    """用 Word/WPS 转换文档。成功返回 app_label，失败返回 None。"""
    source_path = source_path.expanduser().resolve()
    target_path = target_path.expanduser().resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    for prog_id, app_label in office_app_candidates(prefer):
        script = build_convert_doc_script(source_path, target_path, prog_id, file_format)
        try:
            completed = run_office_powershell(script, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if target_path.exists() and target_path.stat().st_size > 0:
            return app_label
        # 部分 WPS 会改扩展名大小写或加后缀，再扫一眼
        if target_path.parent.exists():
            for candidate in target_path.parent.glob(target_path.stem + ".*"):
                if candidate.suffix.lower() == target_path.suffix.lower() and candidate.stat().st_size > 0:
                    if candidate != target_path:
                        candidate.replace(target_path)
                    return app_label
        _ = completed  # silence linter
    return None


def convert_doc_to_txt(source_path: Path, target_txt: Path, prefer: str = "auto") -> str | None:
    """将 .doc/.docx 转为纯文本；成功返回使用的应用名。"""
    return convert_with_office(source_path, target_txt, WD_FORMAT_TEXT, prefer=prefer)


def convert_doc_to_docx(source_path: Path, target_docx: Path, prefer: str = "auto") -> str | None:
    """将 .doc 转为 .docx；成功返回使用的应用名。"""
    return convert_with_office(source_path, target_docx, WD_FORMAT_XML_DOCUMENT, prefer=prefer)


def export_pdf_via_office(docx_path: Path, pdf_path: Path, prefer: str = "auto") -> str | None:
    """用 Word/WPS ExportAsFixedFormat 导出 PDF。成功返回 app_label。"""
    docx_path = docx_path.expanduser().resolve()
    pdf_path = pdf_path.expanduser().resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    docx_lit = powershell_literal(docx_path)
    pdf_lit = powershell_literal(pdf_path)
    for prog_id, app_label in office_app_candidates(prefer):
        script = f"""
$ErrorActionPreference = 'Stop'
$app = $null
$doc = $null
try {{
  $app = New-Object -ComObject {prog_id}
  try {{ $app.Visible = $false }} catch {{}}
  try {{ $app.DisplayAlerts = 0 }} catch {{}}
  $doc = $app.Documents.Open({docx_lit}, $false, $true)
  try {{ $doc.Fields.Update() | Out-Null }} catch {{}}
  try {{
    foreach ($toc in $doc.TablesOfContents) {{ try {{ $toc.Update() }} catch {{}} }}
  }} catch {{}}
  # 17 = wdExportFormatPDF
  $doc.ExportAsFixedFormat({pdf_lit}, 17)
  try {{ $doc.Close(0) }} catch {{}}
  $doc = $null
  if (-not (Test-Path -LiteralPath {pdf_lit})) {{ throw 'PDF 未生成' }}
  Write-Output 'OK'
}} catch {{
  Write-Output ('ERR:' + $_.Exception.Message)
  exit 1
}} finally {{
  if ($doc -ne $null) {{ try {{ $doc.Close(0) }} catch {{}} }}
  if ($app -ne $null) {{ try {{ $app.Quit() }} catch {{}} }}
}}
"""
        try:
            completed = run_office_powershell(script, timeout=600)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return app_label
        _ = completed
    return None


def describe_office_support() -> str:
    """人类可读的 Office 支持说明。"""
    probes = probe_office_apps("auto")
    available = [p for p in probes if p["available"]]
    if not available:
        return (
            "未探测到可用的 Microsoft Word 或 WPS 文字 COM 对象。"
            "请安装 WPS Office 或 Microsoft Office，并在本机至少成功打开过一次文字应用以完成 COM 注册。"
        )
    names = "、".join(f"{p['label']}({p['prog_id']})" for p in available)
    return f"已探测到：{names}"
