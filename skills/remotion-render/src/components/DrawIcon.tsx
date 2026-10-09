/**
 * INPUT: icons/lucide.ts 的图标元素；theme.ts 颜色与缓动
 * OUTPUT: DrawIcon：线性图标逐笔描出，描完轻微回弹落位
 * POS: 文字动效与卡片的图标层。每个 SVG 元素都设 pathLength=1，圆、矩形、折线与路径按同一比例描出，笔画速度一致。
 */

import React from "react";
import { useCurrentFrame } from "remotion";
import { LUCIDE_ICONS } from "../icons/lucide";
import { COLORS, EASE_BACK, progress } from "../theme";

export const DrawIcon: React.FC<{
  name: string;
  size: number;
  startFrame: number;
  drawFrames: number;
  stagger: number;
  color?: string;
  // 24 网格里的线宽；放大到 size 后实际像素 = strokeWidth × size / 24
  strokeWidth?: number;
}> = ({ name, size, startFrame, drawFrames, stagger, color = COLORS.accent, strokeWidth = 1.75 }) => {
  const frame = useCurrentFrame();
  const elements = LUCIDE_ICONS[name];
  if (!elements) throw new Error(`未收录的图标：${name}（见 src/icons/lucide.ts）`);
  const lastEnd = startFrame + (elements.length - 1) * stagger + drawFrames;
  const settle = progress(frame, startFrame, lastEnd - startFrame, EASE_BACK);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ display: "block", overflow: "visible", scale: String(0.86 + settle * 0.14), opacity: Math.min(1, settle * 4) }}
    >
      {elements.map((element, index) => {
        const p = progress(frame, startFrame + index * stagger, drawFrames);
        return React.createElement(element.tag, {
          key: index,
          ...element.attrs,
          pathLength: 1,
          strokeDasharray: "1 1",
          strokeDashoffset: 1 - p,
        });
      })}
    </svg>
  );
};
