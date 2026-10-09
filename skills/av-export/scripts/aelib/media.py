"""
INPUT: ffmpeg / ffprobe 命令行；本地文件
OUTPUT: MediaError、run_tool()、ffprobe_json()、sha256_file()、tool_version()、temp_sibling()、replace_atomic()、
        local_now()、read_json()、write_json_atomic()、inside()
POS: av-export 所有命令共用的底层工具。外部进程统一经 run_tool 调用，缺工具、超时和非零退出都转成 MediaError，由命令入口给出可读错误。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


class MediaError(RuntimeError):
    pass


def run_tool(args: list[str], timeout: int = 1800, check: bool = True) -> subprocess.CompletedProcess[str]:
    """运行 ffmpeg/ffprobe。输出按 UTF-8 解码（中文路径与元数据在 Windows 控制台代码页下也不乱码）。"""
    try:
        completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except FileNotFoundError as error:
        raise MediaError(f"未找到 {args[0]}，请确认已安装并在 PATH 中") from error
    except subprocess.TimeoutExpired as error:
        raise MediaError(f"{args[0]} 超过 {timeout} 秒未结束") from error
    if check and completed.returncode != 0:
        raise MediaError(f"{args[0]} 退出码 {completed.returncode}：{completed.stderr.strip()[-600:]}")
    return completed


def ffprobe_json(path: Path) -> dict[str, Any]:
    completed = run_tool(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], timeout=120)
    return json.loads(completed.stdout)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tool_version(name: str) -> str:
    """返回 `ffmpeg -version` 的第一行，写入产物记录，便于复现。"""
    return run_tool([name, "-version"], timeout=30).stdout.splitlines()[0].strip()


def temp_sibling(path: Path) -> Path:
    # 保留原扩展名，ffmpeg 才能按扩展名选择封装格式
    return path.with_name(f"{path.stem}.tmp{path.suffix}")


def replace_atomic(temporary: Path, final: Path) -> None:
    """检查通过后再替换正式文件；中途失败时上一版正式文件保持不变。"""
    temporary.replace(final)


def local_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise MediaError(f"缺少文件：{path}") from error
    except json.JSONDecodeError as error:
        raise MediaError(f"{path} 不是有效 JSON：{error}") from error


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def inside(root: Path, relative: str) -> Path:
    """把合同里的相对路径解析到 root 下，并拒绝 ../ 越界（数据合同第 2 节）。"""
    resolved = (root / relative).resolve()
    if resolved != root.resolve() and root.resolve() not in resolved.parents:
        raise MediaError(f"路径越界：{relative} 不在 {root} 内")
    return resolved


def relative_to(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
