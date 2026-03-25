# 设计系统规范 v2

本文档定义 HooToolAI PPT 的完整设计规范。6 种配色主题 × 6 种风格预设，通过 CSS 变量和类名组合控制。

---

## 配色主题

所有主题共用相同 CSS 变量名，通过 `[data-theme]` 切换。在 `<html>` 标签设置 `data-theme="{主题ID}"`。

### 主题 1：`ink-dark` 深墨科技

深色背景 + 蓝紫冷光强调。适用发布会、产品展示、技术品牌。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#0B0F19` | 幻灯片背景 |
| `--bg-surface` | `#141926` | 卡片/面板背景 |
| `--bg-surface-hover` | `#1A2035` | 面板悬停 |
| `--border` | `#252D3D` | 边框/分割线 |
| `--border-accent` | `#3A4560` | 高亮边框 |
| `--accent-1` | `#4C9EFF` | 主强调 |
| `--accent-2` | `#F07C5C` | 辅助强调 |
| `--accent-positive` | `#34D399` | 正向/成功 |
| `--text-primary` | `#E8ECF4` | 主文字 |
| `--text-secondary` | `#8892A6` | 次要文字 |
| `--text-muted` | `#5A6378` | 弱化文字 |

### 主题 2：`navy-tech` 深蓝专业

深蓝基底 + 冰蓝强调。适用技术方案、架构评审、研发汇报。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#091428` | 深蓝背景 |
| `--bg-surface` | `#0E1F3D` | 面板背景 |
| `--bg-surface-hover` | `#142A50` | 面板悬停 |
| `--border` | `#1A3358` | 边框 |
| `--border-accent` | `#264A7A` | 高亮边框 |
| `--accent-1` | `#4FC3F7` | 冰蓝主强调 |
| `--accent-2` | `#00E5FF` | 青色辅助 |
| `--accent-positive` | `#69F0AE` | 薄荷绿 |
| `--text-primary` | `#E3F2FD` | 冰白文字 |
| `--text-secondary` | `#90CAF9` | 淡蓝文字 |
| `--text-muted` | `#5B86B5` | 弱化文字 |

### 主题 3：`report-light` 商务浅色

浅灰白背景 + 商务蓝强调。**默认主题**。适用工作汇报、季度总结、项目进展。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#F6F8FB` | 浅灰白背景 |
| `--bg-surface` | `#FFFFFF` | 白色面板 |
| `--bg-surface-hover` | `#F0F4F8` | 面板悬停 |
| `--border` | `#E2E8F0` | 浅灰边框 |
| `--border-accent` | `#CBD5E1` | 高亮边框 |
| `--accent-1` | `#2563EB` | 商务蓝 |
| `--accent-2` | `#F59E0B` | 琥珀色 |
| `--accent-positive` | `#10B981` | 翠绿 |
| `--text-primary` | `#1E293B` | 深灰文字 |
| `--text-secondary` | `#64748B` | 中灰文字 |
| `--text-muted` | `#94A3B8` | 浅灰文字 |

### 主题 4：`warm-paper` 暖白培训

暖白背景 + 暖色调强调。适用培训、分享、内部知识传递。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#FAF8F5` | 暖白背景 |
| `--bg-surface` | `#FFFFFF` | 白色面板 |
| `--bg-surface-hover` | `#F5F0EB` | 面板悬停 |
| `--border` | `#E8E0D8` | 暖灰边框 |
| `--border-accent` | `#D4C8BC` | 高亮边框 |
| `--accent-1` | `#D97706` | 琥珀主色 |
| `--accent-2` | `#DC2626` | 红棕辅助 |
| `--accent-positive` | `#16A34A` | 森林绿 |
| `--text-primary` | `#292524` | 深棕文字 |
| `--text-secondary` | `#78716C` | 暖灰文字 |
| `--text-muted` | `#A8A29E` | 浅暖灰 |

### 主题 5：`saas-white` 白底产品

