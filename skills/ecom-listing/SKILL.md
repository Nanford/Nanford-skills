---
name: ecom-listing
description: 将商品图片、规格、旧 Listing 或口头资料整理为可追溯的商品事实，并完成平台、本地化文案和 7 张以上套图规划。用户要求分析商品、提炼卖点、生成 Amazon/eBay/Temu 文案、选择平台/国家/语言/比例、智能或自定义套图、爆款风格分析，或需要生成 listing.json、strategy.json、copy.json、image_jobs.json 时使用。用户已说明的选项直接采用，只对缺少且会实质影响结果的选项集中提问；完成后可继续调用 ecom-image。
---

# 电商内容与套图规划

把商品资料整理成四个可续跑产物：`listing.json`、`strategy.json`、`copy.json` 和 `image_jobs.json`。本 Skill 负责商品理解、选项收集、站点策略、文案和套图工单，不生成最终图片。

## 选项处理规则

先读取用户消息、已有文件和上下文，再决定是否提问。

1. 用户已经明确给出的值直接采用，不复问、不改写。
2. 能由明确值唯一推出的选项直接推导，并在结果摘要中说明。例如 `Amazon 美国站` 可推导 `amazon-US`；语言未另行指定时可推导 `en-US`。
3. 用户明确要求“自动”“智能匹配”“你来决定”时，代表授权选择合理默认值，不再逐项提问。
4. 缺少且会改变交付结果的选项时，必须调用运行环境的结构化选择控件。Codex 使用 `request_user_input`；其他 Agent 使用等价的选项选择或 elicitation 工具。
5. 禁止在普通对话、commentary 或 final 中列出编号问卷、斜杠选项或让用户手工复制填写选项。
6. 每次控件调用只放 1 至 3 个问题，每题提供 2 至 3 个互斥选项；推荐项排第一，并在标签中标明“推荐”。不要手工添加 `Other`，由客户端提供自由输入。
7. 使用不超过 12 个字符的短标题和稳定的 `snake_case` 问题 ID。选择是继续执行的必要输入时不要设置自动超时。
8. 缺项超过 3 个时分轮显示：先确定发布范围和站点，再确定视觉方案，最后确定图片提供方。上一轮答案能推导出的字段不得在下一轮重复出现。
9. 当前运行环境没有结构化选择控件时，不要退化为文字问卷；只说明“当前模式不支持选项控件，请切换到支持结构化输入的交互模式后重试”，并停止执行需要该选择的阶段。
10. 不要询问与当前请求无关的选项。例如用户只要求提炼卖点时，不询问图片 API。
11. 商品容量、尺寸、材质、功率、成分、认证、防水等级、兼容型号等不可可靠推断的公开事实，必须标为待确认。只有当它们会进入本次公开文案或图片时才向用户确认。

需要按任务检查的选项如下：

| 选项 | 常用值 | 何时必须询问 |
|---|---|---|
| 平台 | Amazon、eBay、Temu、其他 | 要生成站点内容但未说明且无法从文件判断 |
| 国家/站点 | US、DE、JP 等 | 平台存在多个站点且未说明 |
| 语言 | en-US、de-DE、ja-JP 等 | 无法由站点唯一推导，或用户要求跨语言 |
| 画幅 | 1:1、4:5、3:4、16:9、自定义像素 | 要规划图片但未说明，也未授权自动选择 |
| 卖点来源 | 手工、AI 帮写、沿用商品档案 | 现有资料与用户意图无法确定 |
| 套图结构 | 智能匹配、自定义槽位 | 要规划套图但未说明，也未授权自动选择 |
| 图片数量 | 7、8、9 或自定义 | 用户未给数量时，智能模式默认 7 张 |
| 爆款风格分析 | 开、关 | 用户未说明时默认关；开启后只提炼通用规律 |
| 生成文案 | 开、关 | 请求范围不清时询问；完整 Listing 任务默认开 |
| 图片提供方 | Codex ImageGen、Qwen Image 3.0 Pro、Nano Banana 2、Seedream | 将继续正式出图但未说明，也未授权自动选择 |

第一轮结构化选择示例：

