---
name: doubao-review
description: VideoCut 工作流的平台风险语义审核技能：调用火山方舟的豆包大模型，审核配音稿、脚本文稿、封面文字和发布文案（标题、说明、话题、置顶评论）里会导致抖音或视频号「不适宜公开」、下架、限流的内容，逐条给出位置、原文、风险等级、理由和改写；未放行的高风险拦住流程。script-check lint / terms 之后、配音之前使用，发布包定稿后、上传前再审发布文案；提到豆包审核、火山方舟、平台违规、审核文案时使用。
---

# 豆包平台风险审核（doubao-review）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

豆包与抖音同属字节跳动，对抖音的内容尺度有参考价值，但它的判断**不是平台的正式审核**：审核通过不保证作品不被限流，判为高风险也可能是误判。本技能只查平台审核风险，不评价文案好坏、节奏和开头吸引力（那些归 `script-check` 与 `jev-check`）。

## 在流程中的位置

```text
文稿定稿 → script-check lint / terms → doubao-review review（script）→ jev-check review → 配音 → …
发布包定稿 → script-check terms → doubao-review review（publish，文稿部分命中缓存不再计费）→ 上传
```

- **高风险拦截**（用户 2026-09-30 选择）：有未放行的 `high` 条目时退出码 1，改稿后重审；`medium` 逐条判断，`low` 只提示。
- **误判放行**：主理人口头确认某条是误判后，用 `waive` 记下理由（写主理人原话），该条不再拦截；放行按「范围 + 类别 + 原文」匹配，重跑后仍然有效。
- **原文核对**：每条的 `quote` 都会在送审文本里核对，找不到的标 `quote_found: false`（可能是模型编造），人工看一眼。

## 审核范围

| 范围 | 送审内容 | 什么时候审 |
|---|---|---|
| `script` | `speech.json` 每段的字幕显示文本（朗读文本与之不同时一并送审）、`script.md` 全文（含屏幕文字与镜头说明）、`cover.props.json` 的 kicker / title / sub | 配音前 |
| `publish` | `publish.md` 的「标题」「说明」「话题」「来源（置顶评论）」章节；文件表格、AI 声明说明和「发布前核对（不对外）」不送审 | 上传前 |

默认 `--scope all`：两个范围分开请求、分开缓存，没有 `publish.md` 时只审 `script`。平台默认取版本目录名：抖音不允许引导到微信、公众号；视频号允许微信生态，引导去其他平台才算站外引流。

风险类别：境外或未备案服务、境内无法访问的应用、站外引流、虚假夸大与收益承诺、广告法极限用语、代写刷量等灰产、敏感领域、隐私、AI 内容未如实说明、易被判低质或搬运、其他。定义与提示词在 `scripts/review_rules.py`（`PROMPT_VERSION`）。

## 调用方式

在工作区根目录执行（Python 3.10+，依赖 `requests`）：

```bash
# 免费：密钥是否配置、模型、本月用量
python <本技能目录>/scripts/doubao_review.py check

# 计费极少（约 ¥0.00005）：发一次极小请求，验证密钥有效、模型已开通
python <本技能目录>/scripts/doubao_review.py check --ping

# 免费：只估算费用上界
python <本技能目录>/scripts/doubao_review.py review --variant-dir projects/<id>/variants/douyin --dry-run

# 计费：审核，结果写 <版本目录>/doubao-review.json；有未放行的高风险时退出码 1
python <本技能目录>/scripts/doubao_review.py review --variant-dir projects/<id>/variants/douyin

# 免费：主理人确认误判后放行一条，写入 <版本目录>/doubao-review.waivers.json
python <本技能目录>/scripts/doubao_review.py waive --variant-dir projects/<id>/variants/douyin --item script-03 --reason "主理人原话"
```

## 费用与预算

