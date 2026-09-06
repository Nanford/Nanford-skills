# 阶段3细则：资料收集与匹配（含 P0 空库禁写）

> 组合拳定义见 `response-file-format.md`。  
> **P0**：资料库无真实证据文件时，**禁止**撰写含人员/业绩/证书/报价等事实的详细正文；只允许大纲 + 缺口清单。

## 目标

对照招标要求逐项匹配资料库；生成 **material-gate** 写作门禁。

> technical-only：只匹配技术类资料；门禁门槛证据数 ≥1。full：≥3 个真实文件才允许详细正文。

## 步骤

```powershell
python -X utf8 <scripts>\index_materials.py `
  --materials "company-library" `
  --output-dir "bid-projects\<项目>\analysis" `
  --scope full
```

```bash
python3 -X utf8 <scripts>/index_materials.py \
  --materials "company-library" \
  --output-dir "bid-projects/<项目>/analysis" \
  --scope full
```

`--scope` 与项目生成范围一致。然后填写 `material-match-status.md`。

**P1**：打开 `scoring-strategy.md`，按「满分条件」优先凑齐证书截图、业绩五件套、延保决策等可机械得分材料，状态回写策略表。

## 产出

- `material-index.md/.json`
- `material-match-status.md`
- **`material-gate.md/.json`（P0）** — `writing_detail_allowed` / `outline_only`

## P0 空库禁写规则

| material-gate | 允许 | 禁止 |
|---|---|---|
| `writing_detail_allowed=true` | 大纲确认后逐章写正文（仍须证据对应） | 编造无材料的事实 |
| `outline_only=true` | 写作大纲、缺口清单、硬参数/格式克隆表 | 详细技术方案/伪造业绩人员报价；output 大段正文会被门禁拦截 |

用户补齐资料后重新 `index_materials.py`，确认 `writing_detail_allowed=true` 并说「继续」再写正文。

允许的匹配状态：`已具备`、`需补材料`、`需用户确认`、`不适用`、`存在偏离`、`无法判断`。  
**证据不存在且用户未确认的项，不得标记为满足。**

## 组合拳核对

- 业绩五件套、人员三件套、保证金三件套、证书+官网截图、信用五平台（以招标文件为准）

## 完成标志

```powershell
python -X utf8 <scripts>\project_status.py "bid-projects\<项目>" --complete 3
```

完成前须存在 `material-gate.json`。若 `outline_only`，进入阶段4/5时只能出大纲，并在汇报中明确告知用户。
