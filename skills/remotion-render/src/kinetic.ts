/**
 * INPUT: KineticText 镜头的 params（beats、可选 icon）、镜头帧数与开头预滚帧数；markup.ts 的 plainText。纯计算，不依赖 Remotion，node:test 可直接导入
 * OUTPUT: KINETIC_EFFECTS、TIMING、KINETIC_LAYOUT、DEFAULT_TONES（各效果的默认语义色）、heightFontLimit（按高度限字号）、parseKineticBeats（参数校验）、
 *         planKinetic（每拍起止帧、退场帧与动作标记）、countValue / countText（数字滚动）、typedCount（打字进度）、charCount
 * POS: 文字动效场景的唯一时间表。组件按它排动画；配音效时的动作标记也从这里取，避免手写时间与画面脱节
 *      （docs/EDITING_METHOD.md 第 6 节：优先由渲染代码导出实际动作帧）。动作类型取自 sfx-kit 的 kinds。
 */

import { plainText } from "./markup.ts";
import type { Tone } from "./markup.ts";

// 与 scripts/lib.mjs 的 KINETIC_EFFECTS 保持一致；新增效果时两处同步
export const KINETIC_EFFECTS = ["drop", "pop", "count", "strike", "highlight", "type", "fly", "dissolve"] as const;
export type KineticEffect = (typeof KINETIC_EFFECTS)[number];

// 可带 replace 的效果：strike 必填（划掉后换上），dissolve 可选（消散后在原位换上）
const REPLACE_EFFECTS: KineticEffect[] = ["strike", "dissolve"];
// 可带 out_at 退场的效果：fly 不写就不飞出，dissolve 不写就在出现后停留 TIMING.dissolve.hold 帧再消散
const EXIT_EFFECTS: KineticEffect[] = ["fly", "dissolve"];

export interface KineticBeat {
  text: string;
  effect: KineticEffect;
  // 本拍开始的位置：镜头可见时长的比例（0～1），与其他场景的 at 同一口径
  at: number;
  // strike / dissolve：去掉旧说法后换上的说法
  replace?: string;
  // fly / dissolve：退场开始的位置（可见时长比例，须晚于 at）
  outAt?: number;
}

export interface ActionMark {
  // 镜头内帧号（开头镜头含预滚）；换算到全片时加镜头起点、减预滚
  frame: number;
  // sfx-kit 的动作类型
  kind: "land" | "appear" | "appear_small" | "count" | "strike" | "highlight" | "type" | "transition_in" | "transition_out";
  target: string;
}

export interface PlannedBeat extends KineticBeat {
  start: number;
  // 退场开始的帧（fly 没写 out_at 时为 null）
  exit: number | null;
  // 本拍所有动作停稳的帧
  settle: number;
}

export interface KineticPlan {
  iconStart: number;
  beats: PlannedBeat[];
  actions: ActionMark[];
}

// 各效果的关键帧，相对本拍起点（退场相对退场帧）。2026-10-09 主理人看样片后确认，动作说明见 docs/DESIGN.md 第 4 节
export const TIMING = {
  icon: { draw: 18, stagger: 3 },
  drop: { fall: 9, settle: 18 },
  pop: { grow: 12 },
  count: { reveal: 8, roll: 24 },
  strike: { reveal: 10, strikeAt: 14, strikeFrames: 10, replaceAt: 28, settle: 40 },
  highlight: { reveal: 10, sweepAt: 12, sweepFrames: 12 },
  // 打字：每字 2 帧（中文一字一词感，比英文常用的 1 帧慢）；打完光标再闪 cursorTail 帧后消失
  type: { charFrames: 2, cursorTail: 24, blink: 16 },
  // 飞入 / 飞出：逐字错开 stagger 帧，每字 frames 帧走完
  fly: { stagger: 1.5, frames: 12 },
  // 粒子消散：出现 reveal 帧、默认停留 hold 帧；退场逐字 stagger 帧碎开，字 fade 帧淡出，颗粒 drift 帧飘散；换上的说法在退场后 replaceAfter 帧弹出
  dissolve: { reveal: 10, hold: 24, stagger: 1.5, fade: 8, drift: 22, replaceAfter: 12 },
} as const;

