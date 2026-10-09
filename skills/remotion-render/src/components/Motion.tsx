/**
 * INPUT: theme.ts 颜色、缓动与语义色（markup.ts）；kinetic.ts 的 COUNT_PAD；remotion 的 useCurrentFrame、interpolate、interpolateColors
 * OUTPUT: RevealText（逐字对焦出现，支持 {强调} 与 {强调|语义色}）、ToneText（静态语义色强调，可带荧光笔扫过）、GlassPanel（毛玻璃卡片入场）、HandUnderline / HandCircle（手绘下划线与圈注）、
 *         WordCarousel（竖向滚动词列）、DotBurst（圆点迸发）、countUp、seeded（确定性伪随机）
 * POS: 新视觉风格的动效基元，全部场景复用。动画只由帧号驱动，没有随机数、墙钟或 CSS 过渡，同一输入每次渲染一致。
 *      节奏参考 docs/STYLE.md：镜头之间硬切，柔和感由镜头内 5～14 帧的入场动画承担。
 */

import React from "react";
import { interpolate, interpolateColors, useCurrentFrame } from "remotion";
import { COLORS, EASE_BACK, EASE_OUT, GLASS_BLUR, SHADOW, TONES, parseAccent, progress, toneColor, type Tone } from "../theme";
import { COUNT_PAD } from "../kinetic";

