---
name: svg-architecture-diagram
description: 将任意架构文字描述转化为专业的 SVG 信息架构图。当用户提到"画架构图"、"生成系统图"、"可视化架构"、"画流程图"、"信息架构"、"组织结构图"、"数据流图"、"业务流程图"，或提供了一段架构描述希望图形化展示时，必须触发此 Skill。即使用户只是描述了一个系统的组成部分和关系，也应主动使用本 Skill 生成 SVG 图表，而不是用文字或 Mermaid 代替。
---

# SVG 信息架构图生成 Skill

将用户提供的任何架构文字描述，转化为结构清晰、视觉专业、可直接渲染的 SVG 架构图。目标受众是产品经理和业务团队，风格为高对比度商务风格。

---

## 工作流程

拿到用户的描述后，按以下顺序完成任务：

**第一步：理解与分析**
深度解读用户描述，识别架构类型（系统架构 / 业务流程 / 组织结构 / 数据流等），提取所有层级、组件、节点以及它们之间的连接关系。若存在关键歧义，先向用户澄清，或基于最佳实践做假设并明确告知。

同时确定：
- **画布模式**：根据内容复杂度和用户需求选择 `standard`（1400×1000）或 `widescreen`（1920×1080）
- **配色主题**：根据行业/场景自动匹配，或按用户指定

**第二步：输出 JSON 架构模型**
将信息转换为以下结构化 JSON，作为第一部分交付：

```json
{
  "canvasMode": "standard",
  "themeName": "default",
  "canvas": {"w": 1400, "h": 1000},
  "direction": "TTB",
  "theme": {
    "background": "#FFFFFF",
    "layerFills": ["#FFE0B2", "#FFCC80", "#B9F6CA", "#C5CAE9", "#90CAF9"],
    "nodeFill": "#FFFFFF",
    "nodeStroke": "#333333",
    "primaryText": "#000000",
    "secondaryText": "#333333",
    "accentColor": "#FFAB91",
    "lineColor": "#333333"
  },
  "layers": [
    {
      "id": "layer1",
      "title": "层级名称",
      "blocks": [
        {
          "id": "block1",
          "title": "模块标题",
          "layout": "horizontal",
          "nodes": [
            {
              "id": "node1",
              "label": "节点名称",
              "type": "gateway",
              "metadata": { "description": "节点说明" }
            }
          ]
        }
      ]
    }
  ],
  "connections": [
    {
      "from": "node1",
      "to": "node2",
      "label": "连接说明",
      "style": {
        "stroke": "#333333",
        "strokeWidth": 2,
        "strokeDasharray": "5 5"
      }
    }
  ]
}
```

**第三步：生成完整 SVG 代码**
基于 JSON 模型，生成完整可渲染的 SVG，作为第二部分交付。

---

## 画布模式

| 模式 | 字段值 | 尺寸 | 适用场景 |
|------|--------|------|---------|
| 标准 | `"standard"` | 1400×1000 | 常规架构图（默认） |
| 宽屏 | `"widescreen"` | 1920×1080 | 16:9 演示、横向层级较多的架构 |

在 JSON 模型中通过 `canvasMode` 字段指定，`canvas.w` 和 `canvas.h` 对应更新。

---

## 配色主题系统

通过 JSON 中的 `themeName` 字段选择预设主题，`theme` 对象填充对应色值。

| 主题名 | 适用场景 | 风格简述 |
|--------|---------|---------|
| `default` | 通用多彩 | 橙/绿/紫/蓝分层，当前经典风格 |
| `tech-blue` | 科技/软件/SaaS | 蓝色系渐变，科技感 |
| `ocean-dark` | 科技/暗色模式 | 深色背景 + 蓝青高亮 |
| `healthcare` | 医疗/健康/制药 | 柔蓝+绿色信任色系 |
| `finance` | 金融/银行/保险 | 藏青+金色 |
| `forest-green` | 能源/环保/可持续 | 森林绿色系 |
| `enterprise` | 政企/合规/审计 | 中性灰+蓝色强调 |
| `warm-creative` | 营销/创意/品牌 | 暖橙+品红 |

各主题的完整色值定义见 `references/color-themes.md`。

**自动匹配规则**：根据用户描述的行业关键词自动选择主题。若用户明确指定主题名或色系偏好，优先使用用户指定。无法判断时使用 `default`。

---

## SVG 技术规范

### 画布与整体结构
- 画布尺寸使用 JSON 中定义的宽高
- SVG 必须包含 `<style>`（通用样式）和各层注释
- **不使用 `<defs>` 中的 `<marker>` 箭头**，改用几何拼接箭头（见下文）
- 字体：`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`

### 层级背景配色
- 不同层级使用 `theme.layerFills` 数组中的颜色作为背景色，形成视觉分区
- 若层级数量超过 5 个，循环使用 `layerFills` 数组
- 层间距 24px，层标题 20px 字号，左上角显示，颜色使用 `theme.primaryText`
- 每层背景矩形使用对应的 `layerFills` 色值填充

