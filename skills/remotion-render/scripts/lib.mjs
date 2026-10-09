/**
 * INPUT: timeline.json 对象（docs/DATA_CONTRACTS.md 第 6 节）；命令行里的帧区间文字
 * OUTPUT: SUPPORTED_SCENES、textUnits、parseFrameRange、validateTimeline、reviewFrames、sampleFrames、localIsoTimestamp、
 *         imageParams（时间轴里引用的项目图片）、imageSize（PNG / JPEG 头部读宽高）、aiLabelFor（AI 标识角标文字）、
 *         videoParams（时间轴里引用的项目录屏片段）、clipPlayback（录屏片段的源区间与播放倍速）、
 *         parseBackdropTheme / wallpaperGroups / assignBackdrops（按题材组给镜头分配底图）、KINETIC_EFFECTS（文字动效的效果名）、
 *         collectActions（全片动作标记，供 av-export 排音效轨）
 * POS: 渲染技能的纯逻辑部分，不加载 Remotion、不访问文件和网络，便于单独测试。render.mjs 负责调用它们并执行渲染。
 */

// 与 src/types.ts 的 SceneType 保持一致；新增场景时两处同步
export const SUPPORTED_SCENES = ["ResultHook", "StepFlow", "EvidenceCard", "BeforeAfter", "ActionEnd", "ChapterDivider", "ScreenFocus", "ScreenClip", "Illustration", "KineticText"];
// 必须带图片的场景：图片路径相对项目根目录（含 project.json 的目录），渲染前由 render.mjs 暂存到 public 目录
export const IMAGE_SCENES = ["ScreenFocus", "Illustration"];
// 必须带录屏片段的场景：params.video 同样相对项目根目录，由 render.mjs 暂存并读取时长、尺寸
export const VIDEO_SCENES = ["ScreenClip"];
// 以底图为背景的场景；BeforeAfter 只有截图对比（params.images）才用底图，文字对比是浅灰底
export const WALLPAPER_SCENES = ["StepFlow", "EvidenceCard", "ScreenFocus", "ScreenClip"];

/**
 * 一行文字的「字宽」（1 = 一个汉字）。与 src/theme.ts 的 textUnits 同一算法（按 NotoSansSC 实测宽度校准）：
 * 空格按 0.25，间隔号 · 在中文字体里是全角按 1，其余拉丁字符与数字按 0.6，汉字与全角符号按 1；
 * 强调标记的花括号 {} 不显示、不计宽。
 */
export function textUnits(text) {
  let units = 0;
  // 语义色名（{词|痛点} 里的「|痛点」）不上屏、不计宽，与 src/markup.ts 的 stripToneMarks 一致
  for (const char of text.replace(/\|[^{}|]*\}/g, "}")) {
    const code = char.codePointAt(0) ?? 0;
    if (char === "{" || char === "}") continue;
    else if (char === " ") units += 0.25;
    else if (char === "·" || code >= 0x2e80) units += 1;
    else units += 0.6;
  }
  return units;
}

/** "0-89" → [0, 89]（Remotion 的 frameRange 两端都包含）；空值返回 null 表示整片。 */
export function parseFrameRange(text) {
  if (!text) return null;
  const match = /^(\d+)-(\d+)$/.exec(text);
  if (!match) throw new Error(`--frames 格式应为 起始-结束，如 0-89，收到 ${text}`);
  const range = [Number(match[1]), Number(match[2])];
  if (range[1] < range[0]) throw new Error(`--frames 结束帧不能小于起始帧：${text}`);
  return range;
}

const isPositiveInteger = (value) => Number.isInteger(value) && value > 0;

