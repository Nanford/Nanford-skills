# 千问办公 + 钉钉接入规范

仅在 Skill 运行于千问办公，且用户选择钉钉 AI 表格或个人单聊通知时读取本文件。

## 接入边界

- 导入 Skill 只表示千问办公能够识别能力，不代表 Python 依赖、本地数据目录、钉钉表格、通知人或定时任务已经配置完成。
- `dws` 的真实调用由千问办公宿主执行。Python 子进程、Windows 任务计划和独立 `dws-core` 进程不能代替宿主调用。
- 钉钉模式使用“本地计划生成 → 千问办公执行 → 结果回写”的三段式链路。不要让 Python 脚本直接调用 `dws`。
- Base ID、table ID、userId 和机器人标识只写入本地 `data/`，不得进入分发包、公开文档或对外消息。
- 单聊收件人来自每家企业档案的“通知人”列，该列在钉钉模式中表示对应操作人。不得固定为安装者、管理员或任何默认账号。
- 创建表格、写入记录、上传附件、发送消息和创建定时任务均会改变外部状态。执行前展示目标与影响范围；首次批量同步和首次单聊测试须取得用户确认。

## 首次调用必须完成的引导

先检查 `config.env` 中的 `SKILL_MODE` 和 `python scripts/init_setup.py --status --json`。接入配置按 `onboarding.md` 恢复；已有本地查询能力可先使用，不被可选通知或调度待办阻塞。

1. 确认用户已在千问办公登录正确的钉钉组织，并确认本次使用已有 AI 表格还是新建一张。
2. 运行 `python scripts/install.py --mode dingtalk`。该命令安装依赖、初始化本地数据与钉钉配置模板、执行首次采集；不会注册无法完成钉钉链路的 Windows 任务计划。
3. 确认企业档案来源：
   - 已有企业资料时，先补充 `data/enterprises.xlsx`，再同步到钉钉；
   - 计划在钉钉维护时，先建立空表，之后以钉钉「企业档案」表为准拉回本地。
4. 创建或绑定一个钉钉 AI 表格 Base，并准备三张表：`政策清单`、`企业档案`、`匹配结果`。字段以 [fields.md](fields.md) 为准；政策表可额外增加 `政策附件` 附件字段。
5. 将 Base ID 和三张表的 table ID 写入 `data/dingtalk_config.json`。不要保留示例占位值。
6. 通过千问办公宿主导出三张表的字段与记录 JSON，分别保存到：
   - `data/dingtalk_dumps/policy_fields.json`、`policy_records.json`
   - `data/dingtalk_dumps/enterprise_fields.json`、`enterprise_records.json`
   - `data/dingtalk_dumps/match_fields.json`、`match_records.json`
7. 将每家企业的对应操作人填写在企业档案“通知人”列，再把这些操作人逐一映射到经过确认的钉钉身份，写入 `data/dingtalk_notify_users.json`。卡片模式使用 `{"userId":"…","openDingTalkId":"…"}`；只有 userId 的旧字符串映射退化为普通文本。`openDingTalkId` 使用 `dws aisearch person --query <姓名> --dimension name --format json` 查询并人工确认；同名或多候选不得自动选取。
8. 运行 `python scripts/dingtalk_aitable_sync.py plan`，向用户展示新增、更新、无变化、当前有效存量待通知人数和批次数。首次批量写入获确认后，由千问办公逐条执行 `data/dingtalk_ops/ops.json` 中的命令；写入后读回并按 `onboarding.md` 保存 `tables` 回执。
9. 首次通知按企业选择一名已确认的对应操作人发送测试消息，并明确测试企业与收件人。先执行该条 `reserve_argv`，再发送；测试成功依据为真实业务成功，卡片需更新完成。核对后保存 `notification` 回执和通知偏好。
10. 每条通知成功后立即把成功的 `政策ID|企业名称` 写入 `data/dingtalk_ops/result.json`，运行 `python scripts/dingtalk_aitable_sync.py mark --result <结果文件>`，再由千问办公执行生成的通知状态回写命令。不要等整批结束才记录；台账成功后仅恢复表格回写。
11. 用户需要每日自动运行时，创建千问办公定时任务，不创建 Windows 任务计划。默认建议每天 09:00，并允许用户改时间。验证调度环境访问相同数据目录与连接器，实际试运行成功后保存 `schedule` 回执。
12. 最后再次运行 `python scripts/init_setup.py --status`，只在本地配置、三表快照、通知人映射、写入验证、单聊验证和定时任务均满足用户选择时宣布接入完成。

## 建表与同步约束

