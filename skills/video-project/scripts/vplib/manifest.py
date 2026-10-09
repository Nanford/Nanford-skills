"""
INPUT: contracts.py 常量；fsutil.py 原子读写
OUTPUT: create_manifest / load_manifest / save_manifest / update_stage / mark_stale_from
POS: project.json 的唯一写入者。阶段状态只通过这里修改，保证 revision、updated_at 与失效传播一致。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import (
    SCHEMA_VERSION,
    SHARED_STAGE_FIRST_AFFECTED,
    SHARED_STAGES,
    STAGE_STATUSES,
    VARIANT_STAGES,
)
from .fsutil import now_iso, read_json, write_json_atomic

MANIFEST_FILE = "project.json"


def empty_stage() -> dict[str, Any]:
    return {
        "status": "pending",
        "applicability": "required",
        "input_hash": None,
        "config_hash": None,
        "tool_versions": {},
        "output_files": [],
        "checks": [],
        "attempt": 0,
        "started_at": None,
        "finished_at": None,
        "error_code": None,
        "recovery_action": None,
    }


def create_manifest(project_id: str, platforms: list[str]) -> dict[str, Any]:
    now = now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "capabilities": {},
        "shared_stages": {stage: empty_stage() for stage in SHARED_STAGES},
        "variants": {platform: {stage: empty_stage() for stage in VARIANT_STAGES} for platform in platforms},
        "blockers": [],
    }


def load_manifest(project_root: Path) -> dict[str, Any]:
    return read_json(project_root / MANIFEST_FILE)


def save_manifest(project_root: Path, manifest: dict[str, Any]) -> None:
    manifest["revision"] += 1
    manifest["updated_at"] = now_iso()
    write_json_atomic(project_root / MANIFEST_FILE, manifest)


def mark_stale_from(manifest: dict[str, Any], platform: str, first_stage: str) -> list[str]:
    """从 first_stage（含）开始，把已通过或失败的阶段标记为 stale；未开始的阶段保持 pending。"""
    stages = manifest["variants"][platform]
    affected = []
    for stage in VARIANT_STAGES[VARIANT_STAGES.index(first_stage):]:
        if stages[stage]["status"] in ("passed", "failed"):
            stages[stage]["status"] = "stale"
            affected.append(stage)
    return affected


def outputs_changed(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> bool:
    return {(item["path"], item["sha256"]) for item in previous} != {(item["path"], item["sha256"]) for item in current}


def propagate_staleness(manifest: dict[str, Any], stage: str, platform: str | None) -> dict[str, list[str]]:
    """上游产物变化后，按数据合同第 7 节把受影响的下游阶段标为 stale。"""
    if platform is not None:
        index = VARIANT_STAGES.index(stage)
        if index + 1 >= len(VARIANT_STAGES):
            return {}
        return {platform: mark_stale_from(manifest, platform, VARIANT_STAGES[index + 1])}
    first = SHARED_STAGE_FIRST_AFFECTED[stage]
    return {name: mark_stale_from(manifest, name, first) for name in manifest["variants"]}


def stage_record(manifest: dict[str, Any], stage: str, platform: str | None) -> dict[str, Any]:
    if stage in SHARED_STAGES:
        if platform is not None:
            raise ValueError(f"{stage} 是公共阶段，不要指定 --variant")
        return manifest["shared_stages"][stage]
    if stage not in VARIANT_STAGES:
        raise ValueError(f"未知阶段 {stage}，可选：{SHARED_STAGES + VARIANT_STAGES}")
    if platform is None or platform not in manifest["variants"]:
        raise ValueError(f"平台阶段 {stage} 需要 --variant，可选：{sorted(manifest['variants'])}")
    return manifest["variants"][platform][stage]


def update_stage(manifest: dict[str, Any], stage: str, platform: str | None, status: str, patch: dict[str, Any]) -> dict[str, list[str]]:
    """
    更新阶段状态并返回被标记为 stale 的下游阶段。
    只有 passed 且产物校验值与上次不同时才传播失效：重复登记同样的产物不会误伤下游。
    """
    if status not in STAGE_STATUSES:
        raise ValueError(f"未知状态 {status}，可选：{STAGE_STATUSES}")
    record = stage_record(manifest, stage, platform)
    previous_outputs = list(record["output_files"])
    now = now_iso()
    if status == "running":
        record["attempt"] += 1
        record["started_at"] = now
        record["finished_at"] = None
    if status in ("passed", "failed", "blocked"):
        record["finished_at"] = now
    record.update(patch)
    record["status"] = status
    if status == "passed":
        record["error_code"] = None
        record["recovery_action"] = None
        if outputs_changed(previous_outputs, record["output_files"]):
            return propagate_staleness(manifest, stage, platform)
    return {}
