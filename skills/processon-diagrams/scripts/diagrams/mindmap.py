"""ProcessOn 风格思维导图渲染器（diagram: "mindmap"）。

支持：
- 左右均衡展开（layout: "both"，主分支 >= 4 默认）与纯向右逻辑树（layout: "right"）
- 中心主题强调圆角框 + 6 色循环主分支 + 继承分支色调的二/三级节点（胶囊框 + 下划线风格）
- 经典 ProcessOn 平滑三次贝塞尔曲线连线
- 精确自底向上子树高度计算，保证任意深度零重叠；支持节点 tag 徽标（如 P0 / 重点）
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from core import BaseDiagram, lines_height, text_width, wrap

MARGIN_X = 48
MARGIN_Y = 34
TITLE_H = 40
TITLE_GAP = 16
H_GAP_ROOT = 54     # 中心主题到一级分支的水平曲率跨度
H_GAP_SUB = 38      # 子节点之间的水平曲率跨度
V_GAP_MAIN = 20     # 一级分支之间的垂直间距
V_GAP_SUB = 10      # 二/三级子节点之间的垂直间距


class MindMapDiagram(BaseDiagram):
    def __init__(self, model: dict):
        super().__init__(model, default_width=1240)
        if not model.get("root"):
            raise ValueError("思维导图必须提供 root 节点")
        self.root = model["root"]
        self.palette = list(self.t.get("mindBranches") or ["#00A2B8", "#4CAF50", "#FF9800", "#5C6BC0", "#EC407A", "#26A69A"])

    def _measure_node(self, node: dict, depth: int) -> tuple[float, float, list[str], float]:
        label = str(node.get("label", node.get("name", "")))
        tag = str(node.get("tag", "") or "")
        tag_w = (text_width(tag, 11.0) + 14.0) if tag else 0.0

        if depth == 0:
            fs, pad_x, pad_y, max_w = 17.0, 26.0, 14.0, 230.0
        elif depth == 1:
            fs, pad_x, pad_y, max_w = 14.5, 18.0, 10.0, 200.0
        elif depth == 2:
            fs, pad_x, pad_y, max_w = 13.5, 14.0, 7.0, 220.0
        else:
            fs, pad_x, pad_y, max_w = 13.0, 10.0, 5.0, 240.0

        lines = wrap(label, max_w, fs, max_lines=2)
        tw = max((text_width(l, fs) for l in lines), default=40.0)
        w = tw + 2 * pad_x + (tag_w + 6.0 if tag else 0.0)
        h = max(48.0 if depth == 0 else (38.0 if depth == 1 else (32.0 if depth == 2 else 26.0)),
                lines_height(len(lines), fs) + 2 * pad_y)
        return w, h, lines, tag_w

    def _build_branch(self, node: dict, depth: int, color: str) -> dict:
        c = node.get("color") or color
        w, h, lines, tag_w = self._measure_node(node, depth)
        kids = [self._build_branch(ch, depth + 1, c) for ch in (node.get("children") or [])]
        gap = V_GAP_SUB
        if not kids:
            sub_h = h
            sub_w = w
        else:
            kids_h = sum(k["sub_h"] for k in kids) + gap * (len(kids) - 1)
            sub_h = max(h, kids_h)
            sub_w = w + H_GAP_SUB + max(k["sub_w"] for k in kids)
        return {
            "raw": node,
            "depth": depth,
            "color": c,
            "w": w,
            "h": h,
            "lines": lines,
            "tag": str(node.get("tag", "") or ""),
            "tag_w": tag_w,
            "children": kids,
            "sub_h": sub_h,
            "sub_w": sub_w,
        }

    def _draw_text(self, cx: float, cy: float, lines: list[str], fs: float, fill: str, weight: str | None = None, anchor: str = "middle"):
        lh = fs * 1.32
        start = cy - (len(lines) - 1) * lh / 2 + fs * 0.35
        w = f' font-weight="{weight}"' if weight else ""
        for i, line in enumerate(lines):
            self.parts.append(
                f'<text x="{cx:.1f}" y="{start + i * lh:.1f}" font-size="{fs}" '
                f'text-anchor="{anchor}" style="fill:{fill}"{w}>{escape(line)}</text>'
            )

    def _draw_node(self, item: dict, x: float, cy: float, side: int):
        w, h, depth, color = item["w"], item["h"], item["depth"], item["color"]
        y = cy - h / 2
        tag, tag_w = item["tag"], item["tag_w"]

        if depth == 0:
            self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10" fill="{color}"/>')
            tx = x + (w - (tag_w + 6 if tag else 0)) / 2
            self._draw_text(tx, cy, item["lines"], 17.0, "#FFFFFF", weight="bold")
        elif depth == 1:
            self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="{color}"/>')
            tx = x + (w - (tag_w + 6 if tag else 0)) / 2
            self._draw_text(tx, cy, item["lines"], 14.5, "#FFFFFF", weight="bold")
        elif depth == 2:
            self.parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="5" '
                f'fill="{self.t["background"]}" stroke="{color}" stroke-width="1.6"/>'
            )
            tx = x + (w - (tag_w + 6 if tag else 0)) / 2
            self._draw_text(tx, cy, item["lines"], 13.5, self.t["text"], weight="500")
        else:
            # 三级及以下：ProcessOn 经典轻盈下划线节点（避免满屏边框显拥挤）
            self.parts.append(
                f'<line x1="{x + 2:.1f}" y1="{y + h - 2:.1f}" x2="{x + w - 2:.1f}" y2="{y + h - 2:.1f}" '
                f'stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>'
            )
            tx = x + (w - (tag_w + 6 if tag else 0)) / 2
            self._draw_text(tx, cy - 1, item["lines"], 13.0, self.t["text"])

        if tag:
            bx = x + w - tag_w - (10 if depth <= 1 else 6)
            by = cy - 9
            bg = "#FFFFFF" if depth <= 1 else color
            fg = color if depth <= 1 else "#FFFFFF"
            self.parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{tag_w:.1f}" height="18" rx="9" fill="{bg}"/>')
            self._draw_text(bx + tag_w / 2, cy, [tag], 11.0, fg, weight="bold")

        if item["raw"].get("id"):
            self.nodes[item["raw"]["id"]] = (x, y, w, h)

    def _curve(self, x0: float, y0: float, x1: float, y1: float, color: str, width: float):
        mx = (x0 + x1) / 2
        d = f"M{x0:.1f},{y0:.1f} C{mx:.1f},{y0:.1f} {mx:.1f},{y1:.1f} {x1:.1f},{y1:.1f}"
        self.parts.append(f'<path d="{d}" stroke="{color}" stroke-width="{width}" fill="none" stroke-linecap="round"/>')

    def _draw_branch(self, item: dict, anchor_x: float, top_y: float, side: int):
        """side: +1 向右展开，-1 向左展开。anchor_x 是当前节点靠近父节点一侧的边缘 x。"""
        cy = top_y + item["sub_h"] / 2
        x = anchor_x if side == 1 else anchor_x - item["w"]
        # 先画子节点与连线，再画当前节点（确保节点盖住线条端点）
        kids = item["children"]
        if kids:
            kids_h = sum(k["sub_h"] for k in kids) + V_GAP_SUB * (len(kids) - 1)
            ky = top_y + (item["sub_h"] - kids_h) / 2
            out_x = (x + item["w"]) if side == 1 else x
            out_y = (cy + item["h"] / 2 - 2) if item["depth"] >= 3 else cy
            next_anchor_x = out_x + side * H_GAP_SUB
            for k in kids:
                kcy = ky + k["sub_h"] / 2
                in_y = (kcy + k["h"] / 2 - 2) if k["depth"] >= 3 else kcy
                self._curve(out_x, out_y, next_anchor_x, in_y, k["color"], 1.8 if item["depth"] == 1 else 1.4)
                self._draw_branch(k, next_anchor_x, ky, side)
                ky += k["sub_h"] + V_GAP_SUB
        self._draw_node(item, x, cy, side)

    def render(self) -> str:
        t = self.t
        rw, rh, rlines, rtag_w = self._measure_node(self.root, depth=0)
        root_item = {
            "raw": self.root,
            "depth": 0,
            "color": self.root.get("color") or t["mindRootFill"],
            "w": rw,
            "h": rh,
            "lines": rlines,
            "tag": str(self.root.get("tag", "") or ""),
            "tag_w": rtag_w,
        }

        raw_branches = self.root.get("children") or []
        branches = [
            self._build_branch(b, 1, self.palette[i % len(self.palette)])
            for i, b in enumerate(raw_branches)
        ]

        layout = self.m.get("layout")
        if layout not in ("both", "right"):
            layout = "both" if len(branches) >= 4 else "right"

        if layout == "both" and len(branches) >= 2:
            # 顺时针分组：前半放右侧、后半放左侧（保留编号阅读顺序，同时自动寻找高度最均衡的切分点）
            if any(b["raw"].get("side") in ("left", "right") for b in branches):
                right_bs = [b for b in branches if b["raw"].get("side") != "left"]
                left_bs = [b for b in branches if b["raw"].get("side") == "left"]
            else:
                hs = [b["sub_h"] for b in branches]
                best_k = min(range(1, len(branches)), key=lambda k: abs(sum(hs[:k]) - sum(hs[k:])))
                right_bs, left_bs = branches[:best_k], branches[best_k:]
        else:
            right_bs, left_bs = branches, []

        def stack_h(bs: list[dict]) -> float:
            return sum(b["sub_h"] for b in bs) + V_GAP_MAIN * max(len(bs) - 1, 0) if bs else 0.0

        left_w = (max(b["sub_w"] for b in left_bs) + H_GAP_ROOT) if left_bs else 0.0
        right_w = (max(b["sub_w"] for b in right_bs) + H_GAP_ROOT) if right_bs else 0.0
        total_w = left_w + rw + right_w
        total_h = max(rh, stack_h(left_bs), stack_h(right_bs))

        min_w = int(total_w + 2 * MARGIN_X)
        self.W = max(self.W, min_w) if self.m.get("canvas", {}).get("w") else max(980, min_w)
        offset_x = (self.W - total_w) / 2
        root_x = offset_x + left_w

        y = MARGIN_Y
        if self.m.get("title"):
            self.parts.append("<!-- 顶部标题 -->")
            self.rect(MARGIN_X, y, self.W - 2 * MARGIN_X, TITLE_H, t["titleFill"])
            self._draw_text(self.W / 2, y + TITLE_H / 2, [self.m["title"]], 16.5, t["text"], weight="bold")
            y += TITLE_H + TITLE_GAP

        root_cy = y + total_h / 2

        # 绘制右侧分支
        if right_bs:
            self.parts.append("<!-- 右侧分支 -->")
            rh_sum = stack_h(right_bs)
            by = root_cy - rh_sum / 2
            rx_anchor = root_x + rw + H_GAP_ROOT
            for b in right_bs:
                bcy = by + b["sub_h"] / 2
                self._curve(root_x + rw, root_cy, rx_anchor, bcy, b["color"], 2.4)
                self._draw_branch(b, rx_anchor, by, side=1)
                by += b["sub_h"] + V_GAP_MAIN

        # 绘制左侧分支
        if left_bs:
            self.parts.append("<!-- 左侧分支 -->")
            lh_sum = stack_h(left_bs)
            by = root_cy - lh_sum / 2
            lx_anchor = root_x - H_GAP_ROOT
            for b in left_bs:
                bcy = by + b["sub_h"] / 2
                self._curve(root_x, root_cy, lx_anchor, bcy, b["color"], 2.4)
                self._draw_branch(b, lx_anchor, by, side=-1)
                by += b["sub_h"] + V_GAP_MAIN

        # 最后绘制中心主题（压住曲线起点）
        self.parts.append("<!-- 中心主题 -->")
        self._draw_node(root_item, root_x, root_cy, side=1)

        return self.wrap_svg(int(y + total_h + MARGIN_Y))
