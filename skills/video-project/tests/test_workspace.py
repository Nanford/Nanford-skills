"""
INPUT: scripts/vplib/workspace.py 及其在 minimax-tts、doubao-review、jev-check、remotion-render 的副本
OUTPUT: unittest 用例：环境变量优先、按标记文件向上查找、找不到时报错而不是退回主目录、五份副本逐字节一致
POS: 工作区定位的离线测试。技能装到工作区外（~/.codex/skills 等）时，付费接口的用量账本仍须落在工作区里，否则月度上限失效。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

SKILLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS / "video-project" / "scripts"))

from vplib import workspace  # noqa: E402

COPIES = [
    SKILLS / "minimax-tts" / "scripts" / "workspace.py",
    SKILLS / "doubao-review" / "scripts" / "workspace.py",
    SKILLS / "jev-check" / "scripts" / "workspace.py",
    SKILLS / "remotion-render" / "scripts" / "workspace.py",
]


class WorkspaceTest(unittest.TestCase):
    def test_copies_are_identical(self) -> None:
        source = (SKILLS / "video-project" / "scripts" / "vplib" / "workspace.py").read_bytes()
        for copy in COPIES:
            self.assertEqual(copy.read_bytes(), source, f"{copy} 与 video-project 的 workspace.py 不一致")

    def test_env_var_wins(self) -> None:
        with TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {workspace.ENV_NAME: tmp}):
            self.assertEqual(workspace.find_workspace(), Path(tmp).resolve())

    def test_marker_found_from_nested_directory(self) -> None:
        with TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True):
            root = Path(tmp)
            (root / workspace.MARKER).write_text("{}", encoding="utf-8")
            nested = root / "projects" / "a" / "variants"
            nested.mkdir(parents=True)
            self.assertEqual(workspace.find_workspace(nested), root.resolve())

    def test_missing_workspace_raises_instead_of_falling_back(self) -> None:
        with self.assertRaises(ValueError) as caught:
            workspace.require_workspace(None, "用量账本", ValueError)
        self.assertIn(workspace.MARKER, str(caught.exception))
        with TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            workspace.require_workspace(Path(tmp) / "missing", "用量账本", ValueError)


if __name__ == "__main__":
    unittest.main()
