---
name: script-check
description: VideoCut 工作流的文稿闸门技能：平台敏感词检查（口播、上屏文字、封面、发布文案与截图 OCR 文字，配音前与上传前各跑一次）；配音前检查开头（铺垫话、第一句时长、数字是否前置、优势型开头是否有已核实事实、开头镜头、3 个开头备选）、画面文字长度（与渲染层同一套宽度）、事实与数字可追溯、语段结构与时长预估；配音后按真实字幕时间量第一句结束与第一个数字出现的时刻。写完或改完文稿后、配音之前使用；配音完成后、渲染之前再跑 hook-gate。
---

# 文稿检查（script-check）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

## 调用方式

在工作区根目录执行（Python 3.10+，仅标准库，不联网、不计费）：

```bash
# 配音前：结果写入 <版本目录>/script-check.json；有 error 时退出码 1
python <本技能目录>/scripts/script_check.py lint --variant-dir projects/<id>/variants/channels

# 配音后：按 captions.json 的真实时间检查开头；未达标退出码 1
python <本技能目录>/scripts/script_check.py hook-gate --variant-dir projects/<id>/variants/channels

# 平台敏感词：配音前跑一次，发布包定稿后、上传前再跑一次；结果写 <版本目录>/terms-check.json，有 error 时退出码 1
python <本技能目录>/scripts/script_check.py terms --variant-dir projects/<id>/variants/douyin
```

## 平台敏感词（terms）

- **词表**：`config/platform-terms.json`，按类别给每个平台设 `error / warning / off`，并写明替换建议和来源。它是本项目按真实处理积累的工作清单，**不是平台官方名单**；零命中不代表平台一定放行。作品被限制后，按平台给出的原因补词并写来源，不凭想象一次铺满。
- **检查范围**：`speech.json` 的显示文本与朗读文本、`shots.json` 上屏参数与 `screen_text`/`label_text`、`cover.props.json`、`publish.md` 的「标题」「说明」「话题」「来源」章节（其余章节如「发布前核对（不对外）」不查），以及镜头引用的截图（ScreenFocus 的 `image`、BeforeAfter 的 `images[].image`）。录屏片段（ScreenClip 的 `video`）不做 OCR，须在打码工作副本生成后人工逐段看过；片段的源区间与倍速参数不算上屏文字。
- **匹配**：英文按整词、不分大小写：前面不能紧贴字母，后面不能接小写字母（`CLAUDE.md`、`GPT-4o`、驼峰话题 `#ClaudeCode` 命中，`ChatGPT` 不算 GPT，`Clauded` 不算 Claude）；含中文的词按子串。
- **截图 OCR**：调用 Windows 自带的 `Windows.Media.Ocr`（简体中文，不联网、不计费、无需安装依赖），结果按图片 SHA-256 缓存在 `<项目>/assets/ocr-cache.json`。整张截图都会识别，包括聚焦时被裁到画面外的部分，因为截图通常先整张出现再推近。
- **已知限制**：小字、斜体和花哨字体会认错（2026-09-30 实测把「WhatsApp」认成「What$pp」而漏报），OCR 零命中不等于截图干净；封面与首帧截图仍要人工看一眼。非 Windows 环境没有 OCR 时截图记为 `not_checked` 并报 error；确认已人工逐张查看后可加 `--no-ocr`，此时降为 warning。
- **平台**：默认取版本目录名（`douyin` / `channels`），可用 `--platform` 指定；`--terms` 可改用另一份词表。

## 开头规则

| 规则 | 级别 | 说明 |
|---|---|---|
| `hook.filler` | error | 第一段出现铺垫话：最怕的一种情况、今天聊聊、今天我们来、今天给大家、大家好、你知道吗、很多人不知道、我来给大家、话不多说 |
| `hook.benefit_unverified` | error | `brief.hook.type` 为 benefit，但第一段没有关联 `verified_source` / `verified_test` 事实 |
| `hook.first_sentence_long` | warning | 第一句预估超过 4 秒 |
| `hook.number_late` | warning | 文稿里有数字，但第一个数字预估在 5 秒之后 |
| `hook.visual` | warning | 开头镜头不是 ResultHook / EvidenceCard / ScreenFocus / ScreenClip（真实录屏片段），也不是带真实截图的 BeforeAfter 对比 |
| `hook.candidates` | warning | `speech.json` 的 `hook_candidates` 少于 3 个（痛点、数字优势、结果各一）；备选也按同样规则检查 |

配音前的时长是按字数预估（2026-09-29 用温润男声实测校准），只作提前警告；以 `hook-gate` 的实测为准：第一句须在 4000 ms 内说完，第一个数字须在 5000 ms 内出现。

## 其他检查

- **版面**：按 remotion-render 的字号适配算法预判缩放后的字号（居中大字的文字列宽 720px，强调标记 `{}` 与语义色名不计宽）。ResultHook 标题 < 80px、ActionEnd 标题 < 76px、EvidenceCard 大字 < 110px、ScreenFocus / ScreenClip / StepFlow / BeforeAfter 标题 < 52～56px、步骤条目 < 46px 给警告，更小报错；步骤条目 2～4 条；note 不超过两行；kicker 不超过 16 个字宽；封面标题不小于 100px。数值与 remotion-render 各场景的 `fitFontSize` 调用同步维护。
- **事实**：所引 claim 必须存在且不是 `unverified`；上屏文字和口播里的数字须能在所引 claim 的 `statement` 或其来源的标题、范围说明、日期里找到原文（紧跟字母的数字如 a16z 视为名称，不检查；取景坐标、图片路径、背景图等版面参数不上屏，不检查）。
- **语义色**：`{词|色名}`、`tone` 与对比行第三项的色名须是 品牌 / 痛点 / 解法 / 数据 / 提醒（或英文键名），否则报错 `tone.unknown`；同一镜头除品牌紫外超过 2 种语义色报错 `tone.too_many`（KineticText 按动作默认色计入：划掉 / 消散的旧说法痛点、换上的说法解法、数字数据）。色名表与默认色与 remotion-render 的 `src/markup.ts`、`src/kinetic.ts` 同步维护。文字动效的每拍文字也算上屏文字，参与出处核对与平台敏感词检查；最长一行缩到 72px 以下提醒、56px 以下报错。
- **结构与时长**：镜头引用的语段须按口播顺序、不重复不遗漏；预估全片时长不在 `brief.target_duration_seconds` 范围内给警告。

## 输入与产物

输入：版本目录的 `speech.json`（可含 `hook_candidates: [{type, text, claim_ids}]`）、`shots.json`、可选 `cover.props.json`、配音后的 `captions/captions.json`；项目根目录的 `brief.json`、`research/claims.json`、`research/sources.json`。

输入（terms）：另读版本目录的 `publish.md` 与镜头引用的截图文件。

产物：`script-check.json`（预估值、error / warning 数量与逐条结果）；`terms-check.json`（敏感词结果与每张截图的 OCR 状态）；`<项目>/assets/ocr-cache.json`（OCR 缓存）。技能不修改文稿。

## 测试

```bash
python -m unittest discover -s <本技能目录>/tests
```