纯白背景 + 紫蓝渐变强调。适用商业提案、客户演示、SaaS 展示。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#FFFFFF` | 纯白背景 |
| `--bg-surface` | `#F8FAFC` | 极浅灰面板 |
| `--bg-surface-hover` | `#F1F5F9` | 面板悬停 |
| `--border` | `#E2E8F0` | 浅灰边框 |
| `--border-accent` | `#CBD5E1` | 高亮边框 |
| `--accent-1` | `#6366F1` | 靛蓝紫 |
| `--accent-2` | `#EC4899` | 粉色辅助 |
| `--accent-positive` | `#22C55E` | 亮绿 |
| `--text-primary` | `#0F172A` | 墨色文字 |
| `--text-secondary` | `#475569` | 深灰文字 |
| `--text-muted` | `#94A3B8` | 浅灰文字 |

### 主题 6：`mono-minimal` 极简黑白

纯白极简 + 黑色/单色强调。适用学术、极简风格、设计评审。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#FAFAFA` | 纯白背景 |
| `--bg-surface` | `#FFFFFF` | 白色面板 |
| `--bg-surface-hover` | `#F5F5F5` | 面板悬停 |
| `--border` | `#E5E5E5` | 浅灰边框 |
| `--border-accent` | `#D4D4D4` | 高亮边框 |
| `--accent-1` | `#171717` | 黑色主强调 |
| `--accent-2` | `#525252` | 深灰辅助 |
| `--accent-positive` | `#16A34A` | 绿色 |
| `--text-primary` | `#171717` | 黑色文字 |
| `--text-secondary` | `#525252` | 深灰文字 |
| `--text-muted` | `#A3A3A3` | 浅灰文字 |

---

## 字体规范

### 字体栈

```css
--font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
--font-mono: 'SF Mono', 'Fira Code', 'Consolas', monospace;
```

### 字号层级

| 语义类名 | 字号 | 字重 | 行高 | 用途 |
|----------|------|------|------|------|
| `.text-hero` | 72px | 800 | 1.1 | 封面主标题 |
| `.text-title` | 42px | 700 | 1.2 | 页面标题 |
| `.text-subtitle` | 24px | 500 | 1.3 | 副标题/眉标 |
| `.text-body` | 20px | 400 | 1.6 | 正文 |
| `.text-caption` | 14px | 400 | 1.5 | 标注/脚注 |
| `.text-metric-lg` | 96px | 800 | 1.0 | 主数据 |
| `.text-metric-md` | 48px | 700 | 1.1 | 次数据 |
| `.text-metric-sm` | 32px | 600 | 1.2 | 辅助数据 |

---

## 画布系统

### 固定画布 + 缩放适配

```css
:root {
  --slide-w: 1600;
  --slide-h: 900;
}

body {
  margin: 0;
  background: #111;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  overflow: hidden;
}

.deck {
  width: calc(var(--slide-w) * 1px);
  height: calc(var(--slide-h) * 1px);
  position: relative;
  overflow: hidden;
  transform-origin: center center;
  /* JS 动态计算 scale */
}

.slide {
  position: absolute;
  inset: 0;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.4s ease;
}
.slide.active {
  opacity: 1;
  pointer-events: auto;
  z-index: 1;
}
```

### 缩放 JS

```javascript
function fitDeck() {
  const deck = document.querySelector('.deck');
  const sw = 1600, sh = 900;
  const scale = Math.min(window.innerWidth / sw, window.innerHeight / sh);
  deck.style.transform = `scale(${scale})`;
}
window.addEventListener('resize', fitDeck);
fitDeck();
```

---

## Bento Grid Engine（核心视觉系统）

这是让演示稿从"稀疏模板"变为"高质量产品"的核心。必须用于 feature-grid / metrics / solution / thesis / case-study 页面。

### Bento Grid 基础结构

