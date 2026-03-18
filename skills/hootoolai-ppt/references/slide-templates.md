# 幻灯片模板 HTML 片段

以下是每种幻灯片类型的 HTML 模板。生成时选择合适的模板，替换 `{占位符}` 为实际内容即可。

## 目录

1. [封面 (Cover)](#1-封面-cover)
2. [内容 (Content)](#2-内容-content)
3. [数据展示 (Data)](#3-数据展示-data)
4. [对比 (Comparison)](#4-对比-comparison)
5. [流程 (Flow)](#5-流程-flow)
6. [引用/金句 (Quote)](#6-引用金句-quote)
7. [总结 (Summary)](#7-总结-summary)

---

## 1. 封面 (Cover)

适用：演示首页，包含标题、副标题、日期。

```html
<section class="slide slide-cover">
  <div class="glow glow-blue"></div>
  <div class="slide-body cover-layout">
    <div class="cover-content">
      <h1 class="cover-title animate-in">{主标题}</h1>
      <p class="cover-subtitle animate-in">{副标题/描述}</p>
      <div class="accent-line animate-in"></div>
      <p class="cover-date animate-in">{日期或附加信息}</p>
    </div>
  </div>
  <div class="corner-dot"></div>
</section>
```

---

## 2. 内容 (Content)

适用：左右分栏，左侧 Hero 展示核心概念/图标/大数字，右侧列表要点。

```html
<section class="slide slide-content">
  <div class="glow glow-blue-br"></div>
  <div class="slide-body">
    <div class="slide-header animate-in">
      <h2 class="slide-title">{页面标题}</h2>
      <div class="accent-line"></div>
    </div>
    <div class="content-grid">
      <div class="hero-card card animate-in">
        <div class="hero-icon">{Emoji 或大数字}</div>
        <h3 class="hero-label">{核心概念}</h3>
      </div>
      <div class="content-list animate-in">
        <ul>
          <li>{要点一}</li>
          <li>{要点二}</li>
          <li>{要点三}</li>
          <li>{要点四}</li>
        </ul>
      </div>
    </div>
  </div>
</section>
```

---

## 3. 数据展示 (Data)

适用：展示 2-4 个关键数据指标。每个数据卡片使用不同的强调色。

```html
<section class="slide slide-data">
  <div class="glow glow-purple-tl"></div>
  <div class="slide-body">
    <div class="slide-header animate-in">
      <h2 class="slide-title">{页面标题}</h2>
      <div class="accent-line"></div>
    </div>
    <div class="data-grid">
      <div class="data-card card animate-in">
        <span class="data-value" style="color: var(--accent-success)">{数值1}</span>
        <span class="data-label">{标签1}</span>
      </div>
      <div class="data-card card animate-in">
        <span class="data-value" style="color: var(--accent-primary)">{数值2}</span>
        <span class="data-label">{标签2}</span>
      </div>
      <div class="data-card card animate-in">
        <span class="data-value" style="color: var(--accent-tertiary)">{数值3}</span>
        <span class="data-label">{标签3}</span>
      </div>
    </div>
    <!-- 可选：底部横幅 -->
    <div class="data-banner card animate-in">
      <span class="data-value" style="color: var(--accent-secondary)">{补充大数据}</span>
      <span class="data-label">{补充说明}</span>
    </div>
  </div>
</section>
```

---

## 4. 对比 (Comparison)

适用：两组信息的对比展示，如方案对比、优劣对比、前后对比。

```html
<section class="slide slide-comparison">
  <div class="glow glow-orange-tr"></div>
  <div class="slide-body">
    <div class="slide-header animate-in">
      <h2 class="slide-title">{页面标题}</h2>
      <div class="accent-line"></div>
    </div>
    <div class="comparison-grid">
      <div class="compare-card card animate-in">
        <h3 class="compare-title" style="color: var(--accent-secondary)">{左侧标题}</h3>
        <ul>
          <li>{左侧要点1}</li>
          <li>{左侧要点2}</li>
          <li>{左侧要点3}</li>
        </ul>
      </div>
      <div class="compare-divider"></div>
      <div class="compare-card card animate-in">
        <h3 class="compare-title" style="color: var(--accent-success)">{右侧标题}</h3>
        <ul>
          <li>{右侧要点1}</li>
          <li>{右侧要点2}</li>
          <li>{右侧要点3}</li>
        </ul>
      </div>
    </div>
  </div>
</section>
```

---

## 5. 流程 (Flow)

适用：时间轴、步骤流程、阶段展示。水平排列，线条连接。

```html
<section class="slide slide-flow">
  <div class="glow glow-green-bl"></div>
  <div class="slide-body">
    <div class="slide-header animate-in">
      <h2 class="slide-title">{页面标题}</h2>
      <div class="accent-line"></div>
    </div>
    <div class="flow-grid">
      <div class="flow-step animate-in">
        <span class="step-number">01</span>
        <div class="step-card card">
          <h4>{步骤1标题}</h4>
          <p>{步骤1描述}</p>
        </div>
      </div>
      <div class="flow-arrow animate-in">→</div>
      <div class="flow-step animate-in">
        <span class="step-number">02</span>
        <div class="step-card card">
          <h4>{步骤2标题}</h4>
          <p>{步骤2描述}</p>
        </div>
      </div>
      <div class="flow-arrow animate-in">→</div>
      <div class="flow-step animate-in">
        <span class="step-number">03</span>
        <div class="step-card card">
          <h4>{步骤3标题}</h4>
          <p>{步骤3描述}</p>
        </div>
      </div>
    </div>
  </div>
</section>
```

---

## 6. 引用/金句 (Quote)

适用：重要引用、金句、核心理念的突出展示。

```html
<section class="slide slide-quote">
  <div class="glow glow-blue"></div>
  <div class="glow glow-purple-br"></div>
  <div class="slide-body quote-layout">
    <blockquote class="quote-text animate-in">
      "{引用文字}"
    </blockquote>
    <p class="quote-author animate-in">— {作者/来源}</p>
  </div>
</section>
```

---

## 7. 总结 (Summary)

适用：演示末页，回顾要点 + 行动号召。

```html
<section class="slide slide-summary">
  <div class="glow glow-blue-tl"></div>
  <div class="glow glow-orange-br"></div>
  <div class="slide-body summary-layout">
    <h2 class="summary-title animate-in">{总结标题}</h2>
    <ul class="summary-points animate-in">
      <li>{要点回顾1}</li>
      <li>{要点回顾2}</li>
      <li>{要点回顾3}</li>
    </ul>
    <div class="cta-button animate-in">{行动号召文字}</div>
  </div>
</section>
```

---

## 装饰元素类名参考

光晕位置类名 (在 `<div class="glow {位置}">` 中使用)：

| 类名 | 位置 | 颜色 |
|------|------|------|
| `glow-blue` | 右上角 | 赛博蓝 |
| `glow-blue-br` | 右下角 | 赛博蓝 |
| `glow-blue-tl` | 左上角 | 赛博蓝 |
| `glow-orange-tr` | 右上角 | 聚变橙 |
| `glow-orange-br` | 右下角 | 聚变橙 |
| `glow-purple-tl` | 左上角 | 霓虹紫 |
| `glow-purple-br` | 右下角 | 霓虹紫 |
| `glow-green-bl` | 左下角 | 翡翠绿 |
| `corner-dot` | 左下角小圆点 | 聚变橙 |
