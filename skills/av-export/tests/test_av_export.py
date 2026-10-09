"""
INPUT: scripts/aelib 与 scripts/av_export.py；ffmpeg 现场合成的测试画面（testsrc2）与正弦音
OUTPUT: 响度解析、MP4 box 顺序、报告合并、画面前置检查、审阅帧选择、交付状态推导，以及 mix → mux → check → record → deliver 端到端测试
POS: av-export 技能的回归测试（不联网、不计费、不读写真实项目）：
     python -m unittest discover -s .claude/skills/av-export/tests
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import av_export  # noqa: E402
from aelib.checks import make_item, manual_placeholders, merge_report, moov_before_mdat, picture_problems, review_frame_numbers  # noqa: E402
from aelib.delivery import build_delivery  # noqa: E402
from aelib.loudness import LoudnessTarget, level_voice, parse_ebur128_summary  # noqa: E402
from aelib.media import MediaError, inside, sha256_file  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

EBUR128_SAMPLE = """
[Parsed_ebur128_0 @ 000001] t: 1.0 TARGET:-23 LUFS    M: -20.0 S:-120.7     I: -21.0 LUFS       LRA:   0.0 LU  FTPK: -3.0 dBFS  TPK: -3.0 dBFS
[Parsed_ebur128_0 @ 000001] Summary:

  Integrated loudness:
    I:         -16.4 LUFS
    Threshold: -26.9 LUFS

  Loudness range:
    LRA:         3.7 LU
    Threshold:  -36.9 LUFS

  True peak:
    Peak:       -2.0 dBFS
