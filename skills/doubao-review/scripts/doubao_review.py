"""
INPUT: 版本目录的 speech.json、script.md、可选 cover.props.json、publish.md、doubao-review.waivers.json；config.json；ark_client.py 与 review_rules.py
OUTPUT: 子命令
  check    免费：密钥是否配置、模型与预算、本月用量；加 --ping 发一次极小的计费请求，验证密钥与模型已开通
  review   计费：按范围（script 配音稿与脚本 / publish 发布文案）送豆包审核，结果写 doubao-review.json；有未放行的高风险时退出码 1
  waive    免费：主理人确认某条是误判后放行，写入 doubao-review.waivers.json 并更新结果
POS: 配音前与上传前的平台风险语义审核命令。只读文稿、不改文稿、不写 project.json；费用由调用方用 vp.py cost add 登记到项目账本。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from ark_client import SKILL_ROOT, ArkClient, ArkError, find_api_key, now_local
from review_rules import PROMPT_VERSION, SCOPES, Document, ReviewParseError, build_documents, build_messages, make_items, parse_review, response_format, summarize

REPORT_NAME = "doubao-review.json"
WAIVERS_NAME = "doubao-review.waivers.json"


class ReviewError(RuntimeError):
    pass


def load_config() -> dict[str, Any]:
    return json.loads((SKILL_ROOT / "config.json").read_text(encoding="utf-8"))


def read_text(path: Path, required: bool = True) -> str | None:
    if not path.is_file():
        if required:
            raise ReviewError(f"缺少文件：{path}")
        return None
    return path.read_text(encoding="utf-8")


def sha256_of(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def read_waivers(variant_dir: Path) -> list[dict[str, Any]]:
    text = read_text(variant_dir / WAIVERS_NAME, required=False)
    return json.loads(text).get("waivers", []) if text else []


def command_check(args: argparse.Namespace) -> int:
    config = load_config()
    client = ArkClient(config)
    month = now_local().strftime("%Y-%m")
    print(f"密钥 ARK_API_KEY：{'已配置' if find_api_key() else '未配置（在工作区根目录 .env 写入 ARK_API_KEY=你的密钥）'}")
    print(f"模型 {config['model']}；接口 {client.api_base}；本月已用 ¥{client.usage.month_spent_cny(month):.4f} / 上限 ¥{config['monthlyBudgetCny']}")
    if not args.ping:
        return 0 if find_api_key() else 1
    payload = client.build_payload([{"role": "user", "content": "只回复两个字母：ok"}], None)
    payload["max_tokens"] = 16
    result = client.chat(payload, use_cache=False)
    print(f"连通：模型 {result.body.get('model')} 回复「{result.content.strip()[:20]}」；输入 {result.input_tokens} / 输出 {result.output_tokens} token，约 ¥{result.cost_cny:.6f}")
    return 0


def _documents(variant_dir: Path, scope: str) -> list[Document]:
    speech = json.loads(read_text(variant_dir / "speech.json") or "{}")
    cover_text = read_text(variant_dir / "cover.props.json", required=False)
    documents = build_documents(speech, read_text(variant_dir / "script.md") or "", json.loads(cover_text) if cover_text else None,
                                read_text(variant_dir / "publish.md", required=False))
    selected = [document for document in documents if scope == "all" or document.scope == scope]
    if scope == "publish" and not selected:
        raise ReviewError("没有 publish.md 或其中没有公开章节（标题、说明、话题、来源），无法审核发布文案")
    return selected


def _dry_run(client: ArkClient, payloads: list[tuple[Document, dict[str, Any]]]) -> int:
    for document, payload in payloads:
        input_bound, output_bound, cost_bound = client.pricing.bound(payload)
        state = "缓存命中，不计费" if client.is_cached(payload) else f"上界 {input_bound} 输入 + {output_bound} 输出 token，最多 ¥{cost_bound:.4f}"
        print(f"  {document.scope}：{len(document.text)} 字；{state}")
    return 0


def _run_requests(client: ArkClient, payloads: list[tuple[Document, dict[str, Any]]], use_cache: bool,
                  waivers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    fresh = [payload for _, payload in payloads if not (use_cache and client.is_cached(payload))]
    if fresh:
        # 整批先过一次预算闸门：一半请求花了钱、另一半被拦的结果没有用
        client.check_budget(fresh)
    items: list[dict[str, Any]] = []
    requests_log: list[dict[str, Any]] = []
    summaries: dict[str, str] = {}
    for document, payload in payloads:
        result = client.chat(payload, use_cache=use_cache)
        requests_log.append({"scope": document.scope, "request_hash": result.request_hash, "cached": result.cached, "model": result.body.get("model"),
                             "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "cost_cny": round(result.cost_cny, 8)})
        try:
            parsed = parse_review(result.content)
        except ReviewParseError as error:
            raise ReviewError(f"{document.scope} 审核结果无法解析（本次请求已计费并已缓存；改用 --no-cache 重试会再次计费）：{error}") from error
        items += make_items(document.scope, parsed, document, waivers)
        summaries[document.scope] = parsed["summary"]
    return items, requests_log, summaries


def _write_report(variant_dir: Path, report: dict[str, Any]) -> None:
    counts, blocked = summarize(report["items"])
    report["counts"], report["blocked"] = counts, blocked
    tmp_path = variant_dir / f"{REPORT_NAME}.tmp"
    tmp_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(variant_dir / REPORT_NAME)


def _print_report(report: dict[str, Any]) -> None:
    counts = report["counts"]
    usage = report["usage"]
    print(f"{report['variant']}（{report['platform']}）：高 {counts['high']}、中 {counts['medium']}、低 {counts['low']}，已放行 {counts['waived']}；"
          f"新请求 {usage['requests']}、缓存 {usage['cache_hits']}，约 ¥{usage['cost_cny']:.4f} -> {'拦截：先处理高风险' if report['blocked'] else '未拦截'}")
    for item in report["items"]:
        flag = "（已放行）" if item["waived"] else "" if item["quote_found"] else "（原文里找不到这句，可能是模型编造，人工核对）"
        print(f"  [{item['risk']}] {item['item_id']} {item['category_label']} @ {item['location']}{flag}：「{item['quote']}」{item['reason']} → {item['suggestion']}")


def command_review(args: argparse.Namespace) -> int:
    variant_dir = Path(args.variant_dir).resolve()
    platform = args.platform or variant_dir.name
    config = load_config()
    client = ArkClient(config)
    fmt = response_format(config["responseFormat"])
    payloads = [(document, client.build_payload(build_messages(document, platform), fmt)) for document in _documents(variant_dir, args.scope)]
    if args.dry_run:
        return _dry_run(client, payloads)
    items, requests_log, summaries = _run_requests(client, payloads, not args.no_cache, read_waivers(variant_dir))
    fresh = [entry for entry in requests_log if not entry["cached"]]
    report = {
        "schema_version": "1.0", "prompt_version": PROMPT_VERSION, "variant": variant_dir.name, "platform": platform, "model": config["model"],
        "checked_at": now_local().isoformat(timespec="seconds"), "scopes": [document.scope for document, _ in payloads],
        "inputs": {name: sha256_of(variant_dir / name) for name in ("speech.json", "script.md", "cover.props.json", "publish.md")},
        "requests": requests_log,
        "usage": {"requests": len(fresh), "cache_hits": len(requests_log) - len(fresh), "input_tokens": sum(entry["input_tokens"] for entry in fresh),
                  "output_tokens": sum(entry["output_tokens"] for entry in fresh), "cost_cny": round(sum(entry["cost_cny"] for entry in fresh), 6),
                  "price_source": config["priceSource"]},
        "summaries": summaries, "items": items,
    }
    _write_report(variant_dir, report)
    _print_report(report)
    return 1 if report["blocked"] else 0


def command_waive(args: argparse.Namespace) -> int:
    variant_dir = Path(args.variant_dir).resolve()
    report_text = read_text(variant_dir / REPORT_NAME)
    report = json.loads(report_text or "{}")
    item = next((entry for entry in report.get("items", []) if entry["item_id"] == args.item), None)
    if item is None:
        raise ReviewError(f"{REPORT_NAME} 里没有条目 {args.item}")
    waiver = {"scope": item["scope"], "location": item["location"], "quote": item["quote"], "category": item["category"], "risk": item["risk"],
              "reason": args.reason, "approved_by": args.approved_by, "approved_at": now_local().isoformat(timespec="seconds")}
    waivers = read_waivers(variant_dir) + [waiver]
    (variant_dir / WAIVERS_NAME).write_text(json.dumps({"waivers": waivers}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    item["waived"] = {key: waiver[key] for key in ("reason", "approved_by", "approved_at")}
    _write_report(variant_dir, report)
    print(f"已放行 {args.item}（{item['risk']}）：{args.reason}；当前{'仍有未放行的高风险，继续拦截' if report['blocked'] else '无未放行的高风险'}")
    return 1 if report["blocked"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="豆包（火山方舟）平台风险审核：配音稿、脚本与发布文案")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="免费：配置与用量；--ping 发一次极小的计费请求验证连通")
    check.add_argument("--ping", action="store_true")
    review = sub.add_parser("review", help="计费：送豆包审核")
    review.add_argument("--variant-dir", required=True, help="如 projects/<id>/variants/douyin")
    review.add_argument("--scope", choices=(*SCOPES, "all"), default="all", help="script 配音稿与脚本；publish 发布文案；all 两者（默认，没有 publish.md 时只审 script）")
    review.add_argument("--platform", help="douyin / channels，默认取版本目录名")
    review.add_argument("--dry-run", action="store_true", help="免费：只估算费用上界")
    review.add_argument("--no-cache", action="store_true", help="忽略缓存重新请求（会再次计费）")
    waive = sub.add_parser("waive", help="免费：主理人确认误判后放行一条")
    waive.add_argument("--variant-dir", required=True)
    waive.add_argument("--item", required=True, help="doubao-review.json 里的 item_id，如 script-03")
    waive.add_argument("--reason", required=True, help="放行理由，写主理人的原话")
    waive.add_argument("--approved-by", default="主理人")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK：报告里的 ¥ 等字符会让 print 直接抛错；与其他技能一样统一输出 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    commands = {"check": command_check, "review": command_review, "waive": command_waive}
    try:
        return commands[args.command](args)
    except (ReviewError, ArkError) as error:
        print(f"[失败] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
