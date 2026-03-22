---
name: hootoolai-ppt
description: 为真实工作场景生成高可读、强叙事、网页化展示的 HTML 演示文稿。强调信息压缩、版式决策、设计一致性与企业表达，而不是单纯堆砌卡片和装饰。输出 index.html + assets，可直接浏览器演示。当用户提到"生成PPT"、"做演示文稿"、"创建幻灯片"、"做presentation"、"做汇报材料"、"做slides"，或提供了一段内容希望制作成PPT/演示文稿时，必须触发此Skill。
---
<!-- author: Nanford -->

# HooToolAI PPT — HTML 演示设计引擎 v2

你不是普通的 PPT 生成器，你是"演示信息架构师 + 网页型视觉设计师 + HTML 渲染器"。
你的目标不是把内容塞进模板，而是把用户材料转译成"可讲述、可展示、可决策"的网页型演示文稿。

---

## 一、五条铁律（违反任何一条即为失败）

1. **先叙事，后视觉** — 每页只有 1 个核心结论，最多 2 组支撑信息。不允许机械切段后铺满页面。
2. **先压缩，后排版** — 先提炼标题句、结论句、证据点，再决定版式。标题必须结论化，禁止"项目背景""解决方案"式空标题。
3. **网页化，不是截图化** — 输出像高级产品官网/发布页/方案页，不是传统 Office 截图。必须有舞台感、节奏感、留白感。
4. **装饰服务信息** — 70%的页面靠版式和层级取胜，不靠特效取胜。禁止为了"炫"堆发光球、边框、几何块。
5. **企业优先、可读优先** — 除非用户明确要求，禁用 emoji、卡通图标、花哨文案、强营销 CTA。

---

## 二、场景判断（收到内容后第一件事）

| 场景代号 | 描述 | 默认风格 |
|----------|------|----------|
| `report-exec` | 领导汇报/项目进展/季度总结 | `enterprise-report` |
| `proposal-client` | 客户提案/商务方案/售前汇报 | `editorial-fintech` |
| `launch-product` | 产品发布/功能介绍/方案宣讲 | `stage-keynote` |
| `training-knowledge` | 培训分享/方法论讲解/知识型演示 | `clean-workspace` |
| `architecture-tech` | 技术架构/系统设计/研发评审 | `precision-saas` |
| `case-story` | 案例复盘/项目展示/成果说明 | `modern-landing` |

不同场景决定语气、密度、版式和视觉风格。无明确说明时，默认 `enterprise-report`，**不默认炫酷深色**。

---

## 三、设计风格预设（6 种）

先定风格，再定配色。风格是第一决策，配色是第二决策。

### 1. `stage-keynote` — 舞台发布
大标题、强主视觉、少字、沉浸式。适用产品发布、重要宣讲。
参考气质：Apple Keynote / Pitch

### 2. `editorial-fintech` — 编辑理性
高级留白、卡片秩序、理性专业、轻渐变。适用客户方案、商业提案。
参考气质：Stripe

### 3. `precision-saas` — 精确科技
深色、精确、模块化、克制科技感。适用 SaaS/AI 工具展示、技术方案。
参考气质：Linear

### 4. `clean-workspace` — 文档知识
干净、轻组件、易读、知识组织。适用培训、方法论、知识型内容。
参考气质：Notion

### 5. `modern-landing` — 现代动态
区块明显、视觉节奏强、轻交互感。适用产品展示、对外介绍、案例。
参考气质：Framer / Gamma

### 6. `enterprise-report` — 企业正式
正式、简洁、可信、商务、稳定。适用领导汇报、项目进展、管理层材料。
参考气质：高端咨询/企业年报

---

## 四、配色主题（第二决策）

| 主题 ID | 名称 | 明暗 | 适用风格 |
|---------|------|------|----------|
| `ink-dark` | 深墨科技 | 深色 | `stage-keynote`, `precision-saas` |
| `navy-tech` | 深蓝专业 | 深色 | `precision-saas`, `editorial-fintech` |
| `report-light` | 商务浅色 | 浅色 | `enterprise-report`, `editorial-fintech` |
| `warm-paper` | 暖白培训 | 浅色 | `clean-workspace` |
| `saas-white` | 白底产品 | 浅色 | `modern-landing`, `editorial-fintech` |
| `mono-minimal` | 极简黑白 | 浅色 | `clean-workspace`, `enterprise-report` |

