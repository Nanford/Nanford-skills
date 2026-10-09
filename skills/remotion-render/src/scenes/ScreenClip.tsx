/**
 * INPUT: params.video（render.mjs 暂存后的 public 相对路径）、params.video_size（[宽, 高]）、params.source_in_ms（工作副本内的入点）、
 *        params.playback_rate（render.mjs 按 source_out_ms 与镜头时长算定，或时间轴直接给出）、
 *        可选 title（窗口上方标题，{…} 标紫色）、tag（窗口左下角标签）、wallpaper
 * OUTPUT: 录屏片段场景：风景底上的圆角窗口里播放一段真实录屏（静音），全程约 3% 缓推；倍速大于 1 时标签自动注明「N× 加速」
 * POS: 真实操作过程或成品翻阅的动态证据，与 ScreenFocus（静帧截图）互补。工作副本须已在项目里完成裁切与打码，
 *      本场景只决定取景与播放速度，不改画面内容；加速播放必须向观众说明（AGENTS.md 第 8 节「等待过程已加速」）。
 */

import React, { useContext } from "react";
import { OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { GlassPanel, RevealText, Tag } from "../components/Motion";
import { PrerollFrames, SceneShell } from "../components/Frame";
import { PANEL, SHADOW, TEXT_COLUMN_WIDTH, fitFontSize, progress, stringParam } from "../theme";

const VIEW_WIDTH = PANEL.width - 4;
// 倍速与 1 相差不到 5% 时视为原速，不标注加速（铺满镜头时的微小变速观众察觉不到）
const RATE_LABEL_THRESHOLD = 1.05;

interface ClipRef {
  src: string;
  width: number;
  height: number;
  sourceInMs: number;
  rate: number;
}

/** 读取并校验片段参数；缺 video_size 或 playback_rate 说明没经过 render.mjs 暂存，直接报错。 */
function readClip(params: Record<string, unknown>): ClipRef {
  const size = params.video_size;
  const { video, source_in_ms: sourceInMs, playback_rate: rate } = params;
  if (typeof video !== "string" || !Array.isArray(size) || size.length !== 2 || !size.every((value) => typeof value === "number" && value > 0)) {
    throw new Error("ScreenClip 缺少 video 或 video_size：请通过 render.mjs 渲染，它会暂存录屏片段并读取尺寸");
  }
  if (typeof sourceInMs !== "number" || sourceInMs < 0 || typeof rate !== "number" || rate <= 0) {
    throw new Error("ScreenClip 缺少 source_in_ms 或 playback_rate：请通过 render.mjs 渲染，它会按镜头时长算定倍速");
  }
  return { src: video, width: size[0], height: size[1], sourceInMs, rate };
}

/** 倍速标注：整数倍写整数，否则保留一位小数。 */
export function rateLabel(rate: number): string {
  if (rate < RATE_LABEL_THRESHOLD) return "";
  const rounded = Math.round(rate * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}× 加速`;
}

export const ScreenClip: React.FC<{ params: Record<string, unknown>; durationInFrames: number }> = ({ params, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const preroll = useContext(PrerollFrames);
  const clip = readClip(params);
  const title = stringParam(params, "title");
  const titleLines = title ? title.split("\n") : [];
  const titleSize = fitFontSize(titleLines, 68, TEXT_COLUMN_WIDTH);
  const viewH = Math.round(Math.min(1000 - (title ? 140 : 0), Math.max(420, (clip.height * VIEW_WIDTH) / clip.width)));
  // 缓推与 ScreenFocus 一致：全程约 3%，只让画面不死板，以窗口中心为基准
  const push = 1 + 0.03 * progress(frame, 0, durationInFrames);
  const tag = [stringParam(params, "tag"), rateLabel(clip.rate)].filter(Boolean).join(" · ");
  return (
    <SceneShell backdrop="wallpaper" wallpaper={stringParam(params, "wallpaper", "mistlake")}>
      {titleLines.length ? (
        <div style={{ width: TEXT_COLUMN_WIDTH, textAlign: "center", marginBottom: 44 }}>
          {titleLines.map((line, index) => (
            <div key={`${index}-${line}`}>
              <RevealText text={line} fontSize={titleSize} weight={700} startFrame={2 + index * 5} stagger={1} />
            </div>
          ))}
        </div>
      ) : null}
      <GlassPanel appearFrame={0} strong style={{ width: PANEL.width, padding: 0, borderRadius: 34, boxShadow: SHADOW.float, position: "relative" }}>
        <div style={{ position: "relative", width: VIEW_WIDTH, height: viewH, overflow: "hidden", borderRadius: 32, backgroundColor: "#FFFFFF" }}>
          {/* 开头镜头有预滚：录屏从观众可见的第 0 帧才开始播，预滚期间（全片负帧，不会被渲染）不消耗源区间，
              所以 render.mjs 按可见时长做的越界检查与这里一致 */}
          <Sequence from={preroll} layout="none">
            <OffthreadVideo
              src={staticFile(clip.src)}
              muted
              // trimBefore 以合成帧计：入点毫秒按全片 fps 换算，工作副本为同一 fps 的恒定帧率
              trimBefore={Math.round((clip.sourceInMs * fps) / 1000)}
              playbackRate={clip.rate}
              style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", scale: String(push) }}
            />
          </Sequence>
        </div>
        {tag ? (
          <div style={{ position: "absolute", left: 24, bottom: 22 }}>
            <Tag text={tag} opacity={progress(frame, 10, 10)} />
          </div>
        ) : null}
      </GlassPanel>
    </SceneShell>
  );
};
