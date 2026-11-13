"""Windows Office automation bridge: Microsoft Word + WPS 文字 (Kingsoft).

INPUT: absolute file paths to DOCX/DOC (and XLS for conversion); optional preferred app (auto|word|wps); the Windows registry
       (which program each ProgID really starts).
OUTPUT: helpers for COM automation used by report_page_numbers / render_format_sample; office_engines()
        and collect_positions_via_office() for gate B2/W5 (第 4b 步); convert_xls_to_xlsx() for stage 1
        extraction of old .xls bills of quantities (Excel / WPS 表格).
POS: Shared Office compatibility layer for the qingtian-bid skill (format-sample PDF export, page counting,
     old-format conversion before extraction).

迁移来源见 CHANGELOG《脚本来源》。原有函数逻辑未改；第 4b 步只在末尾新增
计页用的函数；真实项目核对（2026-10-30）后再在末尾新增 convert_xls_to_xlsx()，见该节。计页用的函数：
  * office_engines()：按注册表查出每个 ProgID 实际启动的程序，同一个程序只留一个。装了 WPS 并开启
    "兼容 Microsoft Office" 时，Word.Application 启动的其实是 wps.exe，COM 里 Name 还报
    "Microsoft Word"（2026-10-29 本机实测），不去重就会把同一个 WPS 当成两个引擎计两遍；
  * collect_positions_via_office()：先把文档复制到临时目录，只读打开副本，更新目录和域后读总页数、
    页面尺寸、每个一级标题和它前一段末尾所在的页与纵向位置、全文末尾的位置；不保存，用户的文件不动、
    也不留 .bak。

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
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    import winreg
except ImportError:  # 非 Windows：没有注册表，office_engines() 按 ProgID 原样返回
    winreg = None


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


# ---------- 第 4b 步：计页（门禁 B2、W5） ----------

def _registry_default(path: str) -> str | None:
    """HKEY_CLASSES_ROOT 下某个键的默认值；没有这个键返回 None。"""
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, path) as key:
            value = winreg.QueryValue(key, None)
    except OSError:
        return None
    return value.strip() or None


def executable_from_command(command: str) -> str:
    """注册表里的启动命令去掉引号和参数，小写：'"D:\\WPS\\wps.exe" /Automation' → 'd:\\wps\\wps.exe'。"""
    text = command.strip()
    if text.startswith('"'):
        text = text[1:].split('"', 1)[0]
    else:
        match = re.match(r"(.+?\.exe)(?=\s|$)", text, re.IGNORECASE)
        text = match.group(1) if match else text.split(" /", 1)[0]
    return text.strip().lower()


def com_server_executable(prog_id: str) -> str | None:
    """ProgID 实际启动的程序；查不到返回 None。ProgID 只有 CurVer 时跟到带版本号的那个。"""
    clsid = _registry_default(rf"{prog_id}\CLSID")
    if clsid is None:
        current = _registry_default(rf"{prog_id}\CurVer")
        clsid = _registry_default(rf"{current}\CLSID") if current else None
    if clsid is None:
        return None
    for key in (rf"CLSID\{clsid}\LocalServer32", rf"WOW6432Node\CLSID\{clsid}\LocalServer32"):
        command = _registry_default(key)
        if command:
            return executable_from_command(command)
    return None


def engine_label(executable: str, fallback: str) -> str:
    """按程序文件名定显示名：COM 的 Name 不可信，WPS 冒充 Word 时也报 "Microsoft Word"。"""
    name = Path(executable).name
    if name == "winword.exe":
        return "Microsoft Word"
    if name == "wps.exe":
        return "WPS 文字"
    return fallback


def office_engines(prefer: str = "auto") -> list[dict]:
    """能计页的引擎，同一个程序只留一个：[{prog_id, label, executable, aliases}]。只查注册表，不启动程序。

    注册表里没有的 ProgID 不列（New-Object 也起不来）；非 Windows 没有 COM，返回空表。
    """
    if winreg is None:
        return []
    engines: list[dict] = []
    for prog_id, label in office_app_candidates(prefer):
        executable = com_server_executable(prog_id)
        if executable is None:
            continue
        same = next((engine for engine in engines if engine["executable"] == executable), None)
        if same is not None:
            same["aliases"].append(prog_id)
            continue
        engines.append({"prog_id": prog_id, "label": engine_label(executable, label), "executable": executable,
                        "aliases": []})
    return engines


def build_item_position_script(docx_path: Path, map_file: Path, prog_id: str) -> str:
    """只读打开 → 更新域和目录 → 重新分页 → 写 TSV：程序、总页数、页面尺寸、全文末尾、每个一级标题。不保存。

    Information(3) 是所在的物理页（wdActiveEndPageNumber），Information(6) 是到页面上边的距离，单位磅
    （wdVerticalPositionRelativeToPage）。每个一级标题另记它前一个字符的位置，即上一项正文结束的地方。
    一级标题按大纲级别认，WPS 部分版本大纲级别不可靠，再按样式名 Heading 1 / 标题 1 认。
    """
    docx_lit = powershell_literal(docx_path)
    map_lit = powershell_literal(map_file)
    return f"""