- 钉钉单次建表字段数可能受限；字段较多时先建表，再分批新增字段，每批不超过宿主当前限制。执行前先查看命令能力与返回结构。
- 记录写入使用字段 ID，不使用字段名猜测；每次结构变化后重新导出字段快照。
- `ops.json` 出现新的单选或多选选项时，先扩展字段选项，再执行对应记录 upsert，避免新标签导致整批失败。
- 政策表按规范化 `原文链接` 去重，并以“标题+部门+发布日期”作为第二去重键；匹配表按 `政策ID + 企业名称` 去重。
- 同步只纳入当前有效政策。已过申报截止日、正文明确废止/失效/停止执行，或发布时间超出检索窗口且没有未来有效期证据的政策，不新增到钉钉政策表，也不进入匹配和通知。
- `申报截止`、`处理状态`、`是否匹配`、`备注` 等人工列已有值时不得覆盖。
- 单次记录写入不超过 30 条；大批量任务按分片执行并逐批核对返回结果。
- 附件上传采用钉钉签发的上传凭证，并携带与文件扩展名一致的 `Content-Type`；上传成功后再把 fileToken 写入对应记录。
- 首次同步前必须预览；删除表、字段、记录或清空数据不属于本接入流程。

## 每日任务顺序

1. 运行 `fetch_subsidies.py --collect --content --parse-thresholds`，完成近期政策采集、双重去重、正文解析和有效状态刷新；检查本次 `collection_report.json`，`success=false` 时保留结果并停止后续自动外发。记录每个官方源命中数，某源为 0 或骤降时在日报提示核对页面。
2. 刷新企业表快照并运行 `pull-enterprises`，再执行企业匹配。
3. 刷新政策、企业、匹配三表的字段及全部记录快照，保持 `data.tables[].fields` 与 `data.records` 信封结构。
4. 运行 `dingtalk_aitable_sync.py plan`，逐条执行 `ops.json.commands` 中的 upsert；单批不超过 30 条，以返回 `success:true` 为成功依据。
5. 在已启用且已验证的通知范围内，对“当前有效+匹配+可通知+本地未推送+远端未推送+台账未成功或预留”的每个政策×企业组合，各发送一张卡片，包括隔天补档后的匹配。逐条执行 `reserve_argv`，发送成功立即将对应 `match_key` 写入 `result.json` 的 `notified`，运行 `mark`，再执行通知状态回写命令。台账预留未完成项按 `recovery.md` 核对，不能自动重发。
6. 上传 `attachments/` 中当日新增附件，上传请求的 `Content-Type` 必须与申请凭证时的 MIME 类型一致；fileToken 按 recordId 分批写回政策附件字段。
7. 将系统日报发送给另行配置的任务运维人：有新增时按部门分组并包含通知统计，无新增只报告“今日无新增”，任何采集、同步、发送异常都必须报告。不得借用某家企业的操作人作为默认运维收件人。

## 个人卡片通知协议

`ops.json.notify` 每项只对应一个 `政策ID|企业名称`，包含 `mode`、`enterprise`、`policy_id`、`match_key`、`user_id`、`open_dingtalk_id`、`notify_user`、`title`、`content`、`argv`、`argv_update`、`argv_text` 和 `runbook`。

卡片模式必须按两段执行：

1. 执行 `argv` 中的 `dws chat message send-card --receiver <openDingTalkId> --format json`，从 `result.bizId` 读取卡片业务 ID。
2. 用业务 ID 替换 `argv_update` 中的 `{{BIZ_ID}}` 并执行 `update-card`。`--flow-status` 必须为 `3`，否则卡片会停留在生成中。
3. create 明确未送达时，只有存在已确认 userId 才执行 `argv_text` 普通 Markdown 兜底。超时或结果不明时先核对；update 失败优先沿用已有 bizId 恢复，不重新创建卡片。映射缺失时跳过并报告，不得改发他人。

卡片正文固定包含企业名称、政策标题与原文链接、匹配结论与命中条件、匹配表入口；政策表存在“支持额度”时以“补贴金额”显示，存在“申报截止”时同列显示。字段为空时省略对应信息，不显示空占位。

通知成功的唯一闭环是：钉钉返回业务成功结果，卡片 update 完成且 `flow-status=3`，随后本地与远端匹配记录均回写“已推送”。本地已推送或远端快照已推送任一成立，都不得再次发送；内容重新解析或匹配说明变化也不得自动重置成功状态。

## dws 执行约束

- `dws` 命令必须独立执行，不拼接管道、重定向、`cd`、环境变量前缀或后台运行。宿主代执行时不要依赖 `--output` 落盘，以免产生空文件并覆盖快照。
- 大结果被宿主截断时，使用 `--jq ".data"` 缩小结果，并从 PostToolUse 保存的 `qoder-hook-output/hook-output-*.txt` 中解析 `dws_tool_result.content` 重建快照。
- 写操作必须以 `success:true`、`openTaskId` 或 `bizId` 等业务结果核验，不能把“命令已发起”当作成功。
- Markdown 内容必须传真实换行符与空行，不得传字面量 `\n`。
- 出现 `DWS_IDENTITY_CHANGED` 或连接器 `enabled=false` 时停止外部写入，提示用户重新授权；恢复后从已完成步骤之后续跑，已推送状态继续承担幂等保护。

## 接入完成口径

完成状态至少包含：本地依赖与目录正常、`SKILL_MODE=dingtalk`、Base 与三张表 ID 有效、字段和记录快照可刷新、企业档案可双向流转、至少一次受控写入成功、每家启用通知的企业均配置对应操作人及 userId、单聊测试成功。定时任务只有在用户选择启用后才属于完成条件。
