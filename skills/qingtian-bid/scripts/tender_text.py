"""Indexed view of one extracted tender text: raw lines, pages, a flattened search text and row-level refs.

INPUT: extracted text from analysis/extracted-text/ (stage 1), with page marks "--- 第 N 页 ---" when the source
       had pages.
OUTPUT: TextIndex and build_index(); find_all() and candidates() for searching; ref_at() and ref_hit() build the
        {file, page, line, keyword} locators that rule_card_fields.py checks back against the same text.
POS: shared text layer of the stage-2 scaffolds (scaffold_rule_card, scaffold_rule_fields, scaffold_facts) and of the
     ref check. PDF tables break lines mid-sentence and repeat page headers, so searching runs on a flattened text with
     page headers and page numbers removed and maps hits back to source lines. Only digit lines at a page's top or
     bottom count as page numbers: WPS-exported 答疑 PDFs put body digits ("第 134 页", "0 个") on lines of their own,
     and those must stay.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


PAGE_MARK = re.compile(r"^---\s*第\s*(\d+)\s*页\s*---$")
# 单独成行的数字不一定是页码：WPS 导出的答疑 PDF 把"招标文件第 134 页""数量：0 个"里的数字排成单独一行
# （2026-10-31 真实合肥项目的答疑），所以只认页首、页尾的数字行（见 page_number_lines）
DIGIT_LINE = re.compile(r"^\d{1,4}$")
PAGE_NUMBER_REACH = 3  # 等于本页页码的数字行，只在页首、页尾这么多个非空行里才算页码
EXCERPT_CHARS = 160
MAX_CANDIDATES = 12
TOC_LEADER = re.compile(r"[\.．…·]{3,}")
# ref 回查的范围：写的那一行起连续 3 行，PDF 表格里一句话常被折成几行
REF_WINDOW = 3
REF_KEYWORD_CHARS = 16


@dataclass
class TextIndex:
    """一个提取文本：原始行、每行页码，以及去掉页眉和空白后的连续文本（offsets 记每个字所在行）。"""

    name: str
    lines: list[str]
    pages: list[int]
    flat: str = ""
    offsets: list[int] = field(default_factory=list)

    def source(self, line_index: int) -> str:
        page = self.pages[line_index]
        where = f"第{page}页（提取文本第{line_index + 1}行）" if page else f"提取文本第{line_index + 1}行"
        return f"{self.name} {where}"

    def hit(self, start: int, end: int | None = None) -> dict:
        stop = end if end is not None else start + EXCERPT_CHARS
        return {"text": self.flat[start:stop], "source": self.source(self.offsets[start])}

    def content_lines(self) -> list[int]:
        """进了连续文本的行号（0 起）：空行、页眉页脚和页码都不在内。"""
        return sorted(set(self.offsets))


def running_headers(lines: list[str], pages: list[int]) -> set[str]:
    """在三成以上页面重复出现的行视为页眉页脚（如示范文本名称）。"""
    page_count = len(set(pages))
    if page_count < 3:
        return set()
    seen: dict[str, set[int]] = {}
    for line, page in zip(lines, pages):
        text = line.strip()
        if text:
            seen.setdefault(text, set()).add(page)
    return {text for text, on_pages in seen.items() if len(on_pages) >= max(3, page_count * 0.3)}


def page_number_lines(lines: list[str], pages: list[int], headers: set[str]) -> set[int]:
    """单独成行的数字里哪些是页码：本页第一个或最后一个非空行（页眉页脚行不算在内），或在页首、页尾
    PAGE_NUMBER_REACH 个非空行内且等于本页页码。没有分页标记的文本（docx、xlsx）不认页码，数字行全留着。"""
    by_page: dict[int, list[int]] = {}
    for line_index, (line, page) in enumerate(zip(lines, pages)):
        text = line.strip()
        if page and text and not PAGE_MARK.match(text) and text not in headers:
            by_page.setdefault(page, []).append(line_index)
    found = set()
    for page, members in by_page.items():
        last = len(members) - 1
        for rank, line_index in enumerate(members):
            text = lines[line_index].strip()
            if not DIGIT_LINE.match(text):
                continue
            near_edge = rank < PAGE_NUMBER_REACH or rank > last - PAGE_NUMBER_REACH
            if rank in (0, last) or (near_edge and int(text) == page):
                found.add(line_index)
    return found


def build_index(name: str, text: str) -> TextIndex:
    lines = text.splitlines()
    pages, page = [], 0
    for line in lines:
        match = PAGE_MARK.match(line.strip())
        page = int(match.group(1)) if match else page
        pages.append(page)
    index = TextIndex(name, lines, pages)
    headers = running_headers(lines, pages)
    page_numbers = page_number_lines(lines, pages, headers)
    chars: list[str] = []
    for line_index, line in enumerate(lines):
        text = line.strip()
        if not text or PAGE_MARK.match(text) or text in headers or line_index in page_numbers:
            continue
        compact = re.sub(r"\s+", "", text)
        chars.append(compact)
        index.offsets.extend([line_index] * len(compact))
    index.flat = "".join(chars)
    return index


def find_all(indexes: list[TextIndex], pattern: str, limit: int = MAX_CANDIDATES) -> list[tuple[TextIndex, re.Match]]:
    hits = []
    for index in indexes:
        for match in re.finditer(pattern, index.flat):
            hits.append((index, match))
            if len(hits) >= limit:
                return hits
    return hits


def candidates(indexes: list[TextIndex], pattern: str, before: int = 0) -> list[dict]:
    return [index.hit(max(match.start() - before, 0)) for index, match in find_all(indexes, pattern)]


def ref_at(index: TextIndex, start: int, chars: int = REF_KEYWORD_CHARS) -> dict:
    """连续文本第 start 个字的原文定位。关键词从这个字取起，不超出回查范围（所在行起 REF_WINDOW 行）。"""
    line_index = index.offsets[start]
    end = start
    while end < len(index.flat) and end - start < chars and index.offsets[end] < line_index + REF_WINDOW:
        end += 1
    return {"file": index.name, "page": index.pages[line_index] or None, "line": line_index + 1,
            "keyword": index.flat[start:end]}


def ref_hit(index: TextIndex, start: int, end: int | None = None) -> dict:
    """候选片段加一份现成的 ref，核实后可以直接抄进新字段的行里。"""
    return {**index.hit(start, end), "ref": ref_at(index, start)}
