# HTML 原型渲染规范

把页面方案落成可直接打开的单文件 HTML。保持结构清晰、交互克制、样式可替换。

## 输出形式

- 只输出 1 个 `.html` 文件。
- 内联所有 CSS 和 JS。
- 允许 Google Fonts；不要依赖其他外部 JS 或 CSS 库。
- 使用 `<!doctype html>`、UTF-8 和移动端 viewport。

## 文档骨架

优先沿用 `assets/prototype-template.html` 的结构：

```html
<body>
  <div class="app-shell">
    <aside class="sidebar"></aside>
    <div class="workspace">
      <header class="topbar"></header>
      <main class="page-stage">
        <section class="page" data-page="overview"></section>
      </main>
    </div>
  </div>

  <div id="drawer-root"></div>
  <div id="modal-root"></div>
  <div id="toast-root"></div>
</body>
```

没有侧边栏时，保留 `app-shell` 和 `workspace`，让主内容全宽展开。

## 路由规范

- 使用 Hash 路由：`#/page-id`。
- `page-id` 直接来自 ProductSpec 的 `page_id`。
- 每个路由只对应一个 `.page` 容器。
- 默认路由指向首个 P0 页面。
- 导航、卡片跳转、按钮跳转都复用同一个 `navigate(pageId)` 方法。

## 页面最低结构

每个页面至少包含：
- 页面标题或摘要区
- 一个主内容区
- 一个主操作入口
- 一组真实语义的 mock data
- 4 类状态：`loading`、`empty`、`error`、`no_permission`

不要只渲染漂亮卡片而缺动作和状态。

## 交互边界

只实现原型层交互：
- 导航切换
- Tab 切换
- 筛选刷新
- 抽屉打开关闭
- 弹窗打开关闭
- Toast 反馈

不要实现：
- 复杂拖拽
- 多人实时协同
- 真正的鉴权和后端请求
- 深层审批引擎

## 布局要求

- PC 后台优先采用左侧导航或顶部操作栏。
- 移动端工具优先采用底部 Tab 和单手可达按钮。
- 大屏优先使用无滚动或弱滚动的整屏区块。
- 页面之间保持统一的栅格、间距、圆角和阴影体系。

## 视觉要求

- 从 `references/design-presets.md` 选择对应预设并注入 CSS 变量。
- 让中性色承担主体面积，让主色承担方向性。
- 禁用通用 AI 风格：Inter、紫色白底、平均分配多色、过度对称。
- 用少量但明确的动画增强层级，不要堆砌动效。

## Mock Data 要求

- 使用与行业一致的字段名和量级。
- 演示型页面优先使用写实型或行业型 mock data。
- 不要出现 `lorem ipsum`、`item 1` 这类低质量占位。

## 交付要求

- 结果能直接在浏览器打开。
- 关键交互首次点击就能看到反馈。
- 未实现的能力用文案说明，不要做成死按钮。
