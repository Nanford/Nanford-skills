"""
INPUT: vplib 各模块；命令行参数
OUTPUT: init / import / probe / stage / status / cost 子命令
POS: video-project 技能的唯一命令入口：项目建档、素材入库、阶段状态与费用账本。
     其他技能不改 project.json，由智能体在每步完成后调用本命令登记产物与状态。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from vplib.assets import AssetRequest, import_asset
from vplib.contracts import ASSET_KINDS, AUDIENCE_SEGMENTS, DEFAULT_PLATFORMS, PLATFORMS, RIGHTS_STATUSES, SHARED_STAGES, STAGE_STATUSES, VARIANT_STAGES
from vplib.costs import SETTLEMENT_STATUSES, CostEntry, add_cost_entry, summarize_costs
from vplib.fsutil import DataFileError, describe_file
from vplib.manifest import load_manifest, save_manifest, update_stage
from vplib.media import ToolError, probe_media
from vplib.paths import PathSafetyError, project_dir, resolve_inside, to_project_relative
from vplib.project import INPUT_TYPES, ProjectRequest, init_project


def existing_project(project_id: str) -> Path:
    root = project_dir(project_id)
    if not (root / "project.json").exists():
        raise FileNotFoundError(f"项目不存在：{root}（先运行 init）")
    return root


def command_init(args: argparse.Namespace) -> int:
    request = ProjectRequest(
        slug=args.slug,
        date=args.date,
        platforms=args.platforms.split(","),
        topic=args.topic or "",
        audience_segment=args.segment,
        input_type=args.input_type,
        source_article=args.article,
    )
    root = init_project(request)
    print(f"已创建项目：{root}")
    print("下一步：补全 brief.json 的受众、核心问题与开场（hook），再进入脚本阶段。")
    return 0


def command_import(args: argparse.Namespace) -> int:
    root = existing_project(args.project)
    request = AssetRequest(
        source=Path(args.file),
        kind=args.kind,
        rights=args.rights,
        origin_source=args.source,
        author=args.author,
        proof=args.proof,
        ai_generated=args.ai_generated,
        label_info=args.label,
    )
    record = import_asset(root, request)
    duration = f"{record['duration_ms'] / 1000:.2f}s" if record.get("duration_ms") else "-"
    size = f"{record.get('width')}x{record.get('height')}" if record.get("width") else "-"
    print(f"{record['asset_id']}  {record['kind']}  {size}  {duration}  授权：{record['rights']['status']}  -> {record['stored_path']}")
    if record["rights"]["status"] == "unconfirmed":
        print("[提醒] 授权未确认的素材不能入片，确认后在 assets.json 中更新 rights。")
    return 0


def command_probe(args: argparse.Namespace) -> int:
    print(json.dumps(probe_media(Path(args.file)), ensure_ascii=False, indent=2))
    return 0


def parse_outputs(root: Path, specs: list[str]) -> list[dict[str, Any]]:
    """--output 路径:用途；路径相对项目根目录，必须真实存在才能登记。"""
    entries = []
    for spec in specs:
        relative, _, purpose = spec.partition(":")
        absolute = resolve_inside(root, relative)
        if not absolute.is_file():
            raise FileNotFoundError(f"产物不存在，不能登记：{relative}")
        entries.append(describe_file(absolute, to_project_relative(root, absolute), purpose or "output"))
    return entries


def parse_checks(specs: list[str]) -> list[dict[str, Any]]:
    """--check 名称=passed|failed|not_checked[@证据路径]"""
    checks = []
    for spec in specs:
        name, _, rest = spec.partition("=")
        result, _, evidence = rest.partition("@")
        if result not in ("passed", "failed", "not_checked"):
            raise ValueError(f"检查结果只能是 passed/failed/not_checked：{spec}")
        checks.append({"check": name, "result": result, "evidence_path": evidence or None})
    return checks


def command_stage(args: argparse.Namespace) -> int:
    root = existing_project(args.project)
    manifest = load_manifest(root)
    patch: dict[str, Any] = {}
    if args.output:
        patch["output_files"] = parse_outputs(root, args.output)
    if args.check:
        patch["checks"] = parse_checks(args.check)
    if args.error_code:
        patch["error_code"] = args.error_code
        patch["recovery_action"] = args.recovery
    if args.waived:
        patch["applicability"] = "waived"
    stale = update_stage(manifest, args.stage, args.variant, args.status, patch)
    save_manifest(root, manifest)
    where = f"{args.variant}/" if args.variant else ""
    print(f"{where}{args.stage} -> {args.status}（revision {manifest['revision']}）")
    for platform, stages in stale.items():
        if stages:
            print(f"[失效] {platform}: {', '.join(stages)} 需要重跑")
    return 0


def format_stage_row(name: str, record: dict[str, Any]) -> str:
    outputs = len(record["output_files"])
    failed = sum(1 for c in record["checks"] if c["result"] == "failed")
    extra = f"  产物 {outputs}" if outputs else ""
    extra += f"  未通过检查 {failed}" if failed else ""
    extra += f"  错误 {record['error_code']}" if record["error_code"] else ""
    return f"  {name:<12} {record['status']:<8}{extra}"


def command_status(args: argparse.Namespace) -> int:
    root = existing_project(args.project)
    manifest = load_manifest(root)
    print(f"项目 {manifest['project_id']}（revision {manifest['revision']}，更新于 {manifest['updated_at']}）")
    print("公共阶段：")
    for name, record in manifest["shared_stages"].items():
        print(format_stage_row(name, record))
    for platform, stages in manifest["variants"].items():
        print(f"{platform}：")
        for name, record in stages.items():
            print(format_stage_row(name, record))
    costs = summarize_costs(root)
    print(f"费用：已结算 {costs['settled']}，未结算占用 {costs['reserved']}，金额未知条目 {costs['unknown_entries']}")
    for blocker in manifest["blockers"]:
        print(f"[阻塞] {blocker}")
    return 0


def command_cost(args: argparse.Namespace) -> int:
    root = existing_project(args.project)
    if args.cost_command == "summary":
        print(json.dumps(summarize_costs(root), ensure_ascii=False, indent=2))
        return 0
    entry = CostEntry(
        service=args.service,
        unit=args.unit,
        quantity=args.quantity,
        request_id=args.request_id,
        estimated=args.estimated,
        actual=args.actual,
        settlement_status=args.status,
        unit_price_source=args.price_source,
        note=args.note,
    )
    record = add_cost_entry(root, entry)
    print(f"已记账 {record['entry_id']}：{entry.service} {entry.quantity} {entry.unit}（{entry.settlement_status}）")
    return 0


def add_init_parser(sub: argparse._SubParsersAction) -> None:
    init = sub.add_parser("init", help="新建项目目录与清单")
    init.add_argument("slug", help="小写短名，如 bid-skill")
    init.add_argument("--date", help="YYYYMMDD，默认今天")
    init.add_argument("--platforms", default=",".join(DEFAULT_PLATFORMS),
                      help="逗号分隔；默认只做抖音，主理人点名视频号或两个都要时再改，如 douyin,channels")
    init.add_argument("--topic")
    init.add_argument("--segment", choices=AUDIENCE_SEGMENTS, help="受众细分")
    init.add_argument("--input-type", default="topic", choices=INPUT_TYPES)
    init.add_argument("--article", help="改编来源文章路径（只记录，不复制）")


def add_import_parser(sub: argparse._SubParsersAction) -> None:
    imp = sub.add_parser("import", help="导入素材：复制只读副本、计算校验值、探测媒体信息")
    imp.add_argument("project")
    imp.add_argument("file")
    imp.add_argument("--kind", required=True, choices=ASSET_KINDS)
    imp.add_argument("--rights", default="unconfirmed", choices=RIGHTS_STATUSES)
    imp.add_argument("--source", help="来源说明或链接")
    imp.add_argument("--author")
    imp.add_argument("--proof", help="授权证明路径或说明")
    imp.add_argument("--ai-generated", action="store_true")
    imp.add_argument("--label", help="生成内容标识说明")


def add_stage_parser(sub: argparse._SubParsersAction) -> None:
    stage = sub.add_parser("stage", help="更新阶段状态并登记产物")
    stage.add_argument("project")
    stage.add_argument("stage", choices=SHARED_STAGES + VARIANT_STAGES)
    stage.add_argument("--variant", choices=PLATFORMS)
    stage.add_argument("--status", required=True, choices=STAGE_STATUSES)
    stage.add_argument("--output", action="append", help="项目内相对路径:用途，可重复")
    stage.add_argument("--check", action="append", help="名称=passed|failed|not_checked[@证据路径]，可重复")
    stage.add_argument("--error-code")
    stage.add_argument("--recovery")
    stage.add_argument("--waived", action="store_true", help="按任务依据豁免该阶段")


def add_cost_parser(sub: argparse._SubParsersAction) -> None:
    cost = sub.add_parser("cost", help="费用账本")
    cost_sub = cost.add_subparsers(dest="cost_command", required=True)
    add = cost_sub.add_parser("add")
    add.add_argument("project")
    add.add_argument("--service", required=True)
    add.add_argument("--unit", required=True, help="计费单位，如 chars、images、seconds")
    add.add_argument("--quantity", type=float, required=True)
    add.add_argument("--request-id", help="服务端请求 ID，如 MiniMax trace_id")
    add.add_argument("--estimated", type=float)
    add.add_argument("--actual", type=float)
    add.add_argument("--status", default="unknown", choices=SETTLEMENT_STATUSES)
    add.add_argument("--price-source", help="单价来源及核验日期")
    add.add_argument("--note")
    summary = cost_sub.add_parser("summary")
    summary.add_argument("project")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VideoCut 项目管理技能")
    sub = parser.add_subparsers(dest="command", required=True)
    add_init_parser(sub)
    add_import_parser(sub)
    probe = sub.add_parser("probe", help="只探测媒体信息，不入库")
    probe.add_argument("file")
    add_stage_parser(sub)
    status = sub.add_parser("status", help="查看项目阶段与费用")
    status.add_argument("project")
    add_cost_parser(sub)
    return parser


COMMANDS = {
    "init": command_init,
    "import": command_import,
    "probe": command_probe,
    "stage": command_stage,
    "status": command_status,
    "cost": command_cost,
}


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，被智能体管道读取时中文会乱码；统一输出 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (ValueError, OSError, DataFileError, ToolError, PathSafetyError) as error:
        print(f"[失败] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
