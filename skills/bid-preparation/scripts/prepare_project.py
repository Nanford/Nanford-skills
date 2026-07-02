"""Create a bid project workspace from tender files and evidence directories.

INPUT: project root, project name, tender file paths, evidence material paths.
OUTPUT: bid-projects/<project>/ directory and analysis/project-intake.md.
POS: Stage 0 intake helper for the bid-preparation skill.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path


REQUIRED_DIRS = [
    "source",
    "analysis",
    "analysis/extracted-text",
    "output/商务文件",
    "output/技术文件",
    "output/资格证明文件",
    "review",
]


def safe_project_slug(project_name: str) -> str:
    normalized = re.sub(r'[<>:"/\\|?*\r\n\t]+', "-", project_name).strip(" .-")
    return normalized or "未命名投标项目"


def resolve_paths(paths: list[Path]) -> list[Path]:
    resolved = []
    for path in paths:
        real_path = path.expanduser().resolve()
        if not real_path.exists():
            raise FileNotFoundError(f"输入路径不存在: {real_path}")
        resolved.append(real_path)
    return resolved


def unique_project_dir(root: Path, project_name: str) -> Path:
    base_dir = root / "bid-projects" / f"{safe_project_slug(project_name)}-{datetime.now():%Y%m%d}"
    if not base_dir.exists():
        return base_dir
    for index in range(2, 100):
        candidate = Path(f"{base_dir}-{index:02d}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"项目目录已存在且无法生成唯一名称: {base_dir}")


def write_intake(project_dir: Path, tender_paths: list[Path], material_paths: list[Path]) -> Path:
    lines = [
        "# 项目输入登记",
        "",
        "## 招标文件",
        *[f"- `{path}`" for path in tender_paths],
        "",
        "## 资质与证明材料",
        *[f"- `{path}`" for path in material_paths],
        "",
        "## 处理边界",
        "- 招标文件、澄清、补遗和官方附件为最高优先级来源。",
        "- 承诺书和官方格式表不改写原文。",
        "- 未能从材料中证明的资质、人员、业绩和承诺不得写成已具备。",
    ]
    intake_path = project_dir / "analysis" / "project-intake.md"
    intake_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return intake_path


def copy_tenders(tender_paths: list[Path], source_dir: Path) -> list[Path]:
    copied = []
    for tender_path in tender_paths:
        target = source_dir / tender_path.name
        if tender_path.is_file():
            shutil.copy2(tender_path, target)
            copied.append(target)
        else:
            copied.append(tender_path)
    return copied


def prepare_project(
    root: Path,
    project_name: str,
    tender_paths: list[Path],
    material_paths: list[Path],
    copy_sources: bool,
) -> dict:
    root = root.expanduser().resolve()
    tenders = resolve_paths(tender_paths)
    materials = resolve_paths(material_paths)
    project_dir = unique_project_dir(root, project_name)
    for relative_dir in REQUIRED_DIRS:
        (project_dir / relative_dir).mkdir(parents=True, exist_ok=True)
    source_refs = copy_tenders(tenders, project_dir / "source") if copy_sources else tenders
    intake_path = write_intake(project_dir, source_refs, materials)
    return {
        "project_dir": str(project_dir),
        "intake": str(intake_path),
        "tender_files": [str(path) for path in source_refs],
        "material_paths": [str(path) for path in materials],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a bid project workspace.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root.")
    parser.add_argument("--project-name", required=True, help="Project name used for output folder.")
    parser.add_argument("--tender", type=Path, action="append", required=True, help="Tender file path.")
    parser.add_argument("--materials", type=Path, action="append", required=True, help="Evidence file or directory.")
    parser.add_argument("--no-copy-sources", action="store_true", help="Reference tender files without copying.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = prepare_project(
        root=args.root,
        project_name=args.project_name,
        tender_paths=args.tender,
        material_paths=args.materials,
        copy_sources=not args.no_copy_sources,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
