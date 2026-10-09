---
name: remotion-render
description: VideoCut 工作流的画面渲染技能：按 video-timeline 产出的 timeline.json 用 Remotion 渲染 1080×1920、30fps 的无声竖屏画面（十种场景 + 字幕 + 品牌与可选 AI 角标，支持真实截图、录屏片段、示意插图及纯文字动效），另可截取审片静帧、渲染竖版封面。时间轴完成后、混音封装之前使用；改了分镜参数、场景组件或时间轴后重跑。
---

# 画面渲染（remotion-render）

> 路径约定：`<本技能目录>` 指本文件所在目录，`<技能名 技能目录>` 指同名技能的目录；在 VideoCut 工作区里都是 `.claude/skills/<技能名>`，全局安装时是 `~/.codex/skills/<技能名>` 等。命令在工作区根目录（含 `videocut.workspace.json` 的目录）执行，目录含空格时给路径加引号。

## 准备（每台机器一次）

在本技能目录执行（Node.js 22.6+；测试直接导入 TypeScript 源文件，需要类型剥离，Node 22.6～23.5 由 `npm test` 自带的 `--experimental-strip-types` 开启）：

```bash
cd <本技能目录>
npm ci                # 按 package-lock.json 安装锁定版本的 Remotion 4.0.529 与 React 19.2.3
npm run setup:fonts   # 从 google/fonts 固定提交下载 Noto Sans SC 可变字体（约 17 MB，SIL OFL 1.1）并校验 SHA-256
```

- 字体不进 Git（`.gitignore` 已排除 `public/fonts/`，许可文本 OFL.txt 随字体一起下载校验），缺字体时渲染直接失败，不会用系统回退字体出错字形。
- 底图 `public/wallpapers/`（21 张 1080×1920 JPEG，约 6 MB，分 `nature` / `office` / `blueprint` / `tech` / `city` 五组）随仓库提交，保证每台机器渲染结果一致。来源、摄影师、分组、Unsplash License 核验记录（2026-10-07 起另核照片 JSON 的 premium=false、plus=false）、原图与成品校验值、裁切框见 `public/wallpapers/manifest.json`。
- 加图或换图：在清单里写好 id、group、来源页、`source_url`（images.unsplash.com 原图地址）、`focus_x`，运行 `python scripts/wallpapers_build.py`（Pillow；原图缓存在工作区 `.cache/wallpapers/`）取图、裁成 9:16 并写回校验值；再同步 `src/wallpapers.ts`，`npm test` 会核对两处 id 一致。只收浅色、留白多的图，先用 `--backdrop-theme` 出整期静帧确认黑色标题清楚。
- 在新电脑上恢复底图：`python scripts/wallpapers_build.py --restore` 按清单逐张核对，缺的从图库 CDN 下载原图（核对原图校验值）、按清单的裁切框重做，清单不改。有 `source_url` 的 15 张可这样恢复，在 Pillow 12.1.0 下与清单逐字节一致；其他 Pillow 版本会提示「与清单校验值不同」，画面可用，但渲染结果不再与原机器逐字节相同。nature 组 6 张没有 `source_url`（原图当初从下载页手动取得，下载页有人机验证、CDN 版本会重新编码），随技能包附带，缺失时提示重新安装。
- 第一次渲染时 Remotion 会自动下载 Chrome Headless Shell（约 113 MB）到 `node_modules/.remotion/`，之后复用。
- 以上都是免费步骤，不调用任何计费接口。

## 调用方式

在本技能目录执行，路径可以是相对或绝对路径：

```bash
# 只做结构检查：镜头首尾相接覆盖全片、场景类型受支持、字幕在片长内且不重叠
node scripts/render.mjs check  --timeline <版本目录>/timeline.json

# 审片静帧：首帧、每个镜头中段（文字动效取镜头最后一帧）、最宽的 3 条字幕中段、末帧（默认半分辨率）
node scripts/render.mjs stills --timeline <版本目录>/timeline.json --out-dir <版本目录>/preview/stills-v001

# 低清粗剪（AGENTS.md 第 11 节：先粗剪检查再正式导出）
node scripts/render.mjs video  --timeline <版本目录>/timeline.json --out <版本目录>/preview/rough-v001.mp4 --scale 0.5

# 正式画面（无声）；可用 --frames 0-89 只渲染一段做局部检查
node scripts/render.mjs video  --timeline <版本目录>/timeline.json --out <版本目录>/exports/picture-v001.mp4

# 竖版封面
node scripts/render.mjs cover  --props <版本目录>/cover.props.json --out <版本目录>/exports/cover-v001.png

# 动作标记：文字动效每拍的落地、出现、划掉、打字等帧 → actions.json，交给 av-export sfx 排音效轨
# 直接导入 src/kinetic.ts：Node 23.6+ 直接运行；Node 22.6～23.5 写成 node --experimental-strip-types scripts/render.mjs actions …
node scripts/render.mjs actions --timeline <版本目录>/timeline.json --out <版本目录>/actions.json

# 当前渲染代码校验值（与 render.json 的 code_sha256 相同算法）
node scripts/render.mjs code-hash

# 可复现验证：按渲染记录重截抽样帧（首帧、中间镜头中段、末帧，无损 PNG），逐字节比对；一致退出码 0，不一致 1
node scripts/render.mjs verify --timeline <版本目录>/timeline.json --record <版本目录>/exports/picture-v001.mp4.render.json
```

