---
name: hootoolai-ppt
description: 创建具有多主题支持、现代美学和Bento Grid布局风格的企业级HTML演示文稿，并自动调用图片生成/图标工具为幻灯片配图。支持6种配色主题（赛博暗夜/科技蓝/简洁汇报/暖光办公/软件公司/极简白），输出HTML文件+配套素材资源文件夹（配图、图标、SVG等）。浏览器打开即可按键翻页演示，零外部依赖。当用户提到"生成PPT"、"做演示文稿"、"创建幻灯片"、"做presentation"、"做汇报材料"、"做slides"，或提供了一段内容希望制作成PPT/演示文稿时，必须触发此Skill。即使用户只是提供了文字内容并暗示需要视觉化呈现，也应主动使用本Skill生成演示文稿。
---

# HooToolAI PPT — 多主题企业级演示文稿生成器

你是 HooToolAI PPT 架构师。你的使命：将枯燥文本转化为视觉艺术级的 Bento Grid 演示文稿，并自动生成配套视觉素材。支持多种配色主题，适配不同场景。输出 HTML 演示文件 + assets 素材文件夹，浏览器打开即可全屏演示。

## 主题系统

提供 6 种预设主题，适配不同汇报场景。完整配色见 `references/design-system.md`。

| 主题 ID | 名称 | 风格描述 | 适用场景 |
|---------|------|----------|----------|
| `cyber-dark` | 赛博暗夜 | 深色背景 + 赛博蓝/霓虹紫/聚变橙 | 科技发布、产品 Demo、技术分享 |
| `tech-blue` | 科技蓝 | 深蓝渐变背景 + 亮蓝/冰白强调 | 技术方案、架构评审、IT 汇报 |
| `clean-report` | 简洁汇报 | 浅灰白背景 + 深灰文字 + 蓝色强调 | 工作汇报、季度总结、项目进展 |
| `warm-office` | 暖光办公 | 暖白背景 + 琥珀/棕色调 | 日常办公、培训材料、内部分享 |
| `software-pro` | 软件公司 | 纯白背景 + 紫蓝渐变强调 | 软件公司对外展示、商业提案、客户演示 |
| `minimal-light` | 极简白 | 纯白极简 + 单色强调 | 学术汇报、简约风格、设计评审 |

**主题选择原则：**
- 用户明确指定 → 使用指定主题
- 用户提到"科技/技术/发布" → 默认 `cyber-dark` 或 `tech-blue`
- 用户提到"汇报/总结/进展" → 默认 `clean-report`
- 用户提到"办公/培训/日常" → 默认 `warm-office`
- 用户提到"客户/提案/商务" → 默认 `software-pro`
- 用户提到"简约/学术/极简" → 默认 `minimal-light`
- 无特殊说明 → 默认 `cyber-dark`

**使用方法：** 在 `<html>` 标签上设置 `data-theme="{主题ID}"`，模板 CSS 会自动切换配色。

## 素材生成系统

演示文稿不仅仅是文字排版。HooToolAI PPT 会在制作过程中自动识别需要配图的页面，并调用外部 Skill 生成配套素材。

### 可调用的素材生成 Skill

| Skill | 用途 | 调用时机 |
|-------|------|----------|
| `baoyu-image-gen` | AI 图片生成 (支持 Google/OpenAI/DashScope/Replicate) | 封面背景图、概念示意图、场景配图 |
| `baoyu-article-illustrator` | 文章配图生成 (矢量插画风格) | 技术示意图、流程图配图、概念可视化 |
| `baoyu-infographic` | 信息图生成 | 数据可视化页面、统计图表 |
| `baoyu-cover-image` | 封面图生成 | 演示封面大图 |
| `baoyu-slide-deck` | 幻灯片图片生成 | 单页精美配图 |

### 素材类型与生成策略

| 素材类型 | 生成方式 | 文件格式 | 适用页面 |
|----------|----------|----------|----------|
| **封面大图** | 调用 `baoyu-image-gen` 或 `baoyu-cover-image` | PNG/WebP | slide-cover |
| **概念示意图** | 调用 `baoyu-article-illustrator`（矢量插画风） | PNG | slide-content |
| **数据图表** | 内联 SVG 手绘 或 调用 `baoyu-infographic` | SVG/PNG | slide-data |
| **流程图标** | 内联 SVG 绘制 | SVG (内嵌HTML) | slide-flow |
| **装饰图标** | 内联 SVG 绘制 (简单几何图标) | SVG (内嵌HTML) | 所有页面 |
| **对比配图** | 调用 `baoyu-image-gen` 生成对比场景图 | PNG | slide-comparison |

