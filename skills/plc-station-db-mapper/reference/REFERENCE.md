# PLC Station DB Mapper Reference

## 目录
1. 工作流（交互式分支）
2. 输入类型决策树
3. 截图表到标准表规则
4. 标准表结构
5. 地址规则
6. 动态步长（Stride）推算
7. 批量地址推算
8. 命令示例
9. 常见错误

## 1. 工作流（交互式分支）

```text
用户调用 skill
  ↓
询问输入类型（1-4）
  ↓
  ├─ 1.DB截图 → 视觉识别 → 提取字段 → 检测Struct→计算stride → 标准化 → 生成
  ├─ 2.导出PDF → 逐页读取 → 提取字段 → 同上
  ├─ 3.导出XLSX → 读取Excel → 检测地址格式
  │    ├─ DB地址 → normalize + stride 流程
  │    ├─ %I/%Q/%M → 直接标准化（无stride）
  │    └─ 纯偏移 → 需default-db → normalize
  └─ 4.手动输入 → 用户给出点位+stride → 直接生成
```

## 2. 输入类型决策树

### 如何判断输入类型
| 特征 | 类型 | 处理路径 |
|---|---|---|
| PNG/JPG 图片，能看到 Name/Type/Offset 列 | DB截图 | 分支 A |
| PDF 文件，标题含 DB 号 | 导出PDF | 分支 B |
| XLSX 文件，地址含 `DB` 或 `%DB` | 导出XLSX (DB) | 分支 C1 |
| XLSX 文件，地址含 `%I`/`%Q`/`%M` | 导出XLSX (I/O) | 分支 C2 |
| XLSX 文件，地址是纯数字偏移 | 导出XLSX (偏移) | 分支 C3 |
| 用户以文字/表格直接给出 | 手动输入 | 分支 D |

### 地址格式识别优先级
1. `DB{N},{X/B/W/D}{byte}` — 标准 DB 地址，直接使用
2. `%DB{N}.DB{X/B/W/D}{byte}` — TIA Portal 格式，转换为标准格式
3. `%I`/`%Q`/`%M` — I/O 地址，不走 stride 流程
4. 纯数字（如 `16.2`、`160`）— 偏移地址，需要 `--default-db`

## 3. 截图表到标准表规则
脚本：`scripts/normalize_screenshot_excel.py`

### 3.1 输入列（可自动识别或显式指定）
- 字段名列：`Name / Tag / Field / 字段 / 字段名 / 变量名`
- 类型列：`Type / Data Type / Datatype / 数据类型 / 类型`
- 地址列：`Address / Addr / Offset / Logical Address / 地址 / 偏移`
- 注释列：`Comment / Description / 备注 / 注释 / 描述`（可选）
- 类别列：`Category / Group / 分类 / 类别`（可选）

### 3.2 输出列（固定）

```text
Tag Name | Address | Data Type | Respect Data Type | Description
```

### 3.3 Tag Name 生成

```text
<station>.<category>.<field>
```

### 3.4 地址生成
- 绝对地址（`DB76,X16.2` 或 `%DB76.DBX16.2`）：直接沿用（TIA格式自动转换）。
- 偏移地址（`16.2`、`160`）：使用 `--default-db` 补齐 DB 号。
- 地址类型 `X/B/W/D` 由数据类型推断。

## 4. 标准表结构
最小必需列：`Tag Name`、`Address`、`Data Type`

可选列：`Respect Data Type`（默认 `1`）、`Description`

`Tag Name` 需包含站台号前缀，便于分站台推算与排序。

## 5. 地址规则

### 格式
```text
DB{db_no},{kind}{byte}[.{bit}]
```

### Kind 与数据类型映射

| 数据类型 | Kind | 字节数 |
|---|---|---|
| Boolean / Bool | X | 需 bit (0-7) |
| Byte / Char / USInt / SInt | B | 1 |
| Short / Int / Word / UInt | W | 2 |
| DInt / DWord / UDInt / Real / Float | D | 4 |

### TIA Portal 格式转换
```text
%DB142.DBX0.0  →  DB142,X0.0
%DB142.DBW160  →  DB142,W160
%DB50.DBD2.0   →  DB50,D2
```

### 正则
```python
# 标准格式
r"^DB(\d+),(X|B|W|D)(\d+)(?:\.(\d+))?$"
# TIA Portal 格式
r"^%?DB(\d+)\.DB(X|B|W|D)(\d+)(?:\.(\d+))?$"
```

### 约束
- `X` 必须有 `bit`，范围 `0..7`
- 非 `X` 不允许 `.bit`

## 6. 动态步长（Stride）推算

### 6.1 从 Struct 大小推算（最可靠，单站台即可）
DB 截图中如果有 Struct 行，stride = Struct 总字节大小。

计算方法：
```text
stride = 最后字段的 offset + 该字段的字节长度
```

字段字节长度：
- Bool: 不独立占字节（按 bit 打包在同一字节中）
- Byte/Char/USInt/SInt: 1
- Int/Word/UInt: 2
- DInt/DWord/UDInt/Real: 4

对于以 Bool 结尾的 Struct，stride = 最后一个 Bool 所在的字节位置 + 1（向上对齐到完整字节），再根据 Struct 对齐要求可能需要 2 字节对齐。

### 6.2 多站台自动推算
不传 `--stride` 时，脚本从输入标准表自动推算：
- 要求输入中至少有 2 个站台。
- 按同字段（去站台前缀）在不同站台间比较字节偏移。

公式：
```text
stride = (byte2 - byte1) / (station2 - station1)
```

### 6.3 手动指定
使用 `--stride`：
```text
DB51=20,DB76=2
```

## 7. 批量地址推算

```text
delta = target_station - base_station
new_byte = base_byte + delta * stride_map[db_no]
```

生成地址：
- 位地址：`DB{db},X{new_byte}.{bit}`
- 其他：`DB{db},{kind}{new_byte}`

排序规则：
1. 站台号升序
2. 类别：Task > Alarm > State > Other
3. Tag Name 字典序

## 8. 命令示例

### 8.1 截图表标准化
```bash
python scripts/normalize_screenshot_excel.py \
  --input raw_db.xlsx \
  --output normalized_1009_task.xlsx \
  --station 1009 \
  --category Task \
  --default-db 51
```

### 8.2 自动 stride 批量生成
```bash
python scripts/generate_station_table.py \
  --input normalized_multi_station.xlsx \
  --stations 1009-1022 \
  --output output/站台点位表_1009-1022.xlsx \
  --base-station 1009
```

### 8.3 手动 stride 批量生成
```bash
python scripts/generate_station_table.py \
  --input normalized_1009.xlsx \
  --stations 1009-1022 \
  --stride DB51=20,DB76=2 \
  --output output/站台点位表_1009-1022.xlsx \
  --base-station 1009
```

## 9. 常见错误
- **自动 stride 失败（只有一个站台）**：尝试从 Struct 大小推算，或补第二站台样本，或使用 `--stride`。
- **自动 stride 冲突**：字段结构不一致或 OCR 错误，先修正输入。
- **偏移地址无 DB 号**：传 `--default-db`。
- **Boolean 地址缺 bit**：改为 `16.0~16.7`。
- **Tag Name 无站台前缀**：规范为 `<station>.<category>.<field>`。
- **不支持的数据类型**：检查是否为 String/LReal 等特殊类型，手动处理或跳过。
- **%I/%Q 地址误走 stride 流程**：这些是 I/O 点位，不适用站台化推算。
