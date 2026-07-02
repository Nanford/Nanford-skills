"""Index local company evidence materials for bid requirement matching.

INPUT: company-library or another local material file/directory.
OUTPUT: analysis/material-index.md/json.
POS: Stage 3 evidence matching helper for the bid-preparation skill.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


# 说明.md/DIRECTORY.md/README.md 是目录用途占位说明，不是投标证明材料，索引时排除。
IGNORED_NAMES = {"Thumbs.db", ".DS_Store", "说明.md", "DIRECTORY.md", "README.md"}


CATEGORY_RULES = [
    # 体系认证先于人员证书，避免 ISO9001证书 被泛化为人员证书。
    ("体系认证", ("认证", "iso", "cmmi", "itss", "体系")),
    ("人员证书", ("人员", "社保", "证书", "pmp", "项目经理")),
    ("业绩证明", ("业绩", "合同", "验收", "发票", "案例")),
    ("财务资料", ("财务", "审计", "银行", "纳税", "资信")),
    ("产品资料", ("产品", "白皮书", "手册", "说明书")),
    ("技术方案素材", ("方案", "架构", "模板", "实施", "运维")),
    ("商务资质", ("营业执照", "资质", "许可证", "高新", "软件企业")),
]


def classify_material(path: Path) -> str:
    searchable = str(path).lower()
    for category, keywords in CATEGORY_RULES:
        if any(keyword.lower() in searchable for keyword in keywords):
            return category
    if "business" in searchable:
        return "商务材料"
    if "technical" in searchable:
        return "技术材料"
    return "其他材料"


def list_material_files(material_root: Path) -> list[Path]:
    if material_root.is_file():
        return [material_root]
    files = []
    for path in material_root.rglob("*"):
        if path.is_file() and path.name not in IGNORED_NAMES and not path.name.startswith("~$"):
            files.append(path)
    return sorted(files, key=lambda item: str(item).lower())


def material_record(path: Path, base_dir: Path) -> dict:
    try:
        relative_path = path.relative_to(base_dir)
    except ValueError:
        relative_path = path
    return {
        "name": path.name,
        "category": classify_material(path),
        "path": str(path),
        "relative_path": str(relative_path),
        "suffix": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
    }


def write_markdown(records: list[dict], output_dir: Path) -> Path:
    lines = ["# 材料索引", "", "| 序号 | 类别 | 文件名 | 路径 | 大小 |", "|---:|---|---|---|---:|"]
    for index, record in enumerate(records, start=1):
        lines.append(
            f"| {index} | {record['category']} | {record['name']} | `{record['relative_path']}` | {record['size_bytes']} |"
        )
    target = output_dir / "material-index.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def index_materials(material_root: Path, output_dir: Path) -> dict:
    material_root = material_root.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    files = list_material_files(material_root)
    records = [material_record(path, material_root) for path in files]
    markdown_path = write_markdown(records, output_dir)
    json_path = output_dir / "material-index.json"
    result = {"material_root": str(material_root), "materials": records, "markdown": str(markdown_path)}
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index company evidence materials.")
    parser.add_argument("--materials", type=Path, required=True, help="Material file or directory.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Analysis output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = index_materials(args.materials, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
