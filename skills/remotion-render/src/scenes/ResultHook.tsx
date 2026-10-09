/**
 * INPUT: params.kicker（小标签）、params.title（大字，\n 分行，{…} 标紫色强调）、可选 params.focus（标题里的一个词，先放大对焦再缩回句中）、
 *        可选 params.backdrop（paper / night，默认 paper）
 * OUTPUT: 开场 / 结论场景：焦点词由糊到清的大字出现 → 缩回句中原位 → 其余文字逐字对焦 → 强调词下方手绘波浪线
 * POS: 第一句痛点或优势开场，以及片中「一句话结论」。入场动画在 36 帧内完成（开头镜头预滚 36 帧，第 0 帧即完整画面），
 *      波浪线在 36 帧之后才描出，给开头第一秒一个动作。
 */

import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { HandUnderline, RevealText } from "../components/Motion";
import { Kicker, SceneShell } from "../components/Frame";
import { COLORS, TEXT_COLUMN_WIDTH, fitFontSize, parseAccent, plainText, progress, stringParam, textUnits, toneColor, type Tone } from "../theme";

const LINE_HEIGHT = 1.3;
// 时间点（帧）：焦点词 0～12 对焦，16～30 缩回句中；其余文字 18 帧起逐字出现；强调线 38 帧起描出
const FOCUS_IN = 12;
const SHRINK_START = 16;
const SHRINK_END = 30;
const UNDERLINE_AT = 38;

interface FocusTarget {
  line: number;
  from: number;
  to: number;
  dx: number;
  dy: number;
  // 焦点词落在强调段里时用该段的语义色，否则为 null（用正文色）
  tone: Tone | null;
}

/** 在标题里找焦点词，按字宽估算它在句中的中心位置（相对标题块中心）。中文字宽为 1em，估算是精确的。 */
function locateFocus(lines: string[], focus: string, fontSize: number): FocusTarget | null {
  for (let line = 0; line < lines.length; line += 1) {
    const source = lines[line] ?? "";
    const plain = plainText(source);
    const at = plain.indexOf(focus);
    if (at < 0) continue;
    const from = Array.from(plain.slice(0, at)).length;
    const dxUnits = textUnits(plain.slice(0, at)) + textUnits(focus) / 2 - textUnits(plain) / 2;
    let cursor = 0;
    let tone: Tone | null = null;
    for (const run of parseAccent(source)) {
      const length = Array.from(run.text).length;
      if (run.tone && from >= cursor && from < cursor + length) tone = run.tone;
      cursor += length;
    }
    return { line, from, to: from + Array.from(focus).length, dx: dxUnits * fontSize, dy: (line - (lines.length - 1) / 2) * fontSize * LINE_HEIGHT, tone };
  }
  return null;
}

/** 第一段强调文字的位置与语义色：用于在它下方画同色手绘线。 */
function locateAccent(line: string): { left: number; width: number; tone: Tone } | null {
  let before = "";
  for (const run of parseAccent(line)) {
    if (run.tone) return { left: textUnits(before), width: textUnits(run.text), tone: run.tone };
    before += run.text;
  }
  return null;
}

export const ResultHook: React.FC<{ params: Record<string, unknown> }> = ({ params }) => {
  const frame = useCurrentFrame();
  const lines = stringParam(params, "title").split("\n");
  const fontSize = fitFontSize(lines, 104, TEXT_COLUMN_WIDTH);
  const focus = stringParam(params, "focus");
  const target = focus ? locateFocus(lines, focus, fontSize) : null;
  const night = stringParam(params, "backdrop") === "night";
  const bigSize = target ? Math.min(fontSize * 2.6, fitFontSize([focus], 280, TEXT_COLUMN_WIDTH)) : fontSize;
  const shrink = progress(frame, SHRINK_START, SHRINK_END - SHRINK_START);
  const focusIn = progress(frame, 0, FOCUS_IN);
  const revealStart = target ? 18 : 4;
  const inkColor = night ? COLORS.nightText : COLORS.ink;
  return (
    <SceneShell backdrop={night ? "night" : "paper"}>
      <Kicker text={stringParam(params, "kicker")} opacity={progress(frame, target ? 22 : 0, 10)} />
      <div style={{ position: "relative", width: TEXT_COLUMN_WIDTH, textAlign: "center" }}>
        {lines.map((line, index) => {
          const accent = locateAccent(line);
          const lineUnits = textUnits(line);
          return (
            <div key={`${index}-${line}`} style={{ lineHeight: LINE_HEIGHT }}>
              <span style={{ position: "relative", display: "inline-block" }}>
                <RevealText
                  text={line}
                  fontSize={fontSize}
                  weight={700}
                  startFrame={revealStart + index * 6}
                  stagger={1}
                  color={inkColor}
                  night={night}
                  fromColor={night ? "#3A3B44" : COLORS.inkFaint}
                  lineHeight={LINE_HEIGHT}
                  hold={target && target.line === index ? { from: target.from, to: target.to, untilFrame: SHRINK_END } : undefined}
                />
                {accent ? (
                  <span
                    style={{
                      position: "absolute",
                      left: (accent.left / lineUnits) * 100 + "%",
                      width: (accent.width / lineUnits) * 100 + "%",
                      top: "96%",
                    }}
                  >
                    <HandUnderline width={accent.width * fontSize} drawFrame={UNDERLINE_AT} color={toneColor(accent.tone, night)} thickness={Math.max(6, fontSize * 0.075)} />
                  </span>
                ) : null}
              </span>
            </div>
          );
        })}
        {target && frame < SHRINK_END ? (
          // 焦点大字：先在画面中央由糊到清，再缩小并移到句中原位；到位的同一帧句中文字接替显示
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              fontSize: bigSize,
              // 与句中文字同字重，交接时不跳变
              fontWeight: 700,
              lineHeight: 1,
              whiteSpace: "nowrap",
              color: target.tone ? toneColor(target.tone, night) : inkColor,
              opacity: focusIn,
              filter: focusIn < 1 ? `blur(${(1 - focusIn) * 28}px)` : undefined,
              translate: `calc(-50% + ${target.dx * shrink}px) calc(-50% + ${target.dy * shrink}px)`,
              // shrink 已带缓动，这里线性映射；对焦阶段从 1.06 轻微收到 1，缩回阶段从 1 缩到句中字号
              scale: String(interpolate(shrink, [0, 1], [1.06 - focusIn * 0.06, fontSize / bigSize])),
            }}
          >
            {focus}
          </div>
        ) : null}
      </div>
    </SceneShell>
  );
};
