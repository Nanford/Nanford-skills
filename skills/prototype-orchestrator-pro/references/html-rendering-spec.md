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
- 未实现的功能点击后用 Toast 提示"功能开发中"，不要在界面上预先标注说明文字。

## 发布级视觉标准

输出的原型必须看起来像一个真实可用的产品，而不是带批注的线框图：

- **禁止在界面上显示任何规格注释**：页面目标、组件说明、交互描述、字段用途等规格信息只用于指导渲染，绝不能作为可见文字出现在 UI 上。
- **禁止在按钮、卡片、菜单项旁添加功能解释**：按钮只显示动作文案（如"新建""导出""删除"），不要在旁边或下方加"点击此按钮可以……"之类的说明。
- **禁止在页面区域添加用途标注**：不要出现"此区域用于展示……""这里显示……"之类的描述性文字。
- **所有文案都应该是产品级文案**：标题、按钮、提示、空状态文案都应该像真实产品一样简洁自然，不带教学或解释口吻。
- **Mock data 要像真实数据**：用户名、订单号、日期等都要有真实感，不要用"示例数据""测试用户"等暴露原型身份的文案。