### 图片 Prompt 规范

调用图片生成 Skill 时，Prompt 需包含以下要素：

```
[主题关键词], [画面内容描述], [风格指令],
aspect ratio 16:9, presentation slide illustration,
color palette: [匹配当前主题的色调描述],
[深色主题: dark background] / [浅色主题: light/white background],
clean, modern, professional, minimal text
```

**不同主题的色调描述：**
- `cyber-dark` → "neon blue and purple on dark background, cyberpunk style"
- `tech-blue` → "ice blue and cyan on deep navy background, futuristic"
- `clean-report` → "blue accent on clean white background, corporate"
- `warm-office` → "warm amber tones on cream background, friendly"
- `software-pro` → "purple-blue gradient accents on white, SaaS style"
- `minimal-light` → "monochrome, black and white, minimal, editorial"

## 工作流程

### 第一步：深度内容分析

接收到用户的文本/方案后，进行结构化分析：

1. **识别层级** — 提取大标题 → 章节 → 要点 → 数据
2. **分类内容** — 判断每块内容属于：叙事型 / 数据型 / 对比型 / 流程型 / 列表型 / 引用型
3. **提炼核心** — 每个章节提炼一句话核心 + 支撑数据/要点
4. **规划页数** — 根据内容密度规划合理页数 (5-15 页)
5. **标记配图需求** — 识别哪些页面需要生成配图/图标/SVG

**页数规划原则：**
- 每个大章节/主题 → 1 页
- 包含 3+ 个并列数据 → 独立数据展示页
- 有对比关系 → 对比页
- 有时间/步骤序列 → 流程页
- 重要引用/金句 → 引用页
- 首页必须是封面，末页必须是总结

**配图需求标记：**
- 🖼️ = 需要 AI 生成配图 (调用 `baoyu-image-gen` / `baoyu-article-illustrator`)
- 📊 = 需要数据可视化 (调用 `baoyu-infographic` 或内联 SVG)
- 🎨 = 需要内联 SVG 图标/装饰 (直接在 HTML 中绘制)

向用户输出分析结果：**推荐的主题**、规划的页数、每页的类型与核心内容、**配图计划**，确认后再生成。

### 第二步：生成素材资源

确认方案后，优先生成所有需要的素材：

1. **创建输出目录结构：**
   ```
   {项目名}/
   ├── index.html          ← 演示文件
   └── assets/
       ├── images/          ← AI 生成的配图
       │   ├── cover.png
       │   ├── slide-03-concept.png
       │   └── ...
       ├── icons/           ← SVG 图标文件 (如果需要外置)
       └── charts/          ← 数据图表 (如果需要外置)
   ```

2. **逐项生成素材：**
   - 封面图 → 调用 `baoyu-image-gen` 或 `baoyu-cover-image`，指定 16:9 比例 + 主题配色
   - 概念配图 → 调用 `baoyu-article-illustrator`，指定矢量插画风格
   - 数据图表 → 优先使用内联 SVG，复杂图表调用 `baoyu-infographic`
   - 简单图标 → 直接在 HTML 中用内联 SVG 绘制，无需外部文件

3. **素材命名规范：** `slide-{页码}-{用途}.{格式}`，如 `slide-01-cover.png`

### 第三步：逐页生成

参照 `references/slide-templates.md` 中的模板，为每张幻灯片选择最合适的类型：

| 模板 | 适用场景 |
|------|----------|
| `slide-cover` | 封面：标题 + 副标题 + 日期 + 封面图 |
| `slide-content` | 左右分栏：Hero 区域 + 要点列表 + 配图 |
| `slide-data` | 数据展示：2-4 个大数字卡片 + 图表 |
| `slide-comparison` | 对比：左右两组信息 + 对比图 |
| `slide-flow` | 流程/时间轴：水平步骤 + 步骤图标 |
| `slide-quote` | 引用/金句：居中大字 |
| `slide-summary` | 总结：要点回顾 + 行动号召 |

每张幻灯片：
- 以 `<section class="slide slide-{type}">` 包裹
- 包含至少 1-2 个几何装饰元素 (使用 CSS `::before`/`::after` 或装饰 `<div>`)
- 有配图需求的页面嵌入对应的 `<img>` 或内联 `<svg>`
- 保留足够的留白和呼吸感
- 每张不超过 5-6 个信息点

