# 幻灯片模板 v2 — 17 种页面类型

每种页面类型有明确的 HTML 结构和版式规则。生成时严格按类型选用，替换 `{占位符}` 为实际内容。

---

## 1. 封面 `cover`

首页舞台感，大标题 + 副标题 + 可选主视觉。不堆信息。

```html
<section class="slide slide-cover">
  <div class="slide-inner cover-layout">
    <p class="eyebrow anim">{眉标/公司名/日期}</p>
    <h1 class="text-hero anim">{主标题}</h1>
    <p class="text-subtitle anim">{副标题/一句话描述}</p>
    <div class="deco-line anim"></div>
    <p class="text-caption anim">{演讲者 · 日期}</p>
  </div>
  <!-- 可选：封面背景图 -->
  <!-- <div class="cover-bg" style="background-image: url('assets/images/cover.png')"></div> -->
</section>
```

**版式说明：**
- 内容垂直居中，左对齐或居中（视风格而定）
- `stage-keynote`: 居中，超大标题，最多 6 个字
- `enterprise-report`: 左对齐，标题 + 副标题 + 日期
- 留白面积不低于 60%

---

## 2. 目录 `agenda`

简洁目录列表，带章节编号。不用花哨图形。

```html
<section class="slide slide-agenda">
  <div class="slide-inner">
    <h2 class="text-title anim">{目录标题}</h2>
    <div class="deco-line anim"></div>
    <ol class="agenda-list anim">
      <li class="agenda-item">
        <span class="agenda-num">01</span>
        <span class="agenda-text">{章节名称}</span>
      </li>
      <li class="agenda-item">
        <span class="agenda-num">02</span>
        <span class="agenda-text">{章节名称}</span>
      </li>
      <li class="agenda-item">
        <span class="agenda-num">03</span>
        <span class="agenda-text">{章节名称}</span>
      </li>
    </ol>
  </div>
</section>
```

**版式说明：**
- 编号使用 `var(--accent-1)` 高亮
- 每项一行，字号 24-28px
- 不超过 6 项

---

## 3. 章节分隔 `section-divider`

大字居中 + 章节编号，标记叙事转折。

```html
<section class="slide slide-section-divider">
  <div class="slide-inner divider-layout">
    <span class="divider-num text-metric-md anim">{01}</span>
    <h2 class="text-hero anim">{章节标题}</h2>
    <p class="text-subtitle anim">{可选：一句话描述}</p>
  </div>
</section>
```

**版式说明：**
- 垂直水平居中
- 编号用 `var(--accent-1)`，极大字号
- 留白极大，无卡片无装饰

---

## 4. 核心论点 `thesis`

一个大结论 + 2-3 个支撑块。

```html
<section class="slide slide-thesis">
  <div class="slide-inner">
    <p class="eyebrow anim">{眉标}</p>
    <h2 class="text-title anim">{结论句标题}</h2>
    <div class="deco-line anim"></div>
    <div class="layout-thirds thesis-supports">
      <div class="panel anim">
        <h4>{支撑点1标题}</h4>
        <p>{一句话说明}</p>
      </div>
      <div class="panel anim">
        <h4>{支撑点2标题}</h4>
        <p>{一句话说明}</p>
      </div>
      <div class="panel anim">
        <h4>{支撑点3标题}</h4>
        <p>{一句话说明}</p>
      </div>
    </div>
  </div>
</section>
```

---

## 5. 问题陈述 `problem`

左侧问题，右侧影响/症状/代价。双栏布局。

```html
<section class="slide slide-problem">
  <div class="slide-inner">
    <p class="eyebrow anim">{眉标：问题/挑战}</p>
    <h2 class="text-title anim">{问题结论句}</h2>
    <div class="layout-split problem-body">
      <div class="problem-statement anim">
        <p class="text-body">{问题核心描述，2-3句}</p>
      </div>
      <div class="problem-impact anim">
        <div class="impact-item">
          <span class="text-metric-sm" style="color:var(--accent-2)">{影响数据1}</span>
          <span class="text-caption">{说明}</span>
        </div>
        <div class="impact-item">
          <span class="text-metric-sm" style="color:var(--accent-2)">{影响数据2}</span>
          <span class="text-caption">{说明}</span>
        </div>
        <div class="impact-item">
          <span class="text-metric-sm" style="color:var(--accent-2)">{影响数据3}</span>
          <span class="text-caption">{说明}</span>
        </div>
      </div>
    </div>
  </div>
</section>
```

