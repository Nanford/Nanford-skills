"""
INPUT: public/wallpapers/manifest.json 中待处理的条目（有 source_url、没有 sha256，或用 --force 点名的 id）；
       Unsplash 图片 CDN（images.unsplash.com，原图下载页有人机验证，CDN 可直接取原尺寸）；Pillow
OUTPUT: public/wallpapers/<id>.jpg（1080×1920，JPEG 质量 86），并把原图尺寸与校验值、裁切框、成品校验值与字节数写回清单；
        --restore 按清单恢复全部底图（安装技能时用，清单不改）
POS: 风景底图库的维护脚本，只在加图或换图时手动运行；渲染时不联网、不调用本脚本。
     原图缓存在工作区（找不到时为技能目录）的 .cache/wallpapers/（Git 忽略），同一原图重跑得到同一成品。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

from workspace import find_workspace

SKILL_ROOT = Path(__file__).resolve().parents[1]
WALLPAPER_DIR = SKILL_ROOT / "public" / "wallpapers"
MANIFEST_PATH = WALLPAPER_DIR / "manifest.json"
# 原图缓存是构建中间文件，不是工作区状态：有工作区就放工作区 .cache（多个副本共用），
# 没有（如安装技能时还没建工作区）就放技能目录自己的 .cache，两处都被 .gitignore 排除
_WORKSPACE = find_workspace()
CACHE_DIR = (_WORKSPACE or SKILL_ROOT) / ".cache" / "wallpapers"
TARGET_SIZE = (1080, 1920)
JPEG_QUALITY = 86


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download_source(entry: dict) -> Path:
    """取原图到缓存；已缓存就不再联网。fm=jpg&q=100 让 CDN 返回原尺寸 JPEG。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / f"{entry['id']}.jpg"
    if target.exists() and target.stat().st_size > 0:
        return target
    temp = target.with_suffix(".tmp")
    url = f"{entry['source_url']}?fm=jpg&q=100"
    completed = subprocess.run(["curl", "-sS", "-L", "--fail", "--max-time", "120", "-o", str(temp), url],
                               capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"{entry['id']} 原图下载失败：{completed.stderr.strip()}")
    temp.replace(target)
    return target


def crop_box(size: tuple[int, int], focus_x: float, focus_y: float) -> list[int]:
    """原图能容纳的最大 9:16 区域；focus 是取景中心（0～1），靠边时夹在图内。"""
    width, height = size
    target_ratio = TARGET_SIZE[0] / TARGET_SIZE[1]
    if width / height > target_ratio:
        box_w, box_h = round(height * target_ratio), height
    else:
        box_w, box_h = width, round(width / target_ratio)
    left = min(max(round(focus_x * width - box_w / 2), 0), width - box_w)
    top = min(max(round(focus_y * height - box_h / 2), 0), height - box_h)
    return [left, top, left + box_w, top + box_h]


def _render(image: Image.Image, box: list[int], output: Path) -> None:
    result = image.crop(tuple(box)).resize(TARGET_SIZE, Image.Resampling.LANCZOS)
    temp = output.with_suffix(".tmp.jpg")
    result.save(temp, format="JPEG", quality=JPEG_QUALITY)
    temp.replace(output)


def build(entry: dict) -> dict:
    source = download_source(entry)
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    box = crop_box(image.size, entry.get("focus_x", 0.5), entry.get("focus_y", 0.5))
    output = WALLPAPER_DIR / entry["file"]
    _render(image, box, output)
    entry.update({
        "source_size": list(image.size),
        "source_sha256": sha256_of(source),
        "box": box,
        "sha256": sha256_of(output),
        "bytes": output.stat().st_size,
    })
    return entry


def restore(entry: dict) -> str:
    """
    按清单恢复一张底图（安装技能时用，清单不改）：成品已存在且校验值相符就跳过；否则下载原图、核对原图校验值，
    用清单记下的裁切框重做。返回 ok / rebuilt / differs（重做的成品与清单校验值不同：多半是 Pillow 或 libjpeg 版本不同，
    画面肉眼一致，但渲染结果不再与原机器逐字节相同）。
    """
    output = WALLPAPER_DIR / entry["file"]
    if output.is_file() and sha256_of(output) == entry["sha256"]:
        return "ok"
    if not entry.get("source_url"):
        # nature 组 6 张的原图是从图库下载页手动取的，下载页有人机验证、CDN 版本会重新编码，无法原样取回，所以随技能包附带（主理人 2026-10-09 选定）
        raise RuntimeError(f"{entry['id']} 随技能包附带、不能下载，但文件缺失或已改动：请重新安装技能包")
    source = download_source(entry)
    if sha256_of(source) != entry["source_sha256"]:
        raise RuntimeError(f"{entry['id']} 原图与清单记录的校验值不一致（图库换了图？），不使用；删掉缓存 {source} 重试，仍不一致请换图")
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    _render(image, entry["box"], output)
    return "rebuilt" if sha256_of(output) == entry["sha256"] else "differs"


def restore_all(manifest: dict) -> int:
    results = {entry["id"]: restore(entry) for entry in manifest["wallpapers"]}
    differs = [key for key, value in results.items() if value == "differs"]
    print(f"底图 {len(results)} 张：已有 {list(results.values()).count('ok')}，重做 {list(results.values()).count('rebuilt') + len(differs)}")
    if differs:
        print(f"[提示] {len(differs)} 张重做结果与清单校验值不同（{', '.join(differs)}）：本机 Pillow {Image.__version__} 与生成清单时不同，"
              "画面可用，但与原机器的渲染结果不再逐字节一致")
    return 0


def main() -> int:
    # Windows 控制台默认 GBK，被智能体管道读取时中文会乱码；与其他技能一样统一输出 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="下载并裁切风景底图，写回 manifest.json；--restore 只按清单恢复缺失的底图")
    parser.add_argument("--force", nargs="*", default=[], help="重做这些 id（默认只处理还没有 sha256 的条目）")
    parser.add_argument("--restore", action="store_true", help="安装时用：按清单下载并恢复全部底图，核对校验值，不改清单")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if args.restore:
        return restore_all(manifest)
    todo = [e for e in manifest["wallpapers"] if e.get("source_url") and (not e.get("sha256") or e["id"] in args.force)]
    for entry in todo:
        build(entry)
        print(f"{entry['id']}: {entry['source_size'][0]}x{entry['source_size'][1]} box {entry['box']} -> {entry['bytes']} bytes")
    temp = MANIFEST_PATH.with_suffix(".tmp.json")
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(MANIFEST_PATH)
    print(f"处理 {len(todo)} 张；清单共 {len(manifest['wallpapers'])} 张")
    return 0


if __name__ == "__main__":
    sys.exit(main())
