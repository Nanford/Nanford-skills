"""ProcessOn 风格业务流程泳道图渲染器（diagram: "swimlane"）。

支持：
- 顶部流程总标题栏 + 多角色纵向泳道表头（含可选“相关文档”列）
- 标准业务流程图元：起止胶囊(start/end)、业务步骤(process)、条件判断菱形(decision)、
  波浪底文档(document)、子流程(subflow)、数据/表单(data)
- 按 (lane, row) 网格精准排布（省略 row 时支持按拓扑关系自动分层）
- 智能正交折线与避障路由（直线、L 型折线、行间通道 Z 型折线、防节点穿越绕行）
- 几何拼接箭头（禁用 <marker>）+ 断线白底标注（如“是 / 否”）
"""
from __future__ import annotations

import math
import sys
from xml.sax.saxutils import escape

from core import BaseDiagram, lines_height, text_block, text_width, wrap

# ---------- 布局常量（与 references/swimlane.md 保持一致） ----------
MARGIN_X = 36
MARGIN_Y = 24
TITLE_H = 42          # 顶部流程总标题栏高度
LANE_HEADER_H = 38    # 泳道角色表头高度
TOP_PAD = 28          # 首行节点距表头留白
BOTTOM_PAD = 36       # 末行节点距底边留白
ROW_GAP = 40          # 行间通道高度（用于 Z 型折线与标注）
STROKE_W = 1.4        # 经典 ProcessOn 业务流程图描边粗细


