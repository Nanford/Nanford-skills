/**
 * INPUT: video-timeline 技能产出的 timeline.json 结构（docs/DATA_CONTRACTS.md 第 6 节）
 * OUTPUT: Timeline、VisualClip、CaptionClip、CoverProps 等类型
 * POS: 渲染层与数据合同的接口定义。字段变化时先改合同与 video-timeline，再同步这里。
 */

// 与 scripts/lib.mjs 的 SUPPORTED_SCENES 保持一致；新增场景时两处同步
export type SceneType = "ResultHook" | "StepFlow" | "EvidenceCard" | "BeforeAfter" | "ActionEnd" | "ChapterDivider" | "ScreenFocus" | "ScreenClip" | "Illustration" | "KineticText";

export interface VisualClip {
  id: string;
  shot_id: string;
  scene_type: SceneType;
  params: Record<string, unknown>;
  start_frame: number;
  end_frame: number;
}

export interface CaptionClip {
  id: string;
  text: string;
  start_frame: number;
  end_frame: number;
}

export interface Timeline {
  variant: string | null;
  width: number;
  height: number;
  fps: number;
  duration_frames: number;
  tracks: {
    visual: VisualClip[];
    caption: CaptionClip[];
  };
}

// Remotion 要求合成属性可赋值给 Record<string, unknown>，因此用 type 而不是 interface
export type VideoProps = {
  timeline: Timeline;
  // 平台显式标识：配音由 AI 合成，全片保留角标
  aiLabel: string;
  brand: string;
};

export type CoverProps = {
  kicker: string;
  title: string;
  sub: string;
  brand: string;
  aiLabel: string;
};
