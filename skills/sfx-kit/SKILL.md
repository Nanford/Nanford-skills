---
name: sfx-kit
description: VideoCut 工作流的系列音效库技能：用本地代码合成一套短、轻、干净的界面音效（弹出、点击、计数、划入划出、落定、强调铃声、完成、错误、划掉、打字、蓄势），每个音效对应画面里的一类动作，生成 48 kHz 单声道 WAV 与带校验值的清单，并能排出试听文件。给动画、文字动效配音效，试听或调整系列音效，或混音前需要音效库时使用。免费、不联网。
---

# 系列音效库（sfx-kit）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

## 调用方式

在工作区根目录执行（Python 3.10+，仅标准库）：

```bash
# 生成音效库：<本技能目录>/library/<音效>.wav + manifest.json（目录被 Git 忽略，随用随建）
python <本技能目录>/scripts/sfx_kit.py build

# 校验音效库与当前配方一致（混音前跑；不一致时退出码为 1）
python <本技能目录>/scripts/sfx_kit.py verify

# 试听：逐个排开（preview-all.wav），或按一段文字动效镜头的示范动作排列（preview-demo.wav）；打印每个声音的起始时刻
python <本技能目录>/scripts/sfx_kit.py preview
python <本技能目录>/scripts/sfx_kit.py preview --demo

# 列出动作类型与对应音效
python <本技能目录>/scripts/sfx_kit.py list
```

全部为本地计算，不调用计费接口。

## 音效与动作类型

| 动作类型 `kind` | 音效 | 用在什么画面动作上 |
|---|---|---|
| `appear` | `pop` | 卡片、主要元素弹出 |
| `appear_small` | `pop_soft` | 图标、列表项、小元素出现 |
| `press` | `click` | 按下、选中、光标点击 |
| `count` | `tick` | 数字滚动的每一跳、进度推进 |
| `transition_in` / `transition_out` | `whoosh` / `whoosh_out` | 镜头或大元素划入 / 划出 |
| `swap` | `swipe` | 卡片切换、前后对比翻面 |
| `land` | `thud` | 大字或关键数字落定 |
| `highlight` | `ding` | 重点高亮、结论出现 |
| `success` | `success` | 完成、打勾、通过 |
| `wrong` | `error` | 错误说法、否定、警示 |
| `strike` | `strike` | 划掉错误说法 |
| `type` | `type_1`～`type_3` | 打字（三个变体轮换，连续打字不像复读） |
| `build` | `riser` | 揭晓前的蓄势 |

音效只挂在画面动作上（AGENTS.md 第 10 节）：先有动作，再按动作类型取声音；不为了热闹给静止画面加声音，也不给每一句字幕加声音。

## 规则

- **来源与权利**：全部声音由 `scripts/sfxlib/presets.py` 的配方从正弦和带固定种子的噪声计算得到，不含采样、不含外部音频、不是 AI 生成。`manifest.json` 的 `rights` 如实记录。入片的音效用 `video-project` 登记为自有合成，例如 `python <video-project 技能目录>/scripts/vp.py import <项目ID> <本技能目录>/library/pop.wav --kind sfx --rights confirmed --source "sfx-kit 本地合成，配方版本 1.0.0" --proof "sfx-kit manifest.json rights"`（不加 `--ai-generated`）。
- **可复现**：同一配方和种子每次生成完全相同的字节（测试覆盖）。改配方后递增 `sfxlib/library.py` 的 `GENERATOR_VERSION`，`verify` 会提示旧库需要重建；已经混好的音效轨随之失效。
- **电平**：每个音效按配方归一到各自的样本峰值（-5～-15 dBFS），只代表库内的相对轻重。人声、音效、配乐的混音电平在第一个音效项目试听后定下，写入 `av-export` 配置与 `docs/DESIGN.md`（`docs/EDITING_METHOD.md` 第 4.4 节）。
- **处理链**：配方 → 20 Hz 隔直高通 → 首尾淡入淡出（首尾为 0，叠进音效轨时不产生咔哒声）→ 峰值归一 → 16 位 PCM。
- **风格调整**：音色属于系列声音风格，由主理人试听后决定；调整配方前先用 `preview --demo` 给主理人听，选定后再把风格写入 `docs/DESIGN.md`。

## 产物

- `library/<音效>.wav`：48 kHz、单声道、16 位 PCM
- `library/manifest.json`：`generator`（名称与配方版本）、`sample_rate`、`rights`、`kinds`（动作类型 → 音效 ID）、`sounds`（ID、动作类型、说明、文件、时长、峰值与 RMS、种子、SHA-256）
- `library/preview-all.wav`、`library/preview-demo.wav`：试听文件

## 接入流水线（2026-10-09）

1. `remotion-render` 的 `render.mjs actions` 按文字动效时间表导出 `actions.json`（每个动作的帧与动作类型）。
2. `av-export` 的 `av_export.py sfx` 按本库 `kinds` 取声音（同类多个变体按出现次序轮换，如打字 `type_1～3`），按帧换算采样点排出 `audio/sfx.wav`，总线电平暂定 -8 dB。
3. `av_export.py mix` 发现 `audio/sfx.json` 时把音效轨与人声相加后一起限幅。

本技能的 `kinds` 是动作类型的唯一来源；remotion-render 的测试会核对两边一致。入片的音效由 `sfx.json` 记录来源与校验值，不必再逐个登记到 `assets.json`。

## 尚未接入

- 人声避让（音效出现时压低人声）：现在音效电平低、时长短，直接相加；第一条带音效的成片试听后再决定是否需要。
- CC0 音效包导入与付费 AI 音效（ElevenLabs Sound Effects 等）作为后续扩展，主理人选定后再接；付费接口需单独授权预算。

## 测试

```bash
python -m unittest discover -s <本技能目录>/tests
```

测试在临时目录生成音效库，检查可复现、格式、电平、首尾无咔哒、无直流偏移、滤波频率、清单校验与试听文件，不联网、不写真实音效库。