$ErrorActionPreference = 'Stop'
$app = $null
$doc = $null
try {{
  $app = New-Object -ComObject {prog_id}
  try {{ $app.Visible = $false }} catch {{}}
  try {{ $app.DisplayAlerts = 0 }} catch {{}}
  try {{ $app.ScreenUpdating = $false }} catch {{}}
  $doc = $app.Documents.Open({docx_lit}, $false, $true)
  try {{ $doc.Fields.Update() | Out-Null }} catch {{}}
  try {{
    foreach ($toc in $doc.TablesOfContents) {{ try {{ $toc.Update() | Out-Null }} catch {{}} }}
  }} catch {{}}
  try {{ $doc.Repaginate() }} catch {{}}
  $lines = New-Object System.Collections.Generic.List[string]
  $appName = ''
  try {{ $appName = [string]$app.Name }} catch {{}}
  $appVersion = ''
  try {{ $appVersion = [string]$app.Version }} catch {{}}
  $lines.Add("#app`t$appName`t$appVersion")
  $total = 0
  try {{ $total = $doc.ComputeStatistics(2) }} catch {{
    try {{ $total = $doc.ComputeStatistics(2, $false) }} catch {{ $total = 0 }}
  }}
  $lines.Add("#total`t$total")
  $setup = $doc.PageSetup
  $lines.Add("#page`t" + [string]$setup.PageHeight + "`t" + [string]$setup.TopMargin + "`t" + [string]$setup.BottomMargin)
  $end = $doc.Content.Duplicate
  $end.Collapse(0)
  $lines.Add("#end`t" + [string]$end.Information(3) + "`t" + [string]$end.Information(6))
  foreach ($para in $doc.Paragraphs) {{
    $isHeading = $false
    try {{ if ([int]$para.OutlineLevel -eq 1) {{ $isHeading = $true }} }} catch {{}}
    if (-not $isHeading) {{
      $styleName = ''
      try {{ $styleName = [string]$para.Style.NameLocal }} catch {{
        try {{ $styleName = [string]$para.Range.Style.NameLocal }} catch {{ $styleName = '' }}
      }}
      if ($styleName -match '^(Heading|标题)\\s*1$') {{ $isHeading = $true }}
    }}
    if ($isHeading) {{
      $range = $para.Range
      $text = ($range.Text -replace '[\\r\\n\\x07]', '').Trim()
      if ($text) {{
        $start = $range.Duplicate
        $start.Collapse(1)
        $prevPage = 0
        $prevY = -1
        if ($range.Start -gt 0) {{
          $prev = $doc.Range($range.Start - 1, $range.Start - 1)
          $prevPage = $prev.Information(3)
          $prevY = $prev.Information(6)
        }}
        $lines.Add("h1`t" + [string]$start.Information(3) + "`t" + [string]$start.Information(6) + "`t$prevPage`t$prevY`t$text")
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
}}
"""


def parse_position_map(text: str) -> dict:
    """解析 build_item_position_script 写的 TSV；读不出的行跳过，缺项留空由调用方判断。"""
    result: dict = {"app": {}, "total_pages": 0, "page": None, "end": None, "headings": []}
    for line in text.splitlines():
        parts = line.split("\t")
        try:
            if parts[0] == "#app" and len(parts) >= 3:
                result["app"] = {"name": parts[1], "version": parts[2]}
            elif parts[0] == "#total" and len(parts) >= 2:
                result["total_pages"] = int(float(parts[1]))
            elif parts[0] == "#page" and len(parts) >= 4:
                result["page"] = {"height": float(parts[1]), "top": float(parts[2]), "bottom": float(parts[3])}
            elif parts[0] == "#end" and len(parts) >= 3:
                result["end"] = {"page": int(float(parts[1])), "y": float(parts[2])}
            elif parts[0] == "h1" and len(parts) >= 6:
                result["headings"].append({"page": int(float(parts[1])), "y": float(parts[2]),
                                           "prev_page": int(float(parts[3])), "prev_y": float(parts[4]),
                                           "text": "\t".join(parts[5:]).strip()})
        except ValueError:
            continue
    return result


def collect_positions_via_office(docx_path: Path, engine: dict, timeout: int = 600) -> dict:
    """在临时副本上读总页数和一级标题位置：{ok, error, app, total_pages, page, end, headings}。

    用户的文件只被复制，不被打开、更新或保存（第 4b 步约定：计页不改成品，也不留 .bak）。
    """
    docx_path = docx_path.expanduser().resolve()
    # WPS 退出时偶尔崩（RPC 0x800706BE），副本可能还被占着；临时目录清不掉不影响结果
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_name:
        copy = Path(temp_name) / f"count{docx_path.suffix.lower()}"
        shutil.copy2(docx_path, copy)
        map_file = Path(temp_name) / "positions.tsv"
        try:
            completed = run_office_powershell(build_item_position_script(copy, map_file, engine["prog_id"]),
                                              timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": str(exc)[:300]}
        if not map_file.exists():
            return {"ok": False, "error": (completed.stdout or completed.stderr or "无输出").strip()[:300]}
        result = parse_position_map(map_file.read_text(encoding="utf-8"))
    if result["total_pages"] <= 0:
        return {**result, "ok": False, "error": "没有读到总页数"}
    return {**result, "ok": True, "error": ""}


def export_pdf_copy_via_office(docx_path: Path, pdf_path: Path, engine: dict) -> bool:
    """在临时副本上导出 PDF（B2 的第二条路）：export_pdf_via_office 直接打开传入的文件，这里先复制。"""
    docx_path = docx_path.expanduser().resolve()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_name:
        copy = Path(temp_name) / f"count{docx_path.suffix.lower()}"
        shutil.copy2(docx_path, copy)
        prefer = "word" if engine["prog_id"].lower().startswith("word.") else "wps"
        return export_pdf_via_office(copy, pdf_path, prefer=prefer) is not None


# ---------- 解标：老式 .xls 工程量清单另存为 .xlsx ----------

# 表格程序的 ProgID，auto 时依次试：Excel.Application 在装了 WPS 并开启兼容时启动的也可能是 et.exe
SPREADSHEET_PROG_IDS: list[tuple[str, str]] = [
    ("Excel.Application", "Microsoft Excel"),
    ("KET.Application", "WPS 表格"),
    ("ET.Application", "WPS 表格（旧版）"),
]

# Workbook.SaveAs FileFormat: 51 = xlOpenXMLWorkbook (.xlsx)
XL_OPEN_XML_WORKBOOK = 51


def build_convert_xls_script(source_path: Path, target_path: Path, prog_id: str) -> str:
    """生成：用 Excel / WPS 表格只读打开 .xls，另存为 .xlsx。

    合肥的工程量清单、最高投标限价普遍是老式 .xls（2026-10-30 两个真实项目都是）。来源文件不可信：
    打开前禁用宏（AutomationSecurity = 3，msoAutomationSecurityForceDisable，WPS 不认就跳过），
    不更新外部链接（UpdateLinks = 0）。
    """
    src = powershell_literal(source_path)
    dst = powershell_literal(target_path)
    return f"""
$ErrorActionPreference = 'Stop'
$app = $null
$book = $null
try {{
  $app = New-Object -ComObject {prog_id}
  try {{ $app.Visible = $false }} catch {{}}
  try {{ $app.DisplayAlerts = $false }} catch {{}}
  try {{ $app.AutomationSecurity = 3 }} catch {{}}
  $book = $app.Workbooks.Open({src}, 0, $true)
  $book.SaveAs({dst}, {XL_OPEN_XML_WORKBOOK})
  try {{ $book.Close($false) }} catch {{}}
  $book = $null
  if (-not (Test-Path -LiteralPath {dst})) {{ throw '另存失败：目标文件不存在' }}
  Write-Output 'OK'
}} catch {{
  Write-Output ('ERR:' + $_.Exception.Message)
  exit 1
}} finally {{
  if ($book -ne $null) {{ try {{ $book.Close($false) }} catch {{}} }}
  if ($app -ne $null) {{ try {{ $app.Quit() }} catch {{}} }}
}}
"""


def convert_xls_to_xlsx(source_path: Path, target_xlsx: Path, timeout: int = 300) -> str | None:
    """在临时副本上把 .xls 另存为 .xlsx；成功返回所用程序名，都不成功返回 None。

    用户的文件只被复制，不被表格程序打开（与计页同一约定）；副本用短文件名，避开长项目名撞上
    Windows 260 字符的路径上限。
    """
    source_path = source_path.expanduser().resolve()
    target_xlsx = target_xlsx.expanduser().resolve()
    target_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_name:
        copy = Path(temp_name) / "source.xls"
        shutil.copy2(source_path, copy)
        converted = Path(temp_name) / "source.xlsx"
        for prog_id, app_label in SPREADSHEET_PROG_IDS:
            try:
                run_office_powershell(build_convert_xls_script(copy, converted, prog_id), timeout=timeout)
            except (OSError, subprocess.TimeoutExpired):
                continue
            if converted.exists() and converted.stat().st_size > 0:
                shutil.copy2(converted, target_xlsx)
                return app_label
    return None
