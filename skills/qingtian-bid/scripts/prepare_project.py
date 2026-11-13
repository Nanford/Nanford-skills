"""Create a qingtian-bid project workspace and register the four kickoff answers (stage 0).

迁移来源见 CHANGELOG《脚本来源》，按设计稿 v1 第十节改造：
开工五问改为开工四问（招标文件、响应样本、公司资源资料、成品格式）；生成范围固定为
施工组织设计 + 提交前清单，不再询问；项目画像和评审轨道留到阶段 2 判定；成品字体
升级为整套成品格式（预设 + 自定义字段），开工时直接出格式样张，用户确认后才锁定。

公司资料目录：建项目时按 templates/公司资料/ 生成 公司资料/ 和四个子目录（项目管理人员、机械设备、劳动力、
物资），每个目录一份说明，告诉用户这次投标的资料放哪、放什么；这个目录自动登记为公司资源（记相对路径，
项目整体搬走也能编目）。脚本不复制公司资料，资料由用户自己放进来；放在别处的用 --resources 原地登记。

INPUT: workspace root, project name, tender files (招标文件、补遗、工程量清单), drawings the user
       declared as drawings (决策 2A), optional response samples (R25), optional company resource
       paths (管理岗位与持证类别、机械设备、劳动力、主要物资), format preset code and 字段=值
       settings; templates/公司资料/ (说明文件); Word/WPS for the PDF sample; optional --plain-sample.
OUTPUT: bid-projects/<project>-<date>/ with source/ (含 drawings/、response-samples/), analysis/,
        analysis/format/ (格式样张、确认卡), output/实施方案/, review/, 公司资料/ (四个子目录和说明);
        analysis/project-intake.md; project-state.json with stage 0 in progress, the kickoff format
        parked as format_review (not yet document_format), the sources list (path + kind) that stage 1
        must extract, and the resources list (公司资料 relative, other paths absolute, none copied)
        that stage 3 indexes. New projects require the verified PDF at delivery.
POS: stage-0 intake helper for qingtian-bid. Everything stays on the local disk (R26).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

from docx_font_profiles import (
    FIELD_LABELS,
    apply_format_settings,
    load_catalog,
    parse_assignment,
    preset_format,
)
from format_state import save_state, with_blind_mode_defaults
from render_format_sample import custom_fields, propose_review


REQUIRED_DIRS = [
    "source",
    "source/drawings",
    "source/response-samples",
    "analysis",
    "analysis/extracted-text",
    "analysis/format",
    "output/实施方案",
    "review",
]
COMPANY_DIR = "公司资料"  # 子目录名是编目分类的关键词（index_materials.CATEGORY_RULES），改名要同步
COMPANY_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / COMPANY_DIR
STAGE_COUNT = 9  # 阶段 0～8，见 SKILL.md 流程表
# 临时措辞（v2.0-dev）：第 3～5 步接入商务文件和定标部分后改写，改动范围全文搜“本版本暂不生成”。
SCOPE_TEXT = "施工组织设计 + 提交前清单，含完整 PDF（商务文件、报价和评定分离项目的定标部分由用户另行编制）"


def safe_project_slug(project_name: str) -> str:
    normalized = re.sub(r'[<>:"/\\|?*\r\n\t]+', "-", project_name).strip(" .-")
    return normalized or "未命名施组项目"


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


def copy_files(file_paths: list[Path], target_dir: Path) -> list[Path]:
    copied = []
    for file_path in file_paths:
        target = target_dir / file_path.name
        if file_path.is_file():
            shutil.copy2(file_path, target)
            copied.append(target)
        else:
            copied.append(file_path)
    return copied


def install_company_dir(project_dir: Path) -> Path:
    """按模板建 公司资料/ 和说明文件；已有的文件不覆盖，用户放进去的资料不会被动到。"""
    target_root = project_dir / COMPANY_DIR
    for template in sorted(COMPANY_TEMPLATE.rglob("*")):
        target = target_root / template.relative_to(COMPANY_TEMPLATE)
        if template.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template, target)
    return target_root


def kickoff_format(preset: str | None, settings: dict, *, plain_sample: bool = False) -> dict:
    """先在建目录之前校验格式，非法值不留下半个项目。"""
    record = preset_format(preset)
    if preset is None and not plain_sample:
        record = apply_format_settings(record, {
            "margin_top_cm": 2.5, "margin_bottom_cm": 2, "margin_left_cm": 2, "margin_right_cm": 2,
            "heading_page_breaks": False, "require_toc": False,
        }, "框式主样张默认")
    if settings:
        record = apply_format_settings(record, with_blind_mode_defaults(settings),
                                       f"开工所选，用户自定义（{date.today().isoformat()}）")
    return record


def path_lines(paths: list[Path], missing: str) -> list[str]:
    return [f"- `{path}`" for path in paths] if paths else [f"- {missing}"]


def write_intake(project_dir: Path, tenders: list[Path], drawings: list[Path], samples: list[Path],
                 company_dir: Path, resources: list[Path], record: dict, sample: dict) -> Path:
    preset = load_catalog()["presets"][record["preset"]]
    changed = custom_fields(record)
    lines = [
        "# 项目输入登记（qingtian-bid）",
        "",
        "## 范围（开工时告知用户，不再让用户选）",
        f"- {SCOPE_TEXT}",
        "",
        "## 招标文件（含补遗、澄清、工程量清单）",
        *path_lines(tenders, "（缺失：没有招标文件不得继续）"),
        "",
        "## 图纸（用户声明为图纸；提取不到文字时按图号人工读取，不触发 R9 硬停）",
        *path_lines(drawings, "（未登记；之后提供的用 project_status.py --add-source --kind drawing 补登）"),
        "",
        "## 响应样本（R25，结构、详略、版式参考）",
        *path_lines(samples, "（未登记；用户之后提供的，补登后在阶段 1 提取）"),
        "",
        "## 公司资源资料（R7、R8：管理岗位与持证类别、机械设备、劳动力、主要物资）",
        f"- `{company_dir}`：本项目的公司资料目录，已登记。这次投标要用的资料按子目录放进去，"
        "放什么见各目录的 说明.md。",
        *[f"- `{path}`（放在别处，原地登记，不复制）" for path in resources],
        "- 阶段 3 建资源卡前要放齐；缺哪一类，资源卡记缺口，施组只出大纲（R8）。",
        "",
        "## 成品格式（开工所选，待用户看样张确认）",
        f"- 基础预设：{record['preset']} {preset['name']}",
        f"- 与预设不同的字段：{'、'.join(FIELD_LABELS[key] for key in changed) if changed else '无'}",
        f"- 样张：{sample['pdf'] or sample['docx']}",
        f"- 确认卡：{sample['card']}",
        "- 用户确认前，格式只登记为待确认，生成器和校验器拒绝出稿。",
        "- 最终格式以 project-state.json 的 document_format 为准；阶段 2 招标文件（含补遗）规定的字段覆盖开工所选（D7）。",
        "",
        "## 留到阶段 2 判定",
        "- 评审轨道：T-AI、T-暗标、T-合格、T-定档，判不清就硬停。",
        "- 青天启用情况和规则依据范围：按招标文件原文判，判不清就硬停。",
        "- 工程类别：主类别取占比最大的工程类型，不限导则 9 类；没有类别知识卡的只按招标文件和红线写。",
        "",
        "## 处理边界",
        "- 招标文件、补遗、澄清是最高优先级来源；响应样本只参考结构、详略和版式，不抄其事实和承诺数字。",
        "- 所有材料只在本机处理，不外传（R26）。",
        "- 机械、劳动力、物资和管理岗位只来自用户确认过的公司资源卡，不编造（R7、R8）。",
        "- 规则卡经用户确认前不写正文；大纲确认后逐项写，每项用户确认（R1）。",
        "",
    ]
    intake_path = project_dir / "analysis" / "project-intake.md"
    intake_path.write_text("\n".join(lines), encoding="utf-8")
    return intake_path


def project_relative(project_dir: Path, path: Path) -> str:
    """项目里的路径记相对路径，项目整体搬走也能用；项目外的记绝对路径。"""
    try:
        return path.relative_to(project_dir).as_posix()
    except ValueError:
        return str(path)


def source_entries(project_dir: Path, groups: list[tuple[list[Path], str]]) -> list[dict]:
    """阶段 1 按这份清单核对是否全部提取。"""
    return [{"path": project_relative(project_dir, path), "kind": kind} for paths, kind in groups for path in paths]


def write_initial_state(project_dir: Path, project_name: str, sources: list[dict],
                        resources: list[Path] | None = None) -> Path:
    """格式在用户确认样张前不进 document_format，阶段 0 保持进行中。公司资源资料只登记路径，
    脚本不复制（少存一份人员资料），阶段 3 由 index_materials.py 原地编目。"""
    stages = {str(stage): "pending" for stage in range(STAGE_COUNT)}
    stages["0"] = "in-progress"
    state = {
        "project_name": project_name,
        "skill": "qingtian-bid",
        "scope": SCOPE_TEXT,
        "require_pdf_delivery": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "stages": stages,
        "sources": sources,
        "resources": [{"path": project_relative(project_dir, path)} for path in resources or []],
        "format_selection": None,
        "tender_format": None,
        "format_history": [],
    }
    return save_state(project_dir, state)


def prepare_project(
    root: Path,
    project_name: str,
    tender_paths: list[Path],
    resource_paths: list[Path] | None = None,
    sample_paths: list[Path] | None = None,
    drawing_paths: list[Path] | None = None,
    copy_sources: bool = True,
    format_preset: str | None = None,
    format_settings: dict | None = None,
    export_pdf: bool = True,
    office: str = "auto",
    *,
    plain_sample: bool = False,
) -> dict:
    if not tender_paths:
        raise ValueError("没有招标文件不能开工：先向用户索取招标文件")
    record = kickoff_format(format_preset, format_settings or {}, plain_sample=plain_sample)
    tenders = resolve_paths(tender_paths)
    resources = resolve_paths(resource_paths or [])
    samples = resolve_paths(sample_paths or [])
    drawings = resolve_paths(drawing_paths or [])
    project_dir = unique_project_dir(root.expanduser().resolve(), project_name)
    for relative_dir in REQUIRED_DIRS:
        (project_dir / relative_dir).mkdir(parents=True, exist_ok=True)
    if copy_sources:
        tenders = copy_files(tenders, project_dir / "source")
        samples = copy_files(samples, project_dir / "source" / "response-samples")
        drawings = copy_files(drawings, project_dir / "source" / "drawings")
    company_dir = install_company_dir(project_dir)
    sources = source_entries(project_dir, [(tenders, "tender"), (drawings, "drawing"), (samples, "sample")])
    state_path = write_initial_state(project_dir, project_name, sources, [company_dir, *resources])
    sample = propose_review(project_dir, "kickoff", record, None, export_pdf, office, plain_sample=plain_sample)
    intake_path = write_intake(project_dir, tenders, drawings, samples, company_dir, resources, record, sample)
    return {
        "project_dir": str(project_dir),
        "intake": str(intake_path),
        "state": str(state_path),
        "scope": SCOPE_TEXT,
        "format_preset": record["preset"],
        "format_status": "待用户看样张确认",
        "sample_docx": sample["docx"],
        "sample_pdf": sample["pdf"],
        "format_card": sample["card"],
        "tender_files": [str(path) for path in tenders],
        "drawing_files": [str(path) for path in drawings],
        "sample_files": [str(path) for path in samples],
        "company_dir": str(company_dir),
        "resource_paths": [str(path) for path in resources],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="建 qingtian-bid 项目目录，登记开工四问并出格式样张。")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="工作区根目录，项目建在 bid-projects/ 下。")
    parser.add_argument("--project-name", required=True, help="项目名称，从招标文件封面核实。")
    parser.add_argument("--tender", type=Path, action="append", required=True,
                        help="招标文件、补遗、工程量清单；可重复。")
    parser.add_argument("--drawing", type=Path, action="append", default=[],
                        help="用户声明为图纸的文件（决策 2A）；招标文件正文、补遗、清单不得登记为图纸；可重复。")
    parser.add_argument("--sample", type=Path, action="append", default=[], help="响应样本（R25）；可重复。")
    parser.add_argument("--resources", type=Path, action="append", default=[],
                        help="放在项目公司资料目录以外的公司资源资料，原地登记；可重复。")
    parser.add_argument("--no-copy-sources", action="store_true", help="只登记招标文件和样本路径，不复制。")
    parser.add_argument("--format-preset", help="成品格式预设代号（F1～F5），不填用默认预设 F1。")
    parser.add_argument("--format-set", action="append", default=[], metavar="字段=值",
                        help="在预设上改个别字段，如 正文字号=小四；可重复。")
    parser.add_argument("--no-pdf", action="store_true", help="不调用 Word/WPS 导出样张 PDF。")
    parser.add_argument("--plain-sample", action="store_true", help="样张正文不使用分块线框，仍保留图表。")
    parser.add_argument("--office", choices=("auto", "word", "wps"), default="auto", help="导出 PDF 用哪个应用。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = dict(parse_assignment(item) for item in args.format_set)
        result = prepare_project(
            root=args.root,
            project_name=args.project_name,
            tender_paths=args.tender,
            resource_paths=args.resources,
            sample_paths=args.sample,
            drawing_paths=args.drawing,
            copy_sources=not args.no_copy_sources,
            format_preset=args.format_preset,
            format_settings=settings,
            export_pdf=not args.no_pdf,
            office=args.office,
            plain_sample=args.plain_sample,
        )
    except (OSError, ValueError) as exc:
        print(f"项目初始化失败: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
