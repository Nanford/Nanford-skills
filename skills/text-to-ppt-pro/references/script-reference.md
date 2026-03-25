# 程序化生成 PPT — 脚本参考

当用户需要直接生成可编辑的 `.pptx` 文件时，参考本文档。

---

## 路线选择

| 路线 | 技术栈 | 适合场景 |
|------|--------|---------|
| **路线 A** | Python + python-pptx | 内容结构清晰、批量插入、与文档/知识库处理联动 |
| **路线 B** | Node.js + PptxGenJS | 精确布局控制、多图表图形、稳定生成器 |

---

## 推荐数据结构

先把 PPT 拆成结构化 JSON，再交给脚本层渲染：

```json
{
  "meta": {
    "title": "技术团队 AI 使用与落地教程",
    "theme": "dark_tech",
    "ratio": "16:9"
  },
  "slides": [
    {
      "type": "cover",
      "title": "技术团队 AI 使用与落地教程",
      "subtitle": "从会提问到建流程，全面提升 AI 生产力",
      "footer": "适用对象：研发、测试、产品、实施、售前",
      "notes": "讲师备注：先问受众目前用 AI 最多做什么……"
    },
    {
      "type": "two_column_compare",
      "title": "课程导读：为什么要做这次培训？",
      "left": [
        "最大的误区：把 AI 当成单一工具",
        "结果：团队容易走向两个极端"
      ],
      "right": [
        "不讲模型跑分榜单",
        "只讲如何用进真实工作"
      ],
      "notes": "讲师备注内容"
    }
  ]
}
```

---

## 页型函数化

为每种页型写一个函数，避免 28 页写 28 套逻辑：

```
render_cover(slide, data, theme)
render_transition(slide, data, theme)
render_four_cards(slide, data, theme)
render_two_column_compare(slide, data, theme)
render_process(slide, data, theme)
render_framework(slide, data, theme)
render_data(slide, data, theme)
render_summary(slide, data, theme)
```

---

## Python 脚本骨架（python-pptx）

```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

# 主题令牌化 — 所有色值集中配置
THEME = {
    "bg":     RGBColor(15, 23, 42),    # #0F172A
    "card":   RGBColor(22, 32, 51),    # #162033
    "title":  RGBColor(248, 250, 252), # #F8FAFC
    "body":   RGBColor(203, 213, 225), # #CBD5E1
    "accent": RGBColor(56, 189, 248),  # #38BDF8
}

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)


def add_full_bg(slide, color):
    shape = slide.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def add_title(slide, text, x=0.7, y=0.4, w=12.0, h=0.6, size=24):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    p = box.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = THEME["title"]
    p.alignment = PP_ALIGN.LEFT
    return box


def add_body_text(slide, lines, x, y, w, h, size=13):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(size)
        p.font.color.rgb = THEME["body"]
    return box


def render_cover(title, subtitle, footer=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_full_bg(slide, THEME["bg"])
    add_title(slide, title, x=0.9, y=1.7, w=10.5, h=0.8, size=28)
    add_body_text(slide, [subtitle], x=0.95, y=2.65, w=9.8, h=0.6, size=16)
    if footer:
        add_body_text(slide, [footer], x=0.95, y=6.55, w=7.8, h=0.3, size=9)
    return slide


# 使用示例
render_cover(
    "技术团队 AI 使用与落地教程",
    "从会提问到建流程，全面提升 AI 生产力",
    "适用对象：研发、测试、产品、实施、售前"
)
prs.save("output.pptx")
```

---

## Node.js 脚本骨架（PptxGenJS）

```javascript
const pptxgen = require('pptxgenjs');
const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE'; // 13.33 × 7.5 英寸

const theme = {
  bg:     '0F172A',
  card:   '162033',
  title:  'F8FAFC',
  body:   'CBD5E1',
  accent: '38BDF8'
};

function baseSlide() {
  const slide = pptx.addSlide();
  slide.background = { color: theme.bg };
  return slide;
}

function addTitle(slide, text, opts = {}) {
  slide.addText(text, {
    x: 0.8, y: 0.45, w: 11.5, h: 0.5,
    fontFace: 'Microsoft YaHei',
    fontSize: opts.size || 24,
    bold: true,
    color: theme.title,
    ...opts
  });
}

function renderTransition(title, subtitle) {
  const slide = baseSlide();
  slide.addText(title, {
    x: 2.0, y: 2.3, w: 9.2, h: 0.7,
    align: 'center',
    fontFace: 'Microsoft YaHei',
    fontSize: 28, bold: true, color: theme.title
  });
  slide.addText(subtitle, {
    x: 2.4, y: 3.15, w: 8.4, h: 0.4,
    align: 'center',
    fontFace: 'Microsoft YaHei',
    fontSize: 13, color: theme.body
  });
}

renderTransition('第一部分：认识 AI', '先把能力边界和选型逻辑讲清楚');
pptx.writeFile({ fileName: 'output.pptx' });
```

---

## 设计模式

1. **主题令牌化** — 所有颜色、字体、卡片样式集中配置，不写死在函数里
2. **页型函数化** — 每种常见页型写一个函数，换 JSON 数据就能重用渲染逻辑
3. **内容与样式分离** — 结构化数据负责内容，theme 和 render 函数负责样式
4. **备注单独写入** — 备注内容单独维护，不混在主文本字段里
5. **先生成，再巡检** — 程序化生成容易"技术正确但版式难看"，保留巡检环节

---

## 风险提醒

- 中文字体在不同机器上可能被替换，导致换行变化
- 同样长度的文字，在不同页型里可读性差异很大
- 复杂页不要迷信自动排版，必要时保留人工精修
- 一次性生成整套时，最容易出问题的是中后段页面密度失衡

---

## 最佳实践流程

```
1. 用 Skill 拆结构与页型（输出逐页规划表）
2. 脚本快速生成初稿（.pptx）
3. 一轮巡检和精修
```

这样效率和质量更平衡。