function validateVisualTrack(visual, durationFrames, errors) {
  if (!Array.isArray(visual) || visual.length === 0) {
    errors.push("tracks.visual 为空：主画面必须覆盖整条时间轴");
    return;
  }
  // 区间左闭右开 [start, end)：第一个镜头从 0 开始，每个镜头紧接上一个，最后一个结束于片尾
  let expectedStart = 0;
  for (const clip of visual) {
    const label = clip.shot_id ?? clip.id ?? "未知镜头";
    if (!SUPPORTED_SCENES.includes(clip.scene_type)) {
      errors.push(`${label}：未支持的场景类型 ${clip.scene_type}`);
    }
    if (IMAGE_SCENES.includes(clip.scene_type) && (typeof clip.params?.image !== "string" || !clip.params.image.trim())) {
      errors.push(`${label}：${clip.scene_type} 缺少 params.image（相对项目根目录的图片路径）`);
    }
    if (VIDEO_SCENES.includes(clip.scene_type)) validateClipParams(clip.params ?? {}, label, errors);
    if (clip.scene_type === "KineticText") validateKineticParams(clip, label, errors);
    if (clip.scene_type === "Illustration" && typeof clip.params?.title === "string" && clip.params.title.split("\n").length > 2) {
      errors.push(`${label}：Illustration 的 title 最多两行`);
    }
    if (clip.scene_type === "BeforeAfter" && Array.isArray(clip.params?.images)) {
      if (clip.params.images.length !== 2 || !clip.params.images.every((item) => isPath(item?.image))) {
        errors.push(`${label}：BeforeAfter 的 params.images 必须是两项，每项带 image（相对项目根目录的图片路径）`);
      }
    }
    if (!Number.isInteger(clip.start_frame) || !Number.isInteger(clip.end_frame) || clip.end_frame <= clip.start_frame) {
      errors.push(`${label}：帧区间无效 [${clip.start_frame}, ${clip.end_frame})`);
      continue;
    }
    if (clip.start_frame !== expectedStart) {
      const kind = clip.start_frame > expectedStart ? "空洞" : "重叠";
      errors.push(`${label}：与上一镜头之间存在${kind}，期望从第 ${expectedStart} 帧开始，实际 ${clip.start_frame}`);
    }
    expectedStart = clip.end_frame;
  }
  if (expectedStart !== durationFrames) {
    errors.push(`主画面结束于第 ${expectedStart} 帧，片长为 ${durationFrames} 帧`);
  }
}

const isNonNegative = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;

/** ScreenClip 的源区间：入点必填；倍速与出点二选一（给出点时倍速由镜头时长反推，见 clipPlayback）。 */
function validateClipParams(params, label, errors) {
  if (!isPath(params.video)) errors.push(`${label}：ScreenClip 缺少 params.video（相对项目根目录的 MP4 工作副本路径）`);
  if (!isNonNegative(params.source_in_ms)) errors.push(`${label}：ScreenClip 的 source_in_ms 必须是非负毫秒数`);
  const hasRate = typeof params.playback_rate === "number" && params.playback_rate > 0;
  const hasOut = isNonNegative(params.source_out_ms) && params.source_out_ms > params.source_in_ms;
  if (hasRate === hasOut) errors.push(`${label}：ScreenClip 需要 playback_rate（正数）或 source_out_ms（大于入点）二者之一`);
}

// 与 src/kinetic.ts 的 KINETIC_EFFECTS 保持一致；新增效果时两处同步
export const KINETIC_EFFECTS = ["drop", "pop", "count", "strike", "highlight", "type", "fly", "dissolve"];

/**
 * KineticText 的结构检查：1～4 拍、效果名有效、at / out_at 在 0～1 且 out_at 晚于 at、strike 必须带 replace、
 * 只有 strike / dissolve 可写 replace、只有 fly / dissolve 可写 out_at、count 的文字里有整数。
 * 拍子能否在镜头内停稳要按场景动画时长算，由 src/kinetic.ts 的 planKinetic 在渲染时报错。
 * 文字动效从空白开始逐拍出现，第 0 帧不是完整画面，不能作开头镜头（开头规则见 Video.tsx 的预滚）。
 */