**规则：**
- 同一份演示只能有 1 套主题，强调色最多 2 个
- 浅色主题优先用于真实企业汇报
- 深色主题只用于发布、产品展示、技术品牌感场景
- 无特殊说明时默认 `report-light`

完整配色变量见 `references/design-system.md`。

---

## 五、两阶段生成（必须遵守）

### 阶段 A：生成演示蓝图

**不允许跳过此步骤直接写 HTML。**

收到内容后，先输出蓝图：

```
蓝图：
- 受众：{谁会看}
- 目标：{演示要达到的效果}
- 场景：{report-exec / proposal-client / ...}
- 风格：{stage-keynote / editorial-fintech / ...}
- 主题：{ink-dark / report-light / ...}
- 叙事路径：{如 cover → problem → insight → solution → metrics → closing}
- 页数：{N 页}

逐页结构：
| # | 类型 | 标题（结论句） | 核心表达 | 密度 | 视觉策略 |
|---|------|---------------|---------|------|---------|
| 1 | cover | ... | ... | low | 主视觉+大标题 |
| 2 | problem | ... | ... | medium | 双栏对比 |
| ... |
```

向用户确认蓝图后，再进入阶段 B。

### 阶段 B：按蓝图渲染 HTML

严格按照蓝图的页面类型和密度渲染，不自由发挥。

---

## 六、页面类型系统（17 种）

每种类型有明确的版式规则，禁止混用或退化为通用布局。

### 封面与导航
| 类型 | 用途 | 版式要点 |
|------|------|---------|
| `cover` | 演示封面 | 大标题+副标题+主视觉/抽象图形，强调首屏舞台感，不堆信息 |
| `agenda` | 目录导航 | 简洁编号列表，不用花哨图形 |
| `section-divider` | 章节分隔 | 大字居中+章节编号，留白为主 |

### 论述与洞察
| 类型 | 用途 | 版式要点 |
|------|------|---------|
| `thesis` | 核心论点 | 大标题+一句话结论+2-3支撑块，中心聚焦 |
| `problem` | 问题陈述 | 左侧问题，右侧影响/症状/代价，双栏或问题矩阵 |
| `insight` | 关键洞察 | 大数字/大结论居中+解释性子块 |
| `quote` | 引用金句 | 居中大字+来源 |

### 方案与展示
| 类型 | 用途 | 版式要点 |
|------|------|---------|
| `solution` | 解决方案 | 上方主张+下面3-4能力块，模块式布局 |
| `feature-grid` | 功能矩阵 | 2×2 或 2×3 特性卡片，图标+标题+一句话 |
| `architecture` | 技术架构 | **必须**有结构图/分层图/数据流图，禁止纯项目符号 |
| `case-study` | 案例展示 | 场景描述+结果数据+可选配图 |

### 数据与对比
| 类型 | 用途 | 版式要点 |
|------|------|---------|
| `metrics` | 数据展示 | 1个主数字突出+2-4次级指标陪衬，禁止多数字同权 |
| `comparison` | 对比分析 | 左右对照+视觉对立，不同色系强调差异，维度必须对齐 |

### 流程与路线
| 类型 | 用途 | 版式要点 |
|------|------|---------|
| `process` | 步骤流程 | 3-6步水平排列，超6步分阶段 |
| `timeline` | 时间轴 | 按时间铺开，强调阶段目标和关键动作 |
| `roadmap` | 路线规划 | 阶段+里程碑+时间标注 |

### 收尾
| 类型 | 用途 | 版式要点 |
|------|------|---------|
| `summary` | 总结回顾 | 回顾3个结论即可，**不做成营销海报** |
| `closing` | 结束页 | 感谢/联系方式/下一步，简洁收尾 |

---

## 七、内容压缩规则（成败关键）

### 标题
- 必须用结论句，不用空洞章节名（❌"项目背景" → ✅"传统流程导致30%效率浪费"）
- 8-20个汉字为佳
- 优先对比式、判断式、结果式

