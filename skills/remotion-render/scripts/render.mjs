/**
 * INPUT: @remotion/bundler、@remotion/renderer；lib.mjs 的纯逻辑；timeline.json（video-timeline 技能产物）；封面参数 JSON
 * OUTPUT: 子命令
 *   check  --timeline <json>                                              只做结构检查，不渲染
 *   video  --timeline <json> --out <mp4> [--scale 0.5] [--frames 0-89]   渲染无声画面（H.264, yuv420p, 30fps 恒定帧率）
 *   video 与 stills 可加 --backdrop-theme office,blueprint：临时指定底图题材组，不传时读项目 brief.json 的 visual.backdrop_theme
 *   stills --timeline <json> --out-dir <dir> [--scale 0.5]                首末帧、每个镜头中段、最宽字幕中段各截一帧，供审片
 *   cover  --props <json> --out <png>                                     渲染竖版封面
 *   verify --timeline <json> --record <输出>.render.json                   重截记录中的抽样帧，逐字节比对，验证可复现
 *   code-hash                                                              打印当前渲染代码校验值，供上层判断能否复用已有画面
 *   actions --timeline <json> --out <json>                                 导出全片动作标记 actions.json（文字动效每拍的落地、出现、划掉等帧），供 av-export 排音效轨；
 *                                                                          需要直接导入 src/kinetic.ts：Node 23.6+ 直接运行，Node 22.6～23.5 加 --experimental-strip-types
 *   video 与 cover 在输出旁写 <输出>.render.json：输入校验值、用到的项目图片校验值、渲染代码校验值、渲染参数、工具版本、输出校验值；
 *   整片正式渲染另记抽样帧的无损 PNG 校验值（sample_stills），供 verify 使用
 * POS: 渲染技能的命令入口。只产出画面文件；配音混音与封装由 av-export 技能完成，所以视频渲染为静音。
 *      时间轴引用的项目图片（ScreenFocus 的 params.image、BeforeAfter 的 params.images[].image，相对项目根目录）与录屏片段（ScreenClip 的 params.video）
 *      在打包前暂存进临时 public 目录，原 timeline.json 不改动。
 */

