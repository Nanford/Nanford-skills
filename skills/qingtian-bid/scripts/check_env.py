"""环境自检：确认本机能运行本 Skill 的脚本；缺什么，给出补救办法和不补的影响。

INPUT: 上一级目录的 requirements.txt；当前 Python 和已安装的包；注册表里的 Word、WPS、Excel（经 office_bridge，
       只查不启动）；PATH 上的 soffice；读图纸文字用的 ezdxf 和 ODA File Converter（经 dwg_text，只找不运行，
       都是可选项）。
OUTPUT: 逐项结果打印到终端。必需项都满足时退出码 0，缺必需项时退出码 1。
POS: 开工前跑一次（references/stage-0-init.md 第零节）。只读，不改文件，不碰项目资料。

本文件要能在低版本 Python 上跑到"版本太低"那一句，所以 importlib.metadata、第三方包和 office_bridge
都在函数里才导入，也不用新语法。
"""

from __future__ import annotations

import argparse
import importlib
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# office_bridge 用了 TemporaryDirectory(ignore_cleanup_errors=True)，3.10 才有。
# 这个下限是从代码推出来的，实测 3.13 和 3.14，3.10～3.12 没有实测。
MIN_PYTHON = (3, 10)
REQUIREMENTS_FILE = Path(__file__).resolve().parents[1] / "requirements.txt"
# 包名和 import 名不同的才记在这里
IMPORT_NAMES = {"python-docx": "docx"}
PACKAGE_IMPACTS = {
    "pypdf": "读不了 PDF 招标文件，也数不了 PDF 页数",
    "python-docx": "出不了样张和成品 DOCX，也读不了 DOCX 资料",
}
# 成品的目录只有 Word、WPS 能更新，这条影响阶段 7，所以写在最前面
NO_WORD_IMPACTS = (
    "成品的目录和页码更新不了，阶段 7 的 B3 过不了：要拿到装了 Word 或 WPS 的电脑上更新后保存",
    "格式样张导不出 PDF：开工时加 --no-pdf，只出 DOCX",
    "自动计页做不了：导出 PDF 后用 report_page_numbers.py --pdf，或数好页数后用 --manual-pages 加 --reason",
    "老式 .doc 提取不了，除非有 LibreOffice，或请用户另存为 .docx",
)
NO_SPREADSHEET_IMPACTS = ("老式 .xls 清单提取不了，除非有 LibreOffice，或请用户另存为 .xlsx",)
# 读图纸文字的两样都是可选的：不在 requirements.txt 里，没有时只提示（招标文件不带 DWG、DXF 就用不到）
EZDXF_MINIMUM = "1.1"  # 实测 1.4.4；recover 容错读取和多行文字转纯文本在 1.x 都有
NO_DRAWING_TEXT_IMPACT = "DWG、DXF 图纸读不了文字：图上的事实要按图号人工看图，或请用户从 CAD 导出可复制文字的 PDF"


@dataclass
class Check:
    """一项检查的结果。required 为 False 的项没通过时只提示，不挡开工。"""

    name: str
    passed: bool
    required: bool
    detail: str
    fix: str = ""
    impacts: list[str] = field(default_factory=list)


def current_python() -> tuple[int, int, int]:
    return tuple(sys.version_info[:3])


def utf8_mode_enabled() -> bool:
    return bool(sys.flags.utf8_mode)


def version_numbers(text: str) -> tuple[int, ...]:
    """只取开头的数字段：1.1.0rc1 取 (1, 1, 0)。不引入 packaging，免得自检本身多一个依赖。"""
    match = re.match(r"\d+(?:\.\d+)*", text.strip())
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()


def is_at_least(found: str, minimum: str) -> bool:
    """按数字比版本，位数不同时补 0：4.0 不低于 4，10.0 高于 9.0。"""
    found_parts, minimum_parts = version_numbers(found), version_numbers(minimum)
    width = max(len(found_parts), len(minimum_parts))
    return (found_parts + (0,) * (width - len(found_parts))
            >= minimum_parts + (0,) * (width - len(minimum_parts)))


def parse_requirements(path: Path) -> list[tuple[str, str]]:
    """读 requirements.txt，得到（包名，最低版本）。依赖只记在那一个文件里，以后加包不用改这里。"""
    requirements: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        match = None if text.startswith("#") else re.match(r"([A-Za-z0-9._-]+)(?:\s*>=\s*([0-9][0-9.]*))?", text)
        if match:
            # 写法不是 >= 的行也要查"装没装"，不能悄悄跳过，否则少查一个包还报通过
            requirements.append((match.group(1), match.group(2) or "0"))
    return requirements


