# 渲染指令模板

用以下模板生成渲染指令，交给 `frontend-design` skill 配合执行。

## 渲染指令格式

```
请基于下面的产品原型规格，设计并实现一个可交互的单文件 HTML 原型。

## 产品信息
- 产品类型：{product_type}
- 输入来源：{input_source_type}
- 导航模型：{navigation_model}
- 响应策略：{responsive_strategy}
- 目标用户：{target_users}
- 核心目标：{core_goals}

## 设计预设
- 预设方案：{design_preset}
- 主题风格：{theme}
- 信息密度：{density}
- CSS 变量：参考 references/design-presets.md 中对应预设的完整变量定义

## 首批渲染页面
{priority_pages}

## 各页面设计说明
{page_briefs}

## 技术要求
1. 输出单文件 HTML（包含所有 CSS 和 JS）
2. 使用 Hash 路由实现多页面导航
3. 基于 assets/prototype-template.html 骨架结构
4. 不依赖任何外部 JS/CSS 库（Google Fonts 除外）
5. 页面结构忠实于给定规格，视觉可优化但不可改写业务结构

## 交互边界
1. 仅实现原型层交互（参考 references/interaction-recipes.md）
2. 导航切换 + Tab 切换
3. 弹窗/抽屉打开关闭（含动画）
4. 筛选后列表刷新
5. Toast 通知反馈
6. 所有关键模块使用合理 mock data

## 视觉要求
1. 调用 frontend-design skill 确保视觉质量
2. 避免 AI 感（避免 Inter 字体、紫色渐变白底、过度对称）
3. 有明确美学方向和设计意图
4. 微动画和 hover 效果
```

## 分步渲染指令

当页面较多时，分步渲染：

**第一步**：渲染 P0 页面（通常是总览页 + 核心列表页）
```
先渲染以下 P0 页面，建立整体骨架和导航结构：
- {page_1}
- {page_2}
包含完整的侧边栏导航（所有页面入口）和 Hash 路由框架。
```

**第二步**：渲染 P1 页面（详情层、次要列表页）
```
在现有 HTML 基础上，增加以下 P1 页面：
- {page_3}
- {page_4}
保持已有页面不变，仅新增页面内容和对应路由。
```

**第三步**：完善交互和细节
```
在现有 HTML 基础上，完善以下交互细节：
- 补全弹窗/抽屉内容
- 完善 mock data
- 添加 Toast 反馈
- 补全空状态/loading 状态
```