import { createHash } from "node:crypto";
import { copyFile, link, mkdir, mkdtemp, readdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { bundle } from "@remotion/bundler";
import { getVideoMetadata, renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import { aiLabelFor, assignBackdrops, clipPlayback, collectActions, DEFAULT_AI_LABEL, imageParams, imageSize, localIsoTimestamp, parseBackdropTheme, parseFrameRange, reviewFrames, sampleFrames, validateTimeline, videoParams, wallpaperGroups } from "./lib.mjs";

const SKILL_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_BRAND = "Nanford · AI 实战笔记";
// 正式成片的编码参数；预览用 --scale 缩小分辨率，其余参数不变。
// colorSpace 必须显式设为 bt709：Remotion 4 默认 "default" 会把 JPEG 帧的全范围（yuvj420p、BT.601 矩阵）直接编码进 H.264，
// 按 TV 范围解码的播放器会出现发灰或暗部压黑；bt709 会转换为有限范围 yuv420p 并写入 BT.709 色彩标记
const VIDEO_SETTINGS = { codec: "h264", pixelFormat: "yuv420p", colorSpace: "bt709", crf: 18, x264Preset: "medium", imageFormat: "jpeg", jpegQuality: 95, muted: true };

const sha256 = (buffer) => createHash("sha256").update(buffer).digest("hex");

async function readJsonWithHash(path) {
  let raw;
  try {
    raw = await readFile(path);
  } catch (error) {
    throw new Error(`无法读取 ${path}：${error.message}`);
  }
  try {
    return { data: JSON.parse(raw.toString("utf8")), sha256: sha256(raw) };
  } catch (error) {
    throw new Error(`${path} 不是有效 JSON：${error.message}`);
  }
}

async function loadTimeline(path) {
  const { data, sha256: timelineSha } = await readJsonWithHash(path);
  const errors = validateTimeline(data);
  if (errors.length) {
    throw new Error(`timeline 检查未通过（${errors.length} 项）：\n  - ${errors.join("\n  - ")}`);
  }
  return { timeline: data, timelineSha };
}

async function makeBundle(publicDir = join(SKILL_ROOT, "public")) {
  // publicDir 默认只含字体与风景底图；带项目图片时传入 withStagedBundle 生成的暂存目录
  return bundle({ entryPoint: join(SKILL_ROOT, "src", "index.ts"), publicDir });
}

async function findProjectRoot(startDir) {
  for (let dir = startDir; ; dir = dirname(dir)) {
    try {
      await stat(join(dir, "project.json"));
      return dir;
    } catch {
      if (dirname(dir) === dir) return null;
    }
  }
}

/** 角标文字：--ai-label 优先，否则读时间轴所属项目的 brief.json（找不到项目或 brief 时用默认角标）。 */
async function resolveAiLabel(values) {
  if (typeof values["ai-label"] === "string") return values["ai-label"];
  const root = await findProjectRoot(dirname(resolve(values.timeline)));
  if (!root) return aiLabelFor(undefined, null);
  try {
    return aiLabelFor(undefined, JSON.parse(await readFile(join(root, "brief.json"), "utf8")));
  } catch {
    return aiLabelFor(undefined, null);
  }
}

/** 底图题材：--backdrop-theme 优先（逗号分隔），否则读时间轴所属项目 brief.json 的 visual.backdrop_theme；都没有返回 []。 */
async function resolveBackdropTheme(values) {
  if (typeof values["backdrop-theme"] === "string") return parseBackdropTheme(values["backdrop-theme"]);
  const root = await findProjectRoot(dirname(resolve(values.timeline)));
  if (!root) return [];
  try {
    return parseBackdropTheme(JSON.parse(await readFile(join(root, "brief.json"), "utf8"))?.visual?.backdrop_theme);
  } catch {
    return [];
  }
}

/** 按题材给没写 wallpaper 的底图镜头分配底图（组与图的清单在 public/wallpapers/manifest.json）；返回时间轴副本与分配结果。 */
async function applyBackdrops(timeline, theme) {
  const manifest = JSON.parse(await readFile(join(SKILL_ROOT, "public", "wallpapers", "manifest.json"), "utf8"));
  const result = assignBackdrops(timeline, theme, wallpaperGroups(manifest));
  if (!theme.length) console.log("提示：未设 brief.visual.backdrop_theme，底图镜头沿用各场景默认风景图（见 docs/DESIGN.md 第 3 节）");
  else console.log(`底图题材 ${theme.join("、")}：${result.assignments.map((item) => `${item.shot_id}=${item.wallpaper}`).join("，") || "没有需要分配的镜头"}`);
  return { ...result, theme };
}

/** 把技能自带的 public 资源（字体、风景底图）放进暂存目录：同盘硬链接，不能链接时复制。 */
async function linkSkillPublic(target) {
  const source = join(SKILL_ROOT, "public");
  for (const file of await listFiles(source)) {
    const destination = join(target, relative(source, file));
    await mkdir(dirname(destination), { recursive: true });
    await link(file, destination).catch(() => copyFile(file, destination));
  }
}

/**
 * 暂存时间轴引用的项目图片：按内容校验值命名为 project-assets/<sha256>.<png|jpg>，并在时间轴副本里改写为该路径、补上 image_size。
 * 同一张图无论原文件名如何都得到同一路径，渲染结果只取决于图片内容。Remotion 在 Windows 上打包时会复制整个 public 目录，
 * 所以打包完成后即可删除暂存目录。没有项目图片时直接使用技能 public 目录。
 */
async function withStagedBundle(timeline, timelinePath, action) {
  const images = imageParams(timeline);
  const videos = videoParams(timeline);
  if (!images.length && !videos.length) {
    return action({ timeline, assets: [], serveUrl: await makeBundle() });
  }
  const root = await findProjectRoot(dirname(resolve(timelinePath)));
  if (!root) throw new Error(`时间轴引用了项目图片，但 ${timelinePath} 的上级目录中找不到 project.json，无法确定项目根目录`);
  const staged = structuredClone(timeline);
  const assets = [];
  const publicDir = await mkdtemp(join(tmpdir(), "videocut-public-"));
  let serveUrl;
  try {
    await linkSkillPublic(publicDir);
    await mkdir(join(publicDir, "project-assets"), { recursive: true });
    for (const { index, slot, path } of images) {
      const absolute = resolve(root, path);
      let buffer;
      try {
        buffer = await readFile(absolute);
      } catch (error) {
        throw new Error(`镜头 ${timeline.tracks.visual[index].shot_id} 的图片无法读取：${absolute}（${error.message}）`);
      }
      const size = imageSize(buffer);
      const digest = sha256(buffer);
      const name = `project-assets/${digest}.${size.format === "png" ? "png" : "jpg"}`;
      await writeFile(join(publicDir, name), buffer);
      const clip = staged.tracks.visual[index];
      const stagedImage = { image: name, image_size: [size.width, size.height] };
      if (slot === null) {
        clip.params = { ...clip.params, ...stagedImage };
      } else {
        // BeforeAfter 截图对比：改写 params.images[slot]，其余项保持原样
        clip.params = { ...clip.params, images: clip.params.images.map((item, i) => (i === slot ? { ...item, ...stagedImage } : item)) };
      }
      assets.push({ shot_id: clip.shot_id, slot, path, sha256: digest, width: size.width, height: size.height });
    }
    for (const { index, path } of videos) {
      assets.push(await stageVideo({ root, publicDir, clip: staged.tracks.visual[index], path, fps: timeline.fps }));
    }
    serveUrl = await makeBundle(publicDir);
  } finally {
    await rm(publicDir, { recursive: true, force: true });
  }
  return action({ timeline: staged, assets, serveUrl });
}

/**
 * 暂存一段录屏工作副本：按内容校验值命名为 project-assets/<sha256>.mp4，读取尺寸与时长，把倍速算定后写进时间轴副本。
 * 源区间读到工作副本结尾之后就直接报错——不能靠定格或循环悄悄补画面（数据合同第 6 节）。
 * 工作副本须为恒定帧率 H.264，且已在项目里完成裁切与打码；本函数只搬运，不改画面。
 */
async function stageVideo({ root, publicDir, clip, path, fps }) {
  const absolute = resolve(root, path);
  let buffer;
  try {
    buffer = await readFile(absolute);
  } catch (error) {
    throw new Error(`镜头 ${clip.shot_id} 的录屏片段无法读取：${absolute}（${error.message}）`);
  }
  const digest = sha256(buffer);
  const name = `project-assets/${digest}.mp4`;
  await writeFile(join(publicDir, name), buffer);
  const meta = await getVideoMetadata(absolute, { logLevel: "error" });
  if (!meta.width || !meta.height || !meta.durationInSeconds) throw new Error(`镜头 ${clip.shot_id} 的录屏片段读不出尺寸或时长：${absolute}`);
  const durationMs = Math.floor(meta.durationInSeconds * 1000);
  const play = clipPlayback(clip.params, clip.end_frame - clip.start_frame, fps);
  if (play.source_end_ms > durationMs) {
    throw new Error(`镜头 ${clip.shot_id} 需要读到第 ${Math.round(play.source_end_ms)} 毫秒（倍速 ${play.rate.toFixed(2)}），录屏片段只有 ${durationMs} 毫秒`);
  }
  clip.params = { ...clip.params, video: name, video_size: [meta.width, meta.height], playback_rate: play.rate };
  return { shot_id: clip.shot_id, slot: "video", path, sha256: digest, width: meta.width, height: meta.height, duration_ms: durationMs, source_in_ms: play.source_in_ms, source_end_ms: Math.round(play.source_end_ms), playback_rate: play.rate };
}

function toolVersions() {
  const require = createRequire(import.meta.url);
  return { node: process.version, remotion: require("remotion/package.json").version, "@remotion/renderer": require("@remotion/renderer/package.json").version };
}

async function listFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true, recursive: true });
  return entries.filter((entry) => entry.isFile()).map((entry) => join(entry.parentPath ?? entry.path, entry.name));
}

