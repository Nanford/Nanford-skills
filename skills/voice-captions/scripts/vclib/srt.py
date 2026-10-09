"""
INPUT: 带全局毫秒时间的字幕条目
OUTPUT: format_timestamp() 与 to_srt() 生成标准 SRT 文本；validate_entries() 检查时间合法性
POS: 字幕文件输出层。SRT 供平台上传或剪映导入，captions.json 供 Remotion 渲染，两者来自同一份条目。
"""

from __future__ import annotations

from typing import Any


def format_timestamp(ms: float) -> str:
    total = max(0, round(ms))
    hours, rest = divmod(total, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def to_srt(entries: list[dict[str, Any]]) -> str:
    blocks = []
    for number, entry in enumerate(entries, 1):
        blocks.append(f"{number}\n{format_timestamp(entry['start_ms'])} --> {format_timestamp(entry['end_ms'])}\n{entry['text']}\n")
    return "\n".join(blocks)


def validate_entries(entries: list[dict[str, Any]], audio_ms: float) -> list[str]:
    """返回问题清单：时间非法、倒序、重叠或超出音频范围。空清单表示通过。"""
    problems = []
    previous_end = 0.0
    for entry in entries:
        if not 0 <= entry["start_ms"] < entry["end_ms"]:
            problems.append(f"{entry['id']} 起止时间非法")
        if entry["start_ms"] < previous_end:
            problems.append(f"{entry['id']} 与上一条重叠或倒序")
        if entry["end_ms"] > audio_ms:
            problems.append(f"{entry['id']} 超出音频范围")
        previous_end = entry["end_ms"]
    return problems
