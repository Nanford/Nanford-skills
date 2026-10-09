"""
INPUT: 用户提供的素材文件；media.py 探测；fsutil.py 校验值与原子写入
OUTPUT: import_asset() 把素材复制为项目内只读副本并登记到 assets/assets.json
POS: 素材入库的唯一入口。原件不移动、不修改；项目内副本以 asset_id 命名，避免中文与空格路径问题。
"""

from __future__ import annotations

import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import ASSET_KINDS, PLATFORMS, RIGHTS_STATUSES, SCHEMA_VERSION
from .fsutil import now_iso, read_json, sha256_file, write_json_atomic
from .media import probe_media

ASSETS_FILE = Path("assets") / "assets.json"
# 字体与图片不需要 ffprobe 的时长信息，但仍探测以获得宽高；字体文件跳过探测
UNPROBED_KINDS = {"font"}


@dataclass
class AssetRequest:
    source: Path
    kind: str
    rights: str = "unconfirmed"
    origin_source: str | None = None
    author: str | None = None
    proof: str | None = None
    platforms: list[str] = field(default_factory=lambda: list(PLATFORMS))
    ai_generated: bool = False
    label_info: str | None = None


def validate_asset_request(request: AssetRequest) -> Path:
    source = request.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"素材文件不存在：{source}")
    if request.kind not in ASSET_KINDS:
        raise ValueError(f"素材类型只能是 {ASSET_KINDS}")
    if request.rights not in RIGHTS_STATUSES:
        raise ValueError(f"授权状态只能是 {RIGHTS_STATUSES}")
    if any(p not in PLATFORMS for p in request.platforms):
        raise ValueError(f"平台只能是 {PLATFORMS}")
    return source


def next_asset_id(assets: list[dict[str, Any]], kind: str) -> str:
    """asset_<类型>_<序号>：稳定、可读，删除素材后也不复用旧编号，避免分镜引用错位。"""
    prefix = f"asset_{kind}_"
    numbers = [int(a["asset_id"][len(prefix):]) for a in assets if a["asset_id"].startswith(prefix) and a["asset_id"][len(prefix):].isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1:03d}"


def copy_read_only(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.tmp")
    shutil.copy2(source, temporary)
    temporary.replace(target)
    # 项目内原件只读，工作副本另存到 assets/work/，防止剪辑步骤误改原件
    target.chmod(stat.S_IREAD)


def build_record(request: AssetRequest, asset_id: str, source: Path, stored: str, digest: str, size: int, media: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "kind": request.kind,
        "original_path": str(source),
        "stored_path": stored,
        "work_path": None,
        "sha256": digest,
        "bytes": size,
        **media,
        "origin": {"source": request.origin_source, "author": request.author, "imported_at": now_iso()},
        "rights": {
            "status": request.rights,
            "proof": request.proof,
            "platforms": request.platforms,
            "commercial_use": None,
            "attribution_required": None,
            "expires_at": None,
        },
        "privacy_checked": False,
        "ai_generated": request.ai_generated,
        "label_info": request.label_info,
    }


def import_asset(project_root: Path, request: AssetRequest) -> dict[str, Any]:
    source = validate_asset_request(request)
    assets_path = project_root / ASSETS_FILE
    table = read_json(assets_path) if assets_path.exists() else {"schema_version": SCHEMA_VERSION, "assets": []}
    digest = sha256_file(source)
    duplicate = next((a for a in table["assets"] if a["sha256"] == digest), None)
    if duplicate:
        # 同一文件重复导入直接返回已有记录，不生成第二个 ID
        return duplicate
    media = {} if request.kind in UNPROBED_KINDS else probe_media(source)
    asset_id = next_asset_id(table["assets"], request.kind)
    stored = f"assets/original/{asset_id}{source.suffix.lower()}"
    copy_read_only(source, project_root / stored)
    record = build_record(request, asset_id, source, stored, digest, source.stat().st_size, media)
    table["assets"].append(record)
    write_json_atomic(assets_path, table)
    return record
