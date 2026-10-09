"""
INPUT: 平台版本目录下的 speech.json（语段顺序、朗读文本、屏幕写法替换）；
       audio/segments/<id>.mp3、<id>.meta.json、<id>.subtitles.json（minimax-tts 技能产物）；ffmpeg
OUTPUT: assemble 子命令：audio/voice.wav（48 kHz 单声道母轨）、更新后的 speech.json（每段真实时长与全局起止）、
        captions/captions.json 与 captions/subtitles.srt
POS: 配音拼接与字幕生成技能的命令入口。只读写给定版本目录内的文件，不改 project.json。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from vclib.audio import AudioError, assemble_voice, decode_pcm, wav_duration_ms
from vclib.captions import build_captions
from vclib.providers import SubtitleFormatError, parse_minimax_words
from vclib.srt import to_srt, validate_entries

SCHEMA_VERSION = "1.0"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def load_segment_inputs(variant_dir: Path, segment: dict[str, Any]) -> tuple[Path, dict[str, Any], Any]:
    """读取一段的音频、元数据与字幕，并确认音频正是用当前朗读文本合成的。"""
    segment_id = segment["segment_id"]
    folder = variant_dir / "audio" / "segments"
    audio, meta_path, subtitle_path = folder / f"{segment_id}.mp3", folder / f"{segment_id}.meta.json", folder / f"{segment_id}.subtitles.json"
    for required in (audio, meta_path, subtitle_path):
        if not required.exists():
            raise FileNotFoundError(f"缺少 {required.name}，先用 minimax-tts 合成该段")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("text") != segment["spoken_text"]:
        raise ValueError(f"{segment_id} 的音频不是用当前朗读文本合成的，需要重新合成后再拼接")
    return audio, meta, json.loads(subtitle_path.read_text(encoding="utf-8"))


def caption_entries(segment: dict[str, Any], raw_subtitles: Any, offset_ms: float, max_width: float) -> list[dict[str, Any]]:
    text = segment["spoken_text"]
    replacements = [tuple(pair) for pair in segment.get("display_replacements") or []]
    lines = build_captions(text, parse_minimax_words(raw_subtitles, text), replacements, max_width, segment.get("caption_breaks") or [])
    return [
        {
            "id": f"{segment['segment_id']}-{index:02d}",
            "segment_id": segment["segment_id"],
            # 全局时间 = 该段在母轨中的起点 + 段内时间戳
            "start_ms": round(offset_ms + line.start_ms),
            "end_ms": round(offset_ms + line.end_ms),
            "text": line.text,
            "timing_source": "provider",
            "verified": False,
        }
        for index, line in enumerate(lines, 1)
    ]


def update_speech(speech: dict[str, Any], placed: dict[str, Any], metas: dict[str, dict[str, Any]], variant_dir: Path) -> None:
    for segment in speech["segments"]:
        position = placed[segment["segment_id"]]
        audio = variant_dir / "audio" / "segments" / f"{segment['segment_id']}.mp3"
        segment.update({
            "audio_path": audio.relative_to(variant_dir).as_posix(),
            "sha256": sha256_file(audio),
            "duration_ms": round(position.end_ms - position.start_ms),
            "global_start_ms": round(position.start_ms),
            "global_end_ms": round(position.end_ms),
            "timing_source": "provider",
            "timing_granularity": "word",
            "provider_request_id": metas[segment["segment_id"]].get("trace_id"),
        })


def command_assemble(args: argparse.Namespace) -> int:
    variant_dir = Path(args.variant_dir).resolve()
    speech_path = variant_dir / "speech.json"
    speech = json.loads(speech_path.read_text(encoding="utf-8"))
    inputs = {s["segment_id"]: load_segment_inputs(variant_dir, s) for s in speech["segments"]}
    pcm = [(segment_id, decode_pcm(audio)) for segment_id, (audio, _, _) in inputs.items()]
    voice_path = variant_dir / "audio" / "voice.wav"
    placed = {p.segment_id: p for p in assemble_voice(pcm, voice_path, args.lead_ms, args.gap_ms, args.tail_ms)}
    entries: list[dict[str, Any]] = []
    for segment in speech["segments"]:
        entries += caption_entries(segment, inputs[segment["segment_id"]][2], placed[segment["segment_id"]].start_ms, args.max_width)
    duration = wav_duration_ms(voice_path)
    problems = validate_entries(entries, duration)
    update_speech(speech, placed, {k: v[1] for k, v in inputs.items()}, variant_dir)
    speech["master_audio"] = {"path": "audio/voice.wav", "sha256": sha256_file(voice_path), "duration_ms": round(duration),
                              "sample_rate": 48000, "channels": 1, "lead_ms": args.lead_ms, "gap_ms": args.gap_ms, "tail_ms": args.tail_ms}
    captions = {"schema_version": SCHEMA_VERSION, "variant": speech.get("variant"), "audio_sha256": speech["master_audio"]["sha256"],
                "timebase": "ms", "max_line_width": args.max_width, "entries": entries}
    write_text_atomic(speech_path, json.dumps(speech, ensure_ascii=False, indent=2))
    write_text_atomic(variant_dir / "captions" / "captions.json", json.dumps(captions, ensure_ascii=False, indent=2))
    write_text_atomic(variant_dir / "captions" / "subtitles.srt", to_srt(entries))
    print(f"母轨 {duration / 1000:.2f}s，{len(speech['segments'])} 段，字幕 {len(entries)} 条 -> {voice_path}")
    for problem in problems:
        print(f"[字幕问题] {problem}", file=sys.stderr)
    return 1 if problems else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="配音拼接与字幕生成")
    sub = parser.add_subparsers(dest="command", required=True)
    assemble = sub.add_parser("assemble", help="拼接配音母轨并生成字幕")
    assemble.add_argument("--variant-dir", required=True, help="如 projects/<id>/variants/douyin")
    assemble.add_argument("--lead-ms", type=int, default=200, help="片头静音")
    assemble.add_argument("--gap-ms", type=int, default=200, help="段间停顿")
    assemble.add_argument("--tail-ms", type=int, default=800, help="片尾静音，给收尾画面留时间")
    assemble.add_argument("--max-width", type=float, default=16, help="单行字幕最大宽度（汉字计 1）")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，被智能体管道读取时中文会乱码；统一输出 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return command_assemble(args)
    except (AudioError, SubtitleFormatError, ValueError, OSError) as error:
        print(f"[失败] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
