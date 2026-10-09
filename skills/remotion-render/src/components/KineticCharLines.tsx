/**
 * INPUT: kinetic.ts 的每拍时间表、TIMING、DEFAULT_TONES、typedCount、dissolveReplaceFrame；markup.ts 的 toneChars（逐字带色）；
 *        theme.ts 颜色与缓动；Motion.tsx 的 seeded；KineticBase.tsx 的行样式与弹出
 * OUTPUT: TypeLine（打字输入 + 闪烁光标）、FlyLine（逐字飞入，可飞出）、DissolveLine（粒子消散，可在原位换上新说法）
 * POS: KineticText 的逐字效果。三种效果都把整行字先排好再逐字改变颜色、位置或透明度，行宽从头到尾不变，
 *      居中排版不会随打字左右移动。全部由帧号计算，颗粒位置用固定种子，同一输入每次渲染一致。
 */

import React from "react";
import { Easing, useCurrentFrame } from "remotion";
import { seeded } from "./Motion";
import { PopLine, lineStyle, type LineProps } from "./KineticBase";
import { COLORS, EASE_OUT, progress, toneColor, type Tone } from "../theme";
import { toneChars } from "../markup";
import { DEFAULT_TONES, TIMING, dissolveReplaceFrame, typedCount } from "../kinetic";

const EASE_IN = Easing.bezier(0.55, 0, 0.9, 0.45);
// 粒子消散：每个字碎成的颗粒数。首版 8 颗、字号 4%～11% 在成片里偏淡，加到 12 颗、5%～13%
const PARTICLES_PER_CHAR = 12;

const charColor = (tone: Tone | null): string => (tone ? toneColor(tone) : COLORS.ink);

/** 打字：逐字显现（未打出的字透明占位），光标跟在最后一个字后面；打完后光标闪 cursorTail 帧再消失。 */
export const TypeLine: React.FC<LineProps> = ({ beat, fontSize }) => {
  const frame = useCurrentFrame();
  const chars = toneChars(beat.text, DEFAULT_TONES.type.text);
  const typed = frame < beat.start ? 0 : typedCount(beat, frame);
  const done = beat.settle;
  const blinkOn = Math.floor((frame - done) / (TIMING.type.blink / 2)) % 2 === 0;
  const showCursor = frame >= beat.start && (frame < done || (frame < done + TIMING.type.cursorTail && blinkOn));
  const cursor = (
    // 零宽容器放光标：光标不占行宽，整行位置不因光标移动
    <span style={{ position: "relative", display: "inline-block", width: 0 }}>
      <span style={{ position: "absolute", left: fontSize * 0.04, top: -fontSize * 0.92, width: Math.max(5, fontSize * 0.07), height: fontSize * 1.02, borderRadius: 3, backgroundColor: toneColor("brand") }} />
    </span>
  );
  return (
    <span style={lineStyle(fontSize)}>
      {showCursor && typed === 0 ? cursor : null}
      {chars.map((item, index) => (
        <React.Fragment key={index}>
          <span style={{ whiteSpace: "pre", color: index < typed ? charColor(item.tone) : "transparent" }}>{item.char}</span>
          {showCursor && index === typed - 1 ? cursor : null}
        </React.Fragment>
      ))}
    </span>
  );
};

/** 飞入：每个字从右侧带模糊滑入，逐字错开；写了 out_at 时到点向左加速飞出。 */
export const FlyLine: React.FC<LineProps> = ({ beat, fontSize }) => {
  const frame = useCurrentFrame();
  const chars = toneChars(beat.text, DEFAULT_TONES.fly.text);
  const distance = fontSize * 0.9;
  return (
    <span style={lineStyle(fontSize)}>
      {chars.map((item, index) => {
        const enter = progress(frame, beat.start + index * TIMING.fly.stagger, TIMING.fly.frames, EASE_OUT);
        const leave = beat.exit === null ? 0 : progress(frame, beat.exit + index * TIMING.fly.stagger, TIMING.fly.frames, EASE_IN);
        const blur = (1 - enter) * 10 + leave * 10;
        return (
          <span
            key={index}
            style={{
              display: "inline-block",
              whiteSpace: "pre",
              color: charColor(item.tone),
              opacity: enter * (1 - leave),
              translate: `${(1 - enter) * distance - leave * distance}px 0px`,
              filter: blur > 0.01 ? `blur(${blur}px)` : undefined,
            }}
          >
            {item.char}
          </span>
        );
      })}
    </span>
  );
};

/** 一个字碎开的颗粒：从字形范围内的随机位置出发，向右上方飘散、缩小、淡出。 */
const Particles: React.FC<{ seed: number; start: number; fontSize: number; color: string }> = ({ seed, start, fontSize, color }) => {
  const frame = useCurrentFrame();
  if (frame < start) return null;
  const t = progress(frame, start, TIMING.dissolve.drift, EASE_OUT);
  const random = seeded(seed);
  return (
    <>
      {Array.from({ length: PARTICLES_PER_CHAR }, (_, index) => {
        const x = random() * fontSize;
        const y = (0.2 + random() * 0.8) * fontSize;
        const dx = (0.3 + random() * 1.3) * fontSize * t;
        const dy = -(0.2 + random() * 1.1) * fontSize * t;
        const size = fontSize * (0.05 + random() * 0.08) * (1 - t * 0.6);
        return (
          <span
            key={index}
            style={{ position: "absolute", left: x + dx, top: y + dy, width: size, height: size, borderRadius: size * 0.25, backgroundColor: color, opacity: (1 - t) ** 1.2, rotate: `${(random() - 0.5) * 120 * t}deg` }}
          />
        );
      })}
    </>
  );
};

/** 粒子消散：整行上浮出现；到退场帧后从左到右逐字碎成颗粒飘走。写了 replace 时，新说法在同一位置弹出。 */
export const DissolveLine: React.FC<LineProps> = ({ beat, fontSize }) => {
  const frame = useCurrentFrame();
  const chars = toneChars(beat.text, DEFAULT_TONES.dissolve.text);
  const reveal = progress(frame, beat.start, TIMING.dissolve.reveal);
  const exit = beat.exit ?? beat.start;
  return (
    <span style={{ position: "relative", display: "inline-block" }}>
      <span style={{ ...lineStyle(fontSize), opacity: reveal, translate: `0px ${(1 - reveal) * 30}px` }}>
        {chars.map((item, index) => {
          const crumble = exit + Math.round(index * TIMING.dissolve.stagger);
          const fade = progress(frame, crumble, TIMING.dissolve.fade);
          const color = charColor(item.tone);
          return (
            <span key={index} style={{ position: "relative", display: "inline-block", whiteSpace: "pre" }}>
              <span style={{ color, opacity: 1 - fade, filter: fade > 0 ? `blur(${fade * 6}px)` : undefined }}>{item.char}</span>
              {item.char.trim() ? <Particles seed={beat.start * 131 + index * 17 + 1} start={crumble} fontSize={fontSize} color={color} /> : null}
            </span>
          );
        })}
      </span>
      {beat.replace ? (
        <span style={{ position: "absolute", left: "50%", top: 0, translate: "-50% 0px" }}>
          <PopLine text={beat.replace} start={dissolveReplaceFrame(beat)} fontSize={fontSize} defaultTone={DEFAULT_TONES.dissolve.replace} />
        </span>
      ) : null}
    </span>
  );
};
