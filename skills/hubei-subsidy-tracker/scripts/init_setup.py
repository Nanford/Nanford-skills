#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Initialize a mode, inspect readiness, and record verified onboarding progress."""
import argparse
import json
import os
import sys
from pathlib import Path

import setup_state

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = str(setup_state.data_dir())
COMPANY_DIR = os.path.join(DATA_DIR, "company_docs")
CONFIG_ENV = str(setup_state.config_path())
DINGTALK_CONFIG = os.path.join(DATA_DIR, "dingtalk_config.json")
DINGTALK_USERS = os.path.join(DATA_DIR, "dingtalk_notify_users.json")
DINGTALK_DUMPS = os.path.join(DATA_DIR, "dingtalk_dumps")
DINGTALK_OPS = os.path.join(DATA_DIR, "dingtalk_ops")
ENTERPRISE_FIELDS = ["企业名称", "统一信用代码", "行业", "规模-营收", "规模-人数", "资质",
                     "近一年营收", "纳税/利润", "研发费用", "社保人数", "人才类型", "注册地区", "通知人", "备注"]


def ensure_enterprise_template():
    path = Path(DATA_DIR) / "enterprises.xlsx"
    if path.exists():
        return False
    import openpyxl
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "企业档案"
    ws.append(ENTERPRISE_FIELDS)
    ws.freeze_panes = "A2"
    example = wb.create_sheet("填写示例")
    example.append(ENTERPRISE_FIELDS)
    example.append(["武汉示例企业（勿用于正式匹配）", "", "智能制造", "", "", "待确认",
                    "", "", "", "", "", "湖北省武汉市江岸区", "", "金额单位万元，年度需在备注注明；未知字段留空"])
    wb.save(path)
    wb.close()
    return True


def set_mode(mode):
    path = Path(CONFIG_ENV)
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    # Update only this setting, preserving credentials and unrelated options.
    lines = [line for line in lines if line.split("=", 1)[0].strip() != "SKILL_MODE"]
    lines.append(f"SKILL_MODE={mode}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def init_local():
    Path(COMPANY_DIR).mkdir(parents=True, exist_ok=True)
    (Path(DATA_DIR) / "logs").mkdir(parents=True, exist_ok=True)
    ensure_enterprise_template()
    set_mode("local")
    print("本地目录与空白企业档案已准备。")


def init_feishu():
    init_local()
    set_mode("feishu")
    print("已选择飞书协作；保留现有配置，仅补充缺失凭证与表格位置，再执行读写验证。")


def init_dingtalk():
    init_local()
    set_mode("dingtalk")
    Path(DINGTALK_DUMPS).mkdir(parents=True, exist_ok=True)
    Path(DINGTALK_OPS).mkdir(parents=True, exist_ok=True)
    for path, value in ((DINGTALK_CONFIG, {"base_id": "", "tables": {"policy": "", "enterprise": "", "match": ""}}),
                        (DINGTALK_USERS, {"_说明": "按企业通知人映射已确认的 userId；不得设置默认收件人"})):
        if not Path(path).exists():
            setup_state.atomic_json(path, value)
    print("钉钉本地组件已准备；由千问办公继续绑定三张表和企业负责人。")


def status(as_json=False, checkpoint=False):
    from onboarding import report, print_report
    value = report()
    if checkpoint:
        setup_state.atomic_json(setup_state.data_dir() / "setup_report.json", value)
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print_report(value)
    return 0 if value["complete"] else 2


def main(argv=None):
    ap = argparse.ArgumentParser(description="首次引导、状态检查和恢复入口")
    ap.add_argument("--mode", choices=["local", "feishu", "dingtalk"])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--json", action="store_true", help="结构化状态，待完成返回退出码 2")
    ap.add_argument("--checkpoint", action="store_true", help="保存可恢复的当前检查报告")
    ap.add_argument("--notifications", choices=["on", "off"], help="保存用户选定的通知偏好，不实际发送")
    ap.add_argument("--schedule", choices=["on", "off"], help="保存用户选定的定时偏好，不创建任务")
    ap.add_argument("--record", choices=setup_state.STAGES)
    ap.add_argument("--evidence", help="实际验证回执 JSON，格式见 references/onboarding.md")
    args = ap.parse_args(argv)
    try:
        if args.mode:
            {"local": init_local, "feishu": init_feishu, "dingtalk": init_dingtalk}[args.mode]()
        if args.notifications or args.schedule:
            saved = setup_state.load_state()
            for key, value in (("notifications", args.notifications), ("schedule", args.schedule)):
                if value is not None:
                    saved["preferences"][key] = value == "on"
            setup_state.save_state(saved)
        if args.record:
            if not args.evidence:
                ap.error("--record 必须同时提供 --evidence")
            setup_state.record(args.record, json.loads(Path(args.evidence).read_text(encoding="utf-8-sig")))
        if args.status or args.json or args.checkpoint or not any((args.mode, args.record, args.notifications, args.schedule)):
            return status(args.json, args.checkpoint)
        return 0
    except (OSError, ValueError, ImportError) as exc:
        print(f"接入未完成：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
