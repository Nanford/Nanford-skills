#!/usr/bin/env python3
"""Compose deterministic multilingual text layers over generated base images."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageColor, ImageDraw, ImageFont
except ImportError:
    print("需要 Pillow：python -m pip install Pillow")
    raise SystemExit(2)


CJK_LANGS = {"zh", "ja", "ko"}
SCRIPT_DIR = Path(__file__).resolve().parent
FONT_DIR = SCRIPT_DIR.parent / "assets" / "fonts"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_font(locale: str, explicit: str | None) -> Path | None:
    if explicit and Path(explicit).is_file():
        return Path(explicit)
    lang = (locale or "en").split("-", 1)[0].lower()
    bundled = {
        "zh": ["NotoSansSC-Bold.ttf", "NotoSansCJK-Bold.ttc"],
        "ja": ["NotoSansJP-Bold.ttf", "NotoSansCJK-Bold.ttc"],
        "ko": ["NotoSansKR-Bold.ttf", "NotoSansCJK-Bold.ttc"],
    }.get(lang, ["NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf"])
    for name in bundled:
        path = FONT_DIR / name
        if path.is_file():
            return path

    windows = {
        "zh": ["msyhbd.ttc", "simhei.ttf"],
        "ja": ["YuGothB.ttc", "meiryob.ttc"],
        "ko": ["malgunbd.ttf"],
    }.get(lang, ["arialbd.ttf", "segoeuib.ttf"])
    for name in windows:
        path = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts" / name
        if path.is_file():
            return path

    for value in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        path = Path(value)
        if path.is_file():
            return path
    return None


def text_width(draw: ImageDraw.ImageDraw, value: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), value or " ", font=font)
    return box[2] - box[0]


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    locale: str,
) -> list[str]:
    lang = (locale or "en").split("-", 1)[0].lower()
    units = list(text) if lang in CJK_LANGS else text.split()
    joiner = "" if lang in CJK_LANGS else " "
    lines: list[str] = []
    current = ""
    for unit in units:
        candidate = joiner.join(filter(None, (current, unit)))
        if not current or text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = unit
    if current:
        lines.append(current)
    return lines or [""]


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: Path,
    min_size: int,
    max_size: int,
    max_width: int,
    max_height: int,
    locale: str,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    for size in range(max_size, min_size - 1, -2):
        font = ImageFont.truetype(str(font_path), size)
        lines = wrap_text(draw, text, font, max_width, locale)
        line_height = max(1, int((draw.textbbox((0, 0), "Ag", font=font)[3]) * 1.22))
        if line_height * len(lines) <= max_height:
            return font, lines, line_height
    font = ImageFont.truetype(str(font_path), min_size)
    lines = wrap_text(draw, text, font, max_width, locale)
    line_height = max(1, int(draw.textbbox((0, 0), "Ag", font=font)[3] * 1.22))
    return font, lines, line_height


def layer_box(layer: dict[str, Any], width: int, height: int) -> tuple[int, int, int, int]:
    raw = layer.get("box", [0.05, 0.05, 0.50, 0.35])
    if len(raw) != 4 or any(float(value) < 0 or float(value) > 1 for value in raw):
        raise ValueError(f"无效文字框：{raw}")
    left, top, right, bottom = raw
    box = (int(left * width), int(top * height), int(right * width), int(bottom * height))
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError(f"文字框宽高必须为正数：{raw}")
    return box


def compose_job(
    job: dict[str, Any], base_path: Path, output_path: Path, locale: str, font_override: str | None
) -> list[str]:
    image = Image.open(base_path).convert("RGB")
    if job.get("size"):
        image = image.resize(tuple(int(value) for value in job["size"]), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    warnings: list[str] = []
    font_path = find_font(locale, font_override)
    layers = job.get("text_layers", [])
    if layers and not font_path:
        raise RuntimeError("找不到支持目标语言的字体；请用 --font 指定字体文件")

    for layer in layers:
        text = str(layer.get("text", "")).strip()
        if not text:
            continue
        box = layer_box(layer, image.width, image.height)
        padding = int(min(image.size) * float(layer.get("padding", 0.008)))
        max_width = max(1, box[2] - box[0] - 2 * padding)
        max_height = max(1, box[3] - box[1] - 2 * padding)
        requested = float(layer.get("font_size", 0.055))
        max_size = max(10, int(image.height * requested)) if requested <= 1 else int(requested)
        min_size = max(10, int(max_size * 0.55))
        font, lines, line_height = fit_text(
            draw, text, font_path, min_size, max_size, max_width, max_height, locale
        )
        if line_height * len(lines) > max_height:
            warnings.append(f"{job['id']}：文字可能超出安全区：{text[:24]}")

        background = layer.get("background")
        if background:
            radius = int(layer.get("radius", 0.012) * min(image.size))
            draw.rounded_rectangle(box, radius=radius, fill=ImageColor.getrgb(background))

        align = layer.get("align", "left")
        y = box[1] + padding
        for line in lines:
            width = text_width(draw, line, font)
            if align == "center":
                x = box[0] + (box[2] - box[0] - width) // 2
            elif align == "right":
                x = box[2] - padding - width
            else:
                x = box[0] + padding
            draw.text(
                (x, y),
                line,
                font=font,
                fill=ImageColor.getrgb(layer.get("color", "#111111")),
                stroke_width=int(layer.get("stroke_width", 0)),
                stroke_fill=ImageColor.getrgb(layer.get("stroke_color", "#FFFFFF")),
            )
            y += line_height

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=94, subsampling=0)
    return warnings


def find_base(base_dir: Path, job_id: str) -> Path | None:
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        path = base_dir / f"{job_id}{suffix}"
        if path.is_file():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="把精确文字图层合成到电商底图")
    parser.add_argument("--jobs", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--font")
    args = parser.parse_args()

    jobs_path = Path(args.jobs).resolve()
    document = load_json(jobs_path)
    base_dir = Path(args.base).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    locale = document.get("locale", "en-US")
    items = []
    failures = 0
    for job in document.get("jobs", []):
        job_id = job["id"]
        base_path = find_base(base_dir, job_id)
        if not base_path:
            items.append({"job_id": job_id, "status": "failed", "error": "找不到底图"})
            failures += 1
            continue
        output_path = out_dir / f"{job_id}-{job.get('type', 'image')}.jpg"
        try:
            warnings = compose_job(job, base_path, output_path, locale, args.font)
            items.append({
                "job_id": job_id,
                "status": "success",
                "base": str(base_path),
                "output": str(output_path),
                "text_layers": len(job.get("text_layers", [])),
                "warnings": warnings,
            })
        except Exception as exc:
            items.append({"job_id": job_id, "status": "failed", "error": str(exc)})
            failures += 1

    manifest = {
        "schema_version": "1.0",
        "status": "failed" if failures else "complete",
        "locale": locale,
        "items": items,
    }
    (out_dir / "compose_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已合成 {sum(item['status'] == 'success' for item in items)} 张；失败 {failures} 张")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
