# ProcessOn 风格配色主题

本文件是所有图种配色的**唯一数据源**：`scripts/core/theme.py` 会直接解析下面每个 `## 主题名` 下的 JSON 代码块。新增主题或扩展新图种的角色色时，只需保持相同格式即可。

ProcessOn 风格的配色原则：

- **低饱和浅色块 + 统一深灰细描边（1px）**，不用纯黑粗边框
- 颜色按**语义角色**分配，而不是按层级渐变：同一种角色全图保持同色
- 框架色（标题、标签、支撑栏、基座）彼此区分，内容区以白底节点为主，保持高可读性

## 色值角色说明

### 通用基础色（所有图种共用）

| 字段 | 角色 | 说明 |
|------|------|------|
| `background` | 画布背景 | 白色画布 |
| `text` | 全部文字 | 深灰黑，保证对比度 |
| `stroke` | 全部描边（1px） | 所有框线 |
| `titleFill` | 顶部标题横幅 | 全图大标题背景 |
| `nodeFill` | 普通节点 | 白底节点 |
| `iconColor` | 流程图标线条色 | 纯线框图标描边 |
| `lineColor` | 连接线与箭头 | 直线/折线与几何箭头 |

### 分层架构图角色色（`diagram: "architecture"`）

| 字段 | 角色 | 参考示例位置 |
|------|------|-------------|
| `labelFill` | 左侧竖排层标签 | "展现层 / 微服务应用层 / 基础设施" |
| `sideFill` | 右侧竖向支撑栏 | "自动化运维保障体系" |
| `entryFill` | 入口 / 终端节点 | "H5、小程序 / PC / APP" |
| `bannerFill` | 通栏横幅（网关、总线等） | "网关、Gateway路由、鉴权…" |
| `cardHeaderFill` | 服务卡片表头 / 高亮节点 | "用户服务 / 商品服务" 表头 |
| `cardBodyFill` | 服务卡片主体 | 卡片白色主体 |
| `panelFill` | 彩色面板（侧挂面板、底层服务条） | "服务发现…" 面板、"底层服务" 条 |
| `softNodeFill` | 面板内的浅色节点 | "pod" |
| `containerFill` | 灰色大容器 | 基础设施外框 |
| `innerFill` | 容器内的子区块 | 数据流程区、日志区 |
| `baseFill` | 底部基座横幅 | "云服务" |

---

## processon-teal

默认主题，还原 ProcessOn 经典模板配色（青绿 + 杏色 + 浅绿）。适用：通用 / 互联网 / 电商。

```json
{
  "background": "#FFFFFF",
  "text": "#262626",
  "stroke": "#4D4D4D",
  "titleFill": "#90DDDB",
  "labelFill": "#FBE5D6",
  "sideFill": "#E2F0D9",
  "entryFill": "#D3EDC4",
  "bannerFill": "#FDF8EE",
  "cardHeaderFill": "#B4E7E7",
  "cardBodyFill": "#FFFFFF",
  "nodeFill": "#FFFFFF",
  "panelFill": "#B4E7E7",
  "softNodeFill": "#DDF4F4",
  "containerFill": "#E6E9EC",
  "innerFill": "#DAF4F5",
  "baseFill": "#BFBFBF",
  "iconColor": "#4A9DA3",
  "lineColor": "#333333"
}
```

---

## processon-blue

科技蓝。适用：软件 / SaaS / 云平台 / 数据中台。

```json
{
  "background": "#FFFFFF",
  "text": "#1F2D3D",
  "stroke": "#4D5866",
  "titleFill": "#8DB8EA",
  "labelFill": "#DCE8F8",
  "sideFill": "#E3EEF9",
  "entryFill": "#CFE2F7",
  "bannerFill": "#F4F8FE",
  "cardHeaderFill": "#BBD5F2",
  "cardBodyFill": "#FFFFFF",
  "nodeFill": "#FFFFFF",
  "panelFill": "#BBD5F2",
  "softNodeFill": "#E3EEFA",
  "containerFill": "#E8EBEF",
  "innerFill": "#EAF2FB",
  "baseFill": "#BFC6CF",
  "iconColor": "#3D6FA8",
  "lineColor": "#2F3B4A"
}
```

---

## processon-green

清新绿。适用：医疗 / 能源 / 环保 / 农业。

```json
{
  "background": "#FFFFFF",
  "text": "#23302A",
  "stroke": "#4D5A52",
  "titleFill": "#A9D18E",
  "labelFill": "#E2EFDA",
  "sideFill": "#EAF4E4",
  "entryFill": "#D5EBC8",
  "bannerFill": "#F7FBF3",
  "cardHeaderFill": "#C5E0B4",
  "cardBodyFill": "#FFFFFF",
  "nodeFill": "#FFFFFF",
  "panelFill": "#C5E0B4",
  "softNodeFill": "#E6F2DE",
  "containerFill": "#E8EBE7",
  "innerFill": "#EDF6E8",
  "baseFill": "#BCC4B8",
  "iconColor": "#548235",
  "lineColor": "#2E3A32"
}
```

---

## processon-orange

活力橙。适用：营销 / 零售 / 创意 / 品牌。

```json
{
  "background": "#FFFFFF",
  "text": "#3A2A20",
  "stroke": "#5C4D44",
  "titleFill": "#F8CBAD",
  "labelFill": "#FCE4D6",
  "sideFill": "#FFF2CC",
  "entryFill": "#FBE0C8",
  "bannerFill": "#FFFAF3",
  "cardHeaderFill": "#F9D5B8",
  "cardBodyFill": "#FFFFFF",
  "nodeFill": "#FFFFFF",
  "panelFill": "#F9D5B8",
  "softNodeFill": "#FDEBDD",
  "containerFill": "#ECE8E5",
  "innerFill": "#FEF1E6",
  "baseFill": "#C9C0BA",
  "iconColor": "#C55A11",
  "lineColor": "#3A2A20"
}
```

---

## processon-gray

商务灰。适用：政企 / 金融 / 合规 / 审计等正式汇报场景。

```json
{
  "background": "#FFFFFF",
  "text": "#1F2329",
  "stroke": "#4E5560",
  "titleFill": "#C9D3DE",
  "labelFill": "#E4E8ED",
  "sideFill": "#EDF0F3",
  "entryFill": "#DCE3EB",
  "bannerFill": "#F7F8FA",
  "cardHeaderFill": "#D3DCE6",
  "cardBodyFill": "#FFFFFF",
  "nodeFill": "#FFFFFF",
  "panelFill": "#D3DCE6",
  "softNodeFill": "#EDF1F5",
  "containerFill": "#E9ECEF",
  "innerFill": "#F3F5F7",
  "baseFill": "#B8BEC6",
  "iconColor": "#4F6275",
  "lineColor": "#2B3036"
}
```
