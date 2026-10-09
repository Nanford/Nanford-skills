/**
 * INPUT: params.title（\n 分行，{…} 标紫色）、params.sub（互动提示）；账号名由上层传入
 * OUTPUT: 收尾场景：问题大字逐字对焦 → 互动胶囊弹出后倾斜并由白底翻成黑底，同时两侧迸出圆点 → 账号名
 * POS: 片尾互动。不承诺未制作的后续内容，只抛出与主题相关的问题。
 */

import React from "react";
import { interpolate, interpolateColors, useCurrentFrame } from "remotion";
import { DotBurst, RevealText } from "../components/Motion";
import { SceneShell } from "../components/Frame";
import { COLORS, EASE_BACK, TEXT_COLUMN_WIDTH, fitFontSize, progress, stringParam } from "../theme";

// 胶囊：14 帧弹出，26～34 帧倾斜并翻色，同时圆点迸发
const PILL_IN = 14;
const FLIP_AT = 26;

export const ActionEnd: React.FC<{ params: Record<string, unknown>; brand: string }> = ({ params, brand }) => {
  const frame = useCurrentFrame();
  const lines = stringParam(params, "title").split("\n");
  const fontSize = fitFontSize(lines, 96, TEXT_COLUMN_WIDTH);
  const pillIn = progress(frame, PILL_IN, 12, EASE_BACK);
  const flip = progress(frame, FLIP_AT, 8);
  // 翻色后缓慢上下浮动，提示互动；按帧计算，每次渲染结果相同
  const float = Math.sin(((frame - FLIP_AT) / 30) * Math.PI) * 5 * progress(frame, FLIP_AT + 8, 10);
  return (
    <SceneShell backdrop="paper">
      <div style={{ width: TEXT_COLUMN_WIDTH, textAlign: "center" }}>
        {lines.map((line, index) => (
          <div key={`${index}-${line}`} style={{ lineHeight: 1.3 }}>
            <RevealText text={line} fontSize={fontSize} weight={700} startFrame={index * 6} stagger={1} />
          </div>
        ))}
      </div>
      <div style={{ position: "relative", marginTop: 120, height: 130, width: TEXT_COLUMN_WIDTH, display: "flex", justifyContent: "center", alignItems: "center" }}>
        {/* 圆点按横向椭圆分布在胶囊两侧：纵向最远约 105px + 圆点半径，小于与上方问题文字的间距，不会遮字 */}
        <DotBurst startFrame={FLIP_AT} count={12} radius={420} flatten={0.25} />
        <span
          style={{
            position: "relative",
            fontSize: 52,
            fontWeight: 700,
            borderRadius: 999,
            padding: "16px 42px",
            backgroundColor: interpolateColors(flip, [0, 1], ["#FFFFFF", COLORS.ink]),
            color: interpolateColors(flip, [0, 1], [COLORS.ink, "#FFFFFF"]),
            boxShadow: "0 14px 36px rgba(34, 24, 84, 0.18)",
            opacity: Math.min(1, pillIn * 2),
            scale: String(0.6 + pillIn * 0.4),
            rotate: `${interpolate(flip, [0, 1], [0, -5])}deg`,
            translate: `0px ${float}px`,
          }}
        >
          {stringParam(params, "sub")}
        </span>
      </div>
      <div style={{ marginTop: 120, fontSize: 36, fontWeight: 600, color: COLORS.inkSoft, opacity: progress(frame, 20, 12) }}>{brand}</div>
    </SceneShell>
  );
};
