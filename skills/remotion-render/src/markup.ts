/**
 * INPUT: 场景参数里的文字（{…} 强调标记，可带语义色：{熬通宵|痛点}）。纯计算，不依赖 Remotion，node:test 可直接导入
 * OUTPUT: TONES（五种语义色预设）、Tone、resolveTone、toneColor、parseAccent、plainText、stripToneMarks、semanticTones、toneChars（逐字带色）
 * POS: 强调文字的「按文案意思选颜色」预设。2026-10-09 主理人要求：颜色不固定为紫色，按内容选。
 *      没写语义的 {…} 仍是品牌紫，旧项目重渲染结果不变。色值 2026-10-09 经主理人确认，系列规则见 docs/DESIGN.md 第 3 节。
 *      对比度（WCAG，粗体大字及格线 3）：浅色值对浅灰底 #F3F3F3 均 ≥ 4.1，深色值对深色底 #090A0D 均 ≥ 5.8。
 */

export type Tone = "brand" | "pain" | "gain" | "data" | "caution";

export interface ToneSpec {
  // 写稿时用的中文名，标记里写 {词|痛点}；英文键名同样可用
  label: string;
  // 浅色底上的文字色
  light: string;
  // 深色底上的文字色（提亮，保证对比度）
  dark: string;
  // 荧光笔、淡底色用的浅色
  tint: string;
}

export const TONES: Record<Tone, ToneSpec> = {
  // 品牌 / 默认强调：系列紫，与 theme.ts 的 COLORS.accent、accentBright、lavender 相同
  brand: { label: "品牌", light: "#6A3CE9", dark: "#9773FC", tint: "#CDBEFF" },
  // 痛点 / 错误 / 风险
  pain: { label: "痛点", light: "#D93A3F", dark: "#FF6B6E", tint: "#FFD3D4" },
  // 解法 / 正确 / 结果
  gain: { label: "解法", light: "#15803D", dark: "#4ADE80", tint: "#C8F0D5" },
  // 数据 / 数字 / 效率
  data: { label: "数据", light: "#1D5FD8", dark: "#6EA8FF", tint: "#D3E2FF" },
  // 提醒 / 边界 / 注意
  caution: { label: "提醒", light: "#B45309", dark: "#FBBF24", tint: "#FDE6B6" },
};

const TONE_KEYS = Object.keys(TONES) as Tone[];

/** 中文名或英文键名 → 语义色；未知名字直接报错，不悄悄退回紫色。 */
export function resolveTone(name: string): Tone {
  const trimmed = name.trim();
  const found = TONE_KEYS.find((key) => key === trimmed || TONES[key].label === trimmed);
  if (!found) {
    throw new Error(`未知的语义色「${trimmed}」，可用：${TONE_KEYS.map((key) => `${TONES[key].label}（${key}）`).join("、")}`);
  }
  return found;
}

export function toneColor(tone: Tone, night = false): string {
  return night ? TONES[tone].dark : TONES[tone].light;
}

export interface TextRun {
  text: string;
  accent: boolean;
  // 强调段的语义色；普通文字为 null
  tone: Tone | null;
}

/**
 * 解析强调标记：「每次投标都要{熬夜排版}」中花括号内的文字用强调色。
 * 花括号只是标记，不显示、不计入字宽；没有配对的括号按普通文字处理。
 * {词|痛点} 指定语义色；不写时用 defaultTone（场景按动作给默认值，例如被划掉的说法默认痛点色，其余默认品牌紫）。
 */
export function parseAccent(text: string, defaultTone: Tone = "brand"): TextRun[] {
  const runs: TextRun[] = [];
  const pattern = /\{([^{}]*)\}/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) runs.push({ text: text.slice(cursor, index), accent: false, tone: null });
    const body = match[1] ?? "";
    const bar = body.lastIndexOf("|");
    runs.push(bar < 0 ? { text: body, accent: true, tone: defaultTone } : { text: body.slice(0, bar), accent: true, tone: resolveTone(body.slice(bar + 1)) });
    cursor = index + match[0].length;
  }
  if (cursor < text.length) runs.push({ text: text.slice(cursor), accent: false, tone: null });
  return runs.filter((run) => run.text.length > 0);
}

/** 去掉强调标记后的纯文字。 */
export function plainText(text: string): string {
  return parseAccent(text)
    .map((run) => run.text)
    .join("");
}

/** 去掉语义色名（{熬通宵|痛点} → {熬通宵}），供字宽估算使用：色名不上屏、不计宽。 */
export function stripToneMarks(text: string): string {
  return text.replace(/\|[^{}|]*\}/g, "}");
}

/** 一段文字里用到的语义色（不含品牌紫），用于检查「同一镜头除品牌紫外最多 2 种语义色」。 */
export function semanticTones(text: string, defaultTone: Tone = "brand"): Tone[] {
  return [...new Set(parseAccent(text, defaultTone).flatMap((run) => (run.tone && run.tone !== "brand" ? [run.tone] : [])))];
}

/** 拆成逐字列表，每个字带所在强调段的语义色（普通文字为 null），供逐字动画（打字、飞入、粒子消散）使用。 */
export function toneChars(text: string, defaultTone: Tone = "brand"): Array<{ char: string; tone: Tone | null }> {
  return parseAccent(text, defaultTone).flatMap((run) => Array.from(run.text).map((char) => ({ char, tone: run.tone })));
}
