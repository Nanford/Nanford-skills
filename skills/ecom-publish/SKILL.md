---
name: ecom-publish
description: 对 listing.json、strategy.json、copy.json、image_jobs.json 和 final_images 执行发布前质检，检查站点字符限制、禁用词、待确认事实泄漏、图文一致性、图片尺寸比例和套图完整性，并在无阻断问题时导出平台刊登 CSV。用户要求检查 Listing 合规、验收套图、修复阻断问题、生成质量报告、导出 Amazon/eBay/Temu 刊登文件或完成最后发布准备时使用。
---

# 电商发布质检与导出

先质检，后导出。确定性规则交给脚本，语义、视觉和商业表达由当前 Agent 复核。

## 选项处理

1. 优先从 `strategy.json` 读取站点、国家和语言；用户已指定的导出格式或模板直接采用。
2. 用户只要求质检时，仅生成报告，不询问导出选项。
3. 用户要求正式刊登文件但缺少会改变字段映射的信息时，调用结构化选择控件。Codex 使用 `request_user_input`；其他 Agent 使用等价选项工具。不得在普通消息中列出编号选项。
4. 每次显示 1 至 3 题，每题 2 至 3 个互斥选项；推荐项排第一，使用 `export_template`、`category_mapping`、`image_url_mode` 等稳定 ID，不设置自动超时。
5. 正式刊登需要图片 URL 时，优先使用用户提供的永久 CDN URL。只有本地图片且用户只是内部审阅时允许导出本地路径；正式发布前使用结构化控件选择“补充永久 URL”“仅导出内部审阅版”或“暂不导出”。
6. 当前环境没有结构化选择控件时停止正式导出，并提示切换到支持结构化输入的交互模式；不要退化为文本问卷。
7. 不重复询问 `listing.json`、`strategy.json` 或用户消息中已有的信息。

## 质检

从任意目录运行，并把参数指向同一工作目录：

```powershell
python "<本 Skill 目录>/scripts/validate.py" --listing "<工作目录>/listing.json" --copy "<工作目录>/copy.json" --jobs "<工作目录>/image_jobs.json" --images "<工作目录>/final_images" --site amazon-US --json --out "<工作目录>/quality-report.json"
```

检查以下内容：

1. 标题、五点描述、长描述和搜索词的站点限制。
2. 禁用词、绝对化承诺和不允许的全大写格式。
3. 待确认事实是否泄漏到公开文案、底图提示词或图上文字。
4. 图文中的数值、单位、兼容范围和卖点命名是否一致。
5. 成品数量是否达到策略要求，文件是否与工单一一对应。
6. 图片格式、文件大小、长边像素、宽高比和白底主图。
7. 主图、两张代表性信息图和所有失败项的视觉检查。

`block` 必须修复；`warn` 要么修复，要么在报告中说明接受理由。修复事实或文案后，从最早受影响的 Skill 续跑，不绕过阻断项导出。

## 导出

质检报告的 `blocking` 为 0 后运行：

```powershell
python "<本 Skill 目录>/scripts/export_csv.py" --copy "<工作目录>/copy.json" --site amazon-US --images "<工作目录>/final_images" --base-url https://cdn.example.com/SKU-001 --quality "<工作目录>/quality-report.json" --out "<工作目录>/listing_export.csv"
```

如果已有永久图片 URL JSON，可把 `--images` 指向该 JSON 并省略 `--base-url`。导出结果包括 `listing_export.csv` 和 `export_manifest.json`。

## 交付

报告站点、阻断数、警告数、图片数量、CSV 路径和仍需人工处理的发布项。只有在脚本无阻断且视觉抽检完成后，才能说明“可发布”；本地图片路径或临时 URL 不得描述为正式刊登就绪。

所有报告和导出文件都写入用户的工作目录，不要写入 Skill 安装目录；`<本 Skill 目录>` 指当前 `SKILL.md` 所在目录。
