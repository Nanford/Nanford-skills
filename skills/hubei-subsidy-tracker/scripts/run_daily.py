#!/usr/bin/env python3
"""One observable daily entry point; DingTalk external steps remain in its host."""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

import setup_state as state


def execute(script, *args):
    env = dict(os.environ, SUBSIDY_DATA_DIR=str(state.data_dir()),
               SUBSIDY_CONFIG_FILE=str(state.config_path()), PYTHONUTF8="1")
    subprocess.run([sys.executable, "-X", "utf8", str(state.ROOT / "scripts" / script), *args],
                   env=env, check=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--local-only", action="store_true", help="仅运行采集与本地匹配，不连接协作平台或发送通知")
    args = ap.parse_args(argv)
    data = state.data_dir()
    data.mkdir(parents=True, exist_ok=True)
    lock = data / "daily.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("已有日常任务运行或上次异常退出，请核对 daily.lock 对应进程后恢复。", file=sys.stderr)
        return 2
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"pid": os.getpid(), "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}, handle)
    progress = {"started_at": dt.datetime.now(dt.timezone.utc).isoformat(), "steps": [], "success": False}
    try:
        cfg = state.read_config()
        mode = cfg.get("SKILL_MODE", "local")
        if mode == "dingtalk" and not args.local_only:
            raise ValueError("钉钉全流程须由千问办公执行；本地验证使用 --local-only")
        if mode not in ("local", "feishu", "dingtalk"):
            raise ValueError("运行模式无效")
        state.invalidate("collection")
        state.invalidate("matching")
        execute("fetch_subsidies.py", "--collect", "--content", "--parse-thresholds")
        sources = json.loads((data / "collection_report.json").read_text(encoding="utf-8"))
        if not sources.get("success") or sources.get("started_at", "") < progress["started_at"]:
            raise ValueError("部分采集源失败或缺少本次采集证据，已保存可用结果，请查看 collection_report.json")
        state.record_local("collection", "collection_report.json")
        progress["steps"].append("collection")
        if mode == "feishu" and not args.local_only:
            execute("feishu_sync.py", "--pull")
        from onboarding import workbook_rows
        companies = workbook_rows(data / "enterprises.xlsx")
        names = [str(r.get("企业名称") or "").strip() for r in companies if str(r.get("企业名称") or "").strip()]
        if len(names) != len(set(names)):
            raise ValueError("企业名称重复，请先核对信用代码并合并或区分档案")
        if any(str(r.get("企业名称") or "").strip() for r in companies):
            execute("match_engine.py", "--policy", str(data / "subsidy_records.xlsx"),
                    "--enterprises", str(data / "enterprises.xlsx"), "--out", str(data / "match_results.xlsx"))
            state.record_local("matching", "match_results.xlsx")
            progress["steps"].append("matching")
        else:
            progress["pending"] = "补充至少一家企业的基础档案后继续匹配"
        if mode == "feishu" and not args.local_only:
            execute("feishu_sync.py", "--sync")
            progress["steps"].append("sync")
            saved = state.load_state()
            if saved["preferences"].get("notifications"):
                if not state.verified("notification", saved):
                    raise ValueError("通知收件范围未验证或已变化，请先完成受控测试")
                execute("feishu_sync.py", "--notify")
                execute("feishu_sync.py", "--sync", "--only", "match")
                progress["steps"].append("notification")
        progress["success"] = True
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Detailed subprocess logs stay local; do not copy credentials into receipts.
        progress["error_type"] = type(exc).__name__
        print(f"日常任务未完成：{exc}", file=sys.stderr)
        return 2
    finally:
        progress["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            state.atomic_json(data / "last_run.json", progress)
        finally:
            lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
