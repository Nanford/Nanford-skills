# 设计预设

按业务方向选择一种清晰、克制、可落地的配色体系。目标不是“好看一点”，而是让原型在 30 秒内建立正确行业气质。

## 配色方法

1. 用中性色承担 70% 以上面积：背景、面板、边框先稳定，再谈品牌感。
2. 用主色承担方向性：主按钮、激活导航、核心指标、关键链接。
3. 用强调色制造记忆点：只用于告警、重点标签、局部图表，不要和主色平分视觉权重。
4. 控制饱和度：大面积区域用低饱和，只有交互热点和关键数字允许更高对比。
5. 保持状态色统一：成功偏绿、警告偏琥珀、危险偏红、信息偏蓝。
6. 让字体和色彩同向表达：理性场景用硬朗中性字体，服务型场景用更柔和的几何字形。

## industrial-b

适用：工业、制造、仓储、设备、运营后台。  
色彩意图：钢蓝主色建立秩序感，黄铜强调色只点亮风险和效率节点，整体克制、专业、耐看。  
推荐字体：`'IBM Plex Sans', 'Noto Sans SC', sans-serif`

```css
:root {
  --primary: #2f5d8a;
  --primary-hover: #24486a;
  --primary-light: #dbe7f1;
  --accent: #c88a2d;
  --bg-main: #ebf0f4;
  --bg-surface: #ffffff;
  --bg-sidebar: #162230;
  --bg-sidebar-hover: #223345;
  --bg-hover: #f6f9fb;
  --bg-tertiary: #d8e1e8;
  --text-primary: #132232;
  --text-secondary: #516170;
  --text-tertiary: #8090a0;
  --text-sidebar: #d8e2ea;
  --border: #d7e0e8;
  --border-light: #eaf0f4;
  --success: #2f8a5b;
  --warning: #c88a2d;
  --danger: #c45548;
  --info: #2f5d8a;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --shadow-sm: 0 1px 2px rgba(12, 24, 38, 0.06);
  --shadow-md: 0 8px 20px rgba(12, 24, 38, 0.08);
  --shadow-lg: 0 20px 44px rgba(12, 24, 38, 0.12);
  --font-sans: 'IBM Plex Sans', 'Noto Sans SC', system-ui, sans-serif;
  --font-display: 'Sora', 'Noto Sans SC', sans-serif;
  --sidebar-width: 240px;
}
```

推荐特征：左侧导航 + 顶部操作栏 + 表格/卡片混合 + 中高信息密度  
配色建议：钢蓝用于主流程，黄铜只用于告警、效率标签和关键提示。

## command-center

适用：可视化大屏、监控中心、指挥中心。  
色彩意图：深海黑底提供沉浸感，冷青蓝负责信息发光，暖橙仅用于告警和异常聚焦。  
推荐字体：`'IBM Plex Sans', 'Noto Sans SC', sans-serif`

```css
:root {
  --primary: #3fa7c4;
  --primary-hover: #2f829a;
  --primary-light: rgba(63, 167, 196, 0.14);
  --accent: #e29d49;
  --bg-main: #07141c;
  --bg-surface: #10212c;
  --bg-sidebar: #09141d;
  --bg-sidebar-hover: #142736;
  --bg-hover: #183142;
  --bg-tertiary: #122736;
  --text-primary: #e7f0f4;
  --text-secondary: #a2b2bd;
  --text-tertiary: #728593;
  --text-sidebar: #d7e3ea;
  --border: #203747;
  --border-light: #2c495d;
  --success: #3cac79;
  --warning: #e29d49;
  --danger: #dc6b5b;
  --info: #48b7d7;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.28);
  --shadow-md: 0 10px 24px rgba(0, 0, 0, 0.34);
  --shadow-lg: 0 24px 48px rgba(0, 0, 0, 0.42);
  --font-sans: 'IBM Plex Sans', 'Noto Sans SC', system-ui, sans-serif;
  --font-display: 'Rajdhani', 'Noto Sans SC', sans-serif;
  --sidebar-width: 0px;
}
```

