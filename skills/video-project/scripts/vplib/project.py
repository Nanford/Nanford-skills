"""
INPUT: contracts.py 默认值；paths.py 项目目录解析；manifest.py 清单创建
OUTPUT: init_project() 建立 projects/YYYYMMDD-slug/ 目录骨架、brief.json、project.json、空素材表与费用账本
POS: 项目建档。只创建新项目，已存在的项目不覆盖（防止误删已有成果）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import (
    AUDIENCE_SEGMENTS,
    DEFAULT_PLATFORMS,
    DEFAULT_TARGET_SECONDS,
    DEFAULT_VOICE,
    PLATFORMS,
    PROJECT_DIRS,
    SCHEMA_VERSION,
    VARIANT_DIRS,
)
from .fsutil import sha256_file, write_json_atomic
from .manifest import MANIFEST_FILE, create_manifest
from .paths import project_dir, validate_project_id

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
INPUT_TYPES = ("topic", "article", "footage", "audio", "revision")


@dataclass
class ProjectRequest:
    slug: str
    date: str | None = None
    platforms: list[str] = field(default_factory=lambda: list(DEFAULT_PLATFORMS))
    topic: str = ""
    audience_segment: str | None = None
    input_type: str = "topic"
    source_article: str | None = None


def validate_request(request: ProjectRequest) -> str:
    """校验后返回项目 ID；任何不合法参数在创建目录之前就报错。"""
    if not SLUG_PATTERN.match(request.slug):
        raise ValueError(f"slug 只能是小写字母、数字和连字符：{request.slug}")
    unknown = [p for p in request.platforms if p not in PLATFORMS]
    if unknown or not request.platforms:
        raise ValueError(f"平台只能是 {PLATFORMS}，收到 {request.platforms}")
    if request.audience_segment and request.audience_segment not in AUDIENCE_SEGMENTS:
        raise ValueError(f"受众细分只能是 {AUDIENCE_SEGMENTS}")
    if request.input_type not in INPUT_TYPES:
        raise ValueError(f"输入类型只能是 {INPUT_TYPES}")
    date = request.date or datetime.now().strftime("%Y%m%d")
    return validate_project_id(f"{date}-{request.slug}")


def article_input(source_article: str) -> dict[str, Any]:
    """
    改编来源只记录位置与 SHA-256，原文不复制进项目（AGENTS.md 5.1）。
    校验值用于日后判断原文是否被改过；暂不限制来源目录，任何本地文章都可作为来源。
    """
    path = Path(source_article).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"改编来源文章不存在：{path}")
    return {"kind": "article", "path_or_url": str(path), "sha256": sha256_file(path), "usage": "改编来源", "rights_status": "confirmed"}


def build_brief(project_id: str, request: ProjectRequest, inputs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "is_example": False,
        "project_id": project_id,
        "topic": request.topic,
        "audience": "",
        "core_question": "",
        "audience_segment": request.audience_segment,
        "hook": {"type": None, "text": ""},
        "input_type": request.input_type,
        "inputs": inputs,
        "platforms": request.platforms,
        "target_duration_seconds": {p: DEFAULT_TARGET_SECONDS[p] for p in request.platforms},
        "mode": "hybrid",
        "voice": dict(DEFAULT_VOICE),
        "music": {"mode": "licensed_library", "asset_id": None},
        # 预算默认未授权：不产生新增计费请求，直到任务中明确给出上限
        "budget": {"currency": "CNY", "authorized_max": 0, "authorization_ref": None, "allow_new_paid_calls": False},
        "publish": {"authorized": False, "account_ref": None, "authorization_ref": None},
        # 系列默认（docs/DESIGN.md，主理人 2026-09-30 选择）：画面不画 AI 角标、成片不写隐式标识，
        # 靠发布时勾选平台 AI 声明；单条要恢复角标时把 explicit_overlay 改为 corner_badge
        "aigc": {"final_implicit_label": "none", "explicit_overlay": "none", "decision_ref": "系列默认：docs/DESIGN.md 第 3 节（2026-09-30 主理人选择选项 C）"},
        # 底图按题材选组（主理人 2026-10-07）：写脚本时按选题填 office / blueprint / tech / city / nature 中的一到两组，
        # 留空时渲染退回默认风景图，script-check lint 会提醒
        "visual": {"backdrop_theme": None},
        "constraints": [],
    }


def init_project(request: ProjectRequest) -> Path:
    project_id = validate_request(request)
    # 先校验来源文章，再创建目录：来源不存在时不留下空项目
    inputs = [article_input(request.source_article)] if request.source_article else []
    root = project_dir(project_id)
    if (root / MANIFEST_FILE).exists():
        raise FileExistsError(f"项目已存在：{root}")
    for relative in PROJECT_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)
    for platform in request.platforms:
        for relative in VARIANT_DIRS:
            (root / "variants" / platform / relative).mkdir(parents=True, exist_ok=True)
    write_json_atomic(root / "brief.json", build_brief(project_id, request, inputs))
    write_json_atomic(root / "assets" / "assets.json", {"schema_version": SCHEMA_VERSION, "assets": []})
    write_json_atomic(root / "costs" / "ledger.json", {"schema_version": SCHEMA_VERSION, "currency": "CNY", "entries": []})
    write_json_atomic(root / MANIFEST_FILE, create_manifest(project_id, request.platforms))
    return root