```css
/* ── Bento 容器 ────────────────────────────── */
.bento-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  grid-auto-rows: minmax(88px, auto);
  gap: 20px;
  width: 100%;
  flex: 1;
  min-height: 0;
}

/* ── 基础单元格 ────────────────────────────── */
.bento-cell {
  border-radius: 16px;
  padding: 28px;
  position: relative;
  overflow: hidden;
  transition: transform 0.28s cubic-bezier(0.4,0,0.2,1),
              background 0.28s cubic-bezier(0.4,0,0.2,1),
              box-shadow 0.28s cubic-bezier(0.4,0,0.2,1);
  display: flex;
  flex-direction: column;
}

/* 深色主题 — 玻璃态 */
[data-theme="ink-dark"] .bento-cell,
[data-theme="navy-tech"] .bento-cell {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.07);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
[data-theme="ink-dark"] .bento-cell:hover,
[data-theme="navy-tech"] .bento-cell:hover {
  transform: translateY(-4px);
  background: rgba(255,255,255,0.07);
  box-shadow: 0 16px 48px rgba(0,0,0,0.35),
              0 0 0 1px rgba(255,255,255,0.12),
              0 0 24px rgba(76,158,255,0.08);
}

/* 浅色主题 */
[data-theme="report-light"] .bento-cell,
[data-theme="saas-white"] .bento-cell,
[data-theme="warm-paper"] .bento-cell,
[data-theme="mono-minimal"] .bento-cell {
  background: var(--bg-surface);
  border: 1px solid transparent;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.04);
}
[data-theme="report-light"] .bento-cell:hover,
[data-theme="saas-white"] .bento-cell:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 28px rgba(0,0,0,0.1);
}
```

### 单元格尺寸预设

```css
/* 英雄单元：主要洞察/大数据/封面焦点 */
.cell-hero   { grid-column: span 7; grid-row: span 2; }

/* 高耸单元：次级重要内容 */
.cell-tall   { grid-column: span 5; grid-row: span 2; }

/* 标准宽单元 */
.cell-wide   { grid-column: span 7; }
.cell-md     { grid-column: span 5; }
.cell-third  { grid-column: span 4; }
.cell-sm     { grid-column: span 3; }

/* 全宽 */
.cell-full   { grid-column: span 12; }

/* 正方块 */
.cell-square { grid-column: span 3; grid-row: span 2; }
```

### 单元格功能变体

```css
/* 强调单元格 — 主题主色填充，每页最多1个 */
.cell-accent {
  background: var(--accent-1) !important;
  border-color: transparent !important;
  color: #fff;
}
.cell-accent .cell-label,
.cell-accent .eyebrow { color: rgba(255,255,255,0.7); }

/* 指标/数据单元格 — 居中展示大数字 */
.cell-metric {
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 8px;
}
.cell-metric .metric-num {
  font-size: 72px;
  font-weight: 800;
  line-height: 1;
  color: var(--accent-1);
}
.cell-metric .metric-unit {
  font-size: 28px;
  font-weight: 700;
  color: var(--accent-1);
  opacity: 0.8;
  align-self: flex-end;
  margin-bottom: 8px;
}
.cell-metric .metric-label {
  font-size: 14px;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
}

/* 图表容器单元格 */
.cell-chart {
  padding: 20px;
}
.cell-chart svg { width: 100%; height: auto; }

/* 列表单元格 */
.cell-list { gap: 0; }
.cell-list-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  font-size: 15px;
  color: var(--text-primary);
  line-height: 1.5;
}
.cell-list-item:last-child { border-bottom: none; }
.cell-list-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--accent-1);
  flex-shrink: 0;
  margin-top: 7px;
}
```

### 几何装饰点缀系统