/**
 * 渲染代码校验值：src/、scripts/、public/wallpapers/ 全部文件与 package-lock.json。上层用它判断能否复用已有画面——
 * 时间轴和代码都没变才跳过重渲染；场景、风景底图或编码参数改过就必须重渲染。字体由 setup:fonts 按固定校验值下载，不计入。
 * Git 换行转换（CRLF）会改变校验值，只用于同一台机器上的复用判断。
 */
async function codeSha256() {
  const files = [
    ...(await listFiles(join(SKILL_ROOT, "src"))),
    ...(await listFiles(join(SKILL_ROOT, "scripts"))),
    ...(await listFiles(join(SKILL_ROOT, "public", "wallpapers"))),
    join(SKILL_ROOT, "package-lock.json"),
  ];
  const digest = createHash("sha256");
  for (const file of files.map((path) => relative(SKILL_ROOT, path).replaceAll("\\", "/")).sort()) {
    digest.update(`${file}\0${sha256(await readFile(join(SKILL_ROOT, file)))}\n`);
  }
  return digest.digest("hex");
}

async function renderSampleStills({ composition, serveUrl, inputProps, frames }) {
  // 抽样帧按整分辨率截无损 PNG；只留校验值，图片放临时目录用完即删
  const dir = await mkdtemp(join(tmpdir(), "videocut-sample-"));
  try {
    const stills = [];
    for (const frame of frames) {
      const output = join(dir, `${frame}.png`);
      await renderStill({ composition, serveUrl, frame, inputProps, output, scale: 1, imageFormat: "png" });
      stills.push({ frame, sha256: sha256(await readFile(output)) });
    }
    return stills;
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

async function writeRenderRecord(out, record) {
  const buffer = await readFile(out);
  const full = { schema_version: "1.0", ...record, code_sha256: await codeSha256(), output: { path: out, sha256: sha256(buffer), bytes: (await stat(out)).size }, tool_versions: toolVersions(), rendered_at: localIsoTimestamp() };
  await writeFile(`${out}.render.json`, `${JSON.stringify(full, null, 2)}\n`, "utf8");
  return full.output.sha256;
}

function progressLogger() {
  let lastPercent = -10;
  return ({ progress }) => {
    const percent = Math.floor(progress * 100);
    if (percent >= lastPercent + 10) {
      lastPercent = percent;
      console.log(`渲染 ${percent}%`);
    }
  };
}

async function checkOnly(values) {
  const { timeline, timelineSha } = await loadTimeline(values.timeline);
  console.log(`timeline 检查通过：${timeline.tracks.visual.length} 个镜头，${timeline.tracks.caption.length} 条字幕，${timeline.duration_frames} 帧，sha256 ${timelineSha}`);
}

async function renderVideo(values) {
  const { timeline: loaded, timelineSha } = await loadTimeline(values.timeline);
  const backdrop = await applyBackdrops(loaded, await resolveBackdropTheme(values));
  return withStagedBundle(backdrop.timeline, values.timeline, ({ timeline, assets, serveUrl }) =>
    renderVideoWith(values, { timeline, timelineSha, assets, serveUrl, backdrop }),
  );
}

async function renderVideoWith(values, { timeline, timelineSha, assets, serveUrl, backdrop }) {
  const inputProps = { timeline, brand: values.brand ?? DEFAULT_BRAND, aiLabel: await resolveAiLabel(values) };
  const scale = Number(values.scale ?? 1);
  const frameRange = parseFrameRange(values.frames);
  const composition = await selectComposition({ serveUrl, id: "Video", inputProps });
  const out = resolve(values.out);
  const temporary = `${out}.rendering.mp4`;
  await mkdir(dirname(out), { recursive: true });
  await renderMedia({ composition, serveUrl, inputProps, outputLocation: temporary, scale, frameRange, onProgress: progressLogger(), ...VIDEO_SETTINGS });
  // 先写临时文件，完整渲染成功后再替换，失败时保留上一版可用文件
  await rm(out, { force: true });
  await rename(temporary, out);
  const isFullRender = scale === 1 && !frameRange;
  const sampleStills = isFullRender ? await renderSampleStills({ composition, serveUrl, inputProps, frames: sampleFrames(timeline) }) : null;
  const outputSha = await writeRenderRecord(out, {
    kind: "video",
    sample_stills: sampleStills,
    input: { timeline_path: resolve(values.timeline), timeline_sha256: timelineSha, voice_audio_sha256: timeline.voice_audio_sha256 ?? null, images: assets, backdrops: backdrop.assignments },
    settings: { ...VIDEO_SETTINGS, scale, frame_range: frameRange, width: composition.width * scale, height: composition.height * scale, fps: composition.fps, duration_frames: composition.durationInFrames, brand: inputProps.brand, ai_label: inputProps.aiLabel, backdrop_theme: backdrop.theme },
  });
  const renderedFrames = frameRange ? frameRange[1] - frameRange[0] + 1 : composition.durationInFrames;
  console.log(`已输出 ${out}（${renderedFrames} 帧，${composition.width * scale}x${composition.height * scale}，${composition.fps}fps，sha256 ${outputSha}）`);
}

async function renderStills(values) {
  const { timeline: loaded } = await loadTimeline(values.timeline);
  const { timeline: source } = await applyBackdrops(loaded, await resolveBackdropTheme(values));
  return withStagedBundle(source, values.timeline, ({ timeline, serveUrl }) => renderStillsWith(values, timeline, serveUrl));
}

async function renderStillsWith(values, timeline, serveUrl) {
  const inputProps = { timeline, brand: values.brand ?? DEFAULT_BRAND, aiLabel: await resolveAiLabel(values) };
  const composition = await selectComposition({ serveUrl, id: "Video", inputProps });
  const outDir = resolve(values["out-dir"]);
  await mkdir(outDir, { recursive: true });
  for (const { name, frame } of reviewFrames(timeline)) {
    const output = join(outDir, `${String(frame).padStart(5, "0")}-${name}.png`);
    await renderStill({ composition, serveUrl, frame, inputProps, output, scale: Number(values.scale ?? 0.5), imageFormat: "png" });
    console.log(`截帧 ${frame} -> ${output}`);
  }
}

async function renderCover(values) {
  const { data: inputProps, sha256: propsSha } = await readJsonWithHash(values.props);
  const serveUrl = await makeBundle();
  const composition = await selectComposition({ serveUrl, id: "Cover", inputProps });
  const out = resolve(values.out);
  await mkdir(dirname(out), { recursive: true });
  await renderStill({ composition, serveUrl, frame: 0, inputProps, output: out, imageFormat: "png" });
  const outputSha = await writeRenderRecord(out, { kind: "cover", input: { props_path: resolve(values.props), props_sha256: propsSha }, settings: { width: composition.width, height: composition.height, image_format: "png" } });
  console.log(`封面 -> ${out}（sha256 ${outputSha}）`);
}

async function verifyRecord(values) {
  const { timeline: source, timelineSha } = await loadTimeline(values.timeline);
  const { data: record } = await readJsonWithHash(values.record);
  if (!record.sample_stills?.length) throw new Error(`${values.record} 没有抽样帧记录（只有整片正式渲染才会记录）`);
  if (record.input?.timeline_sha256 !== timelineSha) throw new Error("时间轴与渲染记录不一致：画面对应的是旧时间轴，应重新渲染而不是验证");
  // 按渲染时记录的底图题材重新分配，而不是读当前 brief：验证的是那一次渲染能否复现
  const { timeline: themed } = await applyBackdrops(source, parseBackdropTheme(record.settings?.backdrop_theme));
  return withStagedBundle(themed, values.timeline, ({ timeline, assets, serveUrl }) => {
    const recorded = JSON.stringify((record.input?.images ?? []).map((item) => item.sha256));
    if (recorded !== JSON.stringify(assets.map((item) => item.sha256))) throw new Error("项目图片与渲染记录不一致：画面对应的是旧图片，应重新渲染而不是验证");
    return verifyWith(record, timeline, serveUrl);
  });
}

async function verifyWith(record, timeline, serveUrl) {
  const inputProps = { timeline, brand: record.settings?.brand ?? DEFAULT_BRAND, aiLabel: record.settings?.ai_label ?? DEFAULT_AI_LABEL };
  const composition = await selectComposition({ serveUrl, id: "Video", inputProps });
  const actual = await renderSampleStills({ composition, serveUrl, inputProps, frames: record.sample_stills.map((item) => item.frame) });
  const frames = record.sample_stills.map((expected, index) => ({ frame: expected.frame, expected: expected.sha256, actual: actual[index].sha256 }));
  const result = { passed: frames.every((item) => item.expected === item.actual), code_changed: (await codeSha256()) !== record.code_sha256, frames };
  console.log(JSON.stringify(result, null, 2));
  return result.passed ? 0 : 1;
}

async function printCodeHash() {
  console.log(await codeSha256());
}

/** 导入文字动效时间表（TypeScript 源码，与画面同一份）；运行时不支持类型剥离时给出明确提示。 */
async function loadKineticPlanner() {
  try {
    return await import("../src/kinetic.ts");
  } catch (error) {
    throw new Error(`无法导入 src/kinetic.ts（${error.message}）：需要 Node 23.6+；Node 22.6～23.5 请用 node --experimental-strip-types scripts/render.mjs actions …`);
  }
}

/**
 * actions.json：记录时间轴与渲染代码校验值，av-export 据此判断动作标记是否对应当前画面。
 * 写临时文件再改名，失败时保留上一版。
 */
async function exportActions(values) {
  const { timeline, timelineSha } = await loadTimeline(values.timeline);
  const marks = collectActions(timeline, await loadKineticPlanner());
  const record = {
    schema_version: "1.0",
    timeline: { path: values.timeline, sha256: timelineSha },
    fps: timeline.fps,
    duration_frames: timeline.duration_frames,
    code_sha256: await codeSha256(),
    source: "remotion-render planKinetic（目前只有 KineticText 导出动作标记）",
    marks,
    created_at: localIsoTimestamp(),
  };
  const out = resolve(values.out);
  await mkdir(dirname(out), { recursive: true });
  await writeFile(`${out}.tmp`, `${JSON.stringify(record, null, 2)}\n`, "utf8");
  await rename(`${out}.tmp`, out);
  console.log(`动作标记 ${marks.length} 个 -> ${out}`);
}

const COMMANDS = { check: checkOnly, video: renderVideo, stills: renderStills, cover: renderCover, verify: verifyRecord, "code-hash": printCodeHash, actions: exportActions };
const REQUIRED = { check: ["timeline"], video: ["timeline", "out"], stills: ["timeline", "out-dir"], cover: ["props", "out"], verify: ["timeline", "record"], "code-hash": [], actions: ["timeline", "out"] };

async function main() {
  const [command, ...rest] = process.argv.slice(2);
  if (!COMMANDS[command]) {
    console.error("用法：node scripts/render.mjs <check|video|stills|cover|verify|code-hash|actions> ...（见 SKILL.md）");
    return 2;
  }
  const { values } = parseArgs({
    args: rest,
    options: {
      timeline: { type: "string" },
      out: { type: "string" },
      "out-dir": { type: "string" },
      props: { type: "string" },
      record: { type: "string" },
      scale: { type: "string" },
      frames: { type: "string" },
      brand: { type: "string" },
      "ai-label": { type: "string" },
      "backdrop-theme": { type: "string" },
    },
  });
  const missing = REQUIRED[command].filter((key) => !values[key]);
  if (missing.length) {
    console.error(`缺少参数：${missing.map((key) => `--${key}`).join(" ")}`);
    return 2;
  }
  // verify 以退出码表示比对结果；其余命令成功即 0
  return (await COMMANDS[command](values)) ?? 0;
}

main()
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error(`[失败] ${error.message}`);
    process.exit(1);
  });