### 边框与描边
- 所有层级、模块、节点边框使用 `theme.nodeStroke`，描边宽度 1.5px 或 2px
- 模块使用虚线边框：`stroke-dasharray="4 4"`

### 节点样式
- 矩形背景使用 `theme.nodeFill`，边框使用 `theme.nodeStroke`，圆角 2px
- 节点最小尺寸 160×48px，等宽布局
- 节点标题 16px，模块标题 18px，颜色使用 `theme.primaryText`

### 连接线
- 使用 `<path>` 绘制贝塞尔曲线或折线，颜色使用 `theme.lineColor`
- 连接线本身**不带** `marker-end` 属性
- 虚线连接用 `stroke-dasharray="5 5"` 表示非强依赖关系
- 需要标注流向时，在连接线的**终点**位置放置几何拼接箭头

### 几何拼接箭头（核心规范）

**禁止使用 `<marker>` 定义箭头。** 所有数据流向箭头使用 SVG 基础图形（矩形 + 三角形）拼接：

```xml
<!-- 几何拼接箭头模板 -->
<!-- 通过 translate 定位到连接线终点附近，通过 rotate 控制方向 -->
<g class="flow-arrow" transform="translate(x, y) rotate(angle)">
  <!-- 线身：矩形 -->
  <rect x="0" y="-4" width="40" height="8" fill="{lineColor}" rx="1"/>
  <!-- 箭头头部：三角形 -->
  <polygon points="40,-10 40,10 56,0" fill="{lineColor}"/>
</g>
```

**箭头规则：**
- `<rect>` 作为箭头线身，`<polygon>` 三角形作为箭头头部
- 通过 `transform="translate(x, y) rotate(angle)"` 控制位置和方向
- `fill` 颜色使用 `theme.lineColor`
- 箭头放置在连接线的终点位置，标注数据流方向
- 大小可根据图表密度适当调整（缩放线身宽度和三角形大小）
- 常用方向角度：向右 0°、向下 90°、向左 180°、向上 270°

**方向变体示例：**

```xml
<!-- 向右箭头 -->
<g class="flow-arrow" transform="translate(300, 200) rotate(0)">
  <rect x="0" y="-4" width="40" height="8" fill="#333" rx="1"/>
  <polygon points="40,-10 40,10 56,0" fill="#333"/>
</g>

<!-- 向下箭头 -->
<g class="flow-arrow" transform="translate(500, 300) rotate(90)">
  <rect x="0" y="-4" width="40" height="8" fill="#333" rx="1"/>
  <polygon points="40,-10 40,10 56,0" fill="#333"/>
</g>

<!-- 向左箭头 -->
<g class="flow-arrow" transform="translate(200, 400) rotate(180)">
  <rect x="0" y="-4" width="40" height="8" fill="#333" rx="1"/>
  <polygon points="40,-10 40,10 56,0" fill="#333"/>
</g>
```

### 代码结构要求

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="{canvas.w}" height="{canvas.h}">
  <style>
    /* 通用样式：字体、文字颜色等 */
  </style>

  <!-- 背景 -->
  <rect width="100%" height="100%" fill="{background}"/>

  <!-- 层级1：应用层 -->
  <g id="layer1">...</g>

  <!-- 层级2：业务服务层 -->
  <g id="layer2">...</g>

  <!-- 连接线 -->
  <g id="connections">
    <!-- path 连接线（不带 marker-end） -->
    <path d="..." stroke="{lineColor}" fill="none" stroke-width="2"/>
    <!-- 几何拼接箭头 -->
    <g class="flow-arrow" transform="translate(x, y) rotate(angle)">
      <rect x="0" y="-4" width="40" height="8" fill="{lineColor}" rx="1"/>
      <polygon points="40,-10 40,10 56,0" fill="{lineColor}"/>
    </g>
  </g>
</svg>
```

---

## 禁止项

- 禁止省略用户描述中的任何架构细节
- 禁止使用卡通或花哨风格
- 禁止引用外部资源或外部字体
- 禁止输出无法直接渲染的不完整 SVG
- 禁止用 Mermaid 或文字描述替代 SVG 图（除非用户明确要求）
- **禁止使用 `<marker>` 定义箭头**，必须使用几何拼接箭头
- **禁止在连接线 `<path>` 上使用 `marker-end` 属性**

---

## 输出格式

最终交付必须包含两部分：

**第一部分**：高级 JSON 架构分析（按上述结构，包含 `canvasMode` 和 `themeName` 字段）

**第二部分**：完整 SVG 代码，以 ` ```svg ` 代码块包裹，包含从 `<svg>` 到 `</svg>` 的全部内容，并为每个主要层级添加 HTML 注释。
