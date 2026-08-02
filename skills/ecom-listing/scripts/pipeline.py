#!/usr/bin/env python3
"""Detect and record resumable ecommerce listing stages."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


STAGES = [
    ("brief", "ecom-listing", ["listing.json"]),
    ("strategy", "ecom-listing", ["strategy.json"]),
    ("copy", "ecom-listing", ["copy.json"]),
    ("image_plan", "ecom-listing", ["image_jobs.json"]),
    ("image_render", "ecom-image", ["base_images/render_manifest.json"]),
    ("image_compose", "ecom-image", ["final_images/compose_manifest.json"]),
    ("quality", "ecom-publish", ["quality-report.json"]),
    ("export", "ecom-publish", ["listing_export.csv", "export_manifest.json"]),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ok(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if path.name in {"render_manifest.json", "compose_manifest.json"}:
            return payload.get("status") == "complete"
        if path.name == "quality-report.json":
            return int(payload.get("blocking", 1)) == 0
    return True


def status(workdir: Path) -> dict:
    rows = []
    next_skill = None
    prior_complete = True
    upstream_latest = 0.0
    for stage, skill, rel_paths in STAGES:
        paths = [workdir / rel for rel in rel_paths]
        raw_complete = all(artifact_ok(path) for path in paths)
        oldest_artifact = min((path.stat().st_mtime for path in paths if path.exists()), default=0.0)
        fresh = oldest_artifact >= upstream_latest
        complete = prior_complete and raw_complete and fresh
        rows.append({
            "stage": stage,
            "skill": skill,
            "complete": complete,
            "stale": raw_complete and not complete,
            "artifacts": [str(path) for path in paths],
        })
        if not complete and next_skill is None:
            next_skill = skill
        if complete:
            upstream_latest = max(upstream_latest, max(path.stat().st_mtime for path in paths))
        else:
            prior_complete = False
    return {
        "workdir": str(workdir),
        "complete": next_skill is None,
        "next_skill": next_skill,
        "stages": rows,
    }


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": "1.0", "created_at": utc_now(), "history": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mark(workdir: Path, stage_name: str) -> dict:
    match = next((row for row in STAGES if row[0] == stage_name), None)
    if not match:
        raise ValueError(f"未知阶段：{stage_name}")
    _, skill, rel_paths = match
    paths = [workdir / rel for rel in rel_paths]
    missing = [str(path) for path in paths if not artifact_ok(path)]
    if missing:
        raise ValueError("产物缺失或不可解析：" + ", ".join(missing))

    state_path = workdir / "pipeline.json"
    state = load_state(state_path)
    state["updated_at"] = utc_now()
    state["history"].append({
        "stage": stage_name,
        "skill": skill,
        "completed_at": utc_now(),
        "artifacts": [
            {"path": str(path.relative_to(workdir)), "sha256": digest(path)} for path in paths
        ],
    })
    save_state(state_path, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="管理可续跑的电商 Listing 流程")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "status"):
        item = sub.add_parser(command)
        item.add_argument("--workdir", required=True)
    mark_parser = sub.add_parser("mark")
    mark_parser.add_argument("--workdir", required=True)
    mark_parser.add_argument("--stage", required=True, choices=[s[0] for s in STAGES])
    args = parser.parse_args()

    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    if args.command == "init":
        path = workdir / "pipeline.json"
        if not path.exists():
            save_state(path, load_state(path))
        result = status(workdir)
    elif args.command == "mark":
        mark(workdir, args.stage)
        result = status(workdir)
    else:
        result = status(workdir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