class SwimlaneDiagram(BaseDiagram):
    def __init__(self, model: dict):
        super().__init__(model, default_width=1160, default_theme="processon-gray")
        self.lanes = self._resolve_lanes()
        if not self.lanes:
            raise ValueError("泳道图至少需要 1 个泳道（lanes）")
        self.lane_index = self._build_lane_index()
        self.raw_nodes = self._resolve_nodes()
        self.edges = list(model.get("edges") or model.get("connections") or [])
        self._auto_assign_rows()

    # --- 数据归一化 ---
    def _resolve_lanes(self) -> list[dict]:
        lanes = []
        for i, item in enumerate(self.m.get("lanes", [])):
            if isinstance(item, str):
                lanes.append({"id": item, "title": item, "weight": 1.0})
            else:
                title = item.get("title", item.get("name", f"角色{i + 1}"))
                lanes.append({
                    "id": item.get("id", title),
                    "title": title,
                    "weight": float(item.get("width", item.get("weight", 1.0))),
                    "fill": item.get("fill"),
                })
        return lanes

    def _build_lane_index(self) -> dict:
        idx = {}
        for i, lane in enumerate(self.lanes):
            idx[i] = i
            idx[lane["id"]] = i
            idx[lane["title"]] = i
        return idx

    def _resolve_lane_idx(self, ref) -> int:
        if ref in self.lane_index:
            return self.lane_index[ref]
        raise ValueError(f"未知泳道引用: {ref!r}，可用泳道：{[l['title'] for l in self.lanes]}")

    def _resolve_nodes(self) -> list[dict]:
        nodes = []
        for i, n in enumerate(self.m.get("nodes", [])):
            nid = n.get("id", f"n{i + 1}")
            li = self._resolve_lane_idx(n["lane"])
            nodes.append({
                "id": nid,
                "lane": li,
                "row": n.get("row"),
                "label": n.get("label", ""),
                "type": n.get("type", "process"),
                "variant": n.get("variant"),
                "fill": n.get("fill"),
                "width": n.get("width"),
                "height": n.get("height"),
            })
        return nodes

    def _auto_assign_rows(self):
        """若部分或全部节点未指定 row，按边拓扑顺序自动分配行号并避免同格冲突。"""
        if all(n["row"] is not None for n in self.raw_nodes):
            return
        by_id = {n["id"]: n for n in self.raw_nodes}
        preds: dict[str, list[str]] = {n["id"]: [] for n in self.raw_nodes}
        for e in self.edges:
            u, v = e.get("from"), e.get("to")
            if u in by_id and v in by_id and u != v:
                preds[v].append(u)

        used: set[tuple[int, int]] = set()
        for n in self.raw_nodes:
            if n["row"] is not None:
                n["row"] = int(n["row"])
                used.add((n["lane"], n["row"]))

        for n in self.raw_nodes:
            if n["row"] is not None:
                continue
            cand = 0
            for p in preds[n["id"]]:
                pr = by_id[p]["row"]
                if pr is not None:
                    # 同泳道向下递增，跨泳道优先同行或下一行
                    cand = max(cand, pr + (1 if by_id[p]["lane"] == n["lane"] else 0))
            while (n["lane"], cand) in used:
                cand += 1
            n["row"] = cand
            used.add((n["lane"], cand))

    # --- 节点尺寸与图元绘制 ---
    def _wrap_label(self, label: str, max_w: float, fs: float, max_lines: int = 3) -> list[str]:
        out: list[str] = []
        for para in str(label).split("\n"):
            out.extend(wrap(para, max_w, fs, max_lines=max_lines))
        return out[:max_lines]

    def _measure_node(self, n: dict, lane_w: float) -> tuple[float, float, list[str]]:
        t = n["type"]
        fs = 13.5
        base_w = min(124.0, max(92.0, lane_w - 64.0))
        if n.get("width"):
            base_w = float(n["width"])

        if t == "decision":
            w = float(n.get("width") or min(116.0, max(96.0, lane_w - 58.0)))
            lines = self._wrap_label(n["label"], w * 0.62, 13.0, max_lines=3)
            h = float(n.get("height") or max(74.0, lines_height(len(lines), 13.0) + 34.0))
            return w, h, lines

        if t in ("start", "end"):
            lines = self._wrap_label(n["label"], base_w - 28, fs, max_lines=2)
            h = float(n.get("height") or max(48.0, lines_height(len(lines), fs) + 22.0))
            return base_w, h, lines

        if t == "document":
            lines = self._wrap_label(n["label"], base_w - 18, fs, max_lines=3)
            h = float(n.get("height") or max(68.0, lines_height(len(lines), fs) + 30.0))
            return base_w, h, lines

        if t == "subflow":
            lines = self._wrap_label(n["label"], base_w - 30, fs, max_lines=3)
            h = float(n.get("height") or max(48.0, lines_height(len(lines), fs) + 20.0))
            return base_w, h, lines

        if t == "data":
            lines = self._wrap_label(n["label"], base_w - 28, fs, max_lines=3)
            h = float(n.get("height") or max(48.0, lines_height(len(lines), fs) + 20.0))
            return base_w, h, lines

        # process（默认业务步骤）
        lines = self._wrap_label(n["label"], base_w - 18, fs, max_lines=3)
        h = float(n.get("height") or max(48.0, lines_height(len(lines), fs) + 20.0))
        return base_w, h, lines

    def _node_fill(self, n: dict) -> str:
        if n.get("fill"):
            return n["fill"]
        if n.get("variant") == "highlight":
            return self.t["swimHighlightFill"]
        return self.t["nodeFill"]

    def _draw_node(self, n: dict, cx: float, cy: float, w: float, h: float, lines: list[str]) -> dict:
        x, y = cx - w / 2, cy - h / 2
        fill = self._node_fill(n)
        stroke = self.t["stroke"]
        da = ' stroke-dasharray="6 4"' if n.get("variant") == "external" else ""
        t = n["type"]
        weight = "bold" if n.get("variant") == "highlight" else None

        if t in ("start", "end"):
            rx = min(22.0, h / 2)
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
            wave = 10.0
            by = y + h - wave
            d = (
                f"M{x:.1f},{y:.1f} H{x + w:.1f} V{by:.1f} "
                f"Q{x + w * 0.75:.1f},{by - wave:.1f} {cx:.1f},{by:.1f} "
                f"Q{x + w * 0.25:.1f},{by + wave:.1f} {x:.1f},{by:.1f} Z"
            )
            self.parts.append(
                f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>'
            )
            self.parts.append(text_block(cx, y + (h - wave) / 2, lines, 13.5, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, by), "left": (x, cy), "right": (x + w, cy)}

        elif t == "subflow":
            self.parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>'
            )
            self.parts.append(
                f'<line x1="{x + 10:.1f}" y1="{y:.1f}" x2="{x + 10:.1f}" y2="{y + h:.1f}" stroke="{stroke}" stroke-width="{STROKE_W}"/>'
            )
            self.parts.append(
                f'<line x1="{x + w - 10:.1f}" y1="{y:.1f}" x2="{x + w - 10:.1f}" y2="{y + h:.1f}" stroke="{stroke}" stroke-width="{STROKE_W}"/>'
            )
            self.parts.append(text_block(cx, cy, lines, 13.5, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, y + h), "left": (x, cy), "right": (x + w, cy)}

        elif t == "data":
            sk = 11.0
            pts = f"{x + sk:.1f},{y:.1f} {x + w:.1f},{y:.1f} {x + w - sk:.1f},{y + h:.1f} {x:.1f},{y + h:.1f}"
            self.parts.append(
                f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>'
            )
            self.parts.append(text_block(cx, cy, lines, 13.5, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, y + h), "left": (x + sk / 2, cy), "right": (x + w - sk / 2, cy)}

        else:  # process
            self.parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>'
            )
            self.parts.append(text_block(cx, cy, lines, 13.5, weight=weight))
            ports = {"top": (cx, y), "bottom": (cx, y + h), "left": (x, cy), "right": (x + w, cy)}

        self.nodes[n["id"]] = (x, y, w, h)
        return {"cx": cx, "cy": cy, "x": x, "y": y, "w": w, "h": h, "ports": ports, "lane": n["lane"], "row": n["row"]}

    # --- 正交折线避障路由 ---
    def _route_edge(self, e: dict, geom: dict[str, dict], occupied: set[tuple[int, int]],
                    lane_bounds: list[tuple[float, float]], row_bounds: list[tuple[float, float]]) -> list[tuple[float, float]]:
        a, b = geom[e["from"]], geom[e["to"]]
        la, ra = a["lane"], a["row"]
        lb, rb = b["lane"], b["row"]

        def col_clear(lane: int, r1: int, r2: int, include_r2: bool = False) -> bool:
            step = 1 if r2 > r1 else -1
            end = r2 + step if include_r2 else r2
            return all((lane, r) not in occupied for r in range(r1 + step, end, step))

        def row_clear(row: int, l1: int, l2: int, include_l2: bool = False) -> bool:
            step = 1 if l2 > l1 else -1
            end = l2 + step if include_l2 else l2
            return all((l, row) not in occupied for l in range(l1 + step, end, step))

        def row_gutter(r_from: int, direction: int) -> float:
            """返回 r_from 朝 direction (+1下 / -1上) 一侧的水平通道中心 y。"""
            if direction > 0:
                if r_from + 1 < len(row_bounds):
                    return (row_bounds[r_from][1] + row_bounds[r_from + 1][0]) / 2
                return row_bounds[r_from][1] + ROW_GAP / 2
            if r_from - 1 >= 0:
                return (row_bounds[r_from - 1][1] + row_bounds[r_from][0]) / 2
            return row_bounds[r_from][0] - TOP_PAD / 2

        # 显式指定出口/入口端口
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
                gx = lane_bounds[la][1] - 14 if fp == "right" else lane_bounds[la][0] + 14
                return [p0, (gx, p0[1]), (gx, p1[1]), p1]

        # 情况 1：同泳道
        if la == lb:
            if ra == rb:
                return [a["ports"]["right"], b["ports"]["right"]]
            if col_clear(la, ra, rb):
                return [a["ports"]["bottom"], b["ports"]["top"]] if rb > ra else [a["ports"]["top"], b["ports"]["bottom"]]
            # 中间有节点遮挡 -> 沿本泳道右侧边缘绕行
            gx = lane_bounds[la][1] - 14
            return [a["ports"]["right"], (gx, a["cy"]), (gx, b["cy"]), b["ports"]["right"]]

        # 情况 2：同行不同泳道
        if ra == rb:
            if row_clear(ra, la, lb):
                return [a["ports"]["right"], b["ports"]["left"]] if lb > la else [a["ports"]["left"], b["ports"]["right"]]
            # 中间有节点遮挡 -> 走本行下方水平通道
            gy = row_gutter(ra, 1)
            return [a["ports"]["bottom"], (a["cx"], gy), (b["cx"], gy), b["ports"]["bottom"]]

        # 情况 3：跨泳道且跨行
        side_in = "left" if lb > la else "right"
        side_out = "right" if lb > la else "left"
        v_out = "bottom" if rb > ra else "top"
        v_in = "top" if rb > ra else "bottom"
        v_dir = 1 if rb > ra else -1

        # 优先 1：先竖后横 L 型折线（ProcessOn 泳道图最经典走线）
        if col_clear(la, ra, rb, include_r2=True) and row_clear(rb, la, lb):
            p0, p1 = a["ports"][v_out], b["ports"][side_in]
            return [p0, (p0[0], p1[1]), p1]

        # 优先 2：相邻行 Z 型折线（沿两行之间的水平通道穿行，如“修改合同 -> 递交合同”）
        if abs(rb - ra) == 1:
            gy = row_gutter(ra, v_dir)
            p0, p1 = a["ports"][v_out], b["ports"][v_in]
            return [p0, (p0[0], gy), (p1[0], gy), p1]

        # 优先 3：先横后竖 L 型折线
        if row_clear(ra, la, lb, include_l2=True) and col_clear(lb, ra, rb):
            p0, p1 = a["ports"][side_out], b["ports"][v_in]
            return [p0, (p1[0], p0[1]), p1]

        # 优先 4：先入行间通道再垂直进目标（目标列畅通时）
        if col_clear(lb, ra, rb):
            gy = row_gutter(ra, v_dir)
            p0, p1 = a["ports"][v_out], b["ports"][v_in]
            return [p0, (p0[0], gy), (p1[0], gy), p1]

        # 兜底：走起点行间通道 -> 目标泳道侧边空白走廊 -> 目标侧面进入（永不穿越节点）
        gy = row_gutter(ra, v_dir)
        gx = lane_bounds[lb][0] + 14 if lb > la else lane_bounds[lb][1] - 14
        p0, p1 = a["ports"][v_out], b["ports"][side_in]
        return [p0, (p0[0], gy), (gx, gy), (gx, p1[1]), p1]

    def _draw_edge(self, e: dict, pts: list[tuple[float, float]]):
        # 去除连续重合点
        clean: list[tuple[float, float]] = [pts[0]]
        for p in pts[1:]:
            if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 0.5:
                clean.append(p)
        if len(clean) < 2:
            return

        color = e.get("color") or self.t["lineColor"]
        da = ' stroke-dasharray="5 4"' if e.get("dashed") else ""

        # 末段回缩 8px，让线身止于几何箭头底边
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
        # 几何拼接箭头（尖端位于 p_end，禁用 <marker>）
        self.parts.append(
            f'<g class="flow-arrow" transform="translate({p_end[0]:.1f},{p_end[1]:.1f}) rotate({angle:.1f})">'
            f'<polygon points="0,0 -9,-4.2 -9,4.2" fill="{color}"/></g>'
        )

        # 标注文字（放在最长线段中点，带白底断线效果）
        label = e.get("label")
        if label:
            segs = []
            for i in range(len(clean) - 1):
                x1, y1 = clean[i]
                x2, y2 = clean[i + 1]
                length = math.hypot(x2 - x1, y2 - y1)
                is_horiz = abs(y2 - y1) < 1.0
                # 在 L 折线上稍微偏好水平段放“是/否”文字，更符合阅读习惯
                score = length * (1.15 if is_horiz else 1.0)
                segs.append((score, x1, y1, x2, y2))
            _, x1, y1, x2, y2 = max(segs, key=lambda item: item[0])
            tpos = float(e.get("labelPos", 0.5))
            lx = x1 + (x2 - x1) * tpos
            ly = y1 + (y2 - y1) * tpos
            tw = text_width(label, 12.5) + 8
            self.parts.append(
                f'<rect x="{lx - tw / 2:.1f}" y="{ly - 9:.1f}" width="{tw:.1f}" height="18" fill="{self.t["background"]}"/>'
            )
            self.parts.append(text_block(lx, ly, [label], 12.5))

    # --- 总装 ---
    def render(self) -> str:
        t, W = self.t, self.W
        pool_x0 = MARGIN_X
        pool_w = W - 2 * MARGIN_X

        # 计算各泳道水平区间
        total_wt = sum(l["weight"] for l in self.lanes)
        lane_bounds: list[tuple[float, float]] = []
        lx = pool_x0
        for l in self.lanes:
            lw = pool_w * (l["weight"] / total_wt)
            lane_bounds.append((lx, lx + lw))
            lx += lw

        # 预测量所有节点尺寸，计算每行高度
        max_row = max((n["row"] for n in self.raw_nodes), default=0)
        measured: dict[str, tuple[float, float, list[str]]] = {}
        row_hs = [52.0] * (max_row + 1)
        for n in self.raw_nodes:
            lw = lane_bounds[n["lane"]][1] - lane_bounds[n["lane"]][0]
            w, h, lines = self._measure_node(n, lw)
            measured[n["id"]] = (w, h, lines)
            row_hs[n["row"]] = max(row_hs[n["row"]], h)

        # 顶部标题与泳道表头坐标
        y = MARGIN_Y
        has_title = bool(self.m.get("title"))
        pool_y0 = y
        title_h = TITLE_H if has_title else 0
        header_y = pool_y0 + title_h
        body_y = header_y + LANE_HEADER_H

        # 计算各行垂直区间
        row_gap = float(self.m.get("rowGap", ROW_GAP))
        row_bounds: list[tuple[float, float]] = []
        ry = body_y + TOP_PAD
        for rh in row_hs:
            row_bounds.append((ry, ry + rh))
            ry += rh + row_gap
        body_bottom = (row_bounds[-1][1] if row_bounds else body_y + 120) + BOTTOM_PAD
        pool_h = body_bottom - pool_y0

        # 1. 泳道池外框与背景
        self.parts.append("<!-- 泳道框架 -->")
        self.parts.append(
            f'<rect x="{pool_x0:.1f}" y="{pool_y0:.1f}" width="{pool_w:.1f}" height="{pool_h:.1f}" '
            f'fill="{t["background"]}" stroke="{t["stroke"]}" stroke-width="{STROKE_W}"/>'
        )

        # 2. 顶部流程总标题栏
        if has_title:
            self.parts.append(
                f'<rect x="{pool_x0:.1f}" y="{pool_y0:.1f}" width="{pool_w:.1f}" height="{TITLE_H}" '
                f'fill="{t["swimTitleFill"]}" stroke="{t["stroke"]}" stroke-width="{STROKE_W}"/>'
            )
            align = self.m.get("titleAlign", "left")
            if align == "center":
                self.parts.append(text_block(W / 2, pool_y0 + TITLE_H / 2, [self.m["title"]], 16, weight="bold"))
            else:
                self.parts.append(
                    text_block(pool_x0 + 16, pool_y0 + TITLE_H / 2, [self.m["title"]], 16, weight="bold", anchor="start")
                )

        # 3. 泳道角色表头 + 纵向泳道分隔线
        self.parts.append("<!-- 泳道表头与分隔线 -->")
        for i, (lane, (x0, x1)) in enumerate(zip(self.lanes, lane_bounds)):
            hfill = lane.get("fill") or t["swimLaneHeaderFill"]
            self.parts.append(
                f'<rect x="{x0:.1f}" y="{header_y:.1f}" width="{x1 - x0:.1f}" height="{LANE_HEADER_H}" '
                f'fill="{hfill}" stroke="{t["stroke"]}" stroke-width="{STROKE_W}"/>'
            )
            self.parts.append(text_block((x0 + x1) / 2, header_y + LANE_HEADER_H / 2, [lane["title"]], 14, weight="bold"))
            if i > 0:
                self.parts.append(
                    f'<line x1="{x0:.1f}" y1="{header_y:.1f}" x2="{x0:.1f}" y2="{body_bottom:.1f}" '
                    f'stroke="{t["stroke"]}" stroke-width="{STROKE_W}"/>'
                )

        # 4. 绘制节点
        self.parts.append("<!-- 业务流程节点 -->")
        geom: dict[str, dict] = {}
        occupied: set[tuple[int, int]] = set()
        for n in self.raw_nodes:
            x0, x1 = lane_bounds[n["lane"]]
            y0, y1 = row_bounds[n["row"]]
            w, h, lines = measured[n["id"]]
            geom[n["id"]] = self._draw_node(n, (x0 + x1) / 2, (y0 + y1) / 2, w, h, lines)
            occupied.add((n["lane"], n["row"]))

        # 5. 绘制正交连接线与箭头
        self.parts.append("<!-- 流程连接线 -->")
        for e in self.edges:
            if e.get("from") not in geom or e.get("to") not in geom:
                print(f"[warn] 流程连线端点不存在: {e}", file=sys.stderr)
                continue
            pts = self._route_edge(e, geom, occupied, lane_bounds, row_bounds)
            self._draw_edge(e, pts)

        return self.wrap_svg(int(body_bottom + MARGIN_Y))
