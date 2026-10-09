"""
INPUT: 系统 PATH 中的 ffprobe / ffmpeg（subprocess 调用，参数数组传递，不经过 shell）
OUTPUT: probe_media() 读取媒体信息；parse_ffprobe() 把 ffprobe JSON 转成统一字段（纯函数，可单测）；
        tool_version() 读取工具版本；ToolError
POS: 素材导入与质检共用的媒体探测层。只报告文件实际属性，不做转码。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

# 这些封装格式是单张图片；ffprobe 会给它们一个默认 25 fps，不能当作真实帧率
IMAGE_FORMATS = {"image2", "png_pipe", "jpeg_pipe", "webp_pipe", "bmp_pipe", "gif"}
PROBE_TIMEOUT_SEC = 120


class ToolError(RuntimeError):
    pass


def run_tool(args: list[str], timeout_sec: int = PROBE_TIMEOUT_SEC) -> str:
    """执行外部命令并返回 stdout；命令缺失、超时、非零退出都转成带原因的 ToolError。"""
    try:
        completed = subprocess.run(args, capture_output=True, timeout=timeout_sec, check=False)
    except FileNotFoundError as error:
        raise ToolError(f"未找到命令 {args[0]}，请确认已安装并在 PATH 中") from error
    except subprocess.TimeoutExpired as error:
        raise ToolError(f"{args[0]} 超时（{timeout_sec}s）") from error
    stdout = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ToolError(f"{args[0]} 退出码 {completed.returncode}: {stderr[-500:]}")
    return stdout


def tool_version(tool: str) -> str | None:
    """返回版本输出第一行，写入清单用于复现；命令不存在时返回 None。"""
    try:
        return run_tool([tool, "-version"], 30).splitlines()[0].strip()
    except (ToolError, IndexError):
        return None


def parse_rational(value: str | None) -> float | None:
    """"30000/1001" → 29.97；分母为 0 或格式异常时返回 None。"""
    if not value:
        return None
    numerator, _, denominator = value.partition("/")
    try:
        top = float(numerator)
        bottom = float(denominator) if denominator else 1.0
    except ValueError:
        return None
    return None if bottom == 0 else top / bottom


def read_rotation(stream: dict[str, Any]) -> int:
    rotation = next((item["rotation"] for item in stream.get("side_data_list", []) if "rotation" in item), None)
    if rotation is None:
        rotation = float((stream.get("tags") or {}).get("rotate", 0))
    # 统一到 0/90/180/270，便于判断录屏是否需要转向
    return int(round(rotation)) % 360


def is_image_format(format_name: str | None) -> bool:
    return any(name in IMAGE_FORMATS for name in (format_name or "").split(","))


def parse_ffprobe(output: dict[str, Any]) -> dict[str, Any]:
    streams = output.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video" and (s.get("disposition") or {}).get("attached_pic") != 1), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = output.get("format") or {}
    is_image = is_image_format(fmt.get("format_name"))
    average_fps = parse_rational(video.get("avg_frame_rate")) if video and not is_image else None
    nominal_fps = parse_rational(video.get("r_frame_rate")) if video and not is_image else None
    try:
        duration_ms = None if is_image else round(float(fmt["duration"]) * 1000)
    except (KeyError, TypeError, ValueError):
        duration_ms = None
    return {
        "duration_ms": duration_ms,
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "fps": round(average_fps, 3) if average_fps else None,
        # 标称帧率与平均帧率不一致是可变帧率的常见信号；只是启发式判断，转码前需人工确认
        "is_vfr": None if not (average_fps and nominal_fps) else abs(average_fps - nominal_fps) > 0.01,
        "rotation": read_rotation(video) if video else 0,
        "has_audio": audio is not None,
        "has_video": video is not None,
        "video_codec": video.get("codec_name") if video else None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "sample_rate": int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        "channels": audio.get("channels") if audio else None,
    }


def probe_media(path: Path) -> dict[str, Any]:
    stdout = run_tool(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return parse_ffprobe(json.loads(stdout))