底图题材：`video`、`stills` 读时间轴所属项目 `brief.json` 的 `visual.backdrop_theme`（组名或组名数组），给没写 `wallpaper` 的底图镜头（StepFlow、EvidenceCard、ScreenFocus、ScreenClip、截图对比 BeforeAfter）按组顺序轮换分配，相邻镜头不重复；镜头写了 `wallpaper` 的保持原样；没设题材时沿用各场景默认风景图（旧项目重渲染结果不变）。`--backdrop-theme office,blueprint` 可临时覆盖，用于并排比较各组效果。分配结果与题材写进 `render.json`（`input.backdrops`、`settings.backdrop_theme`），`verify` 按记录里的题材复现。

可选：`--brand "Nanford · AI 实战笔记"`、`--ai-label "…"`。角标文字的来源：命令行 `--ai-label` 优先（传 `""` 不画）；未传时读时间轴所属项目 `brief.json` 的 `aigc.explicit_overlay`，为 `none` 时不画（系列默认，见 `docs/DESIGN.md`），其余情况画「AI 合成配音」。`video` 与 `stills` 同一来源，审片静帧与成片一致。封面由 props 的 `aiLabel` 决定，不画时写 `""`。不画角标时发布包须把平台 AI 声明列为必做项。

## 输入

- `timeline.json`：`width`、`height`、`fps`、`duration_frames`、`tracks.visual`（`shot_id`、`scene_type`、`params`、`start_frame`、`end_frame`）、`tracks.caption`（`id`、`text`、`start_frame`、`end_frame`）。帧边界由 video-timeline 一次算定，本技能只按帧排布，不重新计算时长。
- 项目图片：`ScreenFocus` 的 `params.image`、`BeforeAfter` 截图对比的 `params.images[].image` 写**相对项目根目录**（含 `project.json` 的目录）的路径，如 `assets/original/asset_image_003.png`。渲染前 `render.mjs` 把它们按内容校验值暂存为 `project-assets/<sha256>.png|jpg`，补上 `image_size`，原 timeline.json 不改动。只支持 PNG 与 JPEG。
- 补充插图：`Illustration` 同样使用 `params.image` 与上述本地图片暂存流程，支持 PNG 透明度，完整适配而不裁切。生成与来源登记先执行 `visual-assets`；本场景常驻「画面示意」，不与真实截图证据混用。
- 录屏片段：`ScreenClip` 的 `params.video` 同样写相对项目根目录的路径，须是项目里已裁切、打码的 H.264 恒定帧率工作副本（建议 30fps、关键帧间隔 15 帧以内，便于加速播放时逐帧解码），不要直接引用原始录屏。渲染前按内容校验值暂存为 `project-assets/<sha256>.mp4`，读取尺寸与时长，补上 `video_size`，并把倍速算定写入 `playback_rate`；源区间读到片段结尾之后直接报错，不靠定格或循环补画面。
- 封面参数 JSON：`{kicker, title（\n 分行）, sub（可分行，按最长一行缩放到单行放下）, brand, aiLabel}`。

## 场景与参数

文字参数里用 `{…}` 标出强调（如 `"title": "差别不在提示词\n在{规则}"`），花括号不显示、不计字宽。没写色名时是品牌紫，按文案意思选色见下文「语义色」。`wallpaper` 可选 `src/wallpapers.ts` 列出的 21 个 id（分组见 manifest.json），未知 id 直接报错；通常不写，由 `brief.visual.backdrop_theme` 按题材分配。