---

## 6. 关键洞察 `insight`

一个大数字或大结论居中，配解释性子块。

```html
<section class="slide slide-insight">
  <div class="slide-inner insight-layout">
    <p class="eyebrow anim">{眉标}</p>
    <div class="insight-hero anim">
      <span class="text-metric-lg" style="color:var(--accent-1)">{核心数字或关键词}</span>
    </div>
    <h2 class="text-title anim">{解释这个数字/结论的一句话}</h2>
    <p class="text-body anim">{补充说明，不超过2行}</p>
  </div>
</section>
```

**版式说明：**
- 垂直居中
- 主数字/关键词是唯一视觉焦点
- 最少文字量

---

## 7. 引用金句 `quote`

居中大字引用。

```html
<section class="slide slide-quote">
  <div class="slide-inner quote-layout">
    <blockquote class="text-title anim" style="font-style:italic; max-width:900px;">
      "{引用文字}"
    </blockquote>
    <p class="text-caption anim" style="color:var(--text-secondary)">— {来源}</p>
  </div>
</section>
```

**版式说明：**
- 垂直水平居中
- 引用文字不超过 40 个字
- 无卡片、无装饰

---

## 8. 解决方案 `solution`

左侧方案主张大字 + 右侧 Bento 能力卡片组合。禁止三等分列。

```html
<section class="slide slide-solution">
  <div class="slide-inner" style="flex-direction:row;gap:24px;padding:60px 80px;">

    <!-- 左侧方案主张：大字留白，强视觉冲击 -->
    <div class="anim" style="width:420px;flex-shrink:0;display:flex;flex-direction:column;justify-content:center;gap:20px;">
      <p class="eyebrow">{眉标：解决方案}</p>
      <h2 style="font-size:44px;font-weight:800;line-height:1.2;color:var(--text-primary);margin:0;">{方案主张句}</h2>
      <div class="deco-line"></div>
      <p class="text-body" style="color:var(--text-secondary);line-height:1.6;">{方案背景/价值主张，2句以内}</p>
    </div>

    <!-- 右侧 Bento 能力矩阵 -->
    <div style="flex:1;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:16px;">

      <!-- 能力1 — 右上大块 (rowspan 2) -->
      <div class="bento-cell" style="grid-row:span 2;background:var(--accent-1);color:#fff;">
        <div class="deco-ring" style="top:-20px;right:-20px;border-color:rgba(255,255,255,0.2);"></div>
        <svg class="icon-lg" viewBox="0 0 24 24" width="40" height="40" fill="none"
          stroke="rgba(255,255,255,0.9)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          {/* 核心能力图标 */}
        </svg>
        <div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;gap:8px;">
          <h4 style="font-size:22px;font-weight:700;color:#fff;margin:0;">{核心能力}</h4>
          <p style="font-size:15px;color:rgba(255,255,255,0.75);margin:0;line-height:1.5;">{一句话描述}</p>
        </div>
      </div>

      <!-- 能力2 -->
      <div class="bento-cell" style="display:flex;align-items:flex-start;gap:14px;">
        <svg viewBox="0 0 24 24" width="28" height="28" fill="none"
          stroke="var(--accent-1)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:2px;">
          {/* 图标 path */}
        </svg>
        <div>
          <h4 style="font-size:16px;font-weight:600;color:var(--text-primary);margin:0 0 6px;">{能力2}</h4>
          <p style="font-size:13px;color:var(--text-secondary);margin:0;line-height:1.5;">{一句话}</p>
        </div>
      </div>

      <!-- 能力3 -->
      <div class="bento-cell" style="display:flex;align-items:flex-start;gap:14px;">
        <svg viewBox="0 0 24 24" width="28" height="28" fill="none"
          stroke="var(--accent-positive)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:2px;">
          {/* 图标 path */}
        </svg>
        <div>
          <h4 style="font-size:16px;font-weight:600;color:var(--text-primary);margin:0 0 6px;">{能力3}</h4>
          <p style="font-size:13px;color:var(--text-secondary);margin:0;line-height:1.5;">{一句话}</p>
        </div>
      </div>

    </div>
  </div>
</section>
```

---

