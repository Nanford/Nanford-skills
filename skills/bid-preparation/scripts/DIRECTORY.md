# scripts 目录说明

本目录存放 `bid-preparation` Skill 的确定性辅助脚本，用于减少每次投标项目中的重复手工操作。

## 关键脚本

| 文件 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `prepare_project.py` | 招标文件、材料、可选 `--sample` 响应样本、`--scope`、`--procurement-system`、`--procurement-mode`、`--project-type`、`--delivery-mode` | 标准目录 + intake（含 P3 必做核对表提示）+ `project-state.json`（含 writing 写作闸与 P3 路由字段） | 阶段0初始化；登记样本到 source/response-samples |
| `project_status.py` | 项目目录；`--start/--complete/--reopen`；`--confirm-outline`；`--confirm-section --section` | 阶段状态 + 采购体系/方式 + P3 提醒 + 写作闸进度 + 下一步细则 | 断点续作；大纲/逐章确认记录 |
| `extract_text.py` | PDF、DOCX、DOC、TXT/MD 文件 | `analysis/extracted-text/`（样本可放子目录 response-samples） | 提取招标文件与响应样本文字 |
| `index_materials.py` | 公司资料库或材料目录 | `analysis/material-index.md/json` | 建立资质、证书、业绩、技术资料索引 |
| `build_response_docx.py` | Markdown 中间稿或 `--manifest` | `投标响应文件.docx` + `.build-report.json` | 成稿；清洗/告警 Markdown 泄漏 |
| `validate_docx_format.py` | 最终 DOCX | `.format-report.md/json` | 宋体/字号/行距/分页/目录域/**Markdown 泄漏拦截** |
| `office_bridge.py` | （被其他脚本导入） | Word/WPS COM 封装 | **兼容 Microsoft Word 与 WPS 文字**（页码、.doc 转换、导出 PDF） |
| `report_page_numbers.py` | 最终 DOCX；`--office auto|word|wps`；`--pdf`；`--probe` | `.page-map.md/json` | 标题真实页码对照表（Word/WPS 优先） |
| `check_p0_gates.py` | 投标项目目录 | `analysis/p0-gate-report.md/json` | **P0五项** + P1 路由警告 + **P3 采购路由**（政采政策核对表、磋商两阶段报价表、磋商类术语一致性扫描、**评定分离双分册**、工程类要件） |
| `check_content_quality.py` | 投标项目目录 | `analysis/content-quality-report.md/json` | **P2** 章内深度 + ★/需求覆盖率 |
| `build_share_package.py` | 仓库根目录 | `dist/bid-preparation-skill/` + zip | 构建脱敏分享包 |
| `validate_bid_package.py` | 投标项目目录 | `review/validation-report.md/json` | 全量门禁（P0/P1/P2）+人工核查清单 |

## 依赖边界

文本提取脚本默认只依赖 Python 标准库。PDF 提取会优先使用本机已安装的 `pypdf` 或 `PyPDF2`；旧版 `.doc` 优先用 **Word/WPS COM** 转换，其次 `soffice`。

DOCX 成稿脚本依赖 `python-docx`，产出标准 OOXML，**Microsoft Word 与 WPS Office 均可打开编辑**。

页码对照脚本 `report_page_numbers.py`（经 `office_bridge.py`）优先用本机 **Microsoft Word 或 WPS 文字**（COM，仅 Windows）读真实页码；可用 `--office wps` 强制 WPS。均不可用时降级：Office 导出 PDF → LibreOffice → 手动 `--pdf`（文本匹配精度略低，需抽查）。

涉及真实投标文件时，脚本只在本地路径内读写，不上传、不调用外部服务。
