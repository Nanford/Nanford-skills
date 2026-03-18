# 设计系统详细规范

本文档包含 ZENITH PPTX 演示文稿的完整设计规范。支持 6 种主题配色方案，通过 `data-theme` 属性切换。

## 主题配色方案

所有主题共用相同的 CSS 变量名，通过 `[data-theme]` 选择器切换值。

### 主题 1：赛博暗夜 `cyber-dark` (默认)

深色背景 + 赛博风强调色。适用科技发布、产品 Demo、技术分享。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#0D1117` | 幻灯片背景 |
| `--bg-card` | `#161B22` | 卡片/容器背景 |
| `--bg-card-hover` | `#1C2333` | 卡片悬停时背景 |
| `--border` | `#30363D` | 卡片边框、分割线 |
| `--border-light` | `#484F58` | 高亮边框 |
| `--accent-primary` | `#33A0FF` | 主强调：标题、按钮 |
| `--accent-secondary` | `#F78166` | 辅助强调：数据、警告 |
| `--accent-tertiary` | `#A371F7` | 第三强调：创意、技术 |
| `--accent-success` | `#3FB950` | 正向指标 |
| `--text-main` | `#E6EDF3` | 主要文字 |
| `--text-sub` | `#8B949E` | 次要文字 |
| `--text-weak` | `#6E7681` | 弱化文字 |
| `--glow-primary` | `rgba(51, 160, 255, 0.10)` | 主色光晕 |
| `--glow-secondary` | `rgba(247, 129, 102, 0.08)` | 辅助光晕 |
| `--glow-tertiary` | `rgba(163, 113, 247, 0.08)` | 第三光晕 |

---

### 主题 2：科技蓝 `tech-blue`

深蓝渐变背景 + 冰蓝强调。适用技术方案、架构评审、IT 汇报。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#0A1628` | 深蓝背景 |
| `--bg-card` | `#0F2240` | 卡片背景 |
| `--bg-card-hover` | `#142D54` | 卡片悬停 |
| `--border` | `#1B3A5C` | 边框 |
| `--border-light` | `#2A5080` | 高亮边框 |
| `--accent-primary` | `#4FC3F7` | 冰蓝主强调 |
| `--accent-secondary` | `#00E5FF` | 青色辅助 |
| `--accent-tertiary` | `#7C4DFF` | 靛蓝第三 |
| `--accent-success` | `#69F0AE` | 薄荷绿 |
| `--text-main` | `#E3F2FD` | 冰白文字 |
| `--text-sub` | `#90CAF9` | 淡蓝文字 |
| `--text-weak` | `#5C8DB8` | 弱化文字 |
| `--glow-primary` | `rgba(79, 195, 247, 0.12)` | 冰蓝光晕 |
| `--glow-secondary` | `rgba(0, 229, 255, 0.08)` | 青色光晕 |
| `--glow-tertiary` | `rgba(124, 77, 255, 0.08)` | 靛蓝光晕 |

---

### 主题 3：简洁汇报 `clean-report`

浅灰白背景 + 商务蓝强调。适用工作汇报、季度总结、项目进展。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#F5F7FA` | 浅灰白背景 |
| `--bg-card` | `#FFFFFF` | 白色卡片 |
| `--bg-card-hover` | `#F0F4F8` | 卡片悬停 |
| `--border` | `#E2E8F0` | 浅灰边框 |
| `--border-light` | `#CBD5E1` | 高亮边框 |
| `--accent-primary` | `#2563EB` | 商务蓝 |
| `--accent-secondary` | `#F59E0B` | 琥珀色 |
| `--accent-tertiary` | `#8B5CF6` | 紫罗兰 |
| `--accent-success` | `#10B981` | 翠绿 |
| `--text-main` | `#1E293B` | 深灰文字 |
| `--text-sub` | `#64748B` | 中灰文字 |
| `--text-weak` | `#94A3B8` | 浅灰文字 |
| `--glow-primary` | `rgba(37, 99, 235, 0.06)` | 蓝色光晕 |
| `--glow-secondary` | `rgba(245, 158, 11, 0.05)` | 琥珀光晕 |
| `--glow-tertiary` | `rgba(139, 92, 246, 0.05)` | 紫色光晕 |

---

### 主题 4：暖光办公 `warm-office`

