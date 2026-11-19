#!/usr/bin/env python3
"""ProcessOn 风格图表统一渲染入口：JSON 模型 -> SVG（可选导出 PNG 预览）。

用法:
    python render.py model.json -o out.svg [--png out.png] [--diagram architecture]
    python render.py --list

仅依赖 Python 3 标准库。PNG 预览通过本机 Edge / Chrome 无头模式截图实现。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 确保直接运行脚本时能导入同级 core / diagrams 包
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from core import export_png, load_themes
from diagrams import DEFAULT_DIAGRAM, REGISTRY, get_renderer


def _configure_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def main():
    _configure_stdio()
    ap = argparse.ArgumentParser(description="ProcessOn 风格多图种渲染器：JSON -> SVG")
    ap.add_argument("model", nargs="?", help="JSON 图表模型文件")
    ap.add_argument("-o", "--out", help="输出 SVG 路径（默认与 JSON 同名）")
    ap.add_argument("--png", help="同时导出 PNG 预览（需要本机 Edge/Chrome）")
    ap.add_argument("--diagram", help=f"覆盖 JSON 中的 diagram 字段（默认 {DEFAULT_DIAGRAM}）")
    ap.add_argument("--list", action="store_true", help="列出当前支持的图种与配色主题")
    args = ap.parse_args()

    if args.list:
        print("支持的图种:", ", ".join(sorted(REGISTRY)))
        print("支持的主题:", ", ".join(load_themes()))
        return

    if not args.model:
        ap.error("请提供 JSON 模型文件路径，或使用 --list 查看支持的图种与主题")

    model_path = Path(args.model)
    model = json.loads(model_path.read_text(encoding="utf-8"))
    diagram_type = args.diagram or model.get("diagram", DEFAULT_DIAGRAM)

    try:
        renderer_cls = get_renderer(diagram_type)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(2)

    svg = renderer_cls(model).render()
    out = Path(args.out) if args.out else model_path.with_suffix(".svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"SVG: {out}")

    if args.png:
        m = re.search(r'width="(\d+)" height="(\d+)"', svg)
        if m and export_png(out, Path(args.png), int(m.group(1)), int(m.group(2))):
            print(f"PNG: {args.png}")


if __name__ == "__main__":
    main()
