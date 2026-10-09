/**
 * INPUT: src/markup.ts（类型剥离导入）、scripts/lib.mjs 的 textUnits
 * OUTPUT: node:test 用例：语义色解析（中文名与英文键名、默认色、未知名报错）、色名不计宽、逐字带色、语义色统计、预设色值与系列紫一致
 * POS: 「按文案意思选颜色」预设的离线测试。没写语义色的 {…} 必须仍是品牌紫，保证旧项目重渲染结果不变。
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { TONES, parseAccent, plainText, resolveTone, semanticTones, stripToneMarks, toneChars, toneColor } from "../src/markup.ts";
import { textUnits } from "../scripts/lib.mjs";

test("没写语义色的 {…} 用默认色（品牌紫），写了的按中文名或英文键名取色", () => {
  assert.deepEqual(parseAccent("每次都{熬夜}"), [
    { text: "每次都", accent: false, tone: null },
    { text: "熬夜", accent: true, tone: "brand" },
  ]);
  assert.equal(parseAccent("{熬夜|痛点}")[0].tone, "pain");
  assert.equal(parseAccent("{半天|gain}")[0].tone, "gain");
  assert.equal(parseAccent("{12}", "data")[0].tone, "data");
  assert.equal(plainText("{熬夜|痛点}到{两点}"), "熬夜到两点");
});

test("未知的语义色名直接报错，不悄悄退回紫色", () => {
  assert.throws(() => resolveTone("高兴"), /未知的语义色/);
  assert.throws(() => parseAccent("{词|高兴}"), /未知的语义色/);
});

test("品牌紫与系列原有色值一致，深色底用提亮版本", () => {
  assert.equal(toneColor("brand"), "#6A3CE9");
  assert.equal(toneColor("brand", true), "#9773FC");
  assert.equal(Object.keys(TONES).length, 5);
});

test("色名不上屏、不计宽：渲染与时间轴检查两处一致", () => {
  assert.equal(stripToneMarks("每次{熬夜|痛点}到{两点}"), "每次{熬夜}到{两点}");
  assert.equal(textUnits("每次{熬夜|痛点}"), textUnits("每次熬夜"));
});

test("逐字带色与语义色统计（品牌紫不计入）", () => {
  assert.deepEqual(toneChars("a{bc|数据}"), [
    { char: "a", tone: null },
    { char: "b", tone: "data" },
    { char: "c", tone: "data" },
  ]);
  assert.deepEqual(semanticTones("{熬夜|痛点}换成{半天|解法}，{品牌}"), ["pain", "gain"]);
});
