---
name: jev-check
description: VideoCut 工作流的文稿语义检查技能：调用 TypeSafe 的 Jev 决策模型，在配音前判断开头第一句是否具体、开头对准的受众是否与 brief 一致、有没有夸大收益、每段口播是否被所引事实支持；只给提示、不拦流程。script-check lint 之后、配音之前使用；提到 Jev、TypeSafe、语义检查、口播和事实对不对得上时使用。
---

# 文稿语义检查（jev-check）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

Jev 是 TypeSafe 的决策模型：给一段文字和一个类型明确的问题，返回是/否概率（Noul）或多选一及置信度（Choice）。它**只读文字、不生成内容**：不能生成视频、图片、配音或字幕，不擅长算数，中文可用但官方称准确度不稳定。本技能只把它用在「需要判断、但关键词规则判断不了」的文稿检查上。

## 在流程中的位置

```text
文稿定稿 → script-check lint（离线确定性规则，error 必须改）→ jev-check review（语义提示）→ 配音 → script-check hook-gate
```

- 结果只是提示：`flagged` 由智能体或用户逐条判断是否修改，`not_checked` 表示模型拿不准、须人工看；退出码不因提示而非 0。
- 数字、时长、版面、claim 是否存在仍由 `script-check` 负责；Jev 不做数值计算。

## 检查项

| 检查 | 发送内容 | 判定 |
|---|---|---|
| `hook_concrete` | 第一段的第一句 | 是否一开口就给出具体痛点、好处、数字或结果；概率 ≥0.65 通过，≤0.35 提示，中间待人工 |
| `audience` | 前 3 段 | 从 `docs/AUDIENCE.md` 的 6 类人加「无单一人群」中选一个；`general` 或与 `brief.audience_segment` 不一致时提示；置信度 <0.8 待人工 |
| `exaggeration` | 每一段 | 是否夸大或打包票承诺收益；概率 ≥0.65 提示 |
| `support` | 每段口播 + 所引 `verified_source` / `verified_test` 事实原文 | 支持 / 矛盾 / 未涉及；矛盾或未涉及时提示，置信度 <0.8 待人工。只有观点或没有引用事实的段记为 `skipped` |

每项检查单独请求。问题措辞、提问语言与阈值来自 2026-09-29 试点，写在 `scripts/jev_rules.py` 里，改动后须重跑 `calibrate`。

## 试点与校准结果（jev-1.13.0，2026-09-29）

| 检查 | 单句样例 | 语段样例 | 结果 |
|---|---|---|---|
| hook_concrete | 16 | — | 15/16，唯一不符的是已知漏判（见下） |
| audience | 8 | — | 8/8 |
| exaggeration | 8 | 2 | 10/10 |
| support | 12 | 13 | 25/25；语段样例为 `20260929-fde-intro` 的 7 段定稿加 6 个改错版本（岗位数、年薪、出差比例、公司名、年份、年限各改一处） |

- 这些样例同时用来选定提问语言、措辞和阈值，是拟合结果，不是独立验证的准确率。样例全部在 `calibration/cases.json`。
- **已知漏判**：用户否掉的 v001 开头「做 AI 项目最怕的一种情况……」被判为「具体」（两次实测 0.84、0.85）。这句确实含具体痛点；本检查只能判断「具体不具体」，不能判断「抓不抓人」。这句由 `script-check` 的铺垫话规则拦下，开头好不好仍以用户判断为准。
- 同一句两次实测的概率有 0.01 级别的差异，所以默认使用缓存，保证同一份文稿重跑结果一致。
- `20260929-fde-intro` 视频号版定稿实测：21 项中 20 项通过、0 项提示。s02「中文叫前线部署工程师」与 claim 的关系判为待人工（置信度 0.73），原因是这个译名只写在 claim 的 limitations 里，不在 statement 里。
- 选用的提问语言：hook_concrete、exaggeration、support 用中文；audience 用英文描述（中文描述有一条置信度只有 0.43）。

## 调用方式

在工作区根目录执行（Python 3.10+，依赖 `requests`）：

```bash
# 免费：密钥是否配置、接口连通、本月用量
python <本技能目录>/scripts/jev_check.py check

# 免费：只估算请求数与费用上界
python <本技能目录>/scripts/jev_check.py review --variant-dir projects/<id>/variants/douyin --dry-run

# 计费：检查一版文稿，结果写 <版本目录>/jev-check.json
python <本技能目录>/scripts/jev_check.py review --variant-dir projects/<id>/variants/douyin

# 计费：用标注样例重测当前模型（默认不用缓存）；有意外不符时退出码 1
python <本技能目录>/scripts/jev_check.py calibrate
```

