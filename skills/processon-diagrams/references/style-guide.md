# ProcessOn 共用视觉与工程规范

本规范适用于 `processon-diagrams` 下的所有图种（分层架构图，以及后续扩展的甘特图、泳道图、流程图等）。

---

## 视觉规范

| 元素 | 规范 |
|------|------|
| 描边 | 全图统一使用主题 `stroke` 色，**1px** 细线；不用纯黑，不用 2px 粗边框 |
| 填充 | 低饱和浅色块，按**角色**取色（同一角色全图同色），不用花哨渐变 |
| 圆角 | 标题、横幅、卡片、容器为直角（rx=0）；标签栏与支撑栏 rx=4；卡片内节点 rx=6；面板内节点 rx=2–6 |
| 字号 | 标题 18px；标签与支撑栏 15px；卡片/分区表头 15px 加粗；节点 14px；流程步骤 13px；连线标注 12px |
| 字体 | `'PingFang SC','Microsoft YaHei','Hiragino Sans GB','Noto Sans CJK SC','Source Han Sans SC',-apple-system,'Segoe UI',Arial,sans-serif`（中文字体必须靠前） |
| 竖排文字 | 每个字单独一个 `<tspan>` 逐字下移；禁止用 `writing-mode`（部分编辑器与转换器不支持） |
| 箭头 | 使用几何拼接 `<polygon>`，**尖端位于原点 `(0, 0)`**，通过 `translate(x, y) rotate(angle)` 定位；**禁止 `<marker>` 与 `marker-end`**，确保导入 PPT、Word、公众号编辑器时箭头不丢 |
| 文本换行 | 中文按 `1 × 字号`、大写字母/数字按 `0.64 × 字号`、小写按 `0.52 × 字号` 估算宽度；超过「节点宽 − 16」自动换行，节点高度随行数撑开（每行 `1.35 × 字号`，另加上下各 8px） |
| 装饰 | 不加阴影滤镜、渐变、3D 效果或卡通插画 |

## 通用自检清单

查看渲染出的 PNG 预览，逐项核对：

- [ ] 用户描述里的核心要素都在图上，没有遗漏或臆造
- [ ] 没有文字溢出边框、相互重叠或被截断（出现 `…` 说明文案过长，应精简文案、调宽 `canvas.w` 或调整列数）
- [ ] 各分区边界、标签栏、支撑栏上下/左右对齐
- [ ] 连线没有穿过无关节点，连线标注不遮挡节点文字
- [ ] 整体疏密均匀，没有大块尴尬留白或过度拥挤的区域

## 禁止项

- 不要省略用户描述中的关键信息
- 不要引用外部资源（网络图片、Web 字体、外部 CSS）
- 不要使用 `<marker>` 箭头、`<filter>` 阴影或 `<linearGradient>`
- 不要输出残缺、无法直接渲染的 SVG
- 不要用 Mermaid 或纯文字替代 SVG（除非用户明确要求）
- 不要绕开脚本手调 SVG 坐标（仅当环境无法运行 Python 时按规范手写）

## 扩展新图种的标准做法

未来新增图种（如 `gantt`、`swimlane`、`flowchart`）时，保持以下 4 步：

1. 在 `scripts/diagrams/<type>.py` 新增子类，继承 `core.BaseDiagram`，复用配色、文本换行、图元、箭头与 PNG 导出
2. 在 `scripts/diagrams/__init__.py` 的 `REGISTRY` 中注册图种名
3. 在 `references/<type>.md` 编写该图种的 JSON Schema、布局规则与注意事项（若需新角色色，同步补充到 `references/color-themes.md`）
4. 在 `examples/` 放一组 `<example>.json` + `<example>.svg`，并在 `SKILL.md` 的图种路由表里加一行
