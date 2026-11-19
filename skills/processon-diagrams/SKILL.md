---
name: processon-diagrams
description: 将文字描述转化为 ProcessOn 风格的 SVG 专业图表，内置 7 大常用图种：分层架构图(architecture)、甘特图(gantt)、业务流程泳道图(swimlane)、普通流程图(flowchart)、时序图(sequence)、组织结构图(orgchart)、思维导图(mindmap)。当用户提到"画架构图"、"系统架构图"、"技术架构图"、"甘特图"、"项目排期图"、"开发计划图"、"泳道图"、"业务流程图"、"跨部门流程图"、"流程图"、"决策流程图"、"时序图"、"接口调用图"、"交互时序"、"组织架构图"、"组织结构图"、"团队架构"、"WBS图"、"思维导图"、"脑图"、"知识图谱大纲"、"ProcessOn风格"，或提供一段系统组成/排期/流程/交互/组织/大纲描述希望图形化展示时，必须触发此 Skill，输出 SVG 而不是文字或 Mermaid。
---
<!-- author: Nanford -->

# ProcessOn 风格 SVG 专业图表生成

将文字描述转化为 **ProcessOn 模板风格**的可渲染 SVG 图表：清晰配色、统一细描边、中文字体优先、几何拼接箭头（导入 PPT / Word / 公众号不丢箭头）。所有坐标由内置零依赖 Python 脚本自动计算，避免手算导致的重叠与溢出。

---

## 图种路由（先选图种，再读对应参考文档）

根据用户需求选择最匹配的图种，**每次只需加载当前图种的参考文档**，保持上下文精简：

| 图种 (`diagram`) | 适用场景 | 规范文档 | 示例 |
|------------------|---------|---------|------|
| `architecture`（默认） | 系统架构、技术架构、应用架构、数据平台架构、总体架构 | `references/architecture.md` | `examples/ecommerce.json` / `.svg` |
| `gantt` | 项目排期、开发计划、季度路线图、招投标工期横道图、里程碑计划 | `references/gantt.md` | `examples/dev-plan-gantt.json` / `.svg` |
| `swimlane` | 跨部门/跨角色业务流程图、审批流转图、端到端 SOP 流程 | `references/swimlane.md` | `examples/business-swimlane.json` / `.svg` |
| `flowchart` | 单主体业务/逻辑/算法流程图、异常兜底与重试流转 | `references/flowchart.md` | `examples/order-flowchart.json` / `.svg` |
| `sequence` | 系统接口调用时序、支付回调、鉴权交互、微服务消息协作 | `references/sequence.md` | `examples/payment-sequence.json` / `.svg` |
| `orgchart` | 公司组织架构、项目交付团队分工、汇报关系、WBS 树形分解 | `references/orgchart.md` | `examples/company-orgchart.json` / `.svg` |
| `mindmap` | 知识体系梳理、产品脑图、方案大纲、复盘总结、结构化笔记 | `references/mindmap.md` | `examples/ai-product-mindmap.json` / `.svg` |

共用规范与配色：
- 视觉规范、自检清单、禁止项：`references/style-guide.md`
- 配色主题定义（脚本唯一数据源）：`references/color-themes.md`

---

## 标准工作流程

1. **判断图种并读取规范**：根据上表确定 `diagram` 类型，阅读对应的 `references/<diagram>.md` 和 `references/style-guide.md`。
2. **分析需求与匹配主题**：提取用户描述中的所有结构要素；存在关键歧义时先向用户澄清，能合理假设的直接假设并在交付时说明。按行业与图种默认匹配主题（见下文）。
3. **编写 JSON 模型**：按图种规范写出结构化 JSON（必须包含 `"diagram"` 字段），保存为 `<名称>.json` 到用户工作目录。
4. **运行统一脚本渲染**：
   ```bash
   python <skill目录>/scripts/render.py <名称>.json -o <名称>.svg --png <名称>.png
   ```
   可用 `python <skill目录>/scripts/render.py --list` 查看全部支持的图种和主题。
   > 脚本仅依赖 Python 3 标准库；PNG 预览需要本机装有 Edge 或 Chrome。若环境无法运行 Python，再按对应规范与 `references/style-guide.md` 手写 SVG。
5. **看图自检**：打开生成的 PNG，对照 `references/style-guide.md` 与图种规范中的自检清单逐项检查。发现溢出、拥挤或错位时，**修改 JSON 重新渲染**，不要手改 SVG 坐标。
6. **交付**：提供 SVG 与 PNG 文件链接、JSON 模型代码块，以及主题选择和假设说明。

---

## 配色主题速查

完整色值定义见 `references/color-themes.md`。用户指定色系时优先遵循用户，否则按行业与图种自动匹配（`swimlane` 默认 `processon-gray`，其余图种默认 `processon-teal`）：

| `themeName` | 风格 | 适用场景 |
|-------------|------|---------|
| `processon-teal` | ProcessOn 经典青绿系 | 默认 / 互联网 / 电商 / 研发排期 / 思维导图 |
| `processon-gray` | 商务黑白灰 | 泳道业务流程图默认 / 政企 / 金融 / 合规 / 审计 |
| `processon-blue` | 科技蓝 | 软件 / SaaS / 云平台 / 时序交互 / 企业组织架构 |
| `processon-green` | 清新绿 | 医疗 / 能源 / 环保 / 农业 |
| `processon-orange` | 活力橙 | 营销 / 零售 / 创意 / 品牌 |

---

## 交付格式

1. **成品文件**：`<名称>.svg`（主交付物）与 `<名称>.png`（渲染预览），附可点击路径链接
2. **JSON 模型**：放在代码块里，方便用户后续微调文字或结构后重新渲染
3. **简要说明**：所用图种与主题、做了哪些合理假设或归并
