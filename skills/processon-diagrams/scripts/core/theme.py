"""从 references/color-themes.md 加载并解析 ProcessOn 配色主题。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
THEME_FILE = SKILL_DIR / "references" / "color-themes.md"
DEFAULT_THEME = "processon-teal"


def load_themes(theme_file: Path = THEME_FILE) -> dict[str, dict[str, str]]:
    text = theme_file.read_text(encoding="utf-8")
    themes: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"^## (\S+)\s*$((?:(?!^## ).)*?)```json\s*(\{.*?\})\s*```", text, re.S | re.M):
        themes[m.group(1)] = json.loads(m.group(3))
    return themes


def resolve_theme(model: dict, default: str = DEFAULT_THEME) -> dict[str, str]:
    themes = load_themes()
    name = model.get("themeName", default)
    if name not in themes:
        print(f"[warn] 未知主题 {name}，使用 {default}", file=sys.stderr)
        name = default
    return {**themes[name], **model.get("theme", {})}
