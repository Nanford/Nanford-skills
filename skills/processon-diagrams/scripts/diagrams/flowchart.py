"""ProcessOn 风格普通流程图渲染器（diagram: "flowchart"）。

支持：
- 纵向（TB，默认）与横向（LR）流向
- 显式 (col, row) 网格精准排布，或省略坐标时的环安全拓扑自动分层排布
- 8 种标准图元：start / end / process / decision / data / subflow / document / database
- 可选虚线分组框（groups）
- 智能避障正交折线（直线、L 型、行间通道 Z 型、回退环侧边绕行）+ 几何拼接箭头
"""
from __future__ import annotations

import math
import sys
from xml.sax.saxutils import escape

from core import BaseDiagram, lines_height, text_block, text_width, wrap

MARGIN_X = 40
MARGIN_Y = 24
TITLE_H = 44
TITLE_GAP = 22
COL_GAP = 64
ROW_GAP = 46
STROKE_W = 1.4


class FlowchartDiagram(BaseDiagram):
    def __init__(self, model: dict):
        super().__init__(model, default_width=1100)
        self.direction = str(model.get("direction", "TB")).upper()
        if self.direction not in ("TB", "LR"):
            self.direction = "TB"
        self.raw_nodes = self._resolve_nodes()
        if not self.raw_nodes:
            raise ValueError("流程图至少需要 1 个节点（nodes）")
        self.edges = list(model.get("edges") or model.get("connections") or [])
        self._auto_layout()

    def _resolve_nodes(self) -> list[dict]:
        out = []
        for i, n in enumerate(self.m.get("nodes", [])):
            out.append({
                "id": n.get("id", f"n{i + 1}"),
                "label": n.get("label", ""),
                "type": n.get("type", "process"),
                "row": n.get("row"),
                "col": n.get("col"),
                "variant": n.get("variant"),
                "fill": n.get("fill"),
                "width": n.get("width"),
                "height": n.get("height"),
            })
        return out

    def _auto_layout(self):
        """未显式指定 (col, row) 时，使用环安全拓扑分层 + 重心排序自动分配网格坐标。"""
        if all(n["row"] is not None and n["col"] is not None for n in self.raw_nodes):
            for n in self.raw_nodes:
                n["row"] = int(n["row"])
                n["col"] = int(n["col"])
            return

        by_id = {n["id"]: n for n in self.raw_nodes}
        order_idx = {n["id"]: i for i, n in enumerate(self.raw_nodes)}
        adj: dict[str, list[str]] = {n["id"]: [] for n in self.raw_nodes}
        for e in self.edges:
            u, v = e.get("from"), e.get("to")
            if u in by_id and v in by_id and u != v:
                adj[u].append(v)

        # 1. DFS 检测回边（避免循环导致分层死循环）
        state: dict[str, int] = {nid: 0 for nid in by_id}
        back_edges: set[tuple[str, str]] = set()

        def dfs(u: str):
            state[u] = 1
            for v in adj[u]:
                if state[v] == 1:
                    back_edges.add((u, v))
                elif state[v] == 0:
                    dfs(v)
            state[u] = 2

        for n in self.raw_nodes:
            if state[n["id"]] == 0:
                dfs(n["id"])

        # 2. 前向 DAG 最长路径分层（row）
        fwd_preds: dict[str, list[str]] = {nid: [] for nid in by_id}
        fwd_succs: dict[str, list[str]] = {nid: [] for nid in by_id}
        for u, vs in adj.items():
            for v in vs:
                if (u, v) not in back_edges:
                    fwd_succs[u].append(v)
                    fwd_preds[v].append(u)

        layer: dict[str, int] = {}
        for n in self.raw_nodes:
            if n["row"] is not None:
                layer[n["id"]] = int(n["row"])

        # 迭代松弛求最长前向深度
        for nid in by_id:
            layer.setdefault(nid, 0)
        for _ in range(len(self.raw_nodes) + 1):
            changed = False
            for u, vs in fwd_succs.items():
                for v in vs:
                    if by_id[v]["row"] is None and layer[v] < layer[u] + 1:
                        layer[v] = layer[u] + 1
                        changed = True
            if not changed:
                break

        for n in self.raw_nodes:
            n["row"] = layer[n["id"]]

        # 3. 每层内按父节点重心排序并居中分配 col
        by_row: dict[int, list[dict]] = {}
        for n in self.raw_nodes:
            by_row.setdefault(n["row"], []).append(n)

        max_cols_in_row = max((len(ns) for ns in by_row.values()), default=1)
        assigned_col: dict[str, int] = {}
        for r in sorted(by_row):
            ns = by_row[r]
            used = {int(n["col"]) for n in ns if n["col"] is not None}

            def sort_key(n: dict):
                ps = [assigned_col[p] for p in fwd_preds[n["id"]] if p in assigned_col]
                bary = sum(ps) / len(ps) if ps else order_idx[n["id"]]
                return (bary, order_idx[n["id"]])

            auto_ns = sorted([n for n in ns if n["col"] is None], key=sort_key)
            # 居中对齐槽位
            offset = (max_cols_in_row - len(ns)) // 2
            slot = offset
            for n in auto_ns:
                while slot in used:
                    slot += 1
                n["col"] = slot
                used.add(slot)
            for n in ns:
                n["col"] = int(n["col"])
                assigned_col[n["id"]] = n["col"]

        # 归一化最小列/行从 0 开始
        min_c = min(n["col"] for n in self.raw_nodes)
        min_r = min(n["row"] for n in self.raw_nodes)
        for n in self.raw_nodes:
            n["col"] -= min_c
            n["row"] -= min_r

    # --- 节点测量与绘制 ---
    def _wrap_label(self, label: str, max_w: float, fs: float, max_lines: int = 3) -> list[str]:
        out: list[str] = []
        for para in str(label).split("\n"):
            out.extend(wrap(para, max_w, fs, max_lines=max_lines))
        return out[:max_lines]

    def _measure_node(self, n: dict) -> tuple[float, float, list[str]]:
        t = n["type"]
        fs = 13.5
        if t == "decision":
            w = float(n.get("width") or 132.0)
            lines = self._wrap_label(n["label"], w * 0.62, 13.0, max_lines=3)
            h = float(n.get("height") or max(76.0, lines_height(len(lines), 13.0) + 34.0))
            return w, h, lines

        w = float(n.get("width") or 146.0)
        if t in ("start", "end"):
            w = float(n.get("width") or 132.0)
            lines = self._wrap_label(n["label"], w - 28, fs, max_lines=2)
            h = float(n.get("height") or max(46.0, lines_height(len(lines), fs) + 20.0))
            return w, h, lines

        if t == "document":
            lines = self._wrap_label(n["label"], w - 20, fs, max_lines=3)
            h = float(n.get("height") or max(64.0, lines_height(len(lines), fs) + 28.0))
            return w, h, lines

        if t == "database":
            lines = self._wrap_label(n["label"], w - 20, fs, max_lines=3)
            h = float(n.get("height") or max(66.0, lines_height(len(lines), fs) + 32.0))
            return w, h, lines

        if t in ("subflow", "data"):
            lines = self._wrap_label(n["label"], w - 30, fs, max_lines=3)
            h = float(n.get("height") or max(48.0, lines_height(len(lines), fs) + 20.0))
            return w, h, lines

        lines = self._wrap_label(n["label"], w - 20, fs, max_lines=3)
        h = float(n.get("height") or max(48.0, lines_height(len(lines), fs) + 20.0))
        return w, h, lines

    def _node_fill(self, n: dict) -> str:
        if n.get("fill"):
            return n["fill"]
        if n.get("variant") == "highlight":
            return self.t["cardHeaderFill"]
        if n["type"] in ("start", "end"):
            return self.t["flowStartFill"]
        if n["type"] == "decision":
            return self.t["flowDecisionFill"]
        return self.t["nodeFill"]

    def _draw_node(self, n: dict, cx: float, cy: float, w: float, h: float, lines: list[str]) -> dict:
        x, y = cx - w / 2, cy - h / 2
        fill = self._node_fill(n)
        stroke = self.t["stroke"]
        da = ' stroke-dasharray="6 4"' if n.get("variant") == "external" else ""
        t = n["type"]
        weight = "bold" if n.get("variant") == "highlight" or t in ("start", "end") else None

        if t in ("start", "end"):
            rx = h / 2
            self.parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>'
            )
            self.parts.append(text_block(cx, cy, lines, 13.5, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, y + h), "left": (x, cy), "right": (x + w, cy)}

        elif t == "decision":
            pts = f"{cx:.1f},{y:.1f} {x + w:.1f},{cy:.1f} {cx:.1f},{y + h:.1f} {x:.1f},{cy:.1f}"
            self.parts.append(
                f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>'
            )
            self.parts.append(text_block(cx, cy, lines, 13.0, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, y + h), "left": (x, cy), "right": (x + w, cy)}

        elif t == "document":
            wave = 9.0
            by = y + h - wave
            d = (
                f"M{x:.1f},{y:.1f} H{x + w:.1f} V{by:.1f} "
                f"Q{x + w * 0.75:.1f},{by - wave:.1f} {cx:.1f},{by:.1f} "
                f"Q{x + w * 0.25:.1f},{by + wave:.1f} {x:.1f},{by:.1f} Z"
            )
            self.parts.append(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>')
            self.parts.append(text_block(cx, y + (h - wave) / 2, lines, 13.5, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, by), "left": (x, cy), "right": (x + w, cy)}

        elif t == "database":
            ry = 9.0
            rx = w / 2
            d_body = (
                f"M{x:.1f},{y + ry:.1f} V{y + h - ry:.1f} "
                f"A{rx:.1f},{ry:.1f} 0 0 0 {x + w:.1f},{y + h - ry:.1f} V{y + ry:.1f} Z"
            )
            self.parts.append(f'<path d="{d_body}" fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>')
            self.parts.append(
                f'<ellipse cx="{cx:.1f}" cy="{y + ry:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>'
            )
            self.parts.append(text_block(cx, cy + ry * 0.4, lines, 13.5, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, y + h), "left": (x, cy), "right": (x + w, cy)}

        elif t == "subflow":
            self.parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>'
            )
            self.parts.append(f'<line x1="{x + 10:.1f}" y1="{y:.1f}" x2="{x + 10:.1f}" y2="{y + h:.1f}" stroke="{stroke}" stroke-width="{STROKE_W}"/>')
            self.parts.append(f'<line x1="{x + w - 10:.1f}" y1="{y:.1f}" x2="{x + w - 10:.1f}" y2="{y + h:.1f}" stroke="{stroke}" stroke-width="{STROKE_W}"/>')
            self.parts.append(text_block(cx, cy, lines, 13.5, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, y + h), "left": (x, cy), "right": (x + w, cy)}

        elif t == "data":
            sk = 12.0
            pts = f"{x + sk:.1f},{y:.1f} {x + w:.1f},{y:.1f} {x + w - sk:.1f},{y + h:.1f} {x:.1f},{y + h:.1f}"
            self.parts.append(f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>')
            self.parts.append(text_block(cx, cy, lines, 13.5, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, y + h), "left": (x + sk / 2, cy), "right": (x + w - sk / 2, cy)}

        else:  # process
            self.parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>'
            )
            self.parts.append(text_block(cx, cy, lines, 13.5, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, y + h), "left": (x, cy), "right": (x + w, cy)}

        self.nodes[n["id"]] = (x, y, w, h)
        return {"cx": cx, "cy": cy, "x": x, "y": y, "w": w, "h": h, "ports": ports, "gx": n["gx"], "gy": n["gy"]}

    # --- 正交避障路由 ---
    def _route_edge(self, e: dict, geom: dict[str, dict], occupied: set[tuple[int, int]],
                    col_bounds: list[tuple[float, float]], row_bounds: list[tuple[float, float]]) -> list[tuple[float, float]]:
        a, b = geom[e["from"]], geom[e["to"]]
        ca, ra = a["gx"], a["gy"]
        cb, rb = b["gx"], b["gy"]

        def col_clear(c: int, r1: int, r2: int, include_r2: bool = False) -> bool:
            step = 1 if r2 > r1 else -1
            end = r2 + step if include_r2 else r2
            return all((c, r) not in occupied for r in range(r1 + step, end, step))

        def row_clear(r: int, c1: int, c2: int, include_c2: bool = False) -> bool:
            step = 1 if c2 > c1 else -1
            end = c2 + step if include_c2 else c2
            return all((c, r) not in occupied for c in range(c1 + step, end, step))

        def row_gutter(r_from: int, direction: int) -> float:
            if direction > 0:
                if r_from + 1 < len(row_bounds):
                    return (row_bounds[r_from][1] + row_bounds[r_from + 1][0]) / 2
                return row_bounds[r_from][1] + ROW_GAP / 2
            if r_from - 1 >= 0:
                return (row_bounds[r_from - 1][1] + row_bounds[r_from][0]) / 2
            return row_bounds[r_from][0] - ROW_GAP / 2

        def col_gutter(c_from: int, direction: int) -> float:
            if direction > 0:
                if c_from + 1 < len(col_bounds):
                    return (col_bounds[c_from][1] + col_bounds[c_from + 1][0]) / 2
                return col_bounds[c_from][1] + COL_GAP / 2
            if c_from - 1 >= 0:
                return (col_bounds[c_from - 1][1] + col_bounds[c_from][0]) / 2
            return col_bounds[c_from][0] - COL_GAP / 2

        fp, tp = e.get("fromPort"), e.get("toPort")
        if fp and tp:
            p0, p1 = a["ports"][fp], b["ports"][tp]
            if fp in ("top", "bottom") and tp in ("left", "right"):
                return [p0, (p0[0], p1[1]), p1]
            if fp in ("left", "right") and tp in ("top", "bottom"):
                return [p0, (p1[0], p0[1]), p1]
            if fp in ("top", "bottom") and tp in ("top", "bottom"):
                if abs(p0[0] - p1[0]) < 1:
                    return [p0, p1]
                gy = row_gutter(ra, 1 if fp == "bottom" else -1)
                return [p0, (p0[0], gy), (p1[0], gy), p1]
            if fp in ("left", "right") and tp in ("left", "right"):
                if abs(p0[1] - p1[1]) < 1:
                    return [p0, p1]
                gx = col_gutter(ca, 1 if fp == "right" else -1)
                return [p0, (gx, p0[1]), (gx, p1[1]), p1]

        # 同列
        if ca == cb:
            if ra == rb:
                return [a["ports"]["right"], b["ports"]["right"]]
            if col_clear(ca, ra, rb):
                return [a["ports"]["bottom"], b["ports"]["top"]] if rb > ra else [a["ports"]["top"], b["ports"]["bottom"]]
            # 回退/跨越同列中间节点 -> 从右侧空白列通道绕行
            gx = col_gutter(ca, 1)
            return [a["ports"]["right"], (gx, a["cy"]), (gx, b["cy"]), b["ports"]["right"]]

        # 同行
        if ra == rb:
            if row_clear(ra, ca, cb):
                return [a["ports"]["right"], b["ports"]["left"]] if cb > ca else [a["ports"]["left"], b["ports"]["right"]]
            gy = row_gutter(ra, 1)
            return [a["ports"]["bottom"], (a["cx"], gy), (b["cx"], gy), b["ports"]["bottom"]]

        # 跨列且跨行
        side_in = "left" if cb > ca else "right"
        side_out = "right" if cb > ca else "left"
        v_out = "bottom" if rb > ra else "top"
        v_in = "top" if rb > ra else "bottom"
        v_dir = 1 if rb > ra else -1
        h_dir = 1 if cb > ca else -1

        if self.direction == "TB":
            # 纵向流程图：先横后竖（从判断菱形左右分支下到目标顶部）或先竖后横
            if row_clear(ra, ca, cb, include_c2=True) and col_clear(cb, ra, rb):
                p0, p1 = a["ports"][side_out], b["ports"][v_in]
                return [p0, (p1[0], p0[1]), p1]
            if col_clear(ca, ra, rb, include_r2=True) and row_clear(rb, ca, cb):
                p0, p1 = a["ports"][v_out], b["ports"][side_in]
                return [p0, (p0[0], p1[1]), p1]
            if abs(rb - ra) == 1:
                gy = row_gutter(ra, v_dir)
                p0, p1 = a["ports"][v_out], b["ports"][v_in]
                return [p0, (p0[0], gy), (p1[0], gy), p1]
            gy = row_gutter(ra, v_dir)
            if col_clear(cb, ra, rb):
                p0, p1 = a["ports"][v_out], b["ports"][v_in]
                return [p0, (p0[0], gy), (p1[0], gy), p1]
            gx = col_gutter(cb, -h_dir)
            p0, p1 = a["ports"][v_out], b["ports"][side_in]
            return [p0, (p0[0], gy), (gx, gy), (gx, p1[1]), p1]
        else:
            # 横向流程图：优先先竖后横或先横后竖
            if col_clear(ca, ra, rb, include_r2=True) and row_clear(rb, ca, cb):
                p0, p1 = a["ports"][v_out], b["ports"][side_in]
                return [p0, (p0[0], p1[1]), p1]
            if row_clear(ra, ca, cb, include_c2=True) and col_clear(cb, ra, rb):
                p0, p1 = a["ports"][side_out], b["ports"][v_in]
                return [p0, (p1[0], p0[1]), p1]
            gx = col_gutter(ca, h_dir)
            p0, p1 = a["ports"][side_out], b["ports"][side_in]
            return [p0, (gx, p0[1]), (gx, p1[1]), p1]

    def _draw_edge(self, e: dict, pts: list[tuple[float, float]]):
        clean: list[tuple[float, float]] = [pts[0]]
        for p in pts[1:]:
            if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 0.5:
                clean.append(p)
        if len(clean) < 2:
            return
        color = e.get("color") or self.t["lineColor"]
        da = ' stroke-dasharray="5 4"' if e.get("dashed") else ""
        p_prev, p_end = clean[-2], clean[-1]
        dx, dy = p_end[0] - p_prev[0], p_end[1] - p_prev[1]
        seg_len = math.hypot(dx, dy)
        angle = math.degrees(math.atan2(dy, dx))
        draw_pts = list(clean)
        if seg_len > 9:
            ratio = (seg_len - 8.0) / seg_len
            draw_pts[-1] = (p_prev[0] + dx * ratio, p_prev[1] + dy * ratio)

        d = f"M{draw_pts[0][0]:.1f},{draw_pts[0][1]:.1f} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in draw_pts[1:])
        self.parts.append(f'<path d="{d}" stroke="{color}" stroke-width="1.35" fill="none"{da}/>')
        self.parts.append(
            f'<g class="flow-arrow" transform="translate({p_end[0]:.1f},{p_end[1]:.1f}) rotate({angle:.1f})">'
            f'<polygon points="0,0 -9,-4.2 -9,4.2" fill="{color}"/></g>'
        )

        label = e.get("label")
        if label:
            segs = []
            for i in range(len(clean) - 1):
                x1, y1 = clean[i]
                x2, y2 = clean[i + 1]
                length = math.hypot(x2 - x1, y2 - y1)
                is_horiz = abs(y2 - y1) < 1.0
                segs.append((length * (1.15 if is_horiz else 1.0), x1, y1, x2, y2))
            _, x1, y1, x2, y2 = max(segs, key=lambda item: item[0])
            tpos = float(e.get("labelPos", 0.5))
            lx = x1 + (x2 - x1) * tpos
            ly = y1 + (y2 - y1) * tpos
            tw = text_width(label, 12.5) + 8
            self.parts.append(
                f'<rect x="{lx - tw / 2:.1f}" y="{ly - 9:.1f}" width="{tw:.1f}" height="18" fill="{self.t["background"]}"/>'
            )
            self.parts.append(text_block(lx, ly, [label], 12.5))

    def render(self) -> str:
        t = self.t
        # 根据方向映射网格坐标 (gx, gy)
        for n in self.raw_nodes:
            if self.direction == "LR":
                n["gx"], n["gy"] = n["row"], n["col"]
            else:
                n["gx"], n["gy"] = n["col"], n["row"]

        max_gx = max(n["gx"] for n in self.raw_nodes)
        max_gy = max(n["gy"] for n in self.raw_nodes)
        measured: dict[str, tuple[float, float, list[str]]] = {}
        col_ws = [132.0] * (max_gx + 1)
        row_hs = [48.0] * (max_gy + 1)
        for n in self.raw_nodes:
            w, h, lines = self._measure_node(n)
            measured[n["id"]] = (w, h, lines)
            col_ws[n["gx"]] = max(col_ws[n["gx"]], w)
            row_hs[n["gy"]] = max(row_hs[n["gy"]], h)

        col_gap = float(self.m.get("colGap", COL_GAP))
        row_gap = float(self.m.get("rowGap", ROW_GAP))
        content_w = sum(col_ws) + col_gap * max(len(col_ws) - 1, 0)
        # 确保画布宽度能容纳全部列及左右留白（含可能的回退通道空间）
        min_w = int(content_w + 2 * MARGIN_X + 60)
        self.W = max(self.W, min_w) if self.m.get("canvas", {}).get("w") else max(920, min_w)
        start_x = (self.W - content_w) / 2

        col_bounds: list[tuple[float, float]] = []
        cx_cursor = start_x
        for cw in col_ws:
            col_bounds.append((cx_cursor, cx_cursor + cw))
            cx_cursor += cw + col_gap

        y = MARGIN_Y
        if self.m.get("title"):
            self.parts.append("<!-- 顶部标题 -->")
            self.rect(MARGIN_X, y, self.W - 2 * MARGIN_X, TITLE_H, t["titleFill"])
            self.parts.append(text_block(self.W / 2, y + TITLE_H / 2, [self.m["title"]], 17, weight="bold"))
            y += TITLE_H + TITLE_GAP

        # 给顶部可能存在的分组标题留一点空间
        if self.m.get("groups"):
            y += 14

        row_bounds: list[tuple[float, float]] = []
        ry_cursor = y
        for rh in row_hs:
            row_bounds.append((ry_cursor, ry_cursor + rh))
            ry_cursor += rh + row_gap

        # 预计算节点几何位置以便先画背景分组框
        centers: dict[str, tuple[float, float]] = {}
        for n in self.raw_nodes:
            x0, x1 = col_bounds[n["gx"]]
            y0, y1 = row_bounds[n["gy"]]
            centers[n["id"]] = ((x0 + x1) / 2, (y0 + y1) / 2)

        # 1. 可选虚线分组框（底层）
        if self.m.get("groups"):
            self.parts.append("<!-- 流程分组框 -->")
            for g in self.m["groups"]:
                ids = [nid for nid in g.get("nodes", []) if nid in centers]
                if not ids:
                    continue
                xs0 = [centers[nid][0] - measured[nid][0] / 2 for nid in ids]
                xs1 = [centers[nid][0] + measured[nid][0] / 2 for nid in ids]
                ys0 = [centers[nid][1] - measured[nid][1] / 2 for nid in ids]
                ys1 = [centers[nid][1] + measured[nid][1] / 2 for nid in ids]
                pad_x, pad_top, pad_bot = 22, 30, 18
                gx0, gy0 = min(xs0) - pad_x, min(ys0) - pad_top
                gw, gh = max(xs1) - min(xs0) + 2 * pad_x, max(ys1) - min(ys0) + pad_top + pad_bot
                gfill = g.get("fill") or t["bannerFill"]
                self.rect(gx0, gy0, gw, gh, gfill, rx=6, dashed=True)
                if g.get("title"):
                    self.parts.append(text_block(gx0 + 12, gy0 + 16, [g["title"]], 13, weight="bold", anchor="start"))

        # 2. 绘制节点
        self.parts.append("<!-- 流程节点 -->")
        geom: dict[str, dict] = {}
        occupied: set[tuple[int, int]] = set()
        for n in self.raw_nodes:
            cx, cy = centers[n["id"]]
            w, h, lines = measured[n["id"]]
            geom[n["id"]] = self._draw_node(n, cx, cy, w, h, lines)
            occupied.add((n["gx"], n["gy"]))

        # 3. 绘制连接线
        self.parts.append("<!-- 流程连线 -->")
        for e in self.edges:
            if e.get("from") not in geom or e.get("to") not in geom:
                print(f"[warn] 流程连线端点不存在: {e}", file=sys.stderr)
                continue
            pts = self._route_edge(e, geom, occupied, col_bounds, row_bounds)
            self._draw_edge(e, pts)

        bottom_y = (row_bounds[-1][1] if row_bounds else y + 100) + 32
        return self.wrap_svg(int(bottom_y + MARGIN_Y))
