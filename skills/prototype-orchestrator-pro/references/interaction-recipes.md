# 原型交互配方

只定义「原型层交互」，不定义复杂业务引擎。每个配方附带可直接复用的 HTML/CSS/JS 片段。

## 一级交互（每个原型必备）

### 导航切换

适用：左侧导航、顶部导航、底部 Tab。
反馈：切换主视图，高亮当前导航。

```html
<!-- 侧边栏导航切换 -->
<nav class="sidebar">
  <a href="#/dashboard" class="nav-item active" onclick="navigate('dashboard')">总览</a>
  <a href="#/tasks" class="nav-item" onclick="navigate('tasks')">任务</a>
</nav>
<script>
function navigate(page) {
  document.querySelectorAll('.page').forEach(p => p.style.display = 'none');
  document.getElementById('page-' + page).style.display = 'block';
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  event.target.classList.add('active');
}
window.addEventListener('hashchange', () => {
  const page = location.hash.slice(2) || 'dashboard';
  navigate(page);
});
</script>
```

### Tab 切换

适用：详情页内部信息分区。
反馈：内容区域切换，保持页面上下文。

```html
<div class="tabs">
  <button class="tab active" onclick="switchTab(this, 'info')">基本信息</button>
  <button class="tab" onclick="switchTab(this, 'history')">操作记录</button>
</div>
<div id="tab-info" class="tab-panel active">...</div>
<div id="tab-history" class="tab-panel" style="display:none">...</div>
<script>
function switchTab(btn, id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => { p.style.display = 'none'; p.classList.remove('active'); });
  btn.classList.add('active');
  const panel = document.getElementById('tab-' + id);
  panel.style.display = 'block';
  panel.classList.add('active');
}
</script>
```

### 筛选刷新

适用：列表页、看板页。
反馈：短暂 loading 动画 + 列表刷新。

```html
<div class="filter-bar">
  <select onchange="filterList(this.value)">
    <option value="all">全部状态</option>
    <option value="pending">待处理</option>
    <option value="done">已完成</option>
  </select>
</div>
<script>
function filterList(status) {
  const rows = document.querySelectorAll('.list-item');
  rows.forEach(row => {
    row.style.display = (status === 'all' || row.dataset.status === status) ? '' : 'none';
  });
}
</script>
```

## 二级交互（详情和操作）

### 打开详情抽屉

适用：从列表快速查看详情。
反馈：右侧滑入抽屉，保留原列表位置。

```html
<div id="drawer" class="drawer">
  <div class="drawer-header">
    <h3 class="drawer-title">详情</h3>
    <button onclick="closeDrawer()" class="drawer-close">&times;</button>
  </div>
  <div class="drawer-body"><!-- 内容 --></div>
</div>
<div id="drawer-overlay" class="drawer-overlay" onclick="closeDrawer()"></div>
<style>
.drawer { position: fixed; right: -480px; top: 0; width: 480px; height: 100vh; background: var(--bg-surface); box-shadow: -4px 0 24px rgba(0,0,0,.12); transition: right .3s ease; z-index: 1001; }
.drawer.open { right: 0; }
.drawer-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.3); z-index: 1000; }
.drawer-overlay.open { display: block; }
</style>
<script>
function openDrawer(title, content) {
  document.querySelector('.drawer-title').textContent = title;
  document.querySelector('.drawer-body').innerHTML = content;
  document.getElementById('drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
}
function closeDrawer() {
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('drawer-overlay').classList.remove('open');
}
</script>
```

### 打开弹窗

适用：新建/编辑表单、二次确认、轻量操作。
反馈：居中弹窗 + 蒙层。

