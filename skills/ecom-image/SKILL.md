---
name: ecom-image
description: 读取 image_jobs.json，通过 Codex App 的 ImageGen 或阿里云 Qwen Image 3.0 Pro、Google Nano Banana 2、火山引擎 Seedream 批量生成无文字电商底图，再用确定性文字图层合成最终套图。用户要求正式出图、切换图片 API、继续套图生成、批量渲染、替换文案但复用底图，或已有 image_jobs.json 时使用。已指定提供方时直接使用；未指定且会发起正式生成时才询问，完成后可继续调用 ecom-publish。
---

# 电商套图生成

读取 `image_jobs.json`，先生成无文字底图，再合成准确的多语言文字层。保留每张图的执行状态，失败时只重跑失败项。

## 选择图片提供方

1. `image_jobs.json`、`strategy.json` 或用户消息已指定提供方时直接使用，不复问。
2. 用户明确要求自动选择时：活动工具中存在 `image_gen__imagegen` 就使用 Codex ImageGen；否则使用 `ECOM_IMAGE_PROVIDER`，再否则使用 `assets/providers.json` 的 `default_external`。
3. 用户没有指定、没有授权自动选择且即将产生正式 API 调用时，调用结构化选择控件。Codex 使用 `request_user_input`；其他 Agent 使用等价选项工具。不得用普通消息列出图片模型让用户手工回复。
4. 第一题提供 `Codex ImageGen（推荐）`、`外部 API`、`自动路由`。用户选择外部 API 后，第二题提供 Qwen Image 3.0 Pro、Nano Banana 2、Seedream。
5. 每题使用稳定的 `snake_case` ID，例如 `provider_route` 和 `external_provider`；不要设置自动超时，也不要手工添加 `Other`。
6. 当前环境没有结构化选择控件时停止正式出图，并提示切换到支持结构化输入的交互模式；不要退化为文本问卷。
7. 用户只要求检查工单或 dry-run 时，不必询问提供方。
8. API Key 只从环境变量读取，不要求用户把 Key 发在对话中，也不写入仓库、JSON 或日志。

先读取 `references/providers.md`，确认所选提供方的模型名、环境变量、参考图限制和输出特性。

## 生成底图

### Codex App

活动工具中存在 `image_gen__imagegen` 时直接逐项调用：

1. 新生成且无参考图时只传 `prompt`。
2. 所有参考图都有本地路径时传 `referenced_image_paths`，不要同时传 `num_last_images_to_include`。
3. 将结果保存为 `base_images/<job.id>.<ext>`。
4. 写出 `base_images/render_manifest.json`；全部成功时 `status` 为 `complete`。
5. 不要求 OpenAI API Key，不转为外部 OpenAI HTTP 调用。

### 外部 API

先用 dry-run 检查工单，再正式调用：

```powershell
python "<本 Skill 目录>/scripts/gen_image.py" --jobs "<工作目录>/image_jobs.json" --out "<工作目录>/base_images" --provider qwen-image-3.0-pro --dry-run
python "<本 Skill 目录>/scripts/gen_image.py" --jobs "<工作目录>/image_jobs.json" --out "<工作目录>/base_images" --provider qwen-image-3.0-pro
python "<本 Skill 目录>/scripts/gen_image.py" --jobs "<工作目录>/image_jobs.json" --out "<工作目录>/base_images" --provider nano-banana-2
python "<本 Skill 目录>/scripts/gen_image.py" --jobs "<工作目录>/image_jobs.json" --out "<工作目录>/base_images" --provider volcengine-seedream
```

只重跑某个失败任务：

```powershell
python "<本 Skill 目录>/scripts/gen_image.py" --jobs "<工作目录>/image_jobs.json" --out "<工作目录>/base_images" --provider nano-banana-2 --only 03-scene
```

正式调用已经属于用户明确要求的正常执行步骤时，无需再次确认。遇到付费权限不足、配额、Key 缺失或供应商错误时保留已成功图片并报告可操作错误。

## 合成文字

底图全部就绪后运行：

```powershell
python "<本 Skill 目录>/scripts/compose_text.py" --jobs "<工作目录>/image_jobs.json" --base "<工作目录>/base_images" --out "<工作目录>/final_images"
```

1. 严格使用 `text_layers[].text`，不要现场改写。
2. 主图的 `text_layers` 为空时保持无文字。
3. 使用用户品牌字体；未提供时使用支持目标语言的本机字体。若字体授权或字形覆盖不明确，先报告再替换。
4. 文字不得越界、截断或互相覆盖；只修改文案时复用底图，仅重跑合成和下游质检。
5. 写出 `final_images/compose_manifest.json`；全部成功时 `status` 为 `complete`。

## 交付与续跑

展示生成数量、失败项、提供方、底图目录和成品目录。至少打开检查主图与两张信息图；发现明显主体漂移、文字溢出或错误字形时修复后再交付。完成后提示继续调用 `ecom-publish`：Codex 使用 `$ecom-publish`，Claude Code 使用 `/ecom-publish`。

所有底图和成品图都写入用户的工作目录，不要写入 Skill 安装目录；`<本 Skill 目录>` 指当前 `SKILL.md` 所在目录。
