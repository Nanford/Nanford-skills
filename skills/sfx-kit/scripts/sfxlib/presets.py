"""
INPUT: dsp.py 的信号函数
OUTPUT: PRESETS（音效 ID → Preset：动作类型、说明、目标峰值、随机种子、配方函数）；KIND_TO_SOUNDS（动作类型 → 可用音效 ID）
POS: 系列音效的「音色配方表」。每个音效对应画面里的一类动作（出现、落定、划过、计数、强调、划掉等），
     动作标记接入后由 av-export 按动作类型取声音。改配方会改变产物校验值，manifest 会如实记录。
     风格取向：轻、短、干净的界面声，服务于口播而不抢话；具体电平待首个音效项目试听后写入 docs/DESIGN.md。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable

from . import dsp
from .dsp import Signal

Recipe = Callable[[random.Random], Signal]


@dataclass(frozen=True)
class Preset:
    sound_id: str
    kind: str
    description: str
    peak_dbfs: float
    seed: int
    recipe: Recipe


def _pop(f_start: float, f_end: float, seconds: float) -> Recipe:
    """元素弹出：下滑的正弦「啵」+ 2 ms 高频瞬态，让起音更清楚。"""
    def recipe(rng: random.Random) -> Signal:
        body = dsp.multiply(dsp.sine_glide(seconds, f_start, f_end, glide=0.06), dsp.exp_decay(seconds, 0.035))
        transient = dsp.multiply(dsp.one_pole(dsp.noise(0.004, rng), 2500, "high"), dsp.exp_decay(0.004, 0.0015, 0.0003))
        return dsp.mix([(body, 1.0, 0.0), (transient, 0.35, 0.0)])
    return recipe


def _click(rng: random.Random) -> Signal:
    """按下 / 选中：带通噪声短脉冲 + 高音短正弦。"""
    burst = dsp.multiply(dsp.bandpass(dsp.noise(0.012, rng), 3500, 1.2), dsp.exp_decay(0.012, 0.003, 0.0003))
    tone = dsp.multiply(dsp.sine_glide(0.04, 2200, 2000), dsp.exp_decay(0.04, 0.008, 0.0005))
    return dsp.mix([(burst, 1.6, 0.0), (tone, 0.5, 0.0)])


def _tick(rng: random.Random) -> Signal:
    """数字滚动的每一跳：极短的高音，连续出现也不吵。"""
    base = dsp.multiply(dsp.sine_glide(0.035, 2600, 2600), dsp.exp_decay(0.035, 0.009, 0.0004))
    overtone = dsp.multiply(dsp.sine_glide(0.035, 5200, 5200), dsp.exp_decay(0.035, 0.005, 0.0004))
    return dsp.mix([(base, 1.0, 0.0), (overtone, 0.2, 0.0)])


def _whoosh(f_start: float, f_end: float, seconds: float, peak_at: float, q: float) -> Recipe:
    """划过：带通扫频噪声 + 先升后降包络。扫频方向决定「进来」还是「离开」。"""
    def recipe(rng: random.Random) -> Signal:
        swept = dsp.bandpass_sweep(dsp.noise(seconds, rng), f_start, f_end, q)
        return dsp.multiply(swept, dsp.swell(seconds, peak_at=peak_at))
    return recipe


def _thud(rng: random.Random) -> Signal:
    """大字落定：低频下滑正弦 + 低通噪声，给「砸下来」的重量感。"""
    body = dsp.multiply(dsp.sine_glide(0.32, 120, 46, glide=0.18), dsp.exp_decay(0.32, 0.09, 0.001))
    knock = dsp.multiply(dsp.one_pole(dsp.noise(0.03, rng), 900), dsp.exp_decay(0.03, 0.008, 0.0005))
    return dsp.mix([(body, 1.0, 0.0), (knock, 0.6, 0.0)])


def _bell_partials(frequency: float, seconds: float, tau: float) -> Signal:
    # 基频 + 二倍频 + 2.76 倍非谐泛音：后者让声音像小铃而不是纯正弦
    layers = [(1.0, 1.0), (2.0, 0.22), (2.76, 0.12)]
    partials = [(dsp.multiply(dsp.sine_glide(seconds, frequency * r, frequency * r), dsp.exp_decay(seconds, tau / r ** 0.5, 0.002)), g, 0.0)
                for r, g in layers]
    return dsp.mix(partials)


def _ding(rng: random.Random) -> Signal:
    """强调 / 结论出现：单个清亮的铃声（G6）。"""
    return _bell_partials(1568.0, 0.9, 0.32)


def _success(rng: random.Random) -> Signal:
    """完成 / 打勾：两音上行（E6 → B6），间隔 90 ms。"""
    first = _bell_partials(1318.5, 0.5, 0.18)
    second = _bell_partials(1975.5, 0.6, 0.24)
    return dsp.mix([(first, 0.8, 0.0), (second, 1.0, 0.09)])


def _error(rng: random.Random) -> Signal:
    """错误说法 / 否定：两下低沉的短促嗡声，奇次谐波后低通，避免刺耳。"""
    def pulse() -> Signal:
        tone = dsp.mix([(dsp.sine_glide(0.07, 220 * h, 220 * h), 1.0 / h, 0.0) for h in (1, 3, 5)])
        return dsp.multiply(dsp.one_pole(tone, 1800), dsp.exp_decay(0.07, 0.05, 0.003))
    return dsp.mix([(pulse(), 1.0, 0.0), (pulse(), 1.0, 0.12)])


def _strike(rng: random.Random) -> Signal:
    """划掉：笔划过纸面的沙沙声，用 38 Hz 抖动调制出纸面颗粒感。"""
    seconds = 0.24
    scratchy = dsp.bandpass_sweep(dsp.noise(seconds, rng), 2400, 4200, 1.4)
    jitter = dsp.render(seconds, lambda t: 0.55 + 0.45 * abs(math.sin(math.pi * 38 * t)))
    return dsp.multiply(dsp.multiply(scratchy, jitter), dsp.swell(seconds, peak_at=0.3, power=1.0))


def _type(rng: random.Random) -> Signal:
    """打字：键帽的高频咔嗒 + 低频轻撞；中心频率随种子变化，连续打字不像复读。"""
    center = rng.uniform(1700, 2700)
    clack = dsp.multiply(dsp.bandpass(dsp.noise(0.05, rng), center, 2.0), dsp.exp_decay(0.05, 0.010, 0.0004))
    bump = dsp.multiply(dsp.sine_glide(0.05, 190, 150), dsp.exp_decay(0.05, 0.014, 0.001))
    return dsp.mix([(clack, 1.4, 0.0), (bump, 0.4, 0.0)])


def _riser(rng: random.Random) -> Signal:
    """揭晓前的蓄势：1.2 秒上扫噪声 + 上滑正弦，渐强到末尾后快速收住。"""
    seconds = 1.2
    air = dsp.bandpass_sweep(dsp.noise(seconds, rng), 400, 5000, 1.8)
    tone = dsp.sine_glide(seconds, 220, 880)
    crescendo = dsp.render(seconds, lambda t: (t / seconds) ** 2.2)
    body = dsp.mix([(air, 1.0, 0.0), (tone, 0.12, 0.0)])
    return dsp.fade_edges(dsp.multiply(body, crescendo), fade_in=0.01, fade_out=0.03)


PRESETS: dict[str, Preset] = {preset.sound_id: preset for preset in [
    Preset("pop", "appear", "元素弹出、卡片出现", -6.0, 101, _pop(1100, 380, 0.12)),
    Preset("pop_soft", "appear_small", "小元素、图标、列表项出现", -11.0, 102, _pop(720, 260, 0.10)),
    Preset("click", "press", "按下、选中、光标点击", -9.0, 103, _click),
    Preset("tick", "count", "数字滚动每一跳、进度推进", -14.0, 104, _tick),
    Preset("whoosh", "transition_in", "镜头或大元素划入", -10.0, 105, _whoosh(320, 2800, 0.45, 0.62, 2.4)),
    Preset("whoosh_out", "transition_out", "元素划出、收起", -11.0, 106, _whoosh(2800, 300, 0.40, 0.35, 2.4)),
    Preset("swipe", "swap", "卡片切换、前后对比翻面", -13.0, 107, _whoosh(800, 3600, 0.18, 0.55, 1.8)),
    Preset("thud", "land", "大字或关键数字落定", -5.0, 108, _thud),
    Preset("ding", "highlight", "重点高亮、结论出现", -10.0, 109, _ding),
    Preset("success", "success", "完成、打勾、通过", -10.0, 110, _success),
    Preset("error", "wrong", "错误说法、否定、警示", -11.0, 111, _error),
    Preset("strike", "strike", "划掉错误说法", -13.0, 112, _strike),
    Preset("type_1", "type", "打字（变体 1）", -15.0, 113, _type),
    Preset("type_2", "type", "打字（变体 2）", -15.0, 114, _type),
    Preset("type_3", "type", "打字（变体 3）", -15.0, 115, _type),
    Preset("riser", "build", "揭晓前的蓄势", -12.0, 116, _riser),
]}

KIND_TO_SOUNDS: dict[str, list[str]] = {}
for _preset in PRESETS.values():
    KIND_TO_SOUNDS.setdefault(_preset.kind, []).append(_preset.sound_id)


def synthesize(preset: Preset) -> Signal:
    """按配方生成、隔直、去首尾咔哒声、归一到目标峰值。同一配方与种子每次结果相同。"""
    raw = preset.recipe(random.Random(preset.seed))
    # 下滑的低频正弦衰减后会留下直流偏移（thud 实测约 0.002），叠加多个音效时会抬高底噪，20 Hz 高通去掉
    dc_blocked = dsp.one_pole(raw, 20.0, "high")
    return dsp.normalize_peak(dsp.fade_edges(dc_blocked), preset.peak_dbfs)
