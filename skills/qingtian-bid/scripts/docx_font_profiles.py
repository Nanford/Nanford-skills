"""Format presets, custom fields and the normalized DOCX format for qingtian-bid.

迁移来源见 CHANGELOG《脚本来源》，按设计稿 v1 第十节改造：
单一字体代码改为整套格式预设；正文与一至三级标题分设字体和字号（四、五级跟三级），
西文字体可选；行距支持倍数、固定值、最小值；每个字段单独记录出处。

INPUT: templates/format-presets.json; optional project-state.json; user field assignments
       (磅值或中文字号名，如"三号").
OUTPUT: normalized, per-field-sourced document format; preset listing and filtering;
        field parsing and display helpers for the format confirmation card.
POS: single source of truth for qingtian-bid DOCX format, shared by the format sample,
     the builder and the validator. Invalid values raise ValueError, never fall back. Inside a
     project only the confirmed project-state.json document_format counts (see format_state).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parents[1] / "templates" / "format-presets.json"

FONT_FIELDS = ("body_font", "heading1_font", "heading2_font", "heading3_font")
SIZE_FIELDS = (
    "body_size_pt", "heading1_size_pt", "heading2_size_pt", "heading3_size_pt",
    "cover_title_size_pt", "cover_info_size_pt", "header_footer_size_pt",
)
SPACING_FIELDS = ("heading_space_before_pt", "heading_space_after_pt")
PAGE_FIELDS = ("page_width_cm", "page_height_cm")
MARGIN_FIELDS = ("margin_top_cm", "margin_bottom_cm", "margin_left_cm", "margin_right_cm")
BOOL_FIELDS = ("heading_bold", "heading_page_breaks", "require_toc", "require_page_numbers", "blind_mode")
FORMAT_FIELDS = (
    *FONT_FIELDS, "latin_font", *SIZE_FIELDS, "line_spacing_rule", "line_spacing",
    *SPACING_FIELDS, "first_line_indent_chars", *PAGE_FIELDS, *MARGIN_FIELDS, *BOOL_FIELDS,
)
META_FIELDS = ("preset", "sources")

LINE_RULES = {"multiple": "倍数", "exact": "固定值", "at_least": "最小值"}
LINE_RULE_ALIASES = {
    "multiple": "multiple", "倍数": "multiple", "多倍": "multiple",
    "exact": "exact", "固定值": "exact", "固定": "exact",
    "at_least": "at_least", "atleast": "at_least", "最小值": "at_least", "最小": "at_least",
}
CHINESE_SIZES = {
    "初号": 42, "小初": 36, "一号": 26, "小一": 24, "二号": 22, "小二": 18, "三号": 16,
    "小三": 15, "四号": 14, "小四": 12, "五号": 10.5, "小五": 9, "六号": 7.5, "小六": 6.5,
}
SAME_AS_CHINESE = ("同中文", "same", "none", "null", "")
TRUE_WORDS = {"true", "yes", "1", "是", "开", "开启"}
FALSE_WORDS = {"false", "no", "0", "否", "关", "关闭"}

FIELD_LABELS = {
    "body_font": "正文字体",
    "heading1_font": "一级标题字体",
    "heading2_font": "二级标题字体",
    "heading3_font": "三级标题字体（四、五级相同）",
    "latin_font": "西文和数字字体",
    "body_size_pt": "正文字号（表格文字相同）",
    "heading1_size_pt": "一级标题字号",
    "heading2_size_pt": "二级标题字号",
    "heading3_size_pt": "三级标题字号（四、五级相同）",
    "cover_title_size_pt": "封面标题字号",
    "cover_info_size_pt": "封面信息字号",
    "header_footer_size_pt": "页眉页脚字号",
    "line_spacing_rule": "行距方式",
    "line_spacing": "行距值",
    "heading_space_before_pt": "标题段前",
    "heading_space_after_pt": "标题段后",
    "first_line_indent_chars": "正文首行缩进",
    "page_width_cm": "纸张宽度",
    "page_height_cm": "纸张高度",
    "margin_top_cm": "上页边距",
    "margin_bottom_cm": "下页边距",
    "margin_left_cm": "左页边距",
    "margin_right_cm": "右页边距",
    "heading_bold": "标题加粗",
    "heading_page_breaks": "一、二级标题另起一页",
    "require_toc": "生成目录",
    "require_page_numbers": "页脚页码",
    "blind_mode": "暗标模式（不设页眉页脚页码）",
}
LABEL_TO_FIELD = {label.split("（")[0]: key for key, label in FIELD_LABELS.items()}


@lru_cache(maxsize=4)
def _read_catalog(path_text: str) -> dict:
    path = Path(path_text)
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"格式预设库无法读取: {path} ({exc})") from exc
    presets = catalog.get("presets") if isinstance(catalog, dict) else None
    default = catalog.get("default_preset") if isinstance(catalog, dict) else None
    if not isinstance(presets, dict) or default not in presets:
        raise ValueError(f"格式预设库缺少 presets 或 default_preset: {path}")
    missing = [key for key in FORMAT_FIELDS if key not in presets[default].get("fields", {})]
    if missing:
        raise ValueError(f"默认预设 {default} 缺少字段: {', '.join(missing)}")
    return catalog


def load_catalog(path: Path | None = None) -> dict:
    """Return a private copy so callers cannot mutate the cached preset library."""
    return copy.deepcopy(_read_catalog(str((path or CATALOG_PATH).resolve())))


def default_preset_code(catalog: dict | None = None) -> str:
    return (catalog or load_catalog())["default_preset"]


def allowed_fonts(catalog: dict) -> set[str]:
    fonts = catalog.get("fonts", {})
    return set(fonts.get("system", [])) | set(fonts.get("needs_install", []))


def _preset_fields_and_sources(code: str, catalog: dict) -> tuple[dict, dict]:
    """Raw preset values: listed fields carry the preset source, the rest inherit the default preset."""
    presets = catalog["presets"]
    if code not in presets:
        raise ValueError(f"未知格式预设: {code}（可选: {', '.join(presets)}）")
    default_code = catalog["default_preset"]
    default = presets[default_code]
    preset = presets[code]
    unknown = set(preset.get("fields", {})) - set(FORMAT_FIELDS)
    if unknown:
        raise ValueError(f"预设 {code} 含未知字段: {', '.join(sorted(unknown))}")
    fields = {**default["fields"], **preset.get("fields", {})}
    field_sources = preset.get("field_sources", {})
    sources = {}
    for key in FORMAT_FIELDS:
        if key in field_sources:
            sources[key] = field_sources[key]
        elif code == default_code or key in preset.get("fields", {}):
            sources[key] = f"{code} {preset['name']}：{preset['source']}"
        else:
            sources[key] = f"沿用 {default_code}：{default['source']}"
    return fields, sources


def _finite_number(key: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{FIELD_LABELS[key]}（{key}）必须是有限数字")
    return value


def _check_font_fields(result: dict, catalog: dict) -> None:
    fonts = allowed_fonts(catalog)
    for key in FONT_FIELDS:
        if result[key] not in fonts:
            raise ValueError(f"{FIELD_LABELS[key]}不支持“{result[key]}”（可选: {'、'.join(sorted(fonts))}）")
    latin = catalog.get("fonts", {}).get("latin", [])
    if result["latin_font"] is not None and result["latin_font"] not in latin:
        raise ValueError(f"西文字体不支持“{result['latin_font']}”（可选: 同中文、{'、'.join(latin)}）")


def _check_numeric_fields(result: dict) -> None:
    for key in SIZE_FIELDS:
        number = _finite_number(key, result[key])
        if number <= 0 or number > 100 or number * 2 != round(number * 2):
            raise ValueError(f"{FIELD_LABELS[key]}须为不大于100的半磅倍数，当前为 {number}")
    for key in (*SPACING_FIELDS, "first_line_indent_chars", *MARGIN_FIELDS):
        if _finite_number(key, result[key]) < 0:
            raise ValueError(f"{FIELD_LABELS[key]}不能为负数")
    for key in PAGE_FIELDS:
        if _finite_number(key, result[key]) <= 0:
            raise ValueError(f"{FIELD_LABELS[key]}必须大于0")
    for axis, margins in (("width", ("left", "right")), ("height", ("top", "bottom"))):
        if sum(result[f"margin_{side}_cm"] for side in margins) >= result[f"page_{axis}_cm"] - 1.5:
            raise ValueError("页边距未留下足够的可打印区域")


def _check_line_spacing(result: dict) -> None:
    rule = result["line_spacing_rule"]
    if rule not in LINE_RULES:
        raise ValueError(f"行距方式不支持“{rule}”（可选: 倍数、固定值、最小值）")
    value = _finite_number("line_spacing", result["line_spacing"])
    if rule == "multiple":
        if not 0 < value <= 5:
            raise ValueError(f"倍数行距须在 0～5 倍之间，当前为 {value}")
        return
    # Word 以 1/20 磅存储行距，非整数缇会被悄悄舍入，所以直接拒绝。
    if not 1 <= value <= 200 or abs(value * 20 - round(value * 20)) > 1e-6:
        raise ValueError(f"{LINE_RULES[rule]}行距须为 1～200 磅且是 0.05 磅的整数倍，当前为 {value}")
    if rule == "exact":
        # 固定行距小于字号会切掉字形上下沿，任何用到该行距的字号都不得超过它。
        for key in SIZE_FIELDS:
            if result[key] > value:
                raise ValueError(
                    f"固定行距 {value} 磅小于{FIELD_LABELS[key]} {result[key]} 磅，文字会被裁切"
                )


def _check_sources(sources) -> dict:
    if not isinstance(sources, dict):
        raise ValueError("sources 必须是对象")
    unknown = set(sources) - set(FORMAT_FIELDS)
    if unknown:
        raise ValueError(f"sources 含未知字段: {', '.join(sorted(unknown))}")
    for key, text in sources.items():
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{FIELD_LABELS[key]}缺少出处")
    return sources


def normalize_document_format(value: dict | None = None, catalog: dict | None = None) -> dict:
    """Merge onto the named preset and reject misspelled or invalid rules instead of guessing."""
    if value is not None and not isinstance(value, dict):
        raise ValueError("document_format 必须是对象")
    value = value or {}
    unknown = set(value) - set(FORMAT_FIELDS) - set(META_FIELDS)
    if unknown:
        raise ValueError(f"未知格式字段: {', '.join(sorted(unknown))}")
    catalog = catalog or load_catalog()
    code = value.get("preset", catalog["default_preset"])
    fields, sources = _preset_fields_and_sources(code, catalog)
    result = {**fields, **{key: value[key] for key in FORMAT_FIELDS if key in value}}
    sources.update(_check_sources(value.get("sources", {})))
    _check_font_fields(result, catalog)
    _check_numeric_fields(result)
    _check_line_spacing(result)
    for key in BOOL_FIELDS:
        if not isinstance(result[key], bool):
            raise ValueError(f"{FIELD_LABELS[key]}（{key}）必须是布尔值")
    if result["blind_mode"] and result["require_page_numbers"]:
        raise ValueError("暗标模式不设页码：blind_mode 为是时 require_page_numbers 必须为否")
    ordered = {key: result[key] for key in FORMAT_FIELDS}
    ordered["preset"] = code
    ordered["sources"] = {key: sources[key] for key in FORMAT_FIELDS}
    return ordered


def preset_format(code: str | None = None, catalog: dict | None = None) -> dict:
    catalog = catalog or load_catalog()
    return normalize_document_format({"preset": code or catalog["default_preset"]}, catalog)


def apply_format_settings(base: dict, settings: dict, source: str, catalog: dict | None = None) -> dict:
    """Overlay field values and record the same source for each changed field."""
    if not source.strip():
        raise ValueError("自定义字段必须写明出处")
    merged = {**base, **settings, "sources": {**base.get("sources", {}), **{key: source for key in settings}}}
    return normalize_document_format(merged, catalog)


def resolve_field_name(name: str) -> str:
    key = name.strip()
    key = LABEL_TO_FIELD.get(key, key)
    if key not in FORMAT_FIELDS:
        raise ValueError(f"未知格式字段: {name}（可用字段见 FIELD_LABELS）")
    return key


def _parse_number(raw: str, units: tuple[str, ...]) -> float:
    text = raw.strip().lower().replace(" ", "")
    for unit in units:
        if text.endswith(unit):
            text = text[: -len(unit)]
            break
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        raise ValueError(f"无法识别的数值: {raw}")
    number = float(text)
    return int(number) if number.is_integer() else number


def parse_field_value(key: str, raw: str) -> str | float | bool | None:
    """Parse one user-typed value; Chinese size names convert to points (三号 → 16)."""
    key = resolve_field_name(key)
    text = raw.strip()
    if key in FONT_FIELDS:
        return text
    if key == "latin_font":
        return None if text.lower() in SAME_AS_CHINESE else text
    if key in BOOL_FIELDS:
        lowered = text.lower()
        if lowered in TRUE_WORDS:
            return True
        if lowered in FALSE_WORDS:
            return False
        raise ValueError(f"{FIELD_LABELS[key]}只接受 是/否（当前: {raw}）")
    if key == "line_spacing_rule":
        rule = LINE_RULE_ALIASES.get(text.lower())
        if rule is None:
            raise ValueError(f"行距方式只接受 倍数、固定值、最小值（当前: {raw}）")
        return rule
    if key in SIZE_FIELDS:
        if text in CHINESE_SIZES:
            return CHINESE_SIZES[text]
        try:
            return _parse_number(text, ("磅", "pt"))
        except ValueError:
            raise ValueError(f"{FIELD_LABELS[key]}写磅值或中文字号名（{'、'.join(CHINESE_SIZES)}），当前: {raw}") from None
    if key == "line_spacing":
        return _parse_number(text, ("磅", "pt", "倍"))
    if key in SPACING_FIELDS:
        return _parse_number(text, ("磅", "pt"))
    if key == "first_line_indent_chars":
        return _parse_number(text, ("字符", "字"))
    return _parse_number(text, ("厘米", "cm"))


def parse_assignment(text: str) -> tuple[str, str | float | bool | None]:
    if "=" not in text:
        raise ValueError(f"字段设置须写成 字段=值（当前: {text}）")
    name, raw = text.split("=", 1)
    key = resolve_field_name(name)
    return key, parse_field_value(key, raw)


def filter_presets(criteria: dict | None = None, catalog: dict | None = None) -> list[str]:
    """Return preset codes whose normalized values equal every criterion."""
    catalog = catalog or load_catalog()
    matches = []
    for code in catalog["presets"]:
        record = preset_format(code, catalog)
        if all(record[key] == value for key, value in (criteria or {}).items()):
            matches.append(code)
    return matches


def size_name(points: float) -> str:
    names = [name for name, value in CHINESE_SIZES.items() if value == points]
    return f"{points:g} 磅（{names[0]}）" if names else f"{points:g} 磅"


def describe_value(key: str, record: dict) -> str:
    value = record[key]
    if key in BOOL_FIELDS:
        return "是" if value else "否"
    if key == "latin_font":
        return value or "同中文"
    if key in SIZE_FIELDS:
        return size_name(value)
    if key == "line_spacing_rule":
        return LINE_RULES[value]
    if key == "line_spacing":
        return f"{value:g} 倍" if record["line_spacing_rule"] == "multiple" else f"{value:g} 磅"
    if key in SPACING_FIELDS:
        return f"{value:g} 磅"
    if key == "first_line_indent_chars":
        return f"{value:g} 字符"
    if key in (*PAGE_FIELDS, *MARGIN_FIELDS):
        return f"{value:g} 厘米"
    return str(value)


def format_card_rows(record: dict) -> list[tuple[str, str, str]]:
    return [(FIELD_LABELS[key], describe_value(key, record), record["sources"][key]) for key in FORMAT_FIELDS]


def fonts_needing_install(record: dict, catalog: dict | None = None) -> list[str]:
    """W8：评审端未安装的字体会被替换，版式和页数随之变化。"""
    needs = set((catalog or load_catalog()).get("fonts", {}).get("needs_install", []))
    return sorted({record[key] for key in FONT_FIELDS} & needs)


def heading_tier(level: int) -> int:
    return min(max(level, 1), 3)


def heading_font(record: dict, level: int) -> str:
    return record[f"heading{heading_tier(level)}_font"]


def heading_size(record: dict, level: int) -> float:
    return record[f"heading{heading_tier(level)}_size_pt"]


def latin_font_for(record: dict, east_asian_font: str) -> str:
    return record["latin_font"] or east_asian_font


def project_document_format(artifact_path: Path) -> dict | None:
    """Find project state even for nested output folders; never use a build report as authority.

    格式锁：项目里只认用户确认过的 document_format。尚未确认或有变更待确认时直接报错，
    不回退到默认预设，否则未确认的格式会被悄悄用来出稿和校验。
    """
    for parent in artifact_path.expanduser().resolve().parents:
        state_path = parent / "project-state.json"
        if not state_path.exists():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"项目状态无法读取: {state_path} ({exc})") from exc
        if not isinstance(state, dict):
            raise ValueError(f"项目状态格式错误: {state_path}")
        review = state.get("format_review")
        if review:
            raise ValueError(
                f"项目格式有变更待确认（{review.get('kind', '未知')}），用户确认样张前不能出稿或校验: {state_path}"
            )
        if state.get("document_format") is None:
            raise ValueError(f"项目格式尚未确认：先出格式样张，用户确认后再出稿: {state_path}")
        try:
            return normalize_document_format(state["document_format"])
        except ValueError as exc:
            raise ValueError(f"项目格式无法读取: {state_path} ({exc})") from exc
    return None


def resolve_document_format(artifact_path: Path, explicit: dict | None = None) -> dict:
    """Project state wins; an explicit format is only accepted when it agrees or no project exists."""
    project_format = project_document_format(artifact_path)
    if explicit is None:
        return project_format or preset_format()
    selected = normalize_document_format(explicit)
    if project_format is not None and selected != project_format:
        raise ValueError("传入的格式与项目格式不一致，请先更新 project-state.json")
    return selected


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