/** 确定性伪随机（mulberry32）：同一种子永远得到同一数列，用于散点位置等「看起来随机」的布局。 */
export function seeded(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 数字从 0 计到目标值；动画只改变显示过程，终值与事实表一致。 */
export function countUp(target: number, frame: number, startFrame: number, durationFrames: number): number {
  return Math.round(target * progress(frame, startFrame, durationFrames));
}

// 单字对焦：从浅灰、微糊、略偏右，到清晰的目标色。14 帧完成，相邻字错开 stagger 帧
const CHAR_FOCUS_FRAMES = 14;

export const RevealText: React.FC<{
  text: string;
  fontSize: number;
  startFrame?: number;
  stagger?: number;
  weight?: number;
  color?: string;
  // 深色底：强调词用各语义色的提亮版本
  night?: boolean;
  // 没写语义色的 {…} 用哪种颜色（默认品牌紫）
  defaultTone?: Tone;
  fromColor?: string;
  lineHeight?: number;
  // 暂缓显示的一段字（按去掉标记后的字序号，左闭右开）：到 untilFrame 才直接以终态出现，用于大字缩回句中的衔接
  hold?: { from: number; to: number; untilFrame: number };
}> = ({ text, fontSize, startFrame = 0, stagger = 1.2, weight = 600, color = COLORS.ink, night = false, defaultTone = "brand", fromColor = COLORS.inkFaint, lineHeight = 1.3, hold }) => {
  const frame = useCurrentFrame();
  let index = 0;
  return (
    <span style={{ fontSize, fontWeight: weight, lineHeight, whiteSpace: "nowrap" }}>
      {parseAccent(text, defaultTone).map((run, runIndex) => (
        <React.Fragment key={runIndex}>
          {Array.from(run.text).map((char) => {
            const charIndex = index;
            index += 1;
            const target = run.tone ? toneColor(run.tone, night) : color;
            const held = hold !== undefined && charIndex >= hold.from && charIndex < hold.to;
            const p = held ? (frame >= hold.untilFrame ? 1 : 0) : progress(frame, startFrame + charIndex * stagger, CHAR_FOCUS_FRAMES);
            return (
              <span
                key={charIndex}
                style={{
                  display: "inline-block",
                  // 空格用 pre 保留宽度，否则 inline-block 会吞掉空格
                  whiteSpace: "pre",
                  opacity: held ? p : Math.min(1, p * 2.5),
                  color: held ? target : interpolateColors(p, [0, 1], [fromColor, target]),
                  filter: !held && p < 1 ? `blur(${(1 - p) * 8}px)` : undefined,
                  translate: held ? undefined : `${(1 - p) * 0.18 * fontSize}px 0px`,
                }}
              >
                {char}
              </span>
            );
          })}
        </React.Fragment>
      ))}
    </span>
  );
};

/**
 * 静态强调文字：{…} 按语义色着色（没写语义的用 defaultTone）。sweep 给出时，强调词背后画一道由左到右扫过的同色系荧光笔。
 * 不含花括号的文字原样输出，不额外包元素，旧场景渲染结果不变。数字滚动的补位标记画成透明的「0」（见 kinetic.ts 的 COUNT_PAD）。
 */
export const ToneText: React.FC<{ text: string; night?: boolean; defaultTone?: Tone; sweep?: number }> = ({ text, night = false, defaultTone = "brand", sweep }) => {
  if (!text.includes("{") && !text.includes(COUNT_PAD)) return <>{text}</>;
  return (
    <>
      {parseAccent(text, defaultTone).map((run, index) => (
        <span
          key={index}
          style={
            run.tone
              ? {
                  color: toneColor(run.tone, night),
                  backgroundImage: sweep === undefined ? undefined : `linear-gradient(${TONES[run.tone].tint}, ${TONES[run.tone].tint})`,
                  backgroundRepeat: "no-repeat",
                  backgroundPosition: "0 88%",
                  backgroundSize: `${(sweep ?? 0) * 100}% 38%`,
                  borderRadius: 6,
                }
              : undefined
          }
        >
          <PaddedDigits text={run.text} />
        </span>
      ))}
    </>
  );
};

/** 数字滚动的补位标记画成透明的「0」：占位与真实数字同宽（字体 0～9 等宽），且字形来自同一字体。 */
const PaddedDigits: React.FC<{ text: string }> = ({ text }) => {
  if (!text.includes(COUNT_PAD)) return <>{text}</>;
  return (
    <>
      {text.split(COUNT_PAD).map((piece, index) => (
        <React.Fragment key={index}>
          {index > 0 ? <span style={{ color: "transparent" }}>0</span> : null}
          {piece}
        </React.Fragment>
      ))}
    </>
  );
};

/** 一行文字逐字出现所需的帧数：最后一个字开始对焦的时间 + 单字对焦时长。 */
export function revealDuration(text: string, stagger = 1.2): number {
  const count = Array.from(parseAccent(text).map((run) => run.text).join("")).length;
  return Math.ceil(Math.max(0, count - 1) * stagger + CHAR_FOCUS_FRAMES);
}

/** 毛玻璃卡片：上浮 36px、由糊到清、轻微放大落位。tone=dark 用于深色背景。 */
export const GlassPanel: React.FC<{
  children: React.ReactNode;
  appearFrame?: number;
  style?: React.CSSProperties;
  strong?: boolean;
}> = ({ children, appearFrame = 0, style, strong = false }) => {
  const frame = useCurrentFrame();
  const p = progress(frame, appearFrame, 14);
  const settle = progress(frame, appearFrame, 16, EASE_BACK);
  return (
    <div
      style={{
        backgroundColor: strong ? COLORS.glassStrong : COLORS.glass,
        backdropFilter: `blur(${GLASS_BLUR}px) saturate(1.3)`,
        border: `2px solid ${COLORS.glassBorder}`,
        borderRadius: 36,
        boxShadow: SHADOW.card,
        opacity: p,
        translate: `0px ${(1 - p) * 36}px`,
        scale: String(0.96 + settle * 0.04),
        filter: p < 1 ? `blur(${(1 - p) * 10}px)` : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

/** 小标签：卡片左下角「• 规范前」这类说明，参考片的效果名标签。 */
export const Tag: React.FC<{ text: string; opacity?: number; dark?: boolean }> = ({ text, opacity = 1, dark = false }) => (
  <span
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 10,
      fontSize: 28,
      fontWeight: 600,
      letterSpacing: 2,
      color: dark ? COLORS.nightText : COLORS.inkSoft,
      backgroundColor: dark ? "rgba(17, 17, 20, 0.55)" : COLORS.glassStrong,
      border: `1.5px solid ${dark ? "rgba(255, 255, 255, 0.18)" : COLORS.glassBorder}`,
      borderRadius: 999,
      padding: "6px 18px",
      opacity,
    }}
  >
    <span style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.accent }} />
    {text}
  </span>
);

/**
 * 手绘波浪下划线：画在文字下方，由左到右描出。pathLength=1 让虚线长度按比例计算，不依赖实际像素长度。
 * 波形固定（两个半波），不同宽度只做拉伸，保证每次渲染一致。
 */
export const HandUnderline: React.FC<{ width: number; drawFrame: number; color?: string; thickness?: number; frames?: number }> = ({
  width,
  drawFrame,
  color = COLORS.accent,
  thickness = 7,
  frames = 14,
}) => {
  const frame = useCurrentFrame();
  const p = progress(frame, drawFrame, frames);
  const h = 22;
  const path = `M 2 ${h * 0.55} C ${width * 0.18} ${h * 0.05}, ${width * 0.32} ${h * 0.95}, ${width * 0.5} ${h * 0.5} S ${width * 0.82} ${h * 0.1}, ${width - 2} ${h * 0.45}`;
  return (
    <svg width={width} height={h} viewBox={`0 0 ${width} ${h}`} style={{ display: "block", overflow: "visible" }}>
      <path d={path} pathLength={1} fill="none" stroke={color} strokeWidth={thickness} strokeLinecap="round" strokeDasharray="1 1" strokeDashoffset={1 - p} />
    </svg>
  );
};

/**
 * 手绘圈注：略倾斜、首尾交叠的椭圆，框住一个区域。坐标为容器内像素，由调用方定位。
 * 用 4 段三次贝塞尔近似椭圆，第 5 段越过起点形成手绘的交叠感。
 */
export const HandCircle: React.FC<{ x: number; y: number; width: number; height: number; drawFrame: number; color?: string; thickness?: number; frames?: number }> = ({
  x,
  y,
  width,
  height,
  drawFrame,
  color = COLORS.accent,
  thickness = 7,
  frames = 16,
}) => {
  const frame = useCurrentFrame();
  const p = progress(frame, drawFrame, frames);
  const pad = 18;
  const w = width + pad * 2;
  const h = height + pad * 2;
  const k = 0.5523;
  const cx = w / 2;
  const cy = h / 2;
  const rx = w / 2;
  const ry = h / 2;
  const path = [
    `M ${cx - rx * 0.2} ${cy - ry * 1.02}`,
    `C ${cx + rx * k} ${cy - ry * 1.04}, ${cx + rx} ${cy - ry * k}, ${cx + rx} ${cy}`,
    `C ${cx + rx} ${cy + ry * k}, ${cx + rx * k} ${cy + ry}, ${cx} ${cy + ry}`,
    `C ${cx - rx * k} ${cy + ry}, ${cx - rx} ${cy + ry * k}, ${cx - rx} ${cy}`,
    `C ${cx - rx} ${cy - ry * k}, ${cx - rx * k} ${cy - ry * 0.96}, ${cx + rx * 0.25} ${cy - ry * 0.92}`,
  ].join(" ");
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      style={{ position: "absolute", left: x - pad, top: y - pad, overflow: "visible", rotate: "-2deg", pointerEvents: "none" }}
    >
      <path d={path} pathLength={1} fill="none" stroke={color} strokeWidth={thickness} strokeLinecap="round" strokeDasharray="1 1" strokeDashoffset={1 - p} />
    </svg>
  );
};