推荐特征：单页全屏 + 暗色背景 + 指标卡 + 趋势图 + 异常列表  
配色建议：亮青只给关键数字和交互热点，大面积区域坚持低亮深色。

## saas-clean

适用：标准 SaaS、商业后台、运营工具。  
色彩意图：暖白底建立高级感，深钴蓝负责品牌稳定性，辅以低占比松石绿提升现代感。  
推荐字体：`'Public Sans', 'Noto Sans SC', sans-serif`

```css
:root {
  --primary: #2557a7;
  --primary-hover: #1d4585;
  --primary-light: #e3ecfa;
  --accent: #2f8877;
  --bg-main: #f6f4ef;
  --bg-surface: #ffffff;
  --bg-sidebar: #ffffff;
  --bg-sidebar-hover: #f1f4f7;
  --bg-hover: #f7f9fb;
  --bg-tertiary: #e6ebf0;
  --text-primary: #162332;
  --text-secondary: #556372;
  --text-tertiary: #8794a2;
  --text-sidebar: #283848;
  --border: #dde5eb;
  --border-light: #edf2f5;
  --success: #2d8a64;
  --warning: #c48932;
  --danger: #c95b4d;
  --info: #2557a7;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 18px;
  --shadow-sm: 0 1px 2px rgba(17, 29, 40, 0.04);
  --shadow-md: 0 10px 24px rgba(17, 29, 40, 0.06);
  --shadow-lg: 0 22px 48px rgba(17, 29, 40, 0.1);
  --font-sans: 'Public Sans', 'Noto Sans SC', system-ui, sans-serif;
  --font-display: 'Manrope', 'Noto Sans SC', sans-serif;
  --sidebar-width: 260px;
}
```

推荐特征：暖白底 + 清晰层级 + 中密度 + 卡片和表格均衡  
配色建议：钴蓝只在主操作和导航激活态发声，绿色只做次级强调。

## mobile-tool

适用：巡检、作业、移动端业务工具。  
色彩意图：纸感暖底降低压迫，深海蓝绿保证可靠感，陶土橙用来给现场操作一个明确落点。  
推荐字体：`'Manrope', 'Noto Sans SC', sans-serif`

```css
:root {
  --primary: #14748a;
  --primary-hover: #0f5d6f;
  --primary-light: #d9edf2;
  --accent: #e07a4f;
  --bg-main: #f5f1eb;
  --bg-surface: #ffffff;
  --bg-sidebar: #ffffff;
  --bg-sidebar-hover: #f2eee7;
  --bg-hover: #f7f3ed;
  --bg-tertiary: #e7e0d5;
  --text-primary: #17242d;
  --text-secondary: #5d6a73;
  --text-tertiary: #8d98a1;
  --text-sidebar: #223039;
  --border: #ddd5ca;
  --border-light: #eee7de;
  --success: #3d8d69;
  --warning: #d18a38;
  --danger: #c85c4a;
  --info: #14748a;
  --radius-sm: 12px;
  --radius-md: 16px;
  --radius-lg: 22px;
  --shadow-sm: 0 2px 6px rgba(17, 29, 40, 0.06);
  --shadow-md: 0 10px 24px rgba(17, 29, 40, 0.08);
  --shadow-lg: 0 18px 40px rgba(17, 29, 40, 0.12);
  --font-sans: 'Manrope', 'Noto Sans SC', system-ui, sans-serif;
  --font-display: 'Manrope', 'Noto Sans SC', sans-serif;
  --sidebar-width: 0px;
}
```

推荐特征：底部 Tab + 卡片列表 + 固定主操作按钮 + 单手可操作  
配色建议：主色压住信息层级，橙色只落在主 CTA、异常提醒、步骤推进上。

## dashboard-analytics

适用：数据分析平台、BI 工具、报表系统。  
色彩意图：深墨背景承载高密度图表，理性蓝负责趋势和主操作，青绿色只作为分析层次的第二色。  
推荐字体：`'IBM Plex Sans', 'Noto Sans SC', sans-serif`

