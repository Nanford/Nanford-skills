/**
 * INPUT: kinetic.ts 的 TIMING、KINETIC_LAYOUT；theme.ts 颜色、缓动与语义色；Motion.tsx 的 ToneText
 * OUTPUT: LineProps、lineStyle（动效文字的统一行样式）、PopLine（弹出一行，strike / dissolve 换上说法也用它）
 * POS: KineticLines 与 KineticCharLines 共用的基础件，单独成文件以免两者互相导入。
 */

import React from "react";
import { useCurrentFrame } from "remotion";
import { ToneText } from "./Motion";
import { COLORS, EASE_BACK, progress, type Tone } from "../theme";
import { KINETIC_LAYOUT, TIMING, type PlannedBeat } from "../kinetic";

export interface LineProps {
  beat: PlannedBeat;
  fontSize: number;
}

export const lineStyle = (fontSize: number): React.CSSProperties => ({
  fontSize,
  fontWeight: 800,
  lineHeight: KINETIC_LAYOUT.lineHeight,
  whiteSpace: "nowrap",
  color: COLORS.ink,
  display: "inline-block",
});

/** 弹出：由 0 放大到 1，略冲过头再回落。 */
export const PopLine: React.FC<{ text: string; start: number; fontSize: number; defaultTone: Tone }> = ({ text, start, fontSize, defaultTone }) => {
  const frame = useCurrentFrame();
  const grow = progress(frame, start, TIMING.pop.grow, EASE_BACK);
  return (
    <span style={{ ...lineStyle(fontSize), opacity: Math.min(1, grow * 3), scale: String(grow) }}>
      <ToneText text={text} defaultTone={defaultTone} />
    </span>
  );
};

