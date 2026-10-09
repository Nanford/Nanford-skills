/**
 * INPUT: 无
 * OUTPUT: SAMPLE_VIDEO_PROPS、SAMPLE_COVER_PROPS：Studio 预览与渲染测试用的示例数据
 * POS: 仅用于预览和测试，内容明确为示例，不能作为正式成片数据。ScreenFocus 需要项目图片，不在示例里，用真实项目的时间轴预览。
 */

import type { CoverProps, VideoProps } from "./types";

export const SAMPLE_VIDEO_PROPS: VideoProps = {
  brand: "Nanford · AI 实战笔记",
  aiLabel: "AI 合成配音",
  timeline: {
    variant: "sample",
    width: 1080,
    height: 1920,
    fps: 30,
    duration_frames: 540,
    tracks: {
      visual: [
        { id: "v1", shot_id: "sample_1", scene_type: "ResultHook", params: { kicker: "示例", title: "示例开头\n一句{痛点}", focus: "痛点" }, start_frame: 0, end_frame: 90 },
        { id: "v2", shot_id: "sample_2", scene_type: "ChapterDivider", params: { lead: "写清楚", words: ["字体", "字号", "颜色", "行距"] }, start_frame: 90, end_frame: 180 },
        { id: "v3", shot_id: "sample_3", scene_type: "StepFlow", params: { variant: "steps", title: "示例{步骤}", items: ["第一步", "第二步", "第三步"] }, start_frame: 180, end_frame: 270 },
        { id: "v4", shot_id: "sample_4", scene_type: "EvidenceCard", params: { kicker: "示例", big: "42", unit: "示例单位", source: "示例数据，不代表真实结果" }, start_frame: 270, end_frame: 360 },
        { id: "v5", shot_id: "sample_5", scene_type: "BeforeAfter", params: { title: "示例对比", columns: [["之前", "示例说明"], ["之后", "示例说明"]], highlight: 1 }, start_frame: 360, end_frame: 450 },
        { id: "v6", shot_id: "sample_6", scene_type: "ActionEnd", params: { title: "示例收尾\n{提问}？", sub: "评论区聊聊" }, start_frame: 450, end_frame: 540 },
      ],
      caption: [
        { id: "c1", text: "这是示例字幕", start_frame: 5, end_frame: 85 },
        { id: "c2", text: "示例数据不能用于正式成片", start_frame: 95, end_frame: 530 },
      ],
    },
  },
};

export const SAMPLE_COVER_PROPS: CoverProps = {
  kicker: "示例",
  title: "示例封面\n标题{两行}",
  sub: "副标题",
  brand: "Nanford · AI 实战笔记",
  aiLabel: "AI 合成配音",
};
