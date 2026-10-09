"""
INPUT: 环境变量 VC_PROJECTS_ROOT（可选，测试时指向临时目录）；workspace.py 找到的工作区根目录
OUTPUT: REPO_ROOT、项目目录解析、项目 ID 校验、项目内相对路径转换与越界检查
POS: 路径安全的唯一入口。任何写入项目的路径都经过 resolve_inside，防止 ../ 越出项目目录。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .workspace import find_workspace, require_workspace

# 工作区根目录（projects/ 所在）；技能可能装在工作区外，找不到时为 None，见 workspace.py
REPO_ROOT = find_workspace()
PROJECT_ID_PATTERN = re.compile(r"^\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*$")


class PathSafetyError(ValueError):
    pass


def projects_root() -> Path:
    override = os.environ.get("VC_PROJECTS_ROOT")
    if override:
        return Path(override).resolve()
    return (require_workspace(REPO_ROOT, "项目目录", PathSafetyError) / "projects").resolve()


def validate_project_id(project_id: str) -> str:
    if not PROJECT_ID_PATTERN.match(project_id):
        raise PathSafetyError(f"项目 ID 不合法：{project_id}（应为 YYYYMMDD-小写短名，如 20260929-bid-skill）")
    return project_id


def project_dir(project_id: str) -> Path:
    return projects_root() / validate_project_id(project_id)


def resolve_inside(root: Path, relative_path: str) -> Path:
    """把相对路径解析到 root 之内；结果越出 root 时抛错。"""
    if Path(relative_path).is_absolute():
        raise PathSafetyError(f"此处只接受项目内相对路径：{relative_path}")
    base = root.resolve()
    target = (base / relative_path).resolve()
    if target != base and base not in target.parents:
        raise PathSafetyError(f"路径越出项目目录：{relative_path}")
    return target


def to_project_relative(root: Path, absolute_path: Path) -> str:
    """清单中统一存 / 分隔的相对路径，跨平台可读。"""
    base = root.resolve()
    target = absolute_path.resolve()
    if base not in target.parents:
        raise PathSafetyError(f"文件不在项目目录内：{absolute_path}")
    return target.relative_to(base).as_posix()
