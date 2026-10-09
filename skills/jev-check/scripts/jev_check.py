"""
INPUT: config.json；版本目录 speech.json，项目根目录 brief.json、research/claims.json；calibration/cases.json（标注样例）
OUTPUT: 子命令
  check      免费：密钥是否配置、GET /v1/models 连通性、本月用量与上限
  review     计费：对一版文稿做语义检查（开头是否具体、受众、夸大收益、口播与所引事实是否一致），结果写 jev-check.json；
             只给提示、不拦流程；--dry-run 只估算请求数与费用上界
  calibrate  计费：用标注样例重测当前模型，模型版本变化后先跑它再信任 review 的结果
POS: jev-check 技能的命令入口。script-check（离线、确定性规则）之后、配音之前运行；只读项目文件，不改文稿、不写 project.json。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import jev_client
from jev_client import SKILL_ROOT, BudgetExceeded, JevClient, JevError, list_models, load_api_key, max_input_tokens, now_local
from jev_rules import CHECKS, QUESTION_SET, Probe, Result, build_probes, judge

CONFIG_PATH = SKILL_ROOT / "config.json"
DEFAULT_CASES = SKILL_ROOT / "calibration" / "cases.json"
# 校准样例里有真实项目的定稿语段，请求内容可能与 review 完全相同；分开缓存，免得重新校准时覆盖项目文稿的缓存结果
from workspace import require_workspace


def calibration_cache() -> Path:
    """校准用独立缓存（不覆盖项目文稿的检查结果），放在工作区 .cache 下；找不到工作区时报错。"""
    return require_workspace(jev_client.REPO_ROOT, "Jev 校准缓存", JevError) / ".cache" / "jev-check" / "calibration"


class CheckError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    if not path.is_file():
        raise CheckError(f"缺少文件：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CheckError(f"{path} 不是有效 JSON：{error}") from error


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config() -> dict[str, Any]:
    return read_json(CONFIG_PATH)


def command_check(_: argparse.Namespace, config: dict[str, Any]) -> int:
    client = JevClient(config)
    month = now_local().strftime("%Y-%m")
    print(f"本月（{month}）已用 {client.usage.month_spent_usd(month):.6f} / {config['monthlyBudgetUsd']} 美元；单价 {config['priceSource']}")
    try:
        key = load_api_key()
    except JevError as error:
        print(f"[未配置] {error}")
        return 1
    print("TYPESAFE_API_KEY：已配置")
    models = list_models(client.api_base, key)
    print("可用模型：" + "、".join(model["name"] for model in models) + f"；本技能使用 {config['model']}，已校准版本 {config['calibratedModel']}")
    return 0


def _payload(client: JevClient, probe: Probe) -> dict[str, Any]:
    return client.build_payload(probe.state, {probe.check: CHECKS[probe.check]})


def _preflight_budget(client: JevClient, payloads: list[dict[str, Any]], use_cache: bool) -> tuple[int, float]:
    """整批请求的费用上界先过一次预算，避免跑到一半才停、留下半份结果。"""
    fresh = [payload for payload in payloads if not (use_cache and client.is_cached(payload))]
    bound = sum(max_input_tokens(payload, client.pricing.per_question_overhead, client.pricing.base_overhead) for payload in fresh)
    max_usd = client.pricing.cost(bound)
    month = now_local().strftime("%Y-%m")
    spent = client.usage.month_spent_usd(month)
    if spent + max_usd > client.pricing.monthly_budget_usd:
        raise BudgetExceeded(f"本月已用 {spent:.6f} 美元，本次最多 {max_usd:.6f} 美元，会超过上限 {client.pricing.monthly_budget_usd} 美元")
    return len(fresh), max_usd


def _run_probes(client: JevClient, probes: list[Probe], brief: dict[str, Any], use_cache: bool) -> tuple[list[Result], dict[str, Any]]:
    results: list[Result] = []
    stats: dict[str, Any] = {"requests": 0, "cache_hits": 0, "input_tokens": 0, "cost_usd": 0.0, "models": set()}
    for probe in probes:
        asked = client.ask(_payload(client, probe), use_cache=use_cache)
        stats["cache_hits" if asked.cached else "requests"] += 1
        stats["input_tokens"] += asked.input_tokens
        stats["cost_usd"] += asked.cost_usd
        stats["models"].add(asked.body.get("model"))
        results.append(judge(probe, asked.body["answers"][probe.check], brief))
    return results, stats


def _model_warning(models: set[str], config: dict[str, Any]) -> str | None:
    # 别名 jev-latest 会随官方升级指向新版本；版本变了，试点定下的措辞与阈值不再有依据
    others = sorted(str(model) for model in models if model != config["calibratedModel"])
    if others:
        return f"返回的模型版本 {others} 与已校准的 {config['calibratedModel']} 不同；先运行 calibrate 再信任本次结果"
    return None


def command_review(args: argparse.Namespace, config: dict[str, Any]) -> int:
    variant_dir = Path(args.variant_dir).resolve()
    project_dir = variant_dir.parent.parent
    speech_path, brief_path, claims_path = variant_dir / "speech.json", project_dir / "brief.json", project_dir / "research" / "claims.json"
    speech, brief = read_json(speech_path), read_json(brief_path)
    claims = {claim["claim_id"]: claim for claim in read_json(claims_path)["claims"]}
    client = JevClient(config)
    probes, skipped = build_probes(speech, claims)
    fresh, max_usd = _preflight_budget(client, [_payload(client, probe) for probe in probes], not args.no_cache)
    print(f"{variant_dir.name}: {len(probes)} 项判断，需新请求 {fresh} 次，费用上界 {max_usd:.6f} 美元")
    if args.dry_run:
        return 0
    results, stats = _run_probes(client, probes, brief, not args.no_cache)
    results += skipped
    warning = _model_warning(stats["models"], config)
    report = {
        "schema_version": "1.0", "variant": variant_dir.name, "question_set": QUESTION_SET,
        "model_alias": config["model"], "models": sorted(str(model) for model in stats["models"]), "model_warning": warning,
        "checked_at": now_local().isoformat(timespec="seconds"),
        "inputs": {"speech_sha256": sha256_file(speech_path), "brief_sha256": sha256_file(brief_path), "claims_sha256": sha256_file(claims_path)},
        "usage": {"requests": stats["requests"], "cache_hits": stats["cache_hits"], "input_tokens": stats["input_tokens"],
                  "estimated_usd": round(stats["cost_usd"], 9), "price_source": config["priceSource"]},
        "summary": {verdict: sum(1 for result in results if result.verdict == verdict) for verdict in ("passed", "flagged", "not_checked", "skipped")},
        "results": [result.as_dict() for result in results],
    }
    out_path = variant_dir / "jev-check.json"
    tmp_path = out_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(out_path)
    _print_report(report, warning)
    return 0


def _print_report(report: dict[str, Any], warning: str | None) -> None:
    usage, summary = report["usage"], report["summary"]
    print(f"模型 {'、'.join(report['models'])}；新请求 {usage['requests']} 次、缓存 {usage['cache_hits']} 次，输入 {usage['input_tokens']} token，约 {usage['estimated_usd']:.6f} 美元")
    print(f"通过 {summary['passed']}，提示 {summary['flagged']}，待人工 {summary['not_checked']}，跳过 {summary['skipped']}")
    for result in report["results"]:
        if result["verdict"] in ("flagged", "not_checked"):
            label = "提示" if result["verdict"] == "flagged" else "待人工"
            print(f"  [{label}] {result['check']} @ {result['where']}：{result['message']}")
    if warning:
        print(f"[注意] {warning}")


def _case_outcome(case: dict[str, Any], result: Result) -> bool:
    if "expected_choice" in case:
        return result.detail.get("choice") == case["expected_choice"] and result.verdict != "not_checked"
    return result.verdict == case["expected"]


def command_calibrate(args: argparse.Namespace, config: dict[str, Any]) -> int:
    cases = read_json(Path(args.cases))["cases"]
    client = JevClient(config, cache_dir=calibration_cache())
    probes = [Probe(case["check"], f"case-{index:02d}", case["state"]) for index, case in enumerate(cases, start=1)]
    _preflight_budget(client, [_payload(client, probe) for probe in probes], args.use_cache)
    # 受众样例的期望人群写在 brief 里，让 judge 与 review 走同一条判定路径
    results, stats = [], {"models": set(), "cost_usd": 0.0}
    for probe, case in zip(probes, cases):
        asked = client.ask(_payload(client, probe), use_cache=args.use_cache)
        stats["models"].add(asked.body.get("model"))
        stats["cost_usd"] += asked.cost_usd
        results.append(judge(probe, asked.body["answers"][probe.check], {"audience_segment": case.get("expected_choice")}))
    return _print_calibration(cases, results, stats)


def _print_calibration(cases: list[dict[str, Any]], results: list[Result], stats: dict[str, Any]) -> int:
    unexpected = 0
    per_check: dict[str, list[int]] = {}
    for case, result in zip(cases, results):
        ok = _case_outcome(case, result)
        tally = per_check.setdefault(case["check"], [0, 0])
        tally[0] += int(ok)
        tally[1] += 1
        if not ok:
            note = f"（已知漏判：{case['known_miss']}）" if case.get("known_miss") else ""
            unexpected += 0 if case.get("known_miss") else 1
            print(f"  [不符] {case['check']} {json.dumps(case['state'], ensure_ascii=False)[:60]} → {result.verdict} {result.detail}{note}")
    print(f"模型 {'、'.join(sorted(str(model) for model in stats['models']))}，约 {stats['cost_usd']:.6f} 美元")
    print("；".join(f"{check} {ok}/{total}" for check, (ok, total) in per_check.items()) + f"；意外不符 {unexpected} 条")
    return 1 if unexpected else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VideoCut 文稿语义检查（Jev 决策模型）")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="免费：验证密钥与连通性，查看本月用量")
    review = sub.add_parser("review", help="计费：检查一版文稿，写 jev-check.json")
    review.add_argument("--variant-dir", required=True, help="如 projects/<id>/variants/channels")
    review.add_argument("--no-cache", action="store_true", help="不用缓存、重新请求（会再次计费）")
    review.add_argument("--dry-run", action="store_true", help="只估算请求数与费用上界，不发请求")
    calibrate = sub.add_parser("calibrate", help="计费：用标注样例重测当前模型")
    calibrate.add_argument("--cases", default=str(DEFAULT_CASES))
    calibrate.add_argument("--use-cache", action="store_true", help="允许用缓存（默认重新请求，以测到当前模型）")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，被智能体管道读取时中文会乱码；与其他技能一样统一输出 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    handlers = {"check": command_check, "review": command_review, "calibrate": command_calibrate}
    try:
        return handlers[args.command](args, load_config())
    except (CheckError, JevError) as error:
        print(f"[失败] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