/**
 * 竖向滚动词列：当前词最亮，上下相邻的词按距离变暗。active 为连续值（可在两个整数之间），
 * 由调用方按帧给出，词与词之间用缓动过渡，看起来像转盘停靠。
 */
export const WordCarousel: React.FC<{ words: string[]; active: number; fontSize: number; color?: string; dimColor?: string }> = ({
  words,
  active,
  fontSize,
  color = COLORS.nightText,
  dimColor = COLORS.nightMuted,
}) => {
  const lineHeight = fontSize * 1.3;
  return (
    <div style={{ position: "relative", height: lineHeight * 3, width: "100%" }}>
      {words.map((word, index) => {
        const distance = Math.abs(index - active);
        const weight = interpolate(distance, [0, 1], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return (
          <div
            key={word}
            style={{
              position: "absolute",
              left: 0,
              top: lineHeight + (index - active) * lineHeight,
              fontSize,
              fontWeight: 600,
              lineHeight: `${lineHeight}px`,
              whiteSpace: "nowrap",
              color: interpolateColors(weight, [0, 1], [dimColor, color]),
              opacity: interpolate(distance, [0, 1.6, 2.2], [1, 0.9, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            }}
          >
            {word}
          </div>
        );
      })}
    </div>
  );
};

/** 按帧计算当前停在第几个词：每个词停留相同时长，切换用 12 帧缓动。 */
export function carouselActive(frame: number, count: number, startFrame: number, holdFrames: number): number {
  let active = 0;
  for (let index = 1; index < count; index += 1) {
    active += progress(frame, startFrame + index * holdFrames, 12);
  }
  return active;
}

/**
 * 圆点迸发：从中心向四周弹出的实心圆点，紫、黑、淡紫三色。位置由固定种子生成，出场带轻微回弹。
 * 用自家几何圆点，不使用任何第三方角色形象。
 */
export const DotBurst: React.FC<{ startFrame: number; count?: number; radius?: number; seed?: number; flatten?: number }> = ({
  startFrame,
  count = 14,
  radius = 380,
  seed = 7,
  // 纵向分布比例：小于 1 时圆点散成横向椭圆，避开上下方的文字；圆点本身仍是正圆
  flatten = 0.8,
}) => {
  const frame = useCurrentFrame();
  const random = seeded(seed);
  const palette = [COLORS.accent, COLORS.ink, COLORS.lavender];
  return (
    <div style={{ position: "absolute", left: "50%", top: "50%", width: 0, height: 0 }}>
      {Array.from({ length: count }, (_, index) => {
        // 黄金角分布让圆点均匀散开，再叠加种子扰动，避免排成规则的圆环
        const angle = index * 2.39996 + random() * 0.5;
        const distance = radius * (0.55 + random() * 0.45);
        const size = 34 + random() * 70;
        const delay = startFrame + random() * 6;
        const p = progress(frame, delay, 18, EASE_BACK);
        const bob = Math.sin((frame + index * 11) / 14) * 6 * progress(frame, delay + 18, 10);
        return (
          <div
            key={index}
            style={{
              position: "absolute",
              width: size,
              height: size,
              borderRadius: size / 2,
              backgroundColor: palette[index % palette.length],
              left: Math.cos(angle) * distance * p - size / 2,
              top: Math.sin(angle) * distance * flatten * p - size / 2 + bob,
              scale: String(p),
              opacity: Math.min(1, p * 3),
            }}
          />
        );
      })}
    </div>
  );
};

export { EASE_OUT };
