# 工作流技能目录

本目录存放 VideoCut 视频生产流程的技能。每个技能是一个独立子目录，可以单独调用、单独测试、单独迭代或替换。Claude Code 自动发现这里的技能；Codex 按 `AGENTS.md` 的指引读取对应 `SKILL.md` 后执行其中的命令。

## 约定

- 每个技能目录包含：`SKILL.md`（何时用、怎么调用、费用、产物、配置）、`scripts/`（命令入口）、`tests/`（不联网、不计费的测试），按需包含 `config.json`。
- 技能之间只通过文件交换数据，字段遵守 `docs/DATA_CONTRACTS.md`；技能不直接修改 `project.json`，由调用方登记产物。
- 密钥统一放工作区根目录 `.env`（已被 Git 忽略），技能目录 `.env` 可覆盖；参考 `.env.example`。工作区根目录由 `videocut.workspace.json` 标记（或环境变量 `VIDEOCUT_WORKSPACE`），技能装在工作区外也据此定位。
- `SKILL.md` 里的命令用 `<本技能目录>`、`<技能名 技能目录>` 表示技能所在目录，在本仓库里即 `.claude/skills/<技能名>`；每个技能另有 `agents/openai.yaml` 供 Codex 显示名称与默认提示。
- 本目录是唯一来源；对外的技能库（Nanford-skills）由 `tools/export_skills.py` 单向导出，不在那边直接改。
- 会产生费用的命令在 `SKILL.md` 中单独标明，并提供免费的配置检查命令。
- 同一环节可以有多个可替换技能（如配音：MiniMax、豆包语音、Azure；字幕对齐：FunASR、faster-whisper、whisper.cpp），产物格式保持一致，调用方按配置选用。
- 新增或修改技能时，同步更新下表与 `AGENTS.md` 的技能清单。

## 技能清单

| 技能 | 阶段 | 语言 | 状态 | 说明 |
|---|---|---|---|---|
| [video-workflow](video-workflow/SKILL.md) | 总入口 | 文档 + Python | 可用（2 项测试通过；2026-10-09 新增） | 生产流程总入口：阶段顺序、配音前闸门、四个人工确认点、计费与发布边界、断点续跑；`init_workspace.py` 初始化新工作区 |
| [script-check](script-check/SKILL.md) | script / captions | Python | 可用（25 项测试通过） | 配音前文稿闸门：开头规则、画面文字长度、事实与数字可追溯；语义色写法与数量；平台敏感词（含截图 OCR）；配音后按字幕实测开头时长 |
| [doubao-review](doubao-review/SKILL.md) | script / delivery | Python | 可用（9 项测试通过；2026-09-30 首次真实审核 ai-bid-format 两版，单价待控制台核对） | 豆包大模型审核配音稿、脚本、封面文字与发布文案的平台违规风险；未放行的高风险拦截，误判可记录放行；每月上限 ¥20 |
| [jev-check](jev-check/SKILL.md) | script | Python | 可用（20 项测试通过；2026-09-29 试点与校准 59 条样例，jev-1.13.0） | Jev 决策模型做配音前语义提示：开头是否具体、受众是否一致、夸大收益、口播是否被所引事实支持；只提示不拦截，按月 1 美元上限计费 |
| [video-project](video-project/SKILL.md) | 全流程 | Python | 可用（25 项测试通过，含工作区定位） | 项目建档、素材入库、阶段状态与失效传播、费用账本；唯一写 project.json 的技能 |
| [minimax-tts](minimax-tts/SKILL.md) | speech | Python | 可用（2026-09-29 首次真实合成完成，计费规则已核实） | MiniMax 配音、词级字幕时间戳、音色查询与试听、费用估算 |
| [voice-captions](voice-captions/SKILL.md) | speech / captions | Python | 可用（13 项测试通过） | 配音分段拼接为 48 kHz 母轨、逐字时间戳断句生成字幕 JSON 与 SRT |
| [video-timeline](video-timeline/SKILL.md) | edit | Python | 可用（7 项测试通过） | 分镜 + 配音时间 + 字幕 → 统一 timeline.json（毫秒与帧一次算定） |
| [visual-assets](visual-assets/SKILL.md) | visuals | 智能体工具编排 | 流程已接入；真实生图待首个镜头验证 | 内置 image_gen 生成场景插图和透明 PNG，保存生成记录、通过 video-project 入库，再用 Illustration 场景合成；无独立外部生图/生视频 API 适配器 |
| [remotion-render](remotion-render/SKILL.md) | visuals / render | Node.js + TypeScript | 可用（2026-09-30 风格经主理人确认，见 docs/DESIGN.md；2026-10-07 新增 ScreenClip、按题材分组底图与 Illustration 插图场景；2026-10-09 新增 KineticText 文字动效与按文案选色的语义色预设，经主理人确认） | 按 timeline.json 渲染无声竖屏画面、审片静帧与封面；十种场景，含真实截图、录屏、单独标明示意的插图与纯文字动效；AI 角标按 brief.aigc.explicit_overlay 决定 |
| [sfx-kit](sfx-kit/SKILL.md) | mix | Python | 可用（14 项测试通过；2026-10-09 主理人确认为系列音效，对人声电平待首条成片试听） | 本地合成的系列界面音效库：每个音效对应一类画面动作（弹出、落定、划入、计数、强调、划掉、打字等），48 kHz WAV + 带校验值的清单 + 试听文件；不联网、不计费、无第三方权利；经 remotion-render actions 与 av-export sfx 接入混音 |
| [av-export](av-export/SKILL.md) | mix / render / qa / delivery | Python | 可用（14 项测试通过；2026-09-29 首个项目两版成片已跑通） | 按动作标记排音效轨、人声（加音效）响度处理、画面与音频封装、成片自动检查与抽帧、人工审阅登记、delivery.json；配乐避让待首个配乐项目接入 |
