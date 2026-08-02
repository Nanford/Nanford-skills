# 图片提供商路由

## Codex App ImageGen

- 工具：`image_gen__imagegen`
- 认证：由 Codex App 管理。
- 用法：由 Skill 直接调用，不通过 `gen_image.py`。

## 阿里云百炼

- Provider：`qwen-image-3.0-pro`
- 模型：`qwen-image-3.0-pro`
- Key：`DASHSCOPE_API_KEY`
- 可选覆盖：`DASHSCOPE_BASE_URL`、`DASHSCOPE_MODEL`
- 当前模型处于邀测阶段，需先在模型广场申请权限。
- 官方文档：https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference

## Google Nano Banana 2

- Provider：`nano-banana-2`
- 模型：`gemini-3.1-flash-image`
- Key：`GEMINI_API_KEY`
- 可选覆盖：`GEMINI_BASE_URL`、`GEMINI_IMAGE_MODEL`
- 官方文档：https://ai.google.dev/gemini-api/docs/image-generation

## 火山引擎 Seedream

- Provider：`volcengine-seedream`
- 默认模型：`doubao-seedream-4-5-251128`
- Key：`ARK_API_KEY`
- 可选覆盖：`ARK_BASE_URL`、`ARK_IMAGE_MODEL`
- 默认接口：`https://ark.cn-beijing.volces.com/api/v3/images/generations`
- 官方 API：https://api.volcengine.com/api-docs/view?action=ImageGenerations&serviceCode=ark&version=2024-01-01

## 选择原则

- Codex App：优先 `codex-imagegen`。
- 商品参考图较多且需要一致性：优先 Nano Banana 2 或 Seedream。
- 国内网络与阿里云体系：优先 Qwen Image 3.0 Pro。
- 用户指定提供商时不要自动切换；只有用户允许回退时才按 `strategy.json` 的顺序重试。
