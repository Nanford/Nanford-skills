"""纯线框矢量图标库（基础 SVG 图形拼接，约 56×36，零外部依赖）。"""
from __future__ import annotations

ICON_NAMES = (
    "collect", "clean", "compute", "analyze", "storage", "database",
    "server", "cloud", "user", "security", "message", "monitor", "api",
)


def icon(name: str, cx: float, cy: float, color: str) -> str:
    s = f'stroke="{color}" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"'
    shapes = {
        "collect": (
            f'<rect x="-24" y="-16" width="48" height="32" rx="3" {s}/>'
            f'<polyline points="-18,2 -10,2 -6,-8 0,10 5,-4 9,2 18,2" {s}/>'
        ),
        "clean": (
            f'<path d="M-16,-18 H8 L16,-10 V18 H-16 Z" {s}/><path d="M8,-18 V-10 H16" {s}/>'
            f'<circle cx="-2" cy="4" r="7" {s}/><line x1="3" y1="9" x2="10" y2="16" {s}/>'
        ),
        "compute": (
            f'<polygon points="-12,-18 12,-18 24,0 12,18 -12,18 -24,0" {s}/>'
            f'<line x1="-10" y1="-6" x2="10" y2="-6" {s}/><line x1="-14" y1="0" x2="14" y2="0" {s}/>'
            f'<line x1="-10" y1="6" x2="10" y2="6" {s}/>'
        ),
        "analyze": (
            f'<rect x="-26" y="-16" width="52" height="28" rx="2" {s}/>'
            f'<line x1="-14" y1="6" x2="-14" y2="-4" {s}/><line x1="-6" y1="6" x2="-6" y2="-8" {s}/>'
            f'<line x1="2" y1="6" x2="2" y2="0" {s}/><line x1="10" y1="6" x2="10" y2="-6" {s}/>'
            f'<line x1="-10" y1="18" x2="10" y2="18" {s}/>'
        ),
        "storage": (
            f'<ellipse cx="0" cy="-12" rx="18" ry="6" {s}/>'
            f'<path d="M-18,-12 V12 A18,6 0 0 0 18,12 V-12" {s}/><path d="M-18,0 A18,6 0 0 0 18,0" {s}/>'
        ),
        "database": None,
        "server": (
            f'<rect x="-20" y="-18" width="40" height="15" rx="2" {s}/><rect x="-20" y="3" width="40" height="15" rx="2" {s}/>'
            f'<circle cx="-12" cy="-10.5" r="1.5" fill="{color}"/><circle cx="-12" cy="10.5" r="1.5" fill="{color}"/>'
            f'<line x1="0" y1="-10.5" x2="12" y2="-10.5" {s}/><line x1="0" y1="10.5" x2="12" y2="10.5" {s}/>'
        ),
        "cloud": f'<path d="M-14,14 H16 A10,10 0 0 0 14,-6 A13,13 0 0 0 -10,-8 A11,11 0 0 0 -14,14 Z" {s}/>',
        "user": f'<circle cx="0" cy="-8" r="8" {s}/><path d="M-16,18 A16,14 0 0 1 16,18" {s}/>',
        "security": (
            f'<path d="M0,-18 L16,-12 V0 C16,10 8,16 0,19 C-8,16 -16,10 -16,0 V-12 Z" {s}/>'
            f'<polyline points="-7,0 -2,6 8,-5" {s}/>'
        ),
        "message": f'<rect x="-22" y="-14" width="44" height="28" rx="2" {s}/><polyline points="-22,-14 0,4 22,-14" {s}/>',
        "monitor": (
            f'<rect x="-24" y="-16" width="48" height="28" rx="2" {s}/>'
            f'<polyline points="-16,4 -6,-4 2,2 14,-8" {s}/><line x1="-10" y1="18" x2="10" y2="18" {s}/>'
        ),
        "api": (
            f'<rect x="-22" y="-16" width="44" height="32" rx="4" {s}/>'
            f'<polyline points="-8,-6 -14,0 -8,6" {s}/><polyline points="8,-6 14,0 8,6" {s}/>'
            f'<line x1="3" y1="-8" x2="-3" y2="8" {s}/>'
        ),
        "default": f'<rect x="-18" y="-18" width="36" height="36" rx="6" {s}/><circle cx="0" cy="0" r="7" {s}/>',
    }
    shapes["database"] = shapes["storage"]
    body = shapes.get(name) or shapes["default"]
    return f'<g transform="translate({cx:.1f},{cy:.1f})">{body}</g>'
