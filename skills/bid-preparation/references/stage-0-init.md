# 阶段0细则：项目初始化

> `<scripts>` 指 Skill 安装目录下的 `scripts/`（见 SKILL.md）。本阶段前置条件：已完成"开工第一问"，用户确认了生成范围（full / technical-only）。

## 目标

为每个投标项目创建独立的标准目录，登记输入清单和生成范围，建立断点续作状态文件。

## 步骤

```powershell
# Windows PowerShell
python -X utf8 <scripts>\prepare_project.py `
  --root "C:\path\to\工作区根目录" `
  --project-name "项目名称" `
  --tender "C:\path\to\招标文件.pdf" `
  --materials "C:\path\to\company-library" `
  --scope full   # 或 technical-only（按开工第一问的用户选择）
```

```bash
# macOS / Linux
python3 -X utf8 <scripts>/prepare_project.py \
  --root "/path/to/工作区根目录" \
  --project-name "项目名称" \
  --tender "/path/to/招标文件.pdf" \
  --materials "/path/to/company-library" \
  --scope full
```

多份招标文件（含澄清、补遗）时重复 `--tender` 参数逐份登记。

## 产出

- 项目目录：`source/`、`analysis/`、`analysis/extracted-text/`、`output/商务文件/`、`output/技术文件/`、`output/资格证明文件/`、`review/`
- `analysis/project-intake.md`：生成范围、招标文件清单、资料库路径、缺失或不可读的输入
- `project-state.json`：阶段进度状态文件（阶段0自动标记完成；仅技术范围时阶段4自动标记跳过）

## 硬性要求

- **没有招标文件时停止**，向用户索取后再初始化
- 项目名称与标包号从招标文件封面/首页核实，不要凭对话猜测

## 完成标志

项目目录创建成功、intake 登记完整。进入阶段1前运行状态确认：

```powershell
python -X utf8 <scripts>\project_status.py "bid-projects\<项目>"
```
