# bid-preparation 目录说明

本目录是可安装的通用 Agent Skill 源目录（遵循 SKILL.md + references/ + templates/ + scripts/ 结构），用于从招标文件和本地资质材料生成投标响应文件。任何支持 Agent Skills 规范的工具（Claude Code、Codex、OpenClaw、Grok 等）都可安装使用：把本目录整体复制到对应工具的 skills 目录即可。

## 目录职责

| 路径 | 职责 | 产出 |
|---|---|---|
| `SKILL.md` | 路由主文件：开工必问、**大纲闸+逐章确认**、正文内容化响应、格式禁令、样本对照、阶段路由 | AI 执行规则（细则按需加载） |
| `scripts/` | 确定性本地辅助脚本 | 初始化/提取/索引/成稿/格式校验/**P0门禁**/全量门禁/写作闸状态 |
| `references/` | 按阶段加载的参考卡片（含 stage-0..7） | 阶段细则、写作模式（含正文不写采购文件来源编号、PM/实施方案）、成品格式、清单 |
| `templates/` | 通用输出模板 | 分析报告、**商务/技术写作大纲**、导航表、偏离表、服务承诺 |
| `requirements.txt` | Python 依赖清单 | `pip install -r requirements.txt` 一步装齐 pypdf + python-docx |
| `agents/openai.yaml` | Codex UI 元数据（仅 Codex 使用，其他 Agent 忽略） | Skill 展示名称和默认提示 |

## 依赖

基础文本处理脚本使用 Python 标准库。PDF 提取依赖本机已安装的 `pypdf` 或 `PyPDF2`；旧版 `.doc` 自动提取依赖 `soffice`。DOCX 成稿脚本依赖 `python-docx`。依赖缺失时，脚本会写入提取报告或直接失败，不会静默生成不可靠内容。