暖白背景 + 暖色调强调。适用日常办公、培训材料、内部分享。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#FAF8F5` | 暖白背景 |
| `--bg-card` | `#FFFFFF` | 白色卡片 |
| `--bg-card-hover` | `#F5F0EB` | 卡片悬停 |
| `--border` | `#E8E0D8` | 暖灰边框 |
| `--border-light` | `#D4C8BC` | 高亮边框 |
| `--accent-primary` | `#D97706` | 琥珀主色 |
| `--accent-secondary` | `#DC2626` | 红棕辅助 |
| `--accent-tertiary` | `#9333EA` | 紫色第三 |
| `--accent-success` | `#16A34A` | 森林绿 |
| `--text-main` | `#292524` | 深棕文字 |
| `--text-sub` | `#78716C` | 暖灰文字 |
| `--text-weak` | `#A8A29E` | 浅暖灰 |
| `--glow-primary` | `rgba(217, 119, 6, 0.06)` | 琥珀光晕 |
| `--glow-secondary` | `rgba(220, 38, 38, 0.05)` | 红色光晕 |
| `--glow-tertiary` | `rgba(147, 51, 234, 0.05)` | 紫色光晕 |

---

### 主题 5：软件公司 `software-pro`

纯白背景 + 紫蓝渐变强调。适用商业提案、客户演示、对外展示。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#FFFFFF` | 纯白背景 |
| `--bg-card` | `#F8FAFC` | 极浅灰卡片 |
| `--bg-card-hover` | `#F1F5F9` | 卡片悬停 |
| `--border` | `#E2E8F0` | 浅灰边框 |
| `--border-light` | `#CBD5E1` | 高亮边框 |
| `--accent-primary` | `#6366F1` | 靛蓝紫主色 |
| `--accent-secondary` | `#EC4899` | 粉色辅助 |
| `--accent-tertiary` | `#06B6D4` | 青色第三 |
| `--accent-success` | `#22C55E` | 亮绿 |
| `--text-main` | `#0F172A` | 墨色文字 |
| `--text-sub` | `#475569` | 深灰文字 |
| `--text-weak` | `#94A3B8` | 浅灰文字 |
| `--glow-primary` | `rgba(99, 102, 241, 0.08)` | 靛蓝光晕 |
| `--glow-secondary` | `rgba(236, 72, 153, 0.06)` | 粉色光晕 |
| `--glow-tertiary` | `rgba(6, 182, 212, 0.06)` | 青色光晕 |

---

### 主题 6：极简白 `minimal-light`

纯白极简 + 黑色/单色强调。适用学术汇报、简约风格、设计评审。

| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--bg-main` | `#FAFAFA` | 纯白背景 |
| `--bg-card` | `#FFFFFF` | 白色卡片 |
| `--bg-card-hover` | `#F5F5F5` | 卡片悬停 |
| `--border` | `#E5E5E5` | 浅灰边框 |
| `--border-light` | `#D4D4D4` | 高亮边框 |
| `--accent-primary` | `#171717` | 黑色主强调 |
| `--accent-secondary` | `#525252` | 深灰辅助 |
| `--accent-tertiary` | `#737373` | 中灰第三 |
| `--accent-success` | `#16A34A` | 绿色 |
| `--text-main` | `#171717` | 黑色文字 |
| `--text-sub` | `#525252` | 深灰文字 |
| `--text-weak` | `#A3A3A3` | 浅灰文字 |
| `--glow-primary` | `rgba(23, 23, 23, 0.04)` | 灰色光晕 |
| `--glow-secondary` | `rgba(82, 82, 82, 0.03)` | 浅灰光晕 |
| `--glow-tertiary` | `rgba(115, 115, 115, 0.03)` | 极浅光晕 |

---

## 变量名统一映射

旧变量名已统一为语义化命名，确保主题切换兼容：

