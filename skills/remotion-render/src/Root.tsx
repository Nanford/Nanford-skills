/**
 * INPUT: Video.tsx、Cover.tsx、sample.ts
 * OUTPUT: RemotionRoot：注册 Video（时长由 timeline 决定）与 Cover（竖版封面静帧）两个合成
 * POS: Remotion 入口的合成清单。正式渲染时由 scripts/render.mjs 传入真实 timeline，示例数据只用于 Studio 预览。
 */

import React from "react";
import { Composition, Still } from "remotion";
import { CoverStill } from "./Cover";
import { SAMPLE_COVER_PROPS, SAMPLE_VIDEO_PROPS } from "./sample";
import { VideoFromTimeline, calculateVideoMetadata } from "./Video";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Video"
      component={VideoFromTimeline}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={SAMPLE_VIDEO_PROPS.timeline.duration_frames}
      defaultProps={SAMPLE_VIDEO_PROPS}
      calculateMetadata={calculateVideoMetadata}
    />
    <Still id="Cover" component={CoverStill} width={1080} height={1920} defaultProps={SAMPLE_COVER_PROPS} />
  </>
);