// 各效果没写语义色的 {…} 用什么颜色：划掉/消散的旧说法默认痛点色，换上的说法默认解法色，数字默认数据色，其余品牌紫
export const DEFAULT_TONES: Record<KineticEffect, { text: Tone; replace: Tone }> = {
  drop: { text: "brand", replace: "brand" },
  pop: { text: "brand", replace: "brand" },
  count: { text: "data", replace: "data" },
  strike: { text: "pain", replace: "gain" },
  highlight: { text: "brand", replace: "brand" },
  type: { text: "brand", replace: "brand" },
  fly: { text: "brand", replace: "brand" },
  dissolve: { text: "pain", replace: "gain" },
};

// 版式比例（相对字号）：行高、行间距、strike 错误说法的缩小比例、图标与第一行的额外间距
export const KINETIC_LAYOUT = { lineHeight: 1.3, gap: 0.32, strikeScale: 0.82, iconMargin: 0.2 } as const;

// 数字滚动的音效最密每 2 帧一跳，再密听起来就是噪声
const MIN_TICK_GAP = 2;
// 打字声最密每 4 帧一下：每字一声在 2 帧一字时太密，听感像机关枪
const MIN_TYPE_GAP = 4;
// 图标出现的轻音效与其他动作相距不足 4 帧时让位，两个起音挤在一起只会糊成一声
const SOFT_YIELD_GAP = 4;

/**
 * 按高度限制字号：所有行、行距与图标叠起来不超出内容区。宽度限制由 fitFontSize 另算，场景取两者较小值。
 * 最坏情况（图标 + 4 拍 strike，共 8 行）约 86px，仍然可读。dissolve 的换上说法与原文同一行，不占额外高度。
 */
export function heightFontLimit(beats: KineticBeat[], iconSize: number, availableHeight: number): number {
  const { lineHeight, gap, strikeScale, iconMargin } = KINETIC_LAYOUT;
  const rowUnits = beats.reduce((sum, beat) => sum + (beat.effect === "strike" ? (1 + strikeScale) * lineHeight : lineHeight), 0);
  const items = beats.length + (iconSize > 0 ? 1 : 0);
  const units = rowUnits + gap * (items - 1) + (iconSize > 0 ? iconMargin : 0);
  return Math.floor((availableHeight - iconSize) / units);
}

/** 上屏字数（去掉强调标记与语义色名）。 */
export function charCount(text: string): number {
  return Array.from(plainText(text)).length;
}

function readRatio(value: unknown, label: string, key: string): number | undefined {
  if (value === undefined) return undefined;
  if (!(typeof value === "number" && value >= 0 && value < 1)) throw new Error(`${label}的 ${key} 必须在 0～1 之间`);
  return value;
}

/** 校验并整理一拍；不合格直接报错，不渲染半成品。 */
function parseBeat(item: unknown, index: number): KineticBeat {
  const beat = (item ?? {}) as Record<string, unknown>;
  const label = `KineticText 第 ${index + 1} 拍`;
  if (typeof beat.text !== "string" || !beat.text.trim()) throw new Error(`${label}缺少 text`);
  if (!KINETIC_EFFECTS.includes(beat.effect as KineticEffect)) throw new Error(`${label}的 effect 只能是 ${KINETIC_EFFECTS.join(" / ")}`);
  const effect = beat.effect as KineticEffect;
  const at = readRatio(beat.at, label, "at") ?? 0;
  const outAt = readRatio(beat.out_at, label, "out_at");
  const hasReplace = typeof beat.replace === "string" && beat.replace.trim() !== "";
  if (effect === "strike" && !hasReplace) throw new Error(`${label}是 strike，需要 replace（换上的说法）`);
  if (hasReplace && !REPLACE_EFFECTS.includes(effect)) throw new Error(`${label}：只有 strike / dissolve 可以写 replace`);
  if (outAt !== undefined && !EXIT_EFFECTS.includes(effect)) throw new Error(`${label}：只有 fly / dissolve 可以写 out_at`);
  if (outAt !== undefined && outAt <= at) throw new Error(`${label}的 out_at 必须晚于 at`);
  if (effect === "count" && firstNumber(beat.text) === null) throw new Error(`${label}是 count，text 里需要一个整数`);
  return { text: beat.text, effect, at, ...(hasReplace ? { replace: beat.replace as string } : {}), ...(outAt !== undefined ? { outAt } : {}) };
}