| 新变量名 | 对应旧变量名 (cyber-dark) |
|----------|--------------------------|
| `--accent-primary` | `--accent-blue` (#33A0FF) |
| `--accent-secondary` | `--accent-orange` (#F78166) |
| `--accent-tertiary` | `--accent-purple` (#A371F7) |
| `--accent-success` | `--accent-green` (#3FB950) |

模板中同时保留旧变量名作为别名，确保向后兼容。

## 字体规范

### 字体栈

```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
```

### 字号层级

| 级别 | 字号 | 字重 | 用途 |
|------|------|------|------|
| Hero 标题 | 3.5rem (56px) | 800 | 封面主标题 |
| 大标题 | 2.5rem (40px) | 700 | 幻灯片标题 |
| 中标题 | 1.5rem (24px) | 600 | 卡片标题 |
| 正文 | 1.125rem (18px) | 400 | 内容正文 |
| 说明 | 0.9rem (14px) | 400 | 辅助说明 |
| 大数据 | 4rem (64px) | 800 | 数据数字展示 |
| 中数据 | 2.5rem (40px) | 700 | 次要数据 |

## 布局系统

### 幻灯片容器

```css
.slide {
  width: 100vw;
  height: 100vh;
  background: var(--bg-main);
  padding: 60px 80px;
  display: grid;
  position: relative;
  overflow: hidden;
}
```

### Bento Grid 常用布局

**左右分栏 (内容型):**
```css
.slide-content .grid {
  display: grid;
  grid-template-columns: 2fr 3fr;
  gap: 24px;
  align-items: start;
}
```

**三列数据卡片:**
```css
.slide-data .grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}
```

**非对称 Bento (推荐):**
```css
.bento-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: auto auto;
  gap: 24px;
}
/* Hero 区域跨 2 列 2 行 */
.bento-hero { grid-column: span 2; grid-row: span 2; }
/* 数据卡片跨 1 列 */
.bento-data { grid-column: span 1; }
/* 宽卡片跨 2 列 */
.bento-wide { grid-column: span 2; }
```

### 间距系统

| 用途 | 值 |
|------|-----|
| 幻灯片内边距 | 60px 80px |
| 卡片间距 (gap) | 24px |
| 卡片内边距 | 32px |
| 元素间距 | 16px |
| 圆角 | 16px |

## 卡片样式

### 标准卡片

```css
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 32px;
  position: relative;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}
```

### 玻璃拟态卡片

```css
.card-glass {
  background: rgba(22, 27, 34, 0.7);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(48, 54, 61, 0.5);
  border-radius: 16px;
  padding: 32px;
}
```

## 几何装饰元素

### 圆形光晕

```css
.glow-blue::before {
  content: '';
  position: absolute;
  width: 400px; height: 400px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(51,160,255,0.12) 0%, transparent 70%);
  top: -100px; right: -100px;
  pointer-events: none;
}
```

### 线条装饰

```css
.accent-line {
  width: 80px;
  height: 4px;
  background: var(--accent-blue);
  border-radius: 2px;
  margin: 16px 0;
}
```

### 角落几何

```css
.corner-dot::after {
  content: '';
  position: absolute;
  width: 12px; height: 12px;
  border-radius: 50%;
  background: var(--accent-orange);
  bottom: 24px; left: 24px;
}
```

## 动画

### 幻灯片进入动画

```css
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(30px); }
  to { opacity: 1; transform: translateY(0); }
}

.slide.active .animate-in {
  animation: fadeInUp 0.6s ease forwards;
}

/* 依次延迟 */
.slide.active .animate-in:nth-child(1) { animation-delay: 0.1s; }
.slide.active .animate-in:nth-child(2) { animation-delay: 0.2s; }
.slide.active .animate-in:nth-child(3) { animation-delay: 0.3s; }
```

### 幻灯片切换

```css
.slide {
  opacity: 0;
  transition: opacity 0.5s ease;
  position: absolute;
  inset: 0;
}
.slide.active {
  opacity: 1;
  z-index: 1;
}
```

## 主题选择决策指南

| 场景 | 推荐主题 | 理由 |
|------|----------|------|
| 科技产品发布会 | `cyber-dark` | 赛博风格视觉冲击力强 |
| 技术架构方案评审 | `tech-blue` | 专业冷色调，聚焦技术内容 |
| 季度工作汇报 | `clean-report` | 简洁专业，领导友好 |
| 团队内部培训 | `warm-office` | 暖色调轻松不紧张 |
| 客户商务提案 | `software-pro` | 紫蓝渐变现代感强，专业可信 |
| 学术答辩/设计评审 | `minimal-light` | 极简不分散注意力 |
| 开源项目介绍 | `cyber-dark` | 开发者群体偏好深色 |
| 融资路演 | `software-pro` | 商务感+科技感兼备 |
| 年度总结大会 | `clean-report` | 正式场合简洁大方 |
| 新人入职培训 | `warm-office` | 亲和力强，易于接受 |

## 浅色主题装饰调整

浅色主题 (`clean-report`, `warm-office`, `software-pro`, `minimal-light`) 的装饰元素需要调整：

- 光晕透明度从 0.08-0.12 **降低到** 0.04-0.06，避免过于突兀
- 卡片阴影使用 `box-shadow` 代替边框高亮：`0 1px 3px rgba(0,0,0,0.08)`
- 进度条和按钮使用 `--accent-primary` 保持一致
- `.corner-dot` 装饰使用 `--accent-secondary` 而非固定橙色
