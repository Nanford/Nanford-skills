---
name: av-export
description: VideoCut 工作流的混音、封装、质检与交付技能：按画面动作标记排出音效轨（可选），把人声母轨（与音效轨）处理到目标响度（固定增益 + 过采样限幅，-16 LUFS、真峰值受控），与 remotion-render 的无声画面封装为 H.264 + AAC 成片，对最终 MP4 做自动技术检查并从成片抽帧，登记人工审阅结果，生成 delivery.json。画面渲染完成后、交付之前使用；改了配音、时间轴或画面后重跑对应命令。
---

# 混音、封装、质检与交付（av-export）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

## 调用方式

在工作区根目录执行（Python 3.10+，仅标准库；需要 ffmpeg / ffprobe）。`<版本目录>` 形如 `projects/<id>/variants/douyin`，`--picture`、`--out`、`--video` 相对版本目录：

```bash
# 0. 可选：按画面动作排音效轨（先用 remotion-render 的 render.mjs actions 导出 actions.json）；有音效轨时 mix 自动混入
python <本技能目录>/scripts/av_export.py sfx --variant-dir <版本目录> [--actions actions.json] [--level-db -8]

# 1. 混音：audio/voice.wav（+ audio/sfx.wav）→ audio/mix.wav + audio/mix.json
python <本技能目录>/scripts/av_export.py mix --variant-dir <版本目录> [--target-lufs -16]

# 2. 封装：无声画面 + mix.wav → 成片；无配乐时同时写出与成片相同的无配乐母版
python <本技能目录>/scripts/av_export.py mux --variant-dir <版本目录> --picture exports/picture-v001.mp4 --out exports/final-v001.mp4 --voice-only-out exports/voice-only-v001.mp4

# 3. 自动检查 + 从成片抽帧（结果并入 qa/report.json；阻断项未通过时退出码为 1）
python <本技能目录>/scripts/av_export.py check --variant-dir <版本目录> --video exports/final-v001.mp4

# 4. 登记人工 / 模型审阅（只接受人工项，且必须对应当前成片校验值）
python <本技能目录>/scripts/av_export.py record --variant-dir <版本目录> --check-id audio.full_listen --result passed --by "用户" [--detail "..."] [--evidence qa/...]

# 5. 交付清单：projects/<id>/delivery.json
python <本技能目录>/scripts/av_export.py deliver --project-dir projects/<id> [--version v001]
```

全部为本地免费操作，不调用计费接口。

## 规则

- **混音**：`voice.wav` 的校验值必须与 `timeline.json` 记录一致，否则拒绝（配音改过要先重跑 voice-captions 与 video-timeline）。处理链为 4 倍过采样 → 全片一个固定增益 → `alimiter` 前视限幅（天花板 -2 dBFS，关闭自动电平，补偿延迟）→ 48 kHz 单声道 16 位。不用 `loudnorm`：原始峰值偏高时它会退回动态模式逐段改增益，可能泵动。处理后复测，偏离目标超过 0.3 LU 时按差值修正一次；结果不在 -18～-14 LUFS 内不替换 `mix.wav`。采样点数必须与输入一致，保证声画不偏移。
- **音效**（可选）：`sfx` 读 `actions.json`（须对应当前 `timeline.json`）与 sfx-kit 音效库（默认同一技能目录下的 `sfx-kit/library`，缺库时提示先运行 `sfx_kit.py build`；每个音效按清单校验值核对），按「帧 × 48000 / fps」换算采样点叠到与母轨等长的 `audio/sfx.wav`，同类动作的多个变体按出现次序轮换。总线电平默认 -8 dB，**暂定值**，第一条带音效的成片试听后再定（`docs/DESIGN.md` 第 6 节）。`mix` 发现 `audio/sfx.json` 时核对它对应当前时间轴与母轨，再把音效轨与增益后的人声相加、一起限幅；没有音效轨时处理链与以前完全相同，输出逐字节不变。`mux` 发现混音之后音效轨有变化（新增、重做或删除）时拒绝封装。
- **配乐**：`brief.json` 的 `music.mode` 不是 `none` 时直接报错。配乐与人声避让（`sidechaincompress`）在第一条带授权配乐的项目接入时实现。
- **来源 AIGC 标识**：MiniMax 返回的每段 MP3 带有服务商签名的隐式标识（ID3 `TXXX:AIGC`，含 ProduceID）。拼接为母轨后该元数据不会保留，签名绑定原文件，也不能原样迁移到成片。`mix` 把每段的标识字段记入 `mix.json`，原始 MP3 随交付包保留；成片是否另写标识、画面是否画角标（`explicit_overlay`）由账号持有人决定，记在 `brief.json` 的 `aigc` 字段并带入 `delivery.json`，`delivery.json` 的显式标识说明按该字段如实生成；`check` 始终如实报告成片有没有隐式标识（提示项，不阻断）。
- **封装前检查**：画面必须是 H.264、`yuv420p` 有限范围（tv）、与时间轴相同的分辨率和帧数、无音轨；`.render.json` 记录的时间轴校验值与当前 `timeline.json` 一致；`mix.json` 对应当前母轨。任一不符即拒绝。视频流直接复制不重编码；音频 AAC 192 kbps、48 kHz、单声道（母轨本身是单声道，不虚构立体声）；`+faststart`。不加 `-shortest`，避免截掉最后一帧。
- **自动检查**（`scope: render`）：完整解码无错误、视频规格与恒定帧率、音频规格、faststart、解码帧数与时间轴相差 ≤2 帧、音轨时长与时间轴相差 ≤2 帧、最终 AAC 响度 -18～-14 LUFS 且真峰值 ≤ -1 dBTP；黑场（接近纯黑 ≥0.5 秒）与成片隐式 AIGC 标识为提示项。
- **人工项**（`scope: delivery / publish`）：完整试听、字幕关键位置抽听、完整观看、成片抽帧审阅、画面文字对照事实表、画面增量（`picture.value_add`：每个镜头在口播之外提供证据、动作、对比或关系，见 `docs/EDITING_METHOD.md` 第 4.1 节）、显式 AI 标识、权利（字体、声音、音乐与素材的使用范围）、可复用（重渲染一次并比对）、平台上传预览。`check` 只把它们登记为 `not_checked`；同一文件重跑 `check` 不会覆盖已登记的人工结果，文件一变则全部重置。
- **三个状态**：`render_complete` = 当前成片的全部阻断自动项通过；`delivery_ready` = 此外交付文件齐全且 delivery 范围人工项全部通过；`ready_to_publish` = 此外 `brief.publish.authorized` 为真且平台预览通过。

## 产物

- 可选 `audio/sfx.wav`、`audio/sfx.json`（动作标记与音效库校验值、电平、每个音效的位置）
- `audio/mix.wav`、`audio/mix.json`（输入校验值、是否混入音效轨、处理链与各次增益、处理前后响度、来源 AIGC 标识、ffmpeg 版本）
- `exports/final-<版本>.mp4`、可选 `exports/voice-only-<版本>.mp4`、`exports/final-<版本>.mp4.export.json`（输入校验值、编码参数、输出校验值）
- `qa/report.json`（数据合同第 8 节字段，另加 `scope`、`detail`）、`qa/frames/<平台>-<校验值前 8 位>/`、`qa/contact-sheet-<平台>-<校验值前 8 位>.png`
- `delivery.json`

## 测试

```bash
python -m unittest discover -s <本技能目录>/tests
```

测试媒体由 ffmpeg 现场合成（testsrc2 画面、正弦音、带 AIGC 标签的 MP3），在临时目录里跑通 mix → mux → check → record → deliver，不读写真实项目、不联网。
