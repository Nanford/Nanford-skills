---
name: processon-diagrams
description: 将文字描述转化为 ProcessOn 风格的 SVG 专业图表（当前支持分层架构图、甘特图、业务流程泳道图，架构已按多图种拆分，便于后续继续扩展）。当用户提到"画架构图"、"系统架构图"、"技术架构图"、"总体架构"、"分层架构"、"应用架构"、"数据架构"、"画甘特图"、"甘特图"、"项目排期图"、"开发计划图"、"进度计划图"、"工期横道图"、"泳道图"、"业务流程图"、"跨部门流程图"、"审批流程图"、"跨职能流程图"、"ProcessOn风格"、"可视化架构"，或提供一段系统组成描述/项目排期/业务流转步骤希望图形化展示时，必须触发此 Skill，输出 SVG 而不是文字或 Mermaid。
---
<!-- author: Nanford -->

# ProcessOn 风格 SVG 图表生成

将文字描述转化为 **ProcessOn 模板风格**的可渲染 SVG 图表：清晰配色、统一细描边、中文字体优先、几何拼接箭头（导入 PPT / Word / 公众号不丢箭头）。所有坐标由内置 Python 脚本自动计算，避免手算导致的重叠与溢出。

---

## 图种路由（先选图种，再读对应参考文档）

根据用户需求判断图种，只加载当前需要的规范文件，保持上下文精简：

| 图种 (`diagram`) | 适用场景 | 规范文档 | 示例 |
|------------------|---------|---------|------|
| `architecture`（默认） | 系统架构、技术架构、应用架构、数据平台架构、总体架构 | `references/architecture.md` | `examples/ecommerce.json` / `examples/ecommerce.svg` |
| `gantt` | 项目排期、开发计划、季度路线图、招投标工期横道图、里程碑计划 | `references/gantt.md` | `examples/dev-plan-gantt.json` / `examples/dev-plan-gantt.svg` |
| `swimlane` | 业务流程图、跨部门/跨角色泳道图、审批流转图、端到端 SOP 流程 | `references/swimlane.md` | `examples/business-swimlane.json` / `examples/business-swimlane.svg` |

共用规范与配色：
- 视觉规范、自检清单、禁止项：`references/style-guide.md`
- 配色主题定义（脚本唯一数据源）：`references/color-themes.md`

> 如果用户明确要求目前尚未实现的图种（如时序图、ER 图、思维导图），直接说明当前内置脚本支持上述图种，询问是否先按 `references/style-guide.md` 的 ProcessOn 视觉规范手写 SVG，或先扩展该图种渲染器。

---

## 标准工作流程

1. **判断图种并读取规范**：根据上表选择图种，阅读对应的 `references/<diagram>.md` 和 `references/style-guide.md`。
2. **分析需求与匹配主题**：提取用户描述中的所有结构要素（架构的层级/模块/节点、甘特图的时间跨度/阶段/任务/里程碑、或泳道图的角色/步骤/判断分支/交付文档）；存在关键歧义时先向用户澄清，能合理假设的直接假设并在交付时说明。按行业或图种默认匹配主题（见下文）。
3. **编写 JSON 模型**：按图种规范写出结构化 JSON（包含 `"diagram"` 字段），保存为 `<名称>.json` 到用户工作目录。
4. **运行统一脚本渲染**：
   ```bash
   python <skill目录>/scripts/render.py <名称>.json -o <名称>.svg --png <名称>.png
   ```
   可用 `python <skill目录>/scripts/render.py --list` 查看当前支持的图种和主题。
   > 脚本仅依赖 Python 3 标准库；PNG 预览需要本机装有 Edge 或 Chrome。若环境无法运行 Python，再按对应规范与 `references/style-guide.md` 手写 SVG。
5. **看图自检**：打开生成的 PNG，对照 `references/style-guide.md` 与图种规范中的自检清单逐项检查。发现溢出、拥挤或错位时，**修改 JSON 重新渲染**，不要手改 SVG 坐标。
6. **交付**：提供 SVG 与 PNG 文件链接、JSON 模型代码块，以及主题选择和假设说明。

---

## 配色主题速查

完整色值定义见 `references/color-themes.md`。用户指定色系时优先遵循用户，否则按行业与图种自动匹配（`swimlane` 未指定主题时默认使用 `processon-gray` 经典商务黑白灰风格，`architecture` 和 `gantt` 默认使用 `processon-teal`）：

| `themeName` | 风格 | 适用场景 |
|-------------|------|---------|
| `processon-teal` | ProcessOn 经典青绿系 | 架构图与甘特图默认 / 互联网 / 电商 / 研发排期 |
| `processon-gray` | 商务黑白灰 | 泳道业务流程图默认 / 政企 / 金融 / 合规 / 审计 |
| `processon-blue` | 科技蓝 | 软件 / SaaS / 云平台 / 数据中台 |
| `processon-green` | 清新绿 | 医疗 / 能源 / 环保 / 农业 |
| `processon-orange` | 活力橙 | 营销 / 零售 / 创意 / 品牌 |

---

## 交付格式

1. **成品文件**：`<名称>.svg`（主交付物）与 `<名称>.png`（渲染预览），附可点击路径链接
2. **JSON 模型**：放在代码块里，方便用户后续微调文字或结构后重新渲染
3. **简要说明**：所用图种与主题、做了哪些合理假设或归并