/** 校验并整理 params.beats（1～4 拍）。 */
export function parseKineticBeats(params: Record<string, unknown>): KineticBeat[] {
  const raw = params.beats;
  if (!Array.isArray(raw) || raw.length < 1 || raw.length > 4) {
    throw new Error("KineticText 需要 params.beats：1～4 拍");
  }
  return raw.map(parseBeat);
}

/** 文字里第一个整数（花括号强调标记不含数字，直接在原文上找即可）。 */
export function firstNumber(text: string): number | null {
  const match = /\d+/.exec(text);
  return match ? Number(match[0]) : null;
}

/** 数字滚动的当前值：本拍出现后从 0 滚到目标值，缓出（先快后慢），终值与原文一致。 */
export function countValue(beat: PlannedBeat, frame: number): number {
  const target = firstNumber(beat.text) ?? 0;
  const begin = beat.start + TIMING.count.reveal;
  const t = Math.min(1, Math.max(0, (frame - begin) / TIMING.count.roll));
  return Math.round(target * (1 - (1 - t) ** 3));
}

// 补位标记（Unicode 私用区 U+E000）：渲染时画成透明的「0」。
// 不用等宽空格 U+2007：NotoSansSC 没有这个字形，浏览器会借系统字体，换机器就不能逐字节复现。
// 该字体 0～9 前进宽度相同（521/1000），用透明的 0 补位即可保证整行宽度不变
export const COUNT_PAD = "";

/** 把原文第一个整数换成滚动中的值；位数不足时在前面补 COUNT_PAD，整行宽度不变、不左右抖。 */
export function countText(text: string, value: number): string {
  const match = /\d+/.exec(text);
  if (!match) return text;
  const shown = String(value).padStart(match[0].length, COUNT_PAD);
  return text.slice(0, match.index) + shown + text.slice(match.index + match[0].length);
}

/** 打字进度：已经打出的字数（0～总字数）。 */
export function typedCount(beat: PlannedBeat, frame: number): number {
  return Math.max(0, Math.min(charCount(beat.text), Math.floor((frame - beat.start) / TIMING.type.charFrames) + 1));
}

/** dissolve 换上说法弹出的帧：最后一个字开始碎开之后。 */
export function dissolveReplaceFrame(beat: PlannedBeat): number {
  return (beat.exit ?? beat.start) + Math.ceil((charCount(beat.text) - 1) * TIMING.dissolve.stagger) + TIMING.dissolve.replaceAfter;
}

/** 本拍从开始到退场（或入场）结束的帧数。fly 的入场与退场都按逐字错开计算。 */
function settleFrame(beat: PlannedBeat): number {
  const chars = charCount(beat.text);
  switch (beat.effect) {
    case "drop":
      return beat.start + TIMING.drop.settle;
    case "pop":
      return beat.start + TIMING.pop.grow;
    case "count":
      return beat.start + TIMING.count.reveal + TIMING.count.roll;
    case "strike":
      return beat.start + TIMING.strike.settle;
    case "highlight":
      return beat.start + TIMING.highlight.sweepAt + TIMING.highlight.sweepFrames;
    case "type":
      return beat.start + chars * TIMING.type.charFrames;
    case "fly":
      return (beat.exit ?? beat.start) + Math.ceil((chars - 1) * TIMING.fly.stagger) + TIMING.fly.frames;
    case "dissolve": {
      const crumbled = (beat.exit ?? beat.start) + Math.ceil((chars - 1) * TIMING.dissolve.stagger) + TIMING.dissolve.drift;
      return beat.replace ? Math.max(crumbled, dissolveReplaceFrame(beat) + TIMING.pop.grow) : crumbled;
    }
  }
}

