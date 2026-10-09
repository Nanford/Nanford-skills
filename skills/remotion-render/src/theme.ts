/**
 * INPUT: 无
 * OUTPUT: 颜色、阴影、字体族名、安全区与版面宽度、通用缓动、文字宽度估算与字号适配、读取场景参数的小工具；转出 markup.ts 的强调标记解析与语义色
 * POS: 全部场景共享的视觉常量。系列视觉规则见仓库 docs/DESIGN.md（浅灰底、近黑字、单一紫色强调、毛玻璃卡片），改数值时两处同步。
 *      安全区数值来自 AGENTS.md 第 11 节，是保守排版预设，最终以平台预览为准。
 */

import { Easing, interpolate } from "remotion";
import { stripToneMarks } from "./markup";

export const FONT_FAMILY = "NotoSansSC";

export const COLORS = {
  paper: "#F3F3F3",
  ink: "#111114",
  inkSoft: "#5B5B66",
  // 逐字出现的起始色：先浅灰后变黑，比单纯淡入更像「对焦」
  inkFaint: "#C9C9D1",
  accent: "#6A3CE9",
  // 深色底上的紫色要提亮，否则对比度不足
  accentBright: "#9773FC",
  accentSoft: "rgba(106, 60, 233, 0.10)",
  lavender: "#CDBEFF",
  night: "#090A0D",
  nightText: "#F5F5F7",
  nightMuted: "rgba(245, 245, 247, 0.28)",
  glass: "rgba(255, 255, 255, 0.64)",
  glassStrong: "rgba(255, 255, 255, 0.86)",
  glassBorder: "rgba(255, 255, 255, 0.9)",
  hairline: "rgba(17, 17, 20, 0.10)",
  danger: "#E5484D",
};

export const SHADOW = {
  card: "0 24px 60px rgba(34, 24, 84, 0.14)",
  float: "0 40px 110px rgba(34, 24, 84, 0.24)",
};

// 毛玻璃模糊半径：backdrop-filter 在 1080×1920 下较耗时，统一取值便于评估渲染成本
export const GLASS_BLUR = 26;

// 1080×1920 画面的重要内容避让区：右侧为平台点赞、评论按钮，底部为标题与字幕区
export const SAFE = { left: 72, right: 180, top: 160, bottom: 360 };
export const CONTENT_WIDTH = 1080 - SAFE.left - SAFE.right;
// 居中大字的文字列：以画面中线为轴左右各让 180px，视觉居中且右缘不超出安全区（900px）
export const TEXT_COLUMN_WIDTH = 1080 - SAFE.right * 2;
// 卡片与窗口的外框：以画面中线居中、宽 900；框内文字另留右内边距，保证文字右缘不超过 900px
export const PANEL = { left: 90, width: 900 };
// 场景内容区：上缘在品牌角标下方，下缘留出字幕区（约 170px）
export const CONTENT_TOP = SAFE.top + 110;
export const CONTENT_BOTTOM = 1920 - SAFE.bottom - 190;
// 步骤条目文字可用宽度：卡片内边距、图标与间距之后的余量，与 script-check 的 STEP_TEXT_WIDTH 一致
export const STEP_TEXT_WIDTH = 660;
// 字幕文字可用宽度：内容区减去字幕底框左右内边距 52
export const CAPTION_TEXT_WIDTH = CONTENT_WIDTH - 52;
// 中文按词不拆：只在空格和标点处换行；实在放不下时才允许任意位置断开，防止溢出画面
export const KEEP_WORDS = { wordBreak: "keep-all", overflowWrap: "anywhere", textWrap: "balance" } as const;

export const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);
// 带一点回弹的缓出：卡片、标签落位时使用，幅度小，避免显得轻浮
export const EASE_BACK = Easing.bezier(0.34, 1.36, 0.64, 1);

/** 从 startFrame 起 durationFrames 帧内由 0 到 1，钳制在范围内。 */
export function progress(frame: number, startFrame: number, durationFrames: number, easing = EASE_OUT): number {
  return interpolate(frame, [startFrame, startFrame + durationFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing,
  });
}

// 强调标记与语义色的解析在 markup.ts（纯计算，可单测），这里转出供各场景沿用原来的导入路径
export { parseAccent, plainText, resolveTone, toneColor, TONES, type TextRun, type Tone } from "./markup";

/**
 * 估算一行文字占多少个「字宽」（1 = 一个汉字的宽度）。
 * 系数取自 NotoSansSC-VF.ttf 的实测前进宽度：空格 0.22em、间隔号 · 为全角 1em、拉丁字母与数字约 0.5～0.6em，
 * 这里取偏保守值：宁可字号略小，也不让文字超出安全区或折行出孤字。强调标记的花括号不计宽。
 * scripts/lib.mjs 的 textUnits（审片截帧挑最宽字幕）与 script-check 技能的 text_units（配音前预判字号）同一算法，改动时三处同步。
 */
export function textUnits(text: string): number {
  let units = 0;
  // 语义色名（{词|痛点} 里的「|痛点」）不上屏，先去掉再计宽
  for (const char of stripToneMarks(text)) {
    const code = char.codePointAt(0) ?? 0;
    if (char === "{" || char === "}") {
      continue;
    } else if (char === " ") {
      units += 0.25;
    } else if (char === "·" || code >= 0x2e80) {
      units += 1;
    } else {
      units += 0.6;
    }
  }
  return units;
}

// 估算只按字符类别计宽，粗体拉丁字母（如 FDE、OpenAI）实际更宽；留 4% 余量，避免贴边时被浏览器折行
const FIT_MARGIN = 0.96;

/** 让最长的一行放进 availableWidth：返回不超过 maxSize 的字号。多行标题共用一个字号，保持视觉统一。 */
export function fitFontSize(lines: string[], maxSize: number, availableWidth: number = CONTENT_WIDTH): number {
  const widest = Math.max(1, ...lines.map(textUnits));
  return Math.min(maxSize, Math.floor((availableWidth * FIT_MARGIN) / widest));
}

export function stringParam(params: Record<string, unknown>, key: string, fallback = ""): string {
  const value = params[key];
  return typeof value === "string" ? value : fallback;
}

export function listParam(params: Record<string, unknown>, key: string): string[] {
  const value = params[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function numberParam(params: Record<string, unknown>, key: string, fallback: number): number {
  const value = params[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