- 按输入与输出 token 计费。单价写在 `config.json` 的 `priceTiersCnyPerMillion`：Doubao-Seed-2.0-lite 按单次输入长度分档，≤32k 为输入 0.6 / 输出 3.6 元每百万 token。**来源是 2026-09-30 的搜索摘要**，官方价格页是动态页面未能抓取，分档边界待在方舟控制台核对后更新 `priceSource`。
- 实测（2026-09-30，ai-bid-format v003）：一版文稿约 5000 输入 + 400～550 输出 token，发布文案约 1400 + 300～380 token；一个平台版本两个范围合计约 ¥0.007。预算闸门按上界算：输入取请求正文 UTF-8 字节数 + 200，输出取 `maxOutputTokens`（4000），单次上界约 ¥0.02。
- 每月上限 ¥20（`monthlyBudgetCny`，用户 2026-09-30 授权）。每次请求前按「本月已用（含结果不明的占用）+ 这批请求上界 ≤ 上限」检查，超额就不发请求。
- 用量账本 `logs/doubao-review/usage.jsonl`（Git 忽略，一行一次请求）。读超时或连接中断时请求可能已计费，按上界记为 `unknown`，不记 0。删掉该文件会清零本月统计。
- 用在正式项目上时，由调用方登记到项目账本：`vp.py cost add <项目> --service volcengine-ark --unit tokens --quantity <输入+输出 token> --estimated <usage.cost_cny>`。

## 模型与接口

- 接口：`POST https://ark.cn-beijing.volces.com/api/v3/chat/completions`，`Authorization: Bearer $ARK_API_KEY`；环境变量 `ARK_API_BASE` 可覆盖地址。
- 模型：`config.json` 的 `model`（默认 `doubao-seed-2-0-lite-260428`，2026-09-30 首次真实调用确认可用，`json_schema` 严格结构与关闭深度思考均被接受）。**须先在方舟控制台「开通管理」开通该模型**，否则返回 403/404；换模型只改 `model` 与单价。
- 关闭深度思考（`thinking.type = disabled`）、`temperature = 0`、`response_format` 用 `json_schema` 严格结构。接口若不接受 `json_schema`，把 `responseFormat` 改为 `json_object`（提示词里已写明输出结构）。
- 401 / 403 / 404 / 400 属于配置问题，不重试；429 与 5xx 最多重试 2 次并退避。
- 缓存键是完整请求体（模型 ID、提示词、送审文本、输出结构、参数），任何一项变化都会重新请求；缓存在 `.cache/doubao-review/responses/`（Git 忽略）。同一模型 ID 背后的服务端更新不会让缓存失效，需要时用 `--no-cache` 重审（会再次计费）。

## 输入与产物

发送给火山引擎的只有上面「审核范围」里的文字，不发公众号原文、截图、音频和密钥（用户 2026-09-30 要求接入豆包审核，视为同意发送文稿文字）。

产物 `<版本目录>/doubao-review.json`：`prompt_version`、`variant`、`platform`、`model`、`checked_at`、`scopes`、输入文件 SHA-256（`inputs`）、每次请求的缓存与用量（`requests`）、合计用量（`usage`）、各范围总结（`summaries`）、条目（`items`）、计数（`counts`）与是否拦截（`blocked`）。字段见 `docs/DATA_CONTRACTS.md`。本技能不修改文稿、不写 `project.json`。

## 配置

| 位置 | 内容 |
|---|---|
| 工作区根目录 `.env` | `ARK_API_KEY=...`（已被 `.gitignore` 排除）；在方舟控制台「API Key 管理」生成 |
| 技能目录 `.env` | 可选，优先于工作区根目录 |
| `config.json` | 模型、接口地址、思考开关、输出格式、分档单价与来源、每月上限与授权依据 |

密钥查找顺序：环境变量 → 技能目录 `.env` → 工作区根目录 `.env`。`check` 只报告是否已配置，不输出密钥的任何字符。

## 测试

```bash
python -m unittest discover -s <本技能目录>/tests
```

测试伪造 HTTP 响应，不联网、不计费、不读真实 `.env`、不写真实用量账本。
