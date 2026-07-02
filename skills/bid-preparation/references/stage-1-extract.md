# 阶段1细则：文本提取

> `<scripts>` 指 Skill 安装目录下的 `scripts/`（见 SKILL.md）。

## 目标

分析前把全部招标文件（正文、澄清、补遗、附件）提取为可检索文本。

## 步骤

```powershell
# Windows PowerShell
python -X utf8 <scripts>\extract_text.py `
  --output-dir "bid-projects\<项目>\analysis\extracted-text" `
  "bid-projects\<项目>\source\<招标文件>"
```

```bash
# macOS / Linux
python3 -X utf8 <scripts>/extract_text.py \
  --output-dir "bid-projects/<项目>/analysis/extracted-text" \
  "bid-projects/<项目>/source/<招标文件>"
```

支持格式：`.pdf`（pypdf/PyPDF2）、`.docx`、`.doc`（需本机 soffice）、`.txt/.md/.csv`。多个文件一次列在命令末尾。

## 产出

- `analysis/extracted-text/*.txt` — 每份输入一个提取文本
- `analysis/extraction-report.md/.json` — 提取状态报告（成功/失败/受限原因）

## 硬性要求

- **扫描版 PDF 无法提取文字**：提取报告会标记，需要告知用户做 OCR 或提供文字版
- **强制条款或官方格式表所在部分无法可靠读取时，立即停止并告知用户，不得靠猜继续**
- PDF 表格提取会碎片化：评分表、SLA 表等关键表格区域需对照原文人工重建

## 完成标志

所有输入文件在提取报告中状态明确（ok / 需OCR / 需soffice）。完成后更新状态：

```powershell
python -X utf8 <scripts>\project_status.py "bid-projects\<项目>" --complete 1
```
