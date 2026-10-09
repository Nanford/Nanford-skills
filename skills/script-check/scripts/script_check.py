"""
INPUT: 版本目录下 speech.json、shots.json、可选 cover.props.json、publish.md、captions/captions.json；项目根目录 brief.json、research/claims.json、research/sources.json；
       config/platform-terms.json（平台敏感词工作清单）
OUTPUT: 子命令
  lint       配音前检查：开头规则、版面长度、事实与数字可追溯、结构与时长预估；结果写 script-check.json，有 error 时退出码 1
  hook-gate  配音后检查：按真实字幕时间量第一句结束与第一个数字出现的时刻；未达标退出码 1
  terms      平台敏感词检查：口播、上屏文字、封面、发布文案与截图 OCR 文字；结果写 terms-check.json，有 error 或截图未能识别时退出码 1
POS: 文稿阶段的闸门命令。只读项目文件（terms 另写项目内 OCR 缓存），不改文稿、不调用任何计费接口；是否放行由退出码表达，供 video-pipeline 调用。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sclib.ocr import OcrUnavailable, recognize
from sclib.rules import Finding, hook_gate, lint_variant
from sclib.terms import TextItem, collect_texts, load_terms, scan_texts, screenshot_paths, terms_report


class CheckError(RuntimeError):
    pass


def read_json(path: Path, required: bool = True) -> Any:
    if not path.is_file():
        if required:
            raise CheckError(f"缺少文件：{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CheckError(f"{path} 不是有效 JSON：{error}") from error


def by_id(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {item[key]: item for item in items}


def command_lint(args: argparse.Namespace) -> int:
    variant_dir = Path(args.variant_dir).resolve()
    project_dir = variant_dir.parent.parent
    claims = by_id(read_json(project_dir / "research" / "claims.json")["claims"], "claim_id")
    sources = by_id(read_json(project_dir / "research" / "sources.json")["sources"], "source_id")
    report = lint_variant(
        variant_dir.name, read_json(variant_dir / "speech.json"), read_json(variant_dir / "shots.json"), read_json(project_dir / "brief.json"),
        claims, sources, read_json(variant_dir / "cover.props.json", required=False),
    )
    (variant_dir / "script-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    estimates = report["estimates"]
    print(f"{report['variant']}: 预估第一句 {estimates['hook_first_sentence_s']} 秒，第一个数字 {estimates['first_number_s']} 秒，全片约 {estimates['total_s']} 秒；"
          f"error {report['errors']}，warning {report['warnings']}")
    for finding in report["findings"]:
        print(f"  [{finding['level']}] {finding['rule']} @ {finding['where']}：{finding['message']}")
    return 1 if report["errors"] else 0


def command_hook_gate(args: argparse.Namespace) -> int:
    variant_dir = Path(args.variant_dir).resolve()
    speech = read_json(variant_dir / "speech.json")
    captions = read_json(variant_dir / "captions" / "captions.json")["entries"]
    result = hook_gate(speech, captions)
    print(f"{variant_dir.name}: 首条字幕 {result['first_caption_ms']} ms，第一句结束 {result['first_sentence_end_ms']} ms，第一个数字 {result['first_number_ms']} ms -> "
          f"{'通过' if result['passed'] else '未通过：' + '；'.join(result['problems'])}")
    return 0 if result["passed"] else 1


def _scan_screenshots(project_dir: Path, shots: dict[str, Any], skip_ocr: bool) -> tuple[list[TextItem], list[dict[str, Any]], list[Finding]]:
    """镜头用到的截图逐张 OCR。识别不了的截图记为 not_checked 并报 error，不能当作没有敏感词；--no-ocr 时降为 warning。"""
    pairs = screenshot_paths(shots)
    paths = sorted({(project_dir / image).resolve() for _, image in pairs})
    status: dict[Path, str] = {}
    lines: dict[Path, list[str]] = {}
    problem = "按 --no-ocr 跳过" if skip_ocr else None
    missing = [path for path in paths if not path.is_file()]
    if not skip_ocr:
        try:
            lines = recognize([path for path in paths if path.is_file()], project_dir / "assets" / "ocr-cache.json")
        except OcrUnavailable as error:
            problem = str(error)
    for path in paths:
        status[path] = "missing" if path in missing else "passed" if path in lines else "not_checked"
    items = [TextItem(f"{shot_id} 截图 {image}", "\n".join(lines.get((project_dir / image).resolve(), []))) for shot_id, image in pairs]
    findings = [Finding("error", "terms.screenshot_missing", str(path), "镜头引用的截图不存在") for path in missing]
    unchecked = [path for path in paths if status[path] == "not_checked"]
    if unchecked:
        findings.append(Finding("warning" if skip_ocr else "error", "terms.ocr_not_checked", f"{len(unchecked)} 张截图",
                                f"截图文字未检查（{problem}）；逐张人工查看截图里有没有词表里的词"))
    report = [{"path": str(path.relative_to(project_dir)) if path.is_relative_to(project_dir) else str(path), "status": status[path],
               "lines": len(lines.get(path, []))} for path in paths]
    return items, report, findings


def command_terms(args: argparse.Namespace) -> int:
    variant_dir = Path(args.variant_dir).resolve()
    project_dir = variant_dir.parent.parent
    platform = args.platform or variant_dir.name
    terms = load_terms(platform, Path(args.terms)) if args.terms else load_terms(platform)
    shots = read_json(variant_dir / "shots.json")
    publish_path = variant_dir / "publish.md"
    items = collect_texts(read_json(variant_dir / "speech.json"), shots, read_json(variant_dir / "cover.props.json", required=False),
                          publish_path.read_text(encoding="utf-8") if publish_path.is_file() else None)
    screenshot_items, screenshots, findings = _scan_screenshots(project_dir, shots, args.no_ocr)
    findings = scan_texts(items + screenshot_items, terms) + findings
    report = terms_report(platform, findings, screenshots)
    (variant_dir / "terms-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checked = sum(1 for item in screenshots if item["status"] == "passed")
    print(f"{variant_dir.name}（{platform}）：截图 OCR {checked}/{len(screenshots)} 张；error {report['errors']}，warning {report['warnings']}"
          f"{'' if publish_path.is_file() else '；没有 publish.md，发布文案未检查'}")
    for finding in report["findings"]:
        print(f"  [{finding['level']}] {finding['rule']} @ {finding['where']}：{finding['message']}")
    return 1 if report["errors"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VideoCut 文稿检查：开头、版面与事实")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("lint", "配音前检查"), ("hook-gate", "配音后按字幕时间检查开头")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--variant-dir", required=True, help="如 projects/<id>/variants/channels")
    terms = sub.add_parser("terms", help="平台敏感词检查（含截图 OCR）")
    terms.add_argument("--variant-dir", required=True, help="如 projects/<id>/variants/douyin")
    terms.add_argument("--platform", help="词表里的平台键，默认取版本目录名（douyin / channels）")
    terms.add_argument("--terms", help="改用另一份词表 JSON，默认 config/platform-terms.json")
    terms.add_argument("--no-ocr", action="store_true", help="跳过截图 OCR（非 Windows 环境）；截图记为未检查并给 warning")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，被智能体管道读取时中文会乱码；与其他技能一样统一输出 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        commands = {"lint": command_lint, "hook-gate": command_hook_gate, "terms": command_terms}
        return commands[args.command](args)
    except CheckError as error:
        print(f"[失败] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
