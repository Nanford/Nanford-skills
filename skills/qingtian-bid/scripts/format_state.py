"""Project format lifecycle for qingtian-bid: kickoff selection, tender override, confirmation.

INPUT: <project>/project-state.json; a tender format file written at stage 2
       (analysis/tender-format.json: 招标文件对格式的每条规定、"要求"或"建议"、出处，以及可选的
       penalty：评审注释里"不符合将酌情扣分"的原文和出处);
       normalized format records from docx_font_profiles.
OUTPUT: composed candidate format plus three-column diff rows ("所选 / 招标文件要求 / 最终采用"; the
        diff shows the penalty sentence, and a deviation's source carries it); penalty_sentence / penalty_issue
        for the rule-card cross-check;
        pending review records; confirmation that locks document_format in project-state.json.
POS: state layer behind render_format_sample --project and prepare_project. Pure logic, no
     rendering. Priority follows design D7: 招标文件 > 开工所选 > F1. Tender requirements are
     always laid over the user's own selection (format_selection), never over a previous tender
     result, so a later 补遗 that drops a field returns it to the user's choice.

project-state.json keys owned here:
  format_selection  用户自己的格式选择（开工所选及之后的自定义），招标文件覆盖以它为底
  tender_format     已确认的招标文件格式规定及用户同意的偏离
  document_format   锁定的最终格式；生成器和校验器只认它
  format_review     待确认的变更（kind: kickoff / selection / tender）；存在时生成器和校验器拒绝工作
  format_history    每次确认的记录
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path

from docx_font_profiles import (
    FIELD_LABELS,
    describe_value,
    file_sha256,
    normalize_document_format,
    parse_field_value,
    resolve_field_name,
)


STATE_NAME = "project-state.json"
TENDER_KINDS = ("要求", "建议")
# 评审注释里的扣分句。2026-10-30 核对的两份合肥招标文件都在编制建议末尾写了"如不符合上述要求将酌情扣分"：
# "建议"可以偏离，但偏离可能被扣分，所以偏离前必须把这句原文给用户看
PENALTY_SENTENCE = re.compile(r"[^。；;]*扣分[^。；;]*")
REVIEW_KINDS = ("kickoff", "selection", "tender")


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def state_path(project_dir: Path) -> Path:
    return project_dir.expanduser().resolve() / STATE_NAME


def load_state(project_dir: Path) -> dict:
    path = state_path(project_dir)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"项目状态无法读取: {path} ({exc})") from exc
    if not isinstance(state, dict) or not isinstance(state.get("stages"), dict):
        raise ValueError(f"项目状态缺少 stages，不是 qingtian-bid 项目: {path}")
    return state


# Windows 上杀毒、索引程序偶尔短暂占着刚写的文件，os.replace 报"拒绝访问"，等一下再试就好。合计等约 1.5 秒
REPLACE_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8)


def replace_state_file(temporary: Path, path: Path) -> None:
    """换上新的状态文件。只有被占用才重试；一直被占用才报错，原文件不动。"""
    for delay in REPLACE_RETRY_DELAYS:
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            time.sleep(delay)
    try:
        os.replace(temporary, path)
    except PermissionError as exc:
        raise PermissionError(f"项目状态文件被别的程序占用，这次没有保存，关掉占用它的程序后重试：{path}") from exc


def save_state(project_dir: Path, state: dict) -> Path:
    """先写临时文件再替换，避免中途失败留下半个状态文件。"""
    path = state_path(project_dir)
    state["updated_at"] = now_text()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".json",
                                     delete=False) as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        temporary = Path(stream.name)
    try:
        replace_state_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def current_selection(state: dict) -> dict | None:
    review = state.get("format_review")
    return review["selection"] if review else state.get("format_selection")


def current_tender(state: dict) -> dict | None:
    review = state.get("format_review")
    return review["tender"] if review else state.get("tender_format")


def with_blind_mode_defaults(settings: dict) -> dict:
    """决策 2A：暗标不设页码。用户只说开暗标时，页码随之关闭，不让用户再改一次。"""
    if settings.get("blind_mode") is True and "require_page_numbers" not in settings:
        return {**settings, "require_page_numbers": False}
    return settings


def _parse_requirement_value(field: str, raw: object) -> object:
    if isinstance(raw, str):
        return parse_field_value(field, raw)
    return raw  # JSON 里的数字、布尔和 null 原样交给 normalize_document_format 校验


def load_tender_spec(path: Path) -> dict:
    """Read the stage-2 tender format file; ambiguous or unsourced entries stop here."""
    path = path.expanduser().resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"招标文件格式规定无法读取: {path} ({exc})") from exc
    entries = data.get("requirements") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"招标文件格式规定缺少非空 requirements 列表: {path}")
    requirements = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or not {"field", "value", "kind", "source"} <= set(entry):
            raise ValueError(f"第 {index} 条规定须含 field、value、kind、source")
        field = resolve_field_name(str(entry["field"]))
        if field in seen:
            raise ValueError(f"招标文件对{FIELD_LABELS[field]}有两条规定，先在规则卡里核清以哪条为准")
        seen.add(field)
        if entry["kind"] not in TENDER_KINDS:
            raise ValueError(f"{FIELD_LABELS[field]}的 kind 只能是 要求 或 建议（当前: {entry['kind']}）")
        source = entry["source"]
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"{FIELD_LABELS[field]}缺少招标文件出处（章节、页码）")
        requirements.append({
            "field": field,
            "value": _parse_requirement_value(field, entry["value"]),
            "kind": entry["kind"],
            "source": source.strip(),
        })
    return {
        "document": str(data.get("document", "")).strip(),
        "file": str(path),
        "sha256": file_sha256(path),
        "requirements": requirements,
        "penalty": _parse_penalty(data.get("penalty")),
        "deviations": {},
    }


def _parse_penalty(raw: object) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or not all(isinstance(raw.get(key), str) and raw[key].strip()
                                            for key in ("text", "source")):
        raise ValueError("penalty 须含招标文件扣分原文 text 和出处 source")
    return {"text": raw["text"].strip(), "source": raw["source"].strip()}


def penalty_sentence(review_notes: object) -> str | None:
    """规则卡评审注释里的扣分句；没有注释或注释没写扣分的返回 None。"""
    match = PENALTY_SENTENCE.search(review_notes) if isinstance(review_notes, str) else None
    return match.group(0).strip("，, ") if match else None


def penalty_issue(review_notes: object, tender: dict) -> str | None:
    """评审注释写了扣分、招标文件格式规定里又有可偏离的"建议"时，格式规定必须登记扣分原文。"""
    sentence = penalty_sentence(review_notes)
    if not sentence or tender.get("penalty") or not any(item["kind"] == "建议" for item in tender["requirements"]):
        return None
    return (f"规则卡评审注释写明“{sentence}”：在招标文件格式规定里写 penalty（扣分原文 text、出处 source），"
            "偏离任何一条建议前先把原文给用户看")


def add_deviations(tender: dict, fields: list[str], note: str) -> dict:
    """Only a "建议" may be deviated from, and only with the user's recorded consent."""
    if fields and not note.strip():
        raise ValueError("偏离招标文件建议须写明用户同意的记录（--deviation-note）")
    by_field = {item["field"]: item for item in tender["requirements"]}
    deviations = dict(tender.get("deviations", {}))
    for name in fields:
        field = resolve_field_name(name)
        item = by_field.get(field)
        if item is None:
            raise ValueError(f"招标文件没有规定{FIELD_LABELS[field]}，无需偏离")
        if item["kind"] != "建议":
            raise ValueError(f"{FIELD_LABELS[field]}是招标文件的“要求”，不得偏离（{item['source']}）")
        deviations[field] = note.strip()
    return {**tender, "deviations": deviations}