## 9. 功能矩阵 `feature-grid`

**必须用 Bento Grid**，禁止等分列。核心能力占英雄单元，其余环绕。

```html
<section class="slide slide-feature-grid">
  <div class="slide-inner" style="gap:20px;">
    <div class="anim" style="display:flex;flex-direction:column;gap:4px;">
      <p class="eyebrow">{眉标}</p>
      <h2 class="text-title">{标题结论句}</h2>
    </div>
    <div class="bento-grid anim" style="flex:1;">

      <!-- 英雄单元：核心能力，占视觉主体 -->
      <div class="bento-cell cell-hero cell-accent">
        <div class="deco-glow-orb" style="top:-60px;right:-60px;"></div>
        <svg class="icon-lg" viewBox="0 0 24 24" width="48" height="48" fill="none"
          stroke="rgba(255,255,255,0.9)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          {/* 主功能图标 path */}
        </svg>
        <div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;gap:8px;">
          <h3 style="font-size:28px;font-weight:700;color:#fff;margin:0;">{核心能力名称}</h3>
          <p style="font-size:16px;color:rgba(255,255,255,0.75);margin:0;line-height:1.5;">{一句话核心价值描述}</p>
        </div>
      </div>

      <!-- 次级能力 2 -->
      <div class="bento-cell cell-sm">
        <svg class="icon-md" viewBox="0 0 24 24" width="32" height="32" fill="none"
          stroke="var(--accent-1)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          {/* 图标 path */}
        </svg>
        <h4 style="font-size:17px;font-weight:600;margin:12px 0 6px;color:var(--text-primary);">{能力2}</h4>
        <p class="text-caption" style="color:var(--text-secondary);line-height:1.5;">{一句话}</p>
      </div>

      <!-- 次级能力 3 -->
      <div class="bento-cell cell-sm">
        <svg class="icon-md" viewBox="0 0 24 24" width="32" height="32" fill="none"
          stroke="var(--accent-1)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          {/* 图标 path */}
        </svg>
        <h4 style="font-size:17px;font-weight:600;margin:12px 0 6px;color:var(--text-primary);">{能力3}</h4>
        <p class="text-caption" style="color:var(--text-secondary);line-height:1.5;">{一句话}</p>
      </div>

      <!-- 次级能力 4 -->
      <div class="bento-cell cell-sm">
        <svg class="icon-md" viewBox="0 0 24 24" width="32" height="32" fill="none"
          stroke="var(--accent-positive)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          {/* 图标 path */}
        </svg>
        <h4 style="font-size:17px;font-weight:600;margin:12px 0 6px;color:var(--text-primary);">{能力4}</h4>
        <p class="text-caption" style="color:var(--text-secondary);line-height:1.5;">{一句话}</p>
      </div>

      <!-- 次级能力 5 -->
      <div class="bento-cell cell-sm">
        <svg class="icon-md" viewBox="0 0 24 24" width="32" height="32" fill="none"
          stroke="var(--accent-positive)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          {/* 图标 path */}
        </svg>
        <h4 style="font-size:17px;font-weight:600;margin:12px 0 6px;color:var(--text-primary);">{能力5}</h4>
        <p class="text-caption" style="color:var(--text-secondary);line-height:1.5;">{一句话}</p>
      </div>

    </div>
  </div>
</section>
```

**版式说明：**
- 英雄单元 span7/row2 承载核心能力，用 `cell-accent` 强调色填充
- 5个次级单元 span3，两行排列在英雄右侧（5列 ÷ 5 = 各占约3列）
- 图标严格统一线性风格，禁止 emoji
- 不超过 6 个特性（超出则拆页）

---

## 10. 技术架构 `architecture`

**必须有结构图。** 禁止纯项目符号。