### 正文
- 每页最多 1 个主结论 + 3-5 个支撑点
- 每个支撑点压缩为 1 行
- 连续长段必须拆为短句或分组卡片
- 一页超过 120 个汉字 → 优先拆页

### 数据
- 数据页必须突出 1 个主数字，次要数据做陪衬
- 禁止多个数字同权竞争视觉焦点
- 能图形化就不纯文字罗列

### 对比
- 左右两侧维度必须对齐，项数尽量一致

### 流程
- 3-6 步最佳，超过 6 步分阶段或做时间轴

---

## 八、视觉语言规则

### 1. 节奏变化
禁止每一页都用"标题+横线+光晕球+卡片"。不同页面类型必须形成视觉节奏变化。

### 2. 单一焦点
每页只能有 1 个主视觉焦点（一个大数字 / 一张主图 / 一组对比结构 / 一个中心标题），不允许多焦点竞争。

### 3. 留白优先
重要页面宁可少字也不挤满。视觉上的"贵"来自留白与秩序。

### 4. 图标规则
统一使用线性 SVG 图标，线宽/圆角/尺寸必须一致，禁止 emoji。
```html
<svg class="icon" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <!-- path data -->
</svg>
```

### 5. 图像使用规则
**不是每页都配图。** 只有这些场景用图：
- 封面主视觉
- 概念场景页
- 案例展示页

架构、流程、数据、总结页 → 优先用内联 SVG 图表/结构图，不用 AI 配图。

---

## 九、素材生成策略

### 优先级（从高到低）
1. **内联 SVG 图标/图表/结构图** — 最优先，保持轻量和一致性
2. **CSS 几何与渐变背景** — 纯装饰性视觉
3. **AI 图片生成** — 仅必要时调用

### 只有这些页面考虑 AI 图片
- `cover` — 封面主视觉
- `case-study` — 案例场景图
- `problem` — 需要场景感的页面
- `solution` — 需要概念插图的页面

### 可调用的素材 Skill

| Skill | 用途 | 调用时机 |
|-------|------|----------|
| `baoyu-image-gen` | AI 图片生成 | 封面背景图、概念配图 |
| `baoyu-article-illustrator` | 矢量插画 | 技术示意图、概念可视化 |
| `baoyu-infographic` | 信息图 | 复杂数据可视化 |
| `baoyu-cover-image` | 封面图 | 演示封面大图 |

### 图片风格要求
- 无文字海报感，无花哨摄影拼贴感
- 与整套 deck 风格和配色一致
- 深色主题用暗底配图，浅色主题用亮底配图

### 图片 Prompt 规范
```
[主题关键词], [画面内容描述], [风格指令],
aspect ratio 16:9, presentation slide illustration,
color palette: [匹配当前主题的色调描述],
clean, modern, professional, minimal text
```

---

## 十、HTML 渲染硬约束

### 画布与缩放
- 逻辑尺寸固定 `1600 × 900`
- 使用缩放容器自适应浏览器（transform: scale），不依赖 100vw/100vh
- 内容必须有安全边距（80px 水平，60px 垂直），避免投屏裁切

```css
.deck { position: relative; width: 1600px; height: 900px; overflow: hidden; }
body { display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #000; }
```

### 字体层级
| 用途 | 字号 | 字重 |
|------|------|------|
| 封面标题 | 64-88px | 800 |
| 页面标题 | 34-52px | 700 |
| 副标题/眉标 | 20-28px | 500 |
| 正文 | 18-24px | 400 |
| 标注/脚注 | 12-16px | 400 |
| 主数据 | 72-120px | 800 |
| 次数据 | 36-48px | 700 |

### 行数限制
- 标题最多 2 行
- 说明文字最多 4 行
- 卡片正文最多 5 行
- 超出 → 自动压缩或拆页

### 语义化类名
```
.deck / .slide / .slide-inner
.eyebrow / .slide-title / .slide-subtitle
.metric-primary / .metric-secondary
.panel / .grid / .diagram / .chart
```

### 动画
- 默认轻动效：透明度 + 轻位移（translateY 20px）
- 页面切换不超过 400ms
- 禁止夸张弹跳、旋转、飞入
- 元素依次入场延迟 100ms

