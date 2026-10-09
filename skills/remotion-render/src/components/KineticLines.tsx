/**
 * INPUT: kinetic.ts 的每拍时间表、TIMING 与 DEFAULT_TONES；theme.ts 颜色、缓动与语义色；Motion.tsx 的 RevealText、ToneText；KineticBase.tsx 的行样式与弹出；KineticCharLines.tsx 的逐字效果
 * OUTPUT: KineticLine：按效果渲染一行文字——drop（落下挤压回弹）、pop（弹出）、count（数字滚动）、strike（划掉换词）、highlight（荧光笔扫过强调词），
 *         type / fly / dissolve 转交 KineticCharLines
 * POS: KineticText 场景的单行动画。所有关键帧都取自 planKinetic 的整数帧，组件不另算时间，保证画面与动作标记同源。
 *      没写语义色的 {…} 按效果取默认色（DEFAULT_TONES）：划掉的旧说法痛点色、换上的说法解法色、数字数据色，其余品牌紫。
 */

import React from "react";
import { interpolate, interpolateColors, useCurrentFrame } from "remotion";
import { RevealText, ToneText } from "./Motion";
import { DissolveLine, FlyLine, TypeLine } from "./KineticCharLines";
import { PopLine, lineStyle, type LineProps } from "./KineticBase";
import { COLORS, EASE_BACK, progress, toneColor } from "../theme";
import { DEFAULT_TONES, KINETIC_LAYOUT, TIMING, countText, countValue } from "../kinetic";

const LINE_HEIGHT = KINETIC_LAYOUT.lineHeight;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/**
 * 落下：前 fall 帧加速下落（略拉长），触地一帧压扁，之后回弹站稳。以字底为轴变形，像落在地面上。
 * 外层按本行上沿裁切：字从本行上方「掉进」自己的位置，不会穿过上一行文字或图标；左右与下方留出挤压变宽的余量。
 */
const DropLine: React.FC<LineProps> = ({ beat, fontSize }) => {
  const frame = useCurrentFrame();
  const fall = Math.min(1, Math.max(0, (frame - beat.start) / TIMING.drop.fall));
  const landed = frame >= beat.start + TIMING.drop.fall;
  const recover = progress(frame, beat.start + TIMING.drop.fall, TIMING.drop.settle - TIMING.drop.fall, EASE_BACK);
  // 下落用二次加速（t²），触地瞬间速度最大，挤压才显得有分量
  const y = -(1 - fall * fall) * fontSize * 1.4;
  const squash = landed ? 1 - 0.16 * (1 - recover) : 1 + 0.06 * fall;
  return (
    <span style={{ display: "inline-block", clipPath: "inset(0px -12% -30% -12%)" }}>
      <span style={{ ...lineStyle(fontSize), opacity: fall > 0 ? 1 : 0, translate: `0px ${y}px`, transformOrigin: "50% 100%", scale: `${2 - squash} ${squash}` }}>
        <ToneText text={beat.text} defaultTone={DEFAULT_TONES.drop.text} />
      </span>
    </span>
  );
};

/** 数字滚动：整行上浮出现，数字从 0 滚到目标值；透明的 0 补位（字体数字本身等宽），整行不抖。 */
const CountLine: React.FC<LineProps> = ({ beat, fontSize }) => {
  const frame = useCurrentFrame();
  const reveal = progress(frame, beat.start, TIMING.count.reveal);
  return (
    <span style={{ ...lineStyle(fontSize), opacity: reveal, translate: `0px ${(1 - reveal) * 30}px` }}>
      <ToneText text={countText(beat.text, countValue(beat, frame))} defaultTone={DEFAULT_TONES.count.text} />
    </span>
  );
};

/** 划掉：错误说法逐字出现 → 一道痛点色的线从左到右划过并变淡 → 下一行弹出正确说法。 */
const StrikeLine: React.FC<LineProps> = ({ beat, fontSize }) => {
  const frame = useCurrentFrame();
  const strikeStart = beat.start + TIMING.strike.strikeAt;
  const cut = progress(frame, strikeStart, TIMING.strike.strikeFrames);
  const dim = interpolate(frame, [strikeStart, strikeStart + TIMING.strike.strikeFrames], [0, 1], clamp);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
      <span style={{ position: "relative", display: "inline-block", opacity: 1 - dim * 0.45 }}>
        <RevealText
          text={beat.text}
          fontSize={fontSize * KINETIC_LAYOUT.strikeScale}
          weight={700}
          startFrame={beat.start}
          stagger={1}
          lineHeight={LINE_HEIGHT}
          defaultTone={DEFAULT_TONES.strike.text}
          color={interpolateColors(dim, [0, 1], [COLORS.ink, COLORS.inkSoft])}
        />
        {/* 划线用实心圆角条从左向右伸出（略微倾斜像手划），不用虚线描边，避免未划时残留端点 */}
        <span
          style={{
            position: "absolute",
            left: "-3%",
            top: "52%",
            width: `${cut * 106}%`,
            height: Math.max(6, fontSize * 0.07),
            borderRadius: 999,
            backgroundColor: toneColor(DEFAULT_TONES.strike.text),
            rotate: "-2deg",
            transformOrigin: "0% 50%",
            opacity: cut > 0 ? 1 : 0,
          }}
        />
      </span>
      <PopLine text={beat.replace ?? ""} start={beat.start + TIMING.strike.replaceAt} fontSize={fontSize} defaultTone={DEFAULT_TONES.strike.replace} />
    </div>
  );
};

/** 荧光笔：整行由糊到清上浮，然后同色系浅色块从左到右扫过强调词。 */
const HighlightLine: React.FC<LineProps> = ({ beat, fontSize }) => {
  const frame = useCurrentFrame();
  const reveal = progress(frame, beat.start, TIMING.highlight.reveal);
  const sweep = progress(frame, beat.start + TIMING.highlight.sweepAt, TIMING.highlight.sweepFrames);
  return (
    <span style={{ ...lineStyle(fontSize), opacity: reveal, translate: `0px ${(1 - reveal) * 30}px`, filter: reveal < 1 ? `blur(${(1 - reveal) * 8}px)` : undefined }}>
      <ToneText text={beat.text} sweep={sweep} defaultTone={DEFAULT_TONES.highlight.text} />
    </span>
  );
};

export const KineticLine: React.FC<LineProps> = ({ beat, fontSize }) => {
  switch (beat.effect) {
    case "drop":
      return <DropLine beat={beat} fontSize={fontSize} />;
    case "pop":
      return <PopLine text={beat.text} start={beat.start} fontSize={fontSize} defaultTone={DEFAULT_TONES.pop.text} />;
    case "count":
      return <CountLine beat={beat} fontSize={fontSize} />;
    case "strike":
      return <StrikeLine beat={beat} fontSize={fontSize} />;
    case "highlight":
      return <HighlightLine beat={beat} fontSize={fontSize} />;
    case "type":
      return <TypeLine beat={beat} fontSize={fontSize} />;
    case "fly":
      return <FlyLine beat={beat} fontSize={fontSize} />;
    case "dissolve":
      return <DissolveLine beat={beat} fontSize={fontSize} />;
  }
};
