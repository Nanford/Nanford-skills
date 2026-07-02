---
name: plc-station-db-mapper
description: 面向西门子PLC站台化项目的点位映射技能。支持4种输入方式（DB截图、PDF导出、Excel导出、手动输入），交互式引导用户选择输入类型后，按对应路径标准化为统一Excel并批量生成目标站台点位表。用于 Task/Alarm/State 等类别的点位扩展、补表、续表。
---

# PLC Station DB Mapper

## 核心原则
- 以本次项目提供的数据为准，不使用历史固定偏移模板。
- 示例中的 `DB50=20`、`DB70=2` 仅为参考示例，不可默认复用。
- 每次先确认输入类型，再按对应分支处理。

## Step 0：交互式确认输入类型

**每次用户调用本 skill 时，必须先询问以下选择：**

```
请选择你本次提供的原始点位格式：

1. DB截图 — TIA Portal 中 DB 块的截图（如 DB50.png），包含 Name/Type/Offset 等列
2. 导出PDF — TIA Portal 导出的 DB 定义 PDF 文件（如 堆垛机DDJ_Data (DB142).pdf）
3. 导出XLSX — TIA Portal 导出的变量表 Excel（如 原料库南D02变量表.xlsx）
4. 手动输入 — 直接给出初始点位列表、偏移量(stride)、以及点位结构

请告诉我编号（1/2/3/4），以及：
- 目标站台范围（如 1009-1022）
- 基准站台号（如 1009）
- 点位类别（如 Task / Alarm / State，可多个）
```

根据用户的选择，进入对应分支。

---

## 分支 A：DB截图（选择1）

**适用场景**：用户提供 TIA Portal 中 DB 块编辑器的截图（PNG/JPG），截图中能看到字段表格。

### 处理步骤

1. **读取截图**：使用 Claude 视觉能力识别截图中的表格内容。
2. **提取字段**：识别每行的 `Name`（字段名）、`Type`（数据类型）、`Offset`（偏移量）、`Comment`（注释）。
3. **检测 Struct 行**：
   - 如果截图顶部有 Struct 行（如 `M[5001]  Struct  0.0`），说明这是站台化的重复结构。
   - **Struct 的总字节大小 = stride**。计算方法：最后一个字段的 offset + 该字段的字节长度 = Struct 大小。
   - 有 Struct 行时，**只需要 1 个站台的数据就能推算全部站台**，不需要第二站台。
4. **确认 DB 号**：从截图标题或用户输入获取 DB 号（如 DB50、DB70）。
5. **类别拆分**：根据「类别自动判定规则」将字段分为 Task / Alarm / State，而非全部归入用户指定的单一类别。
6. **标准化为五列格式**：
   - `Tag Name`：`<station>.<category>.<field>`（category 由步骤 5 判定）
   - `Address`：`DB{N},{kind}{byte}[.{bit}]`（用 Offset + DB 号 + 数据类型推断 kind）
   - `Data Type`、`Respect Data Type`（默认1）、`Description`
   - 字段名统一为 PascalCase（如 `Drive_FAULT` → `DriveFault`）
7. **生成目标站台点位表**：按 stride 批量推算所有目标站台的地址。

### 关键提取规则
- Struct 行本身不作为点位输出，只用于计算 stride。
- 偏移量是 Struct 内部相对偏移，需加上基准站台的起始偏移。
- 如果用户提供了基准站台在 DB 中的起始绝对偏移（如"1009 站从 DB51 的 byte 160 开始"），则使用该值；否则需要询问。

### 询问要点
- DB 号（如果截图中不明确）
- 基准站台在 DB 中的起始偏移（如果无法从截图推断）
- 类别（Task/Alarm/State 或自定义）

---

## 分支 B：导出 PDF（选择2）

**适用场景**：用户提供从 TIA Portal 导出的 DB 定义 PDF。

### 处理步骤

1. **读取 PDF**：使用 Claude 视觉能力逐页读取 PDF（PDF 中通常是 DB 块的表格定义）。
2. **提取表格**：识别 Name、Data Type、Offset、Comment 列。
3. **后续流程同分支 A 的步骤 3-6**。

### 注意事项
- PDF 可能有多页，需要逐页读取并合并。
- PDF 表格排版可能不如截图清晰，需注意 OCR 准确性。
- 如果 PDF 包含多个 DB 块的定义，需要与用户确认处理哪些。

---

## 分支 C：导出 XLSX（选择3）

**适用场景**：用户提供从 TIA Portal 导出的变量表 Excel 文件。

### 处理步骤

