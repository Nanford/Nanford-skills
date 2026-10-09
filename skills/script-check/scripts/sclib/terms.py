"""
INPUT: config/platform-terms.json（平台敏感词工作清单）；版本目录的 speech.json、shots.json、可选 cover.props.json、publish.md；
       截图文字由调用方经 ocr.py 取得后传入
OUTPUT: load_terms()、collect_texts()、screenshot_paths()、public_publish_sections()、scan_texts()、terms_report()
POS: 发布前的平台敏感词闸门。覆盖口播、上屏文字、封面、发布文案（含置顶评论来源）和截图里的文字；
     词表是本项目按真实处理通知积累的工作清单，不代表平台官方名单，命中为零也不保证平台一定放行。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sclib.rules import Finding, _display_texts

DEFAULT_TERMS_PATH = Path(__file__).resolve().parents[2] / "config" / "platform-terms.json"
# 发布包里会公开给观众的章节（按标题前缀）：标题、说明、话题，以及准备放进置顶评论的来源
PUBLIC_SECTION_PREFIXES = ("标题", "说明", "话题", "来源")
CONTEXT_CHARS = 12


@dataclass(frozen=True)
class Term:
    text: str
    category: str
    label: str
    level: str
    suggestion: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class TextItem:
    where: str  # 如 speech.s03、shot_01.params、publish.md#标题、shot_01 截图 assets/original/a.png
    text: str


def _compile(term: str) -> re.Pattern[str]:
    if re.search(r"[^\x00-\x7f]", term):
        return re.compile(re.escape(term), re.IGNORECASE)
    # 纯英文词按整词匹配：前面不能紧贴字母（ChatGPT 不算 GPT），后面不能接小写字母（Clauded 不算 Claude）；
    # 后面允许大写字母、数字与符号，驼峰话题 #ClaudeCode、GPT-4o、CLAUDE.md 照常命中。只对词本身忽略大小写
    return re.compile(rf"(?<![A-Za-z])(?i:{re.escape(term)})(?![a-z])")


def load_terms(platform: str, path: Path = DEFAULT_TERMS_PATH) -> list[Term]:
    config = json.loads(path.read_text(encoding="utf-8"))
    terms: list[Term] = []
    for category in config["categories"]:
        level = category["levels"].get(platform, "off")
        if level == "off":
            continue
        terms += [Term(text, category["category"], category["label"], level, category["suggestion"], _compile(text)) for text in category["terms"]]
    return terms


def normalize(text: str) -> str:
    """去掉紧挨汉字等非 ASCII 字符的空白：Windows OCR 会在每个汉字之间插空格（「中 国 大 陆」），英文词之间的空格保留。"""
    return re.sub(r"\s+(?=[^\x00-\x7f])|(?<=[^\x00-\x7f])\s+", "", text)


def public_publish_sections(markdown: str) -> list[TextItem]:
    """publish.md 里对外公开的章节；文件表格、AI 声明说明和「发布前核对（不对外）」不检查。"""
    items: list[TextItem] = []
    for block in re.split(r"^## ", markdown, flags=re.MULTILINE)[1:]:
        heading, _, body = block.partition("\n")
        if heading.strip().startswith(PUBLIC_SECTION_PREFIXES) and "不对外" not in heading:
            items.append(TextItem(f"publish.md#{heading.strip()}", body))
    return items


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _string_values(item)]
    if isinstance(value, list):
        return [text for item in value for text in _string_values(item)]
    return []


def collect_texts(speech: dict[str, Any], shots: dict[str, Any], cover: dict[str, Any] | None, publish_md: str | None) -> list[TextItem]:
    items: list[TextItem] = []
    for segment in speech["segments"]:
        # 字幕来自 display_text，配音读的是 spoken_text，两者都会被平台识别
        spoken = segment.get("spoken_text", "")
        items.append(TextItem(f"speech.{segment['segment_id']}", f"{segment.get('display_text', '')}\n{spoken}"))
    for shot in shots["shots"]:
        texts = _display_texts(shot.get("params", {})) + _string_values([shot.get("screen_text"), shot.get("label_text")])
        items.append(TextItem(f"{shot['shot_id']}.params", "\n".join(texts)))
    if cover:
        items.append(TextItem("cover.props.json", "\n".join(_string_values(cover))))
    if publish_md:
        items += public_publish_sections(publish_md)
    return items


def screenshot_paths(shots: dict[str, Any]) -> list[tuple[str, str]]:
    """(镜头 ID, 相对项目目录的图片路径)：ScreenFocus 的 image 与截图对比 BeforeAfter 的 images[].image。"""
    pairs: list[tuple[str, str]] = []
    for shot in shots["shots"]:
        params = shot.get("params", {})
        images = [params.get("image")] + [item.get("image") for item in params.get("images", []) if isinstance(item, dict)]
        pairs += [(shot["shot_id"], image) for image in images if isinstance(image, str) and image]
    return pairs


def _context(text: str, start: int, end: int) -> str:
    return text[max(0, start - CONTEXT_CHARS): end + CONTEXT_CHARS].replace("\n", " ").strip()


def scan_texts(items: list[TextItem], terms: list[Term]) -> list[Finding]:
    findings: list[Finding] = []
    for item in items:
        text = normalize(item.text)
        for term in terms:
            match = term.pattern.search(text)
            if match:
                findings.append(Finding(term.level, f"terms.{term.category}", item.where,
                                        f"「{match.group(0)}」属于{term.label}（…{_context(text, match.start(), match.end())}…）；{term.suggestion}"))
    return findings


def terms_report(platform: str, findings: list[Finding], screenshots: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "platform": platform,
        "terms_config": "config/platform-terms.json",
        "errors": sum(1 for finding in findings if finding.level == "error"),
        "warnings": sum(1 for finding in findings if finding.level == "warning"),
        "screenshots": screenshots,
        "findings": [finding.as_dict() for finding in findings],
    }
