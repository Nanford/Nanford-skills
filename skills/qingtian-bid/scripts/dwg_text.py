"""Read the text on DWG and DXF drawings, offline (stage 1, drawings the user declared).

- DXF 直接用 ezdxf 读；DWG 先用 ODA File Converter 在临时目录里转成 DXF 再读，用户的文件不动，
  转出来的 DXF 读完就删；全程在本机（R26）。
- 读的是图上的文字：单行文字、多行文字、图框和图块里的属性（图号、图名多在这里）、引线文字，以及标注和
  表格生成的匿名块里的文字。勾选框、填充、线条这类图形信息不是文字，读不出来，仍按图号人工看图。
- 文字按"模型空间 / 布局 / 块"分段，段内去重；标注、表格生成的匿名块一张图上千个，按类合成"标注文字"
  "表格和其他匿名块"两段。块定义只读用到的（从模型空间和布局里的块参照找起），
  图库里没用上的块不读，免得把模板里的占位文字当成本项目的事实；属性定义（ATTDEF）是模板默认值，也不读。
- 工具没装、转换失败、文件读不了，一律抛 DrawingUnreadable 并写明原因；调用方按图纸放行、不硬停（决策 2A）。
- ODA File Converter 的许可不允许随 Skill 分发，由用户自己从 ODA 官网下载安装；ezdxf 是可选的 pip 包。

INPUT: a .dwg or .dxf file; ODA File Converter for .dwg (found through the QINGTIAN_ODA_CONVERTER
       environment variable, then PATH, then its default install folders); the ezdxf package.
OUTPUT: read_drawing_text(path) -> text, one line per text item, grouped by section; find_oda_converter();
        ezdxf_problem(); DrawingUnreadable with a reason the user can act on.
POS: helper of extract_text.py (stage 1) and check_env.py. Imports ezdxf only when a drawing is read.
"""

from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


DRAWING_SUFFIXES = {".dwg", ".dxf"}
# 设了这个环境变量就只认它指的程序；指向不存在的路径等于没装（测试和不想自动转换时用）
ODA_ENV = "QINGTIAN_ODA_CONVERTER"
ODA_PROGRAM = "ODAFileConverter"
CONVERT_TIMEOUT_SECONDS = 300  # 一张图一般几秒；大的总图也就几十秒，超过 5 分钟按转换失败处理
# ODA 的命令行：输入目录 输出目录 输出版本 输出类型 是否递归 是否修复 过滤
ODA_OUTPUT_VERSION = "ACAD2018"
TEXT_TYPES = {"TEXT", "MTEXT", "ATTRIB"}
NO_ODA_REASON = ("DWG 要先转成 DXF 才能读文字，本机没找到 ODA File Converter。它是免费软件，"
                 "从 ODA 官网（opendesign.com）下载安装后重新提取；或请用户从 CAD 导出可复制文字的 PDF，按图纸登记")
NO_EZDXF_REASON = "读 DWG、DXF 图纸的文字要 Python 包 ezdxf，没装：python -m pip install ezdxf，装好后重新提取"


class DrawingUnreadable(Exception):
    """图纸文字读不了；消息写给用户看：缺什么、怎么补。"""


def version_key(folder_name: str) -> tuple[int, ...]:
    """"ODAFileConverter 27.1.0" 取 (27, 1, 0)，装了几个版本时用最新的。"""
    match = re.search(r"\d+(?:\.\d+)*", folder_name)
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()


