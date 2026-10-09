/**
 * INPUT: 文字对比：params.columns（[[名称, 说明, 可选语义色], ...]，说明里可用 {…} 强调）、params.highlight（高亮行序号）、可选 params.title（{…} 标紫色）、params.source；
 *        截图对比：params.images（两项 {image, image_size, tag, focus?}，由 render.mjs 暂存）、params.beats（[{index, at}] 依次点亮，at 为可见时长比例）
 *        或 params.highlight（只点亮第几张，默认 1）、可选 title、wallpaper
 * OUTPUT: 对比场景。文字对比：白色卡片依次浮现，最后高亮目标行（紫色描边、名称变紫），其余变暗；
 *         截图对比：风景底上两扇窗口上下排列，同时可见，按口播依次点亮（紫色外描边），未点亮的变暗，最后点亮的一扇缓推
 * POS: 表达「A 和 B 的区别」。竖屏下用上下排列代替左右分栏；截图对比用于开头「同样用 AI，两种结果」，第 0 帧两张真实成稿都在画面里。
 */

import React from "react";
import { useCurrentFrame } from "remotion";
import { GlassPanel, RevealText, Tag, ToneText } from "../components/Motion";
import { SceneShell, SourceNote, useVisibleFrame } from "../components/Frame";
import { type ImageRef, ScreenshotView, clampCamera, fitRect, isUnit, pushCamera, readImage, readRects } from "../components/Screenshot";
import { COLORS, KEEP_WORDS, PANEL, SHADOW, TEXT_COLUMN_WIDTH, fitFontSize, progress, resolveTone, stringParam, toneColor, type Tone } from "../theme";

const VIEW_WIDTH = PANEL.width - 4;

interface CompareItem {
  image: ImageRef;
  tag: string;
  focus: { x: number; y: number; w: number; h: number } | null;
}

function readCompare(params: Record<string, unknown>): CompareItem[] | null {
  if (!Array.isArray(params.images)) return null;
  return params.images.map((raw, index) => {
    const item = raw as Record<string, unknown>;
    const [focus] = readRects(item.focus ? [item.focus] : [], `BeforeAfter 的 images[${index}].focus`);
    return { image: readImage(item, `BeforeAfter 的 images[${index}]`), tag: typeof item.tag === "string" ? item.tag : "", focus: focus ?? null };
  });
}

interface Beat {
  index: number;
  at: number;
}

/**
 * 点亮顺序：beats 为 [{index, at}]，at 是观众可见时长的比例，对齐口播里「上面……」「下面……」的时间。
 * 没有 beats 时只在 40% 处点亮 highlight（默认第 2 张）。
 */
function readBeats(params: Record<string, unknown>): Beat[] {
  if (Array.isArray(params.beats)) {
    return params.beats
      .map((raw) => raw as Record<string, unknown>)
      .filter((beat): beat is { index: number; at: number } => typeof beat.index === "number" && isUnit(beat.at))
      .sort((a, b) => a.at - b.at);
  }
  return [{ index: typeof params.highlight === "number" ? params.highlight : 1, at: 0.4 }];
}

const CompareShots: React.FC<{ items: CompareItem[]; params: Record<string, unknown>; durationInFrames: number }> = ({ items, params, durationInFrames }) => {
  const frame = useCurrentFrame();
  const visibleFrame = useVisibleFrame();
  const title = stringParam(params, "title");
  // 两扇窗口同时可见；有标题时每扇 440 高，无标题 500 高，合计不超出内容区
  const viewH = title ? 440 : 500;
  const beats = readBeats(params).map((beat) => ({ index: beat.index, frame: visibleFrame(beat.at, durationInFrames) }));
  // 每扇窗口的点亮程度：轮到它时 10 帧亮起，下一拍轮到别的窗口时 10 帧熄灭
  const lit = items.map((_, index) =>
    beats.reduce((value, beat) => (beat.index === index ? Math.max(value, progress(frame, beat.frame, 10)) : value * (1 - progress(frame, beat.frame, 10))), 0),
  );
  const anyLit = beats.length ? progress(frame, beats[0]!.frame, 10) : 0;
  const lastTarget = beats.length ? beats[beats.length - 1]!.index : -1;
  return (
    <SceneShell backdrop="wallpaper" wallpaper={stringParam(params, "wallpaper", "mistlake")}>
      {title ? (
        <div style={{ width: TEXT_COLUMN_WIDTH, textAlign: "center", marginBottom: 36 }}>
          <RevealText text={title} fontSize={fitFontSize([title], 68, TEXT_COLUMN_WIDTH)} weight={700} startFrame={2} stagger={1} />
        </div>
      ) : null}
      {items.map((item, index) => {
        const glow = lit[index] ?? 0;
        // 点亮后未被点亮的窗口变暗、降饱和，引导视线；第一拍之前两扇都保持原样
        const dim = anyLit * (1 - glow) * 0.45;
        const base = item.focus ? fitRect(item.focus, item.image, VIEW_WIDTH, viewH, "cover") : clampCamera({ scale: VIEW_WIDTH / item.image.width, x: 0, y: 0 }, item.image, VIEW_WIDTH, viewH);
        // 最后被点亮的窗口（结论方）继续约 4% 缓推，另一扇保持不动
        const lastBeat = beats[beats.length - 1];
        const camera = index === lastTarget && lastBeat ? pushCamera(base, 1 + 0.04 * progress(frame, lastBeat.frame, Math.max(1, durationInFrames - lastBeat.frame)), item.image, VIEW_WIDTH, viewH) : base;
        return (
          <GlassPanel
            key={`${index}-${item.image.src}`}
            appearFrame={index * 6}
            strong
            style={{
              width: PANEL.width,
              padding: 0,
              borderRadius: 34,
              // 紫色描边用外侧环形阴影：画在窗口外，不会被截图内容盖住
              boxShadow: `0 0 0 ${(glow * 6).toFixed(2)}px ${COLORS.accent}, ${SHADOW.float}`,
              position: "relative",
              marginBottom: index === 0 ? 34 : 0,
            }}
          >
            <div style={{ opacity: 1 - dim, filter: dim > 0 ? `saturate(${1 - dim})` : undefined }}>
              <ScreenshotView image={item.image} camera={camera} width={VIEW_WIDTH} height={viewH} />
            </div>
            {item.tag ? (
              <div style={{ position: "absolute", left: 24, bottom: 20 }}>
                <Tag text={item.tag} opacity={progress(frame, 8 + index * 6, 10)} />
              </div>
            ) : null}
          </GlassPanel>
        );
      })}
    </SceneShell>
  );
};

