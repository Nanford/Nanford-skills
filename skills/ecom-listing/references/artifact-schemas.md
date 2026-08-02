# 下游产物规范

所有 JSON 使用 UTF-8、`schema_version: "1.0"`。允许添加不冲突的扩展字段，但不要改名或删除下列核心字段。

## strategy.json

```json
{
  "schema_version": "1.0",
  "site": {
    "platform": "amazon",
    "country": "US",
    "locale": "en-US",
    "site_id": "amazon-US"
  },
  "creative": {
    "aspect_ratio": "1:1",
    "width": 2000,
    "height": 2000,
    "selling_point_mode": "from_listing",
    "bestseller_style_analysis": false,
    "generate_copy": true
  },
  "image_set": {
    "mode": "smart",
    "minimum_images": 7,
    "slots": []
  },
  "image_provider": {
    "preferred": "codex-imagegen",
    "fallback_order": []
  },
  "constraints": {
    "brand_colors": [],
    "forbidden_visuals": [],
    "must_include": []
  }
}
```

`selling_point_mode` 使用 `manual`、`ai_assist` 或 `from_listing`。`image_set.mode` 使用 `smart` 或 `custom`。图片提供方使用 `codex-imagegen`、`qwen-image-3.0-pro`、`nano-banana-2`、`volcengine-seedream` 或用户配置的自定义值。

## copy.json

```json
{
  "schema_version": "1.0",
  "site_id": "amazon-US",
  "locale": "en-US",
  "sku": "SKU-001",
  "brand": "Brand",
  "title": "Localized product title",
  "bullets": [
    "Benefit - Enjoy an evidence-backed product advantage in a relevant customer scenario"
  ],
  "bullet_dimensions": ["core_function"],
  "description": "Localized long description",
  "search_terms": "backend search terms",
  "image_copy": {
    "sp1": {
      "headline": "Short benefit",
      "support": "One concise proof point"
    }
  },
  "excluded_points": [
    {
      "id": "attribute.capacity",
      "reason": "needs_confirmation"
    }
  ]
}
```

`bullets` 与 `bullet_dimensions` 按相同顺序一一对应。图上文案只引用已确认事实。

## image_jobs.json

```json
{
  "schema_version": "1.0",
  "site_id": "amazon-US",
  "locale": "en-US",
  "provider": "codex-imagegen",
  "jobs": [
    {
      "id": "01-main",
      "type": "main",
      "base_prompt": "Photorealistic product on pure white background, centered, no text, no logo, no watermark",
      "reference_images": ["uploads/main.jpg"],
      "size": [2000, 2000],
      "aspect_ratio": "1:1",
      "text_layers": [],
      "provider_options": {}
    },
    {
      "id": "02-feature",
      "type": "feature",
      "base_prompt": "Product detail composition with clean copy space on the left, no text, no logo, no watermark",
      "reference_images": ["uploads/main.jpg"],
      "size": [2000, 2000],
      "aspect_ratio": "1:1",
      "text_layers": [
        {
          "text": "Short benefit",
          "box": [0.06, 0.08, 0.46, 0.30],
          "font_size": 0.065,
          "color": "#111111",
          "align": "left"
        }
      ],
      "provider_options": {}
    }
  ]
}
```

`jobs` 的数量必须满足策略要求且至少为 7。`id` 唯一并使用便于排序的两位序号。`reference_images` 使用相对于工作目录的路径；`box` 为 `[left, top, right, bottom]` 的 0 至 1 归一化坐标。