| scene_type | 背景 | params | 用途 |
|---|---|---|---|
| `ResultHook` | 浅灰（`backdrop: "night"` 为深色） | `kicker`、`title`（\n 分行）、可选 `focus`（标题里的一个词：先放大对焦，再缩回句中原位） | 痛点/优势开场、一句话结论；强调词下方描出手绘波浪线 |
| `ChapterDivider` | 深色 | `lead`（紫色引导词）、`words`（2～6 个，竖向滚动逐个停靠） | 段落节奏点、要点点名 |
| `StepFlow` | 底图（没设题材时默认 glacier） | `variant`（problem / steps / check）、`title`、`items`（2～4 条）、可选 `footnote`、`wallpaper` | 问题清单、操作步骤、能力清单（毛玻璃卡片） |
| `EvidenceCard` | 底图（没设题材时默认 alpenglow） | `kicker`、`big`（纯数字会从 0 计数）、`unit`、`sub`、`note`、`chips`、`source`、`wallpaper` | 有来源的事实；数值必须来自 claims.json 已核实条目 |
| `ScreenFocus` | 底图（没设题材时默认 mistlake） | `image`（必填）、可选 `title`、`tag`、`focus`（[{x,y,w,h}] 依次推近）、`highlights`（[{x,y,w,h,shape: circle/underline, at}]）、`quote`（原文摘录，\n 分行）、`wallpaper` | 真实截图证据：先看全图再分段推近、手绘圈注；截图字太小时用 `quote` 由排版层原样放大，必须与截图一字不差 |
| `Illustration` | 浅灰 | `image`（必填）、可选 `title`（最多两行） | 场景插图或透明主体，图片完整显示且静止，准确标题另行排版；常驻「画面示意」，用于补充说明而非实测证据 |
| `KineticText` | 浅灰 | `beats`（1～4 拍，每拍 `{text, effect, at}`；`effect` 为 `drop` 落下挤压回弹 / `pop` 弹出 / `count` 数字从 0 滚到原文整数 / `strike` 划掉后弹出 `replace` / `highlight` 同色系荧光笔扫过强调词 / `type` 打字输入带闪烁光标 / `fly` 逐字飞入，写 `out_at` 时到点飞出 / `dissolve` 粒子消散，可写 `out_at` 指定消散时刻、`replace` 在原位换上新说法）、可选 `icon`（`src/icons/lucide.ts` 收录的线性图标，逐笔描出） | 2026-10-09 主理人确认（见 docs/DESIGN.md 第 4 节）。没有截图可放、要把一句结论或对比做成动作的镜头；不能作开头镜头（第 0 帧不是完整画面，`check` 会报错）。每拍时间与动作标记由 `src/kinetic.ts` 的 `planKinetic` 统一算出，配音效时直接取用，动作类型与 sfx-kit 的 `kinds` 一致 |
| `ScreenClip` | 底图（没设题材时默认 mistlake） | `video`（必填）、`source_in_ms`（片段内入点）、`source_out_ms` 或 `playback_rate` 二选一（给出点时倍速 = 源区间 ÷ 镜头时长，配音定时长、画面跟着变速）、可选 `title`、`tag`、`wallpaper` | 真实录屏的动态证据（操作过程、成品翻阅）：与截图同一窗口，静音播放，全程约 3% 缓推；倍速 ≥ 1.05 时标签自动追加「N× 加速」。开头镜头的预滚不消耗源区间，第 0 帧即播放入点 |
| `BeforeAfter` | 文字对比浅灰；截图对比底图 | 文字对比：`columns`（[[名称, 说明], …]）、`highlight`、可选 `title`、`source`；截图对比：`images`（两项 {image, tag, focus}）、`beats`（[{index, at}] 按口播依次点亮）或 `highlight` | A 与 B 的区别，竖屏上下排列；截图对比适合「同样用 AI，两种结果」的开头 |
| `ActionEnd` | 浅灰 | `title`（\n 分行）、`sub` | 片尾互动：胶囊倾斜翻色并迸出圆点 |

**语义色（2026-10-09 主理人确认，系列规则见 docs/DESIGN.md 第 3 节）**：强调色按文案意思选，写成 `{词|色名}`，色名不上屏、不计宽。没写色名的 `{…}` 仍是品牌紫，旧项目重渲染结果不变。预设在 `src/markup.ts`：

| 色名 | 用在什么文案 | 浅底 | 深底 |
|---|---|---|---|
| `品牌`（brand） | 系列名、普通重点词（默认） | `#6A3CE9` | `#9773FC` |
| `痛点`（pain） | 痛点、错误说法、风险 | `#D93A3F` | `#FF6B6E` |
| `解法`（gain） | 解法、正确做法、结果 | `#15803D` | `#4ADE80` |
| `数据`（data） | 数字、数据、效率 | `#1D5FD8` | `#6EA8FF` |
| `提醒`（caution） | 边界、注意事项、需人工复核 | `#B45309` | `#FBBF24` |