```css
/* 所有装饰指针事件关闭，不影响内容层 */

/* 辉光圆 — 深色主题封面/强调页背景 */
.deco-glow-orb {
  position: absolute;
  width: 200px; height: 200px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--accent-1), transparent 70%);
  opacity: 0.09;
  pointer-events: none;
  z-index: 0;
}

/* 圆圈轮廓 — 单元格角落点缀 */
.deco-ring {
  position: absolute;
  width: 80px; height: 80px;
  border-radius: 50%;
  border: 1.5px solid var(--accent-1);
  opacity: 0.18;
  pointer-events: none;
}

/* 角落小点 — 精致科技感 */
.deco-dot-grid {
  position: absolute;
  width: 60px; height: 60px;
  background-image: radial-gradient(circle, var(--text-muted) 1px, transparent 1px);
  background-size: 10px 10px;
  opacity: 0.25;
  pointer-events: none;
}

/* 标题强调线 — 比 deco-line 更有力 */
.deco-bar {
  width: 4px;
  align-self: stretch;
  background: var(--accent-1);
  border-radius: 2px;
  flex-shrink: 0;
}

/* 单元格内容 z-index 修正 */
.bento-cell > * { position: relative; z-index: 1; }
```

### 常用 Bento 排版组合

```
组合 A（英雄+三卫星）— 适用 metrics/solution/feature:
  [  hero: span7/row2  ] [ sm ] [ sm ]
  [  hero: span7/row2  ] [ sm ] [ sm ]
  布局: grid-template-columns: repeat(12,1fr)
  hero占7列, 其余5列放2个span2.5(约span3)

组合 B（强调+内容）— 适用 thesis/insight:
  [ accent: span5/row2 ] [  wide: span7  ]
  [ accent: span5/row2 ] [  wide: span7  ]

组合 C（全宽标题+Bento下半）— 适用 case-study/comparison:
  [     full: span12       ]  ← 标题行
  [ tall:span5 ] [ md:span4 ] [ sm:span3 ]
  [ tall:span5 ] [ md:span4 ] [ sm:span3 ]

组合 D（仪表板 2×3）— 适用 KPI总览/多指标:
  [ third:span4 ] [ third:span4 ] [ third:span4 ]
  [ third:span4 ] [ third:span4 ] [ third:span4 ]

组合 E（顶部英雄+底部细节行）— 适用 quote+证据/洞察+支撑:
  [        wide hero: span12         ]  ← 主结论/引用
  [ sm:span4 ] [ sm:span4 ] [ sm:span4 ]  ← 支撑证据
```

### Bento 内容自适应尺寸规则

| 内容量 | 单元格内调整策略 |
|--------|----------------|
| 单个指标（1数字+标签） | 大数字居中 72-96px，font-weight:800，标签置于下方 14px |
| 短文本（< 30字） | 标准 body 20px，padding 28px |
| 中文本（30-80字） | 缩小 body 至 16px，padding 缩至 20px |
| 长文本（> 80字） | 缩小 body 至 14px，padding 缩至 16px |
| > 5 个要点 | 在单元格内改用双栏 bullet 列表 |
| > 8 个要点 | 拆分为两个相邻单元格，不能再缩字号 |

**最小字号限制**：body 14px / 标题 18px / 数字 32px。低于这些值时必须拆页或拆单元格。

### 卡片宽高比约束

- **最小宽高比**：1:2（宽度不低于高度的一半）
- **最大宽高比**：4:1（宽度不超过高度的4倍）
- **首选比例**：16:9、4:3、1:1、3:4

### 数据图表选型决策树

| 演示目的 | 推荐方式 | 禁止 |
|---------|---------|------|
| 展示这个数字本身 | 大数字卡片（72-96px） | 不用图表 |
| 展示增长/下降趋势 | 迷你折线图 + 关键数字 | 不用饼图 |
| 比较多个项目 | 水平条形图（对齐基线） | 不用多色饼图 |
| 占比/构成 | 环形图（最多6段） | 不用多层嵌套 |
| 数据 > 10 条 | 表格卡片 | 不用折线图 |
| 时间序列 | 折线图 + 关键节点标注 | 不用雷达图 |

---

## 构图黄金法则

### 黄金比例（62:38）

非对称布局时，首选黄金比例分割，而非随意的 50:50 或 60:40：

```
画布 1600px 宽：
  主区域 ≈ 992px（62%）| 次区域 ≈ 608px（38%）

画布 900px 高：
  主区域 ≈ 558px（62%）| 次区域 ≈ 342px（38%）
```