/** 等间隔动作（数字跳动、打字）：值变化处出声，间隔不少于 gap 帧。 */
function steppedMarks(from: number, to: number, valueAt: (frame: number) => number, gap: number, kind: ActionMark["kind"], target: string): ActionMark[] {
  const marks: ActionMark[] = [];
  let previous = valueAt(from - 1);
  let lastMark = -Infinity;
  for (let frame = from; frame <= to; frame += 1) {
    const value = valueAt(frame);
    if (value !== previous && frame - lastMark >= gap) {
      marks.push({ frame, kind, target });
      lastMark = frame;
    }
    previous = value;
  }
  return marks;
}

function beatActions(beat: PlannedBeat, index: number): ActionMark[] {
  const target = `beat_${index + 1}`;
  switch (beat.effect) {
    case "drop":
      return [{ frame: beat.start + TIMING.drop.fall, kind: "land", target }];
    case "pop":
      return [{ frame: beat.start + 1, kind: "appear", target }];
    case "count": {
      const begin = beat.start + TIMING.count.reveal;
      return steppedMarks(begin + 1, begin + TIMING.count.roll, (frame) => countValue(beat, frame), MIN_TICK_GAP, "count", target);
    }
    case "strike":
      return [
        { frame: beat.start + TIMING.strike.strikeAt, kind: "strike", target },
        { frame: beat.start + TIMING.strike.replaceAt, kind: "appear", target: `${target}_replace` },
      ];
    case "highlight":
      return [{ frame: beat.start + TIMING.highlight.sweepAt, kind: "highlight", target }];
    case "type":
      return steppedMarks(beat.start, beat.settle, (frame) => typedCount(beat, frame), MIN_TYPE_GAP, "type", target);
    case "fly":
      return [{ frame: beat.start, kind: "transition_in", target }, ...(beat.exit !== null ? [{ frame: beat.exit, kind: "transition_out" as const, target }] : [])];
    case "dissolve":
      return [
        { frame: beat.exit ?? beat.start, kind: "transition_out", target },
        ...(beat.replace ? [{ frame: dissolveReplaceFrame(beat) + 1, kind: "appear" as const, target: `${target}_replace` }] : []),
      ];
  }
}

/**
 * 排出每一拍的起止帧、退场帧与动作标记。起点 = 预滚 + at × 可见时长，取整一次，后续关键帧都是整数偏移，
 * 组件与音效读同一组整数，不会各自取整而错开一帧。最后一拍来不及停稳就报错，由分镜调整 at 或镜头时长。
 */
export function planKinetic(beats: KineticBeat[], sceneFrames: number, preroll: number, hasIcon: boolean): KineticPlan {
  const visible = sceneFrames - preroll;
  const toFrame = (ratio: number) => Math.round(preroll + ratio * visible);
  const planned = beats.map((beat) => {
    const start = toFrame(beat.at);
    const defaultExit = beat.effect === "dissolve" ? start + TIMING.dissolve.reveal + TIMING.dissolve.hold : null;
    const draft: PlannedBeat = { ...beat, start, exit: beat.outAt !== undefined ? toFrame(beat.outAt) : defaultExit, settle: start };
    return { ...draft, settle: settleFrame(draft) };
  });
  planned.forEach((beat, index) => {
    if (beat.settle > sceneFrames) {
      throw new Error(`KineticText 第 ${index + 1} 拍要到镜头第 ${beat.settle} 帧才停稳，超过镜头长度 ${sceneFrames} 帧；把 at 提前或加长镜头`);
    }
  });
  const iconStart = preroll;
  const actions: ActionMark[] = hasIcon ? [{ frame: iconStart, kind: "appear_small", target: "icon" }] : [];
  planned.forEach((beat, index) => actions.push(...beatActions(beat, index)));
  actions.sort((a, b) => a.frame - b.frame);
  return { iconStart, beats: planned, actions: yieldSoftMarks(actions) };
}

/** 去掉紧挨其他动作的 appear_small：画面动作照常，只是不单独出声。 */
function yieldSoftMarks(actions: ActionMark[]): ActionMark[] {
  return actions.filter(
    (mark) => mark.kind !== "appear_small" || !actions.some((other) => other !== mark && other.kind !== "appear_small" && Math.abs(other.frame - mark.frame) < SOFT_YIELD_GAP),
  );
}
