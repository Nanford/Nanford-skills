---
name: prototype-orchestrator-pro
description: 将口语化需求、会议纪要、聊天记录或半结构化需求文档编排为可交互的单文件 HTML 产品原型。用于“帮我做原型”“把需求变成界面”“根据会议纪要出后台页面”“做个低保真/中保真页面”“prototype from requirements”“convert notes to UI”等场景；先归一需求，再输出 ProductSpec、页面方案与 frontend-design 渲染指令。
---

# Prototype Orchestrator Pro

把模糊需求转成可评审、可渲染的原型规格，而不是只列功能点。

## 按阶段工作

只在当前阶段读取必要资源，避免一次性加载全部上下文。

1. 识别输入类型和输出模式。
   - 读取 `references/input-normalization.md`。
   - 将输入识别为：口语化需求、会议纪要、半结构化需求、目标导向型需求、需求文档。
   - 用户只说“先看效果”“先出图”“不用解释太多”时，切换到快速模式。
2. 建立产品规格。
   - 读取 `references/prototype-spec-schema.md`。
   - 选择视觉预设时，再读取 `references/design-presets.md`。
3. 展开页面和交互。
   - 需要具体交互时，读取 `references/interaction-recipes.md`。
4. 生成渲染交接。
   - 读取 `references/rendering-prompt-template.md` 和 `references/html-rendering-spec.md`。
   - 需要骨架时，再读取 `assets/prototype-template.html`。
   - 只在此阶段读取 `frontend-design` skill。
5. 结束前自检。
   - 读取 `references/output-quality-checklist.md`。

需要校准输出风格时，再读取 `examples/meeting-notes-to-prototype.md`。

## 坚持这些原则

- 先归一事实，再做页面。
- 先定义角色、任务、页面树和状态，再做视觉。
- 把补全内容标记为 `[默认推断]`，不要伪装成已确认需求。
- 除非缺失会改变产品方向，否则不要频繁追问。
- 永远输出页面、动作、状态和跳转，不要只输出模块名。

## 选择运行模式

### 快速模式

在用户更看重“先看到效果”时使用。

输出：
- `[需求解析摘要（压缩版）]`
- `[页面设计方案]`
- `[原型渲染指令]`

规则：
- 只保留主链路。
- 默认先做 1 个总览页 + 1 个列表页 + 1 个详情层。
- 默认先渲染 P0，再补 P1。

### 专业模式

在用户需要需求梳理、方案评审或多角色页面结构时使用。

按顺序输出：
1. `[需求解析摘要]`
2. `[产品建模结果]`
3. `[页面设计方案]`
4. `[原型渲染指令]`

## 产出每个阶段

### 产出 `[需求解析摘要]`

提取并整理：
- 产品方向
- 目标用户
- 业务目标
- 关键对象
- 已确认事实
- `[默认推断]`
- 待确认项（最多 5 条，只保留高影响项）

会议纪要额外提炼：
- 已达成结论
- 待办项
- 优先级
- 争议点

### 产出 `[产品建模结果]`

严格按 `references/prototype-spec-schema.md` 组织，至少包含：
- 角色清单
- 模块清单
- 页面清单（P0 / P1 / P2）
- 主流程
- 关键实体与状态
- 权限边界
- 视觉预设选择与理由

### 产出 `[页面设计方案]`

为每个核心页面输出：

```md
### 页面名
- 页面目标：
- 适用角色：
- 页面布局：
- 核心区域：
- 核心字段 / 数据：
- 主操作 / 次操作：
- 交互行为（至少 2 条）：
- 状态反馈（loading / empty / error / no_permission）：
- 页面跳转关系：
```

满足最低要求：
- 每页至少 3 个组件
- 每页至少 2 条可执行交互
- 每页覆盖 4 类状态
- 每页至少 1 组 mock data

### 产出 `[原型渲染指令]`

把结构化结果转成交给 `frontend-design` 的明确任务。

要求：
- 指定产品类型、导航模型、响应策略和视觉预设。
- 指定首批渲染页面，默认先 P0。
- 使用 `references/rendering-prompt-template.md` 的结构。
- 遵循 `references/html-rendering-spec.md`。
- 输出单文件 HTML，内联 CSS 和 JS，使用 Hash 路由。
- 只实现原型层交互，不补业务后端。
- 使用与场景一致的 mock data。

## 选择视觉预设

按业务方向选择，不按个人偏好随机选色。

- 仓储、设备、工单、调度、运行态势：`industrial-b`
- 大屏、监控中心、指挥中心：`command-center`
- SaaS、项目管理、运营后台：`saas-clean`
- 巡检、作业、现场上报、移动工具：`mobile-tool`
- 数据分析、报表、BI：`dashboard-analytics`
- CRM、客户门户、销售管理：`crm-portal`

如果没有明显行业信号，默认 `saas-clean`。

## 控制首轮范围

- 优先做能讲清主链路的 P0 页面。
- 不要在首轮加入拖拽画布、复杂审批引擎、多人协同、条件编排器。
- 页面数过多时，按 `references/rendering-prompt-template.md` 的分步渲染方式拆批。

## 进入迭代模式

在用户提出“加一个详情页”“把表格改成卡片”这类修改时：

1. 先定位变更范围：单组件、单页面或跨页面。
2. 只增量修改受影响的 ProductSpec 和页面方案。
3. 只重写受影响的渲染交接。
4. 保持未修改部分的页面结构和视觉基调稳定。

## 处理失败保护

输入极度混乱时：
- 收敛成最小可行方向。
- 默认输出 1 个总览页 + 1 个列表页 + 1 个详情层。
- 把高不确定项放进“待确认项”，不要阻塞产出。

长会议纪要只抽取影响页面设计的内容，不逐句复述。
