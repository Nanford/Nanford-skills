/**
 * INPUT: VideoProps（timeline.json 内容、AI 标识文字、账号名）；scenes/ 下各场景组件
 * OUTPUT: VideoFromTimeline 组件：按 timeline.tracks.visual 逐镜头排布场景（开头镜头预滚、第 0 帧即完整），叠加字幕与角标；calculateVideoMetadata
 * POS: 渲染主合成。只读取时间轴里已算好的帧边界，不自行计算时长，保证与配音、字幕同源。
 *      背景由各场景自己决定（浅灰 / 深色 / 风景），镜头之间硬切；柔和感由镜头内的入场动画承担（docs/STYLE.md）。
 */

import React from "react";
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame, type CalculateMetadataFunction } from "remotion";
import "./fonts";
import { Chrome, EntranceScale, PrerollFrames } from "./components/Frame";
import { Captions } from "./components/Captions";
import { ActionEnd } from "./scenes/ActionEnd";
import { BeforeAfter } from "./scenes/BeforeAfter";
import { ChapterDivider } from "./scenes/ChapterDivider";
import { EvidenceCard } from "./scenes/EvidenceCard";
import { Illustration } from "./scenes/Illustration";
import { KineticText } from "./scenes/KineticText";
import { ResultHook } from "./scenes/ResultHook";
import { ScreenClip } from "./scenes/ScreenClip";
import { ScreenFocus } from "./scenes/ScreenFocus";
import { StepFlow } from "./scenes/StepFlow";
import { EASE_OUT } from "./theme";
import type { VideoProps, VisualClip } from "./types";

// 开头镜头预滚：场景内部时钟提前 36 帧（各场景入场动画都在 36 帧内完成），第 0 帧即显示完整开头，
// 而不是从空白淡入——第 0 帧是平台默认首帧，也是观众决定是否划走的第一眼
const HOOK_PREROLL_FRAMES = 36;
// 预滚后画面是静止的，用 10 帧由 0.95 放大到 1 给开头一个动作；从小到大而不是从大到小，内容始终不越出安全区
const HOOK_PUNCH_FRAMES = 10;

const Scene: React.FC<{ clip: VisualClip; brand: string; durationInFrames: number }> = ({ clip, brand, durationInFrames }) => {
  switch (clip.scene_type) {
    case "ResultHook":
      return <ResultHook params={clip.params} />;
    case "StepFlow":
      return <StepFlow params={clip.params} durationInFrames={durationInFrames} />;
    case "EvidenceCard":
      return <EvidenceCard params={clip.params} />;
    case "BeforeAfter":
      return <BeforeAfter params={clip.params} durationInFrames={durationInFrames} />;
    case "ActionEnd":
      return <ActionEnd params={clip.params} brand={brand} />;
    case "ChapterDivider":
      return <ChapterDivider params={clip.params} durationInFrames={durationInFrames} />;
    case "ScreenFocus":
      return <ScreenFocus params={clip.params} durationInFrames={durationInFrames} />;
    case "Illustration":
      return <Illustration params={clip.params} />;
    case "ScreenClip":
      return <ScreenClip params={clip.params} durationInFrames={durationInFrames} />;
    case "KineticText":
      return <KineticText params={clip.params} durationInFrames={durationInFrames} />;
    default:
      // 未知场景直接报错，不渲染空白画面冒充成片
      throw new Error(`未支持的场景类型：${String((clip as VisualClip).scene_type)}（镜头 ${clip.shot_id}）`);
  }
};

const HookEntrance: React.FC<{ clip: VisualClip; brand: string }> = ({ clip, brand }) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, HOOK_PUNCH_FRAMES], [0.95, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT });
  const durationInFrames = clip.end_frame - clip.start_frame + HOOK_PREROLL_FRAMES;
  return (
    // 放大只作用于场景内容层（SceneShell 读取），背景始终铺满画面，不会在四周露出空白
    <EntranceScale.Provider value={scale}>
      {/* 场景按「可见时长比例」安排的动作要扣掉预滚，见 Frame.tsx 的 useVisibleFrame */}
      <PrerollFrames.Provider value={HOOK_PREROLL_FRAMES}>
        {/* 负的 from：子序列比父序列早开始，场景在全片第 0 帧时已处于第 36 帧 */}
        <Sequence from={-HOOK_PREROLL_FRAMES} durationInFrames={durationInFrames} name={`${clip.shot_id}-preroll`}>
          <Scene clip={clip} brand={brand} durationInFrames={durationInFrames} />
        </Sequence>
      </PrerollFrames.Provider>
    </EntranceScale.Provider>
  );
};

export const VideoFromTimeline: React.FC<VideoProps> = ({ timeline, aiLabel, brand }) => (
  <AbsoluteFill>
    {timeline.tracks.visual.map((clip) => (
      <Sequence key={clip.id} from={clip.start_frame} durationInFrames={clip.end_frame - clip.start_frame} name={clip.shot_id}>
        {clip.start_frame === 0 ? (
          <HookEntrance clip={clip} brand={brand} />
        ) : (
          <Scene clip={clip} brand={brand} durationInFrames={clip.end_frame - clip.start_frame} />
        )}
      </Sequence>
    ))}
    <Chrome brand={brand} aiLabel={aiLabel} />
    <Captions captions={timeline.tracks.caption} />
  </AbsoluteFill>
);

export const calculateVideoMetadata: CalculateMetadataFunction<VideoProps> = ({ props }) => ({
  durationInFrames: props.timeline.duration_frames,
  fps: props.timeline.fps,
  width: props.timeline.width,
  height: props.timeline.height,
});