### 三分法构图（主视觉锚点定位）

每页的视觉"锚"（主数字/主标题/主图）应落在三分法交叉点附近：

```
1600×900 画布的三分法交叉点：
┌──────────────────────────────────────────┐
│         │                   │            │
│     ●(533,300)           ●(1067,300)    │
│         │                   │            │
│─────────────────────────────────────────│
│         │                   │            │
│     ●(533,600)           ●(1067,600)    │
│         │                   │            │
└──────────────────────────────────────────┘

主视觉锚点优先落在左上(533,300)或右上(1067,300)交叉点。
数据型页面优先左上，叙事型页面优先居中或左上。
```

### 视觉重心平衡

- **水平平衡**：左右视觉重量大致相等，即使面积不等（重色块 = 大面积浅色）
- **垂直平衡**：视觉重心略低于几何中心（y ≈ 480-520 而非 450）
- **留白方向**：留白应集中在一个方向，不要四面均匀留白

---

## 布局系统

### 安全区域

```css
.slide-inner {
  padding: 60px 80px;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}
```

### 常用 Grid 布局

```css
/* 双栏（左窄右宽）— thesis, problem, solution */
.layout-split { display: grid; grid-template-columns: 2fr 3fr; gap: 40px; align-items: start; }

/* 双栏等分 — comparison */
.layout-halves { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }

/* 三列 — feature-grid */
.layout-thirds { display: grid; grid-template-columns: repeat(3, 1fr); gap: 32px; }

/* 四列 — metrics */
.layout-fourths { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; }

/* 主+辅 数据布局 — metrics (1大+3小) */
.layout-metric-hero {
  display: grid;
  grid-template-columns: 1.5fr 1fr 1fr 1fr;
  gap: 24px;
  align-items: end;
}

/* 2×2 网格 — feature-grid */
.layout-2x2 { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 24px; }

/* 2×3 网格 — feature-grid */
.layout-2x3 { display: grid; grid-template-columns: repeat(3, 1fr); grid-template-rows: 1fr 1fr; gap: 24px; }
```

### 间距系统

| 用途 | 值 | 变量 |
|------|-----|------|
| 页面安全边距 | 60px 80px | `--pad-slide` |
| 面板间距 | 32px | `--gap-lg` |
| 面板内边距 | 28px | `--pad-panel` |
| 元素间距 | 16px | `--gap-sm` |
| 紧凑间距 | 8px | `--gap-xs` |
| 标准圆角 | 12px | `--radius` |
| 大圆角 | 16px | `--radius-lg` |

---

## 面板/卡片样式

### 标准面板

```css
.panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--pad-panel);
}
```

### 浅色主题面板（带阴影）

```css
[data-theme="report-light"] .panel,
[data-theme="warm-paper"] .panel,
[data-theme="saas-white"] .panel,
[data-theme="mono-minimal"] .panel {
  box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
  border-color: transparent;
}
```

### 深色主题面板（边框发光）

```css
[data-theme="ink-dark"] .panel,
[data-theme="navy-tech"] .panel {
  border-color: var(--border);
  box-shadow: 0 0 0 1px var(--border);
}
```

---

## 装饰规则

### 原则
- 装饰是点缀，不是主角
- 每页最多 1 个背景装饰元素
- 浅色主题的装饰透明度上限 0.05
- 深色主题的装饰透明度上限 0.12
- 禁止每页都用相同的装饰组合

### 允许的装饰类型

```css
/* 柔和渐变光晕 — 只用于 cover/section-divider */
.deco-glow {
  position: absolute;
  width: 500px; height: 500px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--accent-1), transparent 70%);
  opacity: 0.08;
  pointer-events: none;
}

/* 细线分隔 — 标题下方 */
.deco-line {
  width: 48px; height: 3px;
  background: var(--accent-1);
  border-radius: 2px;
  margin-top: 12px;
}

/* 极细边线装饰 — section-divider */
.deco-rule {
  width: 100%; height: 1px;
  background: var(--border);
}
```

