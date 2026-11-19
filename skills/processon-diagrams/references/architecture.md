# 分层架构图规范（`diagram: "architecture"`）

适用于系统架构图、技术架构图、应用架构图、数据平台架构图、总体架构图。

参考成品：`examples/ecommerce.svg`（由 `examples/ecommerce.json` 生成）。

---

## JSON 模型

```json
{
  "diagram": "architecture",
  "title": "XX系统总体架构图",
  "themeName": "processon-teal",
  "canvas": { "w": 1200 },
  "sideBar": { "title": "自动化运维保障体系" },
  "layers": [
    {
      "label": "展现层",
      "rows": [
        { "type": "entry", "nodes": ["H5、小程序", "PC", "APP", "管理端"] }
      ]
    },
    {
      "label": "应用层",
      "rows": [
        { "type": "banner", "text": "统一网关、路由、鉴权、限流熔断" },
        {
          "type": "cards",
          "columns": [
            [
              { "title": "用户服务", "nodes": ["注册", "登录"] },
              { "title": "物流服务", "nodes": ["查询"] }
            ],
            [
              { "title": "订单服务", "cols": 2, "nodes": ["下单", { "id": "pay", "label": "支付", "variant": "highlight" }] }
            ]
          ],
          "aside": { "title": "可选标题", "nodes": ["服务注册", "配置中心", "监控告警"] }
        }
      ]
    },
    {
      "label": "基础设施",
      "rows": [
        { "type": "panel", "title": "底层服务", "nodes": ["pod", "pod"] },
        {
          "type": "container",
          "title": "可选标题",
          "children": [
            { "type": "flow", "steps": [{ "label": "数据采集", "icon": "collect" }, { "label": "数据存储", "icon": "storage" }] },
            { "type": "nodes", "title": "可选标题", "nodes": ["系统日志", "业务数据"] }
          ]
        }
      ]
    }
  ],
  "base": { "text": "云服务" },
  "connections": [
    { "from": "nodeA", "to": "pay", "label": "调用", "dashed": false }
  ]
}
```

### 顶层字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `diagram` | 建议 | 填 `"architecture"`（省略时默认也是 `"architecture"`） |
| `title` | 建议 | 顶部标题横幅文字，不填则不画横幅 |
| `themeName` | 否 | 配色主题，默认 `processon-teal`，见 `references/color-themes.md` |
| `theme` | 否 | 覆盖主题中的个别色值，例如 `{"titleFill": "#9DC3E6"}` |
| `canvas.w` | 否 | 画布宽度，默认 1200；内容多时用 1400–1600。画布高度自动计算 |
| `sideBar` | 否 | 右侧竖向支撑栏，贯穿所有层（安全体系、运维体系、标准规范等） |
| `layers` | 是 | 自上而下的层级；每层的 `label` 显示为左侧竖排标签 |
| `base` | 否 | 底部通栏基座（云服务、IDC、IaaS 等） |
| `connections` | 否 | 节点间连线，按节点 `id` 引用（见下文「连线规则」） |

---

## 行类型（`layers[].rows[].type`）

| type | 视觉样式 | 适用内容 | 字段 |
|------|---------|---------|------|
| `entry` | 一排浅色方角节点，等距分布 | 终端、渠道、用户入口 | `nodes` |
| `banner` | 通栏浅色横条，居中文字 | 网关、ESB、统一门户等横向能力 | `text` |
| `cards` | 多列服务卡片（彩色表头 + 白底圆角节点网格），右侧可选挂竖向面板 | 微服务、业务域、子系统 | `columns`（二维数组：列 → 卡片），`aside`（含 `nodes`，可选 `title`、`w`） |
| `panel` | 彩色横条，左侧标题，右侧浅色节点 | 底层服务、中间件、公共组件 | `title`，`nodes` |
| `container` | 灰色大容器，内部纵向堆叠子区块 | 数据平台、基础设施等需要再分区的层 | `title`（可选），`children` |

`container.children` 支持 3 种类型：
- `flow`：横向流程，步骤间自动画箭头，默认虚线外框（可设 `"dashed": false`）。`steps[].icon` 可选值：`collect` `clean` `compute` `analyze` `storage` `database` `server` `cloud` `user` `security` `message` `monitor` `api`。不写 `icon` 时画成白色节点框。
- `nodes`：浅色框内一排白色节点，可选 `title`、`dashed`。
- `panel`：同上表的 `panel` 行。

---

## 卡片与节点

- 卡片：`{"title": "用户服务", "cols": 2, "nodes": [...]}`。`cols` 默认 2；节点多或名称短时用 3。
- 同列多张卡片纵向堆叠，**每列最后一张卡片自动拉伸**，保证各列底部对齐。
- 节点既可直接写字符串，也可写对象 `{"id": "x", "label": "名称", "variant": "highlight | external"}`：
  - `highlight`：卡片表头色填充 + 加粗，用于核心/本期新建模块
  - `external`：虚线边框，用于外部系统或第三方接口
  - `id`：仅在需要被 `connections` 引用时填写

---

## 布局常量（脚本已实现，手写 SVG 时照此计算）

- 画布左右边距 `40`，上边距 `16`；左侧标签栏宽 `40`，右侧支撑栏宽 `40`，与内容区间隔 `16`
- 内容区 x 范围：`40 + (有标签 ? 56 : 0)` 到 `W − 40 − (有支撑栏 ? 56 : 0)`
- 层间距 `16`，层内行间距 `14`；顶部标题高 `44`，底部基座高 `44`
- 节点默认高 `40`；卡片表头高 `40`，卡片内边距与节点间距 `12`，卡片间距 `14`，侧挂面板默认宽 `130`
- 横排节点采用 space-evenly 分布：`gap = (可用宽 − n · w) / (n + 1)`
- 卡片内节点宽：`(卡片宽 − 2 · 12 − (cols − 1) · 12) / cols`

---

## 连线规则

ProcessOn 架构图主要靠**层级位置与包含关系**表达结构，连线应克制：

- 层与层之间的调用关系靠上下排列表达，**不要**给每一层都画箭头
- 仅在需要说明关键数据流或调用链时使用 `connections`，全图建议不超过 5 条
- 只连接**相邻且中间没有其他节点**的两个节点（上下相邻层或同行左右邻居），避免连线穿越无关节点
- 线性处理链路（如"采集 → 清洗 → 计算 → 存储"）使用 `container` 中的 `flow`，不要用 `connections` 拼装

---

## 架构图专属自检

在完成 `references/style-guide.md` 通用自检外，额外确认：

- [ ] 各列卡片底部对齐，右侧 `aside` 面板与卡片区等高
- [ ] 左侧层标签与对应层上下边界对齐，竖排文字无挤压截断
- [ ] 如使用 `sideBar`，其上下边界与所有层对齐（不含标题横幅与底部基座）