def default_install_paths() -> list[Path]:
    """ODA 安装程序的默认位置：Windows 装在 Program Files\\ODA\\ODAFileConverter <版本>\\。"""
    if sys.platform == "win32":
        roots = {os.environ.get(name) for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")}
        found = [path for root in roots if root
                 for path in Path(root).glob(f"ODA/{ODA_PROGRAM}*/{ODA_PROGRAM}.exe")]
        return sorted(found, key=lambda path: version_key(path.parent.name), reverse=True)
    if sys.platform == "darwin":
        return [Path(f"/Applications/{ODA_PROGRAM}.app/Contents/MacOS/{ODA_PROGRAM}")]
    return sorted(Path("/opt").glob(f"{ODA_PROGRAM}*/{ODA_PROGRAM}"), reverse=True)


def find_oda_converter() -> Path | None:
    """找 ODA File Converter；找不到返回 None，不报错（只有遇到 DWG 才需要它）。"""
    if ODA_ENV in os.environ:
        configured = Path(os.environ[ODA_ENV]).expanduser()
        return configured if configured.is_file() else None
    on_path = shutil.which(ODA_PROGRAM)
    if on_path:
        return Path(on_path)
    return next((path for path in default_install_paths() if path.is_file()), None)


def load_ezdxf_recover():
    """ezdxf 的容错读取：图纸常有小毛病，标准读法会整张拒绝。没装时给出安装办法。"""
    try:
        return importlib.import_module("ezdxf.recover")
    except ImportError as exc:
        raise DrawingUnreadable(NO_EZDXF_REASON) from exc


def ezdxf_problem() -> str:
    """给环境自检用：ezdxf 能用返回空串，否则返回原因。"""
    try:
        load_ezdxf_recover()
    except DrawingUnreadable as exc:
        return str(exc)
    return ""


def convert_dwg(source: Path, converter: Path, work_dir: Path) -> Path:
    """把 DWG 复制到临时目录再转，用户的文件不动；转不出 DXF 就说明原因。"""
    input_dir, output_dir = work_dir / "in", work_dir / "out"
    input_dir.mkdir()
    output_dir.mkdir()
    shutil.copyfile(source, input_dir / "drawing.dwg")
    command = [str(converter), str(input_dir), str(output_dir), ODA_OUTPUT_VERSION, "DXF", "0", "1", "*.DWG"]
    # Windows 上不弹出控制台窗口
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(command, capture_output=True, timeout=CONVERT_TIMEOUT_SECONDS, creationflags=flags)
    except subprocess.TimeoutExpired as exc:
        raise DrawingUnreadable(f"ODA File Converter 转换超过 {CONVERT_TIMEOUT_SECONDS} 秒，按转换失败处理") from exc
    except OSError as exc:
        raise DrawingUnreadable(f"ODA File Converter 启动不了（{converter}）：{exc}") from exc
    target = output_dir / "drawing.dxf"
    if result.returncode != 0 or not target.is_file():
        # ODA 转换失败时在输出目录写 .err 文件，内容比退出码有用
        errors = " ".join(path.read_text(encoding="utf-8", errors="replace").strip()
                          for path in output_dir.glob("*.err"))
        detail = errors or result.stderr.decode("utf-8", errors="replace").strip() or f"退出码 {result.returncode}"
        raise DrawingUnreadable(f"ODA File Converter 没转出 DXF，文件可能损坏或版本太新：{detail[:300]}")
    return target


def entity_texts(entity) -> list[str]:
    """一个图元上的文字；块参照取它的属性值（图号、图名），引线取它的文字。其余图元没有文字。"""
    kind = entity.dxftype()
    if kind in TEXT_TYPES:
        return [entity.plain_text()]
    if kind == "INSERT":
        return [attrib.plain_text() for attrib in entity.attribs]
    if kind == "MULTILEADER":
        content = entity.get_mtext_content() if hasattr(entity, "get_mtext_content") else ""
        return [entity_plain_mtext(content)] if content else []
    return []


def entity_plain_mtext(content: str) -> str:
    text_tools = importlib.import_module("ezdxf.tools.text")
    return text_tools.plain_mtext(content)


def referenced_blocks(entity) -> list[str]:
    """块参照指向的块，标注指向它生成的匿名块（标注文字在那里面）。"""
    kind = entity.dxftype()
    if kind == "INSERT":
        return [entity.dxf.name]
    if kind == "DIMENSION" and entity.dxf.hasattr("geometry"):
        return [entity.dxf.geometry]
    return []


def section_lines(entities) -> tuple[list[str], list[str]]:
    """一段里的文字（逐行、去重、保持顺序）和它引用的块名。"""
    lines: dict[str, None] = {}
    blocks: list[str] = []
    for entity in entities:
        for text in entity_texts(entity):
            for line in str(text or "").splitlines():
                if line.strip():
                    lines.setdefault(line.strip(), None)
        blocks.extend(referenced_blocks(entity))
    return list(lines), blocks


def is_layout_block(name: str) -> bool:
    return name.lower().startswith(("*model_space", "*paper_space"))


def anonymous_section(name: str) -> str:
    """匿名块（名字以 * 开头）是标注、表格等自动生成的；一张图有上千个，按类合成一段，不逐个分段。"""
    return "标注文字" if name.upper().startswith("*D") else "表格和其他匿名块"


def drawing_sections(doc) -> list[tuple[str, list[str]]]:
    """先读模型空间和各布局，再顺着块参照读用到的块（每个块只读一次）；标注、表格生成的匿名块都读，按类合段。"""
    sections: list[tuple[str, list[str]]] = []
    grouped: dict[str, dict[str, None]] = {}
    pending: list[str] = []
    # doc.layouts 按名字排，模型空间不一定在前；按"模型空间、再按布局标签顺序"读
    layouts = sorted(doc.layouts, key=lambda item: (not item.is_modelspace, item.dxf.get("taborder", 0)))
    for layout in layouts:
        lines, blocks = section_lines(layout)
        title = "模型空间" if layout.is_modelspace else f"布局：{layout.name}"
        sections.append((title, lines))
        pending.extend(blocks)
    pending.extend(block.name for block in doc.blocks if block.name.startswith("*") and not is_layout_block(block.name))
    visited: set[str] = set()
    while pending:
        name = pending.pop(0)
        if name in visited or is_layout_block(name) or name not in doc.blocks:
            continue
        visited.add(name)
        lines, blocks = section_lines(doc.blocks.get(name))
        if name.startswith("*"):
            grouped.setdefault(anonymous_section(name), {}).update(dict.fromkeys(lines))
        else:
            sections.append((f"块：{name}", lines))
        pending.extend(blocks)
    sections.extend((title, list(lines)) for title, lines in grouped.items())
    return [(title, lines) for title, lines in sections if lines]


def read_dxf_text(path: Path) -> str:
    recover = load_ezdxf_recover()
    try:
        doc, _auditor = recover.readfile(str(path))
    except Exception as exc:  # ezdxf 对坏文件抛的异常类型不一，统一转成能看懂的原因
        raise DrawingUnreadable(f"图纸文件读不了：{type(exc).__name__}: {exc}") from exc
    return "\n".join(f"【{title}】\n" + "\n".join(lines) for title, lines in drawing_sections(doc))


def read_drawing_text(path: Path) -> str:
    """读一张 DWG 或 DXF 图纸上的文字。DWG 没有转换程序时直接说明，不去猜。"""
    if path.suffix.lower() == ".dxf":
        return read_dxf_text(path)
    load_ezdxf_recover()  # 先查 ezdxf，免得转完才发现读不了
    converter = find_oda_converter()
    if converter is None:
        raise DrawingUnreadable(NO_ODA_REASON)
    with tempfile.TemporaryDirectory(prefix="qingtian-dwg-", ignore_cleanup_errors=True) as work:
        return read_dxf_text(convert_dwg(path, converter, Path(work)))