def _tender_overlay(selection: dict, tender: dict) -> tuple[dict, dict, list[dict]]:
    values: dict = {}
    sources: dict = {}
    rows: list[dict] = []
    deviations = tender.get("deviations", {})
    by_field = {item["field"]: item for item in tender["requirements"]}
    for field, item in by_field.items():
        if field in deviations:
            if item["kind"] != "建议":
                raise ValueError(f"{FIELD_LABELS[field]}是招标文件的“要求”，不得偏离")
            values[field] = selection[field]
            sources[field] = f"偏离招标文件建议（{item['source']}）：{deviations[field]}{_penalty_note(tender)}"
            outcome = "偏离（用户同意）"
        else:
            values[field] = item["value"]
            sources[field] = f"招标文件{item['kind']}：{item['source']}"
            outcome = "一致" if selection[field] == item["value"] else "按招标文件覆盖"
        rows.append({"field": field, "selected": selection[field], "tender": item["value"],
                     "kind": item["kind"], "source": item["source"], "outcome": outcome})
    blind = values.get("blind_mode", selection["blind_mode"])
    if blind and selection["require_page_numbers"] and "require_page_numbers" not in by_field:
        # 暗标轨道一律不设页眉页脚页码（决策 2A）；招标文件明确要求页码的，交给 normalize 报冲突。
        reason = sources.get("blind_mode", selection["sources"]["blind_mode"])
        values["require_page_numbers"] = False
        sources["require_page_numbers"] = f"暗标不设页码（决策 2A；暗标依据：{reason}）"
        rows.append({"field": "require_page_numbers", "selected": True, "tender": None,
                     "kind": "随暗标", "source": reason, "outcome": "随暗标关闭"})
    return values, sources, rows


def compose_format(selection: dict, tender: dict | None) -> tuple[dict, list[dict]]:
    """Candidate = user selection overlaid with tender requirements (D7), plus diff rows."""
    selection = normalize_document_format(selection)
    if tender is None:
        return selection, []
    values, sources, rows = _tender_overlay(selection, tender)
    merged = {**selection, **values, "sources": {**selection["sources"], **sources}}
    try:
        candidate = normalize_document_format(merged)
    except ValueError as exc:
        raise ValueError(
            f"招标文件规定与所选格式合起来不成立：{exc}。请用 --set 调整招标文件未规定的字段，"
            "需要时把招标文件规定的字段按其取值一并写入（如 行距方式=固定值 与 行距值=28 同时设）"
        ) from exc
    for row in rows:
        row["final"] = candidate[row["field"]]
    return candidate, rows


