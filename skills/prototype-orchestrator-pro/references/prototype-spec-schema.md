# ProductSpec Schema

产品建模的中间规格，合并了产品拆解和原型规格。不是 PRD，而是「原型编排协议」。

## Schema 定义

```json
{
  "product_type": "B端后台 | C端工具 | 移动端 | 可视化大屏 | 混合型",
  "input_source_type": "口语化需求 | 会议纪要 | 半结构化需求 | 目标导向型需求 | 需求文档",
  "target_users": ["角色1", "角色2"],
  "core_goals": ["目标1", "目标2"],

  "navigation_model": "左侧导航 | 顶部导航 | 底部Tab | 单页 | 混合导航",
  "responsive_strategy": "PC优先 | 移动优先 | 自适应",
  "multi_page_routing": {
    "mode": "hash路由 | 单页Tab切换",
    "pages": ["page_id_1 → page_id_2 via 按钮点击"]
  },

  "design_style": {
    "preset": "industrial-b | command-center | saas-clean | mobile-tool | dashboard-analytics | crm-portal",
    "theme": "工业风 | 简洁商务 | 消费友好 | 暗色大屏 | 极简工具 | 数据分析 | 客户门户",
    "density": "高密度 | 中密度 | 低密度"
  },

  "feature_modules": [
    {
      "module": "模块名",
      "priority": "P0 | P1 | P2",
      "description": "一句话描述",
      "pages": ["页面A", "页面B"]
    }
  ],

  "entities": [
    {
      "name": "实体名",
      "description": "例如任务/工单/设备",
      "key_fields": ["字段1", "字段2"],
      "states": ["状态1", "状态2"]
    }
  ],

  "roles": [
    {
      "name": "角色名",
      "tasks": ["核心任务1", "核心任务2"],
      "accessible_pages": ["page_id_1", "page_id_2"]
    }
  ],

  "main_flow": [
    "步骤1：进入总览页查看总体状态",
    "步骤2：通过筛选进入列表页定位对象",
    "步骤3：打开详情层查看详情",
    "步骤4：执行处理动作并看到反馈"
  ],

  "page_specs": [
    {
      "page_id": "page_overview",
      "page_name": "总览页",
      "page_type": "总览页 | 列表页 | 详情页 | 表单页 | 看板页 | 大屏页",
      "page_goal": "一句话描述页面价值",
      "priority_level": "P0 | P1 | P2",
      "primary_roles": ["角色1"],
      "layout_zones": ["顶部区", "筛选区", "指标区", "列表区"],
      "components": [
        {
          "zone": "指标区",
          "type": "统计卡片",
          "title": "在途任务",
          "data_fields": ["任务数", "同比变化"],
          "mock_data": ["128", "+12%"],
          "action": "点击进入任务列表"
        }
      ],
      "interactions": [
        {
          "trigger": "点击卡片",
          "action": "跳转列表页",
          "target": "任务列表页",
          "feedback": "视图切换"
        }
      ],
      "states": {
        "loading": "骨架屏或局部 loading",
        "empty": "空状态图示 + 说明",
        "error": "错误提示 + 重试",
        "no_permission": "无权限提示"
      },
      "navigation_links": ["导航切换到页面A", "组件跳转到页面B"]
    }
  ],

  "mock_data_strategy": "写实型 | 占位型 | 行业型",

  "design_system": {
    "list_page_pattern": "筛选区 + 操作区 + 表格区 + 分页区",
    "detail_page_pattern": "摘要区 + 页签区 + 历史区",
    "form_pattern": "分组表单 + 固定底部按钮",
    "modal_usage": "轻量编辑 / 二次确认 / 简单表单",
    "drawer_usage": "详情查看 / 复杂筛选 / 历史记录",
    "button_hierarchy": "主按钮、次按钮、危险按钮、链接按钮"
  },

  "assumptions": ["默认推断1", "默认推断2"]
}
```

## 页面最低要求

每个页面至少满足：
- 1 个明确页面目标
- 3 个以上组件
- 2 条以上交互
- 4 类状态处理（loading / empty / error / no_permission）
- 1 组以上 mock data

## 首轮页面优先级

P0（必须渲染）：首页/总览页 + 核心列表页
P1（推荐渲染）：详情层（抽屉/弹窗/详情页）
P2（按需渲染）：表单页、设置页、次要功能页

首轮不要贪多，优先 P0 + P1。

## 页面类型选择

| 用户强调 | 优先页面类型 |
|----------|-------------|
| "整体看板" | 总览页 |
| "查找和处理" | 列表页 |
| "编辑和录入" | 表单页 |
| "流程推进" | 看板页或流程详情页 |
| "数据趋势" | 图表看板页 |

## Mock Data 策略

在 ProductSpec 中通过 `mock_data_strategy` 字段指定：`写实型`（客户演示）、`占位型`（内部评审）或 `行业型`（行业原型）。具体数据要求见 `references/rendering-prompt-template.md` 的 Mock Data 部分。
