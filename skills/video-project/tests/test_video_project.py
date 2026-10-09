"""
INPUT: scripts/vplib 各模块与 scripts/vp.py；ffmpeg 生成的合成测试素材（testsrc 画面 + 正弦音），不使用任何私人文件
OUTPUT: 媒体解析、路径安全、项目建档、阶段失效传播、素材入库、费用账本与命令入口的测试
POS: video-project 技能的回归测试。改动 scripts/ 下任一文件后运行：
     python -m unittest discover -s .claude/skills/video-project/tests
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import vp  # noqa: E402
from vplib.assets import AssetRequest, import_asset  # noqa: E402
from vplib.costs import CostEntry, add_cost_entry, summarize_costs  # noqa: E402
from vplib.manifest import create_manifest, update_stage  # noqa: E402
from vplib.media import parse_ffprobe, parse_rational  # noqa: E402
from vplib.paths import PathSafetyError, resolve_inside, to_project_relative  # noqa: E402
from vplib.project import ProjectRequest, init_project  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def make_test_video(path: Path) -> None:
    """1 秒 320x240 30fps 测试画面 + 440Hz 正弦音，完全由 ffmpeg 合成。"""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )


class MediaParseTest(unittest.TestCase):
    def test_parse_rational(self) -> None:
        self.assertAlmostEqual(parse_rational("30000/1001"), 29.97, places=2)
        self.assertEqual(parse_rational("30"), 30.0)
        self.assertIsNone(parse_rational("30/0"))
        self.assertIsNone(parse_rational("abc"))

    def test_video_with_vfr_and_rotation(self) -> None:
        info = parse_ffprobe({
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "60/1",
                 "avg_frame_rate": "30/1", "side_data_list": [{"rotation": -90}]},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
            ],
            "format": {"duration": "12.3456", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
        })
        self.assertEqual(info["duration_ms"], 12346)
        self.assertEqual(info["fps"], 30.0)
        self.assertTrue(info["is_vfr"])
        self.assertEqual(info["rotation"], 270)
        self.assertEqual((info["sample_rate"], info["channels"]), (48000, 2))

    def test_image_has_no_fps_or_duration(self) -> None:
        info = parse_ffprobe({
            "streams": [{"codec_type": "video", "codec_name": "png", "width": 800, "height": 600, "r_frame_rate": "25/1", "avg_frame_rate": "25/1"}],
            "format": {"format_name": "png_pipe", "duration": "0.04"},
        })
        self.assertIsNone(info["fps"])
        self.assertIsNone(info["duration_ms"])
        self.assertEqual((info["width"], info["height"]), (800, 600))

    def test_mp3_cover_art_is_not_video(self) -> None:
        info = parse_ffprobe({
            "streams": [
                {"codec_type": "audio", "codec_name": "mp3", "sample_rate": "32000", "channels": 1},
                {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
            ],
            "format": {"duration": "2.0", "format_name": "mp3"},
        })
        self.assertFalse(info["has_video"])
        self.assertEqual(info["duration_ms"], 2000)


class PathSafetyTest(unittest.TestCase):
    def test_rejects_traversal_and_absolute(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(PathSafetyError):
                resolve_inside(root, "../outside.txt")
            with self.assertRaises(PathSafetyError):
                resolve_inside(root, str(root / "x.txt"))
            self.assertEqual(resolve_inside(root, "a/b.txt"), (root / "a" / "b.txt").resolve())

    def test_relative_paths_use_forward_slashes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(to_project_relative(root, root / "variants" / "douyin" / "a.mp3"), "variants/douyin/a.mp3")


class ProjectTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"VC_PROJECTS_ROOT": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def new_project(self, **kwargs: object) -> Path:
        return init_project(ProjectRequest(slug="bid-skill", date="20260929", **kwargs))  # type: ignore[arg-type]


class InitTest(ProjectTestCase):
    def test_creates_skeleton_with_safe_defaults(self) -> None:
        root = self.new_project(audience_segment="ai_office")
        for relative in ("assets/original", "variants/douyin/audio", "variants/douyin/exports", "costs/ledger.json", "project.json"):
            self.assertTrue((root / relative).exists(), relative)
        # 默认只做抖音一版：不建视频号目录，brief 与清单里也只有抖音
        self.assertFalse((root / "variants" / "channels").exists())
        brief = json.loads((root / "brief.json").read_text(encoding="utf-8"))
        self.assertEqual(brief["platforms"], ["douyin"])
        self.assertEqual(list(brief["target_duration_seconds"]), ["douyin"])
        manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(list(manifest["variants"]), ["douyin"])
        self.assertFalse(brief["budget"]["allow_new_paid_calls"])
        self.assertFalse(brief["publish"]["authorized"])
        self.assertEqual(brief["target_duration_seconds"]["douyin"], {"min": 60, "max": 120})
        self.assertEqual(brief["voice"]["voice_id"], "Chinese (Mandarin)_Gentleman")
        self.assertEqual(brief["aigc"]["explicit_overlay"], "none")
        # 底图题材留给写脚本时按选题填，默认空
        self.assertIsNone(brief["visual"]["backdrop_theme"])

    def test_both_platforms_only_when_requested(self) -> None:
        root = self.new_project(platforms=["douyin", "channels"])
        for relative in ("variants/douyin/exports", "variants/channels/exports"):
            self.assertTrue((root / relative).exists(), relative)
        brief = json.loads((root / "brief.json").read_text(encoding="utf-8"))
        self.assertEqual(brief["target_duration_seconds"]["channels"], {"min": 60, "max": 180})

    def test_article_source_recorded_with_hash_and_must_exist(self) -> None:
        article = Path(self._tmp.name) / "公众号 文章.md"
        article.write_text("# 标题\n正文", encoding="utf-8")
        root = self.new_project(input_type="article", source_article=str(article))
        brief = json.loads((root / "brief.json").read_text(encoding="utf-8"))
        self.assertEqual(brief["inputs"][0]["path_or_url"], str(article.resolve()))
        self.assertEqual(len(brief["inputs"][0]["sha256"]), 64)
        with self.assertRaises(FileNotFoundError):
            init_project(ProjectRequest(slug="missing-article", date="20260929", source_article=str(article) + ".nope"))
        self.assertFalse((Path(self._tmp.name) / "20260929-missing-article").exists())

    def test_refuses_to_overwrite_existing_project(self) -> None:
        self.new_project()
        with self.assertRaises(FileExistsError):
            self.new_project()

    def test_rejects_bad_slug_and_platform(self) -> None:
        with self.assertRaises(ValueError):
            init_project(ProjectRequest(slug="Bad Slug", date="20260929"))
        with self.assertRaises(ValueError):
            init_project(ProjectRequest(slug="ok", date="20260929", platforms=["youtube"]))


def file_entry(path: str, digest: str) -> dict:
    return {"path": path, "sha256": digest, "bytes": 1, "purpose": "test"}


class StageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = create_manifest("20260929-bid-skill", ["douyin", "channels"])
        for stage in ("script", "speech", "captions", "visuals"):
            update_stage(self.manifest, stage, "douyin", "passed", {"output_files": [file_entry(stage, "v1")]})

    def status(self, platform: str, stage: str) -> str:
        return self.manifest["variants"][platform][stage]["status"]

    def test_running_increments_attempt(self) -> None:
        update_stage(self.manifest, "mix", "douyin", "running", {})
        update_stage(self.manifest, "mix", "douyin", "running", {})
        self.assertEqual(self.manifest["variants"]["douyin"]["mix"]["attempt"], 2)

    def test_changed_output_marks_downstream_stale(self) -> None:
        stale = update_stage(self.manifest, "speech", "douyin", "passed", {"output_files": [file_entry("speech", "v2")]})
        self.assertEqual(stale, {"douyin": ["captions", "visuals"]})
        self.assertEqual(self.status("douyin", "script"), "passed")
        self.assertEqual(self.status("douyin", "edit"), "pending")

    def test_same_output_does_not_invalidate(self) -> None:
        stale = update_stage(self.manifest, "speech", "douyin", "passed", {"output_files": [file_entry("speech", "v1")]})
        self.assertEqual(stale, {})
        self.assertEqual(self.status("douyin", "captions"), "passed")

    def test_research_change_invalidates_scripts_everywhere(self) -> None:
        update_stage(self.manifest, "research", None, "passed", {"output_files": [file_entry("claims", "v2")]})
        self.assertEqual(self.status("douyin", "script"), "stale")
        self.assertEqual(self.status("douyin", "visuals"), "stale")

    def test_asset_index_change_keeps_script_and_speech(self) -> None:
        update_stage(self.manifest, "asset_index", None, "passed", {"output_files": [file_entry("index", "v2")]})
        self.assertEqual(self.status("douyin", "speech"), "passed")
        self.assertEqual(self.status("douyin", "visuals"), "stale")

    def test_variant_rules(self) -> None:
        with self.assertRaises(ValueError):
            update_stage(self.manifest, "speech", None, "passed", {})
        with self.assertRaises(ValueError):
            update_stage(self.manifest, "research", "douyin", "passed", {})
        with self.assertRaises(ValueError):
            update_stage(self.manifest, "speech", "douyin", "done", {})


@unittest.skipUnless(HAS_FFMPEG, "需要 ffmpeg / ffprobe")
class ImportTest(ProjectTestCase):
    def test_import_copies_read_only_and_probes(self) -> None:
        root = self.new_project()
        source = Path(self._tmp.name) / "测试 录屏.mp4"
        make_test_video(source)
        record = import_asset(root, AssetRequest(source=source, kind="footage", rights="confirmed", origin_source="ffmpeg testsrc"))
        self.assertEqual(record["asset_id"], "asset_footage_001")
        self.assertEqual(record["stored_path"], "assets/original/asset_footage_001.mp4")
        self.assertEqual((record["width"], record["height"], record["fps"]), (320, 240, 30.0))
        self.assertTrue(record["has_audio"])
        self.assertAlmostEqual(record["duration_ms"], 1000, delta=100)
        stored = root / record["stored_path"]
        self.assertFalse(stored.stat().st_mode & stat.S_IWRITE)
        again = import_asset(root, AssetRequest(source=source, kind="footage"))
        self.assertEqual(again["asset_id"], "asset_footage_001")
        table = json.loads((root / "assets" / "assets.json").read_text(encoding="utf-8"))
        self.assertEqual(len(table["assets"]), 1)
        stored.chmod(stat.S_IWRITE | stat.S_IREAD)  # 让临时目录可以清理

    def test_cli_stage_registers_real_outputs_only(self) -> None:
        root = self.new_project()
        (root / "variants" / "douyin" / "script.md").write_text("脚本", encoding="utf-8")
        ok = vp.main(["stage", "20260929-bid-skill", "script", "--variant", "douyin", "--status", "passed", "--output", "variants/douyin/script.md:脚本"])
        self.assertEqual(ok, 0)
        missing = vp.main(["stage", "20260929-bid-skill", "speech", "--variant", "douyin", "--status", "passed", "--output", "variants/douyin/none.mp3:配音"])
        self.assertEqual(missing, 1)
        escape = vp.main(["stage", "20260929-bid-skill", "speech", "--variant", "douyin", "--status", "passed", "--output", "../x:配音"])
        self.assertEqual(escape, 1)
        manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["variants"]["douyin"]["script"]["output_files"][0]["path"], "variants/douyin/script.md")
        self.assertEqual(manifest["variants"]["douyin"]["speech"]["status"], "pending")


class CostTest(ProjectTestCase):
    def test_unknown_amounts_are_not_counted_as_zero(self) -> None:
        root = self.new_project()
        add_cost_entry(root, CostEntry(service="minimax", unit="chars", quantity=30, request_id="trace-1"))
        add_cost_entry(root, CostEntry(service="minimax", unit="chars", quantity=10, request_id="trace-2", actual=0.05, settlement_status="settled"))
        summary = summarize_costs(root)
        self.assertEqual(summary["settled"], 0.05)
        self.assertEqual(summary["unknown_entries"], 1)

    def test_same_request_recorded_once(self) -> None:
        root = self.new_project()
        add_cost_entry(root, CostEntry(service="minimax", unit="chars", quantity=30, request_id="trace-1"))
        with self.assertRaises(ValueError):
            add_cost_entry(root, CostEntry(service="minimax", unit="chars", quantity=30, request_id="trace-1"))


if __name__ == "__main__":
    unittest.main()
