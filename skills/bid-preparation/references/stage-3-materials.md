# 阶段3细则：资料收集与匹配

> 组合拳定义详见 `references/response-file-format.md` 第3节。

## 目标

对照招标要求逐项匹配公司资料库，标记缺失项。

> 范围裁剪：仅技术部分（technical-only）时只匹配技术类资料——体系认证、技术人员证书、案例业绩、方案素材；商务资质/财务/保证金类跳过。

## 步骤

```powershell
# Windows PowerShell
python -X utf8 <scripts>\index_materials.py `
  --materials "company-library" `
  --output-dir "bid-projects\<项目>\analysis"
```

```bash
# macOS / Linux
python3 -X utf8 <scripts>/index_materials.py \
  --materials "company-library" \
  --output-dir "bid-projects/<项目>/analysis"
```

然后逐项映射：每一条资格条件、评分项、★条款、证明要求 → 真实文件路径或缺口状态。

## 产出

- `analysis/material-index.md/.json` — 资料库索引
- `analysis/material-match-status.md` — 逐项匹配表（用 `templates/material-match-status.md`）

允许的状态：`已具备`、`需补材料`、`需用户确认`、`不适用`、`存在偏离`、`无法判断`。**证据不存在且用户未确认的项，不得标记为满足。**

## "组合拳"完整性核对

> 以下组合提炼自最严格的烟草体系中标样本，是**最稳妥的准备口径**；具体需要哪几件，以当前招标文件的证明材料要求为准（要求更少时按招标文件执行，不强加）。

- **业绩五件套**：合同关键页（名称页/内容页/金额页/签章页/时间页）+ 发票 + 发票查验平台截图 + 银行收款凭证 + 其他说明
- **人员三件套**：毕业证及身份证 + 资格证书 + 社保证明（连续6个月）
- **保证金三件套**：银行汇款凭证 + 基本存款账户信息 + 已开立银行结算账户清单
- **证书+查询截图配对**：ISO类证书配 cx.cnca.cn 截图、ITSS配 itss.cn 截图、纳税信用配税务局查询截图（只放证书不得分）
- **信用查询五平台截图**：国家企业信用信息公示系统、信用中国、中国执行信息公开网、中国裁判文书网、天眼查（招标文件可能约定由代理机构查询，投标人无需提供）

## 完成标志

**用户确认资料齐全或明确哪些缺口无法补充**后，更新状态：

```powershell
python -X utf8 <scripts>\project_status.py "bid-projects\<项目>" --complete 3
```