```json
{
  "questions": [
    {
      "header": "产出范围",
      "id": "output_scope",
      "question": "本次希望完成到哪个阶段？",
      "options": [
        {"label": "完整套图（推荐）", "description": "生成 Listing、文案和 7 张以上套图工单。"},
        {"label": "完整 Listing", "description": "生成商品事实、标题、五点和长描述。"},
        {"label": "仅五点描述", "description": "只生成目标站点的五点描述。"}
      ]
    },
    {
      "header": "发布站点",
      "id": "target_site",
      "question": "商品准备发布到哪个站点？",
      "options": [
        {"label": "Amazon US（推荐）", "description": "使用美国英语和 Amazon 美国站规则。"},
        {"label": "Amazon DE", "description": "使用德国站规则和德语本地化。"},
        {"label": "eBay UK", "description": "使用英国站规则和英国英语。"}
      ]
    }
  ]
}
```

第二轮仅在需要套图且相关值缺失时显示 `aspect_ratio`、`image_set`、`bestseller_analysis`；第三轮先选择 `Codex ImageGen`、`外部 API` 或 `自动路由`，只有选择外部 API 后才显示 Qwen、Nano Banana 2、Seedream 三选一。

## 工作流

### 1. 检查现有进度

有工作目录时先运行：

```powershell
python "<本 Skill 目录>/scripts/pipeline.py" status --workdir "<工作目录>"
```

存在有效产物时从最早缺失或过期的产物继续，不重复已确认阶段。上游文件更新时间晚于下游时，下游视为过期。

### 2. 建立商品事实

1. 收集商品图、规格表、包装文字、旧 Listing、SKU、品牌和用户补充信息。
2. 只读取 `references/category-cues.md` 中匹配类目的段落，并按 `references/confidence-rules.md` 区分可观察、用户确认、文档声明和推断。
3. 形成 5 至 8 条候选卖点，每条包含证据；推断项设置 `needs_confirmation: true`。
4. 检查原图分辨率、模糊、水印、第三方 Logo、主体遮挡和抠图难度。
5. 按 `references/listing-schema.md` 写出 `listing.json`。

### 3. 固化站点与创意策略

1. 按选项处理规则得到平台、国家、语言、比例、套图模式、数量、两个内容开关和图片提供方。
2. 只读取目标平台的 `references/sites/<platform>.md` 与目标语言的 `references/locale/<locale>.md`。
3. 智能套图至少 7 张；自定义套图严格使用用户给定槽位。
4. 爆款分析只提炼构图、色彩、信息密度和场景等通用规律，不复制商标、角色、包装或独特版权元素。
5. 按 `references/artifact-schemas.md` 写出 `strategy.json`。

### 4. 生成站点文案

1. 读取 `references/copy-patterns.md`，直接用目标语言写作，不先写中间语言再机械翻译。
2. 排除所有 `needs_confirmation: true` 的事实，并在 `excluded_points` 中记录原因。
3. 生成标题、五点描述、长描述、搜索词和图上短文案；若 `generate_copy` 为关，则只保留用户提供的文字并跳过扩写。
4. 保持所有文字中的卖点名称、数值、单位和限定条件一致。
5. 按 `references/artifact-schemas.md` 写出 `copy.json`。

### 5. 生成套图工单

1. 读取 `references/image-types.md`。
2. 智能模式按类目、卖点优先级和站点规则编排；自定义模式严格按用户槽位编排。
3. 每个 `base_prompt` 必须要求无文字、无 Logo、无水印，并说明主体、环境、构图、镜头、光线、留白和商品一致性。
4. 把准确文案写入 `text_layers`，不要写入底图提示词。`box` 使用 `[left, top, right, bottom]` 的 0 至 1 归一化坐标。
5. 需要保持商品外观时写入本地 `reference_images`。
6. 按 `references/artifact-schemas.md` 写出 `image_jobs.json`。

## 交付与续跑

对话中只展示关键摘要、已采用选项、待确认事实和文件路径，不粘贴整份 JSON。完成后提示用户继续调用 `ecom-image`，并带上同一工作目录。Codex 中可用 `$ecom-image`，Claude Code 中可用 `/ecom-image`。

所有产物都写入用户的工作目录，不要写入 Skill 安装目录；`<本 Skill 目录>` 指当前 `SKILL.md` 所在目录。
