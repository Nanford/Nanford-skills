/**
 * INPUT: params.lead（左侧紫色引导词，如「写清楚」）、params.words（右侧滚动词列，2～6 个，如 字体 / 字号 / 颜色 / 行距）
 * OUTPUT: 深色章节页：引导词对焦出现，右侧词列像转盘一样逐个停靠，当前词最亮、相邻词变暗，最后停在最后一个词上
 * POS: 段落之间的节奏点与要点清单的快速点名。深色底与前后浅色镜头形成反差，镜头之间仍是硬切。
 */

import React from "react";
import { useCurrentFrame } from "remotion";
import { RevealText, WordCarousel, carouselActive } from "../components/Motion";
import { SceneShell } from "../components/Frame";
import { COLORS, TEXT_COLUMN_WIDTH, listParam, progress, stringParam, textUnits } from "../theme";

const GAP_UNITS = 0.6;

export const ChapterDivider: React.FC<{ params: Record<string, unknown>; durationInFrames: number }> = ({ params, durationInFrames }) => {
  const frame = useCurrentFrame();
  const lead = stringParam(params, "lead");
  const words = listParam(params, "words");
  if (!words.length) {
    throw new Error("ChapterDivider 需要 params.words（至少 1 个词）");
  }
  // 引导词 + 间距 + 最长的词 放进居中文字列，字号上限 100
  const widest = Math.max(...words.map(textUnits));
  const fontSize = Math.min(100, Math.floor((TEXT_COLUMN_WIDTH * 0.96) / (textUnits(lead) + GAP_UNITS + widest)));
  // 第一个词随词列一起出现；第 k 个词在 10 + k×hold 帧停靠，每个词停留相同时长，最后一个词停到镜头结束
  const hold = Math.max(14, Math.floor((durationInFrames - 16) / words.length));
  const active = carouselActive(frame, words.length, 10, hold);
  const listIn = progress(frame, 4, 12);
  return (
    <SceneShell backdrop="night">
      <div style={{ display: "flex", alignItems: "center", gap: fontSize * GAP_UNITS, width: TEXT_COLUMN_WIDTH, justifyContent: "center" }}>
        <div style={{ flexShrink: 0 }}>
          <RevealText text={lead} fontSize={fontSize} weight={600} color={COLORS.accentBright} fromColor="#2A2340" startFrame={0} stagger={1.2} />
        </div>
        <div style={{ width: widest * fontSize, opacity: listIn, translate: `${(1 - listIn) * 24}px 0px` }}>
          <WordCarousel words={words} active={active} fontSize={fontSize} />
        </div>
      </div>
    </SceneShell>
  );
};
