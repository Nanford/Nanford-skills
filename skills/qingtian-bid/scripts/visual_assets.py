"""Validate reviewed visual assets without claiming to detect Agent tools locally.

INPUT: optional visual-assets.json, local images and recorded visual review hashes.
OUTPUT: validated image records, required-job coverage and build-dependency issues; CLI exits 1 on errors.
POS: stage-5/6 visual provenance and stage-6/7 change detection, no network calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

KINDS = {"ai-illustration", "source-photo", "technical-diagram"}
CHECKS = ("content", "safety", "identity", "legibility")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_visual_assets(path: Path) -> dict[Path, dict]:
    """A review is valid only for the exact bytes inspected; never auto-approve it."""
    path = path.resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("图片清单 schema_version 必须为 1")
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise ValueError("图片清单 assets 必须是列表")
    jobs = data.get("required_jobs", [])
    if not isinstance(jobs, list):
        raise ValueError("required_jobs 必须为列表")
    planned = {}
    for job in jobs:
        if not isinstance(job, dict) or any(not isinstance(job.get(key), str) or not job[key].strip()
                                            for key in ("id", "kind", "section")):
            raise ValueError("必需配图作业须登记 id、kind、section")
        if job["id"] in planned or job["kind"] not in KINDS:
            raise ValueError(f"必需配图作业编号重复或类型无效：{job['id']}")
        planned[job["id"]] = job
    result, ids, captions = {}, set(), set()
    for item in assets:
        if not isinstance(item, dict):
            raise ValueError("图片条目必须是对象")
        for key in ("id", "file", "caption", "purpose", "section"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"图片条目缺少 {key}")
        label = item["id"]
        job = planned.get(label)
        if job and (item.get("kind") != job["kind"] or item["section"] != job["section"]):
            raise ValueError(f"配图类型或小节与作业不符：{label}")
        if label in ids or item["caption"] in captions:
            raise ValueError(f"图片编号或图题重复：{label}")
        ids.add(label)
        captions.add(item["caption"])
        image_path = (path.parent / item["file"]).resolve()
        if image_path in result or not image_path.is_file():
            raise ValueError(f"图片路径重复或不存在：{label}")
        if not isinstance(item.get("kind"), str) or item["kind"] not in KINDS:
            raise ValueError(f"图片类型无效：{label}")
        refs = item.get("source_refs")
        if not isinstance(refs, list) or not refs or any(not isinstance(x, str) or not x.strip() for x in refs):
            raise ValueError(f"图片缺少事实/资源/图纸依据：{label}")
        review = item.get("review") or {}
        if not isinstance(review, dict) or any(review.get(k) is not True for k in CHECKS):
            raise ValueError(f"图片尚未完成内容、安全、身份、可读性检查：{label}")
        sha = digest(image_path)
        if review.get("sha256") != sha:
            raise ValueError(f"图片在检查后发生变化，须重新检查：{label}")
        if not isinstance(review.get("note"), str) or not review["note"].strip():
            raise ValueError(f"图片缺少检查说明：{label}")
        if item["kind"] == "ai-illustration":
            if "示意" not in item["caption"]:
                raise ValueError(f"生成图片图题须明确为示意：{label}")
            generation = item.get("generation") or {}
            if not isinstance(generation, dict) or any(not isinstance(generation.get(k), str) or not generation[k].strip()
                                                       for k in ("tool", "mode", "prompt")):
                raise ValueError(f"生成图片缺少工具、模式或提示词记录：{label}")
        result[image_path] = {**item, "sha256": sha, "required_section": job["section"] if job else None}
    missing = planned.keys() - ids
    if missing:
        raise ValueError(f"必需配图尚未完成：{'、'.join(sorted(missing))}")
    if not result:
        raise ValueError("图片清单 assets 必须是非空列表")
    return result


def visual_dependency_issues(report: dict, docx_path: Path | None = None) -> list[str]:
    """Legacy reports without visual tracking remain readable; new reports fail closed."""
    if not isinstance(report, dict):
        return ["构建报告图片来源记录损坏，须重新出稿"]
    if "image_sources" not in report and "visual_manifest" not in report:
        return []
    sources = report.get("image_sources", [])
    if not isinstance(sources, list):
        return ["构建报告图片来源记录损坏，须重新出稿"]
    records = list(sources)
    if report.get("visual_manifest") is not None:
        records.append(report["visual_manifest"])
    issues = []
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("file"), str) or not item.get("file"):
            issues.append("构建报告图片来源记录损坏，须重新出稿")
            continue
        path = Path(item["file"])
        try:
            valid = path.is_file() and digest(path) == item.get("sha256")
        except OSError:
            valid = False
        if not valid:
            issues.append(f"图片或图文清单已变化/缺失，须重新检查并出稿：{path.name}")
    if docx_path is not None and "image_sources" in report:
        # Word can replace an embedded picture without changing any source PNG.
        # Compare media bytes as well, so the approved sources still match delivery.
        expected = {item["sha256"] for item in sources
                    if isinstance(item, dict) and isinstance(item.get("sha256"), str)}
        try:
            with ZipFile(docx_path) as package:
                actual = {hashlib.sha256(package.read(name)).hexdigest()
                          for name in package.namelist() if name.startswith("word/media/") and not name.endswith("/")}
            if actual != expected:
                issues.append("DOCX 内嵌图片与构建记录不一致，须重新检查并出稿")
        except (OSError, BadZipFile):
            issues.append("DOCX 内嵌图片无法核对，须重新检查并出稿")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="检查图文清单及图片审查记录；不探测当前 Agent 的工具。")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        assets = load_visual_assets(args.manifest)
    except (OSError, ValueError, TypeError) as exc:
        print(f"图片检查失败：{exc}")
        return 1
    print(json.dumps({"assets": len(assets), "status": "passed"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
