"""
INPUT: presets.py 的音色配方；输出目录（默认技能目录下 library/，被 .gitignore 的 library/ 规则忽略）
OUTPUT: build_library() 写出全部音效 WAV（48 kHz 单声道 16 位）与 manifest.json；verify_library() 校验文件与清单一致；
        build_preview() 把全部音效逐个排开，或按一段示范动作排成试听文件
POS: 音效库的生成与校验。WAV 不进 Git，由本模块从配方重建（同字体一样随用随建）；
     manifest 记录配方版本、校验值与权利信息，av-export 接入音效轨时只读 manifest 取文件。
"""

from __future__ import annotations

import hashlib
import json
import struct
import wave
from pathlib import Path
from typing import Any

from . import dsp
from .presets import KIND_TO_SOUNDS, PRESETS, synthesize

# 配方或处理链改动时递增；manifest 里的版本不同说明库需要重建，下游已混好的音效轨随之失效
GENERATOR_VERSION = "1.0.0"
MANIFEST_NAME = "manifest.json"
RIGHTS = {
    "source": "procedural",
    "ai_generated": False,
    "license": "本项目代码合成，无第三方素材与权利限制",
    "note": "全部声音由 sfxlib 配方从正弦与带种子的噪声计算得到，不含采样或外部音频",
}

# 示范动作序列（秒, 音效 ID）：模拟一个纯文字动效镜头，用来在上下文里试听，而不是一个个孤立地听
DEMO_SEQUENCE: list[tuple[float, str]] = [
    (0.0, "riser"), (1.2, "thud"),
    (1.8, "pop_soft"), (2.05, "pop_soft"), (2.3, "pop_soft"),
    *[(2.8 + 0.06 * step, "tick") for step in range(10)], (3.5, "ding"),
    (4.3, "strike"), (4.6, "error"),
    (5.2, "swipe"), (5.6, "success"),
    *[(6.4 + 0.11 * step, f"type_{step % 3 + 1}") for step in range(6)],
    (7.3, "whoosh_out"), (7.9, "whoosh"), (8.3, "pop"), (8.5, "click"),
]


def write_wav(path: Path, signal: dsp.Signal) -> str:
    """写 16 位 PCM WAV 并返回 SHA-256。先写临时文件再替换，中断时不留下半个文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = b"".join(struct.pack("<h", max(-32768, min(32767, round(x * 32767)))) for x in signal)
    temp = path.with_suffix(".tmp.wav")
    with wave.open(str(temp), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(dsp.SAMPLE_RATE)
        handle.writeframes(frames)
    temp.replace(path)
    return sha256_of(path)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sound_entry(sound_id: str, signal: dsp.Signal, sha256: str) -> dict[str, Any]:
    preset = PRESETS[sound_id]
    return {
        "id": sound_id,
        "kind": preset.kind,
        "description": preset.description,
        "file": f"{sound_id}.wav",
        "duration_ms": round(len(signal) * 1000 / dsp.SAMPLE_RATE),
        "peak_dbfs": round(dsp.to_dbfs(dsp.peak(signal)), 2),
        "rms_dbfs": round(dsp.to_dbfs(dsp.rms(signal)), 2),
        "seed": preset.seed,
        "sha256": sha256,
    }


def build_library(out_dir: Path) -> dict[str, Any]:
    """生成全部音效与清单。已存在且校验值一致的文件也会重写：配方是纯计算，重建比判断缓存更可靠。"""
    sounds = []
    for sound_id, preset in PRESETS.items():
        signal = synthesize(preset)
        sha256 = write_wav(out_dir / f"{sound_id}.wav", signal)
        sounds.append(_sound_entry(sound_id, signal, sha256))
    manifest = {
        "schema_version": "1.0",
        "generator": {"name": "sfx-kit", "version": GENERATOR_VERSION},
        "sample_rate": dsp.SAMPLE_RATE,
        "channels": 1,
        "sample_format": "s16",
        "rights": RIGHTS,
        "kinds": KIND_TO_SOUNDS,
        "sounds": sounds,
    }
    temp = out_dir / f"{MANIFEST_NAME}.tmp"
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(out_dir / MANIFEST_NAME)
    return manifest


def verify_library(out_dir: Path) -> list[str]:
    """返回问题列表；空列表表示清单、文件与当前配方版本一致。"""
    manifest_path = out_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return [f"缺少 {manifest_path}，先运行 build"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems = []
    if manifest.get("generator", {}).get("version") != GENERATOR_VERSION:
        problems.append(f"音效库由配方版本 {manifest.get('generator', {}).get('version')} 生成，当前为 {GENERATOR_VERSION}，需重新 build")
    listed = {entry["id"]: entry for entry in manifest.get("sounds", [])}
    for sound_id in PRESETS:
        entry = listed.get(sound_id)
        path = out_dir / f"{sound_id}.wav"
        if entry is None:
            problems.append(f"清单缺少 {sound_id}")
        elif not path.exists():
            problems.append(f"缺少文件 {path.name}")
        elif sha256_of(path) != entry["sha256"]:
            problems.append(f"{path.name} 与清单校验值不一致")
    return problems


def _catalog_sequence(gap: float) -> list[tuple[float, str]]:
    sequence, cursor = [], 0.3
    for sound_id, preset in PRESETS.items():
        sequence.append((round(cursor, 3), sound_id))
        cursor += len(synthesize(preset)) / dsp.SAMPLE_RATE + gap
    return sequence


def build_preview(dest: Path, demo: bool, gap: float = 0.8) -> list[tuple[float, str]]:
    """写试听文件并返回 (起始秒, 音效 ID) 列表。demo=True 时按示范动作排列，否则逐个排开。"""
    sequence = DEMO_SEQUENCE if demo else _catalog_sequence(gap)
    cache = {sound_id: synthesize(PRESETS[sound_id]) for _, sound_id in sequence}
    layers = [(cache[sound_id], 1.0, start) for start, sound_id in sequence]
    layers.append((dsp.silence(0.5), 0.0, sequence[-1][0] + len(cache[sequence[-1][1]]) / dsp.SAMPLE_RATE))
    signal = dsp.mix(layers)
    # 示范序列里声音会重叠，叠加后可能超过满刻度；只在超出时整体压低，保持各音效相对电平不变
    if dsp.peak(signal) > 0.95:
        signal = dsp.normalize_peak(signal, -1.0)
    write_wav(dest, signal)
    return sequence
