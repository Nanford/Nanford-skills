# 组织结构图规范（`diagram: "orgchart"`）

适用于公司组织架构、项目交付团队分工、汇报关系、WBS 工作分解结构等树形层级展示。

参考成品：`examples/company-orgchart.svg`（由 `examples/company-orgchart.json` 生成）。

---

## JSON 模型

```json
{
  "diagram": "orgchart",
  "title": "星辰科技有限公司组织架构图",
  "themeName": "processon-blue",
  "root": {
    "name": "总经理（CEO）",
    "subtitle": "张明",
    "assistants": [
      { "name": "总经办 / 法务合规", "subtitle": "4人" }
    ],
    "children": [
      {
        "name": "产研中心",
        "subtitle": "CTO · 李华",
        "children": [
          {
            "name": "工程研发部",
            "subtitle": "38人",
            "children": [
              { "name": "前端与移动组" },
              { "name": "中台架构组" },
              { "name": "AI算法组" }
            ]
          }
        ]
      },
      {
        "name": "商业增长中心",
        "subtitle": "VP · 王芳",
        "layout": "vertical",
        "children": [
          { "name": "大客户销售部", "subtitle": "18人" },
          { "name": "解决方案售前部", "subtitle": "10人" }
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
| `diagram` | 是 | 固定填 `"orgchart"` |
| `title` | 建议 | 顶部居中标题横幅 |
| `themeName` | 否 | 默认 `processon-teal`，企业汇报推荐 `processon-blue` 或 `processon-gray` |
| `root` | 是 | 递归树根节点 |

**树节点通用字段：**
- `name`（必填，兼容 `label`）：主标题（部门名 / 岗位名 / WBS 阶段名）
- `subtitle`（可选，兼容 `role`）：副标题（负责人 / 人数 / 职责简述）
- `assistants`（可选）：参谋/助理节点数组，自动从当前领导正下方主干右侧引出
- `children`（可选）：下级节点数组
- `layout`（可选）：`"horizontal"`（横向 T 型总线）或 `"vertical"`（左侧总线紧凑纵向列表）。省略时，深度 >= 2 且包含 >= 3 个全叶子子节点会自动切换为 `"vertical"`，避免整图过宽
- `variant`（可选）：`"highlight"`（深色白字强调）或 `"external"`（虚线外包/外协团队）
- `fill`（可选）：自定义背景色；默认按层级自动配色（根节点深色白字 → 一级/二级浅色 → 末级白底）
