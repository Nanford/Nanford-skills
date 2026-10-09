/**
 * INPUT: CoverProps（kicker、title 分行大字（{…} 标强调，{词|痛点} 指定语义色，默认品牌紫）、sub 副标题，两者都可用 \n 分行；账号名、AI 标识）
 * OUTPUT: CoverStill 组件：1080×1920 竖版封面（浅灰底、近黑大字、紫色强调词下方手绘波浪线）
 * POS: 封面由排版层绘制文字，不依赖图像模型生成文字。重要文字放在中上部，平台裁切以实际上传预览为准。
 */

import React from "react";
import { AbsoluteFill } from "remotion";
import "./fonts";
import { Backdrop, Chrome } from "./components/Frame";
import { HandUnderline } from "./components/Motion";
import { COLORS, FONT_FAMILY, SAFE, TEXT_COLUMN_WIDTH, fitFontSize, parseAccent, textUnits, toneColor, type Tone } from "./theme";
import type { CoverProps } from "./types";

const TitleLine: React.FC<{ line: string; fontSize: number }> = ({ line, fontSize }) => {
  let before = "";
  let underline: { left: number; width: number; tone: Tone } | null = null;
  const runs = parseAccent(line);
  for (const run of runs) {
    if (run.tone && !underline) underline = { left: textUnits(before), width: textUnits(run.text), tone: run.tone };
    before += run.text;
  }
  const lineUnits = textUnits(line);
  return (
    <div style={{ lineHeight: 1.22, marginTop: 18 }}>
      <span style={{ position: "relative", display: "inline-block", fontSize, fontWeight: 800, whiteSpace: "nowrap" }}>
        {runs.map((run, index) => (
          <span key={index} style={{ color: run.tone ? toneColor(run.tone) : COLORS.ink }}>
            {run.text}
          </span>
        ))}
        {underline ? (
          <span style={{ position: "absolute", left: `${(underline.left / lineUnits) * 100}%`, width: `${(underline.width / lineUnits) * 100}%`, top: "98%" }}>
            {/* 封面是静帧：drawFrame 取负值让波浪线在第 0 帧已画满 */}
            <HandUnderline width={underline.width * fontSize} drawFrame={-100} color={toneColor(underline.tone)} thickness={Math.max(8, fontSize * 0.075)} />
          </span>
        ) : null}
      </span>
    </div>
  );
};

export const CoverStill: React.FC<CoverProps> = ({ kicker, title, sub, brand, aiLabel }) => {
  const lines = title.split("\n");
  const subLines = sub.split("\n");
  // 封面大字与副标题都按最长一行缩放，分行完全由文字中的 \n 决定，不让浏览器在词中间折行
  const titleSize = fitFontSize(lines, 150, TEXT_COLUMN_WIDTH);
  const subSize = fitFontSize(subLines, 60, TEXT_COLUMN_WIDTH);
  return (
    <AbsoluteFill style={{ fontFamily: FONT_FAMILY, color: COLORS.ink }}>
      <Backdrop kind="paper" />
      <Chrome brand={brand} aiLabel={aiLabel} />
      <div style={{ position: "absolute", left: SAFE.right, right: SAFE.right, top: 440, textAlign: "center" }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 16,
            fontSize: 46,
            fontWeight: 600,
            color: COLORS.inkSoft,
            backgroundColor: "#FFFFFF",
            border: `1.5px solid ${COLORS.hairline}`,
            borderRadius: 999,
            padding: "10px 32px",
            boxShadow: "0 8px 24px rgba(34, 24, 84, 0.08)",
          }}
        >
          <span style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: COLORS.accent }} />
          {kicker}
        </span>
        <div style={{ marginTop: 40 }}>
          {lines.map((line, index) => (
            <TitleLine key={`${index}-${line}`} line={line} fontSize={titleSize} />
          ))}
        </div>
        <div style={{ marginTop: 70, fontSize: subSize, fontWeight: 600, lineHeight: 1.35, color: COLORS.inkSoft }}>
          {subLines.map((line, index) => (
            <div key={`${index}-${line}`} style={{ whiteSpace: "nowrap" }}>
              {line}
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
