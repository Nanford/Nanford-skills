/**
 * INPUT: src/kinetic.ts（Node 23.6+ 直接剥离类型导入）、scripts/lib.mjs 的 validateTimeline 与 KINETIC_EFFECTS、sfx-kit 配方表的动作类型（调用本机 python）
 * OUTPUT: node:test 用例：文字动效的参数校验、每拍起止帧（含开头预滚）、动作标记与 sfx-kit 动作类型、数字滚动终值与补位、时间轴检查
 * POS: KineticText 时间表的离线测试。画面与音效对点都依赖这份时间表，所以单独覆盖；不加载 Remotion、不启动浏览器。
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { COUNT_PAD, DEFAULT_TONES, KINETIC_EFFECTS, KINETIC_LAYOUT, TIMING, dissolveReplaceFrame, heightFontLimit, typedCount, countText, countValue, parseKineticBeats, planKinetic } from "../src/kinetic.ts";
import { KINETIC_EFFECTS as LIB_EFFECTS, reviewFrames, validateTimeline } from "../scripts/lib.mjs";

const here = dirname(fileURLToPath(import.meta.url));

/** Windows 上通常叫 python，macOS / Linux 上通常只有 python3：依次尝试。 */
function runPython(script, cwd) {
  for (const command of ["python", "python3"]) {
    try {
      return execFileSync(command, ["-c", script], { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  throw new Error("找不到 python 或 python3：本测试要读取 sfx-kit 的动作类型");
}

test("效果名在渲染代码与时间轴检查两处一致", () => {
  assert.deepEqual([...KINETIC_EFFECTS], LIB_EFFECTS);
});

test("参数校验：拍数、效果名、at 范围、strike 需要 replace、count 需要整数", () => {
  assert.throws(() => parseKineticBeats({}), /1～4 拍/);
  assert.throws(() => parseKineticBeats({ beats: [{ text: "a", effect: "spin" }] }), /effect/);
  assert.throws(() => parseKineticBeats({ beats: [{ text: "a", effect: "pop", at: 1 }] }), /at/);
  assert.throws(() => parseKineticBeats({ beats: [{ text: "a", effect: "strike" }] }), /replace/);
  assert.throws(() => parseKineticBeats({ beats: [{ text: "三小时", effect: "count" }] }), /整数/);
  const beats = parseKineticBeats({ beats: [{ text: "通宵", effect: "strike", at: 0.2, replace: "半天" }] });
  assert.deepEqual(beats, [{ text: "通宵", effect: "strike", at: 0.2, replace: "半天" }]);
});

test("起始帧 = 预滚 + at × 可见时长，取整一次；开头镜头的动作不会被预滚吃掉", () => {
  const beats = parseKineticBeats({ beats: [{ text: "甲", effect: "drop", at: 0 }, { text: "乙", effect: "pop", at: 0.5 }] });
  const plain = planKinetic(beats, 100, 0, false);
  assert.deepEqual(plain.beats.map((beat) => beat.start), [0, 50]);
  const opener = planKinetic(beats, 136, 36, false);
  assert.deepEqual(opener.beats.map((beat) => beat.start), [36, 86]);
});

test("动作标记：每种效果落在约定的关键帧，类型都来自 sfx-kit", () => {
  const beats = parseKineticBeats({
    beats: [
      { text: "落下", effect: "drop", at: 0 },
      { text: "划掉", effect: "strike", at: 0.2, replace: "换上" },
      { text: "{重点}", effect: "highlight", at: 0.5 },
      { text: "弹出", effect: "pop", at: 0.7 },
    ],
  });
  const plan = planKinetic(beats, 200, 0, true);
  // 动作类型的唯一来源是 sfx-kit 的配方表（音效库目录不进 Git，所以直接读配方而不是 manifest）
  const script = "import json; from sfxlib.presets import KIND_TO_SOUNDS; print(json.dumps(list(KIND_TO_SOUNDS)))";
  const kinds = new Set(JSON.parse(runPython(script, join(here, "../../sfx-kit/scripts"))));
  for (const mark of plan.actions) assert.ok(kinds.has(mark.kind), `sfx-kit 没有动作类型 ${mark.kind}`);
  const find = (target, kind) => plan.actions.find((mark) => mark.target === target && mark.kind === kind)?.frame;
  assert.equal(find("icon", "appear_small"), 0);
  assert.equal(find("beat_1", "land"), TIMING.drop.fall);
  assert.equal(find("beat_2", "strike"), 40 + TIMING.strike.strikeAt);
  assert.equal(find("beat_2_replace", "appear"), 40 + TIMING.strike.replaceAt);
  assert.equal(find("beat_3", "highlight"), 100 + TIMING.highlight.sweepAt);
  assert.equal(find("beat_4", "appear"), 141);
  const frames = plan.actions.map((mark) => mark.frame);
  assert.deepEqual(frames, [...frames].sort((a, b) => a - b));
});

test("数字滚动：终值等于原文，跳数间隔不少于 2 帧，位数不足用补位标记补齐", () => {
  const [beat] = planKinetic(parseKineticBeats({ beats: [{ text: "省下 {12} 小时", effect: "count", at: 0 }] }), 60, 0, false).beats;
  assert.equal(countValue(beat, 0), 0);
  assert.equal(countValue(beat, TIMING.count.reveal + TIMING.count.roll), 12);
  assert.equal(countText(beat.text, 5), `省下 {${COUNT_PAD}5} 小时`);
  const ticks = planKinetic([beat], 60, 0, false).actions.map((mark) => mark.frame);
  assert.ok(ticks.length >= 5 && ticks.length <= 12, `跳数 ${ticks.length}`);
  ticks.slice(1).forEach((frame, index) => assert.ok(frame - ticks[index] >= 2));
});

test("图标出现的轻音效与第一拍挤在一起时让位，隔开时保留", () => {
  const close = planKinetic(parseKineticBeats({ beats: [{ text: "甲", effect: "pop", at: 0 }] }), 60, 0, true);
  assert.deepEqual(close.actions.map((mark) => mark.kind), ["appear"]);
  const apart = planKinetic(parseKineticBeats({ beats: [{ text: "甲", effect: "drop", at: 0 }] }), 60, 0, true);
  assert.deepEqual(apart.actions.map((mark) => mark.kind), ["appear_small", "land"]);
});

test("按高度限字号：最坏情况（图标 + 4 拍 strike）叠起来不超出 1100px 内容区，且不小于 80px", () => {
  const beats = parseKineticBeats({ beats: Array.from({ length: 4 }, () => ({ text: "错误说法", effect: "strike", at: 0, replace: "正确说法" })) });
  const available = 1100;
  const size = heightFontLimit(beats, 150, available);
  const { lineHeight, gap, strikeScale, iconMargin } = KINETIC_LAYOUT;
  const height = 150 + size * iconMargin + 4 * size * (1 + strikeScale) * lineHeight + 4 * size * gap;
  assert.ok(height <= available, `高度 ${height}`);
  assert.ok(size >= 80, `字号 ${size}`);
  assert.ok(heightFontLimit(beats.slice(0, 1), 0, available) > 112, "拍数少时由宽度决定字号");
});

test("新效果的参数规则：replace 只给 strike / dissolve，out_at 只给 fly / dissolve 且晚于 at", () => {
  assert.throws(() => parseKineticBeats({ beats: [{ text: "甲", effect: "pop", replace: "乙" }] }), /replace/);
  assert.throws(() => parseKineticBeats({ beats: [{ text: "甲", effect: "type", out_at: 0.5 }] }), /out_at/);
  assert.throws(() => parseKineticBeats({ beats: [{ text: "甲", effect: "fly", at: 0.5, out_at: 0.4 }] }), /晚于/);
  const [beat] = parseKineticBeats({ beats: [{ text: "甲", effect: "dissolve", at: 0.1, out_at: 0.5, replace: "乙" }] });
  assert.deepEqual(beat, { text: "甲", effect: "dissolve", at: 0.1, replace: "乙", outAt: 0.5 });
});

test("打字：每 2 帧一个字，强调标记与色名不算字；打字声最密每 4 帧一下", () => {
  const plan = planKinetic(parseKineticBeats({ beats: [{ text: "按{规则|解法}自动排版", effect: "type", at: 0 }] }), 60, 0, false);
  const [beat] = plan.beats;
  // 「按规则自动排版」共 7 个字
  assert.equal(beat.settle, 7 * TIMING.type.charFrames);
  assert.equal(typedCount(beat, 0), 1);
  assert.equal(typedCount(beat, 13), 7);
  assert.equal(typedCount(beat, 40), 7);
  const frames = plan.actions.map((mark) => mark.frame);
  assert.ok(plan.actions.every((mark) => mark.kind === "type"));
  frames.slice(1).forEach((frame, index) => assert.ok(frame - frames[index] >= 4));
});

test("飞入飞出与粒子消散：退场帧按 out_at 取整，dissolve 不写 out_at 时停留后自动消散，换上说法在碎完后弹出", () => {
  const plan = planKinetic(
    parseKineticBeats({
      beats: [
        { text: "四个字啊", effect: "fly", at: 0, out_at: 0.5 },
        { text: "旧做法", effect: "dissolve", at: 0.1, replace: "新做法" },
      ],
    }),
    200,
    0,
    false,
  );
  const [fly, dissolve] = plan.beats;
  assert.equal(fly.exit, 100);
  assert.equal(fly.settle, 100 + Math.ceil(3 * TIMING.fly.stagger) + TIMING.fly.frames);
  assert.equal(dissolve.exit, 20 + TIMING.dissolve.reveal + TIMING.dissolve.hold);
  assert.equal(dissolveReplaceFrame(dissolve), dissolve.exit + Math.ceil(2 * TIMING.dissolve.stagger) + TIMING.dissolve.replaceAfter);
  const kinds = plan.actions.map((mark) => `${mark.target}:${mark.kind}`);
  assert.ok(kinds.includes("beat_1:transition_in") && kinds.includes("beat_1:transition_out"));
  assert.ok(kinds.includes("beat_2:transition_out") && kinds.includes("beat_2_replace:appear"));
});

test("默认语义色：划掉 / 消散的旧说法痛点色、换上的说法解法色、数字数据色", () => {
  assert.deepEqual(DEFAULT_TONES.strike, { text: "pain", replace: "gain" });
  assert.deepEqual(DEFAULT_TONES.dissolve, { text: "pain", replace: "gain" });
  assert.equal(DEFAULT_TONES.count.text, "data");
  assert.equal(DEFAULT_TONES.pop.text, "brand");
});

test("最后一拍来不及停稳时报错，而不是画到镜头外", () => {
  const beats = parseKineticBeats({ beats: [{ text: "划掉", effect: "strike", at: 0.9, replace: "换上" }] });
  assert.throws(() => planKinetic(beats, 90, 0, false), /停稳/);
});

test("时间轴检查：KineticText 不能作开头镜头，拍子结构有误时报出", () => {
  const timeline = (clips) => ({
    width: 1080,
    height: 1920,
    fps: 30,
    duration_frames: clips.at(-1).end_frame,
    tracks: { visual: clips, caption: [] },
  });
  const hook = { id: "v1", shot_id: "s1", scene_type: "ResultHook", params: { title: "开头" }, start_frame: 0, end_frame: 30 };
  const ok = { id: "v2", shot_id: "s2", scene_type: "KineticText", params: { beats: [{ text: "甲", effect: "pop", at: 0 }] }, start_frame: 30, end_frame: 90 };
  assert.deepEqual(validateTimeline(timeline([hook, ok])), []);
  const opener = { ...ok, start_frame: 0, end_frame: 60 };
  assert.ok(validateTimeline(timeline([opener])).some((error) => error.includes("开头镜头")));
  const broken = { ...ok, params: { beats: [{ text: "甲", effect: "count", at: 0 }] } };
  assert.ok(validateTimeline(timeline([hook, broken])).some((error) => error.includes("整数")));
});

test("审片静帧：文字动效镜头取最后一帧，其他镜头仍取中段", () => {
  const timeline = {
    duration_frames: 120,
    tracks: {
      visual: [
        { shot_id: "hook", scene_type: "ResultHook", start_frame: 0, end_frame: 30 },
        { shot_id: "kinetic", scene_type: "KineticText", start_frame: 30, end_frame: 120 },
      ],
      caption: [],
    },
  };
  const frames = Object.fromEntries(reviewFrames(timeline).map((item) => [item.name, item.frame]));
  assert.equal(frames.hook, 15);
  assert.equal(frames.kinetic, 119);
});

test("全片动作标记：只取文字动效镜头，帧号加镜头起点，按帧排序", async () => {
  const { collectActions } = await import("../scripts/lib.mjs");
  const timeline = {
    fps: 30,
    tracks: {
      visual: [
        { shot_id: "hook", scene_type: "ResultHook", params: { title: "开头" }, start_frame: 0, end_frame: 30 },
        { shot_id: "k", scene_type: "KineticText", params: { beats: [{ text: "落下", effect: "drop", at: 0 }] }, start_frame: 30, end_frame: 90 },
      ],
    },
  };
  const marks = collectActions(timeline, { parseKineticBeats, planKinetic });
  assert.deepEqual(marks, [{ shot_id: "k", frame: 30 + TIMING.drop.fall, time_ms: Math.round(((30 + TIMING.drop.fall) * 1000) / 30), kind: "land", target: "beat_1" }]);
});