1. **读取 Excel**：使用 openpyxl 读取，自动识别列头。
2. **检测地址格式**，进入子分支：

#### 子分支 C1：DB 地址（`DB{N},X/B/W/D{byte}` 或 `%DB{N}.DB{X/B/W/D}{byte}`）
- 这是标准的 DB 块点位，走 normalize + stride 流程。
- 如果地址是 `%DB` TIA 格式（如 `%DB142.DBX0.0`），先转换为 `DB142,X0.0`。
- 如果 Excel 中包含多个站台的数据，自动推算 stride。
- 如果只有单站台，询问 stride 或从 Struct 大小推算。

#### 子分支 C2：I/O 地址（`%I`、`%Q`、`%M` 开头）
- 这些是 PLC 的 I/O 点位，**不适用 stride 站台化推算**。
- 直接标准化为输出格式，不做站台批量复制。
- 告知用户：这些 I/O 点位不遵循 DB 块的站台重复模式，如果需要按站台区分，请提供 DB 块数据。

#### 子分支 C3：纯偏移量（如 `16.2`、`160`）
- 需要用户提供 `--default-db`（DB 号）。
- 走 normalize 标准流程补齐地址。

### 列名自动识别规则
- 字段名：`Name / Tag / Field / 字段 / 字段名 / 变量名`
- 类型：`Type / Data Type / Datatype / 数据类型 / 类型`
- 地址：`Address / Addr / Offset / Logical Address / 地址 / 偏移`
- 注释：`Comment / Description / 备注 / 注释 / 描述`

---

## 分支 D：手动输入（选择4）

**适用场景**：用户直接提供点位信息，无需解析文件。

### 用户需要提供
1. **基准站台点位列表**（以文字或表格形式），每个点位包含：
   - 字段名
   - 地址（完整的 `DB{N},{kind}{byte}` 格式）
   - 数据类型
   - 注释（可选）
2. **stride**（每个 DB 的步长），格式：`DB51=20,DB76=2`
3. **目标站台范围**
4. **类别**

### 处理步骤
1. 将用户提供的点位列表整理为标准五列格式。
2. 使用用户指定的 stride 直接生成全部目标站台。
3. 无需自动推算 stride。

---

## 标准输出格式

所有分支最终输出统一的 Excel，包含：

### 元数据区（第1-7行）
```
# PLC站台点位表
生成日期: YYYY-MM-DD HH:MM:SS
站台范围: 1009-1022 (共14个站台)
基准站台: 1009
DB块步长: DB51=20字节, DB76=2字节
步长来源: auto_struct_size / auto_inferred_from_input / manual
总点位数: N个
```

### 数据区（第8行起）
```
Tag Name | Address | Data Type | Respect Data Type | Description
```

### Tag Name 格式
```
<station>.<category>.<field>
```

### 类别自动判定规则

当用户提供的原始数据（截图/PDF/手动输入）未明确区分类别时，根据字段名和含义自动归类：

| 类别 | 判定规则 | 典型字段名关键词 |
|------|----------|------------------|
| **Task** | 任务相关：任务号、条码、站台地址、货物类型 | Task, Code, StartSta, DestSta, TpType |
| **Alarm** | 故障/报警类：字段名含 Fault、Error、Alarm | *Fault, *Error, *Alarm, TimeOut, Estop, QF_, QS_, PH_, LS_ |
| **State** | 运行状态类：运行、负载、选中、备用等 | Running, Load, Run, Select, BY*, State_* |

**优先级**：
1. 用户明确指定 `--category` 时，全部使用指定类别，不做自动判定。
2. 同一个 DB 截图/Struct 中混合了多种类别的字段时，**必须按上述规则拆分**，分别归入 Alarm / State / Task。
3. 字段名不含明显关键词时，归入 **Other**，并在输出时提示用户确认。

**命名规范**（参考 `reference/托盘输送线.csv`）：
- 输出字段名使用 PascalCase（如 `DriveFault`，不用 `Drive_FAULT`）
- 去除原始字段名中的多余下划线和大小写不一致

### 排序规则
1. 站台号升序
2. 类别优先级：Task > Alarm > State > Other
3. Tag Name 字典序

---

## 地址规则

### 格式
```
DB{db_no},{kind}{byte}[.{bit}]
```

### Kind 与数据类型映射

| 数据类型 | Kind | 字节数 |
|---|---|---|
| Boolean / Bool | X | 0.125（需 bit 位 0-7） |
| Byte / Char / USInt / SInt | B | 1 |
| Short / Int / Word / UInt | W | 2 |
| DInt / DWord / UDInt / Real / Float | D | 4 |

