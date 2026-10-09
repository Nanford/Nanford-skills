"""
INPUT: speech.json（语段）、shots.json（镜头与画面参数）、claims.json / sources.json（事实与来源）、brief.json（开头类型、目标时长）、
       可选 cover.props.json；配音后另读 captions.json
OUTPUT: Finding、text_units()、estimate_seconds()、lint_variant()（配音前检查）、hook_gate()（配音后按真实字幕时间检查开头）
POS: 文稿阶段的质量闸门。在花钱配音、花时间渲染之前拦下开头拖沓、画面文字过长、数字无出处、语义色写错或过多等问题。
     版面宽度与 remotion-render 的 src/theme.ts 同一套数值；改动任一侧时两处同步。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .tones import check_tones, plain_display, strip_tone_marks

# 开头常见的铺垫话：说了等于没说，占掉最值钱的第一秒
FILLER_PHRASES = ("最怕的一种情况", "今天聊聊", "今天我们来", "今天给大家", "大家好", "你知道吗", "很多人不知道", "我来给大家", "话不多说")
HOOK_FIRST_SENTENCE_MAX_S = 4.0
FIRST_NUMBER_MAX_S = 5.0
VERIFIED_STATUSES = {"verified_source", "verified_test"}
# 开头镜头：结论大字、证据数字，或真实成品截图（ScreenFocus）、真实录屏片段（ScreenClip）
VISUAL_HOOK_SCENES = {"ResultHook", "EvidenceCard", "ScreenFocus", "ScreenClip"}

# 与 theme.ts 一致：内容区宽 828px；居中大字的文字列宽 720px（以画面中线为轴左右各让 180px）；字号适配留 4% 余量
CONTENT_WIDTH = 828
TEXT_COLUMN_WIDTH = 720
FIT_MARGIN = 0.96
STEP_TEXT_WIDTH = CONTENT_WIDTH - 168
NOTE_TEXT_WIDTH = CONTENT_WIDTH - 36


@dataclass(frozen=True)
class Finding:
    level: str  # error：必须改；warning：建议改
    rule: str
    where: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def text_units(text: str) -> float:
    """一行文字的字宽（1 = 一个汉字）。与 theme.ts 的 textUnits 同一算法：空格 0.25，间隔号与全角字符 1，其余 0.6；强调标记 {} 与语义色名不计宽。"""
    units = 0.0
    for char in strip_tone_marks(text):
        if char in "{}":
            continue
        if char == " ":
            units += 0.25
        elif char == "·" or ord(char) >= 0x2E80:
            units += 1
        else:
            units += 0.6
    return units


def fit_size(lines: list[str], max_size: float, width: float = CONTENT_WIDTH) -> int:
    widest = max([1.0, *(text_units(line) for line in lines)])
    return int(min(max_size, (width * FIT_MARGIN) // widest))


def estimate_seconds(text: str) -> float:
    """
    配音前的时长预估，只用于提前警告，真实时长以配音后的字幕时间为准（hook_gate）。
    系数用 2026-09-29 温润男声实测校准：「OpenAI 正在招 23 个 FDE 相关岗位。」预估 3.3 秒，实测 3.2 秒。
    """
    cjk = len(re.findall(r"[一-鿿]", text))
    words = len(re.findall(r"[A-Za-z]+", text))
    numbers = len(re.findall(r"\d+(?:\.\d+)?", text))
    short_pauses = len(re.findall(r"[，、：；,]", text))
    long_pauses = len(re.findall(r"[。？！?!]", text))
    return cjk / 4.3 + words * 0.4 + numbers * 0.35 + short_pauses * 0.15 + long_pauses * 0.3


def first_sentence(text: str) -> str:
    match = re.search(r"[。？！?!]", text)
    return text[: match.end()] if match else text


def _hook_findings(text: str, where: str) -> list[Finding]:
    findings = [Finding("error", "hook.filler", where, f"开头出现铺垫话「{phrase}」，第一句直接给痛点、数字或结果") for phrase in FILLER_PHRASES if phrase in text]
    seconds = estimate_seconds(first_sentence(text))
    if seconds > HOOK_FIRST_SENTENCE_MAX_S:
        findings.append(Finding("warning", "hook.first_sentence_long", where, f"第一句预估 {seconds:.1f} 秒，超过 {HOOK_FIRST_SENTENCE_MAX_S} 秒；拆句或删铺垫"))
    return findings


def _first_number_seconds(segments: list[dict[str, Any]]) -> float | None:
    elapsed = 0.0
    for segment in segments:
        text = segment["display_text"]
        match = re.search(r"\d", text)
        if match:
            return elapsed + estimate_seconds(text[: match.start()])
        elapsed += estimate_seconds(text)
    return None


def check_hook(speech: dict[str, Any], shots: dict[str, Any], brief: dict[str, Any], claims: dict[str, dict[str, Any]]) -> list[Finding]:
    segments = speech["segments"]
    first = segments[0]
    findings = _hook_findings(first["display_text"], first["segment_id"])
    first_number = _first_number_seconds(segments)
    if first_number is not None and first_number > FIRST_NUMBER_MAX_S:
        findings.append(Finding("warning", "hook.number_late", first["segment_id"], f"第一个数字预估在第 {first_number:.1f} 秒才出现；有核实过的数字应放进前 {FIRST_NUMBER_MAX_S:.0f} 秒"))
    hook_type = (brief.get("hook") or {}).get("type")
    verified = [cid for cid in first.get("claim_ids", []) if claims.get(cid, {}).get("status") in VERIFIED_STATUSES]
    if hook_type == "benefit" and not verified:
        findings.append(Finding("error", "hook.benefit_unverified", first["segment_id"], "优势型开头必须关联已核实事实（verified_source / verified_test）"))
    first_shot = shots["shots"][0]
    if not _is_visual_hook(first_shot):
        findings.append(Finding("warning", "hook.visual", first_shot["shot_id"], f"开头镜头是 {first_shot['scene_type']}；建议用 ResultHook、EvidenceCard 或 ScreenFocus 把结论、数字或真实成品直接放大"))
    candidates = speech.get("hook_candidates") or []
    if len(candidates) < 3:
        findings.append(Finding("warning", "hook.candidates", "speech.json", f"只记录了 {len(candidates)} 个开头备选；按规范写 3 个（痛点、数字优势、结果）再选"))
    for index, candidate in enumerate(candidates, start=1):
        findings += [Finding("warning", finding.rule, f"hook_candidates[{index}]", finding.message) for finding in _hook_findings(candidate.get("text", ""), "")]
    return findings


# (场景, 参数, 最大字号, 可用宽度, 低于该字号给警告, 低于该字号报错)；数值与 remotion-render 各场景的 fitFontSize 调用一致
_LINE_LIMITS: list[tuple[str, str, float, float, int, int]] = [
    ("ResultHook", "title", 104, TEXT_COLUMN_WIDTH, 80, 60),
    ("ActionEnd", "title", 96, TEXT_COLUMN_WIDTH, 76, 60),
    ("EvidenceCard", "big", 260, TEXT_COLUMN_WIDTH, 110, 72),
    ("ScreenFocus", "title", 68, TEXT_COLUMN_WIDTH, 52, 44),
    ("ScreenClip", "title", 68, TEXT_COLUMN_WIDTH, 52, 44),
    ("StepFlow", "title", 72, TEXT_COLUMN_WIDTH, 56, 44),
    ("BeforeAfter", "title", 72, TEXT_COLUMN_WIDTH, 56, 44),
]


def _split_lines(value: Any) -> list[str]:
    return str(value).split("\n") if value else []


def check_layout(shots: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for shot in shots["shots"]:
        scene, params, where = shot["scene_type"], shot.get("params", {}), shot["shot_id"]
        for limit_scene, key, max_size, width, warn_below, error_below in _LINE_LIMITS:
            lines = _split_lines(params.get(key))
            if scene == limit_scene and lines:
                size = fit_size(lines, max_size, width)
                if size < warn_below:
                    level = "error" if size < error_below else "warning"
                    findings.append(Finding(level, "layout.too_long", where, f"{key}「{'／'.join(lines)}」会缩到 {size}px（建议 ≥{warn_below}px）；缩短或用 \\n 分行"))
        if scene == "StepFlow":
            items = [str(item) for item in params.get("items", [])]
            if not 2 <= len(items) <= 4:
                findings.append(Finding("warning", "layout.item_count", where, f"条目 {len(items)} 条，建议 2～4 条"))
            size = fit_size(items, 54, STEP_TEXT_WIDTH) if items else 54
            if size < 46:
                findings.append(Finding("error" if size < 38 else "warning", "layout.too_long", where, f"条目会缩到 {size}px（建议 ≥46px），最长一条请控制在 13 个字宽内"))
        if scene == "KineticText":
            findings += _kinetic_layout(params, where)
        note = params.get("note")
        if note and text_units(str(note)) * 48 > NOTE_TEXT_WIDTH * 2:
            findings.append(Finding("warning", "layout.too_long", where, "note 超过两行，精简到约 30 个字宽内"))
        kicker = params.get("kicker")
        if kicker and text_units(str(kicker)) > 16:
            findings.append(Finding("warning", "layout.too_long", where, "kicker 过长，建议 16 个字宽内"))
    return findings


def _kinetic_layout(params: dict[str, Any], where: str) -> list[Finding]:
    """文字动效：所有拍共用一个字号（上限 112），按最长一行算；低于 72px 提醒、低于 56px 报错。高度由渲染层另行限制。"""
    beats = [beat for beat in params.get("beats", []) if isinstance(beat, dict)]
    lines = [str(beat.get(field)) for beat in beats for field in ("text", "replace") if beat.get(field)]
    size = fit_size(lines, 112, TEXT_COLUMN_WIDTH) if lines else 112
    if size >= 72:
        return []
    return [Finding("error" if size < 56 else "warning", "layout.too_long", where, f"文字动效会缩到 {size}px（建议 ≥72px）；最长一行控制在约 9 个字宽内")]


def check_cover(cover: dict[str, Any] | None) -> list[Finding]:
    if not cover:
        return [Finding("warning", "cover.missing", "cover.props.json", "缺少封面参数；封面标题应与开头的数字或痛点一致")]
    findings: list[Finding] = []
    if fit_size(_split_lines(cover.get("title")), 150, TEXT_COLUMN_WIDTH) < 100:
        findings.append(Finding("warning", "layout.too_long", "cover.props.json", "封面标题每行会缩到 100px 以下，缩短或分行"))
    if fit_size(_split_lines(cover.get("sub")), 60, TEXT_COLUMN_WIDTH) < 44:
        findings.append(Finding("warning", "layout.too_long", "cover.props.json", "封面副标题过长"))
    return findings


def _structure(speech: dict[str, Any], shots: dict[str, Any]) -> list[Finding]:
    order = [segment["segment_id"] for segment in speech["segments"]]
    used = [segment_id for shot in shots["shots"] for segment_id in shot["segment_ids"]]
    if used != order:
        return [Finding("error", "structure.segments", "shots.json", f"镜头引用的语段须按口播顺序、不重复不遗漏：语段 {order}，镜头引用 {used}")]
    return []


def _evidence_text(claim_ids: list[str], claims: dict[str, dict[str, Any]], sources: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = []
    for claim_id in claim_ids:
        claim = claims.get(claim_id, {})
        # 事实原文字段按数据合同为 statement（docs/DATA_CONTRACTS.md「sources.json 与 claims.json」）
        parts.append(str(claim.get("statement", "")))
        for source_id in claim.get("source_ids", []):
            source = sources.get(source_id, {})
            parts += [str(source.get(key) or "") for key in ("title", "version_or_scope", "checked_at", "published_at")]
    return " ".join(parts)


# 只影响版面、不上屏的参数：取景坐标、图片与录屏路径、录屏源区间与倍速、背景图、高亮序号等。它们里的数字不是事实，不做出处核对
_LAYOUT_KEYS = {"image", "image_size", "focus", "highlights", "highlight", "beats", "wallpaper", "backdrop", "variant",
                "video", "video_size", "source_in_ms", "source_out_ms", "playback_rate", "tone", "icon"}


def _display_texts(params: dict[str, Any]) -> list[str]:
    """上屏文字（去掉强调标记与语义色名），供出处核对与平台敏感词检查。"""
    texts: list[str] = []
    for key, value in params.items():
        if key == "beats" and isinstance(value, list):
            # KineticText 的每拍文字与换上的说法都会上屏；BeforeAfter 的 beats 只有序号与时间，没有 text
            texts += [plain_display(str(beat.get(field, ""))) for beat in value if isinstance(beat, dict) for field in ("text", "replace") if beat.get(field)]
            continue
        if key in _LAYOUT_KEYS:
            continue
        if key == "images" and isinstance(value, list):
            # 截图对比只有标签会上屏
            texts += [str(item.get("tag", "")) for item in value if isinstance(item, dict)]
            continue
        texts.append(plain_display(str(value)))
    return texts


def _is_visual_hook(shot: dict[str, Any]) -> bool:
    # 截图对比（BeforeAfter 带 images）第 0 帧就是两张真实成稿，同样算成品开头
    return shot["scene_type"] in VISUAL_HOOK_SCENES or (shot["scene_type"] == "BeforeAfter" and isinstance(shot.get("params", {}).get("images"), list))


def _numbers(value: Any) -> set[str]:
    text = value if isinstance(value, str) else " ".join(map(str, value)) if isinstance(value, list) else str(value)
    # 紧跟在字母后的数字属于名称（如 a16z、B2B），不当作需要出处的数值
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", text))


def check_traceability(speech: dict[str, Any], shots: dict[str, Any], claims: dict[str, dict[str, Any]], sources: dict[str, dict[str, Any]]) -> list[Finding]:
    findings = _structure(speech, shots)
    segment_claims = {segment["segment_id"]: segment.get("claim_ids", []) for segment in speech["segments"]}
    for shot in shots["shots"]:
        claim_ids = sorted(set(shot.get("claim_ids", [])) | {cid for sid in shot["segment_ids"] for cid in segment_claims.get(sid, [])})
        for claim_id in claim_ids:
            status = claims.get(claim_id, {}).get("status")
            if status is None:
                findings.append(Finding("error", "claims.missing", shot["shot_id"], f"引用了不存在的事实 {claim_id}"))
            elif status == "unverified":
                findings.append(Finding("error", "claims.unverified", shot["shot_id"], f"{claim_id} 未核实，不能进入配音和画面"))
        evidence = _evidence_text(claim_ids, claims, sources)
        texts = _display_texts(shot.get("params", {})) + [segment["display_text"] for segment in speech["segments"] if segment["segment_id"] in shot["segment_ids"]]
        missing = sorted(number for number in _numbers(texts) if number not in evidence)
        if missing:
            findings.append(Finding("warning", "claims.number_untraced", shot["shot_id"], f"数字 {missing} 在所引事实与来源中找不到原文，请核对写法或补充 claim"))
    return findings


# 以底图为背景的场景，与 remotion-render 的 WALLPAPER_SCENES 一致；BeforeAfter 只有截图对比（params.images）用底图
WALLPAPER_SCENES = ("StepFlow", "EvidenceCard", "ScreenFocus", "ScreenClip")


def check_backdrop(shots: dict[str, Any], brief: dict[str, Any]) -> list[Finding]:
    """背景按题材选（主理人 2026-10-07：背景不能每次一样）。有底图镜头却没在 brief.visual.backdrop_theme 选组时提醒；
    选了组但镜头写死 wallpaper 时也提醒，因为写死的镜头不参与题材轮换。"""
    uses = [shot for shot in shots["shots"] if shot["scene_type"] in WALLPAPER_SCENES
            or (shot["scene_type"] == "BeforeAfter" and isinstance((shot.get("params") or {}).get("images"), list))]
    if not uses:
        return []
    theme = (brief.get("visual") or {}).get("backdrop_theme")
    if not theme:
        return [Finding("warning", "backdrop.theme_missing", "brief.visual",
                        "有底图镜头但没设 brief.visual.backdrop_theme：背景会退回默认风景图；按题材选组（office / blueprint / tech / city / nature），见 docs/DESIGN.md 第 3 节")]
    fixed = [shot["shot_id"] for shot in uses if isinstance((shot.get("params") or {}).get("wallpaper"), str)]
    if fixed:
        return [Finding("warning", "backdrop.fixed_wallpaper", "、".join(fixed),
                        "这些镜头写死了 params.wallpaper，不参与题材轮换；确需固定才保留，否则删掉")]
    return []


def check_duration(speech: dict[str, Any], brief: dict[str, Any], variant: str) -> tuple[float, list[Finding]]:
    total = sum(estimate_seconds(segment["display_text"]) for segment in speech["segments"]) + 0.2 * len(speech["segments"]) + 1.0
    target = (brief.get("target_duration_seconds") or {}).get(variant)
    if target and not target["min"] <= total <= target["max"]:
        return total, [Finding("warning", "duration.range", variant, f"预估 {total:.0f} 秒，不在目标 {target['min']}～{target['max']} 秒内")]
    return total, []


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def lint_variant(variant: str, speech: dict[str, Any], shots: dict[str, Any], brief: dict[str, Any], claims: dict[str, dict[str, Any]],
                 sources: dict[str, dict[str, Any]], cover: dict[str, Any] | None) -> dict[str, Any]:
    findings = check_hook(speech, shots, brief, claims) + check_layout(shots) + check_cover(cover) + check_traceability(speech, shots, claims, sources)
    findings += check_backdrop(shots, brief) + check_tones(shots, Finding)
    total, duration_findings = check_duration(speech, brief, variant)
    findings += duration_findings
    first = speech["segments"][0]["display_text"]
    return {
        "variant": variant,
        "estimates": {"hook_first_sentence_s": round(estimate_seconds(first_sentence(first)), 1),
                      "first_number_s": _round(_first_number_seconds(speech["segments"])), "total_s": round(total)},
        "errors": sum(1 for finding in findings if finding.level == "error"),
        "warnings": sum(1 for finding in findings if finding.level == "warning"),
        "findings": [finding.as_dict() for finding in findings],
    }


def _core_chars(text: str) -> str:
    return re.sub(r"[\s，。？！、：；,.?!:;“”\"'（）()《》·]", "", text)


def hook_gate(speech: dict[str, Any], captions: list[dict[str, Any]]) -> dict[str, Any]:
    """
    配音后按真实字幕时间检查开头：第一句在第几毫秒说完、第一个数字在第几毫秒出现。
    字幕在句号处必断行，所以累计首段字幕的有效字数到第一句的字数，即为第一句结束的那条字幕。
    """
    first = speech["segments"][0]
    target = len(_core_chars(first_sentence(first["display_text"])))
    count, sentence_end_ms = 0, None
    for entry in captions:
        if entry.get("segment_id") != first["segment_id"]:
            break
        count += len(_core_chars(entry["text"]))
        if count >= target:
            sentence_end_ms = entry["end_ms"]
            break
    digit = next((entry for entry in captions if re.search(r"\d", entry["text"])), None)
    first_number_ms = digit["start_ms"] if digit else None
    problems = []
    if sentence_end_ms is None or sentence_end_ms > HOOK_FIRST_SENTENCE_MAX_S * 1000:
        problems.append(f"第一句在 {sentence_end_ms} ms 才说完，超过 {HOOK_FIRST_SENTENCE_MAX_S * 1000:.0f} ms")
    if first_number_ms is not None and first_number_ms > FIRST_NUMBER_MAX_S * 1000:
        problems.append(f"第一个数字在 {first_number_ms} ms 才出现，超过 {FIRST_NUMBER_MAX_S * 1000:.0f} ms")
    return {"first_sentence_end_ms": sentence_end_ms, "first_number_ms": first_number_ms, "first_caption_ms": captions[0]["start_ms"] if captions else None,
            "passed": not problems, "problems": problems}
