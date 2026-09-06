# 阶段0细则：项目初始化

> `<scripts>` 指 Skill 安装目录下的 `scripts/`（见 SKILL.md）。本阶段前置条件：已完成开工必问（生成范围、商务资料、响应样本；**P3 采购体系/方式与 P1 项目类型/递交方式可先粗判**）。

## 目标

为每个投标项目创建独立的标准目录，登记输入清单、生成范围、响应样本、**P3 采购体系/方式**、**P1 类型/递交方式**（均可 unset），建立断点续作状态文件。

## 步骤

```powershell
# Windows PowerShell
python -X utf8 <scripts>\prepare_project.py `
  --root "C:\path\to\工作区根目录" `
  --project-name "项目名称" `
  --tender "C:\path\to\招标文件.pdf" `
  --materials "C:\path\to\company-library" `
  --sample "C:\path\to\响应样本.pdf" `
  --scope full `
  --procurement-system unset `
  --procurement-mode unset `
  --award-mode unset `
  --project-type unset `
  --delivery-mode unset
# procurement-system: gov|enterprise|unset
# procurement-mode: open_tender|invited_tender|competitive_consultation|competitive_negotiation|inquiry_single|unset
# award-mode:        standard|evaluation_separated|unset   ← 评定分离须组装两本投标文件
# project-type:      service_ops|it_build|hybrid_retrofit|hardware_supply|construction_epc|simplified|unset
# delivery-mode:     paper|electronic|hybrid|unset
```

```bash
# macOS / Linux
python3 -X utf8 <scripts>/prepare_project.py \
  --root "/path/to/工作区根目录" \
  --project-name "项目名称" \
  --tender "/path/to/招标文件.pdf" \
  --materials "/path/to/company-library" \
  --sample "/path/to/响应样本.pdf" \
  --scope full
```

- 多份招标文件（含澄清、补遗）时重复 `--tender`。
- 多份响应样本时重复 `--sample`（PDF/DOCX 均可）。无样本可省略 `--sample`，但须在 intake 中可见「未登记」。
- 样本会复制到 `source/response-samples/`（未加 `--no-copy-sources` 时）。

## 产出

- 项目目录：`source/`、`source/response-samples/`、`analysis/`、`analysis/extracted-text/`、`output/商务文件/`、`output/技术文件/`、`output/资格证明文件/`、`review/`
- `analysis/project-intake.md`：生成范围、**采购体系与方式及其必做核对表提示**、招标文件、**响应样本**、资料库路径、处理边界
- `project-state.json`：阶段进度 + `writing` 写作闸（大纲/逐章确认）；阶段0自动完成；仅技术范围时阶段4自动跳过

## 硬性要求

- **没有招标文件时停止**，向用户索取后再初始化
- 项目名称与标包号从招标文件封面/首页核实，不要凭对话猜测
- 用户声称有响应样本但未提供路径时，追问路径；有则必须 `--sample` 登记

## 完成标志

项目目录创建成功、intake 登记完整。进入阶段1前：

```powershell
python -X utf8 <scripts>\project_status.py "bid-projects\<项目>"
```
