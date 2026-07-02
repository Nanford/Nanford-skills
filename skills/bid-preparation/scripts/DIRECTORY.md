# scripts 目录说明

本目录存放 `bid-preparation` Skill 的确定性辅助脚本，用于减少每次投标项目中的重复手工操作。

## 关键脚本

| 文件 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `prepare_project.py` | 招标文件路径、材料路径、项目名称、`--scope` 生成范围（full=商务+技术完整包/technical-only=仅技术） | `bid-projects/<项目>/` 标准目录 + intake 登记生成范围 + `project-state.json` 状态文件 | 初始化投标项目工作区（生成范围来自开工第一问，决定后续阶段裁剪） |
| `project_status.py` | 项目目录（含 project-state.json），可选 `--start/--complete/--reopen N` | 阶段状态汇总 + 下一步指引（含细则文件路径） | 断点续作入口：新会话先跑本脚本即知"做到哪、下一步干什么、读哪份细则" |
| `extract_text.py` | PDF、DOCX、DOC、TXT/MD 文件 | `analysis/extracted-text/` 与提取报告 | 提取可检索的招标文件文字 |
| `index_materials.py` | 公司资料库或材料目录 | `analysis/material-index.md/json` | 建立资质、证书、业绩、技术资料索引（自动排除 `说明.md`/`DIRECTORY.md`/`README.md` 等目录占位说明） |
| `build_response_docx.py` | 已完成的 Markdown 响应文件（或 `--manifest` JSON 组装清单） | `output/投标响应文件.docx` + `.build-report.json` | 按中标样本版式合并生成最终 DOCX（分页/封面/目录域/页眉页脚/插图）；构建警告落盘供门禁汇总 |
| `validate_docx_format.py` | 最终 DOCX 文件 | `.format-report.md/json` | 校验宋体、字号、行距、A4、章节分页、页眉页脚、目录域、标题编号 |
| `report_page_numbers.py` | 最终 DOCX（可选 `--pdf`） | `.page-map.md/json` | 用 Word/WPS 更新目录域并读取每个标题的真实页码，生成导航表页码回填对照表 |
| `validate_bid_package.py` | 投标项目目录 | `review/validation-report.md/json` | 检查强制条款、占位符、输出目录和最终 DOCX；报告末尾汇总**人工核查清单**（留空待补材料/图片待补/页码回填/资料缺口/签章提醒） |

## 依赖边界

文本提取脚本默认只依赖 Python 标准库。PDF 提取会优先使用本机已安装的 `pypdf` 或 `PyPDF2`；旧版 `.doc` 文件需要本机存在 `soffice` 才能自动转换，否则脚本会在报告中写明限制。

DOCX 成稿脚本依赖 `python-docx`。当前 Codex bundled Python 和本机 Python 均已验证可导入该库；在新环境中运行前应先确认依赖可用。

页码对照脚本 `report_page_numbers.py` 优先用本机 Microsoft Word 或 WPS 文字（COM 自动化，仅 Windows）读取真实页码；两者都没有时降级为 LibreOffice/手动导出 PDF + 文本匹配（精度略低，需人工抽查）。

涉及真实投标文件时，脚本只在本地路径内读写，不上传、不调用外部服务。
