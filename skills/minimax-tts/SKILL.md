---
name: minimax-tts
description: VideoCut 工作流的 MiniMax 配音技能：用默认的「温润男声」音色把配音稿合成为音频，并返回词级字幕时间戳；也可查询、试听音色和验证 API Key。当任务提到配音、TTS、生成口播音频、MiniMax、换音色、试听音色、配音字幕时间戳，或视频生产流程进入 speech 阶段时使用。
---

# MiniMax 配音（minimax-tts）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

独立技能：只按参数读写文件，不修改 `project.json`。上层流程负责把产物登记进项目清单。

## 何时使用

- 生产流程的 speech 阶段：把 `voiceover.txt` 或 `speech.json` 的自然语段合成为音频。
- 需要字幕时间戳：默认请求词级时间戳（`subtitles: word`），随音频保存。
- 换音色前先 `voices` 查询、`audition` 试听，确认后改 `config.json`。

## 费用规则（先读）

| 子命令 | 是否计费 |
|---|---|
| `check`、`voices` | 不计费（音色查询接口） |
| `say`、`batch`、`audition` | 按合成字数计费 |

- 执行计费命令前，确认当前任务已有预算授权（见仓库 `AGENTS.md` 第 3、13 节）；没有授权时只运行免费命令。
- 相同文本、音色和参数命中缓存时不会重复调用接口；`--force` 会重新计费，非必要不用。
- 单次合成字数超过 `config.json` 的 `maxCharsPerRun`（默认 3000）会在调用前停止。
- 结果元数据保存接口返回的 `extra_info.usage_characters`，即计费字符数（2026-09-29 首次真实调用核实：汉字计 2，字母、数字、标点、空格各计 1）。官方价格 speech-2.8-hd ¥3.50/万字符，写在 `config.json` 的 `pricePer10kBillingChars`，价格变动时更新。`batch` 在调用前打印预计计费字符与金额，结束后写入实际计费字符与估算金额。

## 调用方式

在工作区根目录执行（Python 3.10+，依赖 `requests`）：

```bash
# 验证密钥、接口地址与已配置音色（免费）
python <本技能目录>/scripts/cli.py check

# 查询音色（免费），可按关键词筛选
python <本技能目录>/scripts/cli.py voices --match 男

# 合成一段文本（计费）
python <本技能目录>/scripts/cli.py say --text "每次投标都要熬夜排版？" --out out/minimax/hook.mp3
python <本技能目录>/scripts/cli.py say --text-file projects/<id>/variants/douyin/voiceover.txt --out projects/<id>/variants/douyin/audio/voice-raw.mp3

# 按分段批量合成（计费；未改动的段命中缓存）
python <本技能目录>/scripts/cli.py batch --segments segments.json --out-dir projects/<id>/variants/douyin/audio/segments

# 试听多个音色（计费，默认最多 4 个）
python <本技能目录>/scripts/cli.py audition --match 播音
```

`segments.json` 格式：

```json
{ "segments": [ { "id": "seg-01", "text": "每次投标都要熬夜排版？" }, { "id": "seg-02", "text": "……", "role": "narrator" } ] }
```

`id` 只能包含字母、数字、下划线和连字符。

## 产物

每段音频 `<name>.mp3` 旁边生成：

- `<name>.meta.json`：请求摘要 `request_hash`、模型、音色参数、文本、`duration_ms`（接口精确时长）、`usage_characters`、`trace_id`、音频 SHA-256、字幕状态 `subtitle_status`（`saved` / `failed` / `missing` / `not_requested`）。
- `<name>.subtitles.json`：接口返回的原始字幕 JSON（毫秒）。字幕链接会过期，技能在合成后立即下载保存。

接口一返回就已计费，所以技能先写音频和元数据，再下载字幕。字幕下载失败时音频和计费记录保留，`subtitle_status` 为 `failed`；该段不算完整缓存，重跑会重新合成（再次计费）以取得时间戳。

`batch` 另写 `batch-result.json` 汇总全部段与本次计费字数。

原始字幕 JSON 由 `voice-captions` 技能转换为项目统一的 `captions.json`。实际结构（2026-09-29 核实）：按句数组，每句含 `text`、`pronounce_text`、`time_begin/time_end`（毫秒）与 `timestamped_words[]`（`word`、`word_begin/word_end` 为原文字符位置、`time_begin/time_end` 毫秒）。`pronounce_text` 可用来检查数字和年份的实际读法，例如「2025 年」会被读成「两千零二十五年」，需改写朗读文本。

## 配置

| 位置 | 内容 |
|---|---|
| 工作区根目录 `.env` | `MINIMAX_API_KEY=...`（已被 `.gitignore` 排除）；可选 `MINIMAX_API_HOST`，主地址不可用时改为 `https://api-bj.minimaxi.com` |
| 技能目录 `.env` | 可选，优先于工作区根目录，用于单独给本技能换密钥 |
| `config.json` | 模型、文本规范化、读音词典、音频格式、字幕粒度、字数上限、角色音色表 |

密钥查找顺序：环境变量 → 技能目录 `.env` → 工作区根目录 `.env`。不得在日志、Git、提示词或回复中输出密钥。

`config.json` 字段：

| 字段 | 说明 |
|---|---|
| `model` | 默认 `speech-2.8-hd`；`speech-2.8-turbo` 更便宜更快；字幕仅部分模型支持，技能会在调用前校验 |
| `textNormalization` | 数字、单位规范化朗读，口播含数字时保持开启 |
| `pronunciation` | 读音词典，如 `"码包/(ma3)(bao1)"`，读错的术语统一在这里纠正 |
| `subtitles` | `word` / `sentence` / `none` |
| `roles` | 角色表：`voice_id`（必填）、`speed` 0.5～2、`vol` (0,10]、`pitch` -12～12、`emotion`（可选，不填由模型判断） |

台词里可写 `<#0.5#>` 插入 0.5 秒停顿（仅 MiniMax 生效）。

## 常见错误

| 提示 | 处理 |
|---|---|
| 未找到 MINIMAX_API_KEY | 在工作区根目录 `.env` 写入密钥 |
| 1004 鉴权失败 | 密钥错误，或不是 platform.minimax.cn 的密钥 |
| 1008 余额不足（错误码待首次遇到时核实） | 充值后重试；不要自动重试 |
| 2013 参数不合法 | 检查 voice_id、emotion 与模型是否匹配 |
| 1002 / 1039 限流 | 技能已自动退避重试 2 次；仍失败则稍后再跑，已完成的段会命中缓存 |

## 测试

```bash
python -m unittest discover -s <本技能目录>/tests
```

测试全部使用模拟响应，不联网、不计费。

## 来源

由桌面「视频/remotion-project/scripts/minimax_tts.py」迁移（2026-09-23 实测可用），本版新增字幕时间戳、合成缓存与字数上限。接口依据：[MiniMax 同步语音合成文档](https://platform.minimax.cn/docs/api-reference/speech-t2a-http)（2026-09-29 核验）。
