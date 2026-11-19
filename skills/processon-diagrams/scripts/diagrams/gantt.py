"""ProcessOn 风格甘特图渲染器（diagram: "gantt"）。

支持：
- 日期自动排布（timeline.unit: month-week / quarter-month / week-day / day）与自定义 periods 网格排布
- 单阶段总标题栏（如"开发计划甘特图"）或多阶段分组竖排标题栏
- 单行单条或单行多条胶囊进度条、里程碑菱形、进度占比、今日/节点标记线、底部图例
- 自动适配标签宽度与超短进度条文字外置，避免文字溢出或重叠
"""
from __future__ import annotations

import calendar
import datetime as dt
import sys
from xml.sax.saxutils import escape

from core import BaseDiagram, text_block, text_width, vertical_text, wrap

# ---------- 布局常量（与 references/gantt.md 保持一致） ----------
MARGIN_X = 36
MARGIN_Y = 24
TOP_TITLE_H = 44
TITLE_GAP = 14
GROUP_W = 48
MIN_TASK_W = 108
MAX_TASK_W = 200
SPLIT_GAP = 4       # 左侧栏与右侧时间区、表头与主体之间的清晰留白
MAJOR_H = 36        # 一级时间表头高度（如 2024年2月）
SUB_H = 36          # 二级时间表头高度（如 第一周）
ROW_H = 44          # 单任务行高度
BAR_H = 30          # 胶囊进度条高度
BAR_INSET_X = 2.5   # 进度条左右微内缩，防止相邻进度条贴死
LEGEND_H = 36


def _parse_date(val) -> dt.date | None:
    if not isinstance(val, str):
        return None
    s = val.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _fmt_cn_date(d: dt.date) -> str:
    return f"{d.month}月{d.day}日"


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def _build_periods_from_timeline(tl: dict) -> list[dict]:
    start = _parse_date(tl.get("start"))
    end = _parse_date(tl.get("end"))
    if not start or not end or end < start:
        raise ValueError("timeline.start 与 timeline.end 必须是有效的 YYYY-MM-DD 日期且 end >= start")
    unit = tl.get("unit", "month-week")
    periods: list[dict] = []

    if unit == "month-week":
        subs_tpl = tl.get("weekLabels", ["第一周", "第二周", "第三周", "第四周"])
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            last_day = calendar.monthrange(y, m)[1]
            periods.append({
                "label": f"{y}年{m}月",
                "start": f"{y:04d}-{m:02d}-01",
                "end": f"{y:04d}-{m:02d}-{last_day:02d}",
                "subs": list(subs_tpl),
            })
            y, m = _add_months(y, m, 1)

    elif unit == "quarter-month":
        q_start = (start.month - 1) // 3
        y, q = start.year, q_start
        while True:
            m0 = q * 3 + 1
            m2 = m0 + 2
            q_first = dt.date(y, m0, 1)
            q_last = dt.date(y, m2, calendar.monthrange(y, m2)[1])
            if q_first > end:
                break
            periods.append({
                "label": f"{y}年Q{q + 1}",
                "start": q_first.isoformat(),
                "end": q_last.isoformat(),
                "subs": [f"{m0}月", f"{m0 + 1}月", f"{m2}月"],
            })
            q += 1
            if q == 4:
                q = 0
                y += 1

    elif unit == "week-day":
        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        cur = start - dt.timedelta(days=start.weekday())
        wk = 1
        while cur <= end:
            w_end = cur + dt.timedelta(days=6)
            label = tl.get("weekTitle", "date")
            if label == "number":
                plabel = f"第{wk}周"
            else:
                plabel = f"{cur.month}/{cur.day}~{w_end.month}/{w_end.day}"
            subs = [f"{(cur + dt.timedelta(days=i)).day}日\n{day_names[i]}" if tl.get("showWeekday") else f"{(cur + dt.timedelta(days=i)).month}/{(cur + dt.timedelta(days=i)).day}" for i in range(7)]
            periods.append({
                "label": plabel,
                "start": cur.isoformat(),
                "end": w_end.isoformat(),
                "subs": subs,
            })
            cur += dt.timedelta(days=7)
            wk += 1

    elif unit == "day":
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            d0 = start.day if (y, m) == (start.year, start.month) else 1
            d1 = end.day if (y, m) == (end.year, end.month) else calendar.monthrange(y, m)[1]
            periods.append({
                "label": f"{y}年{m}月",
                "start": f"{y:04d}-{m:02d}-{d0:02d}",
                "end": f"{y:04d}-{m:02d}-{d1:02d}",
                "subs": [str(d) for d in range(d0, d1 + 1)],
            })
            y, m = _add_months(y, m, 1)
    else:
        raise ValueError(f"不支持的 timeline.unit: {unit}（可选：month-week / quarter-month / week-day / day）")

    return periods