### TIA 格式转换
```
%DB142.DBX0.0  →  DB142,X0.0
%DB142.DBW160  →  DB142,W160
%DB50.DBD2     →  DB50,D2
```

### 地址正则
```python
r"^DB(\d+),(X|B|W|D)(\d+)(?:\.(\d+))?$"
```

---

## Stride（步长）推算规则

### 优先级
1. **Struct 大小**（最可靠）：从 DB 截图/PDF 中 Struct 定义直接计算。
2. **多站台自动推算**：输入中有 ≥2 个站台时，按同字段比较字节偏移。
3. **手动指定**：用户直接给出。

### PLC 型号与对齐
- **S7-300/400**：Struct 内字段按 **字对齐**（2 字节边界），stride 计算时需考虑 padding。
- **S7-1200/1500**：默认 **优化访问**（Optimized block access），无固定对齐，但导出时显示的 Offset 已包含实际布局。
- 如果用户未说明 PLC 型号，从截图/PDF 中推断（TIA Portal v13+ 通常为 S7-1200/1500）；无法确定时询问用户。

### Struct 大小计算
```
stride = 最后字段的 offset + 该字段字节长度
```
例：Struct 最后字段 `BY2 Int 28.0`，Int 占 2 字节 → stride = 28 + 2 = 30。

### 多站台自动推算
```
stride = (byte2 - byte1) / (station2 - station1)
```

---

## 脚本工具

### `scripts/normalize_screenshot_excel.py`
截图/OCR 表 → 标准五列 Excel。

```bash
python scripts/normalize_screenshot_excel.py \
  --input raw_db.xlsx \
  --output normalized.xlsx \
  --station 1009 \
  --category Task \
  --default-db 51
```

### `scripts/generate_station_table.py`
标准 Excel → 目标站台批量点位表。支持 3 种模式。

```bash
# 模式1: 自动 stride（需 ≥2 站台数据）
python scripts/generate_station_table.py \
  --input normalized.xlsx \
  --stations 1009-1022 \
  --output output/站台点位表.xlsx \
  --base-station 1009 \
  --insert-separator

# 模式2: Struct 大小作为 stride（单站台即可）
python scripts/generate_station_table.py \
  --input normalized.xlsx \
  --stations 1009-1022 \
  --struct-size DB51=20,DB76=2 \
  --output output/站台点位表.xlsx \
  --base-station 1009

# 模式3: 手动 stride
python scripts/generate_station_table.py \
  --input normalized.xlsx \
  --stations 1009-1022 \
  --stride DB51=20,DB76=2 \
  --output output/站台点位表.xlsx \
  --base-station 1009

# 一步到位: 从原始Excel直接生成（跳过normalize中间步骤）
python scripts/generate_station_table.py \
  --raw-input raw_db_screenshot.xlsx \
  --station 1009 --category Task --default-db 51 \
  --stations 1009-1022 \
  --struct-size DB51=20 \
  --output output/站台点位表.xlsx \
  --base-station 1009 \
  --insert-separator
```

> **注意**：`--raw-input` 模式每次只支持单个 `--category`。如果原始文件包含多个类别（如 Task + Alarm），需要分别运行再合并，或先用 normalize 脚本分类处理。

---

## 响应模板

每次完成后，输出以下信息：
1. 输入类型与来源。
2. 识别到的字段数量与地址修正项。
3. stride 结果（来源、每个 DB 的值）。
4. 输出文件路径与总点位数。
5. 抽检建议（至少检查首尾两个站台的关键字段地址是否正确）。

---

## 失败回退
- **截图/PDF 识别不清**：请用户提供更高清的截图，或直接导出 Excel。
- **stride 冲突**：停止自动推算，要求用户检查数据一致性或手动指定。
- **仅单站台且无 Struct 信息**：要求用户补充第二站台样本或手动指定 stride。
- **I/O 地址（%I/%Q/%M）**：告知用户不适用站台化推算，直接标准化输出。
- **遇到不支持的数据类型**：列出未识别类型，询问用户如何处理。

---

## 待优化项（脚本层面）
- [x] `normalize_screenshot_excel.py` 增加 `Real/Float/USInt/SInt/UInt/UDInt` 类型支持
- [x] 增加 `%DB` TIA 格式地址的自动转换（`%DB142.DBX0.0` → `DB142,X0.0`）
- [x] 支持 `--struct-size` 参数从单站台直接指定 stride
- [x] 合并两个脚本为单一入口（`--raw-input` 模式）
- [ ] PDF 表格提取（pdfplumber）— 当前通过 Claude 视觉能力处理
