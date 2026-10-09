---
name: video-project
description: VideoCut 工作流的项目管理技能：新建视频项目目录与清单、导入素材（只读副本、SHA-256、ffprobe 媒体信息、授权状态）、登记各阶段状态与产物并自动标记下游失效、记录费用账本、查看项目进度。开始一条新视频、导入录屏/截图/配乐/配音、完成任一生产步骤后登记结果、查看项目做到哪一步时使用。
---

# 项目管理（video-project）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

生产流程里唯一写 `project.json`、`assets/assets.json`、`costs/ledger.json` 的技能。其他技能只产出文件，完成后由本技能登记。

## 调用方式

在工作区根目录执行（Python 3.10+，仅标准库；导入素材需要 ffprobe）：

```bash
# 新建项目：projects/20260929-bid-skill/
python <本技能目录>/scripts/vp.py init bid-skill --topic "用 Skill 从招标文件生成标书初稿" --segment ai_office
python <本技能目录>/scripts/vp.py init bid-skill --input-type article --article "<素材库 article_library>\xxx.md"

# 导入素材（原件不动，项目内保存只读副本 assets/original/<asset_id>.<ext>）
python <本技能目录>/scripts/vp.py import 20260929-bid-skill "D:\录屏\标书演示.mp4" --kind footage --rights confirmed --source "自录"

# 只看媒体信息，不入库
python <本技能目录>/scripts/vp.py probe "D:\录屏\标书演示.mp4"

# 登记阶段结果（产物路径相对项目根目录，必须真实存在）
python <本技能目录>/scripts/vp.py stage 20260929-bid-skill script --variant douyin --status passed --output variants/douyin/script.md:脚本 --output variants/douyin/voiceover.txt:配音稿
python <本技能目录>/scripts/vp.py stage 20260929-bid-skill speech --variant douyin --status failed --error-code MINIMAX_1004 --recovery "检查密钥"

# 查看进度与费用
python <本技能目录>/scripts/vp.py status 20260929-bid-skill

# 记账（同一个请求 ID 只能记一次；金额未知就不填，不记 0）
python <本技能目录>/scripts/vp.py cost add 20260929-bid-skill --service minimax --unit chars --quantity 30 --request-id <trace_id>
python <本技能目录>/scripts/vp.py cost summary 20260929-bid-skill
```

## 规则

- `init` 不覆盖已存在的项目。`--article` 指定的来源文章必须存在，`brief.json` 记录其绝对路径与 SHA-256，原文不复制进项目。新项目默认只做抖音一版（`--platforms` 默认 `douyin`；主理人点名视频号或两个都要时传 `--platforms channels` 或 `douyin,channels`，2026-10-07 主理人定），`brief.json` 默认：预算未授权（`allow_new_paid_calls: false`）、不发布、配音为 MiniMax「温润男声」（`Chinese (Mandarin)_Gentleman`）、抖音 60～120 秒（做视频号时 60～180 秒）、画面不画 AI 角标（`aigc.explicit_overlay: none`，系列默认见 `docs/DESIGN.md`，发布时必须勾选平台 AI 声明）。受众、核心问题和开场由智能体按任务补全。
- `import` 对同一文件（SHA-256 相同）重复导入时返回原记录，不生成新 ID。未确认授权的素材会提示，不能入片。
- `stage --status passed` 时，如果登记的产物校验值与上次不同，会按数据合同第 7 节把下游已完成的阶段标为 `stale`，并在输出中列出需要重跑的阶段。重复登记相同产物不会误伤下游。
- 公共阶段失效范围：`intake`、`research` 变化影响各平台 `script` 及之后；`asset_index` 变化只影响 `visuals` 及之后。
- 测试时可设置环境变量 `VC_PROJECTS_ROOT` 指向临时目录，不影响真实项目。

## 产物

`projects/YYYYMMDD-slug/` 下的目录骨架、`brief.json`、`project.json`、`assets/assets.json`、`costs/ledger.json`。字段见 `docs/DATA_CONTRACTS.md`。`projects/` 整体被 Git 忽略。

## 测试

```bash
python -m unittest discover -s <本技能目录>/tests
```

测试素材由 ffmpeg 现场合成（testsrc 画面 + 正弦音），不使用任何私人文件、不联网。
