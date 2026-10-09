"""
INPUT: ffmpeg（把各段配音解码为 48 kHz 单声道 16 位 PCM）；Python wave 模块写出母轨
OUTPUT: decode_pcm() 解码一段音频；assemble_voice() 按片头、段间、片尾静音拼接为 voice.wav 并返回每段的全局起止时间
POS: 配音母轨的唯一生成点。全局时间按采样点累加计算，不做浮点毫秒累加，避免长片累计漂移。
"""

from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 48000
SAMPLE_WIDTH = 2  # 16 位
CHANNELS = 1  # MiniMax 输出为单声道；拼接不虚构立体声


class AudioError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlacedSegment:
    segment_id: str
    start_sample: int
    sample_count: int

    @property
    def start_ms(self) -> float:
        return self.start_sample * 1000 / SAMPLE_RATE

    @property
    def end_ms(self) -> float:
        return (self.start_sample + self.sample_count) * 1000 / SAMPLE_RATE


def decode_pcm(path: Path) -> bytes:
    """统一重采样到 48 kHz 单声道；重采样只统一格式，不代表提升原始音质。"""
    args = ["ffmpeg", "-v", "error", "-i", str(path), "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-f", "s16le", "-"]
    try:
        completed = subprocess.run(args, capture_output=True, check=False, timeout=300)
    except FileNotFoundError as error:
        raise AudioError("未找到 ffmpeg，请确认已安装并在 PATH 中") from error
    if completed.returncode != 0 or not completed.stdout:
        raise AudioError(f"解码失败 {path.name}: {completed.stderr.decode('utf-8', errors='replace')[-300:]}")
    return completed.stdout


def ms_to_samples(ms: int) -> int:
    return round(ms * SAMPLE_RATE / 1000)


def assemble_voice(segments: list[tuple[str, bytes]], out_path: Path, lead_ms: int, gap_ms: int, tail_ms: int) -> list[PlacedSegment]:
    """
    按顺序拼接：片头静音 + 段1 + 段间静音 + 段2 … + 片尾静音。
    段间静音是显式设计的停顿，计入总时长；不能把各段时长直接相加当作整片时长。
    """
    if not segments:
        raise AudioError("没有可拼接的配音段")
    bytes_per_sample = SAMPLE_WIDTH * CHANNELS
    placed: list[PlacedSegment] = []
    cursor = ms_to_samples(lead_ms)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_name(f"{out_path.name}.tmp")
    with wave.open(str(temporary), "wb") as writer:
        writer.setnchannels(CHANNELS)
        writer.setsampwidth(SAMPLE_WIDTH)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(b"\x00" * cursor * bytes_per_sample)
        for index, (segment_id, pcm) in enumerate(segments):
            count = len(pcm) // bytes_per_sample
            placed.append(PlacedSegment(segment_id, cursor, count))
            writer.writeframes(pcm[: count * bytes_per_sample])
            cursor += count
            pause = gap_ms if index < len(segments) - 1 else tail_ms
            writer.writeframes(b"\x00" * ms_to_samples(pause) * bytes_per_sample)
            cursor += ms_to_samples(pause)
    temporary.replace(out_path)
    return placed


def wav_duration_ms(path: Path) -> float:
    with wave.open(str(path), "rb") as reader:
        return reader.getnframes() * 1000 / reader.getframerate()