```css
:root {
  --primary: #4e79d9;
  --primary-hover: #3d61b8;
  --primary-light: rgba(78, 121, 217, 0.16);
  --accent: #17a398;
  --bg-main: #0b1320;
  --bg-surface: #121d2d;
  --bg-sidebar: #0b1320;
  --bg-sidebar-hover: #162336;
  --bg-hover: #1a2940;
  --bg-tertiary: #162235;
  --text-primary: #ebf1f7;
  --text-secondary: #a8b5c3;
  --text-tertiary: #74869a;
  --text-sidebar: #d7e2ec;
  --border: #24364c;
  --border-light: #31465f;
  --success: #35a277;
  --warning: #d69a3d;
  --danger: #d96462;
  --info: #5a96f0;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --shadow-sm: 0 2px 6px rgba(0, 0, 0, 0.2);
  --shadow-md: 0 10px 24px rgba(0, 0, 0, 0.28);
  --shadow-lg: 0 24px 48px rgba(0, 0, 0, 0.34);
  --font-sans: 'IBM Plex Sans', 'Noto Sans SC', system-ui, sans-serif;
  --font-display: 'Sora', 'Noto Sans SC', sans-serif;
  --sidebar-width: 240px;
}
```

推荐特征：深色主画布 + 图表密集 + 数据卡片 + 筛选器组合  
配色建议：蓝色负责趋势，青绿只补充分组差异，不要让图表像彩虹盘。

## crm-portal

适用：客户管理、销售工具、客户门户。  
色彩意图：深青绿色建立信任感，象牙底提升亲和度，铜棕强调色用于转化节点和时间轴重点。  
推荐字体：`'Outfit', 'Noto Sans SC', sans-serif`

```css
:root {
  --primary: #1c7b70;
  --primary-hover: #166158;
  --primary-light: #d8f0eb;
  --accent: #b97a44;
  --bg-main: #f7f3ec;
  --bg-surface: #ffffff;
  --bg-sidebar: #183b3a;
  --bg-sidebar-hover: #215150;
  --bg-hover: #f4f7f5;
  --bg-tertiary: #e4ebe6;
  --text-primary: #18262d;
  --text-secondary: #5c6a70;
  --text-tertiary: #89959a;
  --text-sidebar: #dbece8;
  --border: #d8e2dd;
  --border-light: #edf2ee;
  --success: #2d8a64;
  --warning: #c58b39;
  --danger: #c85b51;
  --info: #2f7397;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 18px;
  --shadow-sm: 0 1px 2px rgba(16, 28, 34, 0.04);
  --shadow-md: 0 10px 24px rgba(16, 28, 34, 0.06);
  --shadow-lg: 0 22px 48px rgba(16, 28, 34, 0.1);
  --font-sans: 'Outfit', 'Noto Sans SC', system-ui, sans-serif;
  --font-display: 'Outfit', 'Noto Sans SC', sans-serif;
  --sidebar-width: 260px;
}
```

推荐特征：白底 + 深青导航 + 客户卡片 + 管道视图 + 时间轴  
配色建议：青绿色负责信任感，铜棕只点在转化、阶段、重点客户标签上。

## 预设选择决策树

```txt
需求是否涉及“仓库 / 设备 / 工单 / 调度 / 运行态势”？
  -> 是：industrial-b
  -> 否：继续
需求是否涉及“大屏 / 监控中心 / 指挥中心 / 实时态势”？
  -> 是：command-center
  -> 否：继续
需求是否涉及“数据分析 / 报表 / BI / 趋势看板”？
  -> 是：dashboard-analytics
  -> 否：继续
需求是否涉及“客户管理 / CRM / 销售 / 客户门户”？
  -> 是：crm-portal
  -> 否：继续
需求是否涉及“巡检 / 现场 / 移动作业 / App”？
  -> 是：mobile-tool
  -> 否：saas-clean
```
