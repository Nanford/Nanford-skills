"""
INPUT: remotion-render actions 导出的 actions.json（全片动作标记）；sfx-kit 音效库（library/manifest.json 与各 WAV，48 kHz 单声道 16 位）；
       版本目录 timeline.json、audio/voice.wav（决定音效轨长度）
OUTPUT: SFX_LEVEL_DB、default_library()、pick_sound()、build_sfx_track()（写 audio/sfx.wav 与 audio/sfx.json）、current_sfx()（mix / mux 用的一致性校验）
POS: 音效轨的唯一实现。音效只挂在画面动作上（AGENTS.md 第 10 节），动作帧来自渲染代码，不手写时间。
     音效轨与人声母轨等长、同为 48 kHz 单声道，由 mix 与人声相加后一起限幅；没有 sfx.json 时 mix 的输出与接入音效前逐字节相同。
"""

from __future__ import annotations

import wave
from array import array
from pathlib import Path
from typing import Any

from .media import MediaError, local_now, read_json, replace_atomic, sha256_file, temp_sibling, write_json_atomic

SAMPLE_RATE = 48000
# 音效总线电平：各音效先按库内电平（峰值 -5～-15 dBFS），再整体压低这么多与人声（约 -16 LUFS）相加。
# 暂定值，尚未在真实配音上试听（docs/DESIGN.md 第 6 节），第一条带音效的成片试听后再定
SFX_LEVEL_DB = -8.0
INT16_MAX = 32767


def default_library() -> Path:
    """sfx-kit 与本技能同在一个技能目录下（工作区的 .claude/skills 或全局技能目录），音效库在 sfx-kit/library。"""
    return Path(__file__).resolve().parents[3] / "sfx-kit" / "library"


def pick_sound(kinds: dict[str, list[str]], kind: str, occurrence: int) -> str:
    """同一动作类型有多个变体（如打字 type_1～3）时按出现次序轮换，结果只取决于动作顺序，可复现。"""
    sounds = kinds.get(kind) or []
    if not sounds:
        raise MediaError(f"音效库没有动作类型 {kind}：sfx-kit 的 kinds 与 remotion-render 的动作类型不一致")
    return sounds[occurrence % len(sounds)]


def _read_mono16(path: Path) -> array:
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != SAMPLE_RATE or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise MediaError(f"{path.name} 不是 48 kHz 单声道 16 位 WAV")
        samples = array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
        return samples


def _wav_frames(path: Path) -> int:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes()


def _load_actions(variant_dir: Path, actions_path: Path) -> dict[str, Any]:
    if not actions_path.is_file():
        raise MediaError(f"找不到 {actions_path}：先运行 remotion-render 的 render.mjs actions 导出动作标记")
    actions = read_json(actions_path)
    timeline = read_json(variant_dir / "timeline.json")
    if actions.get("timeline", {}).get("sha256") != sha256_file(variant_dir / "timeline.json"):
        raise MediaError("actions.json 来自旧的 timeline.json：时间轴改过后请重跑 render.mjs actions")
    if actions.get("fps") != timeline.get("fps"):
        raise MediaError(f"actions.json 的帧率 {actions.get('fps')} 与时间轴 {timeline.get('fps')} 不一致")
    return actions


def _load_library(library: Path) -> dict[str, Any]:
    manifest_path = library / "manifest.json"
    if not manifest_path.is_file():
        raise MediaError(f"找不到音效库 {library}：先运行 python <sfx-kit 技能目录>/scripts/sfx_kit.py build（音效库不进 Git，每台机器生成一次）")
    manifest = read_json(manifest_path)
    manifest["_sha256"] = sha256_file(manifest_path)
    return manifest


def _sound_samples(library: Path, entry: dict[str, Any], cache: dict[str, array]) -> array:
    if entry["id"] not in cache:
        path = library / entry["file"]
        if not path.is_file() or sha256_file(path) != entry["sha256"]:
            raise MediaError(f"音效 {entry['file']} 缺失或与清单校验值不一致：重跑 sfx_kit.py build")
        cache[entry["id"]] = _read_mono16(path)
    return cache[entry["id"]]


