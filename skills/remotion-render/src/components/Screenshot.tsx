/**
 * INPUT: 场景参数里经 render.mjs 暂存的图片（image 为 public 相对路径，image_size 为 [宽, 高]）；remotion 的 Img、staticFile
 * OUTPUT: readImage（读取并校验图片参数）、readRects（读取 0～1 归一化区域）、fitRect / clampCamera / mixCamera（取景计算）、
 *         ScreenshotView（在固定取景框里按镜头参数显示截图）
 * POS: 真实截图的取景工具，ScreenFocus 与 BeforeAfter 的截图对比共用。取景只改变看哪里、看多大，不改变截图内容。
 */

import React from "react";
import { Img, staticFile } from "remotion";

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Camera {
  scale: number;
  x: number;
  y: number;
}

export interface ImageRef {
  src: string;
  width: number;
  height: number;
}

// 推近幅度上限：截图多为 1080 宽，放大超过约 2.2 倍会明显发糊
export const MAX_ZOOM = 2.2;

export function isUnit(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

/** 读取 image 与 image_size；缺尺寸说明没有经过 render.mjs 暂存，直接报错。 */
export function readImage(params: Record<string, unknown>, where: string): ImageRef {
  const size = params.image_size;
  if (typeof params.image !== "string" || !Array.isArray(size) || size.length !== 2 || !size.every((value) => typeof value === "number" && value > 0)) {
    throw new Error(`${where} 缺少 image 或 image_size：请通过 render.mjs 渲染，它会暂存图片并读取尺寸`);
  }
  return { src: params.image, width: size[0], height: size[1] };
}

export function readRects(value: unknown, where: string): Array<Rect & Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.map((item, index) => {
    const rect = item as Record<string, unknown>;
    if (![rect.x, rect.y, rect.w, rect.h].every(isUnit)) {
      throw new Error(`${where}[${index}] 坐标必须是 0～1 之间的数（图片宽高的比例）`);
    }
    return rect as Rect & Record<string, unknown>;
  });
}

/** 保证图片铺满取景框、不露出空白；图片比取景框小的方向居中。 */
export function clampCamera(camera: Camera, image: ImageRef, viewW: number, viewH: number): Camera {
  const clampAxis = (offset: number, content: number, view: number) => (content <= view ? (view - content) / 2 : Math.min(0, Math.max(view - content, offset)));
  return { scale: camera.scale, x: clampAxis(camera.x, image.width * camera.scale, viewW), y: clampAxis(camera.y, image.height * camera.scale, viewH) };
}

/**
 * 让区域尽量填满取景框。contain：区域完整可见（留 10% 边距，用于推近看细节）；cover：区域铺满取景框（用于固定取景的对比窗）。
 * 放大倍数不低于「宽度铺满」，不高于其 MAX_ZOOM 倍。
 */
export function fitRect(rect: Rect, image: ImageRef, viewW: number, viewH: number, mode: "contain" | "cover" = "contain"): Camera {
  const fitWidth = viewW / image.width;
  const byW = viewW / (rect.w * image.width);
  const byH = viewH / (rect.h * image.height);
  const wanted = mode === "contain" ? Math.min(byW, byH) * 0.9 : Math.max(byW, byH);
  const scale = Math.min(Math.max(wanted, fitWidth), fitWidth * MAX_ZOOM);
  return clampCamera({ scale, x: viewW / 2 - (rect.x + rect.w / 2) * image.width * scale, y: viewH / 2 - (rect.y + rect.h / 2) * image.height * scale }, image, viewW, viewH);
}

export const mixCamera = (a: Camera, b: Camera, t: number): Camera => ({ scale: a.scale + (b.scale - a.scale) * t, x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });

/** 以取景框中心为基准再放大 factor 倍（缓推用），并重新限制在图片范围内。 */
export function pushCamera(camera: Camera, factor: number, image: ImageRef, viewW: number, viewH: number): Camera {
  return clampCamera(
    { scale: camera.scale * factor, x: viewW / 2 - (viewW / 2 - camera.x) * factor, y: viewH / 2 - (viewH / 2 - camera.y) * factor },
    image,
    viewW,
    viewH,
  );
}

export const ScreenshotView: React.FC<{ image: ImageRef; camera: Camera; width: number; height: number; children?: React.ReactNode; style?: React.CSSProperties }> = ({
  image,
  camera,
  width,
  height,
  children,
  style,
}) => (
  <div style={{ position: "relative", width, height, overflow: "hidden", borderRadius: 32, backgroundColor: "#FFFFFF", ...style }}>
    <Img
      src={staticFile(image.src)}
      style={{ position: "absolute", left: 0, top: 0, width: image.width, height: image.height, maxWidth: "none", transformOrigin: "0 0", translate: `${camera.x}px ${camera.y}px`, scale: String(camera.scale) }}
    />
    {children}
  </div>
);
