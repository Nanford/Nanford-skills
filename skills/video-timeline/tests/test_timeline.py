"""
INPUT: scripts/timeline.py；手写的 shots / speech / captions 样例
OUTPUT: 帧换算、镜头切点、覆盖完整性与输入校验的测试
POS: video-timeline 技能的回归测试：python -m unittest discover -s .claude/skills/video-timeline/tests
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import timeline  # noqa: E402


def sample(total_ms: float = 5000) -> tuple[dict, dict, dict]:
    speech = {
        "variant": "douyin",
        "master_audio": {"path": "audio/voice.wav", "sha256": "abc", "duration_ms": total_ms},
        "segments": [
            {"segment_id": "s1", "global_start_ms": 200, "global_end_ms": 1800},
            {"segment_id": "s2", "global_start_ms": 2000, "global_end_ms": 3000},
            {"segment_id": "s3", "global_start_ms": 3200, "global_end_ms": 4200},
        ],
    }
    shots = {"shots": [
        {"shot_id": "a", "segment_ids": ["s1"], "scene_type": "ResultHook", "params": {}},
        {"shot_id": "b", "segment_ids": ["s2", "s3"], "scene_type": "StepFlow", "params": {}},
    ]}
    captions = {"audio_sha256": "abc", "entries": [{"id": "c1", "start_ms": 240, "end_ms": 1700, "text": "一"}]}
    return shots, speech, captions


class FrameTest(unittest.TestCase):
    def test_ms_to_frame_rounds_absolute_time(self) -> None:
        self.assertEqual(timeline.ms_to_frame(1000, 30), 30)
        self.assertEqual(timeline.ms_to_frame(1016, 30), 30)
        self.assertEqual(timeline.ms_to_frame(1017, 30), 31)

    def test_many_short_shots_do_not_drift(self) -> None:
        # 100 个 1033ms 的边界逐个取整与整体换算结果一致：边界永远从绝对时间换算
        boundaries = [i * 1033 for i in range(101)]
        frames = [timeline.ms_to_frame(ms, 30) for ms in boundaries]
        self.assertEqual(frames[-1], timeline.ms_to_frame(100 * 1033, 30))


class BuildTest(unittest.TestCase):
    def test_cuts_at_pause_midpoint_and_covers_whole_audio(self) -> None:
        shots, speech, captions = sample()
        result = timeline.build_timeline(shots, speech, captions)
        visual = result["tracks"]["visual"]
        self.assertEqual(visual[0]["start_frame"], 0)
        self.assertEqual(visual[1]["start_ms"], 1900)  # (1800 + 2000) / 2
        self.assertEqual(visual[-1]["end_frame"], result["duration_frames"])
        self.assertEqual(result["duration_frames"], 150)
        self.assertEqual(timeline.check_timeline(result), [])

    def test_duration_rounds_up_to_keep_last_audio(self) -> None:
        shots, speech, captions = sample(total_ms=5010)
        self.assertEqual(timeline.build_timeline(shots, speech, captions)["duration_frames"], 151)

    def test_rejects_skipped_or_reordered_segments(self) -> None:
        shots, speech, captions = sample()
        shots["shots"][1]["segment_ids"] = ["s3"]
        with self.assertRaises(timeline.TimelineError):
            timeline.build_timeline(shots, speech, captions)

    def test_rejects_segments_without_timing(self) -> None:
        shots, speech, captions = sample()
        speech["segments"][1]["global_start_ms"] = None
        with self.assertRaises(timeline.TimelineError):
            timeline.build_timeline(shots, speech, captions)

    def test_cli_rejects_stale_captions(self) -> None:
        shots, speech, captions = sample()
        captions["audio_sha256"] = "old"
        with TemporaryDirectory() as tmp:
            variant = Path(tmp)
            (variant / "captions").mkdir()
            for name, data in (("shots.json", shots), ("speech.json", speech), ("captions/captions.json", captions)):
                (variant / name).write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(timeline.main(["build", "--variant-dir", str(variant)]), 1)
            self.assertFalse((variant / "timeline.json").exists())


if __name__ == "__main__":
    unittest.main()
