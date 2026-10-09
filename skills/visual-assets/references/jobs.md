# 生成任务记录

`generated/jobs.json` 由当前执行者维护，不写 `project.json`、`assets/assets.json` 或费用账本。写入前读最新文件，保留其他任务；使用 UTF-8 临时文件检查后原子替换。根结构是 `{"schema_version":"1.0","jobs":[]}`，字段沿用 `docs/DATA_CONTRACTS.md` 第 5 节。

新任务初始记录示例：

```json
{
  "job_id": "job_illustration_001",
  "provider": "codex_image_gen",
  "region": null,
  "model": null,
  "prompt_path": "generated/prompts/job_illustration_001.md",
  "reference_asset_ids": [],
  "request_hash": null,
  "provider_task_id": null,
  "state": "prepared",
  "reserved_cost": null,
  "actual_cost": null,
  "result_files": [],
  "submitted_at": null,
  "last_checked_at": null
}
```

提交前计算 `request_hash`：对实际提示词、所用工具、实际指定的参数、参考图片 SHA-256 组成的规范化 JSON 取 SHA-256。不得把密钥纳入摘要。内置工具没有指定模型参数时保持 `model: null`；结果返回具体模型后再补记。

`prepared → submitted → running → succeeded / failed / unknown` 表示真实进度，同步工具可从 `submitted` 直接进入终态。工具返回成功仍须检查文件存在、可解码且已保存项目内，才写 `succeeded`。该状态只代表素材生成完成，入片视觉检查和权利检查另行登记。

`result_files` 每项为 `{path, sha256, bytes, purpose, asset_id}`：路径相对项目根目录，校验值与字节数实测，入库前 `asset_id` 为 `null`。如需记录透明、比例或构图等额外参数，将实际工具参数与审查结论保存在同目录的 `<job_id>.record.json`，不要假装未支持的尺寸、种子或质量参数已提交给工具。

`reserved_cost`、`actual_cost` 已知时使用 `{currency, amount}`，未知时为 `null`。内置工具没有价格或消耗回执时，在记录中说明用量未返回；不得填 0、宣称免费或伪造外部结算。外部计费任务提交前须有已核实的请求费用上界和预算预留，结果不明继续占用预算。

新提示词或新的编辑生成建立新 `job_id`，保留上一版记录。任务 ID、生成时间和工具返回说明保留实际值，不能用自编的内部 ID 冒充服务商 ID。
