/**
 * INPUT: scripts/lib.mjs
 * OUTPUT: node:test 用例：字宽估算（含强调标记）、帧区间解析、时间轴结构检查（含图片场景与录屏片段场景）、审片截帧位置、带时区时间戳、图片尺寸读取、AI 角标文字来源、
 *         录屏片段的引用收集与倍速计算、按题材分配底图，以及底图清单与 src/wallpapers.ts 的一致性
 * POS: 渲染技能的离线测试。不加载 Remotion、不启动浏览器、不联网，运行 npm test 即可。
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  aiLabelFor,
  assignBackdrops,
  clipPlayback,
  DEFAULT_AI_LABEL,
  imageParams,
  imageSize,
  localIsoTimestamp,
  parseBackdropTheme,
  parseFrameRange,
  reviewFrames,
  sampleFrames,
  textUnits,
  validateTimeline,
  videoParams,
  wallpaperGroups,
} from "../scripts/lib.mjs";

const SKILL_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

function makeTimeline(overrides = {}) {
  return {
    width: 1080,
    height: 1920,
    fps: 30,
    duration_frames: 100,
    tracks: {
      visual: [
        { id: "v1", shot_id: "s1", scene_type: "ResultHook", params: {}, start_frame: 0, end_frame: 40 },
        { id: "v2", shot_id: "s2", scene_type: "StepFlow", params: {}, start_frame: 40, end_frame: 100 },
      ],
      caption: [
        { id: "c1", text: "短字幕", start_frame: 5, end_frame: 30 },
        { id: "c2", text: "这是一条明显更宽的字幕 Forward Deployed", start_frame: 45, end_frame: 90 },
      ],
    },
    ...overrides,
  };
}

test("textUnits：汉字与间隔号计 1，拉丁字符计 0.6，空格计 0.25", () => {
  assert.equal(textUnits("前线部署"), 4);
  assert.ok(Math.abs(textUnits("FDE") - 1.8) < 1e-9);
  assert.ok(Math.abs(textUnits("写代码 · 推上线") - (6 + 1 + 0.5)) < 1e-9);
  assert.equal(textUnits("？"), 1);
});

test("textUnits：强调标记的花括号不计宽", () => {
  assert.equal(textUnits("满屏{色块}"), 4);
});

test("parseFrameRange：解析、空值与非法输入", () => {
  assert.deepEqual(parseFrameRange("0-89"), [0, 89]);
  assert.equal(parseFrameRange(undefined), null);
  assert.throws(() => parseFrameRange("10"), /起始-结束/);
  assert.throws(() => parseFrameRange("90-10"), /不能小于/);
});

test("validateTimeline：合法时间轴无错误", () => {
  assert.deepEqual(validateTimeline(makeTimeline()), []);
});

test("validateTimeline：镜头之间的空洞、重叠和片尾缺口都会报错", () => {
  const gap = makeTimeline();
  gap.tracks.visual[1].start_frame = 45;
  assert.match(validateTimeline(gap).join("\n"), /空洞/);

  const overlap = makeTimeline();
  overlap.tracks.visual[1].start_frame = 35;
  assert.match(validateTimeline(overlap).join("\n"), /重叠/);

  const short = makeTimeline();
  short.tracks.visual[1].end_frame = 90;
  assert.match(validateTimeline(short).join("\n"), /结束于第 90 帧/);
});

test("validateTimeline：未支持的场景与越界字幕会报错", () => {
  const timeline = makeTimeline();
  timeline.tracks.visual[0].scene_type = "SplitScreen";
  timeline.tracks.caption[1].end_frame = 120;
  const errors = validateTimeline(timeline).join("\n");
  assert.match(errors, /未支持的场景类型 SplitScreen/);
  assert.match(errors, /超出片长/);
});

test("validateTimeline：ScreenFocus 必须带 params.image，带了即通过", () => {
  const missing = makeTimeline();
  missing.tracks.visual[0].scene_type = "ScreenFocus";
  assert.match(validateTimeline(missing).join("\n"), /ScreenFocus 缺少 params\.image/);
  const withImage = makeTimeline();
  withImage.tracks.visual[0] = { ...withImage.tracks.visual[0], scene_type: "ScreenFocus", params: { image: "assets/original/image_001.png" } };
  assert.deepEqual(validateTimeline(withImage), []);
  assert.deepEqual(imageParams(withImage), [{ index: 0, slot: null, path: "assets/original/image_001.png" }]);
});

test("Illustration：校验图片、收集本地素材引用，并拒绝挤占插图区的多行标题", () => {
  const timeline = makeTimeline();
  timeline.tracks.visual[0].scene_type = "Illustration";
  assert.match(validateTimeline(timeline).join("\n"), /Illustration 缺少 params\.image/);
  timeline.tracks.visual[0].params = { image: "assets/original/illustration.png", title: "资料整理\n与交付" };
  assert.deepEqual(validateTimeline(timeline), []);
  assert.deepEqual(imageParams(timeline), [{ index: 0, slot: null, path: "assets/original/illustration.png" }]);
  timeline.tracks.visual[0].params.title += "\n第三行";
  assert.match(validateTimeline(timeline).join("\n"), /title 最多两行/);
});

test("BeforeAfter 截图对比：images 必须两项且带路径，imageParams 按 slot 列出", () => {
  const compare = makeTimeline();
  compare.tracks.visual[1] = { ...compare.tracks.visual[1], scene_type: "BeforeAfter", params: { images: [{ image: "a.png", tag: "前" }, { image: "b.png", tag: "后" }] } };
  assert.deepEqual(validateTimeline(compare), []);
  assert.deepEqual(imageParams(compare), [
    { index: 1, slot: 0, path: "a.png" },
    { index: 1, slot: 1, path: "b.png" },
  ]);
  compare.tracks.visual[1].params.images = [{ image: "a.png" }];
  assert.match(validateTimeline(compare).join("\n"), /images 必须是两项/);
});

test("imageSize：从 PNG 与 JPEG 文件头读取宽高，其他格式报错", () => {
  const png = Buffer.alloc(24);
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(png, 0);
  png.writeUInt32BE(1080, 16);
  png.writeUInt32BE(785, 20);
  assert.deepEqual(imageSize(png), { width: 1080, height: 785, format: "png" });

  // SOI + APP0（段长 16）+ SOF0（高 1920、宽 1080），验证会跳过前面的段找到帧头
  const app0 = Buffer.concat([Buffer.from([0xff, 0xe0, 0x00, 0x10]), Buffer.alloc(14)]);
  const sof0 = Buffer.from([0xff, 0xc0, 0x00, 0x11, 0x08, 0x07, 0x80, 0x04, 0x38, 0x03, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  const jpeg = Buffer.concat([Buffer.from([0xff, 0xd8]), app0, sof0]);
  assert.deepEqual(imageSize(jpeg), { width: 1080, height: 1920, format: "jpeg" });

  assert.throws(() => imageSize(Buffer.from("GIF89a0000000000")), /只支持 PNG 与 JPEG/);
});

test("validateTimeline：字幕时间倒退与基础字段缺失会报错", () => {
  const timeline = makeTimeline();
  timeline.tracks.caption[1].start_frame = 20;
  assert.match(validateTimeline(timeline).join("\n"), /重叠或时间倒退/);
  assert.match(validateTimeline(makeTimeline({ fps: 29.97 })).join("\n"), /fps 必须是正整数/);
});

test("reviewFrames：包含首末帧、镜头中段和最宽字幕，按帧排序且不重复", () => {
  const frames = reviewFrames(makeTimeline(), 1);
  assert.deepEqual(
    frames.map((item) => item.name),
    ["first", "s1", "caption-c2", "s2", "last"],
  );
  assert.deepEqual(
    frames.map((item) => item.frame),
    [0, 20, 67, 70, 99],
  );
});

test("localIsoTimestamp：输出带时区偏移的秒级时间", () => {
  assert.match(localIsoTimestamp(new Date("2026-09-29T08:00:00Z")), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$/);
});

test("sampleFrames：首帧、中间镜头中段、末帧，去重排序", () => {
  assert.deepEqual(sampleFrames(makeTimeline()), [0, 70, 99]);
});

test("AI 角标：命令行优先，未传时按 brief.aigc.explicit_overlay", () => {
  assert.equal(aiLabelFor("", { aigc: { explicit_overlay: "corner_badge" } }), "");
  assert.equal(aiLabelFor("配音由 AI 合成", null), "配音由 AI 合成");
  assert.equal(aiLabelFor(undefined, { aigc: { explicit_overlay: "none" } }), "");
  assert.equal(aiLabelFor(undefined, { aigc: { explicit_overlay: "corner_badge" } }), DEFAULT_AI_LABEL);
  // 旧项目没有该字段：保持原来的默认角标
  assert.equal(aiLabelFor(undefined, { aigc: { final_implicit_label: "none" } }), DEFAULT_AI_LABEL);
  assert.equal(aiLabelFor(undefined, null), DEFAULT_AI_LABEL);
});

function clipTimeline(params) {
  return makeTimeline({
    tracks: {
      visual: [
        { id: "v1", shot_id: "s1", scene_type: "ScreenClip", params, start_frame: 0, end_frame: 60 },
        { id: "v2", shot_id: "s2", scene_type: "StepFlow", params: {}, start_frame: 60, end_frame: 100 },
      ],
      caption: [],
    },
  });
}

test("validateTimeline：ScreenClip 需要 video、入点，以及倍速或出点二者之一", () => {
  assert.deepEqual(validateTimeline(clipTimeline({ video: "assets/work/c.mp4", source_in_ms: 0, source_out_ms: 8000 })), []);
  assert.deepEqual(validateTimeline(clipTimeline({ video: "assets/work/c.mp4", source_in_ms: 1000, playback_rate: 2 })), []);
  const missing = validateTimeline(clipTimeline({ source_in_ms: 0, playback_rate: 1 }));
  assert.ok(missing.some((error) => error.includes("params.video")));
  const both = validateTimeline(clipTimeline({ video: "c.mp4", source_in_ms: 0, playback_rate: 2, source_out_ms: 4000 }));
  assert.ok(both.some((error) => error.includes("二者之一")));
  const backwards = validateTimeline(clipTimeline({ video: "c.mp4", source_in_ms: 5000, source_out_ms: 3000 }));
  assert.ok(backwards.some((error) => error.includes("二者之一")));
});

test("videoParams：只收集 ScreenClip 的 params.video", () => {
  assert.deepEqual(videoParams(clipTimeline({ video: "assets/work/c.mp4", source_in_ms: 0, playback_rate: 1 })), [{ index: 0, path: "assets/work/c.mp4" }]);
  assert.deepEqual(videoParams(makeTimeline()), []);
});

test("clipPlayback：给出点时把源区间铺满镜头，给倍速时按倍速算消耗", () => {
  // 60 帧 @30fps = 2 秒镜头；源区间 16 秒 → 8 倍速，正好读到出点
  const fitted = clipPlayback({ source_in_ms: 30000, source_out_ms: 46000 }, 60, 30);
  assert.equal(fitted.rate, 8);
  assert.equal(fitted.source_end_ms, 46000);
  const fixed = clipPlayback({ source_in_ms: 1000, playback_rate: 1.5 }, 90, 30);
  assert.equal(fixed.source_end_ms, 5500);
});

test("parseBackdropTheme：组名、组名数组、逗号分隔都规整为数组，没设为空", () => {
  assert.deepEqual(parseBackdropTheme("office"), ["office"]);
  assert.deepEqual(parseBackdropTheme(["blueprint", " office "]), ["blueprint", "office"]);
  assert.deepEqual(parseBackdropTheme("blueprint, tech"), ["blueprint", "tech"]);
  assert.deepEqual(parseBackdropTheme(undefined), []);
  assert.deepEqual(parseBackdropTheme(null), []);
});

function backdropTimeline() {
  const shot = (shot_id, scene_type, params = {}) => ({ id: `v-${shot_id}`, shot_id, scene_type, params, start_frame: 0, end_frame: 10 });
  return {
    tracks: {
      visual: [
        shot("s1", "ScreenClip", { video: "a.mp4" }),
        shot("s2", "BeforeAfter", { columns: [["a", "b"]] }), // 文字对比是浅灰底，不分配
        shot("s3", "StepFlow"),
        shot("s4", "ScreenFocus", { image: "b.png", wallpaper: "glacier" }), // 自己写了底图，保持原样
        shot("s5", "ScreenFocus", { image: "c.png" }),
        shot("s6", "ActionEnd"),
        shot("s7", "BeforeAfter", { images: [{ image: "d.png" }, { image: "e.png" }] }), // 截图对比用底图
      ],
      caption: [],
    },
  };
}

test("assignBackdrops：按主题池轮换，跳过非底图场景与已写底图的镜头，不改原对象", () => {
  const groups = { office: ["o1", "o2"], blueprint: ["b1"] };
  const source = backdropTimeline();
  const { timeline, assignments } = assignBackdrops(source, ["office", "blueprint"], groups);
  assert.deepEqual(assignments, [
    { shot_id: "s1", wallpaper: "o1" },
    { shot_id: "s3", wallpaper: "o2" },
    { shot_id: "s5", wallpaper: "b1" },
    { shot_id: "s7", wallpaper: "o1" },
  ]);
  assert.equal(timeline.tracks.visual[3].params.wallpaper, "glacier");
  assert.equal(timeline.tracks.visual[1].params.wallpaper, undefined);
  assert.equal(source.tracks.visual[0].params.wallpaper, undefined);
});

test("assignBackdrops：没设主题原样返回；未知组名报错", () => {
  const source = backdropTimeline();
  assert.equal(assignBackdrops(source, [], { office: ["o1"] }).timeline, source);
  assert.throws(() => assignBackdrops(source, ["space"], { office: ["o1"] }), /未知的底图组 space/);
});

test("底图清单：每张都有组、文件与校验值，id 与 src/wallpapers.ts 一致", () => {
  const manifest = JSON.parse(readFileSync(join(SKILL_ROOT, "public", "wallpapers", "manifest.json"), "utf8"));
  for (const item of manifest.wallpapers) {
    assert.ok(item.group, `${item.id} 缺 group`);
    assert.equal(item.sha256?.length, 64, `${item.id} 缺 sha256`);
    assert.ok(statSync(join(SKILL_ROOT, "public", "wallpapers", item.file)).size > 0, `${item.id} 文件缺失`);
  }
  const source = readFileSync(join(SKILL_ROOT, "src", "wallpapers.ts"), "utf8");
  const listed = [...source.slice(source.indexOf("WALLPAPER_IDS"), source.indexOf("] as const")).matchAll(/"([a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(listed, manifest.wallpapers.map((item) => item.id));
  assert.deepEqual(Object.keys(wallpaperGroups(manifest)), ["nature", "office", "blueprint", "tech", "city"]);
});
