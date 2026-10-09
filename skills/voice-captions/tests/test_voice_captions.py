"""
INPUT: scripts/vclib 与 scripts/voice_captions.py；ffmpeg 合成的正弦音测试段；手写的 MiniMax 格式字幕样例
OUTPUT: 断句、字符计时、读法替换、SRT、母轨拼接偏移与端到端 assemble 的测试
POS: voice-captions 技能的回归测试（不联网、不计费）：
     python -m unittest discover -s .claude/skills/voice-captions/tests
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import voice_captions  # noqa: E402
from vclib.audio import SAMPLE_RATE, assemble_voice, wav_duration_ms  # noqa: E402
from vclib.captions import WordTiming, break_positions, build_captions, char_times, clean_line, split_lines, text_width  # noqa: E402
from vclib.providers import SubtitleFormatError, parse_minimax_words  # noqa: E402
from vclib.srt import format_timestamp, to_srt, validate_entries  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def per_char_words(text: str, start_ms: float = 0, step_ms: float = 100) -> list[WordTiming]:
    """给每个非标点、非空格字符 100ms 的时间戳，模拟逐字返回。"""
    words, cursor = [], start_ms
    for index, char in enumerate(text):
        if char.strip() and char not in "，。？、":
            words.append(WordTiming(index, index + 1, cursor, cursor + step_ms))
            cursor += step_ms
    return words


def minimax_payload(text: str) -> list[dict]:
    words = [{"word": text[w.char_begin:w.char_end], "word_begin": w.char_begin, "word_end": w.char_end,
              "time_begin": w.start_ms, "time_end": w.end_ms} for w in per_char_words(text)]
    return [{"text": text, "time_begin": 0, "time_end": words[-1]["time_end"], "timestamped_words": words}]


class SplitTest(unittest.TestCase):
    def test_sentence_end_always_breaks_and_short_clauses_join(self) -> None:
        text = "数据接不上，流程对不上。好"
        lines = [clean_line(text[a:b]) for a, b in split_lines(text)]
        # 逗号处已够 6 个字宽即断行；句号必断，句号后的碎字不跨句并回上一行
        self.assertEqual(lines, ["数据接不上", "流程对不上", "好"])
        second = "好的，流程对不上。"
        short = [clean_line(second[a:b]) for a, b in split_lines(second)]
        self.assertEqual(short, ["好的 流程对不上"])

    def test_long_line_is_cut_without_breaking_latin_words(self) -> None:
        text = "我今天查了OpenAI的官方招聘页职位名称带Forward Deployed的一共二十三个"
        lines = [text[a:b] for a, b in split_lines(text, max_width=12)]
        joined = "".join(lines)
        self.assertEqual(joined, text)
        for word in ("OpenAI", "Forward", "Deployed"):
            self.assertTrue(any(word in line for line in lines), word)
        self.assertTrue(all(text_width(line) <= 12 for line in lines))

    def test_caption_breaks_force_semantic_line_ends(self) -> None:
        # 2026-09-30 实际字幕：按宽度硬切会得到「……格式列出 / 来 让你核对」
        text = "出完稿，它还会把实际用的格式列出来，让你核对。"
        plain = [clean_line(text[a:b]) for a, b in split_lines(text)]
        self.assertEqual(plain[1], "来 让你核对")
        forced = [clean_line(text[a:b]) for a, b in split_lines(text, forced=break_positions(text, ["实际用的格式"]))]
        self.assertEqual(forced, ["出完稿 它还会把实际用的格式", "列出来 让你核对"])
        with self.assertRaises(ValueError):
            build_captions(text, per_char_words(text), [], breaks=["改稿前的旧短语"])

    def test_protected_phrase_not_split(self) -> None:
        text = "美国风投机构还专门写文章二零二五年六月发布的说法"
        captions = build_captions(text, per_char_words(text), [("二零二五年六月", "2025 年 6 月")], max_width=14)
        self.assertTrue(any("2025 年 6 月" in line.text for line in captions))
        self.assertFalse(any("二零" in line.text for line in captions))

    def test_clean_line_drops_trailing_marks_but_keeps_question(self) -> None:
        self.assertEqual(clean_line("一进客户现场就卡住。"), "一进客户现场就卡住")
        self.assertEqual(clean_line("FDE 到底干什么？"), "FDE 到底干什么？")
        self.assertEqual(clean_line("现在很火，它叫 FDE，"), "现在很火 它叫 FDE")


class TimingTest(unittest.TestCase):
    def test_multi_char_word_is_spread_evenly(self) -> None:
        times = char_times(5, [WordTiming(1, 4, 100, 400)])
        self.assertIsNone(times[0])
        self.assertEqual(times[1], (100, 200))
        self.assertEqual(times[3], (300, 400))

    def test_captions_follow_real_timestamps(self) -> None:
        text = "做 AI 项目最怕的一种情况，演示的时候效果惊艳。"
        captions = build_captions(text, per_char_words(text, start_ms=40), [])
        self.assertEqual(captions[0].start_ms, 40)
        for earlier, later in zip(captions, captions[1:]):
            self.assertLessEqual(earlier.end_ms, later.start_ms)

    def test_minimax_parser_rejects_mismatched_text(self) -> None:
        payload = minimax_payload("你好世界")
        self.assertEqual(len(parse_minimax_words(payload, "你好世界")), 4)
        with self.assertRaises(SubtitleFormatError):
            parse_minimax_words(payload, "你坏世界")


class SrtTest(unittest.TestCase):
    def test_timestamp_format(self) -> None:
        self.assertEqual(format_timestamp(3_723_456), "01:02:03,456")
        self.assertEqual(format_timestamp(-5), "00:00:00,000")

    def test_srt_and_validation(self) -> None:
        entries = [{"id": "a", "start_ms": 0, "end_ms": 900, "text": "一"}, {"id": "b", "start_ms": 800, "end_ms": 2000, "text": "二"}]
        self.assertIn("00:00:00,000 --> 00:00:00,900\n一", to_srt(entries))
        problems = validate_entries(entries, 1500)
        self.assertTrue(any("重叠" in p for p in problems))
        self.assertTrue(any("超出" in p for p in problems))


def silence_pcm(ms: int) -> bytes:
    return b"\x01\x00" * round(ms * SAMPLE_RATE / 1000)


class AssembleTest(unittest.TestCase):
    def test_offsets_include_lead_and_gaps(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "voice.wav"
            placed = assemble_voice([("a", silence_pcm(1000)), ("b", silence_pcm(500))], out, lead_ms=200, gap_ms=300, tail_ms=800)
            self.assertEqual(round(placed[0].start_ms), 200)
            self.assertEqual(round(placed[1].start_ms), 200 + 1000 + 300)
            self.assertEqual(round(wav_duration_ms(out)), 200 + 1000 + 300 + 500 + 800)


def make_segment(folder: Path, segment_id: str, text: str, seconds: float) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}",
                    "-ar", "32000", "-ac", "1", str(folder / f"{segment_id}.mp3")], check=True)
    (folder / f"{segment_id}.meta.json").write_text(json.dumps({"text": text, "trace_id": f"t-{segment_id}"}, ensure_ascii=False), encoding="utf-8")
    (folder / f"{segment_id}.subtitles.json").write_text(json.dumps(minimax_payload(text), ensure_ascii=False), encoding="utf-8")


@unittest.skipUnless(HAS_FFMPEG, "需要 ffmpeg")
class EndToEndTest(unittest.TestCase):
    def test_assemble_writes_voice_speech_and_captions(self) -> None:
        with TemporaryDirectory() as tmp:
            variant = Path(tmp) / "douyin"
            segments_dir = variant / "audio" / "segments"
            segments_dir.mkdir(parents=True)
            texts = {"s1": "演示的时候效果惊艳，一进客户现场就卡住。", "s2": "二零二五年六月的文章。"}
            make_segment(segments_dir, "s1", texts["s1"], 2.5)
            make_segment(segments_dir, "s2", texts["s2"], 1.5)
            speech = {"variant": "douyin", "segments": [
                {"segment_id": "s1", "spoken_text": texts["s1"]},
                {"segment_id": "s2", "spoken_text": texts["s2"], "display_replacements": [["二零二五年六月", "2025 年 6 月"]]},
            ]}
            (variant / "speech.json").write_text(json.dumps(speech, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(voice_captions.main(["assemble", "--variant-dir", str(variant)]), 0)
            updated = json.loads((variant / "speech.json").read_text(encoding="utf-8"))
            captions = json.loads((variant / "captions" / "captions.json").read_text(encoding="utf-8"))
            self.assertGreater(updated["segments"][1]["global_start_ms"], updated["segments"][0]["global_end_ms"])
            self.assertEqual(captions["entries"][-1]["text"], "2025 年 6 月的文章")
            self.assertTrue((variant / "captions" / "subtitles.srt").exists())

    def test_refuses_audio_made_from_old_text(self) -> None:
        with TemporaryDirectory() as tmp:
            variant = Path(tmp) / "douyin"
            segments_dir = variant / "audio" / "segments"
            segments_dir.mkdir(parents=True)
            make_segment(segments_dir, "s1", "旧的文本。", 1.0)
            speech = {"segments": [{"segment_id": "s1", "spoken_text": "新的文本。"}]}
            (variant / "speech.json").write_text(json.dumps(speech, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(voice_captions.main(["assemble", "--variant-dir", str(variant)]), 1)


if __name__ == "__main__":
    unittest.main()
