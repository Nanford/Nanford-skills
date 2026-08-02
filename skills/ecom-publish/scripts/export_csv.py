#!/usr/bin/env python3
"""Export validated listing copy and permanent image URLs to marketplace CSV."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RULES_PATH = Path(__file__).resolve().parent.parent / "assets" / "export_rules.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".webp"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_images(source: str | None, base_url: str | None) -> list[str]:
    if not source:
        return []
    path = Path(source)
    if path.is_file() and path.suffix.lower() == ".json":
        payload = load_json(path)
        values = payload.get("images", payload.get("urls", []))
        return [item.get("url", "") if isinstance(item, dict) else str(item) for item in values]
    files = sorted(item for item in path.iterdir() if item.suffix.lower() in IMAGE_EXTENSIONS)
    files.sort(key=lambda item: (0 if item.name.startswith("01") or "main" in item.name.lower() else 1, item.name))
    prefix = (base_url or "").rstrip("/")
    return [f"{prefix}/{item.name}" if prefix else str(item) for item in files]


def build_row(copy_data: dict[str, Any], urls: list[str], mapping: dict[str, Any], platform: str) -> dict[str, str]:
    row: dict[str, str] = {}
    sku = copy_data.get("sku") or copy_data.get("product", {}).get("sku", "")
    simple_fields = {
        "sku": sku,
        "title": copy_data.get("title", ""),
        "brand": copy_data.get("brand", ""),
        "description": copy_data.get("description", ""),
        "search_terms": copy_data.get("search_terms", ""),
    }
    for key, value in simple_fields.items():
        if key in mapping and value:
            row[mapping[key]] = str(value)

    bullets = copy_data.get("bullets", [])
    if mapping.get("bullets"):
        for index, bullet in enumerate(bullets, 1):
            row[mapping["bullets"].format(i=index)] = bullet
    elif bullets and mapping.get("description"):
        prefix = "\n".join(f"• {bullet}" for bullet in bullets)
        row[mapping["description"]] = f"{prefix}\n\n{row.get(mapping['description'], '')}".strip()

    if urls and mapping.get("main_image"):
        row[mapping["main_image"]] = "|".join(urls) if platform == "ebay" else urls[0]
        if platform != "ebay" and mapping.get("other_images"):
            for index, url in enumerate(urls[1:], 1):
                row[mapping["other_images"].format(i=index)] = url
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="导出平台刊登 CSV")
    parser.add_argument("--copy", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--images", help="成品图目录或图片 URL JSON")
    parser.add_argument("--base-url", help="成品图永久 CDN 前缀")
    parser.add_argument("--quality", help="quality-report.json；提供时必须无阻断")
    parser.add_argument("--out", default="listing_export.csv")
    args = parser.parse_args()

    if args.quality:
        quality = load_json(Path(args.quality))
        if int(quality.get("blocking", 0)) > 0:
            print("质检报告仍有阻断项，拒绝导出正式刊登包。")
            return 2

    rules = load_json(RULES_PATH)
    platform = rules["sites"].get(args.site)
    if not platform:
        print(f"未知站点：{args.site}")
        return 2
    copy_data = load_json(Path(args.copy))
    urls = collect_images(args.images, args.base_url)
    row = build_row(copy_data, urls, rules["field_maps"][platform], platform)

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)

    manifest = {
        "schema_version": "1.0",
        "site_id": args.site,
        "sku": copy_data.get("sku") or copy_data.get("product", {}).get("sku", ""),
        "csv": str(out_path),
        "image_count": len(urls),
        "quality_report": str(Path(args.quality).resolve()) if args.quality else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = out_path.with_name("export_manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已导出：{out_path}（{len(row)} 个字段，{len(urls)} 张图）")
    if urls and not args.base_url and not (args.images and Path(args.images).suffix.lower() == ".json"):
        print("提醒：当前 CSV 使用本地图片路径，正式刊登前替换为永久公网直链。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