class GanttDiagram(BaseDiagram):
    def __init__(self, model: dict):
        super().__init__(model, default_width=1200)
        self.periods = self._resolve_periods()
        self.total_cols = sum(len(p["subs"]) for p in self.periods)
        if self.total_cols <= 0:
            raise ValueError("甘特图至少需要 1 个时间子列（请配置 timeline 或 periods）")
        self.groups = self._resolve_groups()

    # --- 数据归一化 ---
    def _resolve_periods(self) -> list[dict]:
        if self.m.get("periods"):
            periods = []
            for p in self.m["periods"]:
                subs = p.get("subs") or [p.get("label", "")]
                periods.append({
                    "label": p.get("label", ""),
                    "start": p.get("start"),
                    "end": p.get("end"),
                    "subs": list(subs),
                })
            return periods
        if self.m.get("timeline"):
            return _build_periods_from_timeline(self.m["timeline"])
        raise ValueError("甘特图必须提供 periods 或 timeline")

    def _resolve_groups(self) -> list[dict]:
        if self.m.get("groups"):
            return self.m["groups"]
        tasks = self.m.get("tasks", [])
        title = self.m.get("title", "")
        return [{"title": title, "tasks": tasks}]

    def _bar_color(self, color_name: str | None) -> str:
        t = self.t
        if not color_name or color_name == "primary":
            return t["ganttBarPrimary"]
        if color_name.startswith("#"):
            return color_name
        mapping = {
            "teal": t["ganttBarPrimary"],
            "accent1": t["ganttBarAccent1"],
            "pink": t["ganttBarAccent1"],
            "coral": t["ganttBarAccent1"],
            "accent2": t["ganttBarAccent2"],
            "green": t["ganttBarAccent2"],
            "accent3": t["ganttBarAccent3"],
            "navy": t["ganttBarAccent3"],
            "blue": t["ganttBarAccent3"],
            "critical": t["ganttBarCritical"],
            "red": t["ganttBarCritical"],
            "milestone": t["ganttBarCritical"],
            "orange": "#F59E0B",
            "purple": "#7C5CFA",
            "gray": "#6B7280",
        }
        return mapping.get(color_name.lower(), t["ganttBarPrimary"])

    # --- 坐标换算：日期或列索引 -> [0, total_cols] ---
    def _pos_to_col(self, val, is_end: bool = False) -> float:
        if isinstance(val, (int, float)):
            return max(0.0, min(float(self.total_cols), float(val)))
        d = _parse_date(val)
        if d is None:
            raise ValueError(f"无法解析甘特图位置值: {val!r}（应为 YYYY-MM-DD 或数字列索引）")

        # 遍历带日期范围的 periods，按天精确映射
        dated_ranges: list[tuple[dt.date, dt.date, int, int]] = []
        col_cursor = 0
        for p in self.periods:
            n = len(p["subs"])
            ps, pe = _parse_date(p.get("start")), _parse_date(p.get("end"))
            if ps and pe and pe >= ps:
                dated_ranges.append((ps, pe, col_cursor, n))
            col_cursor += n

        if not dated_ranges:
            raise ValueError(f"任务使用了日期 {val!r}，但 periods 未配置 start/end 日期")

        if d < dated_ranges[0][0]:
            return 0.0
        if d > dated_ranges[-1][1]:
            return float(self.total_cols)

        for ps, pe, c0, n in dated_ranges:
            if ps <= d <= pe:
                days = (pe - ps).days + 1
                offset = (d - ps).days + (1 if is_end else 0)
                return c0 + (offset / days) * n

        # 若日期恰好落在两个 period 之间的空隙，取最近边界
        for i in range(len(dated_ranges) - 1):
            if dated_ranges[i][1] < d < dated_ranges[i + 1][0]:
                return float(dated_ranges[i + 1][2])
        return float(self.total_cols)

    def _text_colored(self, cx: float, cy: float, lines: list[str], fs: float,
                      fill: str, weight: str | None = None, anchor: str = "middle"):
        lh = fs * 1.3
        start = cy - (len(lines) - 1) * lh / 2 + fs * 0.35
        w = f' font-weight="{weight}"' if weight else ""
        for i, line in enumerate(lines):
            self.parts.append(
                f'<text x="{cx:.1f}" y="{start + i * lh:.1f}" font-size="{fs}" '
                f'text-anchor="{anchor}" style="fill:{fill}"{w}>{escape(line)}</text>'
            )

    def _vertical_colored(self, cx: float, cy: float, s: str, fs: float, avail_h: float,
                          fill: str, weight: str = "bold"):
        chars = list(s)
        lh = min(fs + 7, max(fs, (avail_h - 16) / max(len(chars), 1)))
        start = cy - (len(chars) - 1) * lh / 2 + fs * 0.35
        spans = "".join(
            f'<tspan x="{cx:.1f}" y="{start + i * lh:.1f}">{escape(c)}</tspan>' for i, c in enumerate(chars)
        )
        self.parts.append(
            f'<text font-size="{fs}" font-weight="{weight}" text-anchor="middle" style="fill:{fill}">{spans}</text>'
        )

    # --- 绘制各区块 ---
    def _bar_bounds(self, bar: dict, gx0: float, gx1: float, col_w: float) -> tuple[float, float]:
        if bar.get("type") == "milestone":
            c = self._pos_to_col(bar.get("at", bar.get("start")), is_end=False)
            mx = gx0 + c * col_w
            return mx - 10, mx + 10
        c0 = self._pos_to_col(bar["start"], is_end=False)
        c1 = self._pos_to_col(bar["end"], is_end=True)
        if c1 < c0:
            c0, c1 = c1, c0
        x0 = gx0 + c0 * col_w + BAR_INSET_X
        x1 = gx0 + c1 * col_w - BAR_INSET_X
        bw = max(18.0, x1 - x0)
        if x0 + bw > gx1 - 1:
            x0 = max(gx0 + 1, gx1 - 1 - bw)
        return x0, x0 + bw

    def _draw_bar(self, bar: dict, gx0: float, gx1: float, col_w: float, row_cy: float,
                  right_limit: float | None = None, left_limit: float | None = None,
                  label_below_y: float | None = None):
        default_color = "critical" if bar.get("type") == "milestone" else "primary"
        color = self._bar_color(bar.get("color", default_color))
        rlim = gx1 - 4 if right_limit is None else right_limit
        llim = gx0 + 4 if left_limit is None else left_limit

        if bar.get("type") == "milestone":
            at = bar.get("at", bar.get("start"))
            c = self._pos_to_col(at, is_end=False)
            mx = gx0 + c * col_w
            r = 10
            pts = f"{mx:.1f},{row_cy - r:.1f} {mx + r:.1f},{row_cy:.1f} {mx:.1f},{row_cy + r:.1f} {mx - r:.1f},{row_cy:.1f}"
            self.parts.append(f'<polygon points="{pts}" fill="{color}" stroke="{self.t["background"]}" stroke-width="1.5"/>')
            label = bar.get("label", "")
            if label:
                tw = text_width(label, 13)
                if mx + r + 8 + tw <= rlim:
                    self._text_colored(mx + r + 6, row_cy, [label], 13, self.t["text"], weight="bold", anchor="start")
                elif mx - r - 8 - tw >= llim:
                    self._text_colored(mx - r - 6, row_cy, [label], 13, self.t["text"], weight="bold", anchor="end")
                elif label_below_y is not None:
                    lx = min(mx, gx1 - tw / 2 - 6)
                    lx = max(lx, gx0 + tw / 2 + 6)
                    self._text_colored(lx, label_below_y, [label], 12, color, weight="bold", anchor="middle")
                else:
                    self._text_colored(mx - r - 6, row_cy, [label], 12, self.t["text"], weight="bold", anchor="end")
            return

        x0, x1 = self._bar_bounds(bar, gx0, gx1, col_w)
        bw = x1 - x0
        by = row_cy - BAR_H / 2
        rx = min(BAR_H / 2, bw / 2)

        # 胶囊底色
        self.parts.append(
            f'<rect x="{x0:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{BAR_H}" rx="{rx:.1f}" fill="{color}"/>'
        )

        # 可选进度占比
        prog = bar.get("progress")
        if isinstance(prog, (int, float)) and 0 < prog < 1:
            pw = max(rx * 2, bw * float(prog))
            self.parts.append(
                f'<rect x="{x0:.1f}" y="{by:.1f}" width="{min(pw, bw):.1f}" height="{BAR_H}" '
                f'rx="{rx:.1f}" fill="#000000" fill-opacity="0.18"/>'
            )

        # 注册节点位置，允许可选 connections 引用
        if bar.get("id"):
            self.nodes[bar["id"]] = (x0, by, bw, BAR_H)

        # 自动生成日期文案（太窄时优先尝试紧凑格式 M/D~M/D）
        auto_label = bar.get("label") is None
        label = bar.get("label")
        compact_label = None
        if auto_label:
            ds, de = _parse_date(bar.get("start")), _parse_date(bar.get("end"))
            if ds and de:
                label = _fmt_cn_date(ds) if ds == de else f"{_fmt_cn_date(ds)}~{_fmt_cn_date(de)}"
                compact_label = f"{ds.month}/{ds.day}" if ds == de else f"{ds.month}/{ds.day}~{de.month}/{de.day}"
            else:
                label = ""

        if label:
            if text_width(label, 13.5) + 14 <= bw:
                self._text_colored(x0 + bw / 2, row_cy, [label], 13.5, "#FFFFFF", weight="bold")
            elif text_width(label, 12) + 10 <= bw:
                self._text_colored(x0 + bw / 2, row_cy, [label], 12, "#FFFFFF", weight="bold")
            elif compact_label and text_width(compact_label, 11.5) + 10 <= bw:
                self._text_colored(x0 + bw / 2, row_cy, [compact_label], 11.5, "#FFFFFF", weight="bold")
            else:
                # 进度条太短时外置到可用空间较大的一侧，避免压盖同行的其他进度条
                tw = text_width(label, 13)
                if x1 + 8 + tw <= rlim:
                    self._text_colored(x1 + 6, row_cy, [label], 13, self.t["text"], weight="bold", anchor="start")
                elif x0 - 8 - tw >= llim:
                    self._text_colored(x0 - 6, row_cy, [label], 13, self.t["text"], weight="bold", anchor="end")
                else:
                    self._text_colored(x1 + 6, row_cy, [label], 12, self.t["text"], weight="bold", anchor="start")

    def _draw_markers(self, gx0: float, col_w: float, gy0: float, gy1: float):
        markers = list(self.m.get("markers", []))
        if self.m.get("today"):
            markers.append({"at": self.m["today"], "label": "今日", "color": self.t["ganttBarCritical"]})
        for mk in markers:
            c = self._pos_to_col(mk["at"], is_end=False)
            x = gx0 + c * col_w
            color = self._bar_color(mk.get("color", "critical"))
            self.parts.append(
                f'<line x1="{x:.1f}" y1="{gy0:.1f}" x2="{x:.1f}" y2="{gy1:.1f}" '
                f'stroke="{color}" stroke-width="1.5" stroke-dasharray="5 4"/>'
            )
            lbl = mk.get("label")
            if lbl:
                lw = text_width(lbl, 11) + 12
                self.parts.append(
                    f'<rect x="{x - lw / 2:.1f}" y="{gy0 - 8:.1f}" width="{lw:.1f}" height="16" rx="8" fill="{color}"/>'
                )
                self._text_colored(x, gy0, [lbl], 11, "#FFFFFF", weight="bold")

    def _draw_legend(self, legend: list[dict], y: float) -> float:
        items = []
        total_w = 0.0
        for item in legend:
            lbl = item.get("label", "")
            iw = 22 + 6 + text_width(lbl, 12.5)
            items.append((self._bar_color(item.get("color")), lbl, iw))
            total_w += iw
        gap = 22
        total_w += gap * max(len(items) - 1, 0)
        x = (self.W - total_w) / 2
        cy = y + 18
        for color, lbl, iw in items:
            self.parts.append(f'<rect x="{x:.1f}" y="{cy - 6:.1f}" width="22" height="12" rx="6" fill="{color}"/>')
            self._text_colored(x + 28, cy, [lbl], 12.5, self.t["text"], anchor="start")
            x += iw + gap
        return LEGEND_H

    # --- 总装 ---
    def render(self) -> str:
        t, W = self.t, self.W
        y = MARGIN_Y

        # 可选顶部标题横幅
        if self.m.get("topTitle"):
            self.parts.append("<!-- 顶部标题 -->")
            self.rect(MARGIN_X, y, W - 2 * MARGIN_X, TOP_TITLE_H, t["titleFill"])
            self.parts.append(text_block(W / 2, y + TOP_TITLE_H / 2, [self.m["topTitle"]], 18, weight="bold"))
            y += TOP_TITLE_H + TITLE_GAP

        # 计算左侧栏宽度
        has_group_bar = any(g.get("title") for g in self.groups)
        group_w = GROUP_W if has_group_bar else 0
        all_tasks = [tk for g in self.groups for tk in g.get("tasks", [])]
        max_task_tw = max((text_width(tk.get("name", ""), 14) for tk in all_tasks), default=80)
        task_w = int(min(MAX_TASK_W, max(MIN_TASK_W, max_task_tw + 28)))
        left_w = group_w + task_w

        lx0 = MARGIN_X
        gx0 = lx0 + left_w + SPLIT_GAP
        gx1 = W - MARGIN_X
        gw = gx1 - gx0
        col_w = gw / self.total_cols

        # --- 表头区域 ---
        header_y = y
        header_h = MAJOR_H + SUB_H
        self.parts.append("<!-- 左上角标题格 -->")
        self.rect(lx0, header_y, left_w, header_h, t["ganttCornerFill"])
        if self.m.get("cornerText"):
            self._text_colored(lx0 + left_w / 2, header_y + header_h / 2, [self.m["cornerText"]], 15, t["ganttHeaderText"], weight="bold")

        self.parts.append("<!-- 时间表头 -->")
        # 二级表头淡色衬底条
        self.parts.append(
            f'<rect x="{gx0:.1f}" y="{header_y + MAJOR_H:.1f}" width="{gw:.1f}" height="{SUB_H}" fill="{t["ganttSubStripFill"]}"/>'
        )
        col_idx = 0
        sub_fs = 13.5 if col_w >= 54 else (11.5 if col_w >= 34 else 10)
        for p in self.periods:
            n = len(p["subs"])
            px = gx0 + col_idx * col_w
            pw = n * col_w
            # 一级表头
            self.rect(px, header_y, pw, MAJOR_H, t["ganttHeaderFill"])
            self._text_colored(px + pw / 2, header_y + MAJOR_H / 2, [p["label"]], 15, t["ganttHeaderText"], weight="bold")
            # 二级表头（白底虚线内嵌格，复刻 ProcessOn 经典模板）
            for si, sub in enumerate(p["subs"]):
                sx = gx0 + (col_idx + si) * col_w
                pad = 2.5 if col_w >= 36 else 1.5
                self.parts.append(
                    f'<rect x="{sx + pad:.1f}" y="{header_y + MAJOR_H + pad:.1f}" '
                    f'width="{col_w - 2 * pad:.1f}" height="{SUB_H - 2 * pad:.1f}" '
                    f'fill="{t["background"]}" stroke="{t["stroke"]}" stroke-width="1" stroke-dasharray="2.5 2.5"/>'
                )
                sub_lines = str(sub).split("\n")
                self._text_colored(sx + col_w / 2, header_y + MAJOR_H + SUB_H / 2, sub_lines, sub_fs, t["text"], weight="bold")
            col_idx += n

        # --- 主体区域：左侧阶段栏 + 任务列 + 右侧甘特网格 ---
        body_y = header_y + header_h + SPLIT_GAP
        row_heights: list[list[float]] = []
        row_sandwiched: list[list[bool]] = []
        for g in self.groups:
            ghs, gsw = [], []
            for tk in g.get("tasks", []):
                lines = wrap(tk.get("name", ""), task_w - 18, 14, max_lines=2)
                base_h = max(ROW_H, len(lines) * 18 + 18)
                bars = tk.get("bars")
                if bars is None and ("start" in tk or "at" in tk):
                    bars = [tk]
                bar_list = list(bars or [])
                bounds = [self._bar_bounds(b, gx0, gx1, col_w) for b in bar_list]
                order = sorted(range(len(bar_list)), key=lambda idx: bounds[idx][0])
                sandwiched = False
                for pos, idx in enumerate(order):
                    b = bar_list[idx]
                    if b.get("type") == "milestone" and b.get("label"):
                        mx = (bounds[idx][0] + bounds[idx][1]) / 2
                        tw = text_width(b["label"], 13)
                        llim = bounds[order[pos - 1]][1] + 4 if pos > 0 else gx0 + 4
                        rlim = bounds[order[pos + 1]][0] - 4 if pos + 1 < len(order) else gx1 - 4
                        if mx + 18 + tw > rlim and mx - 18 - tw < llim:
                            sandwiched = True
                ghs.append(max(base_h, 58) if sandwiched else base_h)
                gsw.append(sandwiched)
            row_heights.append(ghs)
            row_sandwiched.append(gsw)
        total_body_h = sum(sum(ghs) for ghs in row_heights)

        # 右侧网格背景与时间分隔竖线
        self.parts.append("<!-- 甘特时间网格 -->")
        self.rect(gx0, body_y, gw, total_body_h, t["background"])
        for c in range(1, self.total_cols):
            vx = gx0 + c * col_w
            self.parts.append(
                f'<line x1="{vx:.1f}" y1="{body_y:.1f}" x2="{vx:.1f}" y2="{body_y + total_body_h:.1f}" '
                f'stroke="{t["ganttGridLine"]}" stroke-width="1"/>'
            )

        # 任务行、左侧分组栏、任务标签与进度条
        cur_y = body_y
        show_row_lines = bool(self.m.get("showRowLines", False))
        for gi, (g, ghs, gsw) in enumerate(zip(self.groups, row_heights, row_sandwiched)):
            group_h = sum(ghs)
            if group_h <= 0:
                continue
            self.parts.append(f"<!-- 阶段{gi + 1}：{escape(g.get('title', ''))} -->")

            # 左侧竖排阶段/标题栏
            if has_group_bar:
                gfill = self._bar_color(g["fill"]) if g.get("fill") else t["ganttGroupFill"]
                self.parts.append(
                    f'<rect x="{lx0:.1f}" y="{cur_y:.1f}" width="{group_w}" height="{group_h:.1f}" fill="{gfill}"/>'
                )
                if g.get("title"):
                    self._vertical_colored(lx0 + group_w / 2, cur_y + group_h / 2, g["title"], 16, group_h, t["ganttHeaderText"])

            # 任务列浅色衬底条
            tx0 = lx0 + group_w
            self.parts.append(
                f'<rect x="{tx0:.1f}" y="{cur_y:.1f}" width="{task_w}" height="{group_h:.1f}" fill="{t["ganttSubStripFill"]}"/>'
            )

            # 多阶段之间的分隔线
            if gi > 0:
                self.parts.append(
                    f'<line x1="{lx0:.1f}" y1="{cur_y:.1f}" x2="{gx1:.1f}" y2="{cur_y:.1f}" '
                    f'stroke="{t["stroke"]}" stroke-width="1"/>'
                )

            ry = cur_y
            for ti, (tk, rh, sw) in enumerate(zip(g.get("tasks", []), ghs, gsw)):
                # 可选水平行分隔线
                if show_row_lines and ti > 0:
                    self.parts.append(
                        f'<line x1="{gx0:.1f}" y1="{ry:.1f}" x2="{gx1:.1f}" y2="{ry:.1f}" '
                        f'stroke="{t["ganttGridLine"]}" stroke-width="0.6" stroke-opacity="0.45"/>'
                    )
                # 任务名称块（青色内嵌矩形，白字粗体）
                inset_x, inset_y = 3, 2.5
                tfill = self._bar_color(tk["fill"]) if tk.get("fill") else t["ganttTaskFill"]
                self.parts.append(
                    f'<rect x="{tx0 + inset_x:.1f}" y="{ry + inset_y:.1f}" '
                    f'width="{task_w - 2 * inset_x:.1f}" height="{rh - 2 * inset_y:.1f}" fill="{tfill}"/>'
                )
                tlines = wrap(tk.get("name", ""), task_w - 18, 14, max_lines=2)
                self._text_colored(tx0 + task_w / 2, ry + rh / 2, tlines, 14, t["ganttHeaderText"], weight="bold")

                # 任务进度条（支持单条简写或 bars 多条数组，同行多条自动计算左右避让边界）
                bars = tk.get("bars")
                if bars is None and ("start" in tk or "at" in tk):
                    bars = [tk]
                bar_list = list(bars or [])
                bounds = [self._bar_bounds(b, gx0, gx1, col_w) for b in bar_list]
                order = sorted(range(len(bar_list)), key=lambda idx: bounds[idx][0])
                bar_cy = ry + 21 if sw else ry + rh / 2
                below_y = ry + rh - 10 if sw else None
                for pos, idx in enumerate(order):
                    llim = bounds[order[pos - 1]][1] + 4 if pos > 0 else gx0 + 4
                    rlim = bounds[order[pos + 1]][0] - 4 if pos + 1 < len(order) else gx1 - 4
                    self._draw_bar(bar_list[idx], gx0, gx1, col_w, bar_cy,
                                   right_limit=rlim, left_limit=llim, label_below_y=below_y)

                ry += rh
            cur_y += group_h

        # 补画外框（保证右侧网格外框线清晰不被进度条压盖）
        self.parts.append(
            f'<rect x="{gx0:.1f}" y="{body_y:.1f}" width="{gw:.1f}" height="{total_body_h:.1f}" '
            f'fill="none" stroke="{t["stroke"]}" stroke-width="1"/>'
        )

        # 可选今日/标记线
        if self.m.get("today") or self.m.get("markers"):
            self.parts.append("<!-- 标记线 -->")
            self._draw_markers(gx0, col_w, body_y, body_y + total_body_h)

        # 可选连线（依赖箭头）
        if self.m.get("connections"):
            self.parts.append("<!-- 任务依赖线 -->")
            self.draw_connections()

        end_y = body_y + total_body_h
        if self.m.get("legend"):
            self.parts.append("<!-- 图例 -->")
            end_y += 10 + self._draw_legend(self.m["legend"], end_y + 10)

        return self.wrap_svg(int(end_y + MARGIN_Y))