function validateKineticParams(clip, label, errors) {
  const beats = clip.params?.beats;
  if (clip.start_frame === 0) errors.push(`${label}：KineticText 第 0 帧没有完整画面，不能作开头镜头`);
  if (!Array.isArray(beats) || beats.length < 1 || beats.length > 4) {
    errors.push(`${label}：KineticText 需要 params.beats（1～4 拍）`);
    return;
  }
  beats.forEach((beat, index) => {
    const where = `${label}：KineticText 第 ${index + 1} 拍`;
    if (typeof beat?.text !== "string" || !beat.text.trim()) errors.push(`${where}缺少 text`);
    if (!KINETIC_EFFECTS.includes(beat?.effect)) errors.push(`${where}的 effect 只能是 ${KINETIC_EFFECTS.join(" / ")}`);
    const ratio = (value) => typeof value === "number" && value >= 0 && value < 1;
    if (beat?.at !== undefined && !ratio(beat.at)) errors.push(`${where}的 at 必须在 0～1 之间`);
    const hasReplace = typeof beat?.replace === "string" && beat.replace.trim() !== "";
    if (beat?.effect === "strike" && !hasReplace) errors.push(`${where}是 strike，需要 replace`);
    if (hasReplace && !["strike", "dissolve"].includes(beat?.effect)) errors.push(`${where}：只有 strike / dissolve 可以写 replace`);
    if (beat?.out_at !== undefined) {
      if (!["fly", "dissolve"].includes(beat?.effect)) errors.push(`${where}：只有 fly / dissolve 可以写 out_at`);
      else if (!ratio(beat.out_at) || beat.out_at <= (beat.at ?? 0)) errors.push(`${where}的 out_at 必须在 0～1 之间且晚于 at`);
    }
    if (beat?.effect === "count" && !/\d+/.test(String(beat.text ?? ""))) errors.push(`${where}是 count，text 里需要一个整数`);
  });
}

function validateCaptionTrack(captions, durationFrames, errors) {
  if (!Array.isArray(captions)) {
    errors.push("tracks.caption 缺失");
    return;
  }
  let previousEnd = 0;
  for (const caption of captions) {
    const label = caption.id ?? "未知字幕";
    if (!Number.isInteger(caption.start_frame) || !Number.isInteger(caption.end_frame) || caption.end_frame <= caption.start_frame) {
      errors.push(`字幕 ${label}：帧区间无效 [${caption.start_frame}, ${caption.end_frame})`);
      continue;
    }
    if (caption.start_frame < previousEnd) errors.push(`字幕 ${label}：与上一条重叠或时间倒退`);
    if (caption.end_frame > durationFrames) errors.push(`字幕 ${label}：结束于第 ${caption.end_frame} 帧，超出片长 ${durationFrames}`);
    if (typeof caption.text !== "string" || !caption.text.trim()) errors.push(`字幕 ${label}：文字为空`);
    previousEnd = caption.end_frame;
  }
}

/** 渲染前的结构检查，返回错误列表；非空时拒绝渲染，不输出有空洞或越界的成片。 */
export function validateTimeline(timeline) {
  const errors = [];
  if (!timeline || typeof timeline !== "object") return ["timeline 不是 JSON 对象"];
  for (const key of ["width", "height", "fps", "duration_frames"]) {
    if (!isPositiveInteger(timeline[key])) errors.push(`${key} 必须是正整数，收到 ${timeline[key]}`);
  }
  if (errors.length) return errors;
  validateVisualTrack(timeline.tracks?.visual, timeline.duration_frames, errors);
  validateCaptionTrack(timeline.tracks?.caption, timeline.duration_frames, errors);
  return errors;
}

/**
 * 审片截帧位置：首帧、每个镜头中段、最宽的几条字幕中段、末帧。
 * 最宽字幕最容易折行或越界，单独抽出来看；按帧号排序并去重。
 */
export function reviewFrames(timeline, widestCaptionCount = 3) {
  const frames = [{ name: "first", frame: 0 }];
  for (const clip of timeline.tracks.visual) {
    // 文字动效逐拍出现，中段往往还没出齐；取最后一帧（planKinetic 保证各拍此时已停稳）才能看全版面与安全区
    const frame = clip.scene_type === "KineticText" ? clip.end_frame - 1 : Math.floor((clip.start_frame + clip.end_frame) / 2);
    frames.push({ name: clip.shot_id, frame });
  }
  const widest = [...timeline.tracks.caption]
    .sort((a, b) => textUnits(b.text) - textUnits(a.text))
    .slice(0, widestCaptionCount);
  for (const caption of widest) {
    frames.push({ name: `caption-${caption.id}`, frame: Math.floor((caption.start_frame + caption.end_frame) / 2) });
  }
  frames.push({ name: "last", frame: timeline.duration_frames - 1 });
  const seen = new Set();
  return frames
    .sort((a, b) => a.frame - b.frame)
    .filter(({ frame }) => (seen.has(frame) ? false : (seen.add(frame), true)));
}

