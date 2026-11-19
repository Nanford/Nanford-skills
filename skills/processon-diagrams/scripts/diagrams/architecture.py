"""ProcessOn 风格分层架构图渲染器（diagram: "architecture"）。"""
from __future__ import annotations

import sys
from xml.sax.saxutils import escape

from core import BaseDiagram, icon, lines_height, text_block, text_width, vertical_text, wrap

# ---------- 布局常量（与 references/architecture.md 保持一致） ----------
MARGIN = 40          # 画布左右边距
TOP = 16             # 画布上边距
TITLE_H = 44         # 顶部标题横幅高度
BASE_H = 44          # 底部基座横幅高度
LABEL_W = 40         # 左侧竖排层标签宽度
SIDE_W = 40          # 右侧支撑栏宽度
COL_GAP = 16         # 标签/支撑栏与内容区间距
LAYER_GAP = 16       # 层与层间距
ROW_GAP = 14         # 层内行间距
NODE_H = 40          # 节点默认高度
NODE_FS = 14         # 节点字号
CARD_HEADER_H = 40   # 卡片表头高度
CARD_PAD = 12        # 卡片内边距
CARD_GAP = 14        # 卡片间距
ASIDE_W = 130        # 卡片区右侧挂面板宽度


class ArchitectureDiagram(BaseDiagram):
    def __init__(self, model: dict):
        super().__init__(model, default_width=1200)
        has_label = any(l.get("label") for l in model.get("layers", []))
        self.cx0 = MARGIN + (LABEL_W + COL_GAP if has_label else 0)
        self.cx1 = self.W - MARGIN - (SIDE_W + COL_GAP if model.get("sideBar") else 0)
        self.cw = self.cx1 - self.cx0

    # --- 行类型 ---
    def row_entry(self, row: dict, y: float) -> float:
        nodes = row["nodes"]
        n = len(nodes)
        w = min(180, (self.cw - (n + 1) * 16) / n)
        h = max(self.node_h(it, w) for it in nodes)
        pad = 10
        for x, it in zip(self.evenly(self.cx0, self.cx1, n, w), nodes):
            self.node(x, y + pad, w, h, it, self.t["entryFill"], rx=0)
        return h + pad * 2

    def row_banner(self, row: dict, y: float) -> float:
        lines = wrap(row["text"], self.cw - 40, NODE_FS)
        h = max(52, lines_height(len(lines), NODE_FS) + 24)
        self.rect(self.cx0, y, self.cw, h, self.t["bannerFill"])
        self.parts.append(text_block(self.cx0 + self.cw / 2, y + h / 2, lines, NODE_FS))
        return h

    def card_layout(self, card: dict, w: float):
        cols = card.get("cols", 2)
        nw = (w - 2 * CARD_PAD - (cols - 1) * CARD_PAD) / cols
        items = card.get("nodes", [])
        rows = [items[i:i + cols] for i in range(0, len(items), cols)]
        rhs = [max(self.node_h(it, nw) for it in r) for r in rows]
        body = sum(rhs) + CARD_PAD * (len(rows) + 1) if rows else CARD_PAD * 2
        return cols, nw, rows, rhs, CARD_HEADER_H + body

    def draw_card(self, card: dict, x: float, y: float, w: float, h: float):
        _, nw, rows, rhs, _ = self.card_layout(card, w)
        self.rect(x, y, w, h, self.t["cardBodyFill"])
        self.rect(x, y, w, CARD_HEADER_H, self.t["cardHeaderFill"])
        self.parts.append(text_block(x + w / 2, y + CARD_HEADER_H / 2, [card.get("title", "")], 15, weight="bold"))
        cy = y + CARD_HEADER_H + CARD_PAD
        for r, rh in zip(rows, rhs):
            for i, it in enumerate(r):
                self.node(x + CARD_PAD + i * (nw + CARD_PAD), cy, nw, rh, it, self.t["nodeFill"])
            cy += rh + CARD_PAD

    def row_cards(self, row: dict, y: float) -> float:
        columns = row["columns"]
        aside = row.get("aside")
        aside_w = aside.get("w", ASIDE_W) if aside else 0
        area = self.cw - (aside_w + CARD_GAP if aside else 0)
        n = len(columns)
        colw = (area - (n - 1) * CARD_GAP) / n
        layouts = [[self.card_layout(c, colw)[-1] for c in col] for col in columns]
        col_hs = [sum(hs) + CARD_GAP * (len(hs) - 1) for hs in layouts]
        if aside:
            an = len(aside["nodes"])
            col_hs.append(an * NODE_H + (an - 1) * 12 + 2 * CARD_PAD + (40 if aside.get("title") else 0))
        total = max(col_hs)
        for ci, (col, hs) in enumerate(zip(columns, layouts)):
            x = self.cx0 + ci * (colw + CARD_GAP)
            cy = y
            extra = total - (sum(hs) + CARD_GAP * (len(hs) - 1))
            for k, (card, h) in enumerate(zip(col, hs)):
                if k == len(col) - 1:
                    h += extra  # 末张卡片拉伸，使各列底部对齐
                self.draw_card(card, x, cy, colw, h)
                cy += h + CARD_GAP
        if aside:
            ax = self.cx1 - aside_w
            self.rect(ax, y, aside_w, total, self.t["panelFill"], rx=2)
            top = y
            if aside.get("title"):
                self.parts.append(text_block(ax + aside_w / 2, y + 22, [aside["title"]], 15, weight="bold"))
                top += 40
            an = len(aside["nodes"])
            avail = y + total - top - 2 * CARD_PAD
            gap = (avail - an * NODE_H) / max(an - 1, 1)
            for i, it in enumerate(aside["nodes"]):
                self.node(
                    ax + CARD_PAD,
                    top + CARD_PAD + i * (NODE_H + gap),
                    aside_w - 2 * CARD_PAD,
                    NODE_H,
                    it,
                    self.t["nodeFill"],
                    rx=2,
                )
        return total

    def row_panel(self, row: dict, y: float, x0: float | None = None, x1: float | None = None) -> float:
        x0 = self.cx0 if x0 is None else x0
        x1 = self.cx1 if x1 is None else x1
        h = 64
        self.rect(x0, y, x1 - x0, h, self.t["panelFill"], rx=2)
        start = x0
        if row.get("title"):
            self.parts.append(text_block(x0 + 16, y + h / 2, [row["title"]], NODE_FS, anchor="start"))
            start = x0 + 16 + text_width(row["title"], NODE_FS) + 16
        nodes = row["nodes"]
        n = len(nodes)
        w = min(150, (x1 - start - (n + 1) * 16) / n)
        for x, it in zip(self.evenly(start, x1, n, w), nodes):
            self.node(x, y + 12, w, NODE_H, it, self.t["softNodeFill"])
        return h

    def child_nodes(self, ch: dict, x0: float, x1: float, y: float, dashed: bool = False) -> float:
        nodes = ch["nodes"]
        n = len(nodes)
        w = min(130, (x1 - x0 - (n + 1) * 16) / n)
        nh = max(self.node_h(it, w) for it in nodes)
        top = 26 if ch.get("title") else 16
        h = nh + top + 16
        self.rect(x0, y, x1 - x0, h, self.t["innerFill"], dashed=dashed)
        if ch.get("title"):
            self.parts.append(text_block(x0 + 12, y + 14, [ch["title"]], 13, weight="bold", anchor="start"))
        for x, it in zip(self.evenly(x0, x1, n, w), nodes):
            self.node(x, y + top, w, nh, it, self.t["nodeFill"], rx=2)
        return h

    def child_flow(self, ch: dict, x0: float, x1: float, y: float) -> float:
        steps = ch["steps"]
        n = len(steps)
        has_icon = any(isinstance(s, dict) and s.get("icon") for s in steps)
        h = 112 if has_icon else 72
        self.rect(x0, y, x1 - x0, h, self.t["innerFill"], dashed=ch.get("dashed", True))
        slot = (x1 - x0 - 48) / n
        centers = [x0 + 24 + slot * (i + 0.5) for i in range(n)]
        half = []
        for cx, s in zip(centers, steps):
            label = s["label"] if isinstance(s, dict) else s
            if has_icon:
                self.parts.append(
                    icon(s.get("icon", "default") if isinstance(s, dict) else "default", cx, y + 42, self.t["iconColor"])
                )
                self.parts.append(text_block(cx, y + 86, [label], 13))
                half.append(28)
            else:
                w = min(140, slot - 48)
                self.node(cx - w / 2, y + 16, w, NODE_H, s, self.t["nodeFill"], rx=2)
                half.append(w / 2)
        ay = y + (42 if has_icon else 36)
        for i in range(n - 1):
            self.arrow_line(centers[i] + half[i] + 8, ay, centers[i + 1] - half[i + 1] - 8, ay)
        return h

    def row_container(self, row: dict, y: float) -> float:
        pad = 16
        inner_y = y + pad
        x0, x1 = self.cx0 + pad, self.cx1 - pad
        body: list[str] = []
        saved, self.parts = self.parts, body
        if row.get("title"):
            self.parts.append(text_block(x0, inner_y + 8, [row["title"]], 14, weight="bold", anchor="start"))
            inner_y += 26
        for ch in row.get("children", []):
            t = ch.get("type")
            if t == "flow":
                inner_y += self.child_flow(ch, x0, x1, inner_y)
            elif t == "panel":
                inner_y += self.row_panel(ch, inner_y, x0, x1)
            else:
                inner_y += self.child_nodes(ch, x0, x1, inner_y, dashed=ch.get("dashed", False))
            inner_y += ROW_GAP
        self.parts = saved
        h = inner_y - ROW_GAP + pad - y
        self.rect(self.cx0, y, self.cw, h, self.t["containerFill"])
        self.parts.extend(body)
        return h

    # --- 总装 ---
    def render(self) -> str:
        t, W = self.t, self.W
        y = TOP
        if self.m.get("title"):
            self.rect(MARGIN, y, W - 2 * MARGIN, TITLE_H, t["titleFill"])
            self.parts.append(text_block(W / 2, y + TITLE_H / 2, [self.m["title"]], 18, weight="500"))
            y += TITLE_H + LAYER_GAP
        layers_top = y
        handlers = {
            "entry": self.row_entry,
            "banner": self.row_banner,
            "cards": self.row_cards,
            "panel": self.row_panel,
            "container": self.row_container,
        }
        for li, layer in enumerate(self.m.get("layers", [])):
            self.parts.append(f"<!-- 层级{li + 1}：{escape(layer.get('label', ''))} -->")
            ly = y
            for row in layer.get("rows", []):
                fn = handlers.get(row.get("type"))
                if not fn:
                    print(f"[warn] 未知行类型 {row.get('type')}", file=sys.stderr)
                    continue
                y += fn(row, y) + ROW_GAP
            y -= ROW_GAP
            if layer.get("label"):
                self.rect(MARGIN, ly, LABEL_W, y - ly, t["labelFill"], rx=4)
                self.parts.append(vertical_text(MARGIN + LABEL_W / 2, (ly + y) / 2, layer["label"], 15, y - ly))
            y += LAYER_GAP
        y -= LAYER_GAP
        if self.m.get("sideBar"):
            sb = self.m["sideBar"]
            sx = W - MARGIN - SIDE_W
            self.parts.append("<!-- 右侧支撑栏 -->")
            self.rect(sx, layers_top, SIDE_W, y - layers_top, t["sideFill"], rx=4)
            self.parts.append(vertical_text(sx + SIDE_W / 2, (layers_top + y) / 2, sb["title"], 15, y - layers_top))
        if self.m.get("base"):
            y += LAYER_GAP
            self.parts.append("<!-- 底部基座 -->")
            self.rect(MARGIN, y, W - 2 * MARGIN, BASE_H, t["baseFill"])
            self.parts.append(text_block(W / 2, y + BASE_H / 2, [self.m["base"]["text"]], 15))
            y += BASE_H
        self.parts.append("<!-- 连接线 -->")
        self.draw_connections()
        return self.wrap_svg(int(y + 24))
