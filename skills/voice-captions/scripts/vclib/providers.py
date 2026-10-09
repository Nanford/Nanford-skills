"""
INPUT: 服务商原始字幕 JSON（当前支持 MiniMax 同步合成 subtitle_type=word 的返回结构）
OUTPUT: parse_minimax_words() 转成统一的 WordTiming 列表
POS: 服务商适配层。新增豆包、Azure 或转写对齐工具时，在这里各加一个解析函数，输出同样的 WordTiming。
"""

from __future__ import annotations

from typing import Any

from .captions import WordTiming


class SubtitleFormatError(ValueError):
    pass


def parse_minimax_words(raw: Any, text: str) -> list[WordTiming]:
    """
    MiniMax 返回按句的数组；每句的 timestamped_words 带 word_begin / word_end（在原始请求文本中的字符位置）
    与 time_begin / time_end（毫秒，相对本段音频起点）。结构于 2026-09-29 首次真实调用时核实。
    位置对应的是提交的朗读文本，所以要求传入的 text 与合成时完全一致。
    """
    if not isinstance(raw, list):
        raise SubtitleFormatError("MiniMax 字幕应为数组")
    words: list[WordTiming] = []
    for sentence in raw:
        for item in sentence.get("timestamped_words") or []:
            begin, end = int(item["word_begin"]), int(item["word_end"])
            if begin < 0 or end > len(text) or begin >= end:
                raise SubtitleFormatError(f"字幕位置越界：{item.get('word')} [{begin},{end})，文本长度 {len(text)}")
            if text[begin:end] != item["word"]:
                raise SubtitleFormatError(f"字幕与定稿不一致：位置 {begin} 期望「{text[begin:end]}」，返回「{item['word']}」")
            words.append(WordTiming(begin, end, float(item["time_begin"]), float(item["time_end"])))
    if not words:
        raise SubtitleFormatError("字幕中没有逐字时间戳（确认合成时 subtitles=word）")
    return words