```html
<section class="slide slide-architecture">
  <div class="slide-inner">
    <p class="eyebrow anim">{眉标：系统架构}</p>
    <h2 class="text-title anim">{架构标题}</h2>
    <div class="diagram anim">
      <svg class="architecture-diagram" viewBox="0 0 1200 500" fill="none">
        <!-- 分层结构示例 -->
        <!-- 层1：用户层 -->
        <rect x="100" y="20" width="1000" height="80" rx="8" fill="var(--bg-surface)" stroke="var(--border)"/>
        <text x="600" y="68" text-anchor="middle" fill="var(--text-primary)" font-size="18">{用户/接入层}</text>

        <!-- 层2：服务层 -->
        <rect x="100" y="140" width="480" height="80" rx="8" fill="var(--bg-surface)" stroke="var(--accent-1)" stroke-width="1.5"/>
        <text x="340" y="188" text-anchor="middle" fill="var(--text-primary)" font-size="16">{服务A}</text>
        <rect x="620" y="140" width="480" height="80" rx="8" fill="var(--bg-surface)" stroke="var(--accent-1)" stroke-width="1.5"/>
        <text x="860" y="188" text-anchor="middle" fill="var(--text-primary)" font-size="16">{服务B}</text>

        <!-- 连接箭头 -->
        <line x1="600" y1="100" x2="340" y2="140" stroke="var(--text-muted)" stroke-width="1"/>
        <line x1="600" y1="100" x2="860" y2="140" stroke="var(--text-muted)" stroke-width="1"/>

        <!-- 层3：数据层 -->
        <rect x="100" y="260" width="1000" height="80" rx="8" fill="var(--bg-surface)" stroke="var(--border)"/>
        <text x="600" y="308" text-anchor="middle" fill="var(--text-primary)" font-size="18">{数据/存储层}</text>
      </svg>
    </div>
  </div>
</section>
```

**版式说明：**
- SVG 结构图占页面主体 60%+
- 使用 CSS 变量取色，跟随主题
- 可在侧面添加简短标注，但不超过 3 条

---

## 11. 案例展示 `case-study`

场景描述 + 结果数据 + 可选配图。

```html
<section class="slide slide-case-study">
  <div class="slide-inner">
    <p class="eyebrow anim">{眉标：案例/实践}</p>
    <h2 class="text-title anim">{案例标题（结论句）}</h2>
    <div class="layout-split case-body">
      <div class="case-narrative anim">
        <p class="text-body">{场景描述，2-3句}</p>
        <p class="text-body">{方法/做法，1-2句}</p>
      </div>
      <div class="case-results anim">
        <div class="result-item">
          <span class="text-metric-md" style="color:var(--accent-positive)">{结果数据1}</span>
          <span class="text-caption">{指标名}</span>
        </div>
        <div class="result-item">
          <span class="text-metric-md" style="color:var(--accent-1)">{结果数据2}</span>
          <span class="text-caption">{指标名}</span>
        </div>
      </div>
    </div>
  </div>
</section>
```

---

## 12. 数据展示 `metrics`

1 个主数字突出 + 2-4 个次级指标陪衬。**禁止多数字同权。必须 Bento Grid。**

```html
<section class="slide slide-metrics">
  <div class="slide-inner" style="gap:20px;">
    <div class="anim" style="display:flex;flex-direction:column;gap:4px;">
      <p class="eyebrow">{眉标}</p>
      <h2 class="text-title">{数据页标题（结论句）}</h2>
    </div>
    <div class="bento-grid anim" style="flex:1;">

      <!-- 主数据英雄单元 — 视觉绝对焦点 -->
      <div class="bento-cell cell-hero cell-metric" style="background:var(--accent-1);color:#fff;">
        <div class="deco-glow-orb" style="bottom:-80px;left:-80px;background:radial-gradient(circle,rgba(255,255,255,0.2),transparent 70%);"></div>
        <p style="font-size:13px;letter-spacing:0.1em;text-transform:uppercase;color:rgba(255,255,255,0.65);margin:0;">{眉标/指标类别}</p>
        <div style="display:flex;align-items:flex-end;gap:8px;margin:auto 0;">
          <span style="font-size:96px;font-weight:800;line-height:1;color:#fff;">{主数字}</span>
          <span style="font-size:36px;font-weight:700;color:rgba(255,255,255,0.7);margin-bottom:12px;">{单位}</span>
        </div>
        <p style="font-size:18px;color:rgba(255,255,255,0.85);margin:0;font-weight:500;">{主指标名称}</p>
        <p style="font-size:14px;color:rgba(255,255,255,0.6);margin:8px 0 0;">{简短说明}</p>
      </div>

      <!-- 次级数据 1 -->
      <div class="bento-cell cell-sm cell-metric">
        <p class="eyebrow" style="margin:0 0 auto;">{次指标1}</p>
        <span style="font-size:48px;font-weight:800;line-height:1;color:var(--accent-positive);">{数字2}</span>
        <span style="font-size:13px;color:var(--text-secondary);margin-top:6px;">{说明}</span>
      </div>

      <!-- 次级数据 2 -->
      <div class="bento-cell cell-sm cell-metric">
        <p class="eyebrow" style="margin:0 0 auto;">{次指标2}</p>
        <span style="font-size:48px;font-weight:800;line-height:1;color:var(--text-primary);">{数字3}</span>
        <span style="font-size:13px;color:var(--text-secondary);margin-top:6px;">{说明}</span>
      </div>

      <!-- 次级数据 3 -->
      <div class="bento-cell cell-sm cell-metric">
        <p class="eyebrow" style="margin:0 0 auto;">{次指标3}</p>
        <span style="font-size:48px;font-weight:800;line-height:1;color:var(--text-primary);">{数字4}</span>
        <span style="font-size:13px;color:var(--text-secondary);margin-top:6px;">{说明}</span>
      </div>

      <!-- 可选：趋势图单元格 (跨满5列) -->
      <div class="bento-cell cell-md cell-chart">
        <p class="eyebrow" style="margin:0 0 12px;">趋势</p>
        <svg viewBox="0 0 300 100" fill="none" style="width:100%;height:auto;">
          <polyline points="0,80 60,60 120,45 180,30 240,20 300,10"
            stroke="var(--accent-1)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          <polyline points="0,80 60,60 120,45 180,30 240,20 300,10 300,100 0,100"
            fill="var(--accent-1)" opacity="0.08"/>
        </svg>
      </div>

    </div>
  </div>
</section>
```

