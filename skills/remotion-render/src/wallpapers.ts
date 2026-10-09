/**
 * INPUT: public/wallpapers/ 下的 1080×1920 底图（来源、授权、分组与校验值见 public/wallpapers/manifest.json）
 * OUTPUT: WALLPAPER_IDS、DEFAULT_WALLPAPER、wallpaperFile()
 * POS: 底图的唯一清单。场景参数里的 wallpaper 只能取这里列出的 id，未知 id 直接报错，不静默换图。
 *      按题材分组与轮换分配在 scripts/lib.mjs 的 assignBackdrops（读 manifest.json 的 group），这里只管 id 到文件。
 *      加图或换图时与 manifest.json 同步，tests/lib.test.mjs 会核对两处 id 一致。
 */

export const WALLPAPER_IDS = [
  // nature：2026-09-29 首批风景图
  "glacier",
  "meltwater",
  "alpenglow",
  "pinkbeach",
  "pinkclouds",
  "mistlake",
  // office：办公桌面与文件（2026-10-07 新增，下同）
  "deskwhite",
  "coffeenote",
  "studiowhite",
  "scissorsnote",
  // blueprint：建筑图纸与工程线稿
  "blueprints",
  "draftpencil",
  "sectionblue",
  "linesblue",
  // tech：明亮的机房、实验室与浅色线条（深色图压黑字看不清，不入库）
  "labwhite",
  "wavewhite",
  "serveraisle",
  // city：上海天际线与楼群
  "lujiazui",
  "shanghaiclouds",
  "bunddusk",
  "shanghaiaerial",
] as const;
export type WallpaperId = (typeof WALLPAPER_IDS)[number];

export const DEFAULT_WALLPAPER: WallpaperId = "glacier";

export function wallpaperFile(id: string | undefined): string {
  const chosen = id ?? DEFAULT_WALLPAPER;
  if (!(WALLPAPER_IDS as readonly string[]).includes(chosen)) {
    throw new Error(`未知的底图 ${chosen}；可选：${WALLPAPER_IDS.join("、")}`);
  }
  return `wallpapers/${chosen}.jpg`;
}
