# 阶段7细则：合规审查与交付

> 配套阅读：`references/document-checklist.md`（最终检查清单）。
> 范围裁剪：仅技术部分（technical-only）时审查项裁剪为技术★条款响应、技术评分覆盖率、技术偏离表无空项、格式校验与人工核查清单；商务类检查项标记"不适用"。

## 目标

全面审查，确保无遗漏无错误。输出 `review/compliance-report.md`（用 `templates/compliance-report.md`），然后运行质量门禁。

## 质量门禁

```powershell
# P0/P1
python -X utf8 <scripts>\check_p0_gates.py "bid-projects\<项目>"
# P2 深度+覆盖率
python -X utf8 <scripts>\check_content_quality.py "bid-projects\<项目>"
# 全量门禁（内含 P0/P1/P2）
python -X utf8 <scripts>\validate_bid_package.py "bid-projects\<项目>"
```

```bash
python3 -X utf8 <scripts>/check_p0_gates.py "bid-projects/<项目>"
python3 -X utf8 <scripts>/check_content_quality.py "bid-projects/<项目>"
python3 -X utf8 <scripts>/validate_bid_package.py "bid-projects/<项目>"
```

报告：`analysis/p0-gate-report.md` + `analysis/content-quality-report.md` + `review/validation-report.md`。**交付前逐项处理完。**

## 审查必须确认

### P0 五项（任一项 blocker = 不能交付）

- [ ] 提取门禁通过（无 needs_ocr/failed）
- [ ] `hard-parameters.md` 填完；报价/有效期/保证金与响应文件一致；**分项限价均未超**
- [ ] `format-clone-checklist.md` 无「缺口」；成品目录对齐官方格式章
- [ ] ★三角闭环（偏离表位置 + 正文位置 + 状态已响应）
- [ ] 资料库非空壳禁写违规（outline_only 时无大段伪正文）

### P1 路由（warning 应清零后再交付）

- [ ] `project-profile.md` 类型与递交方式已确认
- [ ] 电子标：`e-bid-delivery-checklist` 平台动作完成或明确责任人
- [ ] 多现场/改造：`multi-site-plan` 已融入实施方案
- [ ] 施工安装：安全环保专章已写
- [ ] `scoring-strategy` 可得分项已执行或用户确认放弃

### P2 内容质量

- [ ] `content-quality-report` 偏薄章节已加厚或有合理说明
- [ ] ★/强制条款正文覆盖率达标
- [ ] 若有 `requirement-index.md`，需求编号覆盖达标

### 常规项

- [ ] 每条★条款有明确响应（**一条未响应 = 不能交付**）
- [ ] 每个评分项映射到响应章节和证据
- [ ] 偏离表无空行；不允许偏离时无负偏离
- [ ] 资格材料齐全或已列为缺口；五件套/三件套完整
- [ ] 承诺书保持官方原文
- [ ] 有效期、限价（含分项）、服务范围、质保前后一致；报价大小写一致
- [ ] 三张导航表页码回填或已提醒
- [ ] 签章/装订/正副本已确认
- [ ] DOCX 格式校验通过、无 Markdown 泄漏
- [ ] 写作大纲已用户确认
- [ ] 技术含项目管理/实施方案/进度计划（或注明不适用）
- [ ] 有响应样本时抽查模块完整度

## 结论与交付

结论：**可交付** / **需修改后交付**（逐条列出修改项）。交付内容：成品 DOCX + 合规审查报告 + 人工核查清单。

全部确认后更新状态收尾：

```powershell
python -X utf8 <scripts>\project_status.py "bid-projects\<项目>" --complete 7
```
