---
name: video-workflow
description: VideoCut AI 实战短视频生产流程的总入口：把主题、公众号文章或录屏做成抖音 / 视频号竖屏成片（1080×1920），按阶段调度 video-project、script-check、doubao-review、jev-check、minimax-tts、voice-captions、video-timeline、visual-assets、remotion-render、sfx-kit、av-export 十一个技能，写明每阶段的输入、命令、产物、配音前闸门、四个人工确认点、计费与发布边界和断点续跑；也负责初始化新的工作区。要做一条视频、继续一条做到一半的视频、在新电脑上搭这套流程，或问「下一步该做什么」时使用。
---

# 视频生产总流程（video-workflow）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

本技能不含生产代码，只负责调度：判断交给智能体，精确计算交给各技能的本地命令。任何能读文件、能在本机运行 Python 3.10+、Node.js 22.6+ 与 FFmpeg 的智能体都能驱动（Codex、Claude Code 等）；网页对话跑不了本机命令，只能写稿。

## 先读的规则

工作区根目录的 `AGENTS.md` 是总规则（Claude Code 经 `CLAUDE.md` 引用同一份），其余按需读：

| 文件 | 什么时候读 |
|---|---|
| `AGENTS.md` | 每次开工；优先级、默认配置、各阶段硬规则、计费与发布边界 |
| `WORKFLOW.md` | 第一次接手；生产链全貌、分工、包装参数 |
| `docs/DATA_CONTRACTS.md` | 读写任何项目文件之前（目录、字段、失效规则） |
| `docs/DESIGN.md` | 写分镜与画面参数之前（配色、语义色、文字动效、底图、音效） |
| `docs/EDITING_METHOD.md` | 分镜、画面增量、音效对点、制作复盘 |
| `docs/ACCEPTANCE.md` | 质检与交付 |
| `docs/AUDIENCE.md` | 定受众与开头 |

这些文件里写的 `.claude/skills/<技能名>` 指已安装的同名技能目录。安装包里它们在 `<本技能目录>/references/workspace/`，`init_workspace.py` 会复制到新工作区根目录。

## 新工作区（每台电脑或每个账号一次）

```bash
# 建工作区：标记文件、projects/、规则文档、模板、.env.example、.gitignore；已有文件一律不覆盖
python <本技能目录>/scripts/init_workspace.py <工作区目录> [--article-library "<公众号文章目录>"]
```

之后在工作区根目录：复制 `.env.example` 为 `.env` 填密钥；在 `<remotion-render 技能目录>` 执行 `npm ci` 与 `npm run setup:fonts`；执行 `python <sfx-kit 技能目录>/scripts/sfx_kit.py build`；跑三个免费的凭据检查（`minimax-tts` 的 `cli.py check`、`doubao-review` 与 `jev-check` 的 `check`）。只报告「已配置 / 未配置」，不输出密钥。

技能装在工作区外时，靠 `videocut.workspace.json`（或环境变量 `VIDEOCUT_WORKSPACE`）找到工作区；找不到就报错，不会把用量账本写到别处。

## 阶段顺序

每一步完成后用 `video-project` 登记（`vp.py stage <项目ID> <阶段> --variant <平台> --status passed --output <路径>:<说明>`），不手改 `project.json`。阶段名：公共阶段 `intake / research / asset_index`，每个平台 `script / speech / captions / visuals / edit / mix / render / qa / delivery`。