### 禁止的装饰
- ❌ 每页都有大面积发光球
- ❌ 多个角落同时有装饰点
- ❌ 与内容重叠的渐变覆盖层
- ❌ 3D/立体/弹跳/旋转装饰

---

## 动画规范

### 页面切换

```css
.slide { opacity: 0; transition: opacity 0.4s ease; }
.slide.active { opacity: 1; }
```

### 元素入场

```css
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.slide.active .anim {
  animation: fadeUp 0.5s ease forwards;
}
.slide.active .anim:nth-child(1) { animation-delay: 0.05s; }
.slide.active .anim:nth-child(2) { animation-delay: 0.15s; }
.slide.active .anim:nth-child(3) { animation-delay: 0.25s; }
.slide.active .anim:nth-child(4) { animation-delay: 0.35s; }
.slide.active .anim:nth-child(5) { animation-delay: 0.45s; }
```

### 禁止的动画
- ❌ 弹跳 (bounce)
- ❌ 旋转 (rotate)
- ❌ 缩放弹性 (scale + elastic)
- ❌ 飞入 (translateX > 100px)
- ❌ 闪烁 (blink/flash)

---

## SVG 图表规范

### 通用规则
- 使用 `currentColor` 或 CSS 变量取色，自动跟随主题
- 不添加网格线，背景透明
- 标注文字使用 `var(--text-secondary)`
- 主数据使用 `var(--accent-1)` 高亮

### 条形图骨架

```html
<svg class="chart" viewBox="0 0 400 200" fill="none">
  <!-- 数据条 -->
  <rect x="20" y="40" width="280" height="28" rx="4" fill="var(--accent-1)" opacity="0.9"/>
  <rect x="20" y="80" width="200" height="28" rx="4" fill="var(--accent-1)" opacity="0.5"/>
  <rect x="20" y="120" width="140" height="28" rx="4" fill="var(--accent-1)" opacity="0.3"/>
  <!-- 标签 -->
  <text x="310" y="58" fill="var(--text-secondary)" font-size="14">85%</text>
  <text x="230" y="98" fill="var(--text-secondary)" font-size="14">60%</text>
  <text x="170" y="138" fill="var(--text-secondary)" font-size="14">42%</text>
</svg>
```

### 环形图骨架

```html
<svg class="chart" viewBox="0 0 200 200" fill="none">
  <circle cx="100" cy="100" r="70" stroke="var(--border)" stroke-width="16" fill="none"/>
  <circle cx="100" cy="100" r="70" stroke="var(--accent-1)" stroke-width="16" fill="none"
    stroke-dasharray="330 440" stroke-linecap="round" transform="rotate(-90 100 100)"/>
  <text x="100" y="105" text-anchor="middle" fill="var(--text-primary)" font-size="28" font-weight="700">75%</text>
</svg>
```

---

## 图标规范

### 统一格式

```html
<svg class="icon" viewBox="0 0 24 24" width="24" height="24"
  fill="none" stroke="currentColor" stroke-width="1.5"
  stroke-linecap="round" stroke-linejoin="round">
  <!-- path -->
</svg>
```

### 尺寸规则
| 场景 | 尺寸 | 类名 |
|------|------|------|
| 正文内联 | 20px | `.icon-sm` |
| 卡片标题旁 | 24px | `.icon` |
| 特性卡片中心 | 32px | `.icon-md` |
| 封面/大展示 | 48px | `.icon-lg` |

### 颜色规则
- 默认用 `currentColor` 继承父元素颜色
- 需要强调时用 `var(--accent-1)`
- 禁止使用多色/emoji 风格图标

---

## 风格预设与布局映射

不同风格预设对布局和装饰有不同偏好：