"""

TIMELINE = {"width": 108, "height": 192, "fps": 30, "duration_ms": 2000, "duration_frames": 60,
            "tracks": {"visual": [{"shot_id": "s1", "start_frame": 0, "end_frame": 30}, {"shot_id": "s2", "start_frame": 30, "end_frame": 60}], "caption": []}}


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *args], check=True)


class ParseTest(unittest.TestCase):
    def test_summary_is_parsed_not_the_running_log(self) -> None:
        loudness = parse_ebur128_summary(EBUR128_SAMPLE)
        self.assertEqual((loudness.integrated_lufs, loudness.lra_lu, loudness.true_peak_dbtp), (-16.4, 3.7, -2.0))

    def test_missing_summary_raises(self) -> None:
        with self.assertRaises(MediaError):
            parse_ebur128_summary("no summary here")


class BoxOrderTest(unittest.TestCase):
    def write_boxes(self, path: Path, order: list[bytes]) -> None:
        path.write_bytes(b"".join(struct.pack(">I4s", 16, name) + b"\0" * 8 for name in order))

    def test_moov_first_and_last(self) -> None:
        with TemporaryDirectory() as tmp:
            faststart, trailing = Path(tmp) / "a.mp4", Path(tmp) / "b.mp4"
            self.write_boxes(faststart, [b"ftyp", b"moov", b"mdat"])
            self.write_boxes(trailing, [b"ftyp", b"mdat", b"moov"])
            self.assertTrue(moov_before_mdat(faststart))
            self.assertFalse(moov_before_mdat(trailing))


class ReportMergeTest(unittest.TestCase):
    def test_manual_pass_survives_recheck_of_same_file_but_not_a_new_file(self) -> None:
        artifact = Path("variants/douyin/exports/final-v001.mp4")
        report = merge_report({}, manual_placeholders("douyin", artifact, "sha-a"))
        listen = next(item for item in report["items"] if item["check_id"] == "audio.full_listen")
        listen.update({"result": "passed", "checked_by": "用户"})
        # 同一文件重跑 check：人工通过结果保留
        report = merge_report(report, manual_placeholders("douyin", artifact, "sha-a"))
        self.assertEqual(next(i for i in report["items"] if i["check_id"] == "audio.full_listen")["result"], "passed")
        # 文件变了：人工结果被 not_checked 替换
        report = merge_report(report, manual_placeholders("douyin", artifact, "sha-b"))
        replaced = next(i for i in report["items"] if i["check_id"] == "audio.full_listen")
        self.assertEqual((replaced["result"], replaced["artifact_sha256"]), ("not_checked", "sha-b"))

    def test_automated_item_always_replaced(self) -> None:
        artifact = Path("x.mp4")
        first = make_item("spec.video", "douyin", artifact, "sha-a", result="failed", method="m", blocking=True, scope="render")
        second = make_item("spec.video", "douyin", artifact, "sha-a", result="passed", method="m", blocking=True, scope="render")
        report = merge_report(merge_report({}, [first]), [second])
        self.assertEqual([item["result"] for item in report["items"]], ["passed"])


class PictureAndFramesTest(unittest.TestCase):
    def test_picture_problems_flags_full_range_and_audio(self) -> None:
        info = {"streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 108, "height": 192, "pix_fmt": "yuvj420p", "color_range": "pc", "r_frame_rate": "30/1", "nb_frames": "60"},
            {"codec_type": "audio", "codec_name": "aac"},
        ]}
        problems = "\n".join(picture_problems(info, TIMELINE))
        self.assertIn("pix_fmt", problems)
        self.assertIn("color_range", problems)
        self.assertIn("含音轨", problems)

    def test_review_frames_cover_cut_points(self) -> None:
        frames = review_frame_numbers(TIMELINE)
        self.assertEqual([number for number, _ in frames], [0, 15, 29, 30, 45, 59])

    def test_inside_rejects_traversal(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(MediaError):
                inside(Path(tmp), "../escape.txt")


def make_project(root: Path) -> Path:
    """临时项目骨架：brief、账本、一个版本目录与示例文件。"""
    project = root / "projects" / "20260101-test"
    variant = project / "variants" / "douyin"
    (variant / "audio" / "segments").mkdir(parents=True)
    (project / "costs").mkdir(parents=True)
    brief = {"project_id": "20260101-test", "platforms": ["douyin"], "music": {"mode": "none", "waiver_ref": "测试"},
             "publish": {"authorized": False}, "voice": {"provider": "test"}, "budget": {"authorized_max": 0},
             "aigc": {"final_implicit_label": "none", "decision_ref": "测试决定"}}
    (project / "brief.json").write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
    ledger = {"currency": "CNY", "entries": [{"estimated": 0.1, "actual": None, "settlement_status": "estimated"}]}
    (project / "costs" / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    return variant


class DeliveryStatusTest(unittest.TestCase):
    def test_statuses_follow_checks_bound_to_current_file(self) -> None:
        with TemporaryDirectory() as tmp:
            variant = make_project(Path(tmp))
            project = variant.parent.parent
            final = variant / "exports" / "final-v001.mp4"
            final.parent.mkdir()
            final.write_bytes(b"final")
            sha = sha256_file(final)
            artifact = Path("variants/douyin/exports/final-v001.mp4")
            items = [make_item("spec.video", "douyin", artifact, sha, result="passed", method="m", blocking=True, scope="render")]
            report = merge_report({}, items + manual_placeholders("douyin", artifact, sha))
            (project / "qa").mkdir()
            (project / "qa" / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            delivery = build_delivery(project, "v001", [])
            block = delivery["variants"]["douyin"]
            self.assertTrue(block["render_complete"])
            # 人工项仍是 not_checked，且大量交付文件缺失：不能标记 delivery_ready
            self.assertFalse(block["delivery_ready"])
            self.assertIn("variants/douyin/publish.md", block["missing"])
            pending = [item["check_id"] for item in block["pending_checks"]]
            self.assertIn("audio.full_listen", pending)
            # 画面增量是阻断交付的人工项，未登记前一直待查
            self.assertIn("picture.value_add", pending)
            # 成片隐式标识的决定从 brief 原样带出
            self.assertEqual(delivery["aigc"]["final_implicit_label_decision"]["final_implicit_label"], "none")
            # 没有结算额时 actual_total 为 null，不写 0
            self.assertIsNone(delivery["costs"]["actual_total"])
            # 成片一变，旧检查不再适用
            final.write_bytes(b"changed")
            self.assertFalse(build_delivery(project, "v001", [])["variants"]["douyin"]["render_complete"])


@unittest.skipUnless(HAS_FFMPEG, "需要 ffmpeg / ffprobe")
class LevelVoiceTest(unittest.TestCase):
    def test_quiet_peaky_voice_reaches_target_without_changing_length(self) -> None:
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "voice.wav", Path(tmp) / "mix.wav"
            # 安静的正弦音 + 短促的高峰（模拟爆破音），直接加增益会超过真峰值上限
            ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=4", "-af",
                   "volume=-24dB,volume=enable='between(t,1,1.02)':volume=14dB", "-ac", "1", "-c:a", "pcm_s16le", str(src))
            result = level_voice(src, dst, LoudnessTarget())
            self.assertLessEqual(abs(result["after"]["integrated_lufs"] + 16), 1.0)
            self.assertLessEqual(result["after"]["true_peak_dbtp"], -1.5)
            with wave.open(str(src)) as a, wave.open(str(dst)) as b:
                self.assertEqual(a.getnframes(), b.getnframes())
                self.assertEqual((b.getframerate(), b.getnchannels()), (48000, 1))


@unittest.skipUnless(HAS_FFMPEG, "需要 ffmpeg / ffprobe")
class EndToEndTest(unittest.TestCase):
    def build_inputs(self, variant: Path) -> None:
        (variant / "timeline.json").write_text(json.dumps(TIMELINE), encoding="utf-8")
        voice = variant / "audio" / "voice.wav"
        ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=2", "-af", "volume=-20dB", "-ac", "1", "-c:a", "pcm_s16le", str(voice))
        timeline = dict(TIMELINE, voice_audio_sha256=sha256_file(voice))
        (variant / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
        segment = variant / "audio" / "segments" / "s01.mp3"
        ffmpeg("-i", str(voice), "-metadata", 'AIGC={"Label":"1","ContentProducer":"Test","ProduceID":"abc"}', "-id3v2_version", "4", str(segment))
        speech = {"segments": [{"segment_id": "s01", "audio_path": "audio/segments/s01.mp3"}]}
        (variant / "speech.json").write_text(json.dumps(speech), encoding="utf-8")
        picture = variant / "exports" / "picture-v001.mp4"
        picture.parent.mkdir(exist_ok=True)
        ffmpeg("-f", "lavfi", "-i", "testsrc2=size=108x192:rate=30", "-frames:v", "60", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               # 与 remotion-render 的 bt709 输出一致：只设 color_range 时 x264 不写色彩信息，必须连同色彩空间一起标记
               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", str(picture))
        record = {"input": {"timeline_sha256": sha256_file(variant / "timeline.json")}, "output": {"sha256": sha256_file(picture)}}
        (variant / "exports" / "picture-v001.mp4.render.json").write_text(json.dumps(record), encoding="utf-8")

    def test_mix_mux_check_record_deliver(self) -> None:
        with TemporaryDirectory() as tmp:
            variant = make_project(Path(tmp))
            project = variant.parent.parent
            self.build_inputs(variant)
            vd = str(variant)
            self.assertEqual(av_export.main(["mix", "--variant-dir", vd]), 0)
            mix = json.loads((variant / "audio" / "mix.json").read_text(encoding="utf-8"))
            self.assertEqual(mix["source_aigc_labels"][0]["ProduceID"], "abc")
            self.assertEqual(av_export.main(["mux", "--variant-dir", vd, "--picture", "exports/picture-v001.mp4", "--out", "exports/final-v001.mp4", "--voice-only-out", "exports/voice-only-v001.mp4"]), 0)
            self.assertEqual(sha256_file(variant / "exports" / "final-v001.mp4"), sha256_file(variant / "exports" / "voice-only-v001.mp4"))
            self.assertEqual(av_export.main(["check", "--variant-dir", vd, "--video", "exports/final-v001.mp4"]), 0)
            report = json.loads((project / "qa" / "report.json").read_text(encoding="utf-8"))
            results = {item["check_id"]: item["result"] for item in report["items"]}
            for check_id in ("file.full_decode", "spec.video", "spec.audio", "spec.faststart", "timeline.frame_count", "timeline.audio_duration", "audio.loudness"):
                self.assertEqual(results[check_id], "passed", check_id)
            self.assertEqual(results["audio.full_listen"], "not_checked")
            # 自动检查项不能手工改结果
            self.assertEqual(av_export.main(["record", "--variant-dir", vd, "--check-id", "spec.video", "--result", "passed", "--by", "x"]), 1)
            self.assertEqual(av_export.main(["record", "--variant-dir", vd, "--check-id", "audio.full_listen", "--result", "passed", "--by", "测试"]), 0)
            self.assertEqual(results["picture.value_add"], "not_checked")
            self.assertEqual(av_export.main(["record", "--variant-dir", vd, "--check-id", "picture.value_add", "--result", "passed", "--by", "测试"]), 0)
            self.assertEqual(av_export.main(["deliver", "--project-dir", str(project)]), 0)
            delivery = json.loads((project / "delivery.json").read_text(encoding="utf-8"))
            self.assertTrue(delivery["variants"]["douyin"]["render_complete"])
            self.assertFalse(delivery["delivery_ready"])
            self.assertIn("voice_only_note", delivery["variants"]["douyin"])

    @staticmethod
    def build_sfx_inputs(variant: Path, library: Path) -> None:
        """测试用的小音效库（一个 0.1 秒正弦「thud」）与一个落在第 15 帧的动作标记。"""
        library.mkdir()
        ffmpeg("-f", "lavfi", "-i", "sine=frequency=120:sample_rate=48000:duration=0.1", "-ac", "1", "-c:a", "pcm_s16le", str(library / "thud.wav"))
        manifest = {"generator": {"name": "test", "version": "0"}, "kinds": {"land": ["thud"]},
                    "sounds": [{"id": "thud", "file": "thud.wav", "sha256": sha256_file(library / "thud.wav")}]}
        (library / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        actions = {"timeline": {"sha256": sha256_file(variant / "timeline.json")}, "fps": 30,
                   "marks": [{"shot_id": "s1", "frame": 15, "time_ms": 500, "kind": "land", "target": "beat_1"}]}
        (variant / "actions.json").write_text(json.dumps(actions), encoding="utf-8")

    def test_sfx_track_is_mixed_and_mux_tracks_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            variant = make_project(Path(tmp))
            self.build_inputs(variant)
            vd = str(variant)
            # 没有音效轨时 mix 只处理人声，记录为 none
            self.assertEqual(av_export.main(["mix", "--variant-dir", vd]), 0)
            voice_only_mix = sha256_file(variant / "audio" / "mix.wav")
            self.assertEqual(json.loads((variant / "audio" / "mix.json").read_text(encoding="utf-8"))["sfx"], {"mode": "none"})
            self.build_sfx_inputs(variant, Path(tmp) / "library")
            self.assertEqual(av_export.main(["sfx", "--variant-dir", vd, "--library", str(Path(tmp) / "library")]), 0)
            record = json.loads((variant / "audio" / "sfx.json").read_text(encoding="utf-8"))
            # 第 15 帧 → 第 24000 个采样点（15 × 48000 / 30），与人声母轨等长
            self.assertEqual(record["placements"][0]["sample_offset"], 24000)
            with wave.open(str(variant / "audio" / "sfx.wav"), "rb") as handle:
                self.assertEqual(handle.getnframes(), 96000)
            # 混音前封装应被拒绝：音效轨是混音之后新增的
            mux = ["mux", "--variant-dir", vd, "--picture", "exports/picture-v001.mp4", "--out", "exports/final-v001.mp4"]
            self.assertEqual(av_export.main(mux), 1)
            self.assertEqual(av_export.main(["mix", "--variant-dir", vd]), 0)
            mix = json.loads((variant / "audio" / "mix.json").read_text(encoding="utf-8"))
            self.assertEqual(mix["sfx"]["mode"], "track")
            self.assertNotEqual(sha256_file(variant / "audio" / "mix.wav"), voice_only_mix)
            self.assertEqual(av_export.main(mux), 0)
            # 改动音效轨后，mix 拒绝使用不一致的轨道
            with open(variant / "audio" / "sfx.wav", "ab") as handle:
                handle.write(b"\0\0")
            self.assertEqual(av_export.main(["mix", "--variant-dir", vd]), 1)

    def test_sfx_requires_library_and_current_actions(self) -> None:
        with TemporaryDirectory() as tmp:
            variant = make_project(Path(tmp))
            self.build_inputs(variant)
            self.build_sfx_inputs(variant, Path(tmp) / "library")
            self.assertEqual(av_export.main(["sfx", "--variant-dir", str(variant), "--library", str(Path(tmp) / "missing")]), 1)
            actions = json.loads((variant / "actions.json").read_text(encoding="utf-8"))
            actions["timeline"]["sha256"] = "old"
            (variant / "actions.json").write_text(json.dumps(actions), encoding="utf-8")
            self.assertEqual(av_export.main(["sfx", "--variant-dir", str(variant), "--library", str(Path(tmp) / "library")]), 1)

    def test_mux_refuses_picture_from_old_timeline(self) -> None:
        with TemporaryDirectory() as tmp:
            variant = make_project(Path(tmp))
            self.build_inputs(variant)
            self.assertEqual(av_export.main(["mix", "--variant-dir", str(variant)]), 0)
            record_path = variant / "exports" / "picture-v001.mp4.render.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["input"]["timeline_sha256"] = "old"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(av_export.main(["mux", "--variant-dir", str(variant), "--picture", "exports/picture-v001.mp4", "--out", "exports/final-v001.mp4"]), 1)
            self.assertFalse((variant / "exports" / "final-v001.mp4").exists())


if __name__ == "__main__":
    unittest.main()
