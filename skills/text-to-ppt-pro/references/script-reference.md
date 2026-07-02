# 程序化生成 PPT — 完整脚本参考

技术栈：Python + python-pptx。本文件包含全部 13 种页型的渲染函数实现。

坐标参数与 `layout-specs.md` 对齐，直接使用，不需要重新计算。

---

## 目录

1. [基础设施：主题与工具函数](#基础设施)
2. [13 种页型渲染函数](#渲染函数)
3. [自动验证函数](#验证函数)
4. [主程序入口模板](#主程序)
5. [风险提醒](#风险提醒)

---

## 基础设施

```python
import json
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor

# ── 主题加载 ──────────────────────────────────────────────
def load_theme(theme_name, json_path="theme-presets.json"):
    """加载主题配置，将 hex 色值转为 RGBColor 对象，保留 is_light 布尔标识"""
    with open(json_path) as f:
        presets = json.load(f)
    raw = presets[theme_name]
    t = {}
    for k, v in raw.items():
        if k in ("name", "description"):
            continue
        if v is None:
            t[k] = None
        elif isinstance(v, bool):
            t[k] = v
        elif isinstance(v, str) and v.startswith("#"):
            t[k] = RGBColor.from_string(v[1:])
        elif isinstance(v, str) and v.startswith("rgba"):
            # rgba 色值退化为半透明灰，python-pptx 不支持透明度
            t[k] = RGBColor(148, 163, 184)
        else:
            t[k] = v
    return t

# ── 画布初始化 ────────────────────────────────────────────
def create_prs():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs

# ── 通用工具函数 ──────────────────────────────────────────
def add_bg(slide, prs, color):
    """全画布背景填充"""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()

def add_text(slide, text, x, y, w, h, size=13, bold=False, color=None,
             align=PP_ALIGN.LEFT, font_name="Microsoft YaHei"):
    """添加文本框，返回 shape 对象"""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.name = font_name
    if color:
        r.font.color.rgb = color
    return box

def add_card(slide, x, y, w, h, fill_color, theme=None, accent_bar=False, corner_radius=80000):
    """添加卡片背景。浅色主题自动加边框；accent_bar=True 时左侧加强调色条"""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.adjustments[0] = corner_radius / shape.width if shape.width else 0.02

    # 浅色主题：加可见边框
    if theme and theme.get("is_light") and theme.get("card_border"):
        shape.line.color.rgb = theme["card_border"]
        shape.line.width = Pt(0.75)
    else:
        shape.line.fill.background()

    # 可选：左侧强调色条（浅色主题下增加视觉层次）
    if accent_bar and theme and theme.get("accent"):
        bar = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(x), Inches(y), Inches(0.06), Inches(h)
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = theme["accent"]
        bar.line.fill.background()

    return shape

def add_line(slide, x1, y1, x2, y2, color, width_pt=1.0):
    """添加直线"""
    connector = slide.shapes.add_connector(
        1,  # msoConnectorStraight
        Inches(x1), Inches(y1), Inches(x2), Inches(y2)
    )
    connector.line.color.rgb = color
    connector.line.width = Pt(width_pt)
    return connector

def add_page_title(slide, title, theme, subtitle=None):
    """通用页面标题区"""
    add_text(slide, title, 0.7, 0.4, 11.9, 0.55,
             size=22, bold=True, color=theme["title"])
    if subtitle:
        add_text(slide, subtitle, 0.7, 0.95, 11.9, 0.35,
                 size=12, color=theme["muted"])

def add_footer(slide, page_num, theme, project_name=None):
    """通用页脚"""
    add_text(slide, str(page_num), 12.3, 7.0, 0.5, 0.25,
             size=9, color=theme["muted"], align=PP_ALIGN.RIGHT)
    if project_name:
        add_text(slide, project_name, 0.7, 7.0, 4.0, 0.25,
                 size=8, color=theme["muted"])

def add_notes(slide, notes_text):
    """写入备注区"""
    if notes_text:
        slide.notes_slide.notes_text_frame.text = notes_text

def new_slide(prs, theme):
    """创建空白幻灯片并填充背景"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白布局
    add_bg(slide, prs, theme["background"])
    return slide
```

---

## 渲染函数

### 1. `render_cover`

```python
def render_cover(prs, theme, data, page_num=None):
    """封面页：大标题 + 副标题 + 页脚信息"""
    slide = new_slide(prs, theme)
    add_text(slide, data["title"], 1.2, 2.4, 10.9, 0.9,
             size=32, bold=True, color=theme["title"], align=PP_ALIGN.CENTER)
    if data.get("subtitle"):
        add_text(slide, data["subtitle"], 1.8, 3.5, 9.7, 0.5,
                 size=15, color=theme["body"], align=PP_ALIGN.CENTER)
    if data.get("footer"):
        add_text(slide, data["footer"], 1.8, 6.2, 9.7, 0.35,
                 size=10, color=theme["muted"], align=PP_ALIGN.CENTER)
    add_notes(slide, data.get("notes"))
    return slide
```

### 2. `render_intro`

```python
def render_intro(prs, theme, data, page_num=1):
    """导读页：左右对照"""
    slide = new_slide(prs, theme)
    add_page_title(slide, data["title"], theme)

    # 左栏 — 问题/现状
    add_card(slide, 0.7, 1.5, 5.6, 5.0, theme["card"], theme=theme)
    left_title = data.get("left_title", "现状与问题")
    add_text(slide, left_title, 1.0, 1.65, 5.0, 0.35,
             size=15, bold=True, color=theme["warning"])
    for i, item in enumerate(data.get("left", [])):
        add_text(slide, f"• {item}", 1.0, 2.2 + i * 0.55, 5.0, 0.45,
                 size=12, color=theme["body"])

    # 右栏 — 目标/收益
    add_card(slide, 6.6, 1.5, 5.7, 5.0, theme["card"], theme=theme)
    right_title = data.get("right_title", "本次目标")
    add_text(slide, right_title, 6.9, 1.65, 5.1, 0.35,
             size=15, bold=True, color=theme["accent"])
    for i, item in enumerate(data.get("right", [])):
        add_text(slide, f"• {item}", 6.9, 2.2 + i * 0.55, 5.1, 0.45,
                 size=12, color=theme["body"])

    add_footer(slide, page_num, theme)
    add_notes(slide, data.get("notes"))
    return slide
```

### 3. `render_toc`

```python
def render_toc(prs, theme, data, page_num=1):
    """目录页：编号 + 标题 + 描述"""
    slide = new_slide(prs, theme)
    add_page_title(slide, data.get("title", "目录"), theme)

    chapters = data.get("chapters", [])
    n = len(chapters)
    spacing = {3: 1.5, 4: 1.2, 5: 1.0, 6: 0.85}.get(n, 1.0)

    for i, ch in enumerate(chapters):
        y = 1.5 + i * spacing
        highlight = i == data.get("active_index", -1)
        num_color = theme["accent"] if highlight else theme["muted"]
        text_color = theme["accent"] if highlight else theme["title"]

        add_text(slide, f"{i+1:02d}", 0.7, y, 0.6, 0.5,
                 size=20, bold=True, color=num_color)
        add_text(slide, ch["title"], 1.4, y, 4.0, 0.5,
                 size=16, bold=True, color=text_color)
        if ch.get("desc"):
            add_text(slide, ch["desc"], 5.6, y + 0.05, 7.0, 0.45,
                     size=11, color=theme["body"])

    add_footer(slide, page_num, theme)
    add_notes(slide, data.get("notes"))
    return slide
```

### 4. `render_transition`

```python
def render_transition(prs, theme, data, page_num=1):
    """章节过渡页：居中大字"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide, prs, theme.get("background_alt", theme["background"]))

    section_num = data.get("section_num", "01")
    add_text(slide, f"{section_num} /", 2.0, 2.2, 9.3, 0.5,
             size=16, color=theme["accent"], align=PP_ALIGN.CENTER)
    add_text(slide, data["title"], 2.0, 2.9, 9.3, 0.7,
             size=28, bold=True, color=theme["title"], align=PP_ALIGN.CENTER)
    if data.get("subtitle"):
        add_text(slide, data["subtitle"], 2.5, 3.8, 8.3, 0.4,
                 size=13, color=theme["body"], align=PP_ALIGN.CENTER)

    add_notes(slide, data.get("notes"))
    return slide
```

### 5. `render_four_grid`

```python
def render_four_grid(prs, theme, data, page_num=1):
    """四宫格认知页：2×2 卡片"""
    slide = new_slide(prs, theme)
    add_page_title(slide, data["title"], theme)

    positions = [
        (0.7, 1.5, 5.6, 2.4),   # 左上
        (6.6, 1.5, 5.7, 2.4),   # 右上
        (0.7, 4.15, 5.6, 2.4),  # 左下
        (6.6, 4.15, 5.7, 2.4),  # 右下
    ]

    cards = data.get("cards", [])
    for i, (x, y, w, h) in enumerate(positions):
        if i >= len(cards):
            break
        card = cards[i]
        add_card(slide, x, y, w, h, theme["card"], theme=theme)
        add_text(slide, card["title"], x + 0.25, y + 0.2, w - 0.5, 0.35,
                 size=15, bold=True, color=theme["accent"])
        add_text(slide, card.get("body", ""), x + 0.25, y + 0.65, w - 0.5, h - 0.9,
                 size=11, color=theme["body"])

    add_footer(slide, page_num, theme)
    add_notes(slide, data.get("notes"))
    return slide
```

### 6. `render_comparison`

```python
def render_comparison(prs, theme, data, page_num=1):
    """对比页：左右双栏"""
    slide = new_slide(prs, theme)
    add_page_title(slide, data["title"], theme)

    # 左栏
    add_card(slide, 0.7, 1.5, 5.6, 5.2, theme["card"], theme=theme)
    add_text(slide, data.get("left_title", "现状"), 1.0, 1.7, 5.0, 0.35,
             size=16, bold=True, color=theme.get("danger", theme["warning"]))
    for i, item in enumerate(data.get("left", [])):
        add_text(slide, f"• {item}", 1.0, 2.3 + i * 0.6, 5.0, 0.5,
                 size=12, color=theme["body"])

    # 右栏
    add_card(slide, 6.6, 1.5, 5.7, 5.2, theme["card"], theme=theme)
    add_text(slide, data.get("right_title", "目标"), 6.9, 1.7, 5.1, 0.35,
             size=16, bold=True, color=theme["accent"])
    for i, item in enumerate(data.get("right", [])):
        add_text(slide, f"• {item}", 6.9, 2.3 + i * 0.6, 5.1, 0.5,
                 size=12, color=theme["body"])

    add_footer(slide, page_num, theme)
    add_notes(slide, data.get("notes"))
    return slide
```

### 7. `render_process`

```python
def render_process(prs, theme, data, page_num=1):
    """流程页：横向步骤链"""
    slide = new_slide(prs, theme)
    add_page_title(slide, data["title"], theme)

    steps = data.get("steps", [])
    n = len(steps)
    specs = {
        3: {"node_w": 3.2, "gap": 0.8},
        4: {"node_w": 2.5, "gap": 0.5},
        5: {"node_w": 2.0, "gap": 0.35},
        6: {"node_w": 1.65, "gap": 0.3},
    }
    s = specs.get(n, specs[min(n, 6)])
    node_w = s["node_w"]
    gap = s["gap"]

    for i, step in enumerate(steps):
        x = 0.7 + i * (node_w + gap)
        # 编号圆圈
        circle_size = 0.45
        cx = x + (node_w - circle_size) / 2
        circle = slide.shapes.add_shape(
            MSO_SHAPE.OVAL, Inches(cx), Inches(2.2), Inches(circle_size), Inches(circle_size)
        )
        circle.fill.solid()
        circle.fill.fore_color.rgb = theme["accent"]
        circle.line.fill.background()
        # 圆圈内数字
        tf = circle.text_frame
        tf.word_wrap = False
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = str(i + 1)
        r.font.size = Pt(14)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE

        # 步骤名
        add_text(slide, step["name"], x, 2.8, node_w, 0.4,
                 size=13, bold=True, color=theme["title"], align=PP_ALIGN.CENTER)
        # 步骤说明
        if step.get("desc"):
            add_text(slide, step["desc"], x, 3.25, node_w, 0.8,
                     size=10, color=theme["body"], align=PP_ALIGN.CENTER)

        # 箭头连接线（非最后一个步骤）
        if i < n - 1:
            arrow_x1 = x + node_w
            arrow_x2 = arrow_x1 + gap
            arrow_y = 2.2 + circle_size / 2
            add_line(slide, arrow_x1, arrow_y, arrow_x2, arrow_y,
                     theme.get("line", theme["muted"]), 1.5)

    add_footer(slide, page_num, theme)
    add_notes(slide, data.get("notes"))
    return slide
```

### 8. `render_method`

```python
def render_method(prs, theme, data, page_num=1):
    """方法步骤页：编号 + 步骤名 + 说明"""
    slide = new_slide(prs, theme)
    add_page_title(slide, data["title"], theme)

    steps = data.get("steps", [])
    n = len(steps)
    step_h = {3: 1.4, 4: 1.1, 5: 0.85}.get(n, 0.85)
    gap = 0.15

    for i, step in enumerate(steps):
        y = 1.5 + i * (step_h + gap)
        # 底部卡片
        add_card(slide, 0.7, y, 11.9, step_h, theme["card"], theme=theme, accent_bar=True)
        # 编号
        add_text(slide, f"{i+1:02d}", 0.9, y + 0.15, 0.8, step_h - 0.3,
                 size=20, bold=True, color=theme["accent"])
        # 分隔线
        add_line(slide, 1.5, y + 0.15, 1.5, y + step_h - 0.15,
                 theme.get("line", theme["muted"]), 1.0)
        # 步骤名
        add_text(slide, step["name"], 1.7, y + 0.15, 2.8, step_h - 0.3,
                 size=14, bold=True, color=theme["title"])
        # 说明
        if step.get("desc"):
            add_text(slide, step["desc"], 4.8, y + 0.15, 7.5, step_h - 0.3,
                     size=11, color=theme["body"])

    add_footer(slide, page_num, theme)
    add_notes(slide, data.get("notes"))
    return slide
```

### 9. `render_framework`

```python
def render_framework(prs, theme, data, page_num=1):
    """框架模型页：分层横条卡片"""
    slide = new_slide(prs, theme)
    add_page_title(slide, data["title"], theme)

    layers = data.get("layers", [])
    n = len(layers)
    layer_h = {2: 2.2, 3: 1.4, 4: 1.0}.get(n, 1.0)
    gap = {2: 0.3, 3: 0.25, 4: 0.2}.get(n, 0.2)

    for i, layer in enumerate(layers):
        y = 1.5 + i * (layer_h + gap)
        add_card(slide, 0.7, y, 11.9, layer_h, theme["card"], theme=theme, accent_bar=True)
        add_text(slide, layer["name"], 1.0, y + 0.15, 2.3, layer_h - 0.3,
                 size=14, bold=True, color=theme["accent"])
        if layer.get("desc"):
            add_text(slide, layer["desc"], 3.5, y + 0.15, 8.8, layer_h - 0.3,
                     size=11, color=theme["body"])

    add_footer(slide, page_num, theme)
    add_notes(slide, data.get("notes"))
    return slide
```

### 10. `render_case_study`

```python
def render_case_study(prs, theme, data, page_num=1):
    """案例页：三栏（问题-动作-结果）"""
    slide = new_slide(prs, theme)
    add_page_title(slide, data["title"], theme)

    columns = [
        {"x": 0.7, "w": 3.7, "label": data.get("col1_title", "问题"),
         "content": data.get("problem", ""), "color": theme["warning"]},
        {"x": 4.7, "w": 3.7, "label": data.get("col2_title", "动作"),
         "content": data.get("action", ""), "color": theme["accent"]},
        {"x": 8.7, "w": 3.9, "label": data.get("col3_title", "结果"),
         "content": data.get("result", ""), "color": theme.get("accent_2", theme["accent"])},
    ]

    for col in columns:
        add_card(slide, col["x"], 1.5, col["w"], 5.0, theme["card"], theme=theme)
        add_text(slide, col["label"], col["x"] + 0.25, 1.7, col["w"] - 0.5, 0.35,
                 size=14, bold=True, color=col["color"])
        add_text(slide, col["content"], col["x"] + 0.25, 2.2, col["w"] - 0.5, 4.0,
                 size=11, color=theme["body"])

    add_footer(slide, page_num, theme)
    add_notes(slide, data.get("notes"))
    return slide
```

### 11. `render_data`

```python
def render_data(prs, theme, data, page_num=1):
    """数据结论页：结论 + KPI 卡片 + 说明区"""
    slide = new_slide(prs, theme)
    add_page_title(slide, data["title"], theme)

    # 结论短句
    add_text(slide, data.get("conclusion", ""), 0.7, 1.2, 11.9, 0.45,
             size=14, bold=True, color=theme["title"])

    # KPI 卡片
    kpis = data.get("kpis", [])
    n = len(kpis)
    kpi_positions = {
        1: [(4.67, 4.0)],
        2: [(0.7, 5.5), (6.6, 5.5)],
        3: [(0.7, 3.6), (4.55, 3.6), (8.4, 3.6)],
    }
    positions = kpi_positions.get(n, kpi_positions[3][:n])

    for i, kpi in enumerate(kpis):
        if i >= len(positions):
            break
        x, w = positions[i]
        add_card(slide, x, 1.85, w, 1.2, theme["card"], theme=theme)
        add_text(slide, kpi["value"], x + 0.2, 1.9, w - 0.4, 0.6,
                 size=28, bold=True, color=theme["accent"], align=PP_ALIGN.CENTER)
        add_text(slide, kpi.get("label", ""), x + 0.2, 2.55, w - 0.4, 0.35,
                 size=10, color=theme["muted"], align=PP_ALIGN.CENTER)

    # 说明区
    if data.get("body"):
        add_text(slide, data["body"], 0.7, 3.4, 11.9, 3.2,
                 size=11, color=theme["body"])

    add_footer(slide, page_num, theme)
    add_notes(slide, data.get("notes"))
    return slide
```

### 12. `render_summary`

```python
def render_summary(prs, theme, data, page_num=1):
    """总结页：3 条结论/建议卡片"""
    slide = new_slide(prs, theme)
    add_page_title(slide, data["title"], theme)

    points = data.get("points", [])
    n = len(points)

    if n <= 2:
        positions = [(0.7, 5.6), (6.6, 5.7)]
    else:
        positions = [(0.7, 3.7), (4.65, 3.7), (8.6, 3.7)]

    for i, point in enumerate(points):
        if i >= len(positions):
            break
        x, w = positions[i]
        add_card(slide, x, 1.6, w, 4.8, theme["card"], theme=theme, accent_bar=True)
        add_text(slide, f"{i+1:02d}", x + 0.3, 1.85, 0.6, 0.5,
                 size=24, bold=True, color=theme["accent"])
        add_text(slide, point["title"], x + 0.3, 2.4, w - 0.6, 0.4,
                 size=14, bold=True, color=theme["title"])
        if point.get("desc"):
            add_text(slide, point["desc"], x + 0.3, 2.85, w - 0.6, 3.2,
                     size=11, color=theme["body"])

    add_footer(slide, page_num, theme)
    add_notes(slide, data.get("notes"))
    return slide
```

### 13. `render_closing`

```python
def render_closing(prs, theme, data, page_num=1):
    """致谢页：居中感谢语"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide, prs, theme.get("background_alt", theme["background"]))

    add_text(slide, data.get("thanks", "谢谢"), 2.0, 2.5, 9.3, 0.7,
             size=28, bold=True, color=theme["title"], align=PP_ALIGN.CENTER)
    if data.get("contact"):
        add_text(slide, data["contact"], 2.5, 3.6, 8.3, 0.8,
                 size=12, color=theme["body"], align=PP_ALIGN.CENTER)
    if data.get("qa_hint"):
        add_text(slide, data["qa_hint"], 2.5, 4.8, 8.3, 0.4,
                 size=14, color=theme["muted"], align=PP_ALIGN.CENTER)

    add_notes(slide, data.get("notes"))
    return slide
```

---

## 验证函数

```python
SAFE_AREA = {
    "left": 0.55, "right": 0.55,
    "top": 0.4, "bottom": 0.65
}
MIN_FONT = {"body": 10.5, "title": 16}
MAX_CHARS_PER_SLIDE = 120

def validate_slide(slide, prs, slide_num):
    """验证单页排版质量，返回问题列表"""
    issues = []
    canvas_w = prs.slide_width.inches
    canvas_h = prs.slide_height.inches
    total_chars = 0

    for shape in slide.shapes:
        # 边界检查
        left = shape.left.inches if hasattr(shape.left, 'inches') else shape.left / 914400
        top = shape.top.inches if hasattr(shape.top, 'inches') else shape.top / 914400
        right = left + (shape.width.inches if hasattr(shape.width, 'inches') else shape.width / 914400)
        bottom = top + (shape.height.inches if hasattr(shape.height, 'inches') else shape.height / 914400)

        if left < SAFE_AREA["left"] - 0.05:
            issues.append(f"页{slide_num}: 元素左侧超出安全区 (x={left:.2f})")
        if right > canvas_w - SAFE_AREA["right"] + 0.05:
            issues.append(f"页{slide_num}: 元素右侧超出安全区 (x+w={right:.2f})")
        if top < SAFE_AREA["top"] - 0.05:
            issues.append(f"页{slide_num}: 元素顶部超出安全区 (y={top:.2f})")
        if bottom > canvas_h - SAFE_AREA["bottom"] + 0.05:
            issues.append(f"页{slide_num}: 元素底部超出安全区 (y+h={bottom:.2f})")

        # 字号检查
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    total_chars += len(run.text)
                    if run.font.size:
                        pt = run.font.size.pt
                        if run.font.bold and pt < MIN_FONT["title"]:
                            pass  # 标题类文本不强制检查（编号等可能小于16pt）
                        elif not run.font.bold and pt < MIN_FONT["body"]:
                            issues.append(
                                f"页{slide_num}: 正文字号 {pt}pt 低于最小值 {MIN_FONT['body']}pt"
                            )

    if total_chars > MAX_CHARS_PER_SLIDE:
        issues.append(
            f"页{slide_num}: 总字数 {total_chars} 超过 {MAX_CHARS_PER_SLIDE} 字上限"
        )

    return issues


def validate_all(prs):
    """验证整套 PPT"""
    all_issues = []
    for i, slide in enumerate(prs.slides):
        all_issues.extend(validate_slide(slide, prs, i + 1))

    # 连续版式检查（简化：检查连续 5 页 shape 数量完全一致）
    shape_counts = [len(s.shapes) for s in prs.slides]
    for i in range(len(shape_counts) - 4):
        window = shape_counts[i:i+5]
        if len(set(window)) == 1:
            all_issues.append(f"页{i+1}–{i+5}: 连续 5 页 shape 数量相同，版式可能重复")

    if not all_issues:
        print("✓ 全部通过")
    else:
        for issue in all_issues:
            print(f"⚠ {issue}")
    return all_issues
```

---

## 主程序

```python
# ── 渲染器注册表 ──────────────────────────────────────────
RENDERERS = {
    "cover": render_cover,
    "intro": render_intro,
    "toc": render_toc,
    "transition": render_transition,
    "four-grid": render_four_grid,
    "comparison": render_comparison,
    "process": render_process,
    "method": render_method,
    "framework": render_framework,
    "case-study": render_case_study,
    "data": render_data,
    "summary": render_summary,
    "closing": render_closing,
}

def generate_pptx(slides_data, theme_name="dark_tech", output_path="output.pptx"):
    """主入口：接收逐页数据，生成 .pptx 文件"""
    prs = create_prs()
    theme = load_theme(theme_name)

    for i, slide_data in enumerate(slides_data):
        page_type = slide_data["type"]
        renderer = RENDERERS.get(page_type)
        if renderer is None:
            print(f"⚠ 未知页型: {page_type}，跳过第 {i+1} 页")
            continue
        renderer(prs, theme, slide_data, page_num=i + 1)

    # 验证
    issues = validate_all(prs)

    # 保存
    prs.save(output_path)
    print(f"✓ 已保存: {output_path} ({len(prs.slides)} 页)")
    return issues
```

### 输入数据结构示例

```json
[
  {
    "type": "cover",
    "title": "技术团队 AI 使用与落地教程",
    "subtitle": "从会提问到建流程，全面提升 AI 生产力",
    "footer": "适用对象：研发、测试、产品",
    "notes": "讲师备注：先问受众目前用 AI 做什么"
  },
  {
    "type": "comparison",
    "title": "课程导读：为什么要做这次培训？",
    "left_title": "常见误区",
    "left": ["把 AI 当搜索引擎", "只会问一句话", "不敢在工作中用"],
    "right_title": "本次目标",
    "right": ["建立 AI 协作思维", "掌握结构化提问", "落地 3 个工作场景"],
    "notes": "讲师备注内容"
  },
  {
    "type": "four-grid",
    "title": "AI 能力四象限",
    "cards": [
      {"title": "文本生成", "body": "报告、邮件、方案的起草与润色"},
      {"title": "数据分析", "body": "表格处理、趋势提取、异常检测"},
      {"title": "代码辅助", "body": "代码生成、调试、重构、文档化"},
      {"title": "知识问答", "body": "专业咨询、流程查询、技术解释"}
    ],
    "notes": "这四个象限不是互斥的..."
  },
  {
    "type": "process",
    "title": "AI 协作的标准流程",
    "steps": [
      {"name": "明确目标", "desc": "想清楚要什么"},
      {"name": "构建提示", "desc": "用结构化方式提问"},
      {"name": "迭代优化", "desc": "多轮对话精修"},
      {"name": "验证输出", "desc": "人工审核与修正"}
    ],
    "notes": "强调这不是线性流程，而是循环"
  }
]
```

---

## 风险提醒

- 中文字体在不同机器上可能被替换，导致换行位置变化。建议统一使用微软雅黑（Windows 内置）
- python-pptx 的圆角矩形 `adjustments` 参数是比例值而非绝对像素，不同尺寸的卡片圆角视觉效果可能不一致
- 连接线（connector）在某些 PPT 版本中渲染位置可能偏移，用简单直线替代更稳定
- 一次性生成 20+ 页时，中后段页面最容易出现密度失衡，建议生成后执行 `validate_all` 检查
