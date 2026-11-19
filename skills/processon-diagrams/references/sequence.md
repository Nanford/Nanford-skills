# 时序图规范（`diagram: "sequence"`）

适用于系统接口调用链路、支付回调、登录鉴权、微服务消息协作等按时间先后交互的场景。

参考成品：`examples/payment-sequence.svg`（由 `examples/payment-sequence.json` 生成）。

---

## JSON 模型

```json
{
  "diagram": "sequence",
  "title": "在线支付下单与异步回调时序图",
  "themeName": "processon-blue",
  "autonumber": true,
  "mirrorFooter": true,
  "participants": [
    { "id": "user", "label": "用户端", "type": "actor" },
    { "id": "order", "label": "订单服务", "type": "participant" },
    { "id": "pay", "label": "支付中心", "type": "participant" },
    { "id": "db", "label": "账务库", "type": "database" }
  ],
  "steps": [
    { "from": "user", "to": "order", "label": "提交订单" },
    { "from": "order", "to": "pay", "label": "创建预支付单" },
    { "from": "pay", "to": "user", "type": "reply", "label": "返回收银台参数" },
    { "type": "note", "over": "user", "position": "right", "label": "用户完成付款" },
    {
      "type": "alt",
      "label": "支付成功",
      "steps": [
        { "from": "pay", "to": "pay", "label": "验签与幂等校验" },
        { "from": "pay", "to": "db", "label": "写入支付流水" },
        { "from": "pay", "to": "order", "type": "async", "label": "MQ通知已支付" }
      ],
      "else": [
        { "label": "回调超时", "steps": [{ "from": "pay", "to": "order", "label": "标记待补单" }] }
      ]
    }
  ]
}
```

---

## 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `diagram` | 是 | 固定填 `"sequence"` |
| `title` | 建议 | 顶部居中标题横幅 |
| `themeName` | 否 | 默认 `processon-teal`，接口/系统交互推荐 `processon-blue` |
| `autonumber` | 否 | `true` 时自动为消息加 `1. `、`2. ` 序号 |
| `mirrorFooter` | 否 | 底部是否重复显示参与者栏（步骤数 >= 7 时默认 `true`） |
| `participants` | 是 | 参与者列表（从左到右）。`type` 可选 `participant`（默认系统框）、`actor`（火柴人角色）、`database`（数据库圆柱） |
| `steps` | 是 | 按时间顺序排列的交互事件列表（兼容 `messages` 字段名） |

**`steps[]` 支持的事件类型：**
- **消息**：`{"from": "a", "to": "b", "label": "...", "type": "sync | reply | async", "activate": true/false, "deactivate": true/false}`
  - `sync`（默认）：实线 + 实心三角箭头；`reply`：虚线返回箭头；`async`：实线 + 开放式 V 形箭头
  - `from == to` 时自动画右侧 U 形自调用回环
- **便签注释**：`{"type": "note", "over": "id" | ["id1", "id2"], "position": "left | right | over", "label": "..."}`
- **组合片段**：`{"type": "alt | opt | loop | par", "label": "条件说明", "steps": [...], "else": [{"label": "分支说明", "steps": [...]}]}`（支持嵌套）