## 费用与预算

| 子命令 | 是否计费 |
|---|---|
| `check`、`review --dry-run` | 不计费 |
| `review`、`calibrate` | 按输入 token 计费，输出免费 |

- 单价：每百万输入 token 0.042 美元（`config.json` 的 `pricePerMillionInputTokensUsd`，来源 docs.typesafe.ai/models.md，2026-09-29 核验）。一版约 11 段的文稿约 9000 token，约 0.0004 美元；`calibrate` 约 0.0011 美元。
- 每月上限 1 美元（`monthlyBudgetUsd`，用户 2026-09-29 授权）。每次请求前按「本月已用（含结果不明的占用）+ 下次请求上界 ≤ 上限」检查，`review` 与 `calibrate` 开始前还会对整批请求先检查一次，超额就不发请求。
- 用量账本在工作区根目录 `logs/jev-check/usage.jsonl`（Git 忽略，一行一次请求）。读超时或连接中断时，请求可能已经计费，按上界记为 `unknown`，不记 0。删掉该文件会清零本月统计。
- token 上界 = 请求正文 UTF-8 字节数 + 每个问题 100 + 每次请求 200。试点 44 次请求的实际 token 数都小于正文字节数。
- 用在正式项目上时，由调用方登记到项目账本：`vp.py cost add <项目> --service typesafe-jev --unit input_tokens --quantity <usage.input_tokens> --note "约 <estimated_usd> 美元"`。账本币种是人民币，汇率未知，所以美元金额写在 note 里，不填 `--estimated`。试点与校准不属于任何项目，只记在用量账本里。

## 模型版本

接口只提供别名（`jev-latest`、`jev-preview`），不能锁定版本。`config.json` 的 `calibratedModel` 记录已校准的版本（`jev-1.13.0`）。`review` 返回的版本与它不同时，`jev-check.json` 的 `model_warning` 会提示先跑 `calibrate`；校准通过后再更新 `calibratedModel`。

缓存键包含模型别名、发送内容和问题定义，但不包含别名背后的版本。版本升级后，要让结果反映新模型，用 `review --no-cache` 重新请求（会再次计费）。

## 输入与产物

输入：版本目录的 `speech.json`（`segments[].display_text`、`claim_ids`）；项目根目录的 `brief.json`（`audience_segment`）、`research/claims.json`。发送给 TypeSafe 的只有这些文稿文字与 claim 原文，不发公众号原文、素材和密钥（用户 2026-09-29 同意发送文稿文字；官方称不用客户请求训练模型，零数据保留仅限企业版）。

产物：`<版本目录>/jev-check.json`，包含以下内容：

- 问题集版本 `question_set`
- 模型别名与返回的真实版本、`model_warning`
- 输入文件的 SHA-256
- 用量：新请求数、缓存命中数、输入 token、估算美元
- 汇总：`passed / flagged / not_checked / skipped` 各多少条
- 逐条结果：检查项、位置、结论、说明、原始概率或置信度

缓存在 `.cache/jev-check/responses/`（Git 忽略）；`calibrate` 使用单独的 `.cache/jev-check/calibration/`，重新校准不会覆盖项目文稿的缓存结果。本技能不修改文稿、不写 `project.json`。

## 配置

| 位置 | 内容 |
|---|---|
| 工作区根目录 `.env` | `TYPESAFE_API_KEY=...`（已被 `.gitignore` 排除）；密钥在 console.typesafe.ai/keys 生成 |
| 技能目录 `.env` | 可选，优先于工作区根目录 |
| 环境变量 `TYPESAFE_API_BASE` | 可选，覆盖接口地址 |
| `config.json` | 模型别名、已校准版本、单价、每月上限与授权依据、token 上界常数 |

密钥查找顺序：环境变量 → 技能目录 `.env` → 工作区根目录 `.env`。`check` 只报告是否已配置，不输出密钥的任何字符。

## 测试

```bash
python -m unittest discover -s <本技能目录>/tests
```

测试伪造 HTTP 响应，不联网、不计费、不读真实 `.env`、不写真实用量账本。
