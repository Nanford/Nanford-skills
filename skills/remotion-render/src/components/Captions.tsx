/**
 * INPUT: timeline.tracks.caption（全局帧区间与文字）
 * OUTPUT: Captions 组件：当前帧对应的一条字幕，位于底部避让区上方
 * POS: 字幕层。字幕时间来自真实配音时间戳，这里只按帧显示，不再推算时间。
 */

import React from "react";
import { useCurrentFrame } from "remotion";
import type { CaptionClip } from "../types";
import { CAPTION_TEXT_WIDTH, COLORS, FONT_FAMILY, GLASS_BLUR, KEEP_WORDS, SAFE, fitFontSize } from "../theme";

// 字幕字号：常规 56px；超宽的一行缩小到能单行放下，但不低于 48px，保证手机上可读
const CAPTION_MAX_SIZE = 56;
const CAPTION_MIN_SIZE = 48;

export const Captions: React.FC<{ captions: CaptionClip[] }> = ({ captions }) => {
  const frame = useCurrentFrame();
  const active = captions.find((caption) => frame >= caption.start_frame && frame < caption.end_frame);
  if (!active) {
    return null;
  }
  // 字幕技能按约 16 个字宽断句，而右侧避让区让一行只容得下约 13.8 个字宽（56px）。
  // 缩字号保持单行，比折成两行更不容易把词拆开；低于 48px 仍放不下时才按词折行。
  const fontSize = Math.max(CAPTION_MIN_SIZE, fitFontSize([active.text], CAPTION_MAX_SIZE, CAPTION_TEXT_WIDTH));
  return (
    <div
      style={{
        position: "absolute",
        left: SAFE.left,
        right: SAFE.right,
        bottom: SAFE.bottom + 20,
        display: "flex",
        justifyContent: "center",
        fontFamily: FONT_FAMILY,
      }}
    >
      {/* 毛玻璃白底 + 近黑字：浅灰底、深色章节页、风景照片上都清楚，且与卡片同一材质 */}
      <span
        style={{
          backgroundColor: "rgba(255, 255, 255, 0.78)",
          backdropFilter: `blur(${GLASS_BLUR}px) saturate(1.3)`,
          border: "1.5px solid rgba(255, 255, 255, 0.9)",
          boxShadow: "0 10px 30px rgba(34, 24, 84, 0.12)",
          color: COLORS.ink,
          fontSize,
          fontWeight: 600,
          lineHeight: 1.35,
          padding: "10px 26px",
          borderRadius: 22,
          textAlign: "center",
          ...KEEP_WORDS,
        }}
      >
        {active.text}
      </span>
    </div>
  );
};
