"""
INPUT: 无外部依赖（仅标准库 math）
OUTPUT: 48 kHz 单声道浮点信号的生成与处理函数：正弦滑音、噪声、包络、滤波、混合、峰值归一化与电平测量
POS: sfx-kit 的信号处理底层。音色配方（presets.py）只组合这里的函数，不直接写采样循环。
     只用标准库，保证技能单独复制到别处也能跑，与 av-export 一致。
"""

from __future__ import annotations

import math
import random
from typing import Callable

SAMPLE_RATE = 48_000
Signal = list[float]


def n_samples(seconds: float) -> int:
    return max(1, round(seconds * SAMPLE_RATE))


def silence(seconds: float) -> Signal:
    return [0.0] * n_samples(seconds)


def sine_glide(seconds: float, f_start: float, f_end: float, glide: float | None = None) -> Signal:
    """频率从 f_start 指数滑到 f_end（glide 秒内滑完，之后保持）。

    用相位累加而不是 sin(2πft)：频率随时间变化时直接代入 f(t) 会产生错误的瞬时频率。
    """
    glide = seconds if glide is None else max(glide, 1.0 / SAMPLE_RATE)
    ratio = f_end / f_start
    phase = 0.0
    out: Signal = []
    for index in range(n_samples(seconds)):
        progress = min(index / SAMPLE_RATE / glide, 1.0)
        frequency = f_start * ratio ** progress
        out.append(math.sin(phase))
        phase += 2.0 * math.pi * frequency / SAMPLE_RATE
    return out


def noise(seconds: float, rng: random.Random) -> Signal:
    """白噪声。随机源由调用方传入固定种子，同一配方每次生成相同采样。"""
    return [rng.uniform(-1.0, 1.0) for _ in range(n_samples(seconds))]


def exp_decay(seconds: float, tau: float, attack: float = 0.002) -> Signal:
    """短线性起音 + 指数衰减：打击类声音的基本包络。"""
    attack_samples = max(1, n_samples(attack))
    out: Signal = []
    for index in range(n_samples(seconds)):
        if index < attack_samples:
            out.append(index / attack_samples)
        else:
            out.append(math.exp(-(index - attack_samples) / SAMPLE_RATE / tau))
    return out


def swell(seconds: float, peak_at: float = 0.5, power: float = 2.0) -> Signal:
    """先升后降的包络，峰值位于 peak_at（0～1）。用于划过声，避免像开关一样突然出现。"""
    total = n_samples(seconds)
    peak_index = max(1, min(total - 1, round(total * peak_at)))
    out: Signal = []
    for index in range(total):
        if index <= peak_index:
            position = index / peak_index
        else:
            position = 1.0 - (index - peak_index) / max(1, total - 1 - peak_index)
        out.append(math.sin(position * math.pi / 2.0) ** power)
    return out


def multiply(a: Signal, b: Signal) -> Signal:
    return [x * y for x, y in zip(a, b)]


def scale(signal: Signal, gain: float) -> Signal:
    return [x * gain for x in signal]


def mix(layers: list[tuple[Signal, float, float]], seconds: float | None = None) -> Signal:
    """按 (信号, 增益, 起始秒) 叠加多层；总长默认取最晚结束的一层。"""
    end = max(round(offset * SAMPLE_RATE) + len(signal) for signal, _, offset in layers)
    total = n_samples(seconds) if seconds is not None else end
    out = [0.0] * total
    for signal, gain, offset in layers:
        start = round(offset * SAMPLE_RATE)
        for index, value in enumerate(signal):
            position = start + index
            if position >= total:
                break
            out[position] += value * gain
    return out


def _bandpass_coefficients(center: float, q: float) -> tuple[float, float, float, float, float]:
    # RBJ Audio EQ Cookbook 带通（恒定 0 dB 峰值增益），已按 a0 归一化
    omega = 2.0 * math.pi * min(center, SAMPLE_RATE * 0.45) / SAMPLE_RATE
    alpha = math.sin(omega) / (2.0 * q)
    a0 = 1.0 + alpha
    return alpha / a0, 0.0, -alpha / a0, -2.0 * math.cos(omega) / a0, (1.0 - alpha) / a0


def bandpass_sweep(signal: Signal, f_start: float, f_end: float, q: float, block: int = 32) -> Signal:
    """中心频率从 f_start 指数扫到 f_end 的带通滤波。

    每 block 个采样更新一次系数：逐采样重算太慢，32 个采样（0.67 ms）的阶梯听不出来。
    用转置直接 II 型结构，系数缓变时状态连续、不爆音。
    """
    ratio = f_end / f_start
    total = len(signal)
    z1 = z2 = 0.0
    b0 = b1 = b2 = a1 = a2 = 0.0
    out: Signal = []
    for index, x in enumerate(signal):
        if index % block == 0:
            center = f_start * ratio ** (index / max(1, total - 1))
            b0, b1, b2, a1, a2 = _bandpass_coefficients(center, q)
        y = b0 * x + z1
        z1 = b1 * x - a1 * y + z2
        z2 = b2 * x - a2 * y
        out.append(y)
    return out


def bandpass(signal: Signal, center: float, q: float) -> Signal:
    return bandpass_sweep(signal, center, center, q)


def one_pole(signal: Signal, cutoff: float, mode: str = "low") -> Signal:
    """一阶低通 / 高通，用来去掉噪声里刺耳的高频或闷响的低频。"""
    coefficient = math.exp(-2.0 * math.pi * cutoff / SAMPLE_RATE)
    state = 0.0
    out: Signal = []
    for x in signal:
        state = (1.0 - coefficient) * x + coefficient * state
        out.append(state if mode == "low" else x - state)
    return out


def fade_edges(signal: Signal, fade_in: float = 0.001, fade_out: float = 0.004) -> Signal:
    """首尾短淡入淡出，保证从 0 开始、回到 0 结束，混音时不产生咔哒声。"""
    out = list(signal)
    head = min(len(out), n_samples(fade_in))
    tail = min(len(out), n_samples(fade_out))
    for index in range(head):
        out[index] *= index / head
    for index in range(tail):
        out[len(out) - 1 - index] *= index / tail
    return out


def peak(signal: Signal) -> float:
    return max((abs(x) for x in signal), default=0.0)


def to_dbfs(level: float) -> float:
    return -120.0 if level <= 1e-6 else 20.0 * math.log10(level)


def rms(signal: Signal) -> float:
    return math.sqrt(sum(x * x for x in signal) / len(signal)) if signal else 0.0


def normalize_peak(signal: Signal, peak_dbfs: float) -> Signal:
    """把样本峰值归一到 peak_dbfs。音效库内部的相对电平靠它统一，进混音时再整体定增益。"""
    current = peak(signal)
    if current <= 0.0:
        return list(signal)
    return scale(signal, 10.0 ** (peak_dbfs / 20.0) / current)


def render(length_seconds: float, sample: Callable[[float], float]) -> Signal:
    """按时间函数逐点生成信号，给少数无法用上面组合表达的配方使用。"""
    return [sample(index / SAMPLE_RATE) for index in range(n_samples(length_seconds))]
