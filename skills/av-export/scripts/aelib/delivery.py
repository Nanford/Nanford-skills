"""
INPUT: 项目目录下 brief.json、costs/ledger.json、qa/report.json、各版本产物与 audio/mix.json
OUTPUT: build_delivery()：数据合同第 8 节的 delivery.json 内容（文件清单、三个独立状态、待检查事项、授权、成本、AIGC 标识、重渲染说明）
POS: 交付清单的唯一生成点。状态只由 qa/report.json 中「绑定当前成片校验值」的检查结果推导，文件存在本身不算通过。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .media import local_now, read_json, sha256_file

# (相对版本目录的路径模板, 用途)；{version} 为交付版本号，如 v001
VARIANT_FILES: list[tuple[str, str]] = [
    ("exports/final-{version}.mp4", "正式成片（字幕、人声、标识）"),
    ("exports/voice-only-{version}.mp4", "无配乐母版"),
    ("exports/cover-{version}.png", "竖版封面"),
    ("cover.props.json", "可编辑封面布局参数"),
    ("publish.md", "标题、说明、话题与 AI 内容声明"),
    ("captions/subtitles.srt", "SRT 字幕"),
    ("captions/captions.json", "字幕 JSON"),
    ("audio/voice.wav", "原始配音母轨"),
    ("audio/mix.wav", "最终混音"),
    ("audio/mix.json", "混音记录与来源 AIGC 标识"),
    ("script.md", "定稿脚本"),
    ("voiceover.txt", "配音稿"),
    ("speech.json", "语段、读音与真实时间"),
    ("shots.json", "分镜"),
    ("timeline.json", "最终时间轴"),
]
# 可选产物：存在才列入清单，缺了不算缺件（没有文字动效的片子就没有音效轨）
OPTIONAL_VARIANT_FILES: list[tuple[str, str]] = [
    ("actions.json", "动作标记（画面动作帧，音效对点依据）"),
    ("audio/sfx.wav", "音效轨（sfx-kit 本地合成，自有、无第三方权利）"),
    ("audio/sfx.json", "音效轨记录（每个音效的动作、帧与校验值）"),
]
PROJECT_FILES: list[tuple[str, str]] = [
    ("brief.json", "任务说明与授权"),
    ("research/claims.json", "事实表"),
    ("research/sources.json", "来源清单"),
    ("assets/assets.json", "素材清单"),
    ("costs/ledger.json", "成本记录"),
    ("qa/report.json", "质检报告"),
]


def _file_entry(project_dir: Path, path: Path, purpose: str) -> dict[str, Any]:
    return {"path": path.relative_to(project_dir).as_posix(), "purpose": purpose, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _collect(project_dir: Path, base: Path, specs: list[tuple[str, str]], version: str) -> tuple[list[dict[str, Any]], list[str]]:
    files, missing = [], []
    for template, purpose in specs:
        path = base / template.format(version=version)
        if path.is_file():
            files.append(_file_entry(project_dir, path, purpose))
        else:
            missing.append(path.relative_to(project_dir).as_posix())
    return files, missing


def _segment_files(project_dir: Path, variant_dir: Path) -> list[dict[str, Any]]:
    """原始配音分段 MP3 保留服务商签名的 AIGC 隐式标识，随交付包保存。"""
    return [_file_entry(project_dir, path, "原始配音分段（含服务商 AIGC 标识）") for path in sorted((variant_dir / "audio" / "segments").glob("*.mp3"))]


def _status(items: list[dict[str, Any]], scope: str) -> bool:
    scoped = [item for item in items if item["scope"] == scope and item["blocking"]]
    return bool(scoped) and all(item["result"] == "passed" for item in scoped)


def _variant_block(project_dir: Path, variant: str, version: str, report: dict[str, Any], publish_authorized: bool) -> dict[str, Any]:
    variant_dir = project_dir / "variants" / variant
    files, missing = _collect(project_dir, variant_dir, VARIANT_FILES, version)
    files += _segment_files(project_dir, variant_dir)
    files += [_file_entry(project_dir, variant_dir / path, purpose) for path, purpose in OPTIONAL_VARIANT_FILES if (variant_dir / path).is_file()]
    final = next((entry for entry in files if entry["path"].endswith(f"exports/final-{version}.mp4")), None)
    voice_only = next((entry for entry in files if entry["path"].endswith(f"exports/voice-only-{version}.mp4")), None)
    items = [item for item in report.get("items", []) if item["variant"] == variant and final and item["artifact_sha256"] == final["sha256"]]
    render_complete = final is not None and _status(items, "render")
    delivery_ready = render_complete and not missing and _status(items, "delivery")
    block: dict[str, Any] = {
        "render_complete": render_complete,
        "delivery_ready": delivery_ready,
        "ready_to_publish": delivery_ready and publish_authorized and _status(items, "publish"),
        "final": final,
        "files": files,
        "missing": missing,
        "pending_checks": [{key: item[key] for key in ("check_id", "scope", "result", "blocking", "method")} for item in items if item["result"] != "passed"],
    }
    if final and voice_only and final["sha256"] == voice_only["sha256"]:
        block["voice_only_note"] = "本片无配乐，无配乐母版与正式成片内容相同（保留字幕、人声与 AI 标识）"
    return block


def _costs(ledger: dict[str, Any]) -> dict[str, Any]:
    entries = ledger.get("entries", [])
    actual = [entry["actual"] for entry in entries if entry.get("actual") is not None]
    return {
        "currency": ledger.get("currency"),
        "entries": len(entries),
        "estimated_total": round(sum(entry.get("estimated") or 0 for entry in entries), 4),
        # 没有任何结算额时为 null，不能写 0 冒充已结算
        "actual_total": round(sum(actual), 4) if actual else None,
        "unsettled_entries": sum(1 for entry in entries if entry.get("settlement_status") != "settled"),
    }


def explicit_label_text(decision: dict[str, Any] | None) -> str:
    """显式标识的实际形式：explicit_overlay 为 none 时画面不画角标，只剩发布时的平台声明，交付清单必须如实写出。"""
    if decision and decision.get("explicit_overlay") == "none":
        return "画面无 AI 角标；依靠发布时勾选平台的 AI 生成内容声明（brief.aigc.explicit_overlay = none）"
    return "画面顶部全程「AI 合成配音」角标"


def _aigc(project_dir: Path, variants: list[str], report: dict[str, Any], decision: dict[str, Any] | None) -> dict[str, Any]:
    # decision 来自 brief.aigc：成片是否另写隐式标识、画面是否画角标都由账号持有人决定，未决定时为 null
    summary: dict[str, Any] = {"explicit_label": explicit_label_text(decision), "final_implicit_label_decision": decision, "variants": {}}
    for variant in variants:
        mix_path = project_dir / "variants" / variant / "audio" / "mix.json"
        labels = read_json(mix_path).get("source_aigc_labels", []) if mix_path.is_file() else []
        implicit = next((item for item in report.get("items", []) if item["variant"] == variant and item["check_id"] == "labels.aigc_implicit"), None)
        summary["variants"][variant] = {
            "source_segments": len(labels),
            "source_segments_labeled": sum(1 for label in labels if label.get("present")),
            "final_file_implicit_label": None if implicit is None else implicit["result"] == "passed",
        }
    return summary


def build_delivery(project_dir: Path, version: str, rerender: list[str]) -> dict[str, Any]:
    brief = read_json(project_dir / "brief.json")
    report_path = project_dir / "qa" / "report.json"
    report = read_json(report_path) if report_path.is_file() else {"items": []}
    publish_authorized = bool(brief.get("publish", {}).get("authorized"))
    variants = list(brief.get("platforms", []))
    blocks = {variant: _variant_block(project_dir, variant, version, report, publish_authorized) for variant in variants}
    project_files, project_missing = _collect(project_dir, project_dir, PROJECT_FILES, version)
    return {
        "schema_version": "1.0",
        "project_id": brief.get("project_id"),
        "version": version,
        "generated_at": local_now(),
        "render_complete": all(block["render_complete"] for block in blocks.values()),
        "delivery_ready": all(block["delivery_ready"] for block in blocks.values()) and not project_missing,
        "ready_to_publish": all(block["ready_to_publish"] for block in blocks.values()),
        "variants": blocks,
        "project_files": project_files,
        "project_missing": project_missing,
        "authorization": {
            "publish": brief.get("publish"),
            "voice": brief.get("voice"),
            "music": brief.get("music"),
            "budget": brief.get("budget"),
        },
        "costs": _costs(read_json(project_dir / "costs" / "ledger.json")),
        "aigc": _aigc(project_dir, variants, report, brief.get("aigc")),
        "rerender": rerender,
    }
