# 原型交互配方

只定义「原型层交互」，不定义复杂业务引擎。所有基础交互（导航、抽屉、弹窗、Toast）的参考实现见 `assets/prototype-template.html`，此处只描述行为和组合模式。

## 一级交互（每个原型必备）

### 导航切换
适用：左侧导航、顶部导航、底部 Tab。
反馈：切换主视图，高亮当前导航项。
实现：复用模板中的 `navigate(route)` 方法 + `hashchange` 监听。

### Tab 切换
适用：详情页内部信息分区。
反馈：内容区域切换，保持页面上下文。
实现：切换 `.tab` 的 active 状态，显示/隐藏对应 `.tab-panel`。

### 筛选刷新
适用：列表页、看板页。
反馈：短暂 loading 动画 + 列表刷新。
实现：根据筛选值控制 `.list-item` 或 `<tr>` 的显示/隐藏。

## 二级交互（详情和操作）

### 打开详情抽屉
适用：从列表快速查看详情。
反馈：右侧滑入抽屉，保留原列表位置。
实现：复用模板中的 `openDrawer(title, content)` / `closeDrawer()`。

### 打开弹窗
适用：新建/编辑表单、二次确认、轻量操作。
反馈：居中弹窗 + 蒙层，带缩放入场动画。
实现：复用模板中的 `openModal(title, content)` / `closeModal()`。

### 二次确认弹窗
适用：删除、停用、关闭等危险动作。
反馈：弹窗正文展示风险说明，确认按钮使用危险色。
实现：在 `openModal` 基础上，将确认按钮样式改为 `.btn-danger`。

## 三级交互（反馈和跳转）

### 提交后局部刷新
适用：表单提交、状态处理。
反馈：关闭弹窗/抽屉 → Toast 成功提示 → 局部刷新相关区域。

### 卡片跳详情页
适用：总览页或看板页。
反馈：点击统计卡片，通过 `navigate()` 跳转到对应列表/详情页。

### 查看历史记录
适用：详情页或抽屉。
反馈：切换 Tab 或展开折叠区显示操作记录。

## 四级交互（微反馈）

### Toast 通知
反馈：右上角滑入提示条，自动消失。
类型：success（绿）、error（红）、info（蓝）、warning（琥珀）。
实现：复用模板中的 `showToast(message, type)`。

### Skeleton Loading
反馈：内容加载前显示骨架屏占位。
实现：使用 `.skeleton-line` + shimmer 动画，内容就绪后替换。

```css
.skeleton-line {
  background: linear-gradient(90deg, var(--bg-tertiary) 25%, var(--bg-hover) 50%, var(--bg-tertiary) 75%);
  background-size: 200% 100%;
  border-radius: 4px;
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
```

## 交互组合模式

### 列表页标准组合
筛选刷新 + 行点击打开抽屉 + 行内快捷操作按钮 + 新建弹窗

### 总览页标准组合
卡片跳转列表 + 筛选联动 + 指标卡刷新

### 详情层标准组合
Tab 切换 + 编辑弹窗 + 状态变更 Toast + 历史记录折叠

## 首轮原型不建议加入

- 拖拽排序
- 复杂画布交互
- 多人实时协同
- 深层审批引擎
- 条件编排器

首轮要把主路径讲清楚，不是把高级能力硬塞进去。