/** 对比行：[名称, 说明, 可选语义色]，例如 ["之前", "熬一个通宵", "痛点"]、["之后", "半天出初稿", "解法"]。 */
function readColumns(params: Record<string, unknown>): Array<[string, string, Tone | null]> {
  const raw = params.columns;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .filter((row): row is unknown[] => Array.isArray(row) && row.length >= 2)
    .map((row) => [String(row[0]), String(row[1]), typeof row[2] === "string" ? resolveTone(row[2]) : null]);
}

export const BeforeAfter: React.FC<{ params: Record<string, unknown>; durationInFrames: number }> = ({ params, durationInFrames }) => {
  const compare = readCompare(params);
  return compare ? <CompareShots items={compare} params={params} durationInFrames={durationInFrames} /> : <TextRows params={params} durationInFrames={durationInFrames} />;
};

const TextRows: React.FC<{ params: Record<string, unknown>; durationInFrames: number }> = ({ params, durationInFrames }) => {
  const frame = useCurrentFrame();
  const rows = readColumns(params);
  const title = stringParam(params, "title", "区别在这里");
  const highlight = typeof params.highlight === "number" ? params.highlight : rows.length - 1;
  // 各行在镜头前 45% 依次出现，随后高亮目标行
  const step = Math.max(Math.round((durationInFrames * 0.45) / Math.max(rows.length, 1)), 8);
  const focus = progress(frame, step * rows.length + 6, 12);
  return (
    <SceneShell backdrop="paper">
      <div style={{ width: TEXT_COLUMN_WIDTH, textAlign: "center", marginBottom: 48 }}>
        <RevealText text={title} fontSize={fitFontSize([title], 72, TEXT_COLUMN_WIDTH)} weight={700} startFrame={0} stagger={1} />
      </div>
      {rows.map(([label, description, tone], index) => {
        const appear = progress(frame, 6 + index * step, 12);
        const isTarget = index === highlight;
        // 写了语义色的行，名称始终用该色；没写的沿用原规则：只有被点亮的目标行名称变品牌紫
        const lit = isTarget && focus > 0;
        const labelColor = tone ? toneColor(tone) : lit ? COLORS.accent : COLORS.ink;
        const dim = isTarget ? 1 : 1 - focus * 0.5;
        return (
          <div
            key={`${index}-${label}`}
            style={{
              width: PANEL.width,
              boxSizing: "border-box",
              display: "flex",
              alignItems: "center",
              gap: 34,
              marginBottom: 26,
              // 右内边距 90：框可以伸到 990，文字右缘仍在安全区 900 以内
              padding: "30px 90px 30px 44px",
              borderRadius: 30,
              backgroundColor: "#FFFFFF",
              border: `3px solid ${lit ? toneColor(tone ?? "brand") : "transparent"}`,
              boxShadow: SHADOW.card,
              opacity: appear * dim,
              translate: `0px ${(1 - appear) * 28}px`,
              filter: appear < 1 ? `blur(${(1 - appear) * 6}px)` : undefined,
              scale: isTarget ? String(1 + focus * 0.03) : "1",
            }}
          >
            <div style={{ width: 170, flexShrink: 0, fontSize: 54, fontWeight: 800, color: labelColor }}>{label}</div>
            <div style={{ fontSize: 46, fontWeight: 500, color: COLORS.ink, lineHeight: 1.35, ...KEEP_WORDS }}>
              <ToneText text={description} />
            </div>
          </div>
        );
      })}
      <SourceNote text={stringParam(params, "source")} opacity={focus} />
    </SceneShell>
  );
};
