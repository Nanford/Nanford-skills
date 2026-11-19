"""ProcessOn 风格时序图渲染器（diagram: "sequence"）。

支持：
- 顶部（及可选底部镜像）参与者：普通系统(participant)、角色火柴人(actor)、数据库圆柱(database)
- 同步调用(sync)、虚线返回(reply)、异步消息(async)、自调用(self)与自动编号(autonumber)
- 生命线与激活条（显式 activate/deactivate 或自动高亮调用区间）
- 组合片段框（alt / else / opt / loop / par，带左上角五边形标签与嵌套支持）
- 折角便签注释（note：left / right / over）
"""
from __future__ import annotations

import sys
from xml.sax.saxutils import escape

from core import BaseDiagram, lines_height, text_block, text_width, wrap

MARGIN_X = 44
MARGIN_Y = 24
TITLE_H = 44
TITLE_GAP = 18
ACTOR_H = 48
ACTOR_MIN_W = 110
STEP_H = 44
SELF_H = 54
FRAG_HEADER_H = 28
FRAG_PAD_BOTTOM = 12
ACT_W = 12
STROKE_W = 1.3


class SequenceDiagram(BaseDiagram):
    def __init__(self, model: dict):
        super().__init__(model, default_width=1160)
        self.participants = self._resolve_participants()
        if not self.participants:
            raise ValueError("时序图至少需要 1 个参与者（participants）")
        self.p_idx = {}
        for i, p in enumerate(self.participants):
            self.p_idx[p["id"]] = i
            self.p_idx[p["label"]] = i
        self.steps = list(model.get("steps") or model.get("messages") or [])
        self.autonumber = bool(model.get("autonumber", False))
        self._msg_counter = 0

    def _resolve_participants(self) -> list[dict]:
        out = []
        for i, p in enumerate(self.m.get("participants", [])):
            if isinstance(p, str):
                out.append({"id": p, "label": p, "type": "participant"})
            else:
                lbl = p.get("label", p.get("name", p.get("id", f"P{i + 1}")))
                out.append({
                    "id": p.get("id", lbl),
                    "label": lbl,
                    "type": p.get("type", "participant"),
                    "fill": p.get("fill"),
                })
        return out

    def _pid(self, ref) -> int:
        if ref in self.p_idx:
            return self.p_idx[ref]
        raise ValueError(f"未知参与者引用: {ref!r}，可用参与者：{[p['id'] for p in self.participants]}")

    # --- 扁平化事件流并收集组合片段边界 ---
    def _collect_items(self, steps: list[dict], out_events: list[dict], out_frags: list[dict], depth: int = 0):
        for st in steps:
            stype = st.get("type", "sync")
            if stype in ("alt", "opt", "loop", "par"):
                start_idx = len(out_events)
                out_events.append({"kind": "frag_open", "depth": depth})
                self._collect_items(st.get("steps", []), out_events, out_frags, depth + 1)
                dividers: list[tuple[int, str]] = []
                for eb in st.get("else", []):
                    div_idx = len(out_events)
                    dividers.append((div_idx, eb.get("label", "else")))
                    out_events.append({"kind": "frag_else", "depth": depth})
                    self._collect_items(eb.get("steps", []), out_events, out_frags, depth + 1)
                end_idx = len(out_events)
                out_events.append({"kind": "frag_close", "depth": depth})
                out_frags.append({
                    "type": stype,
                    "label": st.get("label", ""),
                    "start_idx": start_idx,
                    "end_idx": end_idx,
                    "dividers": dividers,
                    "depth": depth,
                })
            elif stype == "note":
                out_events.append({"kind": "note", "step": st})
            else:
                self._msg_counter += 1
                out_events.append({"kind": "msg", "step": st, "num": self._msg_counter})

    # --- 绘制参与者头部/底部 ---
    def _draw_participant(self, p: dict, cx: float, y: float, w: float, h: float):
        fill = p.get("fill") or self.t["seqActorFill"]
        stroke = self.t["stroke"]
        ptype = p["type"]
        if ptype == "actor":
            # 经典 UML 火柴人 + 名称
            s = f'stroke="{stroke}" stroke-width="1.5" fill="none" stroke-linecap="round"'
            hy = y + 8
            self.parts.append(f'<circle cx="{cx:.1f}" cy="{hy:.1f}" r="6.5" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
            self.parts.append(f'<line x1="{cx:.1f}" y1="{hy + 6.5:.1f}" x2="{cx:.1f}" y2="{hy + 21:.1f}" {s}/>')
            self.parts.append(f'<line x1="{cx - 10:.1f}" y1="{hy + 12:.1f}" x2="{cx + 10:.1f}" y2="{hy + 12:.1f}" {s}/>')
            self.parts.append(f'<line x1="{cx:.1f}" y1="{hy + 21:.1f}" x2="{cx - 8:.1f}" y2="{hy + 31:.1f}" {s}/>')
            self.parts.append(f'<line x1="{cx:.1f}" y1="{hy + 21:.1f}" x2="{cx + 8:.1f}" y2="{hy + 31:.1f}" {s}/>')
            self.parts.append(text_block(cx, y + h - 4, [p["label"]], 13.5, weight="bold"))
        elif ptype == "database":
            bw, bh = min(w, 108.0), h
            x = cx - bw / 2
            ry = 7.5
            d = (
                f"M{x:.1f},{y + ry:.1f} V{y + bh - ry:.1f} "
                f"A{bw / 2:.1f},{ry:.1f} 0 0 0 {x + bw:.1f},{y + bh - ry:.1f} V{y + ry:.1f} Z"
            )
            self.parts.append(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"/>')
            self.parts.append(f'<ellipse cx="{cx:.1f}" cy="{y + ry:.1f}" rx="{bw / 2:.1f}" ry="{ry:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"/>')
            self.parts.append(text_block(cx, y + bh / 2 + 3, wrap(p["label"], bw - 16, 13.5, 2), 13.5, weight="bold"))
        else:
            x = cx - w / 2
            self.parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"/>'
            )
            self.parts.append(text_block(cx, y + h / 2, wrap(p["label"], w - 16, 14, 2), 14, weight="bold"))

    def _open_arrow(self, x: float, y: float, angle: float, color: str):
        self.parts.append(
            f'<g class="flow-arrow" transform="translate({x:.1f},{y:.1f}) rotate({angle:.1f})">'
            f'<polyline points="-9,-4.5 0,0 -9,4.5" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></g>'
        )

    def _solid_arrow(self, x: float, y: float, angle: float, color: str):
        self.parts.append(
            f'<g class="flow-arrow" transform="translate({x:.1f},{y:.1f}) rotate({angle:.1f})">'
            f'<polygon points="0,0 -9,-4.5 -9,4.5" fill="{color}"/></g>'
        )

    def render(self) -> str:
        t = self.t
        events: list[dict] = []
        frags: list[dict] = []
        self._collect_items(self.steps, events, frags)

        n = len(self.participants)
        # 1. 计算每个参与者框宽与相邻间距（确保消息标签不会挤在一起）
        p_ws = [max(ACTOR_MIN_W, min(160.0, text_width(p["label"], 14) + 32)) for p in self.participants]
        pair_min_gap = [max(140.0, (p_ws[i] + p_ws[i + 1]) / 2 + 44) for i in range(n - 1)]

        for ev in events:
            if ev["kind"] == "msg":
                st = ev["step"]
                fi, ti = self._pid(st["from"]), self._pid(st["to"])
                lbl = st.get("label", "")
                if self.autonumber and lbl:
                    lbl = f"{ev['num']}. {lbl}"
                tw = text_width(lbl, 13) + 34
                if fi != ti:
                    lo, hi = min(fi, ti), max(fi, ti)
                    per_span = tw / (hi - lo)
                    for k in range(lo, hi):
                        pair_min_gap[k] = max(pair_min_gap[k], per_span)

        # 检查是否需要在右侧留空间（自调用或右侧 note）
        right_extra = 48.0
        left_extra = 28.0
        for ev in events:
            if ev["kind"] == "msg":
                st = ev["step"]
                if self._pid(st["from"]) == self._pid(st["to"]) == n - 1:
                    lbl = st.get("label", "")
                    right_extra = max(right_extra, 56 + text_width(lbl, 13))
            elif ev["kind"] == "note":
                st = ev["step"]
                pos = st.get("position", "right")
                over = st.get("over")
                idx = self._pid(over[0] if isinstance(over, list) else over)
                nw = min(190.0, max(110.0, text_width(st.get("label", ""), 12.5) + 26))
                if pos == "right" and idx == n - 1:
                    right_extra = max(right_extra, nw + 30)
                if pos == "left" and idx == 0:
                    left_extra = max(left_extra, nw + 30)

        min_span_w = sum(pair_min_gap) + p_ws[0] / 2 + p_ws[-1] / 2 + left_extra + right_extra + 2 * MARGIN_X
        self.W = max(self.W, int(min_span_w)) if self.m.get("canvas", {}).get("w") else max(960, int(min_span_w))

        # 均匀拉宽间距以充满画布
        avail = self.W - 2 * MARGIN_X - left_extra - right_extra - p_ws[0] / 2 - p_ws[-1] / 2
        base_sum = sum(pair_min_gap) or 1.0
        scale = max(1.0, avail / base_sum) if n > 1 else 1.0
        xs = [MARGIN_X + left_extra + p_ws[0] / 2]
        for g in pair_min_gap:
            xs.append(xs[-1] + g * scale)
        if n == 1:
            xs = [self.W / 2]

        # 2. 计算所有事件垂直坐标 y
        y = MARGIN_Y
        if self.m.get("title"):
            self.parts.append("<!-- 顶部标题 -->")
            self.rect(MARGIN_X, y, self.W - 2 * MARGIN_X, TITLE_H, t["titleFill"])
            self.parts.append(text_block(self.W / 2, y + TITLE_H / 2, [self.m["title"]], 17, weight="bold"))
            y += TITLE_H + TITLE_GAP

        top_actor_y = y
        lifeline_y0 = top_actor_y + ACTOR_H
        cur_y = lifeline_y0 + 26

        ev_y: list[float] = []
        ev_h: list[float] = []
        for ev in events:
            k = ev["kind"]
            if k == "frag_open":
                ev_y.append(cur_y)
                ev_h.append(FRAG_HEADER_H + 8)
                cur_y += FRAG_HEADER_H + 8
            elif k == "frag_else":
                ev_y.append(cur_y)
                ev_h.append(24)
                cur_y += 24
            elif k == "frag_close":
                ev_y.append(cur_y)
                ev_h.append(FRAG_PAD_BOTTOM)
                cur_y += FRAG_PAD_BOTTOM
            elif k == "note":
                lines = wrap(ev["step"].get("label", ""), 165, 12.5, max_lines=3)
                nh = max(34.0, lines_height(len(lines), 12.5) + 16)
                ev_y.append(cur_y + nh / 2)
                ev_h.append(nh + 14)
                cur_y += nh + 14
            else:
                st = ev["step"]
                is_self = self._pid(st["from"]) == self._pid(st["to"])
                h = SELF_H if is_self else STEP_H
                ev_y.append(cur_y + (12 if is_self else 20))
                ev_h.append(h)
                cur_y += h

        lifeline_y1 = cur_y + 16
        mirror_footer = self.m.get("mirrorFooter", len(events) >= 7)

        # 3. 生命线（底层）
        self.parts.append("<!-- 生命线 -->")
        for i in range(n):
            self.parts.append(
                f'<line x1="{xs[i]:.1f}" y1="{lifeline_y0:.1f}" x2="{xs[i]:.1f}" y2="{lifeline_y1:.1f}" '
                f'stroke="{t["stroke"]}" stroke-width="1.2" stroke-dasharray="6 4"/>'
            )

        # 4. 组合片段框（alt / opt / loop / par，外框放底层，标签稍后绘于激活条之上避免压字）
        frag_labels: list[tuple[float, float, str, float, str]] = []  # (x, y, text, fs, weight)
        if frags:
            self.parts.append("<!-- 组合片段 -->")
            for fr in sorted(frags, key=lambda f: f["depth"]):
                # 找到片段内涉及的最左/最右参与者
                idxs = []
                for idx in range(fr["start_idx"], fr["end_idx"]):
                    ev = events[idx]
                    if ev["kind"] == "msg":
                        idxs.extend([self._pid(ev["step"]["from"]), self._pid(ev["step"]["to"])])
                    elif ev["kind"] == "note":
                        ov = ev["step"].get("over")
                        idxs.extend([self._pid(x) for x in (ov if isinstance(ov, list) else [ov])])
                lo = min(idxs) if idxs else 0
                hi = max(idxs) if idxs else n - 1
                pad = max(24.0, 44.0 - fr["depth"] * 10.0)
                fx0 = max(MARGIN_X + 4, xs[lo] - pad)
                fx1 = min(self.W - MARGIN_X - 4, xs[hi] + pad + (36 if lo == hi else 0))
                fy0 = ev_y[fr["start_idx"]] - 4
                fy1 = ev_y[fr["end_idx"]] + FRAG_PAD_BOTTOM - 2
                self.parts.append(
                    f'<rect x="{fx0:.1f}" y="{fy0:.1f}" width="{fx1 - fx0:.1f}" height="{fy1 - fy0:.1f}" '
                    f'fill="{t["background"]}" fill-opacity="0.35" stroke="{t["stroke"]}" stroke-width="1.2"/>'
                )
                # 左上角经典 UML 五边形标签
                tag = fr["type"]
                tw = max(48.0, text_width(tag, 12.5) + 22)
                th = 22.0
                poly = f"{fx0:.1f},{fy0:.1f} {fx0 + tw:.1f},{fy0:.1f} {fx0 + tw:.1f},{fy0 + th - 6:.1f} {fx0 + tw - 8:.1f},{fy0 + th:.1f} {fx0:.1f},{fy0 + th:.1f}"
                self.parts.append(f'<polygon points="{poly}" fill="{t["seqFragmentFill"]}" stroke="{t["stroke"]}" stroke-width="1.2"/>')
                self.parts.append(text_block(fx0 + (tw - 4) / 2, fy0 + th / 2, [tag], 12.5, weight="bold"))
                label_x = max(fx0 + tw + 10, xs[lo] + ACT_W / 2 + 12)
                if fr["label"]:
                    frag_labels.append((label_x, fy0 + th / 2, f"[{fr['label']}]", 12.5, "bold"))
                # else 分隔虚线
                for div_idx, div_lbl in fr["dividers"]:
                    dy = ev_y[div_idx] + 2
                    self.parts.append(
                        f'<line x1="{fx0:.1f}" y1="{dy:.1f}" x2="{fx1:.1f}" y2="{dy:.1f}" '
                        f'stroke="{t["stroke"]}" stroke-width="1.1" stroke-dasharray="5 4"/>'
                    )
                    if div_lbl:
                        frag_labels.append((max(fx0 + 12, xs[lo] + ACT_W / 2 + 12), dy + 14, f"[{div_lbl}]", 12.0, "bold"))

        # 5. 激活条计算与绘制（无对应 reply 的调用自动收口为短执行块，不拖到图底）
        active_stack: dict[int, list[tuple[int, float]]] = {i: [] for i in range(n)}
        act_bars: list[tuple[int, float, float]] = []
        for idx, ev in enumerate(events):
            if ev["kind"] != "msg":
                continue
            st = ev["step"]
            fi, ti = self._pid(st["from"]), self._pid(st["to"])
            my = ev_y[idx]
            mtype = st.get("type", "sync")
            if st.get("activate") or (mtype == "sync" and fi != ti and st.get("activate") is not False):
                if not active_stack[ti]:
                    active_stack[ti].append((idx, my))
            if st.get("deactivate") or (mtype in ("reply", "return") and active_stack[fi]):
                if active_stack[fi]:
                    _, sy = active_stack[fi].pop()
                    act_bars.append((fi, sy, my))
        for pi, starts in active_stack.items():
            for start_idx, sy in starts:
                # 若后续不再由该参与者发出任何消息，画一个干脆的短执行块（26px）而非拖到底部
                last_y = sy + 26.0
                for j in range(start_idx + 1, len(events)):
                    if events[j]["kind"] == "msg" and self._pid(events[j]["step"]["from"]) == pi:
                        last_y = max(last_y, ev_y[j])
                act_bars.append((pi, sy, min(last_y, lifeline_y1 - 14)))

        if act_bars:
            self.parts.append("<!-- 激活条 -->")
            for pi, y0, y1 in act_bars:
                if y1 - y0 >= 6:
                    self.parts.append(
                        f'<rect x="{xs[pi] - ACT_W / 2:.1f}" y="{y0:.1f}" width="{ACT_W}" height="{y1 - y0:.1f}" '
                        f'rx="2" fill="{t["seqActivationFill"]}" stroke="{t["stroke"]}" stroke-width="1.1"/>'
                    )

        # 绘制片段条件文字（置于激活条之上，带微透明白底防止任何压线）
        for lx, ly, ltxt, lfs, lwt in frag_labels:
            lw = text_width(ltxt, lfs) + 8
            self.parts.append(
                f'<rect x="{lx - 4:.1f}" y="{ly - 9:.1f}" width="{lw:.1f}" height="18" fill="{t["background"]}" fill-opacity="0.9"/>'
            )
            self.parts.append(text_block(lx, ly, [ltxt], lfs, weight=lwt, anchor="start"))

        # 6. 消息箭头与便签注释
        self.parts.append("<!-- 交互消息与注释 -->")
        for idx, ev in enumerate(events):
            if ev["kind"] == "msg":
                st = ev["step"]
                fi, ti = self._pid(st["from"]), self._pid(st["to"])
                my = ev_y[idx]
                mtype = st.get("type", "sync")
                color = st.get("color") or t["lineColor"]
                lbl = st.get("label", "")
                if self.autonumber and lbl:
                    lbl = f"{ev['num']}. {lbl}"
                dashed = mtype in ("reply", "return") or bool(st.get("dashed"))
                da = ' stroke-dasharray="5 4"' if dashed else ""

                if fi == ti:
                    # 自调用 U 形回环
                    sx = xs[fi] + ACT_W / 2
                    loop_w, loop_h = 38.0, 26.0
                    d = f"M{sx:.1f},{my:.1f} H{sx + loop_w:.1f} V{my + loop_h:.1f} H{sx + 8:.1f}"
                    self.parts.append(f'<path d="{d}" stroke="{color}" stroke-width="1.35" fill="none"{da}/>')
                    if mtype == "async":
                        self._open_arrow(sx, my + loop_h, 180, color)
                    else:
                        self._solid_arrow(sx, my + loop_h, 180, color)
                    if lbl:
                        self.parts.append(text_block(sx + loop_w + 8, my + loop_h / 2, [lbl], 13, anchor="start"))
                else:
                    right = ti > fi
                    offset = ACT_W / 2
                    x0 = xs[fi] + (offset if right else -offset)
                    x1 = xs[ti] + (-offset if right else offset)
                    end_x = x1 + (-8 if right else 8)
                    self.parts.append(
                        f'<line x1="{x0:.1f}" y1="{my:.1f}" x2="{end_x:.1f}" y2="{my:.1f}" '
                        f'stroke="{color}" stroke-width="1.35"{da}/>'
                    )
                    ang = 0.0 if right else 180.0
                    if mtype == "async":
                        self._open_arrow(x1, my, ang, color)
                    else:
                        self._solid_arrow(x1, my, ang, color)
                    if lbl:
                        mx = (x0 + x1) / 2
                        tw = text_width(lbl, 13) + 10
                        self.parts.append(
                            f'<rect x="{mx - tw / 2:.1f}" y="{my - 21:.1f}" width="{tw:.1f}" height="17" fill="{t["background"]}" fill-opacity="0.88"/>'
                        )
                        self.parts.append(text_block(mx, my - 12, [lbl], 13))

            elif ev["kind"] == "note":
                st = ev["step"]
                my = ev_y[idx]
                ov = st.get("over")
                pos = st.get("position", "over" if isinstance(ov, list) else "right")
                lines = wrap(st.get("label", ""), 165, 12.5, max_lines=3)
                nh = max(32.0, lines_height(len(lines), 12.5) + 14)
                nw = max(92.0, max((text_width(l, 12.5) for l in lines), default=60) + 26)
                if isinstance(ov, list):
                    i0, i1 = self._pid(ov[0]), self._pid(ov[-1])
                    nx0 = min(xs[i0], xs[i1]) - 36
                    nx1 = max(xs[i0], xs[i1]) + 36
                    nw = max(nw, nx1 - nx0)
                    nx = (xs[i0] + xs[i1]) / 2 - nw / 2
                else:
                    pi = self._pid(ov)
                    if pos == "left":
                        nx = xs[pi] - ACT_W / 2 - 12 - nw
                    elif pos == "right":
                        nx = xs[pi] + ACT_W / 2 + 12
                    else:
                        nx = xs[pi] - nw / 2
                ny = my - nh / 2
                fold = 10.0
                d = f"M{nx:.1f},{ny:.1f} H{nx + nw - fold:.1f} L{nx + nw:.1f},{ny + fold:.1f} V{ny + nh:.1f} H{nx:.1f} Z"
                self.parts.append(f'<path d="{d}" fill="{t["seqNoteFill"]}" stroke="{t["stroke"]}" stroke-width="1.1"/>')
                self.parts.append(
                    f'<path d="M{nx + nw - fold:.1f},{ny:.1f} V{ny + fold:.1f} H{nx + nw:.1f}" fill="none" stroke="{t["stroke"]}" stroke-width="1.1"/>'
                )
                self.parts.append(text_block(nx + nw / 2, my, lines, 12.5))

        # 7. 顶部参与者（以及可选底部镜像参与者）
        self.parts.append("<!-- 顶部参与者 -->")
        for i, p in enumerate(self.participants):
            self._draw_participant(p, xs[i], top_actor_y, p_ws[i], ACTOR_H)

        bottom_y = lifeline_y1
        if mirror_footer:
            self.parts.append("<!-- 底部参与者 -->")
            for i, p in enumerate(self.participants):
                self._draw_participant(p, xs[i], lifeline_y1, p_ws[i], ACTOR_H)
            bottom_y = lifeline_y1 + ACTOR_H

        return self.wrap_svg(int(bottom_y + MARGIN_Y + 8))
