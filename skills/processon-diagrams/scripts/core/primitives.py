"""所有 ProcessOn 图种共用的 SVG 渲染基类（基础图元、几何箭头、连线与文档封装）。"""
from __future__ import annotations

import sys

from .text import FONT, lines_height, text_block, text_width, wrap
from .theme import DEFAULT_THEME, resolve_theme

DEFAULT_NODE_H = 40
DEFAULT_NODE_FS = 14


class BaseDiagram:
    """所有图种渲染器的基类。子类实现 render() -> str 即可复用配色、排版、箭头与导出能力。"""

    def __init__(self, model: dict, default_width: int = 1200, default_theme: str = DEFAULT_THEME):
        self.m = model
        self.t = resolve_theme(model, default=default_theme)
        self.W = int(model.get("canvas", {}).get("w", default_width))
        self.parts: list[str] = []
        self.nodes: dict[str, tuple[float, float, float, float]] = {}  # id -> (x, y, w, h)

    # --- 基础图元 ---
    def rect(self, x: float, y: float, w: float, h: float, fill: str, rx: float = 0,
             dashed: bool = False, stroke: str | None = None):
        da = ' stroke-dasharray="6 4"' if dashed else ""
        self.parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke or self.t["stroke"]}" stroke-width="1"{da}/>'
        )

    @staticmethod
    def parse_item(item) -> tuple[str, str | None, str | None]:
        if isinstance(item, str):
            return item, None, None
        return item.get("label", ""), item.get("id"), item.get("variant")

    def node_h(self, item, w: float, fs: float = DEFAULT_NODE_FS, min_h: float = DEFAULT_NODE_H) -> float:
        label = self.parse_item(item)[0]
        n = len(wrap(label, w - 16, fs))
        return max(min_h, lines_height(n, fs) + 16)

    def node(self, x: float, y: float, w: float, h: float, item, fill: str,
             rx: float = 6, fs: float = DEFAULT_NODE_FS):
        label, nid, variant = self.parse_item(item)
        if variant == "highlight":
            fill = self.t["cardHeaderFill"]
        self.rect(x, y, w, h, fill, rx, dashed=(variant == "external"))
        self.parts.append(
            text_block(
                x + w / 2,
                y + h / 2,
                wrap(label, w - 16, fs),
                fs,
                weight="bold" if variant == "highlight" else None,
            )
        )
        if nid:
            self.nodes[nid] = (x, y, w, h)

    @staticmethod
    def evenly(x0: float, x1: float, n: int, w: float) -> list[float]:
        """在 [x0, x1] 内等距（space-evenly）排列 n 个宽 w 的元素，返回各元素 x。"""
        gap = (x1 - x0 - n * w) / (n + 1)
        return [x0 + gap + i * (w + gap) for i in range(n)]

    # --- 几何拼接箭头与连线（禁用 <marker> 以保证跨工具渲染一致） ---
    def arrow_head(self, x: float, y: float, angle: float):
        c = self.t["lineColor"]
        self.parts.append(
            f'<g class="flow-arrow" transform="translate({x:.1f},{y:.1f}) rotate({angle})">'
            f'<polygon points="0,0 -9,-4.5 -9,4.5" fill="{c}"/></g>'
        )

    def arrow_line(self, x1: float, y1: float, x2: float, y2: float, dashed: bool = False):
        c = self.t["lineColor"]
        da = ' stroke-dasharray="5 4"' if dashed else ""
        if y1 == y2:
            d, ang, ex = (1 if x2 > x1 else -1), (0 if x2 > x1 else 180), x2
            self.parts.append(
                f'<path d="M{x1:.1f},{y1:.1f} H{ex - d * 8:.1f}" stroke="{c}" stroke-width="1.2" fill="none"{da}/>'
            )
        else:
            d, ang = (1 if y2 > y1 else -1), (90 if y2 > y1 else 270)
            self.parts.append(
                f'<path d="M{x1:.1f},{y1:.1f} V{y2 - d * 8:.1f}" stroke="{c}" stroke-width="1.2" fill="none"{da}/>'
            )
        self.arrow_head(x2, y2, ang)

    def draw_connections(self, connections: list[dict] | None = None):
        c = self.t["lineColor"]
        items = self.m.get("connections", []) if connections is None else connections
        for con in items:
            a, b = self.nodes.get(con["from"]), self.nodes.get(con["to"])
            if not a or not b:
                print(f"[warn] 连线端点不存在: {con}", file=sys.stderr)
                continue
            ax, ay, aw, ah = a
            bx, by, bw, bh = b
            da = ' stroke-dasharray="5 4"' if con.get("dashed") else ""
            ox0, ox1 = max(ax, bx), min(ax + aw, bx + bw)  # 水平投影重叠区间
            oy0, oy1 = max(ay, by), min(ay + ah, by + bh)  # 垂直投影重叠区间
            if ox1 - ox0 >= 20 and (by >= ay + ah or by + bh <= ay):  # 上下对齐：直线
                x = (ox0 + ox1) / 2
                down = by >= ay + ah
                sy, ey = (ay + ah, by) if down else (ay, by + bh)
                ex, ang = x, (90 if down else 270)
                d = f"M{x:.1f},{sy:.1f} V{ey - (8 if down else -8):.1f}"
                lx, ly = x, (sy + ey) / 2
            elif oy1 - oy0 >= 20 and (bx >= ax + aw or bx + bw <= ax):  # 左右对齐：直线
                y = (oy0 + oy1) / 2
                right = bx >= ax + aw
                sx, ex = (ax + aw, bx) if right else (ax, bx + bw)
                ey, ang = y, (0 if right else 180)
                d = f"M{sx:.1f},{y:.1f} H{ex - (8 if right else -8):.1f}"
                lx, ly = (sx + ex) / 2, y
            elif by >= ay + ah:  # 向下折线
                sx, sy, ex, ey, ang = ax + aw / 2, ay + ah, bx + bw / 2, by, 90
                my = (sy + ey) / 2
                d = f"M{sx:.1f},{sy:.1f} V{my:.1f} H{ex:.1f} V{ey - 8:.1f}"
                lx, ly = (sx + ex) / 2, my
            elif by + bh <= ay:  # 向上折线
                sx, sy, ex, ey, ang = ax + aw / 2, ay, bx + bw / 2, by + bh, 270
                my = (sy + ey) / 2
                d = f"M{sx:.1f},{sy:.1f} V{my:.1f} H{ex:.1f} V{ey + 8:.1f}"
                lx, ly = (sx + ex) / 2, my
            else:  # 水平折线
                right = bx >= ax + aw
                sx = ax + aw if right else ax
                ex = bx if right else bx + bw
                sy, ey, ang = ay + ah / 2, by + bh / 2, (0 if right else 180)
                mx = (sx + ex) / 2
                k = 8 if right else -8
                d = f"M{sx:.1f},{sy:.1f} H{mx:.1f} V{ey:.1f} H{ex - k:.1f}"
                lx, ly = mx, (sy + ey) / 2
            self.parts.append(f'<path d="{d}" stroke="{c}" stroke-width="1.2" fill="none"{da}/>')
            self.arrow_head(ex, ey, ang)
            if con.get("label"):
                tw = text_width(con["label"], 12) + 10
                self.parts.append(
                    f'<rect x="{lx - tw / 2:.1f}" y="{ly - 9:.1f}" width="{tw:.1f}" height="18" fill="{self.t["background"]}"/>'
                )
                self.parts.append(text_block(lx, ly, [con["label"]], 12))

    # --- SVG 文档封装 ---
    def wrap_svg(self, height: int) -> str:
        t, W = self.t, self.W
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}">\n'
            f'<style>text{{font-family:{FONT};fill:{t["text"]};}}</style>\n'
            f'<rect width="{W}" height="{height}" fill="{t["background"]}"/>\n'
        )
        return head + "\n".join(self.parts) + "\n</svg>\n"

    def render(self) -> str:
        raise NotImplementedError