| 风格 | 间距感 | 装饰量 | 卡片风格 | 标题风格 |
|------|--------|--------|---------|---------|
| `stage-keynote` | 极大留白 | 极少 | 无边框/透明 | 超大居中 |
| `editorial-fintech` | 大留白 | 少 | 精致阴影 | 左对齐+眉标 |
| `precision-saas` | 中等 | 少 | 细边框 | 左对齐紧凑 |
| `clean-workspace` | 中等 | 极少 | 轻阴影 | 左对齐朴素 |
| `modern-landing` | 中等 | 中等 | 圆角阴影 | 居中/左对齐 |
| `enterprise-report` | 标准 | 少 | 轻边框 | 左对齐正式 |

---

## 演示控制 JS（三模式 + 键盘导航）

所有 index.html 必须内置以下控制逻辑：

```javascript
// ── 三种浏览模式 ───────────────────────────────
// present: 全屏幻灯片演示（默认）
// gallery: 缩略图网格总览
// scroll:  纵向连续滚动

let mode = 'present';
let current = 0;
const slides = document.querySelectorAll('.slide');
const total = slides.length;

function setMode(m) {
  mode = m;
  document.body.dataset.mode = m;
  if (m === 'present') goTo(current);
}

function goTo(n) {
  current = Math.max(0, Math.min(n, total - 1));
  slides.forEach((s, i) => s.classList.toggle('active', i === current));
  updateProgress();
}

function updateProgress() {
  const bar = document.querySelector('.progress-bar');
  if (bar) bar.style.width = `${((current + 1) / total) * 100}%`;
  const num = document.querySelector('.slide-counter');
  if (num) num.textContent = `${current + 1} / ${total}`;
}

// ── 键盘快捷键 ────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'ArrowDown') goTo(current + 1);
  if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') goTo(current - 1);
  if (e.key === 'p' || e.key === 'P') setMode('present');
  if (e.key === 'g' || e.key === 'G') setMode('gallery');
  if (e.key === 's' || e.key === 'S') setMode('scroll');
  if (e.key === 'f' || e.key === 'F') document.documentElement.requestFullscreen?.();
  if (e.key === 'n' || e.key === 'N') toggleNotes();
  if (e.key === 'Escape') { if (document.fullscreenElement) document.exitFullscreen(); else setMode('present'); }
});

// ── 演讲者备注面板 ────────────────────────────
function toggleNotes() {
  const panel = document.querySelector('.notes-panel');
  if (panel) panel.classList.toggle('visible');
}

// ── 画布自适应缩放 ────────────────────────────
function fitDeck() {
  const deck = document.querySelector('.deck');
  const sw = 1600, sh = 900;
  const scale = Math.min(window.innerWidth / sw, window.innerHeight / sh);
  deck.style.transform = `scale(${scale})`;
}
window.addEventListener('resize', fitDeck);
document.addEventListener('DOMContentLoaded', () => { fitDeck(); goTo(0); });
```

### CSS 模式切换

```css
/* Gallery 模式 */
body[data-mode="gallery"] .deck {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  width: 100%;
  height: auto;
  transform: none !important;
  padding: 24px;
  box-sizing: border-box;
}
body[data-mode="gallery"] .slide {
  position: relative;
  opacity: 1 !important;
  pointer-events: auto !important;
  cursor: pointer;
  transform: scale(0.2);
  transform-origin: top left;
  border-radius: 8px;
  overflow: hidden;
}

/* Scroll 模式 */
body[data-mode="scroll"] .deck {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 1600px;
  height: auto;
  transform: none !important;
}
body[data-mode="scroll"] .slide {
  position: relative;
  opacity: 1 !important;
  pointer-events: auto !important;
  height: 900px;
}

/* 进度条 */
.progress-bar-track {
  position: fixed; bottom: 0; left: 0; width: 100%; height: 3px;
  background: rgba(255,255,255,0.1); z-index: 100;
}
.progress-bar {
  height: 100%; background: var(--accent-1);
  transition: width 0.3s ease;
}

/* 页码 */
.slide-counter {
  position: fixed; bottom: 12px; right: 16px;
  font-size: 13px; color: var(--text-muted);
  z-index: 100; font-family: var(--font-mono);
}
```
