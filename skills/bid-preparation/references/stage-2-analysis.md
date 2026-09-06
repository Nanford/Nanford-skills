# 阶段2细则：解标分析（含 P0 硬参数 + 格式克隆 + ★三角）

> 配套阅读：`bid-structure-analysis.md`、`mandatory-clause-guide.md`。  
> **前置**：阶段1 `extraction-report` 门禁已通过。  
> 行业提示：仅烟草体系参考 `tobacco-industry-notes.md`。

## 目标

吃透招标文件；输出结构化分析 + **P0 三张表**（硬参数、格式克隆、★三角清单）。**不解清楚标，绝不动笔。**

## 产出

| 文件 | 说明 |
|------|------|
| `analysis/project-profile.md` | **P3+P1** 采购体系+采购方式+项目类型+递交方式+扩展标志（路由） |
| `analysis/gov-policy-checklist.md` | **P3** `gov` 体系必填（价格扣除测算/强制节能/信用查询/资格三段式） |
| `analysis/consultation-strategy.md` | **P3** 磋商/谈判/询价类必填（两阶段报价/术语切换/可变动条款） |
| `analysis/bid-analysis.md` | 项目信息、参数、资质、时间节点、样本对照 |
| `analysis/scoring-matrix.md` | 评分标准原文 + 响应策略 |
| `analysis/scoring-strategy.md` | **P1** 机械得分行动表（延保/业绩份数/证书截图） |
| `analysis/mandatory-checklist.md` | ★/强制条款 + **偏离表位置 + 正文位置** |
| `analysis/hard-parameters.md` | **P0** 前附表硬参数（含分项限价、多现场） |
| `analysis/format-clone-checklist.md` | **P0** 官方响应格式目录克隆 |
| `analysis/e-bid-delivery-checklist.md` | **P1** 电子标时必填（内容稿 vs 平台递交） |
| `analysis/multi-site-plan.md` | **P1** 多现场/改造时必填 |

模板见 `templates/`；路由说明见 `references/project-type-routing.md`。

## P3 采购路由（**最先执行**，先于项目类型）

1. 读采购公告/须知首页 → 判**采购体系**：看采购人性质 + 引用法条
   - 行政机关/事业单位/团体 + 《政府采购法》 → `gov`
   - 烟草/物流/集团企业 + 《招标投标法》或企业制度 → `enterprise`
   - **存疑按 `gov`**：判错成 enterprise 会整体漏掉政采政策性得分
2. 读文件封面与须知标题 → 判**采购方式**：叫「招标文件」还是「磋商/谈判文件」
3. 两项写入 `project-profile.md` 一之二/一之三节，**请用户确认**后同步写回 `project-state.json`
4. `gov` → 建 `gov-policy-checklist.md`，逐项完成：
   - **资格三段式**：先答"是否专门面向中小企业"——是且我方为大中型企业则**立即停止编制**
   - **价格扣除测算**：企业划型 → 适用比例 → 扣除前后评审价对比（直接决定报价策略）
   - **强制采购节能产品**：涉及则须列明具体产品名称 + 证书 + cx.cnca.cn 截图，缺证即无效响应
   - **信用查询**：信用中国 + 中国政府采购网 + 中国执行信息公开网（联合体查全体成员）
   - **地方信用评价分**：若存在折分条款，须提前查分并留出提分时间
5. 磋商/谈判/询价类 → 建 `consultation-strategy.md`：
   - 首次报价**必须预留下调空间**（最后报价不得高于首次报价，除非提高承诺标准）
   - 准备"可加码承诺清单"作为不降价时的筹码
   - 逐条登记"可实质性变动内容"的让步空间与底线
   - 完成术语映射核对（详见 `procurement-mode-routing.md` 第三节）

细则：`references/procurement-mode-routing.md`、`references/gov-procurement-policy.md`。

## P1 类型路由（先于写作骨架，后于 P3）

1. 填写并请用户确认 `project-profile.md`  
2. 将 `project_type` / `delivery_mode` 写回 `project-state.json`（可手改 JSON 或重跑 prepare 参数）  
3. 按类型选择技术骨架（禁止 simplified 硬套 30 页服务方案；禁止硬件标只写空泛理念）  
4. `electronic`/`hybrid` → 建电子递交清单  
5. 多现场/改造 → `multi-site-plan.md`（模板 `templates/multi-site-implementation.md`）；
   施工/安装/工程类 → 安全环保专章计划（模板 `templates/safety-env-plan.md`）  
6. 评分可量化项 → `scoring-strategy.md`

## 必须提取的字段（写入 hard-parameters）

- 最高限价 + **分项限价**（设备/施工/技术服务等，无则写「无」）
- 保证金金额/形式/到账截止/基本户/平台子账号
- 投标有效期、交货/服务/质保/试运行
- 联合体/分包、正副本与电子版、装订密封
- 税率发票、递交方式与电子平台名
- 偏离规则（允许 / 不允许 / 仅★）
- **政采专属**：价格扣除比例、是否涉及强制/优先采购节能产品与环境标志产品、是否涉及进口产品、是否专门面向中小企业
- **磋商谈判类专属**：报价轮次、最后报价提交时限、最低有效家数、可实质性变动内容范围

## 格式克隆步骤（P0）

1. 定位官方「投标/响应文件格式」章（不一定叫第六章）
2. **原样列出每一个格式标题**到 `format-clone-checklist.md`
3. 商务/技术大纲只能基于此表增补评标友好件（如导航表），不得漏官方件
4. 状态列不得残留 **缺口**

## ★三角闭环（P0）

对每条废标风险/★条款：

1. 写入 `mandatory-checklist`  
2. 预留或填写 **偏离表位置**（商务偏离表/技术偏离表第几条）  
3. 预留或填写 **正文/方案位置**（章节名；禁止指针句代替）  
4. 若招标写「不允许偏离」→ 策略见清单模板，负偏离须停问用户

阶段4/5 写偏离表与正文时回填位置；阶段7 / `check_p0_gates.py` 检查空位。

## 响应样本对照

有 `extracted-text/response-samples/` 时，在 `bid-analysis.md` 写模块完整度与详略要点（不抄数字事实）。

## 硬性要求

- 评分标准**原文照录**
- ★含义不清 → 硬停止问用户
- hard-parameters / format-clone / mandatory 三表未完成 → **不得** `--complete 2`，不得进入写作

## 自检命令

```powershell
python -X utf8 <scripts>\check_p0_gates.py "bid-projects\<项目>"
```

（阶段2末可能因资料门禁/正文未写产生 warning，但 hard-parameters 与 format-clone 的 blocker 必须清零。）

## 完成标志

用户确认分析准确后：

```powershell
python -X utf8 <scripts>\project_status.py "bid-projects\<项目>" --complete 2
```