---

## 13. 对比分析 `comparison`

左右对照，必须有视觉对立。

```html
<section class="slide slide-comparison">
  <div class="slide-inner">
    <p class="eyebrow anim">{眉标}</p>
    <h2 class="text-title anim">{对比标题}</h2>
    <div class="layout-halves comparison-body">
      <div class="panel compare-left anim" style="border-top: 3px solid var(--accent-2)">
        <h3>{左侧标题}</h3>
        <ul>
          <li>{维度1}</li>
          <li>{维度2}</li>
          <li>{维度3}</li>
        </ul>
      </div>
      <div class="panel compare-right anim" style="border-top: 3px solid var(--accent-positive)">
        <h3>{右侧标题}</h3>
        <ul>
          <li>{维度1（对齐）}</li>
          <li>{维度2（对齐）}</li>
          <li>{维度3（对齐）}</li>
        </ul>
      </div>
    </div>
  </div>
</section>
```

**版式说明：**
- 两侧维度数量必须一致
- 用不同色系的顶部边线区分

---

## 14. 步骤流程 `process`

3-6 步水平排列。

```html
<section class="slide slide-process">
  <div class="slide-inner">
    <p class="eyebrow anim">{眉标}</p>
    <h2 class="text-title anim">{流程标题}</h2>
    <div class="process-flow anim">
      <div class="process-step">
        <span class="step-num">01</span>
        <h4>{步骤标题}</h4>
        <p class="text-caption">{一句话}</p>
      </div>
      <div class="process-arrow">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--text-muted)" stroke-width="1.5"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
      </div>
      <div class="process-step">
        <span class="step-num">02</span>
        <h4>{步骤标题}</h4>
        <p class="text-caption">{一句话}</p>
      </div>
      <div class="process-arrow">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--text-muted)" stroke-width="1.5"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
      </div>
      <div class="process-step">
        <span class="step-num">03</span>
        <h4>{步骤标题}</h4>
        <p class="text-caption">{一句话}</p>
      </div>
    </div>
  </div>
</section>
```

**版式说明：**
- 步骤编号用 `var(--accent-1)` 高亮
- 步骤间用箭头 SVG 连接
- 每步描述不超过 1 行
- 超过 6 步 → 改用 `timeline`

---

## 15. 时间轴 `timeline`

按时间/阶段铺开，适合长序列。

