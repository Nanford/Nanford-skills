/**
 * INPUT: theme.ts 颜色与安全区；wallpapers.ts 品牌风景底图清单；remotion 的 Img、staticFile
 * OUTPUT: SceneShell（场景外壳：背景 + 内容层，开头镜头的放大动作只作用于内容层）、EntranceScale（开头放大的上下文）、
 *         Backdrop（浅灰 paper / 深色 night / 风景 wallpaper 三种背景）、Chrome（品牌与 AI 合成标识角标）、Kicker、SourceNote
 * POS: 所有场景共用的画面外框。背景由场景各自决定，镜头之间硬切；标识放在安全区内，不会被平台按钮遮挡。
 */

import React, { createContext, useContext } from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { COLORS, CONTENT_BOTTOM, CONTENT_TOP, FONT_FAMILY, GLASS_BLUR, KEEP_WORDS, SAFE } from "../theme";
import { wallpaperFile } from "../wallpapers";

export type BackdropKind = "paper" | "night" | "wallpaper";

// 开头镜头的「放大落位」动作：由 Video.tsx 提供数值，SceneShell 只缩放内容层，背景始终铺满画面
export const EntranceScale = createContext(1);
// 开头镜头的预滚帧数：场景时钟比全片早开始这么多帧。场景里按「镜头时长比例」安排的动作（如 at: 0.4）
// 要换算成观众可见部分的比例，否则开头镜头的动作会整体提前
export const PrerollFrames = createContext(0);

/** 观众可见部分的比例 → 场景帧号。durationInFrames 为场景时长（开头镜头含预滚）。 */
export function useVisibleFrame(): (fraction: number, durationInFrames: number) => number {
  const preroll = useContext(PrerollFrames);
  return (fraction, durationInFrames) => Math.round(preroll + fraction * (durationInFrames - preroll));
}

export const Backdrop: React.FC<{ kind: BackdropKind; wallpaper?: string }> = ({ kind, wallpaper }) => {
  if (kind === "night") {
    return (
      <AbsoluteFill
        style={{ backgroundColor: COLORS.night, backgroundImage: "radial-gradient(circle at 30% 28%, #1A1B22 0%, transparent 60%)" }}
      />
    );
  }
  if (kind === "wallpaper") {
    return (
      <AbsoluteFill style={{ backgroundColor: COLORS.paper }}>
        {/* 风景底图静止不动：参考片里风景镜头一律不运镜，推近只留给界面截图 */}
        <Img src={staticFile(wallpaperFile(wallpaper))} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        {/* 顶部向浅灰过渡：让顶部的黑色标题在任何照片上都读得清 */}
        <AbsoluteFill style={{ backgroundImage: `linear-gradient(180deg, rgba(243, 243, 243, 0.92) 0%, rgba(243, 243, 243, 0.55) 22%, rgba(243, 243, 243, 0) 42%)` }} />
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.paper, backgroundImage: "radial-gradient(circle at 50% 42%, #FAFAFA 0%, transparent 62%)" }} />
  );
};

/** 场景外壳：背景铺满画面，内容层位于安全区内的内容区，接受开头放大动作。 */
export const SceneShell: React.FC<{
  backdrop: BackdropKind;
  wallpaper?: string;
  children: React.ReactNode;
  justify?: "center" | "flex-start";
  align?: "center" | "stretch";
}> = ({ backdrop, wallpaper, children, justify = "center", align = "center" }) => {
  const scale = useContext(EntranceScale);
  return (
    <AbsoluteFill>
      <Backdrop kind={backdrop} wallpaper={wallpaper} />
      <AbsoluteFill style={{ scale: String(scale) }}>
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: CONTENT_TOP,
            height: CONTENT_BOTTOM - CONTENT_TOP,
            display: "flex",
            flexDirection: "column",
            justifyContent: justify,
            alignItems: align,
            fontFamily: FONT_FAMILY,
            color: backdrop === "night" ? COLORS.nightText : COLORS.ink,
          }}
        >
          {children}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const chromePill: React.CSSProperties = {
  backgroundColor: "rgba(255, 255, 255, 0.62)",
  backdropFilter: `blur(${GLASS_BLUR}px)`,
  border: "1.5px solid rgba(255, 255, 255, 0.85)",
  borderRadius: 999,
  padding: "6px 20px",
  color: COLORS.inkSoft,
};

/**
 * 品牌名与「AI 合成配音」显式标识：毛玻璃小胶囊，浅灰底、深色底、风景底上都能看清。
 * aiLabel 为空字符串时不画标识胶囊：账号持有人选择只靠发布时的平台 AI 声明（决定记在 brief.json 的 aigc）。
 */
export const Chrome: React.FC<{ brand: string; aiLabel: string }> = ({ brand, aiLabel }) => (
  <div
    style={{
      position: "absolute",
      left: SAFE.left,
      right: SAFE.right,
      top: SAFE.top,
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      fontFamily: FONT_FAMILY,
      fontSize: 28,
      fontWeight: 600,
    }}
  >
    {/* 品牌胶囊比标识胶囊醒目（2026-09-30 主理人要求品牌名凸显）：更大、更粗、近黑字，前缀紫点与画面标签同源 */}
    <span
      style={{
        ...chromePill,
        backgroundColor: "rgba(255, 255, 255, 0.86)",
        color: COLORS.ink,
        fontSize: 36,
        fontWeight: 800,
        padding: "8px 26px",
        display: "inline-flex",
        alignItems: "center",
        gap: 12,
      }}
    >
      <span style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: COLORS.accent }} />
      {brand}
    </span>
    {aiLabel ? <span style={{ ...chromePill, fontSize: 26 }}>{aiLabel}</span> : null}
  </div>
);

/** 来源或脚注小字。风景底上用毛玻璃底衬（glass），照片下半部颜色不定，直接放灰字可能看不清。 */
export const SourceNote: React.FC<{ text: string; opacity: number; dark?: boolean; glass?: boolean }> = ({ text, opacity, dark = false, glass = false }) =>
  text ? (
    <div style={{ marginTop: 36, opacity, display: "flex", justifyContent: "center", maxWidth: 828 }}>
      <span
        style={{
          fontSize: 30,
          lineHeight: 1.4,
          textAlign: "center",
          color: dark ? COLORS.nightMuted : COLORS.inkSoft,
          ...(glass ? { ...chromePill, borderRadius: 20, padding: "8px 22px" } : {}),
          ...KEEP_WORDS,
        }}
      >
        {text}
      </span>
    </div>
  ) : null;

/** 小标题胶囊：紫色小圆点 + 深灰文字，放在大字上方。 */
export const Kicker: React.FC<{ text: string; opacity: number }> = ({ text, opacity }) =>
  text ? (
    <div style={{ opacity, marginBottom: 40, display: "flex", justifyContent: "center" }}>
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 14,
          fontSize: 36,
          fontWeight: 600,
          color: COLORS.inkSoft,
          backgroundColor: "#FFFFFF",
          border: `1.5px solid ${COLORS.hairline}`,
          borderRadius: 999,
          padding: "8px 28px",
          boxShadow: "0 8px 24px rgba(34, 24, 84, 0.08)",
        }}
      >
        <span style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: COLORS.accent }} />
        {text}
      </span>
    </div>
  ) : null;
