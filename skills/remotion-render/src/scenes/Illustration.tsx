/**
 * INPUT: 项目插图 image / image_size（render.mjs 暂存），可选 title（最多两行）。
 * OUTPUT: 完整适配插图、可编辑标题与常驻「画面示意」说明。
 * POS: 生成或绘制的补充画面；与 ScreenFocus 的真实证据用途分开。
 */

import React from "react";
import { Img, staticFile } from "remotion";
import { SceneShell } from "../components/Frame";
import { RevealText, Tag } from "../components/Motion";
import { readImage } from "../components/Screenshot";
import { TEXT_COLUMN_WIDTH, fitFontSize, stringParam } from "../theme";

export const Illustration: React.FC<{ params: Record<string, unknown> }> = ({ params }) => {
  const image = readImage(params, "Illustration");
  const title = stringParam(params, "title");
  const lines = title ? title.split("\n") : [];
  if (lines.length > 2) throw new Error("Illustration 的 title 最多两行");
  const titleSize = fitFontSize(lines, 68, TEXT_COLUMN_WIDTH);
  // 横图按自身比例收紧容器，让说明紧邻图片；竖图限制高度以避让字幕。
  const imageHeight = Math.min(760, Math.round(TEXT_COLUMN_WIDTH * image.height / image.width));
  return (
    <SceneShell backdrop="paper">
      {lines.length ? (
        <div style={{ width: TEXT_COLUMN_WIDTH, textAlign: "center", marginBottom: 28 }}>
          {lines.map((line, index) => (
            <div key={index} style={{ lineHeight: 1.25 }}>
              <RevealText text={line} fontSize={titleSize} weight={700} startFrame={2 + index * 5} stagger={1} />
            </div>
          ))}
        </div>
      ) : null}
      {/* contain 保留主体边缘和 PNG 透明度；背景与插图静止，沿用系列运动规则。 */}
      <Img src={staticFile(image.src)} style={{ width: TEXT_COLUMN_WIDTH, height: imageHeight, objectFit: "contain" }} />
      {/* 从镜头第一帧可见，避免把生成的场景误读为真实案例。 */}
      <div style={{ marginTop: 24 }}><Tag text="画面示意" opacity={1} /></div>
    </SceneShell>
  );
};
