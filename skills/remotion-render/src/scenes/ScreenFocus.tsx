/**
 * INPUT: params.image（render.mjs 暂存后的 public 相对路径）、params.image_size（[宽, 高]，由 render.mjs 读取文件头补上）、
 *        可选 title（窗口上方标题，{…} 标紫色）、tag（窗口左下角标签，如「终端实录」）、
 *        focus（[{x, y, w, h}]，图片内归一化坐标，镜头依次推近到这些区域）、
 *        highlights（[{x, y, w, h, shape: "circle" | "underline", at}]，手绘圈注，at 为镜头时长比例）、
 *        quote（窗口下方的原文摘录，\n 分行；截图里的字太小时用排版层放大，必须与截图原文一字不差）、wallpaper
 * OUTPUT: 截图聚焦场景：风景底上的圆角窗口装着真实截图，先看全图，再分段推近到关键区域并圈出；可选原文摘录卡
 * POS: 真实成品与证据画面（录屏截图、文档截图）。截图内容必须是真实素材，推近只改变取景，不改变内容。
 *      参考片中只有界面截图与实拍镜头运镜，所以推近只在截图场景里使用；风景与文字镜头保持静止。
 */

import React from "react";
import { useCurrentFrame } from "remotion";
import { GlassPanel, HandCircle, HandUnderline, RevealText, Tag } from "../components/Motion";
import { SceneShell, useVisibleFrame } from "../components/Frame";
import { ScreenshotView, clampCamera, fitRect, isUnit, mixCamera, pushCamera, readImage, readRects } from "../components/Screenshot";
import { COLORS, PANEL, SHADOW, TEXT_COLUMN_WIDTH, fitFontSize, progress, stringParam } from "../theme";

const VIEW_WIDTH = PANEL.width - 4;
const MOVE_FRAMES = 20;
// 摘录卡文字宽度：卡片 900 宽，左内边距 44、右内边距 90（文字右缘不超过安全区 900px）
const QUOTE_TEXT_WIDTH = PANEL.width - 134;

export const ScreenFocus: React.FC<{ params: Record<string, unknown>; durationInFrames: number }> = ({ params, durationInFrames }) => {
  const frame = useCurrentFrame();
  const visibleFrame = useVisibleFrame();
  const image = readImage(params, "ScreenFocus");
  const title = stringParam(params, "title");
  const titleLines = title ? title.split("\n") : [];
  const titleSize = fitFontSize(titleLines, 68, TEXT_COLUMN_WIDTH);
  const quote = stringParam(params, "quote");
  const quoteLines = quote ? quote.split("\n") : [];
  const quoteSize = fitFontSize(quoteLines, 40, QUOTE_TEXT_WIDTH);
  // 取景框高度随图片比例；标题、摘录各占一部分内容区，保证整体不超出内容区（约 1100px 高）
  const maxViewH = 1000 - (title ? 140 : 0) - (quote ? 60 + quoteLines.length * quoteSize * 1.45 : 0);
  const viewH = Math.round(Math.min(maxViewH, Math.max(420, (image.height * VIEW_WIDTH) / image.width)));
  const overview = clampCamera({ scale: VIEW_WIDTH / image.width, x: 0, y: 0 }, image, VIEW_WIDTH, viewH);
  const focus = readRects(params.focus, "ScreenFocus 的 focus").map((rect) => fitRect(rect, image, VIEW_WIDTH, viewH));
  // 先看全图约 28% 的可见时长，之后在 85% 之前依次推到各个区域（开头镜头扣除预滚）
  const firstMove = Math.max(visibleFrame(0, durationInFrames) + 20, visibleFrame(0.28, durationInFrames));
  const spacing = focus.length ? (visibleFrame(0.85, durationInFrames) - firstMove) / focus.length : 0;
  let camera = overview;
  focus.forEach((target, index) => {
    camera = mixCamera(camera, target, progress(frame, firstMove + index * spacing, MOVE_FRAMES));
  });
  // 全程约 3% 的缓推，数值很小，只让画面不死板
  camera = pushCamera(camera, 1 + 0.03 * progress(frame, 0, durationInFrames), image, VIEW_WIDTH, viewH);
  const lastMoveEnd = focus.length ? firstMove + (focus.length - 1) * spacing + MOVE_FRAMES : visibleFrame(0.3, durationInFrames);
  const highlights = readRects(params.highlights, "ScreenFocus 的 highlights");
  const tag = stringParam(params, "tag");
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
        <ScreenshotView image={image} camera={camera} width={VIEW_WIDTH} height={viewH}>
          {highlights.map((mark, index) => {
            // 圈注画在取景框坐标里，随镜头移动但线宽不随放大变粗
            const x = camera.x + mark.x * image.width * camera.scale;
            const y = camera.y + mark.y * image.height * camera.scale;
            const w = mark.w * image.width * camera.scale;
            const h = mark.h * image.height * camera.scale;
            const drawFrame = isUnit(mark.at) ? visibleFrame(mark.at, durationInFrames) : lastMoveEnd + index * 8;
            return mark.shape === "underline" ? (
              <div key={index} style={{ position: "absolute", left: x, top: y + h }}>
                <HandUnderline width={w} drawFrame={drawFrame} />
              </div>
            ) : (
              <HandCircle key={index} x={x} y={y} width={w} height={h} drawFrame={drawFrame} />
            );
          })}
        </ScreenshotView>
        {tag ? (
          <div style={{ position: "absolute", left: 24, bottom: 22 }}>
            <Tag text={tag} opacity={progress(frame, 10, 10)} />
          </div>
        ) : null}
      </GlassPanel>
      {quoteLines.length ? (
        // 原文摘录：与第一处圈注同时出现，截图证明真实，摘录保证手机上读得清
        <GlassPanel appearFrame={Math.max(14, lastMoveEnd - 6)} strong style={{ width: PANEL.width, marginTop: 28, padding: "22px 90px 24px 44px", boxSizing: "border-box" }}>
          <div style={{ fontSize: 26, fontWeight: 600, color: COLORS.accent, letterSpacing: 2, marginBottom: 8 }}>原文</div>
          {quoteLines.map((line, index) => (
            <div key={`${index}-${line}`} style={{ fontSize: quoteSize, fontWeight: 600, lineHeight: 1.45, color: COLORS.ink, whiteSpace: "nowrap" }}>
              {line}
            </div>
          ))}
        </GlassPanel>
      ) : null}
    </SceneShell>
  );
};
