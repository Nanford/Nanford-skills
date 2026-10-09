"""
INPUT: 图片路径列表；Windows 自带 OCR（经 ocr_windows.ps1 调用）；项目目录下的 OCR 缓存 assets/ocr-cache.json
OUTPUT: OcrUnavailable、recognize()（返回 {路径: 识别出的文字行}，按图片 SHA-256 缓存）
POS: script-check terms 的截图文字来源。只读图片、不联网、不计费；识别失败时抛 OcrUnavailable，
     由调用方把截图标成未检查（not_checked），不当作没有敏感词。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE = "windows.media.ocr"
LANGUAGE = "zh-Hans-CN"
SCRIPT = Path(__file__).resolve().parent / "ocr_windows.ps1"
TIMEOUT_S = 300


class OcrUnavailable(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_windows_ocr(paths: list[Path]) -> dict[str, list[str]]:
    if sys.platform != "win32":
        raise OcrUnavailable("截图 OCR 目前只支持 Windows 自带引擎，本机不是 Windows")
    # 路径写进 UTF-8 文件再交给 PowerShell，避免中文路径经命令行参数被控制台编码破坏
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
        handle.write("\n".join(str(path) for path in paths))
        list_file = handle.name
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-ListFile", list_file, "-Language", LANGUAGE],
            capture_output=True, timeout=TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OcrUnavailable(f"调用 Windows OCR 失败：{error}") from error
    finally:
        os.unlink(list_file)
    if completed.returncode != 0:
        raise OcrUnavailable(f"Windows OCR 退出码 {completed.returncode}：{completed.stderr.decode('utf-8', 'replace').strip()[:300]}")
    results = json.loads(completed.stdout.decode("utf-8-sig"))
    failed = [item for item in results if item.get("error")]
    if failed:
        raise OcrUnavailable(f"{failed[0]['path']} 识别失败：{failed[0]['error']}")
    return {item["path"]: list(item.get("lines") or []) for item in results}


def recognize(paths: list[Path], cache_path: Path) -> dict[Path, list[str]]:
    """识别每张图的文字行。缓存键是图片 SHA-256 + 引擎 + 语言：图片一换就重识别，同一张图跨版本复用。"""
    cache: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
    hashes = {path: _sha256(path) for path in paths}
    missing = [path for path in paths if (cache.get(hashes[path]) or {}).get("engine") != f"{ENGINE}:{LANGUAGE}"]
    if missing:
        fresh = _run_windows_ocr(missing)
        for path in missing:
            cache[hashes[path]] = {"engine": f"{ENGINE}:{LANGUAGE}", "source_name": path.name, "lines": fresh[str(path)]}
        # 先写临时文件再替换，中断时不留下半截缓存
        temp_path = cache_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, cache_path)
    return {path: cache[hashes[path]]["lines"] for path in paths}
