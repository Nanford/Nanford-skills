# scripts 目录说明

本目录存放 `bid-preparation` Skill 的确定性辅助脚本，用于减少每次投标项目中的重复手工操作。

## 关键脚本

| 文件 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `prepare_project.py` | 招标文件路径、材料路径、项目名称 | `bid-projects/<项目>/` 标准目录 | 初始化投标项目工作区 |
| `extract_text.py` | PDF、DOCX、DOC、TXT/MD 文件 | `analysis/extracted-text/` 与提取报告 | 提取可检索的招标文件文字 |
| `index_materials.py` | 公司资料库或材料目录 | `analysis/material-index.md/json` | 建立资质、证书、业绩、技术资料索引 |
| `build_response_docx.py` | 已完成的 Markdown 响应文件 | `output/投标响应文件.docx` | 合并生成最终 DOCX 响应文件 |
| `validate_docx_format.py` | 最终 DOCX 文件 | `.format-report.md/json` | 校验宋体、字号、颜色、行距和标题编号 |
| `validate_bid_package.py` | 投标项目目录 | `review/validation-report.md/json` | 检查强制条款、占位符、输出目录和最终 DOCX |

## 依赖边界

文本提取脚本默认只依赖 Python 标准库。PDF 提取会优先使用本机已安装的 `pypdf` 或 `PyPDF2`；旧版 `.doc` 文件需要本机存在 `soffice` 才能自动转换，否则脚本会在报告中写明限制。

DOCX 成稿脚本依赖 `python-docx`。当前 Codex bundled Python 和本机 Python 均已验证可导入该库；在新环境中运行前应先确认依赖可用。

涉及真实投标文件时，脚本只在本地路径内读写，不上传、不调用外部服务。