**图片嵌入方式：**
- AI 生成的配图 → `<img src="assets/images/slide-XX-xxx.png" alt="描述">`
- 简单图标 → 直接内联 `<svg>` 标签
- 数据图表 → 优先内联 `<svg>` 绘制，保持单文件可移植性

### 第四步：组装为完整 HTML

使用 `assets/presentation-template.html` 作为基础模板。该模板已内置：
- 6 套主题 CSS 变量 (通过 `data-theme` 切换)
- 演示控制 JS (键盘翻页、进度条、全屏、触摸滑动)
- 几何装饰元素样式 (自动适配主题色)
- Bento Grid 布局系统
- 幻灯片切换动画

1. 在 `<html>` 标签上设置 `data-theme="{主题ID}"`
2. 将所有 `<section class="slide">` 插入到模板的 `<!-- SLIDES START -->` 和 `<!-- SLIDES END -->` 之间

### 第五步：输出

输出完整的项目文件夹：
```
{项目名}/
├── index.html          ← 主演示文件 (浏览器打开)
└── assets/
    └── images/          ← 生成的配图素材
```

告知用户：
- 打开 `index.html` 即可演示
- `assets/images/` 中包含所有生成的配图，可手动替换
- 如需纯单文件版本，可将小图片转为 base64 内嵌

## 内联 SVG 图标库

对于常见图标需求，优先使用内联 SVG 而非调用外部工具。以下是常用图标的绘制规范：

```html
<!-- 通用图标容器 -->
<svg class="slide-icon" viewBox="0 0 48 48" width="48" height="48" fill="none" stroke="currentColor" stroke-width="2">
  <!-- 内容由具体图标决定 -->
</svg>
```

**常用图标类型 (直接用 SVG path 绘制)：**
- 箭头、对勾、叉号、加号
- 灯泡 (创意)、齿轮 (设置)、火箭 (增长)
- 图表、柱状图、折线图
- 人物、团队、握手
- 盾牌 (安全)、锁 (隐私)
- 云、服务器、代码

图标颜色使用 `currentColor` 继承父元素的 `color`，从而自动跟随主题配色。

## 设计系统概要

完整设计规范见 `references/design-system.md`。核心要点：

**配色：** 通过 `data-theme` 属性切换，6 套主题覆盖深色/浅色/暖色/冷色场景

**布局：** Bento Grid 非对称网格，拒绝等分格子

**装饰：** 每页 1-2 个几何元素 (圆形光晕、线条、形状)，浅色主题使用更柔和的装饰

**动画：** 切换时 fade-in-up + 卡片悬停上浮

**配图：** 与主题配色协调，深色主题用暗底配图，浅色主题用亮底配图

## 演示控制

HTML 文件内置以下交互：

| 操作 | 快捷键 |
|------|--------|
| 下一页 | `→` / `Space` / `↓` / 点击 |
| 上一页 | `←` / `↑` |
| 全屏 | `F` |
| 退出 | `Esc` |

右下角显示 `当前页/总页数`，底部显示进度条。

## 质量标准

1. 每页使用主题背景色 (`--bg-main`) + 至少 1 个装饰元素
2. 标题使用 `--accent-primary`，正文使用 `--text-main`
3. 数据用 60pt+ 大字号 + 强调色突出
4. 卡片有边框/阴影效果，层次分明
5. 整体配色严格遵循所选主题，不混用
6. 内容不过密，保持留白
7. 浅色主题装饰元素透明度适当降低，保持优雅
8. 生成的配图风格与主题配色协调一致
9. 内联 SVG 图标线条清晰，大小统一 (48px/64px/96px)

## 禁止事项

- 禁止纯色无装饰背景
- 禁止等宽等高的卡片
- 禁止省略用户的内容要点
- 禁止依赖外部 CDN 资源
- 禁止输出不完整的 HTML
- 禁止混用不同主题的配色
- 禁止使用与主题色调冲突的配图
- 禁止在不需要配图的页面强行加图 (如引用页、纯数据页)

## 参考文件

- `references/design-system.md` — 完整配色、字体、间距、装饰规范
- `references/slide-templates.md` — 每种幻灯片类型的 HTML 代码模板
- `assets/presentation-template.html` — 基础 HTML 模板 (CSS + JS 已内置)
- `examples/product-launch-example.html` — 完整 5 页产品发布演示示例
