# 阶段1细则：文本提取（含 P0 硬停止）

> `<scripts>` 指 Skill 安装目录下的 `scripts/`（见 SKILL.md）。

## 目标

分析前把**全部招标文件**（正文、澄清、补遗、附件）以及**用户提供的响应文件样本**提取为可检索文本。  
**P0**：任一份招标正文提取失败或疑似扫描件（`needs_ocr`）→ **硬停止**，禁止进入阶段2解标与后续写作。

## 步骤

```powershell
python -X utf8 <scripts>\extract_text.py `
  --output-dir "bid-projects\<项目>\analysis\extracted-text" `
  "bid-projects\<项目>\source\<招标文件>"

# 响应样本（若有）
python -X utf8 <scripts>\extract_text.py `
  --output-dir "bid-projects\<项目>\analysis\extracted-text\response-samples" `
  "bid-projects\<项目>\source\response-samples\<样本>"
```

```bash
python3 -X utf8 <scripts>/extract_text.py \
  --output-dir "bid-projects/<项目>/analysis/extracted-text" \
  "bid-projects/<项目>/source/<招标文件>"
```

支持：`.pdf`、`.docx`、`.doc`（优先 Word/WPS COM，其次 soffice）、`.txt/.md/.csv`。

## 产出

- `analysis/extracted-text/*.txt`
- `analysis/extraction-report.md/.json` — **含 gate_ok / hard_stop**
  - `ok`：可用
  - `needs_ocr`：有效字数过低或疑似扫描件
  - `failed`：转换/解析失败

## P0 硬停止规则

| 情况 | 动作 |
|------|------|
| 任一份**招标文件** status ≠ ok | **停止**。告知用户做 OCR 或提供可复制文字版；重新提取至全部 ok |
| 强制条款/评分表/官方格式表所在文件不可读 | **停止**，不得靠猜 |
| 仅响应样本 needs_ocr | 警告：对照深度受限；招标文件 ok 仍可解标，但须记录限制 |
| PDF 表格碎裂 | 评分表/参数表须对照原件人工重建进 hard-parameters / scoring-matrix |

### OCR 指引（给用户）

1. 用 ABBYY / Adobe Acrobat / 微软 OCR / 天若等生成**可选中文字**的 PDF 或 DOCX  
2. 替换 `source/` 中对应文件后重跑 `extract_text.py`  
3. 打开 `extraction-report.md` 确认 **阶段1硬停止门禁：通过**  
4. 才允许 `--complete 1`

## 完成标志

```powershell
# 报告 gate_ok 必须为 true
python -X utf8 <scripts>\project_status.py "bid-projects\<项目>" --complete 1
```

`extraction-report.json` 中 `gate_ok: true` 前**禁止** `--complete 1`。
