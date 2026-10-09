"""
INPUT: shots.json 的镜头参数（{…} 强调标记，可带语义色 {熬通宵|痛点}；EvidenceCard / StepFlow 的 tone；BeforeAfter 对比行的第三项；KineticText 的 beats）
OUTPUT: TONE_NAMES、strip_tone_marks()、plain_display()、shot_tones()、check_tones()
POS: 「按文案意思选颜色」预设的文稿检查（2026-10-09 主理人要求）。色名表、各效果默认色与 remotion-render 的
     src/markup.ts、src/kinetic.ts 的 DEFAULT_TONES 一致，改动时三处同步。渲染时未知色名直接报错，这里提前拦下。
"""

from __future__ import annotations

import re
from typing import Any

# 中文名与英文键名 → 语义色键名；与 remotion-render 的 TONES 一致
TONE_NAMES = {"品牌": "brand", "痛点": "pain", "解法": "gain", "数据": "data", "提醒": "caution"}
TONE_NAMES.update({key: key for key in list(TONE_NAMES.values())})
# 同一镜头除品牌紫外最多几种语义色：再多画面就花了，观众分不清哪个颜色代表什么
MAX_SEMANTIC_TONES = 2
# KineticText 各效果没写语义色时 {…} 的默认色（text, replace），与 src/kinetic.ts 的 DEFAULT_TONES 一致
KINETIC_DEFAULTS = {"count": ("data", "data"), "strike": ("pain", "gain"), "dissolve": ("pain", "gain")}

_ACCENT = re.compile(r"\{([^{}]*)\}")


def strip_tone_marks(text: str) -> str:
    """{熬通宵|痛点} → {熬通宵}：色名不上屏、不计宽。"""
    return re.sub(r"\|[^{}|]*\}", "}", text)


def plain_display(text: str) -> str:
    """上屏的纯文字：去掉色名与花括号。"""
    return strip_tone_marks(text).replace("{", "").replace("}", "")


def _accent_tones(text: str, default: str, unknown: list[str]) -> set[str]:
    tones: set[str] = set()
    for body in _ACCENT.findall(text):
        name = body.rsplit("|", 1)[1].strip() if "|" in body else None
        if name is None:
            tones.add(default)
        elif name in TONE_NAMES:
            tones.add(TONE_NAMES[name])
        else:
            unknown.append(name)
    return tones


def _named(value: Any, unknown: list[str]) -> set[str]:
    if not isinstance(value, str) or not value:
        return set()
    if value in TONE_NAMES:
        return {TONE_NAMES[value]}
    unknown.append(value)
    return set()


def _beat_tones(beats: Any, unknown: list[str]) -> set[str]:
    tones: set[str] = set()
    for beat in beats if isinstance(beats, list) else []:
        if not isinstance(beat, dict):
            continue
        text_default, replace_default = KINETIC_DEFAULTS.get(str(beat.get("effect")), ("brand", "brand"))
        tones |= _accent_tones(str(beat.get("text", "")), text_default, unknown)
        tones |= _accent_tones(str(beat.get("replace", "")), replace_default, unknown)
        # 划线与消散的旧说法本身就用痛点色画（划线条、颗粒），即使文字里没写强调
        if beat.get("effect") == "strike":
            tones.add("pain")
    return tones


def shot_tones(shot: dict[str, Any]) -> tuple[set[str], list[str]]:
    """一个镜头用到的语义色（含品牌紫）与未知色名。"""
    params = shot.get("params") or {}
    unknown: list[str] = []
    tones = _named(params.get("tone"), unknown)
    for key, value in params.items():
        if key == "beats" and shot.get("scene_type") == "KineticText":
            tones |= _beat_tones(value, unknown)
        elif key == "columns" and isinstance(value, list):
            for row in value:
                if isinstance(row, list):
                    tones |= _accent_tones(" ".join(str(cell) for cell in row[:2]), "brand", unknown)
                    tones |= _named(row[2] if len(row) > 2 else None, unknown)
        elif isinstance(value, str):
            tones |= _accent_tones(value, "brand", unknown)
        elif isinstance(value, list):
            tones |= _accent_tones(" ".join(item for item in value if isinstance(item, str)), "brand", unknown)
    return tones, unknown


def check_tones(shots: dict[str, Any], finding: Any) -> list[Any]:
    """未知色名报错（渲染会失败）；同一镜头除品牌紫外超过 MAX_SEMANTIC_TONES 种语义色报错。"""
    findings = []
    for shot in shots["shots"]:
        tones, unknown = shot_tones(shot)
        where = shot["shot_id"]
        if unknown:
            findings.append(finding("error", "tone.unknown", where, f"未知的语义色：{'、'.join(unknown)}；可用 品牌 / 痛点 / 解法 / 数据 / 提醒"))
        semantic = sorted(tones - {"brand"})
        if len(semantic) > MAX_SEMANTIC_TONES:
            findings.append(finding("error", "tone.too_many", where, f"一个镜头用了 {len(semantic)} 种语义色（{'、'.join(semantic)}）；除品牌紫外最多 {MAX_SEMANTIC_TONES} 种，拆镜头或改用品牌紫"))
    return findings
