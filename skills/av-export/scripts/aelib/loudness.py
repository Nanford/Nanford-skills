"""
INPUT: ffmpeg（ebur128 测量、volume + alimiter 处理）；WAV 或含音轨的 MP4
OUTPUT: Loudness、LoudnessTarget、measure_loudness()、parse_ebur128_summary()、level_voice()（可带音效轨一起处理）
POS: 响度处理与测量的唯一实现。混音阶段用它把人声母轨处理到目标响度，质检阶段用同一个测量函数复测最终 AAC 音轨，避免两套算法口径不一。
"""

from __future__ import annotations

import re
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .media import MediaError, run_tool

OUTPUT_RATE = 48000
# 限幅在 4 倍过采样下进行，样点峰值即近似真峰值（ebur128 的真峰值同样按 4 倍过采样计算）
OVERSAMPLE_RATE = OUTPUT_RATE * 4


@dataclass(frozen=True)
class Loudness:
    integrated_lufs: float
    true_peak_dbtp: float
    lra_lu: float


@dataclass(frozen=True)
class LoudnessTarget:
    """AGENTS.md 第 10 节的内部标准：目标 -16 LUFS，容许 -18～-14，最终真峰值不高于 -1 dBTP。"""

    integrated_lufs: float = -16.0
    accept_min_lufs: float = -18.0
    accept_max_lufs: float = -14.0
    max_true_peak_dbtp: float = -1.0
    # 限幅器天花板比最终上限再低 1 dB：留给 48 kHz 重采样与 AAC 编码的峰值上冲
    limiter_ceiling_dbfs: float = -2.0
    # 实测与目标相差超过该值时，按差值再修正一次增益
    retry_tolerance_lu: float = 0.3

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


_SUMMARY_PATTERNS = {
    "integrated_lufs": re.compile(r"I:\s+(-?[\d.]+|-inf)\s+LUFS"),
    "lra_lu": re.compile(r"LRA:\s+(-?[\d.]+)\s+LU\b"),
    "true_peak_dbtp": re.compile(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS"),
}


def _to_float(text: str) -> float:
    return float("-inf") if text == "-inf" else float(text)


def parse_ebur128_summary(stderr: str) -> Loudness:
    """解析 ebur128 滤镜最后输出的 Summary 段；逐帧日志中的同名字段不参与解析。"""
    marker = stderr.rfind("Summary:")
    if marker < 0:
        raise MediaError("ebur128 没有输出 Summary，无法得到响度")
    summary = stderr[marker:]
    values: dict[str, float] = {}
    for key, pattern in _SUMMARY_PATTERNS.items():
        match = pattern.search(summary)
        if not match:
            raise MediaError(f"ebur128 Summary 缺少 {key}")
        values[key] = _to_float(match.group(1))
    return Loudness(**values)


def measure_loudness(path: Path) -> Loudness:
    """测量第一条音轨的综合响度、响度范围与真峰值（ITU-R BS.1770 / EBU R128）。"""
    completed = run_tool(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"], timeout=900)
    return parse_ebur128_summary(completed.stderr)


def _wav_frames(path: Path) -> int:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes()


def _render_leveled(src: Path, dst: Path, gain_db: float, target: LoudnessTarget, sfx: Path | None = None) -> None:
    ceiling = 10 ** (target.limiter_ceiling_dbfs / 20)
    chain = (
        f"aresample={OVERSAMPLE_RATE},volume={gain_db:.2f}dB,"
        # level=0 关闭自动电平（默认会把输出拉满到 0 dBFS）；latency=1 补偿前视延迟，保证声画不偏移
        f"alimiter=limit={ceiling:.5f}:attack=5:release=50:level=0:latency=1,"
        f"aresample={OUTPUT_RATE}"
    )
    if sfx is None:
        # 只有人声：命令与接入音效前完全相同，输出逐字节不变
        inputs = ["-i", str(src), "-map", "0:a:0", "-af", chain]
    else:
        # 人声按增益调到目标响度，音效轨（电平已在 sfx.wav 里定好）原样相加后一起过限幅；normalize=0 让 amix 只相加不平均
        limiter = chain.split(",", 2)[2]
        graph = (f"[0:a]aresample={OVERSAMPLE_RATE},volume={gain_db:.2f}dB[voice];[1:a]aresample={OVERSAMPLE_RATE}[sfx];"
                 f"[voice][sfx]amix=inputs=2:normalize=0:duration=first,{limiter}[out]")
        inputs = ["-i", str(src), "-i", str(sfx), "-filter_complex", graph, "-map", "[out]"]
    run_tool([
        "ffmpeg", "-hide_banner", "-v", "error", "-y", *inputs,
        "-ac", "1", "-ar", str(OUTPUT_RATE), "-c:a", "pcm_s16le", "-map_metadata", "-1",
        # bitexact：不写入编码器版本字符串，同一输入与参数得到逐字节相同的文件
        "-fflags", "+bitexact", "-flags:a", "+bitexact", str(dst),
    ], timeout=900)


def level_voice(src: Path, dst: Path, target: LoudnessTarget, sfx: Path | None = None) -> dict[str, Any]:
    """
    固定增益 + 过采样限幅，把人声处理到目标响度。
    不用 loudnorm：原始峰值偏高时它会退回动态模式，逐段改变增益，可能产生泵动；这里全片只用一个增益值。
    限幅器会略微降低综合响度，所以处理后复测，差值超过容差时按差值修正一次。
    给了 sfx（与母轨等长的音效轨）时，增益仍按人声算，复测与修正针对人声 + 音效的整体响度。
    """
    before = measure_loudness(src)
    if before.integrated_lufs == float("-inf"):
        raise MediaError(f"{src.name} 没有可测量的声音")
    applied_gain_db = target.integrated_lufs - before.integrated_lufs
    attempts: list[dict[str, float]] = []
    for attempt in range(2):
        _render_leveled(src, dst, applied_gain_db, target, sfx)
        after = measure_loudness(dst)
        attempts.append({"gain_db": round(applied_gain_db, 2), "integrated_lufs": after.integrated_lufs, "true_peak_dbtp": after.true_peak_dbtp})
        if attempt == 1 or abs(after.integrated_lufs - target.integrated_lufs) <= target.retry_tolerance_lu:
            break
        applied_gain_db += target.integrated_lufs - after.integrated_lufs
    if _wav_frames(src) != _wav_frames(dst):
        raise MediaError(f"处理前后采样点数不一致（{_wav_frames(src)} → {_wav_frames(dst)}），会造成声画偏移")
    # 返回的增益始终是最后一次实际写入 dst 的值
    return {"before": asdict(before), "after": asdict(after), "attempts": attempts, "final_gain_db": round(applied_gain_db, 2)}