def installed_version(dist_name: str) -> str | None:
    from importlib import metadata  # 3.8 才有；Python 版本检查通过后才走到这里

    try:
        return metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        return None


def import_problem(module_name: str) -> str:
    """真的导入一次。元数据在但导入失败时（如 lxml 的二进制和 Python 版本不配）返回原因，正常返回空串。"""
    try:
        importlib.import_module(module_name)
    except Exception as exc:  # 二进制依赖坏掉时什么异常都可能出现，要报给用户，不能让自检崩掉
        return f"{type(exc).__name__}: {exc}"
    return ""


def pip_command(*options: str) -> str:
    """用当前这个 Python 的 pip 装：本机有几个 Python 时，装到别的 Python 上等于没装。"""
    parts = [f'"{sys.executable}"', "-m", "pip", "install", *options, "-r", f'"{REQUIREMENTS_FILE}"']
    return " ".join(parts)


def check_python(version: tuple[int, int, int]) -> Check:
    text = ".".join(str(part) for part in version)
    wanted = ".".join(str(part) for part in MIN_PYTHON)
    if version[:2] >= MIN_PYTHON:
        return Check("Python", True, True, text)
    return Check("Python", False, True, f"{text}，本 Skill 要 {wanted} 或更新版本",
                 fix=f"安装 Python {wanted} 或更新版本，再用新的 python 运行本脚本",
                 impacts=["脚本跑不起来"])


def check_package(dist_name: str, minimum: str) -> Check:
    wanted = f"要求 >={minimum}"
    impacts = [PACKAGE_IMPACTS.get(dist_name, "用到它的脚本跑不起来")]
    found = installed_version(dist_name)
    if found is None:
        return Check(dist_name, False, True, f"没装（{wanted}）", fix=pip_command(), impacts=impacts)
    if not is_at_least(found, minimum):
        return Check(dist_name, False, True, f"{found} 版本太低（{wanted}）", fix=pip_command(), impacts=impacts)
    problem = import_problem(IMPORT_NAMES.get(dist_name, dist_name))
    if problem:
        return Check(dist_name, False, True, f"{found} 装了但导入失败：{problem}",
                     fix=pip_command("--force-reinstall"), impacts=impacts)
    return Check(dist_name, True, True, f"{found}（{wanted}）")


def find_word_engines() -> list[str]:
    import office_bridge

    return [engine["label"] for engine in office_bridge.office_engines("auto")]


def find_spreadsheet_engines() -> list[str]:
    import office_bridge

    if office_bridge.winreg is None:
        return []
    labels: list[str] = []
    for prog_id, label in office_bridge.SPREADSHEET_PROG_IDS:
        executable = office_bridge.com_server_executable(prog_id)
        if executable:
            # 装了 WPS 并开启兼容时，Excel.Application 启动的也可能是 et.exe，名字按实际程序写
            labels.append("WPS 表格" if Path(executable).name == "et.exe" else label)
    # 同一款软件可能注册了不同路径的程序，用户只需要知道有这款软件
    return list(dict.fromkeys(labels))


def find_libreoffice() -> str | None:
    # extract_text.py 也只认 PATH 上的 soffice，这里查法要和它一样
    return shutil.which("soffice")


def run_probe(probe: Callable[[], list[str]]) -> tuple[list[str], str]:
    """探测失败（注册表没权限、键值损坏）时返回原因，不让自检崩掉。"""
    try:
        return probe(), ""
    except Exception as exc:  # 探测只是为了给提示，任何失败都按"查不到"报
        return [], f"{type(exc).__name__}: {exc}"


def check_office_app(name: str, probe: Callable[[], list[str]], fix: str, impacts: tuple[str, ...]) -> Check:
    labels, problem = run_probe(probe)
    if labels:
        return Check(name, True, False, f"{'、'.join(labels)}（只查了注册表，没有启动程序）")
    detail = f"查不了：{problem}" if problem else "没找到"
    return Check(name, False, False, detail, fix=fix, impacts=list(impacts))


def check_ezdxf() -> Check:
    """读 DWG、DXF 图纸文字用的包；可选，没装只提示。"""
    name = "ezdxf（读图纸文字）"
    fix = f'"{sys.executable}" -m pip install "ezdxf>={EZDXF_MINIMUM}"'
    found = installed_version("ezdxf")
    if found is None:
        return Check(name, False, False, "没装", fix=fix, impacts=[NO_DRAWING_TEXT_IMPACT])
    if not is_at_least(found, EZDXF_MINIMUM):
        return Check(name, False, False, f"{found} 版本太低（要求 >={EZDXF_MINIMUM}）", fix=fix,
                     impacts=[NO_DRAWING_TEXT_IMPACT])
    problem = import_problem("ezdxf")
    if problem:
        return Check(name, False, False, f"{found} 装了但导入失败：{problem}", fix=fix, impacts=[NO_DRAWING_TEXT_IMPACT])
    return Check(name, True, False, found)


