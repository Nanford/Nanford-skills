/**
 * INPUT: lucide-static 0.460.0 的 SVG 源文件（https://unpkg.com/lucide-static@0.460.0/icons/<名称>.svg，2026-10-09 取得）
 * OUTPUT: LUCIDE_ICONS：图标名 → 组成图标的 SVG 元素（标签与属性），24×24 网格、线性描边；ICON_NAMES
 * POS: 文字动效与卡片用的线性图标。只收录用到的图标，不安装整个 npm 包（不新增依赖，也不改 package-lock.json）。
 *      许可：ISC（含 Feather 的 MIT 部分），全文见同目录 LICENSE-lucide.txt，随代码一起保留。
 *      新增图标：从同一版本取 SVG，照抄元素与属性，并在下方 SOURCES 记下 SHA-256；不收品牌或产品标志。
 */

export interface IconElement {
  tag: "path" | "circle" | "rect" | "polyline" | "line";
  attrs: Record<string, string | number>;
}

export const LUCIDE_VERSION = "0.460.0";

// 原始 SVG 文件的 SHA-256，用于核对抄录来源
export const SOURCES: Record<string, string> = {
  bot: "342f3300d42355068660e0b0649288c83ce4e2f284d979c7110dcc2dc1f3fae8",
  "circle-check": "ffd88a7e59f2cc8a0a7a5fee96d16e679d3340aec79131b42a97c4030f08efd3",
  clock: "582c60a98d8e3656ecab7ace7b0b6840ab51b1c371c4861425a9af9299e4ba89",
  "file-text": "089227d1e6ca2358233c09c6f2bb08b135f2ff2f3fc62109d98a3ec9d8c2785d",
};

export const LUCIDE_ICONS: Record<string, IconElement[]> = {
  bot: [
    { tag: "path", attrs: { d: "M12 8V4H8" } },
    { tag: "rect", attrs: { width: 16, height: 12, x: 4, y: 8, rx: 2 } },
    { tag: "path", attrs: { d: "M2 14h2" } },
    { tag: "path", attrs: { d: "M20 14h2" } },
    { tag: "path", attrs: { d: "M15 13v2" } },
    { tag: "path", attrs: { d: "M9 13v2" } },
  ],
  "circle-check": [
    { tag: "circle", attrs: { cx: 12, cy: 12, r: 10 } },
    { tag: "path", attrs: { d: "m9 12 2 2 4-4" } },
  ],
  clock: [
    { tag: "circle", attrs: { cx: 12, cy: 12, r: 10 } },
    { tag: "polyline", attrs: { points: "12 6 12 12 16 14" } },
  ],
  "file-text": [
    { tag: "path", attrs: { d: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" } },
    { tag: "path", attrs: { d: "M14 2v4a2 2 0 0 0 2 2h4" } },
    { tag: "path", attrs: { d: "M10 9H8" } },
    { tag: "path", attrs: { d: "M16 13H8" } },
    { tag: "path", attrs: { d: "M16 17H8" } },
  ],
};

export const ICON_NAMES = Object.keys(LUCIDE_ICONS);
