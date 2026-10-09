---
name: visual-assets
description: 为 VideoCut 视频镜头生成场景插图、概念素材或透明 PNG，并登记来源、生成记录和项目素材，交给 Remotion 合成。适用于分镜已明确但缺少补充画面的情况；真实操作和实测结果继续使用原始录屏。
---

# 图片与视觉素材

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

在分镜之后、画面渲染之前执行。读取项目 `brief.json`、目标平台的 `shots.json`、`docs/DESIGN.md`，复用 `generated/jobs.json` 中已完成且校验值一致的素材。本技能由智能体调用当前会话的生图工具，没有独立生图 API 脚本。

## 选择素材

| 镜头任务 | 方式 |
|---|---|
| 证明产品功能、操作过程、输出质量 | 真实录屏或截图；缺失时补录 |
| 解释步骤、数量、层级和关系 | 现有 Remotion 场景；准确文字和图表由代码绘制 |
| 呈现工作场景、概念意象、无实测含义的道具 | 内置 `image_gen` 生成图片，使用 `Illustration` 场景入片 |
| 需要独立主体或可组合道具 | 内置生图工具生成真正透明的 PNG，保留 alpha |
| 必须依赖连续动作、静态图与现有动画无法表达 | 单独核验视频生成服务、费用和授权；当前没有已接通的视频生成适配器 |

每张图对应明确的 `shot_id`，在 `purpose` 中说明它新增的场景、对象或关系。生成素材不替代开头要求的真实成品展示，不把虚构界面、评价、客户现场或数据当证据。系列封面仍按 `docs/DESIGN.md` 使用纯排版。

## 生成与保存

1. 为镜头写 `generated/prompts/<job_id>.md`：主体与动作、视觉用途、构图与留白、比例、系列配色、参考图角色、是否透明、禁止内容。准确中文、产品名、数字留给 Remotion 排版。提示词不包含私密客户资料或凭据。
2. 读取会话可用的 `imagegen` 技能，默认调用内置 `image_gen`，无需 API 密钥；工具用量不等于免费。已有任务授权覆盖内置工具时直接执行；涉及新增外部 API 费用时执行项目预算检查。没有具体选题和镜头的工作流搭建任务，只完成接入，不为演示而启动生成。
3. 写入 `generated/jobs.json`，结构见 [任务记录](references/jobs.md)。提交前保存提示词和请求摘要；未知模型、任务 ID 或费用填 `null`，不填推测值。超时记为 `unknown`，先恢复或查询原任务，不能直接重复生成。
4. 同期素材保持共同画风和光线；先检查首张，再生成其他镜头所需图片。编辑本地图之前先用 `view_image` 查看，按当前工具支持的引用参数传入。透明请求设置 `transparent_background: true`。
5. 查看实际结果，检查主体、错误文字、比例和边缘；修改时优先做一次有明确目标的编辑。新版本另存，不覆盖已选中的素材。
6. 将工具返回的实际图片保存为 `generated/outputs/<job_id>-v001.png` 或 `.jpg`。内置工具返回本地文件时从实际返回路径复制，不依赖猜测的路径；仅返回内联图而没有可保存的输出时保留待入库状态。项目引用不得停留在会话缓存或临时链接。
7. 经授权和来源检查后，用 `video-project` 导入；以返回的 `asset_id` 和 `stored_path` 更新任务记录及分镜。原始输出和可能附带的生成标识一并保留。

以下命令在工作区根目录执行，将示例项目 ID 和实际输出路径替换为本期值。`--rights confirmed` 只用于已核验使用范围的素材，证明另存为项目文件：

```powershell
python <video-project 技能目录>/scripts/vp.py import <project-id> "<actual-output-path>" --kind image --ai-generated --source "Codex 内置 image_gen；job_illustration_001" --label "画面示意；生成来源见 generated/jobs.json" --rights confirmed --proof "generated/rights.md"
```

首次导入即带上 `--ai-generated`、来源和标识。`vp.py import` 按文件校验值去重，重复导入不会更新旧记录；返回后核对标记，不以重复导入冒充元数据已更新。

## 进入镜头

在既有分镜中保留原 `shot_id`、`segment_ids`、`claim_ids`，将这个补充镜头设为：

```json
{
  "mode": "generated_image",
  "scene_type": "Illustration",
  "asset_ids": ["asset_image_001"],
  "requires_demo_evidence": false,
  "label_text": "画面示意",
  "params": {
    "image": "assets/original/asset_image_001.png",
    "title": "资料整理与交付"
  }
}
```

这只是分镜字段片段，不能覆盖整份 `shots.json`。`Illustration` 支持 PNG/JPEG，完整适配图片、不裁掉主体，标题最多两行，始终显示「画面示意」。透明 PNG 直接叠在系列浅灰背景上。真实截图继续使用 `ScreenFocus`，生成图不进入其证据窗口。

语段和镜头时长不变时保留配音与字幕；更新分镜后重新生成时间轴，让场景参数进入渲染输入。先渲染关键帧，新场景先出几秒样片，再出全片。时间轴、渲染和阶段登记分别按 `video-timeline`、`remotion-render`、`video-project` 的技能执行。

## 完成条件

- 选中图片已保存本地、可解码，素材表有生成标记、来源与使用范围。
- 提示词、参考素材 ID、工具返回信息、SHA-256、实际费用或未知费用状态可追溯；有费用记录时使用 `vp.py cost add`，不手改账本。
- 静帧和样片已实际检查：文字可读、主体完整、透明边缘无异常、「画面示意」可见。
- 由 `vp.py stage` 登记本次产物及真实检查结果；只生成图片不代表视频已交付。发布包保留生成内容声明要求。

内置生图工具不可用时，继续复用已有合格素材或现有 Remotion 场景，记录缺项；仅在用户明确选择外部 CLI/API 且预算已授权时采用该路径，不自动切换供应商。

## 接入验证（2026-10-07）

技能格式校验、素材导入参数检查、渲染器 22 项测试与 TypeScript 检查通过。使用程序合成的透明竖图和不透明横图完成 4 秒、540×960、30fps 静音测试片，完整解码通过，已查看首帧、切换帧与末帧；测试素材不代表 AI 生图结果。真实生图调用、具体图片质量与正式项目视听验收仍待本期任务执行。
