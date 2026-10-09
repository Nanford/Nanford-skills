/**
 * INPUT: params.beats（1～4 拍：{text, effect: drop / pop / count / strike / highlight / type / fly / dissolve, at, replace?, out_at?}，文字里 {词|痛点} 指定语义色）、可选 params.icon（src/icons/lucide.ts 收录的图标名）
 * OUTPUT: 纯文字动效场景：图标逐笔描出，关键词按拍落下、弹出、数字滚动、划掉换词、荧光笔扫过、打字输入、逐字飞入飞出或粒子消散，竖向居中排列
 * POS: 没有截图可展示、需要把一句结论或对比「做成动作」的镜头。浅灰底，与 ResultHook 同一字体与紫色强调。
 *      时间全部来自 kinetic.ts 的 planKinetic，动作标记可直接对音效。2026-10-09 新增并经主理人确认，系列规则见 docs/DESIGN.md 第 4 节。
 */

import React, { useContext } from "react";
import { DrawIcon } from "../components/DrawIcon";
import { KineticLine } from "../components/KineticLines";
import { PrerollFrames, SceneShell } from "../components/Frame";
import { CONTENT_BOTTOM, CONTENT_TOP, TEXT_COLUMN_WIDTH, fitFontSize, stringParam } from "../theme";
import { KINETIC_LAYOUT, TIMING, heightFontLimit, parseKineticBeats, planKinetic, type KineticBeat } from "../kinetic";

const ICON_SIZE = 150;

/** 参与字号计算的所有行：strike 的错误说法缩到 0.82 倍显示，按原字号计算即可保守放下；dissolve 换上的说法与原文同一位置，也要放得下。 */
function layoutLines(beats: KineticBeat[]): string[] {
  return beats.flatMap((beat) => (beat.replace ? [beat.text, beat.replace] : [beat.text]));
}

export const KineticText: React.FC<{ params: Record<string, unknown>; durationInFrames: number }> = ({ params, durationInFrames }) => {
  const preroll = useContext(PrerollFrames);
  const icon = stringParam(params, "icon");
  const beats = parseKineticBeats(params);
  const plan = planKinetic(beats, durationInFrames, preroll, Boolean(icon));
  // 宽度与高度各算一个上限取较小值：拍数多、strike 多时整列仍放在字幕区上方
  const iconSize = icon ? ICON_SIZE : 0;
  const fontSize = Math.min(fitFontSize(layoutLines(beats), 112, TEXT_COLUMN_WIDTH), heightFontLimit(beats, iconSize, CONTENT_BOTTOM - CONTENT_TOP));
  return (
    <SceneShell backdrop="paper">
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: fontSize * KINETIC_LAYOUT.gap, width: TEXT_COLUMN_WIDTH, textAlign: "center" }}>
        {icon ? (
          <div style={{ marginBottom: fontSize * KINETIC_LAYOUT.iconMargin }}>
            <DrawIcon name={icon} size={ICON_SIZE} startFrame={plan.iconStart} drawFrames={TIMING.icon.draw} stagger={TIMING.icon.stagger} />
          </div>
        ) : null}
        {plan.beats.map((beat, index) => (
          <KineticLine key={index} beat={beat} fontSize={fontSize} />
        ))}
      </div>
    </SceneShell>
  );
};
