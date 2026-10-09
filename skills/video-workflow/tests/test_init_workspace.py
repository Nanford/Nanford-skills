"""
INPUT: scripts/init_workspace.py
OUTPUT: unittest 用例：新工作区有标记文件、projects/、规则文档与模板；再次初始化不覆盖已有文件；标记里记下素材库路径
POS: 工作区初始化的离线测试，只在临时目录里写文件。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import init_workspace  # noqa: E402


class InitWorkspaceTest(unittest.TestCase):
    def test_creates_marker_rules_and_templates(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "ws"
            init_workspace.init_workspace(target, "E:/文章")
            marker = json.loads((target / init_workspace.MARKER).read_text(encoding="utf-8"))
            self.assertEqual(marker["article_library"], "E:/文章")
            for name in ("AGENTS.md", "CLAUDE.md", "docs/DESIGN.md", "docs/DATA_CONTRACTS.md", "templates/production-retro.md", ".env.example"):
                self.assertTrue((target / name).is_file(), name)
            self.assertTrue((target / "projects").is_dir())

    def test_second_run_keeps_existing_files(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "ws"
            init_workspace.init_workspace(target, None)
            (target / "AGENTS.md").write_text("本地改过", encoding="utf-8")
            result = init_workspace.init_workspace(target, "ignored")
            self.assertEqual((target / "AGENTS.md").read_text(encoding="utf-8"), "本地改过")
            self.assertEqual(result["created"], [])
            self.assertIsNone(json.loads((target / init_workspace.MARKER).read_text(encoding="utf-8"))["article_library"])


if __name__ == "__main__":
    unittest.main()