```html
<section class="slide slide-timeline">
  <div class="slide-inner">
    <p class="eyebrow anim">{眉标}</p>
    <h2 class="text-title anim">{时间轴标题}</h2>
    <div class="timeline anim">
      <div class="timeline-track"></div>
      <div class="timeline-item">
        <span class="timeline-date">{时间点1}</span>
        <div class="timeline-dot"></div>
        <div class="timeline-content">
          <h4>{事件/阶段}</h4>
          <p class="text-caption">{说明}</p>
        </div>
      </div>
      <div class="timeline-item">
        <span class="timeline-date">{时间点2}</span>
        <div class="timeline-dot"></div>
        <div class="timeline-content">
          <h4>{事件/阶段}</h4>
          <p class="text-caption">{说明}</p>
        </div>
      </div>
      <!-- 3-8 个节点 -->
    </div>
  </div>
</section>
```

**版式说明：**
- 水平时间轴线 1px `var(--border)`
- 节点圆点 8px `var(--accent-1)`
- 当前/高亮阶段圆点可加大到 12px

---

## 16. 路线规划 `roadmap`

阶段 + 里程碑 + 时间标注。

```html
<section class="slide slide-roadmap">
  <div class="slide-inner">
    <p class="eyebrow anim">{眉标：路线图}</p>
    <h2 class="text-title anim">{路线图标题}</h2>
    <div class="roadmap-phases anim">
      <div class="roadmap-phase">
        <div class="phase-header" style="background:var(--accent-1); color:#fff; padding:8px 16px; border-radius:6px;">
          <span>{阶段1名称}</span>
          <span class="text-caption">{时间范围}</span>
        </div>
        <ul class="phase-milestones">
          <li>{里程碑1}</li>
          <li>{里程碑2}</li>
        </ul>
      </div>
      <div class="roadmap-phase">
        <div class="phase-header" style="background:var(--accent-positive); color:#fff; padding:8px 16px; border-radius:6px;">
          <span>{阶段2名称}</span>
          <span class="text-caption">{时间范围}</span>
        </div>
        <ul class="phase-milestones">
          <li>{里程碑3}</li>
          <li>{里程碑4}</li>
        </ul>
      </div>
    </div>
  </div>
</section>
```

---

## 17. 总结 `summary` / 结束 `closing`

### 总结：回顾 3 个结论

```html
<section class="slide slide-summary">
  <div class="slide-inner">
    <p class="eyebrow anim">{眉标：总结}</p>
    <h2 class="text-title anim">{总结标题}</h2>
    <div class="deco-line anim"></div>
    <div class="summary-points anim">
      <div class="summary-point">
        <span class="point-num">1</span>
        <p class="text-body">{结论1}</p>
      </div>
      <div class="summary-point">
        <span class="point-num">2</span>
        <p class="text-body">{结论2}</p>
      </div>
      <div class="summary-point">
        <span class="point-num">3</span>
        <p class="text-body">{结论3}</p>
      </div>
    </div>
  </div>
</section>
```

**版式说明：**
- 最多 3 个要点
- 不做成营销海报
- 不使用 CTA 按钮样式

### 结束：简洁收尾

```html
<section class="slide slide-closing">
  <div class="slide-inner closing-layout">
    <h2 class="text-hero anim">{谢谢 / Thank You}</h2>
    <p class="text-subtitle anim">{联系方式或下一步行动}</p>
    <div class="deco-line anim"></div>
  </div>
</section>
```

---

## CSS 类名速查

### 布局类
| 类名 | 用途 |
|------|------|
| `.layout-split` | 2:3 双栏 |
| `.layout-halves` | 1:1 双栏 |
| `.layout-thirds` | 三列等分 |
| `.layout-fourths` | 四列等分 |
| `.layout-metric-hero` | 1大+3小数据 |
| `.layout-2x2` | 2×2 网格 |
| `.layout-2x3` | 2×3 网格 |

### 文字类
| 类名 | 字号 |
|------|------|
| `.text-hero` | 72px |
| `.text-title` | 42px |
| `.text-subtitle` | 24px |
| `.text-body` | 20px |
| `.text-caption` | 14px |
| `.text-metric-lg` | 96px |
| `.text-metric-md` | 48px |
| `.text-metric-sm` | 32px |
| `.eyebrow` | 14px 大写间距 |

### 组件类
| 类名 | 用途 |
|------|------|
| `.panel` | 标准面板/卡片 |
| `.diagram` | 图表容器 |
| `.chart` | SVG 图表 |
| `.deco-line` | 标题装饰线 |
| `.deco-glow` | 背景光晕（谨慎使用） |
| `.anim` | 入场动画标记 |