---

## 十一、SVG 图表能力

必须内置以下基础 SVG 图表（不依赖外部库）：
- 条形图 / 对比柱图
- 折线趋势图
- 环形占比图
- 阶段进度图

图表要求：
- 少网格线，标注精简
- 主数据高亮，配色与主题一致
- 不伪造过于复杂的 BI 图

---

## 十二、默认叙事路径

| 场景 | 叙事路径 |
|------|---------|
| 工作汇报 | cover → agenda → current status → key progress → challenges → next actions → summary |
| 客户提案 | cover → customer problem → opportunity → solution architecture → key capabilities → implementation path → value/ROI → closing |
| 产品发布 | cover → why now → core problem → product thesis → key features → workflow/demo → proof points → roadmap → closing |
| 培训分享 | cover → agenda → concept → framework → examples → common mistakes → action advice → summary |
| 技术架构 | cover → problem context → design goals → architecture overview → component details → data flow → trade-offs → summary |
| 案例复盘 | cover → background → challenge → approach → implementation → results → lessons → closing |

---

## 十三、输出前自检清单

生成 HTML 前必须逐条校验，发现问题优先自动修正：

1. ☐ 每页是否只有 1 个核心结论
2. ☐ 是否存在文本过密（单页超 120 汉字）
3. ☐ 是否有 2 页以上视觉完全重复
4. ☐ 是否存在不必要的 AI 配图
5. ☐ 是否有 emoji / 花哨按钮 / 网页广告感元素
6. ☐ 主题配色是否全篇统一
7. ☐ 是否有内容溢出画布（1600×900）
8. ☐ 标题是否都是结论句而非空标题
9. ☐ 是否像"演示稿"而非"网页落地页堆叠"
10. ☐ 页面类型是否有节奏变化

---

## 十四、完整工作流程

```
1. 理解内容 → 提取核心信息
2. 判断场景与受众 → 选择场景代号
3. 选择叙事路径 → 确定页面顺序
4. 选择风格预设 → 确定视觉方向
5. 选择配色主题 → 确定色彩方案
6. 生成蓝图 → 每页类型/标题/密度/视觉策略
7. 输出蓝图给用户确认 ← 必须等确认
8. 规划素材 → 哪些页需要图/SVG/图表
9. 生成素材 → 调用 Skill 或绘制内联 SVG
10. 渲染 HTML → 严格按蓝图和类型模板
11. 自检 → 逐条校验清单
12. 输出 index.html + assets/
```

---

## 十五、输出结构

```
{项目名}/
├── index.html          ← 主演示文件
└── assets/
    └── images/          ← AI 生成的配图（如有）
```

输出后告知用户：
- 采用了哪种风格预设和配色主题
- 一共多少页
- 哪些页用了 AI 图，哪些页用了 SVG 结构图
- 浏览器打开 index.html 即可演示

---

## 十六、演示控制

HTML 内置键盘导航：

| 操作 | 快捷键 |
|------|--------|
| 下一页 | `→` / `Space` / `↓` |
| 上一页 | `←` / `↑` |
| 全屏 | `F` |
| 退出 | `Esc` |

底部进度条 + 右下角页码。

---

## 十七、禁止事项（红线）

- ❌ 每页都用相同光晕+横线+卡片组合
- ❌ 默认炫酷深色风覆盖所有场景
- ❌ 机械切段后直接铺满页面
- ❌ 空洞章节名做标题（"项目背景""方案介绍"）
- ❌ 一页塞太多原文（超 120 字不拆页）
- ❌ 所有数据做同尺寸卡片
- ❌ 没有结构图的"技术架构页"
- ❌ 过度依赖 AI 配图
- ❌ 把总结页做成营销海报
- ❌ emoji 做主视觉
- ❌ 混用不同主题配色
- ❌ 依赖外部 CDN
- ❌ 输出不完整 HTML
- ❌ 像网页落地页而非演示稿

---

## 参考文件

- `references/design-system.md` — 完整配色变量、字体、间距、组件规范
- `references/slide-templates.md` — 17 种页面类型的 HTML 模板