```html
<div id="modal" class="modal-overlay" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-header">
      <h3 class="modal-title">标题</h3>
      <button onclick="closeModal()" class="modal-close">&times;</button>
    </div>
    <div class="modal-body"><!-- 内容 --></div>
    <div class="modal-footer">
      <button onclick="closeModal()" class="btn btn-secondary">取消</button>
      <button onclick="handleSubmit()" class="btn btn-primary">确认</button>
    </div>
  </div>
</div>
<style>
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 1000; align-items: center; justify-content: center; }
.modal-overlay.open { display: flex; }
.modal { background: var(--bg-surface); border-radius: 12px; width: 520px; max-height: 80vh; overflow: auto; box-shadow: 0 20px 60px rgba(0,0,0,.2); animation: modalIn .2s ease; }
@keyframes modalIn { from { opacity: 0; transform: scale(.95) translateY(10px); } to { opacity: 1; transform: scale(1) translateY(0); } }
</style>
<script>
function openModal(title, content) {
  document.querySelector('.modal-title').textContent = title;
  document.querySelector('.modal-body').innerHTML = content;
  document.getElementById('modal').classList.add('open');
}
function closeModal() { document.getElementById('modal').classList.remove('open'); }
</script>
```

### 二次确认弹窗

适用：删除、停用、关闭等危险动作。

```javascript
function confirmAction(message, onConfirm) {
  openModal('确认操作', `
    <p style="color:var(--text-secondary);margin:16px 0">${message}</p>
  `);
  document.querySelector('.modal-footer .btn-primary').onclick = () => { onConfirm(); closeModal(); };
  document.querySelector('.modal-footer .btn-primary').classList.add('btn-danger');
}
```

## 三级交互（反馈和跳转）

### 提交后局部刷新

适用：表单提交、状态处理。
反馈：Toast 成功提示 + 局部刷新。

```javascript
function handleSubmit() {
  closeModal();
  showToast('操作成功', 'success');
  // 模拟刷新列表
  setTimeout(() => location.reload(), 500);
}
```

### 卡片跳详情页

适用：总览页或看板页。
反馈：跳转并带上下文。

```html
<div class="stat-card" onclick="navigate('tasks')" style="cursor:pointer">
  <div class="stat-value">128</div>
  <div class="stat-label">在途任务</div>
</div>
```

### 查看历史记录

适用：详情页或抽屉。
反馈：切换 Tab 或展开折叠区。

## 四级交互（微反馈）

### Toast 通知

```html
<div id="toast-container" style="position:fixed;top:24px;right:24px;z-index:9999"></div>
<script>
function showToast(msg, type = 'info') {
  const colors = { success: '#10b981', error: '#ef4444', info: '#3b82f6', warning: '#f59e0b' };
  const toast = document.createElement('div');
  toast.style.cssText = `padding:12px 24px;border-radius:8px;color:#fff;background:${colors[type]};margin-bottom:8px;animation:slideIn .3s ease;box-shadow:0 4px 12px rgba(0,0,0,.15);font-size:14px`;
  toast.textContent = msg;
  document.getElementById('toast-container').appendChild(toast);
  setTimeout(() => { toast.style.animation = 'fadeOut .3s ease'; setTimeout(() => toast.remove(), 300); }, 3000);
}
</script>
<style>
@keyframes slideIn { from { opacity: 0; transform: translateX(100%); } to { opacity: 1; transform: translateX(0); } }
@keyframes fadeOut { to { opacity: 0; transform: translateY(-10px); } }
</style>
```

### Skeleton Loading

```html
<div class="skeleton-card">
  <div class="skeleton-line" style="width:60%;height:20px"></div>
  <div class="skeleton-line" style="width:100%;height:14px;margin-top:12px"></div>
  <div class="skeleton-line" style="width:80%;height:14px;margin-top:8px"></div>
</div>
<style>
.skeleton-line { background: linear-gradient(90deg, var(--bg-tertiary) 25%, var(--bg-hover) 50%, var(--bg-tertiary) 75%); background-size: 200% 100%; border-radius: 4px; animation: shimmer 1.5s infinite; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
</style>
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
