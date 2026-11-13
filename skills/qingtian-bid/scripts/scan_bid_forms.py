"""Scan the tender's 投标文件格式 chapter: its files, sections and parts, and how each file's 目录 differs from its body.

INPUT: TextIndex objects of the tender texts (tender_text); analysis/extraction-report.json for the CLI;
       a rule card dict from templates/rule-card.json.
OUTPUT: chapter_span() gives the chapter's line range; scan_forms() its outline; forms_diff() the 目录 vs 正文 differences;
        fill_bid_forms() writes draft rows into the card, kind empty and checked=false; the CLI prints the outline.
POS: stage-2 helper. scaffold_rule_card.py calls it to draft the card, scaffold_rule_fields.py uses the span to skip the
     bidder's own checkboxes, bid_forms_fields.py re-scans to catch a dropped section. It only reads. The chapter is found
     by title because its number is not fixed. Layouts come from Hefei tenders (only two real ones checked so far), so a
     person checks the outline against the original; kinds and field names are hints, never answers (R1, R3).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path

from rule_card_fields import TENDER_BASIS, UNSPECIFIED, compact, tender_outputs
from tender_text import REF_KEYWORD_CHARS, TextIndex, build_index, candidates, ref_at


FORM_FILES = ("商务", "技术", "报价")
FORMS_TITLE = re.compile(r"^(?:第[一二三四五六七八九十百\d]+章)?(?:投标|响应)文件(?:格式|组成及格式)$")
CHAPTER = re.compile(r"^第[一二三四五六七八九十百\d]+章[^，。；：、“”\"]{0,24}$")
COVER = re.compile(r"^(?:投标文件|响应文件)?[（(](商务|技术|报价)文件[）)]$")
TOC_TITLE = "目录"
SECTION = re.compile(r"^([一二三四五六七八九十]+)、(.+)$")
PART = re.compile(r"^[（(]([一二三四五六七八九十]+)[）)](.+)$")
SENTENCE_MARK = re.compile(r"[，。；：,;:？！]")
TOC_TAIL = re.compile(r"[\.．…·]{2,}\d*$")
MAX_TITLE_CHARS = 30  # 节名上限：长句是正文，如保函里的"五、本保函项下的权利不得转让"
TOC_REACH = 12  # 封面到"目录"之间最多隔几行
CHINESE_DIGITS = "一二三四五六七八九"

FIELD_LABEL = re.compile(r"([^\s：:（）()。，；、,;“”\"]{2,12})[：:]")
CELL_GAP = re.compile(r"\s{2,}")
LABEL_NUMBER = re.compile(r"^[\d\.．、]+")
LABEL_NOT_FIELD = re.compile(r"(?:承诺|如下|以下|说明)$")
ATTACHMENT_LINE = re.compile(r"扫描件|复印件|后附|^附[：:]")
BODY_TITLE = re.compile(r"施工组织设计|说明")
ATTACHMENT_TITLE = re.compile(r"其他材料|证明材料|奖项|荣誉")
CONDITIONAL_TITLE = re.compile(r"如有|如要求|如需")
MAX_FIELD_HINTS = 30
MAX_ATTACHMENT_HINTS = 8
MAX_ATTACHMENT_CHARS = 60
MAX_FALLBACK_HITS = 3

DIFF_BODY_ONLY = "按正文保留这一节；目录没列，要不要实际提供内容，由用户按评标办法决定"
DIFF_TOC_ONLY = "目录列了、正文没有格式：澄清窗口开着就在线提出，关了由用户决定"
DIFF_NUMBER = "节名相同、编号不同：按正文的编号"


@dataclass
class FormPart:
    title: str
    line: int
    end: int = 0


@dataclass
class FormSection:
    """number 是正文里的编号；封面没有编号。in_toc 为 None 表示没得比（封面，或这个文件没有目录）。"""

    number: str | None
    title: str
    line: int
    end: int = 0
    toc_number: str | None = None
    in_toc: bool | None = None
    parts: list[FormPart] = field(default_factory=list)
    last_part: int = 0


@dataclass
class FormFile:
    name: str | None  # 商务、技术、报价；格式没有分文件的是 None
    toc: list[tuple[str, str]]
    sections: list[FormSection]


@dataclass
class FormsScan:
    index: TextIndex
    files: list[FormFile]


def clean(line: str) -> str:
    """去掉空白和 Markdown 标题的井号。"""
    return compact(line).lstrip("#")


def chinese_number(text: str) -> int:
    """一 到 九十九；不是数字写法的返回 0。"""
    if "十" not in text:
        return CHINESE_DIGITS.find(text) + 1 if len(text) == 1 else 0
    tens, _, ones = text.partition("十")
    return (CHINESE_DIGITS.find(tens) + 1 if tens else 1) * 10 + (CHINESE_DIGITS.find(ones) + 1 if ones else 0)


def same_title(first: str, second: str) -> bool:
    return first == second or first in second or second in first


# ---------- 找这一章 ----------

def chapter_span(index: TextIndex) -> tuple[int, int] | None:
    """这一章的行范围（0 起，含头不含尾）。
    目录、页眉、评审表都可能出现同样的字，所以取最后一个商务封面之前最近的标题；评审表里单独成行的"投标文件格式"
    没有"第几章"，只有后面确实跟着封面才算。"""
    lines = index.content_lines()
    texts = {line: clean(index.lines[line]) for line in lines}
    heads = [line for line in lines if FORMS_TITLE.match(texts[line])]
    covers = [line for line in lines if COVER.match(texts[line])]
    business = [line for line in covers if COVER.match(texts[line]).group(1) == FORM_FILES[0]]
    cover = business[-1] if business else (covers[0] if covers else None)
    numbered = [line for line in heads if texts[line].startswith("第")]
    pool = numbered or (heads if cover is not None else [])
    before = [line for line in pool if cover is None or line < cover]
    if not before:
        return None
    start = before[-1]
    end = next((line for line in lines if line > start and CHAPTER.match(texts[line])
                and not FORMS_TITLE.match(texts[line])), len(index.lines))
    return start, end


# ---------- 读目录和正文 ----------

def heading(pattern: re.Pattern, text: str) -> tuple[str, str] | None:
    """节、小节标题是编号加一小段字。带句读的、太长的是正文。"""
    match = pattern.match(TOC_TAIL.sub("", text))
    if not match or len(match.group(2)) > MAX_TITLE_CHARS or SENTENCE_MARK.search(match.group(2)):
        return None
    return match.group(1), match.group(2)


def split_files(index: TextIndex, lines: list[int]) -> list[tuple[str | None, int | None, list[int]]]:
    """按封面分文件：(文件名, 封面行, 封面后面的行)。没有封面的算一个没分文件的整体。"""
    covers = [(at, match.group(1)) for at, line in enumerate(lines) if (match := COVER.match(clean(index.lines[line])))]
    if not covers:
        return [(None, None, lines)]
    stops = [at for at, _ in covers[1:]] + [len(lines)]
    return [(name, lines[at], lines[at + 1:stop]) for (at, name), stop in zip(covers, stops)]


def read_toc(index: TextIndex, lines: list[int]) -> tuple[list[tuple[str, str]], list[int]]:
    """目录项和目录后面的行。正文第一节的编号和目录第一项重复，遇到重复编号就是目录结束了。"""
    start = next((at for at, line in enumerate(lines[:TOC_REACH]) if clean(index.lines[line]) == TOC_TITLE), None)
    if start is None:
        return [], lines
    entries: list[tuple[str, str]] = []
    at = start + 1
    while at < len(lines):
        text = clean(index.lines[lines[at]])
        found = heading(SECTION, text)
        if found and found[0] in {number for number, _ in entries}:
            break
        if found:
            entries.append(found)
        elif not heading(PART, text):  # 目录里列到小节的，小节不比
            break
        at += 1
    return entries, lines[at:]


def add_part(section: FormSection, found: tuple[str, str] | None, line: int) -> None:
    """小节编号接着上一个走。"（六）项目经理简历""（六）项目技术负责人简历"这样编号重复、名字不同的也算。"""
    if not found:
        return
    number = chinese_number(found[0])
    repeated = section.parts and number == section.last_part and found[1] != section.parts[-1].title
    if number == section.last_part + 1 or repeated:
        section.parts.append(FormPart(found[1], line))
        section.last_part = number


def scan_sections(index: TextIndex, lines: list[int], toc: list[tuple[str, str]]) -> list[FormSection]:
    """编号要接着上一节走，否则是正文里的条款（保函的"一、开立人理解"）。目录里有的节名例外：招标文件的编号可能跳。"""
    toc_titles = {title for _, title in toc}
    sections: list[FormSection] = []
    expected = 1
    for line in lines:
        text = clean(index.lines[line])
        found = heading(SECTION, text)
        if found and (chinese_number(found[0]) == expected or found[1] in toc_titles):
            sections.append(FormSection(found[0], found[1], line))
            expected = chinese_number(found[0]) + 1
        elif sections:
            add_part(sections[-1], heading(PART, text), line)
    return sections


def alternative_parts(index: TextIndex, section: FormSection, lines: list[int]) -> list[FormPart]:
    """"法定代表人身份证明或授权委托书"是两张没编号的表，要提供的条件不同，分开列。"""
    pieces = section.title.split("或")
    found: list[FormPart] = []
    for piece in pieces if len(pieces) > 1 else []:
        line = next((line for line in lines if section.line < line < section.end
                     and clean(index.lines[line]) == piece), None)
        if line is None:
            return []
        found.append(FormPart(piece, line))
    return sorted(found, key=lambda part: part.line)


def finish_sections(index: TextIndex, sections: list[FormSection], lines: list[int], stop: int) -> None:
    """定下每节、每小节的行范围。没有小节的节算一个同名小节，下游只认小节。"""
    for section, following in zip(sections, [*sections[1:], None]):
        section.end = following.line if following else stop
        if not section.parts:
            section.parts = alternative_parts(index, section, lines) or [FormPart(section.title, section.line)]
        for part, after in zip(section.parts, [*section.parts[1:], None]):
            part.end = after.line if after else section.end


def mark_toc(form: FormFile) -> None:
    if not form.toc:
        return
    for section in form.sections:
        number = next((number for number, title in form.toc if same_title(title, section.title)), None)
        section.toc_number, section.in_toc = number, number is not None


def scan_file(index: TextIndex, name: str | None, cover: int | None, lines: list[int]) -> FormFile:
    toc, body = read_toc(index, lines)
    sections = scan_sections(index, body, toc)
    stop = (lines[-1] + 1) if lines else 0
    finish_sections(index, sections, lines, stop)
    form = FormFile(name, toc, sections)
    mark_toc(form)
    if cover is not None:
        title = f"{name}文件封面"
        end = sections[0].line if sections else stop
        form.sections.insert(0, FormSection(None, title, cover, end, parts=[FormPart(title, cover, end)]))
    return form


def scan_forms(indexes: list[TextIndex]) -> FormsScan | None:
    """取这一章最长的那份文本：答疑、补遗里偶尔也有同样的标题。一节都读不出来的算没找到。"""
    spans = [(index, span) for index in indexes if (span := chapter_span(index))]
    if not spans:
        return None
    index, (start, end) = max(spans, key=lambda item: item[1][1] - item[1][0])
    lines = [line for line in index.content_lines() if start < line < end]
    files = [scan_file(index, name, cover, body) for name, cover, body in split_files(index, lines)]
    if not any(section.number for form in files for section in form.sections):
        return None
    return FormsScan(index, files)


def scan_project(project_dir: Path) -> FormsScan | None:
    """按提取报告读招标文件文本再扫。读不到的文本跳过，校验和命令行共用。"""
    indexes = []
    for name, output in tender_outputs(project_dir).items():
        try:
            indexes.append(build_index(name, output.read_text(encoding="utf-8")))
        except OSError:
            continue
    return scan_forms(indexes)


# ---------- 目录和正文的差异 ----------

def forms_diff(scan: FormsScan) -> list[dict]:
    """差异都要用户决定（硬停）。有三种：正文多一节、目录多一节、节名相同编号不同。"""
    rows: list[dict] = []
    for form in scan.files:
        rows += section_gaps(form)
        rows += [gap_row(form.name, title, number, None, DIFF_TOC_ONLY) for number, title in form.toc
                 if not any(section.number and same_title(title, section.title) for section in form.sections)]
    return [{"id": f"SD{at:02d}", **row} for at, row in enumerate(rows, 1)]


def section_gaps(form: FormFile) -> list[dict]:
    rows: list[dict] = []
    for section in form.sections:
        if section.in_toc is False:
            rows.append(gap_row(form.name, section.title, None, section.number, DIFF_BODY_ONLY))
        elif section.in_toc and section.toc_number != section.number:
            rows.append(gap_row(form.name, section.title, section.toc_number, section.number, DIFF_NUMBER))
    return rows


def gap_row(file_name: str | None, title: str, toc_number: str | None, body_number: str | None, default: str) -> dict:
    return {"file": file_name, "title": title, "in_toc": toc_number is not None, "in_body": body_number is not None,
            "toc_number": toc_number, "body_number": body_number, "default": default, "decision": None}


# ---------- 给人看的提示 ----------

def field_hints(lines: list[str]) -> list[str]:
    """"姓名：性别："这样的标签，加表格里用两个以上空格隔开的格子。只是提示，提取文本丢了不少表格线。"""
    found: list[str] = []
    for raw in lines:
        labels = [LABEL_NUMBER.sub("", label) for label in FIELD_LABEL.findall(compact(raw))]
        cells = [cell.strip() for cell in CELL_GAP.split(raw) if cell.strip()] if CELL_GAP.search(raw) else []
        found += [label for label in labels if len(label) >= 2 and not LABEL_NOT_FIELD.search(label)]
        found += [cell for cell in cells if 2 <= len(cell) <= 12 and not SENTENCE_MARK.search(cell)]
    return list(dict.fromkeys(found))[:MAX_FIELD_HINTS]


def part_hints(index: TextIndex, part: FormPart) -> dict:
    """永远不提示"无需提供"：不提供要有招标文件的依据，由人写明。"""
    lines = index.lines[part.line + 1:part.end]
    fields = field_hints(lines)
    if BODY_TITLE.search(part.title):
        kind = "正文"
    elif ATTACHMENT_TITLE.search(part.title):
        kind = "附件"
    else:
        kind = "字段值" if fields else "正文"
    attachments = [compact(raw)[:MAX_ATTACHMENT_CHARS] for raw in lines if ATTACHMENT_LINE.search(compact(raw))]
    return {"kind": kind, "fields": fields, "attachments": attachments[:MAX_ATTACHMENT_HINTS],
            "conditional": bool(CONDITIONAL_TITLE.search(part.title))}


# ---------- 写进规则卡 ----------

def line_ref(index: TextIndex, line: int) -> dict:
    """关键词取这一行自己的字，生成的 ref 一定查得回来。"""
    return ref_at(index, bisect_left(index.offsets, line), min(len(compact(index.lines[line])), REF_KEYWORD_CHARS))


def part_row(index: TextIndex, row_id: str, at: int, part: FormPart) -> dict:
    return {"id": f"{row_id}-{at}", "title": part.title, "kind": None, "fields": [], "attachments": [], "protected": [],
            "not_required_basis": None, "ref": line_ref(index, part.line), "hints": part_hints(index, part)}


def form_rows(scan: FormsScan) -> list[dict]:
    rows: list[dict] = []
    for form in scan.files:
        for section in form.sections:
            row_id = f"S{len(rows) + 1:02d}"
            rows.append({"id": row_id, "title": section.title, "number": section.number,
                         "toc_number": section.toc_number, "in_toc": section.in_toc, "file": form.name,
                         "ref": line_ref(scan.index, section.line),
                         "parts": [part_row(scan.index, row_id, at, part) for at, part in enumerate(section.parts, 1)]})
    return rows


def fill_bid_forms(card: dict, indexes: list[TextIndex]) -> dict:
    """全部待核对。没有差异时依据写"招标文件未规定"：没有内容的字段都这么写，校验才分得清是没差异还是没填。"""
    scan = scan_forms(indexes)
    forms, diff = card["bid_forms"], card["bid_forms_diff"]
    if scan is None:
        forms.update(value=[], checked=False, candidates=candidates(indexes, r"投标文件格式")[:MAX_FALLBACK_HITS])
        diff.update(value=[], basis=UNSPECIFIED, checked=False)
        return {"投标文件格式": "没找到这一章，硬停问用户"}
    rows, gaps = form_rows(scan), forms_diff(scan)
    forms.update(value=rows, checked=False)
    diff.update(value=gaps, basis=TENDER_BASIS if gaps else UNSPECIFIED, checked=False)
    return {"投标文件格式": {"节数": len(rows), "小节数": sum(len(row["parts"]) for row in rows),
                       "目录和正文的差异": [row["title"] for row in gaps]}}


# ---------- 命令行 ----------

def outline(scan: FormsScan) -> dict:
    return {"source": scan.index.name,
            "files": [{"file": form.name, "toc": [f"{number}、{title}" for number, title in form.toc],
                       "sections": [{"number": section.number, "title": section.title,
                                     "parts": [part.title for part in section.parts]} for section in form.sections]}
                      for form in scan.files],
            "diff": forms_diff(scan)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按标题找招标文件的投标文件格式一章，列出节、小节和目录差异（只读）。")
    parser.add_argument("project", type=Path, help="项目目录。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scan = scan_project(args.project)
    if scan is None:
        print("没找到投标文件格式这一章。硬停：告诉用户，查招标文件是否完整。", file=sys.stderr)
        return 2
    print(json.dumps(outline(scan), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
