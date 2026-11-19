"""ProcessOn 风格组织结构图 / WBS 树形图渲染器（diagram: "orgchart"）。

支持：
- 递归树形 JSON（root -> children），自动计算子树宽度避免任何重叠
- 混合布局：高层级横向 T 型总线展开 + 底层多叶节点纵向列表总线（layout: "vertical" 或自动切换）
- 助理/参谋节点（assistants：从领导正下方主干侧向引出）
- 层级配色体系（根节点深色白字 -> 一级/二级浅色 -> 末级白底）与双行岗位/副标题卡片
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from core import BaseDiagram, lines_height, text_block, text_width, wrap

MARGIN_X = 40
MARGIN_Y = 24
TITLE_H = 44
TITLE_GAP = 24
H_GAP = 22          # 同级横向子树间距
V_GAP = 38          # 父子节点纵向层间距
V_LEAF_GAP = 12     # 纵向叶列表节点间距
V_BUS_INDENT = 20   # 纵向列表相对左侧主干的缩进
ASST_GAP_X = 24     # 助理节点距主干的水平间距
ASST_ROW_H = 56     # 助理区占用的额外垂直高度
STROKE_W = 1.3


class OrgChartDiagram(BaseDiagram):
    def __init__(self, model: dict):
        super().__init__(model, default_width=1200)
        if not model.get("root"):
            raise ValueError("组织结构图必须提供 root 节点")
        self.root = model["root"]

    # --- 节点测量 ---
    def _measure_node(self, node: dict, depth: int) -> tuple[float, float, list[str], list[str]]:
        name = str(node.get("name", node.get("label", "")))
        sub = str(node.get("subtitle", node.get("role", "")) or "")
        fs_title = 15.0 if depth == 0 else 14.0
        fs_sub = 12.0
        raw_w = max(text_width(name, fs_title), text_width(sub, fs_sub)) + 30
        w = float(node.get("width") or min(186.0, max(124.0, raw_w)))
        tlines = wrap(name, w - 20, fs_title, max_lines=2)
        slines = wrap(sub, w - 20, fs_sub, max_lines=2) if sub else []
        th = lines_height(len(tlines), fs_title)
        sh = (lines_height(len(slines), fs_sub) + 4) if slines else 0
        h = float(node.get("height") or max(44.0 if not slines else 58.0, th + sh + 20.0))
        return w, h, tlines, slines

    def _use_vertical(self, node: dict, depth: int) -> bool:
        children = node.get("children") or []
        if not children:
            return False
        explicit = node.get("layout")
        if explicit == "vertical":
            return True
        if explicit == "horizontal":
            return False
        # 默认：深度 >= 2 且有 >= 3 个全叶子节点时自动转为紧凑纵向列表
        all_leaves = all(not (c.get("children") or c.get("assistants")) for c in children)
        return depth >= 2 and len(children) >= 3 and all_leaves

    def _build_layout(self, node: dict, depth: int = 0) -> dict:
        w, h, tlines, slines = self._measure_node(node, depth)
        children = node.get("children") or []
        assistants = node.get("assistants") or []
        asst_nodes = []
        asst_extra_h = 0.0
        asst_right_w = 0.0
        if assistants:
            for a in assistants:
                aw, ah, atl, asl = self._measure_node(a, depth + 1)
                asst_nodes.append({"raw": a, "w": aw, "h": ah, "tlines": atl, "slines": asl, "depth": depth + 1})
                asst_right_w = max(asst_right_w, ASST_GAP_X + aw)
            asst_extra_h = sum(a["h"] + 10 for a in asst_nodes) + 12

        vertical = self._use_vertical(node, depth)
        child_layouts = [self._build_layout(c, depth + 1) for c in children]

        if not child_layouts:
            sub_w = max(w, w / 2 + asst_right_w) if asst_nodes else w
            sub_h = h + asst_extra_h
            anchor_x = w / 2
        elif vertical:
            max_cw = max(c["sub_w"] for c in child_layouts)
            stack_w = V_BUS_INDENT + max_cw
            sub_w = max(w, stack_w, (w / 2 + asst_right_w) if asst_nodes else 0)
            stack_h = sum(c["sub_h"] for c in child_layouts) + V_LEAF_GAP * (len(child_layouts) - 1)
            sub_h = h + asst_extra_h + 22 + stack_h
            anchor_x = w / 2
        else:
            total_cw = sum(c["sub_w"] for c in child_layouts) + H_GAP * (len(child_layouts) - 1)
            # 父节点中心对齐于第一个与最后一个子节点锚点的中点
            first_cx = child_layouts[0]["anchor_x"]
            last_cx = total_cw - child_layouts[-1]["sub_w"] + child_layouts[-1]["anchor_x"]
            mid_cx = (first_cx + last_cx) / 2
            left_need = max(mid_cx, w / 2)
            right_need = max(total_cw - mid_cx, w / 2, asst_right_w)
            sub_w = left_need + right_need
            anchor_x = left_need
            sub_h = h + asst_extra_h + V_GAP + max(c["sub_h"] for c in child_layouts)

        return {
            "raw": node,
            "depth": depth,
            "w": w,
            "h": h,
            "tlines": tlines,
            "slines": slines,
            "assistants": asst_nodes,
            "asst_extra_h": asst_extra_h,
            "vertical": vertical,
            "children": child_layouts,
            "sub_w": sub_w,
            "sub_h": sub_h,
            "anchor_x": anchor_x,
        }

    # --- 节点与总线绘制 ---
    def _draw_card(self, item: dict, cx: float, y: float):
        raw = item["raw"]
        w, h, depth = item["w"], item["h"], item["depth"]
        x = cx - w / 2
        stroke = self.t["stroke"]
        da = ' stroke-dasharray="6 4"' if raw.get("variant") == "external" else ""

        if raw.get("fill"):
            fill = raw["fill"]
            is_dark = False
        elif raw.get("variant") == "highlight":
            fill = self.t["orgRootFill"]
            is_dark = True
        elif depth == 0:
            fill = self.t["orgRootFill"]
            is_dark = True
        elif depth == 1:
            fill = self.t["orgLevel1Fill"]
            is_dark = False
        elif depth == 2:
            fill = self.t["orgLevel2Fill"]
            is_dark = False
        else:
            fill = self.t["nodeFill"]
            is_dark = False

        self.parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="5" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{STROKE_W}"{da}/>'
        )
        tcolor = "#FFFFFF" if is_dark else self.t["text"]
        scolor = "#EAF6F6" if is_dark else self.t["stroke"]
        fs_t = 15.0 if depth == 0 else 14.0
        tlines, slines = item["tlines"], item["slines"]

        if slines:
            th = lines_height(len(tlines), fs_t)
            sh = lines_height(len(slines), 12.0)
            top = y + (h - (th + sh + 4)) / 2
            self._draw_lines(cx, top + th / 2, tlines, fs_t, tcolor, weight="bold")
            self._draw_lines(cx, top + th + 4 + sh / 2, slines, 12.0, scolor, weight=None)
        else:
            self._draw_lines(cx, y + h / 2, tlines, fs_t, tcolor, weight="bold" if depth <= 1 else None)

        if raw.get("id"):
            self.nodes[raw["id"]] = (x, y, w, h)

    def _draw_lines(self, cx: float, cy: float, lines: list[str], fs: float, fill: str, weight: str | None):
        lh = fs * 1.32
        start = cy - (len(lines) - 1) * lh / 2 + fs * 0.35
        w = f' font-weight="{weight}"' if weight else ""
        for i, line in enumerate(lines):
            self.parts.append(
                f'<text x="{cx:.1f}" y="{start + i * lh:.1f}" font-size="{fs}" '
                f'text-anchor="middle" style="fill:{fill}"{w}>{escape(line)}</text>'
            )

    def _draw_tree(self, item: dict, left_x: float, top_y: float):
        lc = self.t["lineColor"]
        cx = left_x + item["anchor_x"]
        self._draw_card(item, cx, top_y)
        trunk_top = top_y + item["h"]

        # 绘制助理节点（从主干右侧分支引出）
        cur_y = trunk_top
        if item["assistants"]:
            ay = trunk_top + 12
            last_ay = trunk_top
            for a in item["assistants"]:
                acx = cx + ASST_GAP_X + a["w"] / 2
                acy = ay + a["h"] / 2
                self.parts.append(f'<line x1="{cx:.1f}" y1="{acy:.1f}" x2="{cx + ASST_GAP_X:.1f}" y2="{acy:.1f}" stroke="{lc}" stroke-width="1.2"/>')
                self._draw_card(a, acx, ay)
                last_ay = acy
                ay += a["h"] + 10
            if not item["children"]:
                self.parts.append(f'<line x1="{cx:.1f}" y1="{trunk_top:.1f}" x2="{cx:.1f}" y2="{last_ay:.1f}" stroke="{lc}" stroke-width="1.2"/>')
            cur_y = trunk_top + item["asst_extra_h"]

        children = item["children"]
        if not children:
            return

        if item["vertical"]:
            # 纵向叶列表：左侧竖直总线 + 横向短支线
            bus_x = left_x + 10
            # 从父节点底中心先下移一点再折向 bus_x，或直接当 bus_x 在父节点范围内垂直下行
            cy_start = cur_y + 22
            if abs(cx - bus_x) > 1:
                mid_y = cur_y + 11
                self.parts.append(
                    f'<path d="M{cx:.1f},{trunk_top:.1f} V{mid_y:.1f} H{bus_x:.1f}" stroke="{lc}" stroke-width="1.2" fill="none"/>'
                )
                bus_top = mid_y
            else:
                bus_top = trunk_top
            cy = cy_start
            last_cy = cy
            for c in children:
                child_cx = left_x + V_BUS_INDENT + c["w"] / 2
                tick_y = cy + c["h"] / 2
                self.parts.append(
                    f'<line x1="{bus_x:.1f}" y1="{tick_y:.1f}" x2="{left_x + V_BUS_INDENT:.1f}" y2="{tick_y:.1f}" stroke="{lc}" stroke-width="1.2"/>'
                )
                self._draw_card(c, child_cx, cy)
                last_cy = tick_y
                cy += c["sub_h"] + V_LEAF_GAP
            self.parts.append(f'<line x1="{bus_x:.1f}" y1="{bus_top:.1f}" x2="{bus_x:.1f}" y2="{last_cy:.1f}" stroke="{lc}" stroke-width="1.2"/>')
        else:
            # 横向 T 型总线展开
            total_cw = sum(c["sub_w"] for c in children) + H_GAP * (len(children) - 1)
            first_cx = children[0]["anchor_x"]
            last_cx = total_cw - children[-1]["sub_w"] + children[-1]["anchor_x"]
            mid_cx = (first_cx + last_cx) / 2
            c_left = cx - mid_cx
            child_y = cur_y + V_GAP
            bus_y = cur_y + V_GAP / 2

            # 父节点竖干到总线
            self.parts.append(f'<line x1="{cx:.1f}" y1="{trunk_top:.1f}" x2="{cx:.1f}" y2="{bus_y:.1f}" stroke="{lc}" stroke-width="1.2"/>')
            child_xs = []
            cur_x = c_left
            for c in children:
                child_xs.append(cur_x + c["anchor_x"])
                self._draw_tree(c, cur_x, child_y)
                cur_x += c["sub_w"] + H_GAP
            if len(child_xs) > 1:
                self.parts.append(
                    f'<line x1="{child_xs[0]:.1f}" y1="{bus_y:.1f}" x2="{child_xs[-1]:.1f}" y2="{bus_y:.1f}" stroke="{lc}" stroke-width="1.2"/>'
                )
            for ccx in child_xs:
                self.parts.append(f'<line x1="{ccx:.1f}" y1="{bus_y:.1f}" x2="{ccx:.1f}" y2="{child_y:.1f}" stroke="{lc}" stroke-width="1.2"/>')

    def render(self) -> str:
        t = self.t
        tree = self._build_layout(self.root, depth=0)
        min_w = int(tree["sub_w"] + 2 * MARGIN_X)
        self.W = max(self.W, min_w) if self.m.get("canvas", {}).get("w") else max(960, min_w)

        y = MARGIN_Y
        if self.m.get("title"):
            self.parts.append("<!-- 顶部标题 -->")
            self.rect(MARGIN_X, y, self.W - 2 * MARGIN_X, TITLE_H, t["titleFill"])
            self.parts.append(text_block(self.W / 2, y + TITLE_H / 2, [self.m["title"]], 17, weight="bold"))
            y += TITLE_H + TITLE_GAP

        self.parts.append("<!-- 组织结构树 -->")
        root_left = (self.W - tree["sub_w"]) / 2
        self._draw_tree(tree, root_left, y)

        if self.m.get("connections"):
            self.parts.append("<!-- 虚线汇报/协作连线 -->")
            self.draw_connections()

        return self.wrap_svg(int(y + tree["sub_h"] + MARGIN_Y + 8))
