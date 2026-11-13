"""Index the company resource materials of a qingtian-bid project (stage 3) and start the resource card.

迁移来源见 CHANGELOG《脚本来源》，按设计稿 v1 第 3b 步改造：
- 只在项目里工作：编目 project-state.json 里登记的资源路径（开工 --resources 或
  project_status.py --add-resource），不再接受任意目录；
- 分类改为施组要用的四类：管理岗位与持证、机械设备、劳动力、物资，其余记"其他"；
- 每个文件记 sha256，资源卡确认后文件被改动、补登或重新编目，确认即失效；
- 机械、劳动力、物资和其他类文件把文字提取到 analysis/resource-text/ 供核对；人员类文件
  （花名册、证书）不落盘，按原文件核对或用 --show 临时查看（决策 3b-1A：少存一份个人信息）；
- 不按文件数判资料空壳：资源卡逐条指回编目文件、缺什么写进
  gaps：文件数够不说明资料够，缺口逐节写明后 R8 照样只许出大纲；
- 登记路径可以是相对路径（建项目时自动登记的 公司资料/），按项目目录解析；两处登记里编目路径相同的
  文件会让资源卡指错文件，直接报错请用户改名；
- 文件名（不含扩展名）以"证"结尾的，不管放在哪个子目录都按人员资料处理、不落盘文字。

INPUT: <project>/project-state.json (resources: [{path}], files or folders; relative paths resolve
       against the project directory; the skill never copies them); the files under those paths;
       templates/resource-card.json.
OUTPUT: analysis/material-index.json/md; analysis/resource-text/<文件>.txt for non-personnel files;
        analysis/resource-card.json skeleton (with gaps for empty categories) when it does not exist yet.
POS: stage-3 helper of qingtian-bid. Everything stays on the local disk (R26).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from extract_text import extract_one, file_sha256, output_name
from fact_resource_cards import RESOURCE_CARD_FILE, SECTIONS, card_template
from project_cards import MATERIAL_INDEX_FILE, cell, load_json, load_project


# 说明.md/DIRECTORY.md/README.md 是目录用途占位说明，不是公司资料，编目时排除
IGNORED_NAMES = {"Thumbs.db", ".DS_Store", "说明.md", "DIRECTORY.md", "README.md"}
# 按编目路径关键词分类。人员类排最前：路径沾上人员、证书、花名册字样的（如"特种设备操作人员证书"
# "工人花名册"）一律按人员资料处理、不落盘文字，宁可归错类也不多存一份个人信息（决策 3b-1A）
CATEGORY_RULES = [
    ("managers", ("人员", "岗位", "项目部", "建造师", "安全员", "施工员", "质检员", "花名册", "管理人员", "证书")),
    ("machinery", ("机械", "设备", "塔吊", "塔式起重机", "起重", "机具", "施工机具")),
    ("labor", ("劳动力", "劳务", "工人", "班组", "工种")),
    ("materials", ("物资", "材料", "供应商", "周转", "模板", "脚手架")),
]
# 证件按文件名认、不看目录：操作证、职称证放错子目录（如塔吊司机操作证放进 机械设备/）也不落盘文字。
# 代价是材料合格证、供应商资质证这类不涉及个人的证件也不提取，按原文件或 --show 核对（用户 2026-11-09 选 A）
CERT_SUFFIX = "证"
TEXT_DIR = "analysis/resource-text"


def classify_material(path: Path) -> str:
    if path.stem.strip().endswith(CERT_SUFFIX):
        return "managers"
    searchable = str(path).lower()
    for category, keywords in CATEGORY_RULES:
        if any(keyword in searchable for keyword in keywords):
            return category
    return "other"


def category_label(category: str) -> str:
    return SECTIONS[category][0] if category in SECTIONS else "其他"


def list_material_files(material_root: Path) -> list[Path]:
    if material_root.is_file():
        return [material_root]
    files = [path for path in material_root.rglob("*")
             if path.is_file() and path.name not in IGNORED_NAMES and not path.name.startswith("~$")]
    return sorted(files, key=lambda item: str(item).lower())


def resource_root(project_dir: Path, stored: object) -> Path:
    """登记的路径：相对路径按项目目录解析（项目里的 公司资料/），绝对路径原样。"""
    path = Path(str(stored or "")).expanduser()
    return (path if path.is_absolute() else project_dir / path).resolve()


def registered_roots(project_dir: Path, state: dict) -> list[Path]:
    roots = []
    for entry in state.get("resources") or []:
        root = resource_root(project_dir, entry.get("path"))
        if not root.exists():
            raise ValueError(f"登记的公司资源资料不存在: {root}（改了位置就用 --add-resource 重新登记）")
        roots.append(root)
    return roots


def material_file_count(project_dir: Path, state: dict) -> int:
    """登记处现有几个资料文件（说明文件不算）；给进度摘要用，登记处不存在的跳过，不报错。"""
    roots = (resource_root(project_dir, entry.get("path")) for entry in state.get("resources") or [])
    return sum(len(list_material_files(root)) for root in roots if root.exists())


def require_unique_paths(records: list[dict]) -> None:
    """资源卡的 file 写编目路径；两个文件编目路径相同，资源卡就分不清指的是哪一个。"""
    seen: dict[str, str] = {}
    for record in records:
        earlier = seen.setdefault(record["relative_path"], record["path"])
        if earlier != record["path"]:
            raise ValueError(f"编目路径重复：{record['relative_path']}（{earlier} 和 {record['path']}），"
                             "改一个文件名或文件夹名后再编目")


def extract_record_text(path: Path, category: str, project_dir: Path, used: set[str]) -> dict:
    """非人员类文件提取文字供核对；提取不了的只记原因，不阻断（资源卡按原文件核对）。"""
    if category == "managers":
        return {"text": None, "status": "not_saved", "reason": "人员资料不落盘（决策 3b-1A），按原文件或 --show 核对"}
    try:
        text, status, reason = extract_one(path)
    except Exception as exc:  # 公司资料五花八门（照片、加密 PDF），pypdf 等抛什么都有；记原因，不中断整批编目
        return {"text": None, "status": "failed", "reason": str(exc)}
    target = project_dir / TEXT_DIR / output_name(path, used)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text((text or "").strip() + "\n", encoding="utf-8")
    return {"text": target.relative_to(project_dir).as_posix(), "status": status, "reason": reason}


def material_record(path: Path, root: Path, project_dir: Path, used: set[str]) -> dict:
    # 编目路径从登记的文件夹名起算；分类也只看这一段，登记文件夹上层目录的名字不算数
    relative = Path(root.name) / path.relative_to(root) if root.is_dir() else Path(path.name)
    category = classify_material(relative)
    return {
        "name": path.name,
        "category": category,
        "path": str(path),
        "relative_path": relative.as_posix(),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
        **extract_record_text(path, category, project_dir, used),
    }


def write_markdown(records: list[dict], project_dir: Path) -> Path:
    lines = ["# 公司资源编目", "",
             "> 资源卡每条的 file 写这里的\"编目路径\"，locator 写页码或工作表和行号。人员类文件不落盘文字。", "",
             "| 序号 | 类别 | 编目路径 | 文字 | 状态 |", "|---:|---|---|---|---|"]
    for index, record in enumerate(records, start=1):
        status = record["status"] + (f"：{record['reason']}" if record.get("reason") else "")
        lines.append(f"| {index} | {category_label(record['category'])} | `{record['relative_path']}` | "
                     f"{cell(record.get('text'))} | {cell(status)} |")
    if not records:
        lines.append("| — | — | 没有登记公司资源资料 | — | — |")
    target = project_dir / "analysis" / "material-index.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def start_resource_card(project_dir: Path, records: list[dict]) -> str | None:
    """资源卡不存在时出骨架：某类一个文件都没有，就先在 gaps 里写明（R8）。已有资源卡不动。"""
    target = project_dir / RESOURCE_CARD_FILE
    if target.exists():
        return None
    card = card_template("resource-card.json")
    present = {record["category"] for record in records}
    card["gaps"] = [{"section": section, "text": f"公司资源资料里没有{SECTIONS[section][0]}资料，请用户补充"}
                    for section in SECTIONS if section not in present]
    target.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def index_project(project_dir: Path) -> dict:
    project_dir, state = load_project(project_dir)
    used: set[str] = set()
    records = [material_record(path, root, project_dir, used)
               for root in registered_roots(project_dir, state) for path in list_material_files(root)]
    require_unique_paths(records)
    index = {"roots": [str(item.get("path")) for item in state.get("resources") or []], "materials": records}
    (project_dir / MATERIAL_INDEX_FILE).write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {category_label(key): sum(1 for record in records if record["category"] == key)
              for key in (*SECTIONS, "other")}
    return {"index": str(project_dir / MATERIAL_INDEX_FILE), "markdown": str(write_markdown(records, project_dir)),
            "counts": counts, "resource_card_started": start_resource_card(project_dir, records)}


def show_material(project_dir: Path, file: str) -> str:
    """临时提取一个编目文件的文字到标准输出，不落盘；人员资料就用这个核对。"""
    project_dir, _ = load_project(project_dir)
    index = load_json(project_dir / MATERIAL_INDEX_FILE, "公司资源编目")
    wanted = file.replace("\\", "/")
    record = next((item for item in index.get("materials") or []
                   if wanted in (item["relative_path"], item["path"].replace("\\", "/"))), None)
    if record is None:
        raise ValueError(f"编目里没有这个文件: {file}（先运行 --project 编目）")
    text, status, reason = extract_one(Path(record["path"]))
    return text if status == "ok" else f"（{status}：{reason}）\n{text}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="编目项目登记的公司资源资料，出资源卡骨架。")
    parser.add_argument("--project", type=Path, required=True, help="项目目录。")
    parser.add_argument("--show", metavar="编目路径", help="临时查看一个编目文件的文字，不落盘。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = show_material(args.project, args.show) if args.show else \
            json.dumps(index_project(args.project), ensure_ascii=False, indent=2)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"公司资源编目失败: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