def _describe(field: str, value: object, record: dict) -> str:
    if value is None and field != "latin_font":
        return "—"
    return describe_value(field, {**record, field: value})


def _penalty_note(tender: dict) -> str:
    # 状态文件里早于本字段的 tender 记录没有 penalty 键
    penalty = tender.get("penalty")
    return f"；招标文件写明“{penalty['text']}”（{penalty['source']}）" if penalty else ""


def diff_markdown(rows: list[dict], selection: dict, candidate: dict, tender: dict) -> str:
    penalty = tender.get("penalty")
    lines = [
        "# 格式差异：所选 / 招标文件要求 / 最终采用",
        "",
        f"- 招标文件格式规定：{tender['file']}（{tender['document'] or '未写文件名'}）",
        f"- 生成时间：{now_text()}",
        "- 招标文件写“建议”的也默认照做；偏离须用户明确同意，并记在出处里。“要求”不得偏离。",
        *([f"- 扣分原文：“{penalty['text']}”（{penalty['source']}）。偏离任何一条“建议”前，先把这句原文给用户看；"
           "用户知道偏离可能被扣分、仍明确同意的，才记 --deviation-note。"] if penalty else []),
        "",
        "| 字段 | 所选 | 招标文件要求 | 最终采用 | 结果 | 出处 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        field = row["field"]
        tender_text = "—" if row["kind"] == "随暗标" else f"{row['kind']}：{_describe(field, row['tender'], candidate)}"
        lines.append(
            f"| {FIELD_LABELS[field]} | {_describe(field, row['selected'], selection)} | {tender_text} | "
            f"{_describe(field, row['final'], candidate)} | {row['outcome']} | {row['source']} |"
        )
    lines.append("")
    return "\n".join(lines)


def check_tender_settings(settings: dict, tender: dict | None) -> None:
    """--set 改的是用户自己的选择；把招标文件规定的字段改成别的值也会被覆盖，所以直接拦下。

    取值与招标文件一致的放行：招标文件只规定行距方式时，所选的行距值要和行距方式一起改，
    否则单改行距值在原行距方式下不成立，两头都改不动。用户已同意偏离的"建议"字段用的就是
    所选的值，也放行。
    """
    if tender is None:
        return
    by_field = {item["field"]: item for item in tender["requirements"]}
    deviations = tender.get("deviations", {})
    for field, value in settings.items():
        if field in by_field and field not in deviations and value != by_field[field]["value"]:
            hint = "要保留自己的取值请用 --deviate" if by_field[field]["kind"] == "建议" else "不得偏离"
            raise ValueError(f"{FIELD_LABELS[field]}由招标文件{by_field[field]['kind']}规定，{hint}")


def make_review(kind: str, selection: dict, tender: dict | None, candidate: dict, rows: list[dict],
                sample: dict, diff_path: Path | None) -> dict:
    if kind not in REVIEW_KINDS:
        raise ValueError(f"未知的格式变更类型: {kind}")
    docx_path = Path(sample["docx"])
    return {
        "kind": kind,
        "selection": selection,
        "tender": tender,
        "candidate": candidate,
        "diff_rows": rows,
        "diff": str(diff_path) if diff_path else None,
        "sample_docx": str(docx_path),
        "sample_sha256": file_sha256(docx_path),
        "sample_pdf": sample.get("pdf"),
        "card": sample["card"],
        "created_at": now_text(),
    }


def confirm_review(project_dir: Path) -> dict:
    """Lock the pending format. Run only after the user explicitly approved the sample."""
    state = load_state(project_dir)
    review = state.get("format_review")
    if not review:
        raise ValueError("没有待确认的格式变更")
    sample = Path(review["sample_docx"])
    if not sample.exists() or file_sha256(sample) != review["sample_sha256"]:
        raise ValueError(f"样张在出样后被改动或删除，请重新出样再请用户确认: {sample}")
    candidate, _ = compose_format(review["selection"], review["tender"])
    if candidate != review["candidate"]:
        raise ValueError("格式预设库在出样后有变化，请重新出样再请用户确认")
    state["document_format"] = candidate
    state["format_selection"] = normalize_document_format(review["selection"])
    state["tender_format"] = review["tender"]
    state.setdefault("format_history", []).append({
        "kind": review["kind"],
        "confirmed_at": now_text(),
        "preset": candidate["preset"],
        "sample_sha256": review["sample_sha256"],
        "tender_file": review["tender"]["file"] if review["tender"] else None,
    })
    del state["format_review"]
    if state["stages"].get("0") != "done":
        state["stages"]["0"] = "done"  # 开工格式经用户确认，阶段 0 才算完成
    save_state(project_dir, state)
    return {"project": str(state_path(project_dir).parent), "kind": review["kind"],
            "preset": candidate["preset"], "stage_0": state["stages"]["0"]}
