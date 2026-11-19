# 甘特图规范（`diagram: "gantt"`）

适用于研发排期、项目实施计划、季度路线图、招投标工期计划、里程碑跟踪等进度可视化场景。

参考成品：`examples/dev-plan-gantt.svg`（由 `examples/dev-plan-gantt.json` 生成）。

---

## JSON 模型

### 1. 标准单阶段排期（复刻 ProcessOn 经典模板）

```json
{
  "diagram": "gantt",
  "title": "开发计划甘特图",
  "themeName": "processon-teal",
  "canvas": { "w": 1200 },
  "timeline": {
    "start": "2024-02-01",
    "end": "2024-04-30",
    "unit": "month-week"
  },
  "tasks": [
    { "name": "需求调研", "start": "2024-02-01", "end": "2024-02-14", "color": "primary" },
    { "name": "UI设计", "start": "2024-03-01", "end": "2024-03-21", "color": "pink" },
    { "name": "前端开发", "start": "2024-03-08", "end": "2024-03-31", "color": "green" },
    { "name": "后端开发", "start": "2024-03-07", "end": "2024-04-18", "color": "navy" },
    {
      "name": "测试上线",
      "bars": [
        { "start": "2024-04-18", "end": "2024-04-23", "color": "primary" },
        { "start": "2024-04-24", "end": "2024-04-30", "label": "月底上线", "color": "red" }
      ]
    }
  ]
}
```

### 2. 多阶段 / 里程碑 / 今日线 / 进度条（进阶用法）

```json
{
  "diagram": "gantt",
  "topTitle": "智慧园区平台 V2.0 季度实施计划",
  "cornerText": "阶段 / 任务",
  "themeName": "processon-blue",
  "canvas": { "w": 1280 },
  "showRowLines": true,
  "timeline": { "start": "2026-01-01", "end": "2026-06-30", "unit": "quarter-month" },
  "today": "2026-03-18",
  "groups": [
    {
      "title": "筹备",
      "tasks": [
        { "name": "立项调研", "start": "2026-01-01", "end": "2026-01-25", "progress": 1.0 },
        {
          "name": "架构评审",
          "bars": [
            { "start": "2026-01-20", "end": "2026-02-12", "color": "accent1" },
            { "type": "milestone", "at": "2026-02-15", "label": "方案冻结" }
          ]
        }
      ]
    },
    {
      "title": "研发实施",
      "tasks": [
        { "name": "中台开发", "start": "2026-02-15", "end": "2026-04-25", "color": "accent2", "progress": 0.65 }
      ]
    }
  ],
  "legend": [
    { "color": "primary", "label": "常规任务" },
    { "color": "critical", "label": "里程碑 / 今日线" }
  ]
}
```

---

## 字段说明

### 顶层字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `diagram` | 是 | 固定填 `"gantt"` |
| `title` | 否 | 左侧竖排总标题（使用扁平 `tasks` 时自动作为左侧竖排栏文字，如 `"开发计划甘特图"`） |
| `topTitle` | 否 | 顶部通栏大标题横幅，不填则不画（ProcessOn 经典甘特图默认把标题放在左侧竖栏） |
| `cornerText` | 否 | 左上角浅色占位格文字（如 `"阶段 / 任务"`），不填则留白 |
| `themeName` | 否 | 配色主题，默认 `processon-teal`，见 `references/color-themes.md` |
| `canvas.w` | 否 | 画布宽度，默认 `1200`；子列超过 14 列建议 `1400–1600`。高度自动计算 |
| `timeline` | 二选一 | 按日期自动生成时间表头（与 `periods` 二选一） |
| `periods` | 二选一 | 手动指定一级/二级时间表头，支持自定义非日历刻度（如 Sprint、第1~8周） |
| `tasks` | 二选一 | 单阶段扁平任务列表（与 `groups` 二选一） |
| `groups` | 二选一 | 多阶段分组列表，每组含 `title`（左侧竖排阶段名）、可选 `fill` 与 `tasks` |
| `showRowLines` | 否 | 是否显示网格内淡灰色水平行分隔线，默认 `false`（保持参考图纯白网格质感） |
| `today` | 否 | 今日竖向虚线标记（`"YYYY-MM-DD"` 或数字列索引） |
| `markers` | 否 | 自定义竖向标记线数组：`[{"at": "2024-04-01", "label": "提测日", "color": "red"}]` |
| `legend` | 否 | 底部居中图例：`[{"color": "primary", "label": "常规任务"}]` |
| `connections` | 否 | 可选任务依赖连线（通过 bar 的 `id` 引用，慎用，避免遮挡进度条） |