def find_oda_converter() -> str | None:
    # extract_text.py 经 dwg_text 找转换程序，这里查法要和它一样
    import dwg_text

    found = dwg_text.find_oda_converter()
    return str(found) if found else None


def check_oda_converter() -> Check:
    """DWG 先要转成 DXF；转换程序的许可不允许随 Skill 分发，由用户自己装。"""
    import dwg_text

    name = "ODA File Converter（读 DWG 图纸）"
    found = find_oda_converter()
    if found:
        return Check(name, True, False, found)
    return Check(name, False, False, "没找到",
                 fix=f"从 ODA 官网（opendesign.com）下载 ODA File Converter 安装，免费；装在别处的，"
                     f"把程序路径设到环境变量 {dwg_text.ODA_ENV}",
                 impacts=["DWG 图纸读不了文字（DXF 不受影响）：图上的事实要按图号人工看图，或请用户导出可复制文字的 PDF"])


def check_libreoffice() -> Check:
    found = find_libreoffice()
    if found:
        return Check("LibreOffice", True, False, found)
    return Check("LibreOffice", False, False, "PATH 上没有 soffice",
                 impacts=["它只是 .doc、.xls 的备用转换办法，有 Word、WPS 或 Excel 时用不到"])


def check_utf8_mode() -> Check:
    if utf8_mode_enabled():
        return Check("UTF-8 模式", True, False, "已开启")
    return Check("UTF-8 模式", False, False, "这次运行没带 -X utf8", fix="运行脚本时写 python -X utf8",
                 impacts=["Windows 下中文可能乱码"])


def collect_checks() -> list[Check]:
    python_check = check_python(current_python())
    if not python_check.passed:
        return [python_check]  # 版本太低时后面的检查本身可能跑不起来
    checks = [python_check]
    try:
        checks.extend(check_package(name, minimum) for name, minimum in parse_requirements(REQUIREMENTS_FILE))
    except OSError as exc:
        checks.append(Check("依赖清单", False, True, f"读不了 {REQUIREMENTS_FILE}：{exc}",
                            fix="重新复制完整的 qingtian-bid 目录"))
    checks.append(check_office_app("Word 或 WPS", find_word_engines,
                                   "安装 Microsoft Word 或 WPS 文字，或把成品拿到装了它们的电脑上处理", NO_WORD_IMPACTS))
    checks.append(check_office_app("Excel 或 WPS 表格", find_spreadsheet_engines,
                                   "安装 Excel 或 WPS 表格，或请用户把 .xls 另存为 .xlsx", NO_SPREADSHEET_IMPACTS))
    checks.append(check_ezdxf())
    checks.append(check_oda_converter())
    checks.append(check_libreoffice())
    checks.append(check_utf8_mode())
    return checks


def report_lines(checks: list[Check]) -> list[str]:
    lines = ["环境自检（qingtian-bid）"]
    for check in checks:
        status = "通过" if check.passed else ("缺失" if check.required else "提示")
        lines.append(f"[{status}] {check.name}：{check.detail}")
        if check.passed:
            continue
        if check.fix:
            lines.append(f"       补救：{check.fix}")
        lines.extend(f"       影响：{impact}" for impact in check.impacts)
    missing = [check for check in checks if check.required and not check.passed]
    if missing:
        lines.append(f"结论：缺 {len(missing)} 项必需的（{'、'.join(check.name for check in missing)}），"
                     "先按上面的补救办法处理，再运行一次本脚本。")
    else:
        lines.append("结论：必需项都满足，可以开工。标为\"提示\"的项不挡开工，影响见上。")
    return lines


def tolerate_console_encoding() -> None:
    """控制台是 GBK 等编码时，写不出的字符用 ? 代替，不让自检因为打印而崩掉。"""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    tolerate_console_encoding()
    parser = argparse.ArgumentParser(description="检查本机能不能运行本 Skill：缺必需项时退出码为 1。只读，不改文件。")
    parser.parse_args(argv)
    checks = collect_checks()
    print("\n".join(report_lines(checks)))
    return 1 if any(check.required and not check.passed for check in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
