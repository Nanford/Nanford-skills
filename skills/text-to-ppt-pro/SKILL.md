---
name: text-to-ppt-pro
description: 专业 PPT 生成执行层，将结构化 PPT 大纲转化为可编辑的 .pptx 文件。支持 13 种标准页型渲染、4 套主题预设、备注区写入、自动质检。当用户说"帮我做PPT"、"把这段内容转成幻灯片"、"做培训课件"、"做汇报材料"、"做方案PPT"、"制作演示文稿"、"制作PPT"、"给我出PPT结构"、"帮我整理成PPT"，或提供文本/讲稿希望转化为演示文稿时，必须触发此 Skill。
---

# text-to-ppt-pro

PPT 生成执行层。接收结构化大纲，忠实渲染为 .pptx 文件，执行质检。

**职责边界：** 本 Skill 负责"渲染"，不负责"规划"。内容规划、页型选择、信息分层由上游（`article-to-ppt` 或用户手动提供）完成。本 Skill 的输入是已确定页型和内容的逐页规划，输出是可编辑的 .pptx 文件。

如果用户直接提供了原始文本而非结构化大纲，应先调用 `article-to-ppt` 完成规划，再由本 Skill 执行生成。如果用户只是口头描述了一个简单的 PPT 需求（如"做个 5 页的 AI 介绍 PPT"），可直接根据需求快速规划页型并生成，无需强制走上游流程。

---

## 执行流程

### 1. 解析输入

从上游大纲中提取：
- 全局信息：主题名称、受众、主题预设（`dark_tech` / `business_blue` / `mckinsey_clean` / `warm_exec`）、总页数
- 逐页信息：页型标识（`type`）、主标题、文案内容、排版子结构、讲师逐字稿

如果上游未指定主题预设，按以下规则自动选择：

| 受众/场景关键词 | 默认主题 |
|---------------|---------|
| AI、技术、系统、产品演示 | `dark_tech` |
| 汇报、提案、甲方、项目 | `business_blue` |
| 策略、复盘、简报、管理 | `mckinsey_clean` |
| 董事会、经营、年度、高管 | `warm_exec` |

### 2. 加载主题参数

读取 `assets/theme-presets.json` 获取完整色值配置。
读取 `references/design-system.md` 获取字体层级、间距规则、留白原则。

### 3. 逐页渲染

按页型标识调用对应渲染逻辑。每种页型的坐标参数和排版规格见 `references/layout-specs.md`。

13 种页型对应的渲染函数：

| 页型标识 | 渲染函数 | 核心排版特征 |
|---------|---------|-------------|
| `cover` | `render_cover` | 居中大标题 + 副标题 + 页脚 |
| `intro` | `render_intro` | 左右对照或上下递进 |
| `toc` | `render_toc` | 编号列表 + 章节标题 |
| `transition` | `render_transition` | 居中大字 + 章节编号 |
| `four-grid` | `render_four_grid` | 2×2 卡片网格 |
| `comparison` | `render_comparison` | 左右双栏对照 |
| `process` | `render_process` | 横向/纵向步骤链 |
| `method` | `render_method` | 编号步骤 + 说明 |
| `framework` | `render_framework` | 分层卡片（默认）/ 金字塔 |
| `case-study` | `render_case_study` | 三栏：问题-动作-结果 |
| `data` | `render_data` | 结论区 + 数据区上下分层 |
| `summary` | `render_summary` | 3 条结论/建议卡片 |
| `closing` | `render_closing` | 居中感谢语 + 可选联系信息 |

### 4. 写入备注区

上游提供的【讲师逐字稿】写入每页的 `notes` 字段，不混入正文。

### 5. 巡检与修复

生成后执行自动质检（详见 `references/checklist.md`）：

**程序可检项（自动校验）：**
- 文本框是否超出安全区（左右 0.55in，上下 0.4in）
- 正文字号是否低于 10.5pt、标题是否低于 16pt
- 单页文本总字数是否超过 120 字
- 相邻 shape 间距是否小于 12px

**视觉检查项（生成后自述报告）：**
- 是否存在连续 5 页以上使用相同版式
- 是否有页面内容过空（主体面积不足 40%）或过满
- 备注区是否已写入

修复优先级：精简正文 → 调整分组 → 增加留白 → 内容下沉到备注 → 重选页型 → 最后才缩字号。

### 6. 输出文件

保存为 `.pptx` 文件，命名格式：`{主题关键词}_{日期}.pptx`

---

## 参考文件

| 文件 | 内容 | 何时读取 |
|------|------|---------|
| `references/layout-specs.md` | 13 种页型的精确坐标参数和排版规格 | **生成前必读** |
| `references/design-system.md` | 字体规范、留白原则、版式节奏 | 需要具体字号/间距规则时 |
| `references/checklist.md` | 交付前巡检清单 | 生成完成后执行质检时 |
| `references/script-reference.md` | Python/Node.js 完整渲染函数参考 | 编写生成脚本时 |
| `assets/theme-presets.json` | 4 套主题完整色值配置 | 加载主题参数时 |