| # | 阶段 | 执行者与技能 | 产物 | 通过条件 |
|---|---|---|---|---|
| 1 | 建档 intake | `video-project`：`vp.py init`（文章改编加 `--input-type article --article`） | `brief.json`、`project.json` | ⓵ **选题定稿**（人工） |
| 2 | 核验 research | 智能体查官方来源与实测记录 | `research/claims.json`、`sources.json` | 关键事实不是 `unverified` |
| 3 | 素材 asset_index | `video-project`：`vp.py import`；需要补画面时 `visual-assets` | `assets/`、`assets.json` | 授权明确，隐私已遮挡 |
| 4 | 文案 script | 智能体写 `script.md`、`voiceover.txt`、`speech.json`、`shots.json`（画面参数按 `docs/DESIGN.md`，强调词用 `{词|痛点}` 选语义色） | 三层文本 + 分镜 | 闸门全过；⓶ **脚本定稿**（人工，含朗读一遍配音稿） |
| 5 | 配音 speech | `minimax-tts`：`cli.py batch`；首次换音色先 `audition` | `audio/segments/` | ⓷ **音色试听**（仅首次，人工） |
| 6 | 字幕 captions | `voice-captions`：`voice_captions.py assemble`；再跑 `script-check hook-gate` | `audio/voice.wav`、`captions/` | 第一句 ≤ 4 秒、第一个数字 ≤ 5 秒 |
| 7 | 时间轴 edit | `video-timeline`：`timeline.py build` | `timeline.json` | 帧边界一次算定 |
| 8 | 画面 visuals / render | `remotion-render`：`check` → `stills` 自查 → `video --scale 0.5` 粗剪 → `video` 正式；有文字动效时 `actions` | `exports/picture-*.mp4`、`actions.json` | 静帧无遮挡、画面有增量 |
| 9 | 混音 mix | `av-export`：有 `actions.json` 时先 `sfx`，再 `mix` → `mux` | `audio/sfx.wav`、`mix.wav`、`exports/final-*.mp4` | -18～-14 LUFS，真峰值 ≤ -1 dBTP |
| 10 | 质检 qa | `av-export`：`check`，人工项用 `record` 登记 | `qa/report.json`、抽帧总览 | 阻断项全过；⓸ **成片审看**（人工） |
| 11 | 交付 delivery | 智能体写 `publish.md`、封面（`render.mjs cover`）；再跑 `script-check terms` 与 `doubao-review review`；`av-export deliver` | `delivery.json` | 发布文案无 error、无未放行高风险 |

**配音前闸门（第 4 步，顺序固定）**：`script-check lint`（error 必须改）→ `script-check terms`（平台敏感词，含截图 OCR）→ `doubao-review review`（平台违规风险；主理人确认误判才 `waive`）→ `jev-check review`（语义提示，只提示不拦截）。改稿后从 `lint` 重跑。

## 停下来问人的地方

- 四个人工确认点 ⓵～⓸；其余阶段在授权范围内连续执行，不为走流程反复确认。
- 新增费用、超出已授权预算、换真人声音或克隆声音、素材授权不明、关键事实无法核实、改系列风格（`docs/DESIGN.md` 由主理人拍板）。
- 发布：默认只生成发布包，不上传、不发表、不代发评论；上传需要针对账号、版本和动作的明确授权。每条发布都要勾选平台的 AI 生成内容声明。

问的时候给选项和推荐，让对方能直接回答「选 A」。不写某个智能体专有的工具名，用「停下来问用户」表达。

## 计费边界

| 技能 | 计费 | 免费的检查 |
|---|---|---|
| `minimax-tts` | 按字符计费；缓存命中不重复计费 | `cli.py check` |
| `doubao-review` | 按 token；每月上限 ¥20，账本在工作区 `logs/` | `check`、`review --dry-run` |
| `jev-check` | 按 token；每月上限 $1 | `check`、`review --dry-run` |
| `visual-assets` | 视使用的生图工具而定 | — |
| 其余技能 | 本地计算，免费 | — |

每次计费调用后用 `vp.py cost add` 记账；结果不明的付费请求先对账，未知费用不记 0。

## 断点续跑

先 `vp.py status <项目ID>` 看各阶段状态，再检查已有产物的校验值：配音按文本与参数缓存，时间轴、渲染、音效轨、混音、成片都在记录里存了上游校验值，上游没变就复用，变了下游命令会拒绝并提示从哪一步重跑。只重做 `stale` 和 `failed` 的阶段，不从头重建。

## 测试

```bash
python -m unittest discover -s <本技能目录>/tests
```

测试在临时目录里初始化工作区，检查标记文件、规则文档与模板齐全，且再次初始化不覆盖已有文件；不联网、不计费。
