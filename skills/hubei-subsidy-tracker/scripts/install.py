#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install local components; scheduling is explicit and never implies verification."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import init_setup
import setup_state

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = str(setup_state.data_dir())
PY = sys.executable
ENTERPRISE_FIELDS = init_setup.ENTERPRISE_FIELDS
DEPS = ["requests", "beautifulsoup4", "lxml", "openpyxl"]


def ensure_enterprise_template():
    original = init_setup.DATA_DIR
    try:
        init_setup.DATA_DIR = DATA_DIR
        return init_setup.ensure_enterprise_template()
    finally:
        init_setup.DATA_DIR = original


def install_deps():
    subprocess.run([PY, "-m", "pip", "install", "--quiet", "-r", str(Path(ROOT) / "requirements.txt")], check=True)


def generate_run_bat():
    # CMD expands percent and exclamation marks even inside some quoted contexts.
    paths = (PY, DATA_DIR, HERE, str(setup_state.config_path()))
    if any(any(c in path for c in ('%', '!', '\n', '\r', '"')) for path in paths):
        raise ValueError("当前路径包含批处理不支持的字符；请通过智能体直接运行 run_daily.py")
    content = f'''@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
set "SUBSIDY_DATA_DIR={DATA_DIR}"
set "SUBSIDY_CONFIG_FILE={setup_state.config_path()}"
set "PYTHONUTF8=1"
if not exist "{DATA_DIR}\\logs" mkdir "{DATA_DIR}\\logs"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set RUN_DATE=%%I
"{PY}" -X utf8 "{os.path.join(HERE, 'run_daily.py')}" >> "{DATA_DIR}\\logs\\run_%RUN_DATE%.log" 2>&1
exit /b %errorlevel%
'''
    Path(HERE, "run_daily.bat").write_text(content, encoding="utf-8")


def register_task(t):
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t):
        raise ValueError("定时时间必须是 00:00–23:59 的 HH:MM")
    bat = str(Path(HERE, "run_daily.bat").resolve())
    name = "HubeiSubsidyDaily-" + hashlib.sha256(str(Path(DATA_DIR).resolve()).encode()).hexdigest()[:10]
    query = subprocess.run(["schtasks", "/query", "/tn", name, "/xml"], shell=False, capture_output=True, text=True, timeout=60)
    if query.returncode == 0:
        tree = ET.fromstring(query.stdout)
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        command = tree.findtext(".//t:Exec/t:Command", namespaces=ns) or ""
        boundary = tree.findtext(".//t:StartBoundary", namespaces=ns) or ""
        if command.strip('"').casefold() != bat.casefold() or boundary[11:16] != t:
            raise ValueError("已有同名任务的路径或时间不同；请核对后显式调整，不自动覆盖")
        print("已复用相同路径与时间的定时任务。")
    else:
        subprocess.run(["schtasks", "/create", "/tn", name, "/tr", f'"{bat}"',
                        "/sc", "daily", "/st", t], shell=False, capture_output=True, text=True, timeout=60, check=True)
    setup_state.atomic_json(Path(DATA_DIR) / "schedule_registration.json",
                            {"task_name": name, "time": t, "command": bat, "verified_run": False})
    print(f"定时任务已登记：{name}，每天 {t}；实际执行验证尚待完成。")
    return name


def first_run():
    subprocess.run([PY, "-X", "utf8", str(Path(HERE) / "run_daily.py"), "--local-only"],
                   env=dict(os.environ, SUBSIDY_DATA_DIR=DATA_DIR,
                            SUBSIDY_CONFIG_FILE=str(setup_state.config_path()), PYTHONUTF8="1"), check=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="准备组件并继续首次引导")
    ap.add_argument("--mode", choices=["local", "feishu", "dingtalk"], help="省略时保留已有模式，新安装默认本地")
    ap.add_argument("--time", default="09:00")
    task = ap.add_mutually_exclusive_group()
    task.add_argument("--enable-task", action="store_true", help="显式注册 Windows 定时任务")
    task.add_argument("--skip-task", action="store_true", help="兼容旧入口，安装默认不注册任务")
    ap.add_argument("--skip-first-run", action="store_true")
    ap.add_argument("--skip-deps", action="store_true", help="已有依赖时跳过联网安装")
    args = ap.parse_args(argv)
    try:
        if sys.version_info < (3, 10):
            raise ValueError("需要 Python 3.10 或更新版本")
        mode = args.mode or setup_state.read_config().get("SKILL_MODE", "local")
        if mode not in ("local", "feishu", "dingtalk"):
            raise ValueError("已有 SKILL_MODE 无效，请明确选择模式")
        if args.enable_task and (mode == "dingtalk" or os.name != "nt"):
            raise ValueError("此环境不能注册 Windows 全流程任务；钉钉模式由千问办公调度")
        if not args.skip_deps:
            install_deps()
        {"local": init_setup.init_local, "feishu": init_setup.init_feishu, "dingtalk": init_setup.init_dingtalk}[mode]()
        if os.name == "nt":
            generate_run_bat()
        if not args.skip_first_run:
            first_run()
        if args.enable_task:
            register_task(args.time)
            saved = setup_state.load_state()
            saved["preferences"]["schedule"] = True
            setup_state.save_state(saved)
        print("基础组件已准备；接入状态如下。")
        return init_setup.status(checkpoint=True)
    except (OSError, ValueError, ImportError, subprocess.SubprocessError, ET.ParseError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f"安装尚未完成：{reason}。请检查当前步骤，修复后重跑；已有数据保留。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
