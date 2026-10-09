"""
INPUT: Python 标准库（json、hashlib、pathlib、os）
OUTPUT: read_json / write_json_atomic / sha256_file / describe_file / now_iso
POS: 所有清单文件的读写入口。统一「先写临时文件再改名」，中途失败不会留下半截 JSON。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

HASH_CHUNK_BYTES = 1024 * 1024


class DataFileError(RuntimeError):
    pass


def now_iso() -> str:
    """带本地时区的 ISO 8601 时间，符合数据合同对时间点的要求。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DataFileError(f"无法读取 {path}: {error.strerror}") from error
    except ValueError as error:
        raise DataFileError(f"JSON 格式错误 {path}: {error}") from error


def write_json_atomic(path: Path, data: Any) -> None:
    """同目录临时文件 + os.replace：Windows 与 POSIX 上都是原子替换，避免清单被写坏。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    """分块读取，避免把几百 MB 的录屏整个读进内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_file(absolute_path: Path, relative_path: str, purpose: str) -> dict[str, Any]:
    return {
        "path": relative_path,
        "sha256": sha256_file(absolute_path),
        "bytes": absolute_path.stat().st_size,
        "purpose": purpose,
    }
