# 思维导图规范（`diagram: "mindmap"`）

适用于知识体系梳理、产品功能脑图、方案大纲、读书笔记、复盘总结与头脑风暴发散结构。

参考成品：`examples/ai-product-mindmap.svg`（由 `examples/ai-product-mindmap.json` 生成）。

---

## JSON 模型

```json
{
  "diagram": "mindmap",
  "themeName": "processon-teal",
  "layout": "both",
  "root": {
    "label": "企业 AI 落地实施指南",
    "children": [
      {
        "label": "1. 场景筛选",
        "children": [
          { "label": "高频重复痛点", "tag": "P0" },
          {
            "label": "ROI 可量化评估",
            "children": [
              { "label": "人效工时节省" },
              { "label": "转化率与准确率提升" }
            ]
          }
        ]
      },
      {
        "label": "2. 数据与知识库",
        "children": [
          { "label": "文档清洗与分块" },
          { "label": "权限隔离与脱敏", "tag": "必选" }
        ]
      }
    ]
  }
}
```

---

## 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `diagram` | 是 | 固定填 `"mindmap"` |
| `title` | 否 | 可选顶部标题横幅（通常中心主题本身就是标题，省略即可） |
| `themeName` | 否 | 默认 `processon-teal`；每套主题内置 6 色循环主分支色板 |
| `layout` | 否 | `"both"`（左右均衡展开，主分支 >= 4 时默认）或 `"right"`（经典向右逻辑树，适合大纲与目录） |
| `root` | 是 | 思维导图中心主题树 |

**节点字段：**
- `label`（必填，兼容 `name`）：节点文案（建议精炼在 4–12 字，超过自动换行）
- `children`（可选）：子节点数组（支持任意深度：中心主题为强调圆角块 → 一级主分支为彩色实心块 → 二级为彩色描边白底胶囊 → 三级及以下自动切换为 ProcessOn 轻盈彩色下划线样式）
- `tag`（可选）：节点右侧小徽标（如 `"P0"`、`"重点"`、`"必选"`）
- `color`（可选）：自定义分支颜色（`#RRGGBB`），该分支下所有子节点与贝塞尔曲线自动继承此色调
- `side`（可选，仅一级分支在 `layout: "both"` 下有效）：强制指定 `"left"` 或 `"right"`；省略时按高度最均衡点顺时针切分左右两侧
