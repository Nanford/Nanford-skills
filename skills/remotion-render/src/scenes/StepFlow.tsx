/**
 * INPUT: params.title（{…} 标强调，{词|痛点} 指定语义色）、params.items（2～4 条，可用 {…} 强调）、params.variant（problem / steps / check）、可选 params.tone（条目标记的语义色）、可选 params.footnote、params.wallpaper
 * OUTPUT: 清单场景：风景底上的毛玻璃卡片，条目逐行浮现；problem 用深色叉号、steps 用紫色编号、check 用紫色对勾
 * POS: 表达问题清单、操作步骤、能力清单。条目在镜头前 60% 时长内依次出现，跟上口播节奏。
 */

import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { GlassPanel, RevealText, ToneText } from "../components/Motion";
import { SceneShell, SourceNote } from "../components/Frame";
import { COLORS, KEEP_WORDS, PANEL, STEP_TEXT_WIDTH, TEXT_COLUMN_WIDTH, TONES, fitFontSize, listParam, progress, resolveTone, stringParam, toneColor } from "../theme";

type Variant = "problem" | "steps" | "check";

// 默认样式：问题项用深色叉号 + 浅灰圆底，编号与对勾用品牌紫。写了 params.tone 时改用该语义色（见 markerStyle）
const VARIANT_STYLE: Record<Variant, { background: string; color: string; icon: (index: number) => string }> = {
  problem: { background: "rgba(17, 17, 20, 0.08)", color: COLORS.ink, icon: () => "✕" },
  steps: { background: COLORS.accent, color: "#FFFFFF", icon: (index) => String(index + 1) },
  check: { background: COLORS.accentSoft, color: COLORS.accent, icon: () => "✓" },
};

/** 条目标记的颜色：没写 tone 用变体默认样式；写了 tone 时，编号为实心语义色，叉号与对勾为语义色字 + 浅色圆底。 */
function markerStyle(variant: Variant, toneName: string): { background: string; color: string; icon: (index: number) => string } {
  const base = VARIANT_STYLE[variant];
  if (!toneName) return base;
  const tone = resolveTone(toneName);
  return variant === "steps" ? { ...base, background: toneColor(tone) } : { ...base, background: TONES[tone].tint, color: toneColor(tone) };
}

function revealFrame(index: number, count: number, durationInFrames: number): number {
  // 第一条紧跟卡片入场出现，其余在镜头前 60% 内平均分布
  const window = durationInFrames * 0.6;
  return Math.round(10 + (index * window) / Math.max(count, 1));
}

export const StepFlow: React.FC<{ params: Record<string, unknown>; durationInFrames: number }> = ({ params, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const raw = stringParam(params, "variant", "steps");
  const variant: Variant = raw in VARIANT_STYLE ? (raw as Variant) : "steps";
  const style = markerStyle(variant, stringParam(params, "tone"));
  const items = listParam(params, "items");
  const title = stringParam(params, "title");
  // 条目共用一个字号：按最长一条缩到单行放下，各行视觉一致
  const itemFontSize = fitFontSize(items, 54, STEP_TEXT_WIDTH);
  return (
    <SceneShell backdrop="wallpaper" wallpaper={stringParam(params, "wallpaper", "glacier")}>
      {title ? (
        <div style={{ width: TEXT_COLUMN_WIDTH, textAlign: "center", marginBottom: 48 }}>
          <RevealText text={title} fontSize={fitFontSize([title], 72, TEXT_COLUMN_WIDTH)} weight={700} startFrame={0} stagger={1} />
        </div>
      ) : null}
      <GlassPanel appearFrame={4} style={{ width: PANEL.width, padding: "22px 56px" }}>
        {items.map((item, index) => {
          const appear = progress(frame, revealFrame(index, items.length, durationInFrames), 12);
          return (
            <div
              key={`${index}-${item}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 28,
                padding: "26px 0",
                borderTop: index === 0 ? "none" : `1.5px solid ${COLORS.hairline}`,
                opacity: appear,
                translate: `0px ${(1 - appear) * 22}px`,
                filter: appear < 1 ? `blur(${(1 - appear) * 6}px)` : undefined,
              }}
            >
              <div
                style={{
                  width: 56,
                  height: 56,
                  flexShrink: 0,
                  borderRadius: 28,
                  backgroundColor: style.background,
                  color: style.color,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 32,
                  fontWeight: 800,
                }}
              >
                {style.icon(index)}
              </div>
              <div style={{ fontSize: itemFontSize, fontWeight: 600, lineHeight: 1.3, color: COLORS.ink, ...KEEP_WORDS }}>
                <ToneText text={item} />
              </div>
            </div>
          );
        })}
      </GlassPanel>
      <SourceNote text={stringParam(params, "footnote")} opacity={progress(frame, revealFrame(items.length, items.length, durationInFrames), fps / 2)} glass />
    </SceneShell>
  );
};
