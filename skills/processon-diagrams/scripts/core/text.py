"""中英文文本宽度估算、自动换行、水平/竖排 SVG 文本构建。"""
from __future__ import annotations

from xml.sax.saxutils import escape

FONT = (
    "'PingFang SC','Microsoft YaHei','Hiragino Sans GB',"
    "'Noto Sans CJK SC','Source Han Sans SC',-apple-system,'Segoe UI',Arial,sans-serif"
)


def text_width(s: str, fs: float) -> float:
    w = 0.0
    for ch in s:
        o = ord(ch)
        if o >= 0x2E80 or 0xFF00 <= o <= 0xFFEF:
            w += fs
        elif ch in "mwMW@":
            w += fs * 0.85
        elif ch.isupper() or ch.isdigit():
            w += fs * 0.64
        elif ch == " ":
            w += fs * 0.3
        else:
            w += fs * 0.52
    return w


def wrap(s: str, max_w: float, fs: float, max_lines: int = 3) -> list[str]:
    if text_width(s, fs) <= max_w:
        return [s]
    lines, cur = [], ""
    for ch in s:
        if text_width(cur + ch, fs) > max_w and cur:
            lines.append(cur)
            cur = ch.lstrip()
        else:
            cur += ch
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    return lines


def lines_height(n: int, fs: float) -> float:
    return n * fs * 1.35


def text_block(cx: float, cy: float, lines: list[str], fs: float, weight: str | None = None, anchor: str = "middle") -> str:
    lh = fs * 1.35
    start = cy - (len(lines) - 1) * lh / 2 + fs * 0.35
    w = f' font-weight="{weight}"' if weight else ""
    out = []
    for i, line in enumerate(lines):
        out.append(
            f'<text x="{cx:.1f}" y="{start + i * lh:.1f}" font-size="{fs}" text-anchor="{anchor}"{w}>{escape(line)}</text>'
        )
    return "".join(out)


def vertical_text(cx: float, cy: float, s: str, fs: float, avail_h: float) -> str:
    chars = list(s)
    lh = min(fs + 4, max(fs, (avail_h - 12) / max(len(chars), 1)))
    start = cy - (len(chars) - 1) * lh / 2 + fs * 0.35
    spans = "".join(
        f'<tspan x="{cx:.1f}" y="{start + i * lh:.1f}">{escape(c)}</tspan>' for i, c in enumerate(chars)
    )
    return f'<text font-size="{fs}" text-anchor="middle">{spans}</text>'
