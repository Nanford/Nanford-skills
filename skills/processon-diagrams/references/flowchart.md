# 普通流程图规范（`diagram: "flowchart"`）

适用于算法逻辑流、业务决策流程、异常处理流程、状态流转与操作指引（不涉及多部门泳道分工时优先使用本图种）。

参考成品：`examples/order-flowchart.svg`（由 `examples/order-flowchart.json` 生成）。

---

## JSON 模型

```json
{
  "diagram": "flowchart",
  "title": "订单支付与异常处理流程图",
  "themeName": "processon-teal",
  "direction": "TB",
  "nodes": [
    { "id": "start", "type": "start", "col": 1, "row": 0, "label": "提交订单" },
    { "id": "chk", "type": "decision", "col": 1, "row": 1, "label": "库存是否\n充足" },
    { "id": "out", "type": "process", "col": 0, "row": 1, "label": "提示库存不足" },
    { "id": "lock", "type": "process", "col": 1, "row": 2, "label": "锁定库存", "variant": "highlight" },
    { "id": "db", "type": "database", "col": 1, "row": 3, "label": "写订单流水" },
    { "id": "end", "type": "end", "col": 1, "row": 4, "label": "流程结束" }
  ],
  "groups": [
    { "title": "异常兜底区", "nodes": ["out"] }
  ],
  "edges": [
    { "from": "start", "to": "chk" },
    { "from": "chk", "to": "out", "label": "否" },
    { "from": "chk", "to": "lock", "label": "是" },
    { "from": "lock", "to": "db" },
    { "from": "db", "to": "end" }
  ]
}
```

---

## 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `diagram` | 是 | 固定填 `"flowchart"` |
| `title` | 建议 | 顶部居中大标题横幅 |
| `themeName` | 否 | 默认 `processon-teal` |
| `direction` | 否 | `"TB"`（纵向，默认）或 `"LR"`（横向） |
| `nodes` | 是 | 节点数组：`id`、`label`、`type`、可选 `col`/`row`、`variant`（`highlight`/`external`）、`fill` |
| `groups` | 否 | 虚线背景分组框：`[{"title": "分组名", "nodes": ["id1", "id2"], "fill": "..."}]` |
| `edges` | 否 | 连线数组：`from`、`to`、可选 `label`、`dashed`、`fromPort`/`toPort`、`labelPos` |

**支持图元（`nodes[].type`）**：`start` / `end`（起止胶囊）、`process`（圆角矩形，默认）、`decision`（判断菱形）、`data`（平行四边形）、`subflow`（双竖线子流程）、`document`（波浪底文档）、`database`（数据库圆柱）。

**排布建议**：
- 简单线性/树形流程可省略 `col`/`row`，由内置环安全拓扑分层自动排布。
- 含多分支与回退环（如“重试”“驳回”）的复杂流程图，显式写出 `(col, row)` 并把主干放中间列（如 `col: 1`），异常/分支分列左右（`col: 0` / `col: 2`），回退边可用 `fromPort`/`toPort` 精细控制出口方向。
