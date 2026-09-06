# templates 目录说明

本目录存放投标项目输出文件的通用 Markdown 模板，用于在招标文件未提供官方格式时快速建立响应结构。

这些模板是 DOCX 成稿前的中间稿结构，最终交付必须通过 `scripts/build_response_docx.py` 合并为 `output/投标响应文件.docx`，并通过 `scripts/validate_docx_format.py` 校验。

## 使用边界

- 招标文件提供官方格式时，以官方格式为准。
- 承诺书、授权书、投标函、**中小企业声明函**等要求原文照抄的内容不得套用通用模板改写。
- 竞争性磋商/谈判/询价项目：自编文件的用词须切换为「响应文件 / 供应商 / 成交」，模板中的「投标」体系用词不可直接沿用（见 `references/procurement-mode-routing.md` 术语映射表）。
- 模板中的 `{{...}}` 为项目生成过程中的占位内容，进入最终投标文件前必须全部替换或删除。

## 关键模板

| 文件 | 用途 |
|---|---|
| `bid-analysis.md` | 解标分析 |
| `scoring-matrix.md` | 评分矩阵 |
| `mandatory-checklist.md` | 强制条款清单（含★三角：偏离表位置+正文位置） |
| `hard-parameters.md` | P0 前附表硬参数表（限价/分项限价/保证金/多现场） |
| `format-clone-checklist.md` | P0 官方响应格式克隆与大纲 diff |
| `project-profile.md` | P3+P1 采购体系+采购方式+项目类型+递交方式+扩展标志 |
| `政府采购政策核对表.md` | P3 政采必填（落盘 gov-policy-checklist.md）：资格三段式、价格扣除测算、强制节能、信用查询、地方信用分 |
| `中小企业声明函.md` | P3 政策性声明函底稿（货物/服务/工程/残疾人/监狱企业）+ 填写核对清单；官方有格式时以官方为准 |
| `磋商响应策略表.md` | P3 磋商/谈判类必填（落盘 consultation-strategy.md）：两阶段报价、可加码承诺、术语切换、可变动条款 |
| `定标文件与答辩预案.md` | P3 评定分离必填（落盘 award-separation-plan.md）：双分册结构、定标因素映射、答辩小组与陈述稿、交付终检 |
| `联合体协议与分工表.md` | P3 联合体投标（落盘 consortium-plan.md）：成员分工、资质就低、签章分工、价格扣除适用性 |
| `e-bid-delivery-checklist.md` | P1 电子标：内容稿 vs 平台递交 |
| `multi-site-implementation.md` | P1 多现场/多系统实施表（落盘 multi-site-plan.md） |
| `safety-env-plan.md` | P1 安全环保与文明施工专章骨架 |
| `scoring-strategy.md` | P1 评分机械得分策略（延保/业绩/证书） |
| `requirement-index.md` | P2 采购需求编号索引（覆盖率统计可选；编号进入偏离表/追溯矩阵，不进入方案正文） |
| `material-match-status.md` | 材料匹配状态 |
| `business-response-outline.md` | 商务响应文件框架（旧脚手架） |
| `technical-response-outline.md` | 技术响应文件框架（旧脚手架） |
| `商务写作大纲.md` | 阶段4大纲闸：件套清单→用户确认→逐件编制（落盘 analysis/business-writing-outline.md） |
| `技术方案大纲示例.md` | 阶段5大纲闸：需求→章节→评分→PM/实施；确认后逐章写（落盘 analysis/technical-writing-outline.md） |
| `compliance-report.md` | 合规审查报告 |
| `投标函.md` | 通用投标函 |
| `商务响应偏离表.md` | 通用商务偏离表 |
| `技术响应偏离表.md` | 通用技术偏离表 |
| `资格审查导航表.md` | 成品前置导航表（资格要求→页码） |
| `符合性审查导航表.md` | 成品前置导航表（符合性审查→页码） |
| `评标导航表.md` | 成品前置导航表（评分标准原文→自查→页码） |
| `服务承诺书.md` | 技术方案结尾的量化服务承诺 |