def _place(track: array, samples: array, offset: int, gain: float) -> int:
    """把一个音效按增益叠到音效轨上；超出音轨末尾的部分截掉。返回被钳位的采样点数（重叠过多时才会发生）。"""
    clipped = 0
    end = min(len(track), offset + len(samples))
    for index in range(offset, end):
        value = track[index] + round(samples[index - offset] * gain)
        if value > INT16_MAX or value < -INT16_MAX:
            clipped += 1
            value = max(-INT16_MAX, min(INT16_MAX, value))
        track[index] = value
    return clipped


def _write_track(path: Path, track: array) -> None:
    temporary = temp_sibling(path)
    with wave.open(str(temporary), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(track.tobytes())
    replace_atomic(temporary, path)


def build_sfx_track(variant_dir: Path, actions_path: Path, library: Path, level_db: float = SFX_LEVEL_DB) -> dict[str, Any]:
    """按动作标记排出 audio/sfx.wav（与人声母轨等长）并写 audio/sfx.json。"""
    actions = _load_actions(variant_dir, actions_path)
    manifest = _load_library(library)
    sounds = {entry["id"]: entry for entry in manifest["sounds"]}
    voice = variant_dir / "audio" / "voice.wav"
    track = array("h", bytes(2 * _wav_frames(voice)))
    gain = 10 ** (level_db / 20)
    counts: dict[str, int] = {}
    cache: dict[str, array] = {}
    placements, clipped = [], 0
    for mark in actions["marks"]:
        occurrence = counts.get(mark["kind"], 0)
        counts[mark["kind"]] = occurrence + 1
        entry = sounds[pick_sound(manifest["kinds"], mark["kind"], occurrence)]
        # 用帧号换算采样点（帧 × 48000 / fps），不经毫秒取整，音效与画面动作同一帧对齐
        offset = round(mark["frame"] * SAMPLE_RATE / actions["fps"])
        clipped += _place(track, _sound_samples(library, entry, cache), offset, gain)
        placements.append({"shot_id": mark["shot_id"], "frame": mark["frame"], "sample_offset": offset, "kind": mark["kind"], "target": mark["target"], "sound": entry["id"], "sha256": entry["sha256"]})
    out = variant_dir / "audio" / "sfx.wav"
    _write_track(out, track)
    record = {
        "schema_version": "1.0", "variant": variant_dir.name, "created_at": local_now(),
        "inputs": {"actions": {"path": actions_path.relative_to(variant_dir).as_posix() if actions_path.is_relative_to(variant_dir) else str(actions_path), "sha256": sha256_file(actions_path)},
                   "timeline_sha256": actions["timeline"]["sha256"], "voice_sha256": sha256_file(voice)},
        "library": {"generator": manifest.get("generator"), "manifest_sha256": manifest["_sha256"], "rights": manifest.get("rights")},
        "level_db": level_db, "level_note": "暂定值，尚未在真实配音上试听（docs/DESIGN.md 第 6 节）",
        "placements": placements, "clipped_samples": clipped,
        "output": {"path": "audio/sfx.wav", "sha256": sha256_file(out), "sample_rate": SAMPLE_RATE, "channels": 1, "samples": len(track)},
    }
    write_json_atomic(variant_dir / "audio" / "sfx.json", record)
    return record


def current_sfx(variant_dir: Path, timeline: dict[str, Any]) -> dict[str, Any] | None:
    """mix 用：没有 sfx.json 返回 None（只混人声）；有就核对它对应当前时间轴、当前母轨，且 sfx.wav 没被改过。"""
    record_path = variant_dir / "audio" / "sfx.json"
    if not record_path.is_file():
        return None
    record = read_json(record_path)
    problems = []
    if record["inputs"]["timeline_sha256"] != sha256_file(variant_dir / "timeline.json"):
        problems.append("音效轨来自旧的 timeline.json")
    if record["inputs"]["voice_sha256"] != timeline.get("voice_audio_sha256"):
        problems.append("音效轨按旧的配音母轨长度生成")
    sfx_path = variant_dir / "audio" / "sfx.wav"
    if not sfx_path.is_file() or sha256_file(sfx_path) != record["output"]["sha256"]:
        problems.append("sfx.wav 缺失或与 sfx.json 记录不一致")
    if problems:
        raise MediaError("音效轨需要重做（重跑 render.mjs actions 与 av_export.py sfx）：" + "；".join(problems))
    record["_record_sha256"] = sha256_file(record_path)
    return record
