---
name: video-timeline
description: VideoCut 工作流的时间轴技能：根据 shots.json（镜头与所含语段）、speech.json（配音真实时间）和 captions.json 生成统一的 timeline.json，毫秒与帧边界一次算定，供 Remotion 渲染与混音共用。配音与字幕完成后、渲染之前使用；改了配音、字幕或分镜后重跑。
---

# 时间轴（video-timeline）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

## 调用方式

```bash
python <本技能目录>/scripts/timeline.py build --variant-dir projects/<id>/variants/douyin [--fps 30]
```

仅用 Python 标准库。

## 规则

- 配音母轨是时间基准：片长 = 母轨时长（含片头、段间、片尾静音），帧数向上取整，保证声音不被截断。
- 每个镜头从「上一段口播结束与本段开始的中点」切入，画面在停顿里切换；第一个镜头从 0 帧开始，最后一个延续到片尾。
- 所有边界从绝对毫秒换算为帧 `round(ms × fps / 1000)`，不逐段累加，长片不漂移。
- 镜头引用的语段必须按口播顺序、不重复、不遗漏地覆盖全部语段，否则报错。
- 字幕的 `audio_sha256` 必须与当前母轨一致；配音重做后没有重新生成字幕会被拒绝。

## 输入与产物

输入：版本目录下 `shots.json`、`speech.json`（需已由 voice-captions 回写全局时间）、`captions/captions.json`。

产物：`timeline.json`，含 `width`、`height`、`fps`、`duration_ms`、`duration_frames`、`voice_audio_sha256`，以及 `tracks.visual`（镜头：场景类型、参数、起止毫秒与帧）、`tracks.voice`、`tracks.caption`。字段见 `docs/DATA_CONTRACTS.md` 第 6 节。

## 测试

```bash
python -m unittest discover -s <本技能目录>/tests
```
