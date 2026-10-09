/**
 * INPUT: params.kicker、big（大字或数字）、可选 tone（大字的语义色，默认品牌紫）、unit、sub、note、chips（标签）、source（来源说明）、可选 wallpaper
 * OUTPUT: 证据卡场景：风景底上的毛玻璃卡片，数字从 0 计到目标值，标签依次出现，底部显示来源
 * POS: 展示有来源的事实（招聘数量、薪资、实测用时、格式参数）。数值必须来自 claims.json 已核实条目，来源文字随画面显示。
 */

import React from "react";
import { useCurrentFrame } from "remotion";
import { GlassPanel, Tag, countUp } from "../components/Motion";
import { Kicker, SceneShell, SourceNote } from "../components/Frame";
import { COLORS, KEEP_WORDS, PANEL, TEXT_COLUMN_WIDTH, fitFontSize, listParam, progress, resolveTone, stringParam, toneColor } from "../theme";

function displayBig(text: string, frame: number): string {
  // 纯数字从 0 计到目标值，24 帧内完成；动画只改变显示，终值与事实表一致
  return /^\d+$/.test(text) ? String(countUp(Number(text), frame, 6, 24)) : text;
}

export const EvidenceCard: React.FC<{ params: Record<string, unknown> }> = ({ params }) => {
  const frame = useCurrentFrame();
  const big = stringParam(params, "big");
  const note = stringParam(params, "note");
  const chips = listParam(params, "chips");
  // 大字的语义色：默认品牌紫；数字类事实可写 tone: "数据"，风险类写 "痛点"
  const bigColor = toneColor(resolveTone(stringParam(params, "tone", "brand")));
  return (
    <SceneShell backdrop="wallpaper" wallpaper={stringParam(params, "wallpaper", "alpenglow")}>
      <Kicker text={stringParam(params, "kicker")} opacity={progress(frame, 0, 10)} />
      <GlassPanel appearFrame={2} strong style={{ width: PANEL.width, padding: "48px 56px", textAlign: "center" }}>
        {big ? (
          <div style={{ fontSize: fitFontSize([big], 260, TEXT_COLUMN_WIDTH), fontWeight: 800, lineHeight: 1.05, whiteSpace: "nowrap", color: bigColor, letterSpacing: -2 }}>
            {displayBig(big, frame)}
          </div>
        ) : null}
        <div style={{ fontSize: 52, fontWeight: 700, marginTop: 14, color: COLORS.ink, opacity: progress(frame, 10, 12) }}>{stringParam(params, "unit")}</div>
        <div style={{ fontSize: 42, color: COLORS.inkSoft, marginTop: 10, opacity: progress(frame, 13, 12), ...KEEP_WORDS }}>{stringParam(params, "sub")}</div>
        {note ? (
          <div style={{ marginTop: 32, fontSize: 44, fontWeight: 600, lineHeight: 1.4, color: COLORS.ink, opacity: progress(frame, 18, 12), ...KEEP_WORDS }}>{note}</div>
        ) : null}
        {chips.length ? (
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 16, marginTop: 34 }}>
            {chips.map((chip, index) => (
              <Tag key={`${index}-${chip}`} text={chip} opacity={progress(frame, (big ? 20 : 8) + index * 4, 10)} />
            ))}
          </div>
        ) : null}
      </GlassPanel>
      <SourceNote text={stringParam(params, "source")} opacity={progress(frame, 24, 12)} glass />
    </SceneShell>
  );
};
