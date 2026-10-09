"""
INPUT: 定稿朗读文本；服务商返回的逐字（词）时间戳（毫秒，相对该段音频起点）
OUTPUT: char_times() 把词级时间展开到每个字符；split_lines() 语义断句（可按 break_positions() 换算的人工断点强制断行）；build_captions() 生成带时间的字幕行
POS: 字幕计时与断句的纯函数层，不读写文件，便于单测。字幕文字以定稿为准，时间只取自真实音频的时间戳。
"""

from __future__ import annotations

from dataclasses import dataclass

# 句末标点必断行；逗号类标点在已积累足够长度时断行
SENTENCE_END = set("。！？!?；;")
CLAUSE_BREAK = set("，,、：:")
# 字幕里保留问号、感叹号的语气，其余句读去掉，符合常见短视频字幕习惯
KEEP_TRAILING = set("？！?!")
STRIP_CHARS = set("，,、。；;：:") | {" "}
INLINE_TO_SPACE = ("，", "、", ",")


@dataclass(frozen=True)
class WordTiming:
    char_begin: int  # 在朗读文本中的字符位置，左闭右开
    char_end: int
    start_ms: float
    end_ms: float


@dataclass(frozen=True)
class CaptionLine:
    text: str
    start_ms: float
    end_ms: float


def char_width(char: str) -> float:
    """按屏幕占宽估算：汉字与全角符号记 1，拉丁字母、数字、空格约半个汉字宽。"""
    return 0.55 if ord(char) < 0x2E80 else 1.0


def text_width(text: str) -> float:
    return sum(char_width(c) for c in text)


def char_times(text_length: int, words: list[WordTiming]) -> list[tuple[float, float] | None]:
    """每个字符的发声区间；标点、空格等没有时间戳的字符为 None。一个词内的多个字符平分该词时长。"""
    times: list[tuple[float, float] | None] = [None] * text_length
    for word in words:
        span = max(word.char_end - word.char_begin, 1)
        step = (word.end_ms - word.start_ms) / span
        for offset, index in enumerate(range(word.char_begin, min(word.char_end, text_length))):
            times[index] = (word.start_ms + step * offset, word.start_ms + step * (offset + 1))
    return times


def is_latin(char: str) -> bool:
    return char.isascii() and char.isalnum()


def safe_cut(text: str, start: int, limit: float, protected: list[tuple[int, int]]) -> int:
    """在不超过 limit 宽度的前提下找切点；不把英文单词、数字或受保护的短语（如需换回屏幕写法的日期）切开。"""
    width, cut = 0.0, start
    while cut < len(text) and width + char_width(text[cut]) <= limit:
        width += char_width(text[cut])
        cut += 1
    if cut >= len(text):
        return len(text)
    while cut > start + 1 and is_latin(text[cut]) and is_latin(text[cut - 1]):
        cut -= 1
    for begin, end in protected:
        if begin < cut < end:
            cut = begin if begin > start else end
    return cut if cut > start else start + 1


def protected_spans(text: str, phrases: list[str]) -> list[tuple[int, int]]:
    spans = []
    for phrase in phrases:
        position = text.find(phrase)
        while phrase and position >= 0:
            spans.append((position, position + len(phrase)))
            position = text.find(phrase, position + 1)
    return spans


def break_positions(text: str, phrases: list[str]) -> set[int]:
    """把「在这段文字之后断行」的提示换成原文位置；找不到时报错，防止改稿后旧提示静默失效。"""
    positions = set()
    for phrase in phrases:
        position = text.find(phrase)
        if not phrase or position < 0:
            raise ValueError(f"caption_breaks 里的「{phrase}」不在朗读文本中")
        positions.add(position + len(phrase))
    return positions


def split_lines(text: str, max_width: float = 16, min_clause_width: float = 6, protected: list[tuple[int, int]] | None = None,
                forced: set[int] | None = None) -> list[tuple[int, int]]:
    """返回每行在原文中的 [开始, 结束) 位置；句末必断，逗号处够长才断，超长时安全硬切。

    forced 是人工指定的断行位置（该位置之前的字符为一行的末尾）：没有分词时，硬切可能把
    「列出来」切成「列出 / 来」，由剪辑方在语义处显式断开。
    """
    protected = protected or []
    forced = forced or set()
    spans: list[tuple[int, int]] = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        current = text_width(text[start:index + 1])
        if char in SENTENCE_END or (char in CLAUSE_BREAK and current >= min_clause_width) or index + 1 in forced:
            spans.append((start, index + 1))
            start = index + 1
        elif current > max_width:
            cut = safe_cut(text, start, max_width, protected)
            spans.append((start, cut))
            start = cut
            index = cut - 1
        index += 1
    if start < len(text):
        spans.append((start, len(text)))
    return merge_short_tail(text, spans, max_width)


def merge_short_tail(text: str, spans: list[tuple[int, int]], max_width: float) -> list[tuple[int, int]]:
    """只剩一两个字的碎行并回上一行（合并后不超宽时），避免字幕一闪而过。"""
    merged: list[tuple[int, int]] = []
    for span in spans:
        body = clean_line(text[span[0]:span[1]])
        previous_ends_sentence = bool(merged) and text[merged[-1][1] - 1] in SENTENCE_END
        if merged and not previous_ends_sentence and text_width(body) <= 2 and text_width(text[merged[-1][0]:span[1]]) <= max_width + 2:
            merged[-1] = (merged[-1][0], span[1])
        else:
            merged.append(span)
    return merged


def clean_line(line: str) -> str:
    stripped = line.strip()
    while stripped and stripped[-1] in STRIP_CHARS and stripped[-1] not in KEEP_TRAILING:
        stripped = stripped[:-1].rstrip()
    while stripped and stripped[0] in STRIP_CHARS:
        stripped = stripped[1:].lstrip()
    # 行内逗号、顿号改为空格：短视频字幕的常见写法，读起来更干净
    for mark in INLINE_TO_SPACE:
        stripped = stripped.replace(f"{mark} ", " ").replace(mark, " ")
    return stripped


def apply_replacements(line: str, replacements: list[tuple[str, str]]) -> str:
    """把朗读写法换回屏幕写法（如 二零二五年六月 → 2025 年 6 月）；只替换完整落在本行内的片段。"""
    for spoken, display in replacements:
        line = line.replace(spoken, display)
    return line


def build_captions(text: str, words: list[WordTiming], replacements: list[tuple[str, str]], max_width: float = 16,
                   breaks: list[str] | None = None) -> list[CaptionLine]:
    times = char_times(len(text), words)
    lines: list[CaptionLine] = []
    protected = protected_spans(text, [spoken for spoken, _ in replacements])
    for begin, end in split_lines(text, max_width, protected=protected, forced=break_positions(text, breaks or [])):
        timed = [t for t in times[begin:end] if t is not None]
        body = clean_line(text[begin:end])
        if not timed or not body:
            continue  # 纯标点或没有时间戳的片段不单独成行
        lines.append(CaptionLine(apply_replacements(body, replacements), timed[0][0], timed[-1][1]))
    return lines
