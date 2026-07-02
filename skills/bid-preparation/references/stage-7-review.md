# 阶段7细则：合规审查与交付

> 配套阅读：`references/document-checklist.md`（最终检查清单）。
> 范围裁剪：仅技术部分（technical-only）时审查项裁剪为技术★条款响应、技术评分覆盖率、技术偏离表无空项、格式校验与人工核查清单；商务类检查项标记"不适用"。

## 目标

全面审查，确保无遗漏无错误。输出 `review/compliance-report.md`（用 `templates/compliance-report.md`），然后运行质量门禁。

## 质量门禁

```powershell
# Windows PowerShell
python -X utf8 <scripts>\validate_bid_package.py "bid-projects\<项目>"
```

```bash
# macOS / Linux
python3 -X utf8 <scripts>/validate_bid_package.py "bid-projects/<项目>"
```

门禁报告 `review/validation-report.md` 末尾自动汇总**人工核查清单**：留空待补材料（"此处附：XXX"占位页）、构建警告（图片待补充）、导航表 `P__` 页码待回填、资料匹配表未闭环缺口、签字盖章与目录域更新提醒。**交付时必须把这份清单一并交给用户，逐项处理完才算交付完成。**

## 审查必须确认

- [ ] 每条★条款有明确响应（**一条未响应 = 不能交付**）
- [ ] 每个评分项映射到响应章节和证据（覆盖率：🟢刻意优化 / 🟡有内容 / 🔴无内容）
- [ ] 偏离表无空行
- [ ] 资格材料齐全或已列为缺口；五件套/三件套完整
- [ ] 承诺书保持官方原文
- [ ] 有效期、限价、服务范围、质保、付款条款前后一致；报价大小写一致
- [ ] 三张导航表与评分表/审查表一致，页码已按 `page-map.md` 对照表回填（或已明确提醒用户回填）
- [ ] 签章位置齐全、页码连续、正副本份数、装订密封要求已确认
- [ ] 未把未经证实的事实写成已确认
- [ ] `output/投标响应文件.docx` 存在且格式校验通过，无内部写作痕迹

## 结论与交付

结论：**可交付** / **需修改后交付**（逐条列出修改项）。交付内容：成品 DOCX + 合规审查报告 + 人工核查清单。

全部确认后更新状态收尾：

```powershell
python -X utf8 <scripts>\project_status.py "bid-projects\<项目>" --complete 7
```