### 时间轴配置（`timeline` 与 `periods`）

**方式 A：自动日期表头（推荐）**
```json
"timeline": { "start": "2024-02-01", "end": "2024-04-30", "unit": "month-week" }
```
`unit` 可选值：
- `month-week`（默认）：一级为 `YYYY年M月`，二级为 `第一周 / 第二周 / 第三周 / 第四周`（可通过 `weekLabels` 自定义）
- `quarter-month`：一级为 `YYYY年Q1`，二级为 `1月 / 2月 / 3月`（适合半年到全年规划）
- `week-day`：一级为每周范围（或设 `"weekTitle": "number"` 显示 `第1周`），二级为每天日期（可设 `"showWeekday": true` 显示星期）
- `day`：一级为 `YYYY年M月`，二级为日期数字 `1..31`（适合 1–3 周短期冲刺）

**方式 B：自定义表头（适合无具体日期或按阶段/周次排期）**
```json
"periods": [
  { "label": "第一阶段", "subs": ["W1", "W2", "W3", "W4"] },
  { "label": "第二阶段", "subs": ["W5", "W6", "W7", "W8"] }
]
```
- 使用 `periods` 且未给 period 配置 `start`/`end` 日期时，任务条的 `start` / `end` 填**数字列索引**（从 `0` 开始，`0` 到 `2` 表示横跨第 1、2 个子列）。
- 若同时给 period 配置了 `start`/`end` 日期，则任务条既可填 `"YYYY-MM-DD"` 也可填数字列索引。

### 任务与进度条（`tasks[]` / `bars[]`）

- 单条任务可直接把 `start`、`end`、`label`、`color`、`progress` 写在 task 对象上。
- 同行有多个任务条或里程碑时，使用 `bars: [...]` 数组。
- **自动文案**：使用日期且省略 `label` 时，自动生成 `"2月1日~2月14日"`；若胶囊条较短，自动降级为紧凑格式 `"4/18~4/23"`；仍放不下时自动外置到条外空白侧，不会与同行其他进度条重叠。
- **里程碑**：`{"type": "milestone", "at": "2026-06-28", "label": "正式验收", "color": "critical"}`，默认使用 `critical` 红色菱形；若紧贴右边缘与左侧进度条，行高自动增高并将文字置于菱形下方。
- **进度条颜色（`color`）**：
  - 主题语义色：`primary`（默认）、`accent1`（别名 `pink`/`coral`）、`accent2`（别名 `green`）、`accent3`（别名 `navy`/`blue`）、`critical`（别名 `red`/`milestone`）
  - 通用扩展色：`orange`、`purple`、`gray`，或任意 `#RRGGBB` 色值

---

## 甘特图专属自检

在完成 `references/style-guide.md` 通用自检外，额外确认：

- [ ] 时间粒度合适：子列总数建议控制在 **6–18 列**；跨度超过 4 个月优先用 `quarter-month`，1–4 个月用 `month-week`，2–4 周用 `week-day` 或 `day`
- [ ] 一级表头、二级虚线格与下方网格竖线完全对齐
- [ ] 所有进度条、里程碑文字清晰可读，没有相互压盖或超出右边框
- [ ] 同类角色的进度条配色语义一致（如关键上线节点统一用 `red` / `critical`）