/** 带本地时区偏移的 ISO 8601 时间（数据合同要求时间点带时区），如 2026-09-29T16:40:00+08:00。 */
export function localIsoTimestamp(date = new Date()) {
  const pad = (value) => String(Math.trunc(Math.abs(value))).padStart(2, "0");
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const local = new Date(date.getTime() + offsetMinutes * 60000).toISOString().slice(0, 19);
  return `${local}${sign}${pad(offsetMinutes / 60)}:${pad(offsetMinutes % 60)}`;
}

/**
 * 可复用抽样帧：首帧、中间镜头的中段、末帧。正式渲染时把这几帧的无损 PNG 校验值写进 render.json，
 * verify 时重新截同样的帧逐字节比对——比整片重渲染快一个数量级，又能证明同一数据与代码得到同一画面。
 */
export function sampleFrames(timeline) {
  const visual = timeline.tracks.visual;
  const middle = visual[Math.floor(visual.length / 2)];
  const frames = [0, Math.floor((middle.start_frame + middle.end_frame) / 2), timeline.duration_frames - 1];
  return [...new Set(frames)].sort((a, b) => a - b);
}

const isPath = (value) => typeof value === "string" && value.trim() !== "";

/**
 * 时间轴里引用的项目图片：[{ index, slot, path }]。index 为 tracks.visual 的下标；
 * slot 为 null 表示 params.image（ScreenFocus），为数字 i 表示 params.images[i].image（BeforeAfter 截图对比）。
 */
export function imageParams(timeline) {
  return timeline.tracks.visual.flatMap((clip, index) => {
    const found = isPath(clip.params?.image) ? [{ index, slot: null, path: clip.params.image }] : [];
    const list = Array.isArray(clip.params?.images) ? clip.params.images : [];
    list.forEach((item, slot) => {
      if (isPath(item?.image)) found.push({ index, slot, path: item.image });
    });
    return found;
  });
}

/** 时间轴里引用的录屏片段：[{ index, path }]，index 为 tracks.visual 的下标。 */
export function videoParams(timeline) {
  return timeline.tracks.visual.flatMap((clip, index) => (VIDEO_SCENES.includes(clip.scene_type) && isPath(clip.params?.video) ? [{ index, path: clip.params.video }] : []));
}

/**
 * 录屏片段在镜头里怎么播：镜头可见时长（帧数 / fps）乘倍速，就是消耗的源时长。
 * 给了 source_out_ms 时把源区间正好铺满镜头，倍速 = 源区间 / 镜头时长——配音定时长、画面跟着变速，不反过来改配音。
 * 返回的 source_end_ms 用于越界检查：不能读到工作副本结尾之后（数据合同第 6 节「不能越界读取素材」）。
 */
export function clipPlayback(params, durationFrames, fps) {
  const shotMs = (durationFrames * 1000) / fps;
  const rate = typeof params.playback_rate === "number" ? params.playback_rate : (params.source_out_ms - params.source_in_ms) / shotMs;
  return { rate, source_in_ms: params.source_in_ms, source_end_ms: params.source_in_ms + shotMs * rate };
}

/**
 * 从文件头读取图片宽高，不依赖图像库。支持 PNG（IHDR 块）与 JPEG（扫描到 SOF0～SOF15 帧头，跳过 DHT/JPG/DAC）。
 * 场景按宽高计算取景与推近，读不出尺寸时直接报错，不猜测。
 */
export function imageSize(buffer) {
  const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (PNG_SIGNATURE.every((byte, index) => buffer[index] === byte)) {
    return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20), format: "png" };
  }
  if (buffer[0] === 0xff && buffer[1] === 0xd8) {
    let offset = 2;
    while (offset + 9 < buffer.length) {
      if (buffer[offset] !== 0xff) throw new Error(`JPEG 结构异常：偏移 ${offset} 处不是标记`);
      const marker = buffer[offset + 1];
      const length = buffer.readUInt16BE(offset + 2);
      const isFrameHeader = marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker);
      if (isFrameHeader) {
        return { width: buffer.readUInt16BE(offset + 7), height: buffer.readUInt16BE(offset + 5), format: "jpeg" };
      }
      offset += 2 + length;
    }
    throw new Error("JPEG 中没有找到帧头（SOF），无法读取尺寸");
  }
  throw new Error("只支持 PNG 与 JPEG 图片");
}

export const DEFAULT_AI_LABEL = "AI 合成配音";