各场景的写法：标题、条目、对比说明里的 `{词|色名}`；`EvidenceCard` 与 `StepFlow` 可写 `tone`（大字颜色、条目标记颜色）；`BeforeAfter` 文字对比的每行可写第三项，如 `["之前", "手动排版{一整晚}", "痛点"]`。`KineticText` 没写色名时按动作取默认色：被划掉 / 消散的旧说法用痛点色、换上的说法用解法色、滚动的数字用数据色，其余品牌紫。未知色名渲染时直接报错；同一镜头除品牌紫外最多 2 种语义色，由 `script-check` 检查。

图标：`src/icons/` 只收录用到的 Lucide 线性图标（lucide-static 0.460.0，ISC 许可，全文 `LICENSE-lucide.txt`），照抄 SVG 元素并记录原文件 SHA-256，不安装 npm 包；不收品牌与产品标志。

坐标 `x/y/w/h` 与时间 `at` 都是 0～1 的比例：坐标相对图片宽高，`at` 相对镜头的**可见时长**（开头镜头会自动扣除预滚，见下）。

## 排版规则

- 视觉风格：浅灰底 `#F3F3F3`、近黑字、单一紫色 `#6A3CE9` 强调（深色底上用 `#9773FC`），毛玻璃卡片叠在静止的题材底图上，品牌角标、字幕都用毛玻璃胶囊。该风格仿照主理人给的参考片的动效与版式（2026-09-29），2026-09-30 经主理人确认，系列规则见 `docs/DESIGN.md`；数值集中在 `src/theme.ts` 与 `src/components/Frame.tsx`（品牌胶囊），改动时与 DESIGN.md 同步。
- 镜头之间硬切；柔和感由镜头内 5～16 帧的入场动画承担（逐字对焦、卡片由糊到清上浮落位）。只有截图场景持续推近，底图与文字镜头静止。
- 重要内容在安全区内：左 72、右 180、上 160、下 360 px（AGENTS.md 第 11 节的保守预设，以平台实际预览为准）。居中大字用以画面中线为轴的 720px 文字列，卡片与窗口宽 900px 居中，框内文字右缘不超过 900px。
- 标题、条目、字幕的字号按最长一行自动缩小（`fitFontSize`，字宽按 NotoSansSC 实测前进宽度校准并留 4% 余量），分行只由数据里的 `\n` 决定。
- 字幕常规 56px，超宽的一行缩到单行放下，下限 48px；说明类文字只在空格和标点处换行（`keep-all`），不拆开中文词。
- 动画全部由帧号计算，无墙钟、无 CSS 时间动画；散点位置用固定种子的伪随机（`seeded`），同一输入每次渲染结果一致。
- 开头镜头（起始帧为 0）预滚 36 帧：第 0 帧就是完整画面，再用 10 帧由 0.95 放大到 1 给一个动作（只放大内容层，背景始终铺满）。所有场景的入场动画都在 36 帧内完成。第 0 帧是平台默认首帧，也是观众决定是否划走的第一眼，不能是空白淡入。场景里按比例安排的动作通过 `useVisibleFrame` 扣除预滚。

## 产物

- `video`：H.264、`yuv420p` 有限范围（显式设置 `colorSpace: "bt709"` 并写入 BT.709 色彩标记；Remotion 4 默认会输出全范围 `yuvj420p`）、30fps 恒定帧率、CRF 18、无音轨的 MP4。先写 `<输出>.rendering.mp4`，完整成功后才替换正式文件，失败时保留上一版。
- `video` 与 `cover` 在输出旁写 `<输出>.render.json`：时间轴/参数文件的 SHA-256、配音母轨 SHA-256、用到的项目图片（`input.images`：镜头、路径、SHA-256、宽高）、`code_sha256`（src/、scripts/、public/wallpapers/ 与 package-lock.json 的校验值，时间轴和代码都没变才可复用已有画面）、渲染参数、Node 与 Remotion 版本、输出 SHA-256 与字节数、带时区的渲染时间；整片正式渲染另记 `sample_stills`（抽样帧 PNG 校验值），供 `verify` 使用。`verify` 会先核对项目图片与记录一致。
- `stills`：PNG 静帧，文件名为 `帧号-镜头或字幕ID.png`。

画面是静音的：配音、响度处理与封装由 `av-export` 技能完成。

## 测试

```bash
npm test          # node:test，覆盖时间轴检查（含图片场景与录屏片段场景、倍速计算）、文字动效时间表与动作标记（需本机 python 读 sfx-kit 的动作类型）、帧区间解析、审片帧选择、字宽估算（含强调标记）、图片尺寸读取；不启动浏览器、不联网
npm run typecheck # tsc --noEmit
```

真实渲染的验收（静帧抽检、成片解码与规格）在各项目的 QA 阶段记录，不在单元测试里伪造。
