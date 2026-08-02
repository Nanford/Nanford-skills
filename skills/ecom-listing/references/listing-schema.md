# listing.json 契约

```json
{
  "schema_version": "1.1",
  "product": {
    "sku": "SKU-001",
    "name_zh": "内部商品名称",
    "category": "3c-accessory",
    "category_path": "电子配件 > 充电设备",
    "brand": null
  },
  "attributes": [
    {
      "key": "material",
      "value": "铝合金外壳",
      "confidence": "high",
      "evidence": "document",
      "source": "spec.pdf#page=2",
      "needs_confirmation": false,
      "note": ""
    }
  ],
  "selling_points": [
    {
      "id": "sp1",
      "short": "稳固防滑",
      "full": "底部防滑结构减少桌面使用时的移动。",
      "dimension": "material_craft",
      "priority": 1,
      "evidence": "image",
      "source": "uploads/detail-01.jpg",
      "needs_confirmation": false,
      "suggested_image_types": ["feature", "detail"]
    }
  ],
  "images": [
    {
      "file": "uploads/main.jpg",
      "role": "primary_source",
      "notes": "正面 45 度角",
      "issues": []
    }
  ],
  "open_questions": [],
  "confirmed_at": null
}
```

约束：

- `confidence`：`high`、`medium`、`low`。
- `evidence`：`image`、`user_input`、`document`、`inferred`。
- `dimension`：`core_function`、`material_craft`、`use_scenario`、`spec_compatibility`、`accessory_service`。
- `priority`：1 最高，5 最低。
- `needs_confirmation: true` 的内容不得进入下游公开文案，除非用户明确确认并更新本文件。
