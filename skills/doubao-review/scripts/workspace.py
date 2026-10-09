"""
INPUT: 环境变量 VIDEOCUT_WORKSPACE；当前目录及本文件所在位置的各级上级目录里的标记文件 videocut.workspace.json
OUTPUT: MARKER、ENV_NAME、find_workspace()、require_workspace()
POS: 找 VideoCut 工作区根目录（.env、projects/、logs/ 用量账本、.cache/ 都在这里）的唯一算法。
     技能可能装在工作区里（.claude/skills/<技能>），也可能装在 ~/.codex/skills 这类全局目录；找不到工作区时由调用方报错，
     绝不退回技能目录的上级或用户主目录——否则付费接口的月度用量账本会换位置从 0 记起，预算上限失效。
     本文件在 minimax-tts、doubao-review、jev-check、remotion-render、video-project 各有一份（技能之间不互相导入代码），
     内容必须逐字节相同，video-project 的测试会核对。
"""

from __future__ import annotations

import os
from pathlib import Path

MARKER = "videocut.workspace.json"
ENV_NAME = "VIDEOCUT_WORKSPACE"


def find_workspace(start: Path | None = None) -> Path | None:
    """
    依次查找：环境变量 VIDEOCUT_WORKSPACE（明确指定时直接采用）→ 当前目录及各级上级 → 本文件所在位置的各级上级
    （技能装在工作区的 .claude/skills 里时，从任何目录运行都能找到）。都没有标记文件时返回 None。
    """
    configured = os.environ.get(ENV_NAME, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    for origin in (Path(start or Path.cwd()).resolve(), Path(__file__).resolve().parent):
        for directory in (origin, *origin.parents):
            if (directory / MARKER).is_file():
                return directory
    return None


def require_workspace(root: Path | None, purpose: str, error: type[Exception] = RuntimeError) -> Path:
    """需要写入工作区（用量账本、缓存、项目文件）时调用：找不到或目录不存在就抛出调用方的错误类型，给出一行可操作的提示。"""
    if root is None:
        raise error(f"找不到 VideoCut 工作区，无法确定{purpose}的位置：请在工作区根目录（含 {MARKER}）下运行，或设置环境变量 {ENV_NAME}")
    if not root.is_dir():
        raise error(f"{ENV_NAME} 指向的目录不存在：{root}")
    return root
