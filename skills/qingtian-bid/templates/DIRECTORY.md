# templates 目录说明

本目录存放 `qingtian-bid` 的模板和数据文件。

| 文件 | 内容 | 使用者 |
|---|---|---|
| `visual-assets.json` | 图文清单骨架：schema_version 1、required_jobs 配图作业和 assets 成果，具体字段见 image-generation.md | `scripts/visual_assets.py`、`build_response_docx.py`；相对路径以清单目录为准 |
| `format-presets.json` | 格式预设库：F1～F5 五套预设（字段值、预设出处、个别字段的单独出处）；可选字体（系统自带、需另装、西文）；各维度的常用值 | `scripts/docx_font_profiles.py` |
| `rule-card.json` | 规则卡骨架（schema `qingtian-rule-card/3`）：27 个字段。其中 9 个（`qualification`、`checkboxes`、`key_dates`、`off_table`、`award`、`price_limit`、`bid_forms`、`bid_forms_diff`、`profile`）只含 `value`、`basis`、`checked`，出处逐行写 `ref`；其余每个含 `value`、`basis`、`source`、`checked`，轨道另有 `signals`、`handoff`，篇幅另有 `kind`，青天启用情况 `qingtian` 另有 `rule_scope`、`signals`、`user_decision`；工程类别 `project_category` 的 `value` 是 `{main, modules, scenarios}`，决定阶段 4、5 用哪几张类别知识卡 | `scripts/scaffold_rule_card.py` 复制为项目的 `analysis/rule-card.json`；`scripts/project_cards.py` 用它补齐渲染 |
| `fact-card.json` | 事实卡骨架（schema `qingtian-fact-card/2`，第 2L 步加 `cites`）：空的 `facts` 列表，每条事实的键见 `references/stage-3-facts-resources.md` 第三节 | `scripts/scaffold_facts.py` 复制为项目的 `analysis/fact-card.json` |
| `resource-card.json` | 资源卡骨架（schema `qingtian-resource-card/2`，第 2L 步加 `cites`）：`managers`、`machinery`、`labor`、`materials` 四节和 `gaps` 缺口，都是空列表 | `scripts/index_materials.py` 在项目里还没有资源卡时复制，并按缺类别预填缺口 |
| `identity-terms.json` | 身份词清单骨架（schema `qingtian-identity-terms/1`）：空的 `terms` 列表，每条 `{term, kind}`，kind 只能是公司全称、简称、商标、网址，至少一条公司全称；不写人名、证书编号、电话（门禁按格式另查） | 用户复制为项目的 `analysis/identity-terms.json` 后填写；`scripts/text_gates.py` 读它查 B5（决策 4a-3A） |
| `response-matrix.json` | 响应矩阵骨架（schema `qingtian-response-matrix/2`，第 2L 步加 `cites`）：封面目录页数 `front_pages`（默认 2）、余量 `reserve_pages`（默认 3）、空的 `items`、实施进度组织三方面的 `coverage`；每项的键见 `references/stage-4-matrix.md` 第三节 | `scripts/scaffold_matrix.py` 复制后逐项填入；评审内容未规定（T-合格）时手工复制，见该细则第五节 |
| `公司资料/` | 项目公司资料目录的模板：`DIRECTORY.md` 总说明（放什么、怎么放、取什么不取什么、放完以后、注意），`项目管理人员/`、`机械设备/`、`劳动力/`、`物资/` 各一份 `说明.md`。子目录名就是编目分类的关键词，改名要同步 `scripts/index_materials.py` 的 `CATEGORY_RULES` 和 `scripts/prepare_project.py` 的 `COMPANY_DIR`；说明文件不进编目 | `scripts/prepare_project.py` 建项目时复制成项目的 `公司资料/`（已有的文件不覆盖），并自动登记为公司资源 |
| `submission-checklist.json` | 提交前清单模板（schema `qingtian-submission-checklist/1`）：七个组和 S、E、I、P、C 五组固定条目，每条 `id`、`group`、`skippable`（可记不适用）、`tracks`（空即所有轨道）、`locks_docx`（勾选时锁成品）、`text`、`source`、`label`；`text` 里的 `{schedule}`、`{quality_standard}`、`{shortlist_rule}` 取规则卡原文；R 组、M 组不在模板里，由规则卡现算 | `scripts/submission_checklist.py` 每次按轨道筛选、并上规则卡的条目后出清单（决策 4c-1A），不复制进项目 |

## 维护

- 改预设数值直接改 `format-presets.json`。F1 必须写全所有字段；其余预设只写与 F1 不同的字段，没写的字段沿用 F1，格式确认卡上标"沿用 F1"。
- 某个字段的依据与整套预设不同（例如推断值、用户决策），写进该预设的 `field_sources`。
- 新字体须先加入 `fonts` 列表才能使用；系统不自带的放 `needs_install`，用到时确认卡给出 W8 提醒。
- 预设代号一经发布不重排；不再使用的预设在名称里注明，不删除代号。
- 规则卡加字段时，`rule-card.json` 和 `project_cards.py` 的 `RULE_FIELDS`（带 `ref` 的字段在 `rule_card_fields.py` 的 `REF_FIELDS`）同步改，并升 schema 版本；测试核对两边字段一致。
- 事实卡、资源卡加键时，`fact_resource_cards.py` 的 `FACT_KEYS` 或 `SECTIONS` 白名单同步改，并升 schema 版本。资源卡的白名单不得加入姓名、证书编号等身份信息键（决策 3b-1A）。
- 响应矩阵加键时，`response_matrix.py` 的 `TOP_KEYS` 或 `ITEM_KEYS` 白名单同步改，并升 schema 版本。改了已确认项目的矩阵行，引用它的中间稿确认随之失效（决策 3c-2A）。
- 提交前清单加条目时，编号接着本组往后排，发布后不重排、不复用；改了已有条目的文字、出处或规则，已勾的这一条随之失效，须重新核对（决策 4c-2A）。`skippable` 只给按需触发的条目，红线条目一律 false（决策 4c-3A）；改了哪条可记不适用、哪条锁成品，同步改 `tests/test_qingtian_submission.py` 的核对。加字段时同步改 `submission_checklist.py` 并升 schema 版本。
- 身份词清单加 kind 时，`text_gates.py` 的 `IDENTITY_KINDS` 同步改，并升 schema 版本。清单只收公司层面的词，不加人名类 kind（人名按"岗位＋姓名"另查，人员档案不读）。
