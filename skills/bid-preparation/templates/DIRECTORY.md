# templates 目录说明

本目录存放投标项目输出文件的通用 Markdown 模板，用于在招标文件未提供官方格式时快速建立响应结构。

这些模板是 DOCX 成稿前的中间稿结构，最终交付必须通过 `scripts/build_response_docx.py` 合并为 `output/投标响应文件.docx`，并通过 `scripts/validate_docx_format.py` 校验。

## 使用边界

- 招标文件提供官方格式时，以官方格式为准。
- 承诺书、授权书、投标函等要求原文照抄的内容不得套用通用模板改写。
- 模板中的 `{{...}}` 为项目生成过程中的占位内容，进入最终投标文件前必须全部替换或删除。

## 关键模板

| 文件 | 用途 |
|---|---|
| `bid-analysis.md` | 解标分析 |
| `scoring-matrix.md` | 评分矩阵 |
| `mandatory-checklist.md` | 强制条款清单 |
| `material-match-status.md` | 材料匹配状态 |
| `business-response-outline.md` | 商务响应文件框架 |
| `technical-response-outline.md` | 技术响应文件框架 |
| `compliance-report.md` | 合规审查报告 |
| `投标函.md` | 通用投标函 |
| `商务响应偏离表.md` | 通用商务偏离表 |
| `技术响应偏离表.md` | 通用技术偏离表 |
| `资格审查导航表.md` | 成品前置导航表（资格要求→页码） |
| `符合性审查导航表.md` | 成品前置导航表（符合性审查→页码） |
| `评标导航表.md` | 成品前置导航表（评分标准原文→自查→页码） |
| `服务承诺书.md` | 技术方案结尾的量化服务承诺 |
