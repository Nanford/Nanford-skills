"""
INPUT: sfxlib（dsp、presets、library）；临时目录
OUTPUT: unittest 用例：可复现、格式、电平、首尾无咔哒、滤波频率、清单校验与试听文件
POS: sfx-kit 的离线测试，不联网、不写技能目录下的真实音效库。
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sfxlib import dsp  # noqa: E402
from sfxlib.library import GENERATOR_VERSION, build_library, build_preview, verify_library  # noqa: E402
from sfxlib.presets import KIND_TO_SOUNDS, PRESETS, synthesize  # noqa: E402


def dominant_frequency(signal: dsp.Signal, candidates: list[float]) -> float:
    """在候选频率中找能量最大的一个（逐点做单频相关，避免依赖 numpy）。"""
    def energy(frequency: float) -> float:
        real = sum(x * math.cos(2 * math.pi * frequency * i / dsp.SAMPLE_RATE) for i, x in enumerate(signal))
        imag = sum(x * math.sin(2 * math.pi * frequency * i / dsp.SAMPLE_RATE) for i, x in enumerate(signal))
        return real * real + imag * imag
    return max(candidates, key=energy)


class PresetTests(unittest.TestCase):
    def test_same_seed_gives_identical_samples(self) -> None:
        for preset in PRESETS.values():
            self.assertEqual(synthesize(preset), synthesize(preset), preset.sound_id)

    def test_peak_matches_target_and_never_clips(self) -> None:
        for preset in PRESETS.values():
            signal = synthesize(preset)
            self.assertAlmostEqual(dsp.to_dbfs(dsp.peak(signal)), preset.peak_dbfs, places=3, msg=preset.sound_id)
            self.assertLess(dsp.peak(signal), 1.0)

    def test_starts_and_ends_at_zero(self) -> None:
        # 首尾为 0 才能在任意时刻叠进音效轨而不产生咔哒声
        for preset in PRESETS.values():
            signal = synthesize(preset)
            self.assertEqual(signal[0], 0.0, preset.sound_id)
            self.assertLess(abs(signal[-1]), 1e-3, preset.sound_id)

    def test_no_dc_offset(self) -> None:
        for preset in PRESETS.values():
            signal = synthesize(preset)
            self.assertLess(abs(sum(signal) / len(signal)), 5e-4, preset.sound_id)

    def test_type_variants_differ(self) -> None:
        variants = [synthesize(PRESETS[sound_id]) for sound_id in KIND_TO_SOUNDS["type"]]
        self.assertEqual(len(variants), 3)
        self.assertNotEqual(variants[0], variants[1])

    def test_every_kind_has_sounds(self) -> None:
        for kind, sound_ids in KIND_TO_SOUNDS.items():
            self.assertTrue(sound_ids, kind)
            self.assertTrue(all(PRESETS[s].kind == kind for s in sound_ids))


class DspTests(unittest.TestCase):
    def test_bandpass_keeps_center_frequency(self) -> None:
        tones = dsp.mix([(dsp.sine_glide(0.1, 300, 300), 1.0, 0.0), (dsp.sine_glide(0.1, 3000, 3000), 1.0, 0.0)])
        filtered = dsp.bandpass(tones, 3000, 4.0)
        self.assertEqual(dominant_frequency(filtered[1200:], [300.0, 3000.0]), 3000.0)

    def test_sine_glide_ends_at_target(self) -> None:
        glide = dsp.sine_glide(0.2, 1000, 500, glide=0.05)
        self.assertEqual(dominant_frequency(glide[4800:], [500.0, 750.0, 1000.0]), 500.0)

    def test_mix_offsets_by_samples(self) -> None:
        impulse = [1.0]
        mixed = dsp.mix([(impulse, 1.0, 0.0), (impulse, 0.5, 0.01)])
        self.assertEqual(len(mixed), 481)
        self.assertEqual(mixed[480], 0.5)


class LibraryTests(unittest.TestCase):
    def test_build_writes_wavs_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = build_library(out)
            self.assertEqual(manifest["generator"]["version"], GENERATOR_VERSION)
            self.assertFalse(manifest["rights"]["ai_generated"])
            self.assertEqual({entry["id"] for entry in manifest["sounds"]}, set(PRESETS))
            with wave.open(str(out / "pop.wav")) as handle:
                self.assertEqual((handle.getnchannels(), handle.getsampwidth(), handle.getframerate()), (1, 2, 48_000))
            self.assertEqual(verify_library(out), [])

    def test_rebuild_is_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = build_library(Path(tmp) / "a")
            second = build_library(Path(tmp) / "b")
            self.assertEqual([e["sha256"] for e in first["sounds"]], [e["sha256"] for e in second["sounds"]])

    def test_verify_reports_tampered_and_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            build_library(out)
            (out / "tick.wav").write_bytes(b"broken")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            manifest["generator"]["version"] = "0.0.1"
            (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            problems = verify_library(out)
            self.assertTrue(any("tick.wav" in p for p in problems))
            self.assertTrue(any("0.0.1" in p for p in problems))

    def test_verify_without_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(verify_library(Path(tmp)))

    def test_preview_demo_fits_and_lists_sounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "demo.wav"
            sequence = build_preview(dest, demo=True)
            with wave.open(str(dest)) as handle:
                seconds = handle.getnframes() / handle.getframerate()
            self.assertGreater(seconds, sequence[-1][0])
            self.assertTrue(all(sound_id in PRESETS for _, sound_id in sequence))


if __name__ == "__main__":
    unittest.main()
