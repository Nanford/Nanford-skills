---
name: voice-captions
description: VideoCut 工作流的配音拼接与字幕技能：把 minimax-tts 生成的各段配音按片头、段间、片尾停顿拼成 48 kHz 母轨 voice.wav，用服务商返回的逐字时间戳按语义断句生成 captions.json 与 SRT，并回写 speech.json 每段的真实时长与全局起止时间。配音合成完成后、做时间轴和渲染之前使用；改了某段配音后重跑。
---

# 配音拼接与字幕（voice-captions）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

## 调用方式

在工作区根目录执行（Python 3.10+，仅标准库；需要 ffmpeg）：

```bash
python <本技能目录>/scripts/voice_captions.py assemble --variant-dir projects/<id>/variants/douyin
```

可选参数：`--lead-ms 200`（片头静音）、`--gap-ms 200`（段间停顿）、`--tail-ms 800`（片尾静音）、`--max-width 16`（单行字幕宽度，汉字计 1，英文数字约 0.55）。

## 输入

版本目录下：

- `speech.json`：`segments[]` 的顺序、`segment_id`、`spoken_text`（提交给配音服务的文本），可选 `display_replacements`：`[["二零二五年六月", "2025 年 6 月"]]`，用于把为读音改写的文字在字幕里换回屏幕写法。可选 `caption_breaks`：`["实际用的格式"]`，在这些文字之后强制断行；朗读文本里找不到时报错（改稿后须同步）。
- `audio/segments/<id>.mp3`、`<id>.meta.json`、`<id>.subtitles.json`：`minimax-tts` 的产物。技能会核对 meta 中的文本与当前 `spoken_text` 一致，不一致时拒绝拼接（说明该段需要重新合成）。

## 产物

- `audio/voice.wav`：48 kHz、16 位、单声道母轨。全局时间按采样点累加计算，段间停顿计入总长。
- `speech.json`：回写每段 `audio_path`、`sha256`、`duration_ms`、`global_start_ms`、`global_end_ms`、`timing_source: provider`、`timing_granularity: word`、`provider_request_id`，以及 `master_audio`。
- `captions/captions.json`：`entries[]` 为 `{id, segment_id, start_ms, end_ms, text, timing_source, verified}`，时间为全局毫秒。
- `captions/subtitles.srt`：与 captions.json 同源。

## 断句规则

- 句号、问号、感叹号、分号必断行；逗号、顿号处积累到约 6 个字宽才断，避免碎行。
- 超过最大宽度时硬切，但不切开英文单词、数字和需要替换的读法短语。没有分词，硬切可能留下「列出 / 来」这类断词，审片发现后在该段 `caption_breaks` 指定语义断点再重跑。
- 行尾去掉句读，保留问号和感叹号；行内逗号、顿号改为空格。
- 句号后的一两个字不会跨句并回上一行。
- 字幕时间只取自真实音频的时间戳；`verified` 默认为 false，人工抽听关键位置后再改为 true。

## 服务商

`scripts/vclib/providers.py` 目前解析 MiniMax 词级字幕（2026-09-29 首次真实调用时核实结构：按句数组，`timestamped_words[]` 含 `word_begin/word_end` 字符位置与 `time_begin/time_end` 毫秒）。接入豆包、Azure 或转写对齐工具时，在该文件新增解析函数，输出同样的 `WordTiming`。

## 测试

```bash
python -m unittest discover -s <本技能目录>/tests
```

测试音频由 ffmpeg 合成正弦音，字幕为手写样例，不联网、不计费。