/**
 * 右上角 AI 标识角标的文字：命令行 --ai-label 优先（传空字符串即不画）；未传时按 brief.json 的 aigc.explicit_overlay，
 * "none" 表示账号持有人选择只靠发布时的平台 AI 声明（docs/DESIGN.md 的系列默认），其余情况画默认角标。
 * 让审片静帧与正式画面读同一个来源，避免静帧带角标、成片不带。
 */
export function aiLabelFor(cliValue, brief) {
  if (typeof cliValue === "string") return cliValue;
  return brief?.aigc?.explicit_overlay === "none" ? "" : DEFAULT_AI_LABEL;
}

/** 这个镜头是否以底图为背景（只有这些镜头参与按题材分配）。 */
export function usesWallpaper(clip) {
  return WALLPAPER_SCENES.includes(clip.scene_type) || (clip.scene_type === "BeforeAfter" && Array.isArray(clip.params?.images));
}

/**
 * 底图主题规整为组名数组：brief.visual.backdrop_theme 可写一个组名或组名数组，命令行 --backdrop-theme 写逗号分隔。
 * 没设时返回空数组，渲染沿用各场景自己的默认底图。
 */
export function parseBackdropTheme(value) {
  const list = Array.isArray(value) ? value : typeof value === "string" ? value.split(",") : [];
  return list.map((item) => String(item).trim()).filter(Boolean);
}

/** public/wallpapers/manifest.json → { 组名: [底图 id, …] }，组内顺序与清单一致。 */
export function wallpaperGroups(manifest) {
  const groups = {};
  for (const item of manifest?.wallpapers ?? []) {
    const group = item.group ?? "nature";
    (groups[group] ??= []).push(item.id);
  }
  return groups;
}

/**
 * 按题材给没写 wallpaper 的底图镜头轮换分配底图（主理人 2026-10-07：背景不能每次一样，要按题材换）。
 * 池子是主题各组的图按组顺序拼接；按镜头顺序取 pool[k % n]，k 只在被分配的镜头上递增，
 * 所以池子不少于 2 张时相邻两个被分配的镜头不会用同一张。镜头自己写了 wallpaper 的保持原样、不占轮换位。
 * 没设主题时原样返回，旧项目重渲染结果不变。返回时间轴副本，原对象不改。
 */
export function assignBackdrops(timeline, theme, groups) {
  if (!theme.length) return { timeline, assignments: [] };
  const unknown = theme.filter((group) => !groups[group]?.length);
  if (unknown.length) throw new Error(`未知的底图组 ${unknown.join("、")}；可选：${Object.keys(groups).join("、")}`);
  const pool = theme.flatMap((group) => groups[group]);
  const staged = structuredClone(timeline);
  const assignments = [];
  let next = 0;
  for (const clip of staged.tracks.visual) {
    if (!usesWallpaper(clip) || typeof clip.params?.wallpaper === "string") continue;
    const wallpaper = pool[next % pool.length];
    next += 1;
    clip.params = { ...clip.params, wallpaper };
    assignments.push({ shot_id: clip.shot_id, wallpaper });
  }
  return { timeline: staged, assignments };
}

/**
 * 全片动作标记（配音效用）：目前只有 KineticText 导出，每拍的关键帧由 src/kinetic.ts 的 planKinetic 算出，
 * kinetic 参数传入该模块（{ parseKineticBeats, planKinetic }），本文件保持不依赖 TypeScript 源码、可单独测试。
 * 全片帧号 = 镜头起点 + 镜头内帧号（文字动效不作开头镜头，没有预滚）；time_ms 只供阅读，排音效以 frame 为准。
 */
export function collectActions(timeline, kinetic) {
  const marks = [];
  for (const clip of timeline.tracks.visual) {
    if (clip.scene_type !== "KineticText") continue;
    const plan = kinetic.planKinetic(kinetic.parseKineticBeats(clip.params), clip.end_frame - clip.start_frame, 0, Boolean(clip.params?.icon));
    for (const mark of plan.actions) {
      const frame = clip.start_frame + mark.frame;
      marks.push({ shot_id: clip.shot_id, frame, time_ms: Math.round((frame * 1000) / timeline.fps), kind: mark.kind, target: mark.target });
    }
  }
  return marks.sort((a, b) => a.frame - b.frame);
}
