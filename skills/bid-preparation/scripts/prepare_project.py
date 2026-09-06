"""Create a bid project workspace from tender files and evidence directories.

INPUT: project root, project name, tender file paths, evidence material paths,
       optional response-sample paths (历史中标/响应文件样本 PDF/DOCX),
       generation scope (full = 商务+技术完整包, technical-only = 仅技术部分),
       optional P1 project_type / delivery_mode (可阶段2再确认),
       optional P3 procurement_system (gov/enterprise) / procurement_mode (采购方式).
OUTPUT: bid-projects/<project>/ directory, analysis/project-intake.md
        (记录生成范围、样本、类型/递交方式/采购体系与方式), and project-state.json
        (断点续作：阶段0完成；technical-only 时阶段4跳过；writing + P1/P3 路由字段).
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

# 生成范围：使用前必须征询用户；未明确选择时默认推荐 full 并请用户确认
SCOPE_LABELS = {
    "full": "完整投标文件（商务部分+技术部分+导航表+组装成品）",
    "technical-only": "仅技术部分（技术响应偏离表+技术方案+服务承诺）",
}

# P1 项目类型 / 递交方式（详见 references/project-type-routing.md）
PROJECT_TYPE_LABELS = {
    "service_ops": "维保/运维服务",
    "it_build": "IT建设/集成",
    "hybrid_retrofit": "软硬改造",
    "hardware_supply": "硬件采购安装",
    "construction_epc": "工程总承包/施工（需施工资质与建造师）",
    "simplified": "简化/创新采购",
    "unset": "待阶段2判定",
}
DELIVERY_MODE_LABELS = {
    "paper": "纸质为主",
    "electronic": "全电子标",
    "hybrid": "纸电并行",
    "unset": "待阶段2判定",
}

# P3 采购体系 / 采购方式（详见 references/procurement-mode-routing.md）
# 体系决定法律框架与政策性得分项；方式决定流程、术语与报价轮次。
PROCUREMENT_SYSTEM_LABELS = {
    "gov": "政府采购（政采法体系，须做政策核对表）",
    "enterprise": "企业/国企自主采购",
    "unset": "待阶段2判定",
}
PROCUREMENT_MODE_LABELS = {
    "open_tender": "公开招标",
    "invited_tender": "邀请招标",
    "competitive_consultation": "竞争性磋商（两阶段报价）",
    "competitive_negotiation": "竞争性谈判（多轮报价）",
    "inquiry_single": "询价/单一来源",
    "unset": "待阶段2判定",
}

# P3-3 定标方式：评定分离要求投标文件拆成「评标部分」「定标部分」两本分别编制
AWARD_MODE_LABELS = {
    "standard": "常规（评标得分排序定中标人）",
    "evaluation_separated": "评定分离（评标入围+定标委员会票决，投标文件分两本）",
    "unset": "待阶段2判定",
}

# 磋商谈判类：术语须由「投标」体系切换为「响应」体系，且报价分两阶段
CONSULTATION_MODES = {"competitive_consultation", "competitive_negotiation", "inquiry_single"}


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


def _procurement_notes(
    procurement_system: str,
    procurement_mode: str,
    award_mode: str = "unset",
    project_type: str = "unset",
) -> list[str]:
    """按采购体系/方式/定标方式给出阶段2必做动作提示，写进 intake 让新会话一眼看到。"""
    notes: list[str] = []
    if procurement_system == "gov":
        notes.append(
            "- **政府采购必做**：阶段2 建 `analysis/gov-policy-checklist.md`"
            "（价格扣除测算/强制节能/信用查询/资格三段式），见 references/gov-procurement-policy.md"
        )
    if procurement_mode in CONSULTATION_MODES:
        notes.append(
            "- **磋商谈判类必做**：阶段2 建 `analysis/consultation-strategy.md`"
            "（两阶段报价+术语切换+可变动条款），见 references/procurement-mode-routing.md"
        )
    if award_mode == "evaluation_separated":
        notes.append(
            "- **评定分离必做**：阶段2 建 `analysis/award-separation-plan.md`；"
            "**投标文件须拆成「评标部分」「定标部分」两本分别编制并分别上传**；"
            "**立即锁定答辩人档期（缺席即弃权）**，见 references/award-separation-defense.md"
        )
    if project_type == "construction_epc":
        notes.append(
            "- **工程总承包必做**：按 references/sample-construction-epc.md 写骨架；"
            "核对建造师/安全B证/注册建筑师等人证绑定（以投标登记选取的人为准）；"
            "接受联合体时填 `analysis/consortium-plan.md`"
        )
    if procurement_system == "unset" or procurement_mode == "unset":
        notes.append("- 采购体系/方式未定：阶段2 读采购人性质与文件封面后判定并请用户确认")
    return notes


def write_intake(
    project_dir: Path,
    tender_paths: list[Path],
    material_paths: list[Path],
    scope: str,
    sample_paths: list[Path] | None = None,
    project_type: str = "unset",
    delivery_mode: str = "unset",
    procurement_system: str = "unset",
    procurement_mode: str = "unset",
    award_mode: str = "unset",
) -> Path:
    sample_paths = sample_paths or []
    lines = [
        "# 项目输入登记",
        "",
        "## 生成范围（使用前已征询用户）",
        f"- {SCOPE_LABELS[scope]}",
        "",
        "## 采购体系与采购方式（P3，可阶段2修订）",
        f"- 采购体系：`{procurement_system}` — "
        f"{PROCUREMENT_SYSTEM_LABELS.get(procurement_system, procurement_system)}",
        f"- 采购方式：`{procurement_mode}` — "
        f"{PROCUREMENT_MODE_LABELS.get(procurement_mode, procurement_mode)}",
        f"- 定标方式：`{award_mode}` — {AWARD_MODE_LABELS.get(award_mode, award_mode)}",
        *_procurement_notes(procurement_system, procurement_mode, award_mode, project_type),
        "",
        "## 项目类型与递交方式（P1，可阶段2修订）",
        f"- 项目类型：`{project_type}` — {PROJECT_TYPE_LABELS.get(project_type, project_type)}",
        f"- 递交方式：`{delivery_mode}` — {DELIVERY_MODE_LABELS.get(delivery_mode, delivery_mode)}",
        "- 详细画像：阶段2填写 `analysis/project-profile.md`",
        "",
        "## 招标文件",
        *[f"- `{path}`" for path in tender_paths],
        "",
        "## 响应文件样本（结构/详略/版式参考，可选但强烈建议）",
    ]
    if sample_paths:
        lines.extend(f"- `{path}`" for path in sample_paths)
    else:
        lines.append("- （未登记；若用户后续提供历史中标/响应样本，须补登并在阶段1提取）")
    lines.extend([
        "",
        "## 资质与证明材料",
        *[f"- `{path}`" for path in material_paths],
        "",
        "## 处理边界",
        "- 招标文件、澄清、补遗和官方附件为最高优先级来源。",
        "- 用户提供的响应文件样本（PDF/DOCX）为结构、详略、版式的强参考，须认真提取并对照；不抄袭其商务事实与承诺数字。",
        "- 承诺书和官方格式表不改写原文。",
        "- 未能从材料中证明的资质、人员、业绩和承诺不得写成已具备。",
        "- 写作须先大纲确认、再逐章/逐件确认，禁止一次灌完整稿。",
        "- 按项目类型路由写作骨架（service_ops/it_build/hybrid_retrofit/hardware_supply/simplified），禁止一律套服务库长方案。",
        "- 电子标：内容稿与平台递交包分离，见 e-bid-delivery-checklist。",
        "- 先定采购体系与方式，再定项目类型：磋商/谈判类须全文用「响应文件/供应商/成交」，不得混用「投标/中标」。",
        "- 政府采购：中小企业声明函等政策性文件不交即丧失价格扣除，属零成本失分，必须核对。",
    ])
    intake_path = project_dir / "analysis" / "project-intake.md"
    intake_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return intake_path


def default_writing_state(scope: str) -> dict:
    return {
        "business_outline_confirmed": scope == "technical-only",
        "technical_outline_confirmed": False,
        "business_sections_done": [],
        "technical_sections_done": [],
        "current_part": None,
        "current_section": None,
    }


def write_initial_state(
    project_dir: Path,
    project_name: str,
    scope: str,
    project_type: str = "unset",
    delivery_mode: str = "unset",
    procurement_system: str = "unset",
    procurement_mode: str = "unset",
    award_mode: str = "unset",
) -> Path:
    """初始化断点续作状态文件：新会话通过 project_status.py 读取，知道做到哪一步。"""
    stages = {str(stage): "pending" for stage in range(8)}
    stages["0"] = "done"
    if scope == "technical-only":
        stages["4"] = "skipped"
    state = {
        "project_name": project_name,
        "scope": scope,
        "project_type": project_type,
        "delivery_mode": delivery_mode,
        "procurement_system": procurement_system,
        "procurement_mode": procurement_mode,
        "award_mode": award_mode,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "stages": stages,
        "writing": default_writing_state(scope),
    }
    state_path = project_dir / "project-state.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state_path


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


def prepare_project(
    root: Path,
    project_name: str,
    tender_paths: list[Path],
    material_paths: list[Path],
    copy_sources: bool,
    scope: str = "full",
    sample_paths: list[Path] | None = None,
    project_type: str = "unset",
    delivery_mode: str = "unset",
    procurement_system: str = "unset",
    procurement_mode: str = "unset",
    award_mode: str = "unset",
) -> dict:
    if scope not in SCOPE_LABELS:
        raise ValueError(f"未知的生成范围: {scope}（可选: {', '.join(SCOPE_LABELS)}）")
    if project_type not in PROJECT_TYPE_LABELS:
        raise ValueError(f"未知项目类型: {project_type}（可选: {', '.join(PROJECT_TYPE_LABELS)}）")
    if delivery_mode not in DELIVERY_MODE_LABELS:
        raise ValueError(f"未知递交方式: {delivery_mode}（可选: {', '.join(DELIVERY_MODE_LABELS)}）")
    if procurement_system not in PROCUREMENT_SYSTEM_LABELS:
        raise ValueError(
            f"未知采购体系: {procurement_system}（可选: {', '.join(PROCUREMENT_SYSTEM_LABELS)}）"
        )
    if procurement_mode not in PROCUREMENT_MODE_LABELS:
        raise ValueError(
            f"未知采购方式: {procurement_mode}（可选: {', '.join(PROCUREMENT_MODE_LABELS)}）"
        )
    if award_mode not in AWARD_MODE_LABELS:
        raise ValueError(f"未知定标方式: {award_mode}（可选: {', '.join(AWARD_MODE_LABELS)}）")
    root = root.expanduser().resolve()
    tenders = resolve_paths(tender_paths)
    materials = resolve_paths(material_paths) if material_paths else []
    samples = resolve_paths(sample_paths) if sample_paths else []
    project_dir = unique_project_dir(root, project_name)
    for relative_dir in REQUIRED_DIRS:
        (project_dir / relative_dir).mkdir(parents=True, exist_ok=True)
    sample_dir = project_dir / "source" / "response-samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    if copy_sources:
        source_refs = copy_files(tenders, project_dir / "source")
        sample_refs = copy_files(samples, sample_dir) if samples else []
    else:
        source_refs = tenders
        sample_refs = samples
    intake_path = write_intake(
        project_dir,
        source_refs,
        materials,
        scope,
        sample_refs,
        project_type=project_type,
        delivery_mode=delivery_mode,
        procurement_system=procurement_system,
        procurement_mode=procurement_mode,
        award_mode=award_mode,
    )
    state_path = write_initial_state(
        project_dir,
        project_name,
        scope,
        project_type=project_type,
        delivery_mode=delivery_mode,
        procurement_system=procurement_system,
        procurement_mode=procurement_mode,
        award_mode=award_mode,
    )
    return {
        "project_dir": str(project_dir),
        "intake": str(intake_path),
        "state": str(state_path),
        "scope": scope,
        "project_type": project_type,
        "delivery_mode": delivery_mode,
        "procurement_system": procurement_system,
        "procurement_mode": procurement_mode,
        "award_mode": award_mode,
        "required_checklists": _procurement_notes(
            procurement_system, procurement_mode, award_mode, project_type
        ),
        "tender_files": [str(path) for path in source_refs],
        "sample_files": [str(path) for path in sample_refs],
        "material_paths": [str(path) for path in materials],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a bid project workspace.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root.")
    parser.add_argument("--project-name", required=True, help="Project name used for output folder.")
    parser.add_argument("--tender", type=Path, action="append", required=True, help="Tender file path.")
    parser.add_argument(
        "--materials",
        type=Path,
        action="append",
        default=[],
        help="Evidence file or directory (可重复).",
    )
    parser.add_argument(
        "--sample",
        type=Path,
        action="append",
        default=[],
        help="响应文件样本（历史中标/响应 PDF或DOCX，可重复）；结构/详略/版式强参考.",
    )
    parser.add_argument("--no-copy-sources", action="store_true", help="Reference tender files without copying.")
    parser.add_argument(
        "--scope",
        choices=sorted(SCOPE_LABELS),
        default="full",
        help="生成范围：full=商务+技术完整包（默认推荐），technical-only=仅技术部分.",
    )
    parser.add_argument(
        "--project-type",
        choices=sorted(PROJECT_TYPE_LABELS),
        default="unset",
        help="P1 项目类型；unset=阶段2再判定.",
    )
    parser.add_argument(
        "--delivery-mode",
        choices=sorted(DELIVERY_MODE_LABELS),
        default="unset",
        help="P1 递交方式：paper/electronic/hybrid；unset=阶段2再判定.",
    )
    parser.add_argument(
        "--procurement-system",
        choices=sorted(PROCUREMENT_SYSTEM_LABELS),
        default="unset",
        help="P3 采购体系：gov=政府采购（须做政策核对表）/enterprise=企业自主采购；unset=阶段2再判定.",
    )
    parser.add_argument(
        "--procurement-mode",
        choices=sorted(PROCUREMENT_MODE_LABELS),
        default="unset",
        help="P3 采购方式：open_tender/invited_tender/competitive_consultation/"
        "competitive_negotiation/inquiry_single；unset=阶段2再判定.",
    )
    parser.add_argument(
        "--award-mode",
        choices=sorted(AWARD_MODE_LABELS),
        default="unset",
        help="P3 定标方式：standard/evaluation_separated（评定分离须拆两本投标文件）；unset=阶段2再判定.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = prepare_project(
        root=args.root,
        project_name=args.project_name,
        tender_paths=args.tender,
        material_paths=args.materials or [],
        copy_sources=not args.no_copy_sources,
        scope=args.scope,
        sample_paths=args.sample or [],
        project_type=args.project_type,
        delivery_mode=args.delivery_mode,
        procurement_system=args.procurement_system,
        procurement_mode=args.procurement_mode,
        award_mode=args.award_mode,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
