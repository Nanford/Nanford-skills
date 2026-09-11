"""Read-only readiness checks and resumable next actions for the host Agent."""
import importlib.util
import json
import platform
import sys
from pathlib import Path

import setup_state as state


def workbook_rows(path):
    if not Path(path).exists():
        return []
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(wb.active.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(v or "").strip() for v in rows[0]]
        return [dict(zip(headers, values)) for values in rows[1:] if any(v is not None for v in values)]
    finally:
        wb.close()


def configured(value):
    text = str(value or "").strip()
    return bool(text and not any(marker in text.lower() for marker in ("xxxx", "replace_me", "<", "…")))


def report():
    saved = state.load_state()
    cfg = state.read_config()
    mode = cfg.get("SKILL_MODE", "")
    data = state.data_dir()
    checks = []

    def add(key, label, ready, action, optional=False, detail=""):
        checks.append({"id": key, "label": label, "status": "ready" if ready else "optional" if optional else "pending",
                       "next_action": "" if ready or optional else action, "detail": detail})

    missing = [package for module, package in (("requests", "requests"), ("bs4", "beautifulsoup4"),
               ("lxml", "lxml"), ("openpyxl", "openpyxl")) if importlib.util.find_spec(module) is None]
    environment_ok = sys.version_info >= (3, 10) and not missing
    add("environment", "运行环境", environment_ok, "运行安装入口；Python 需为 3.10 或更新版本",
        detail="缺少依赖：" + ", ".join(missing) if missing else platform.system())
    add("mode", "使用方式", mode in ("local", "feishu", "dingtalk"), "确认使用方式并运行 init_setup.py --mode 对应模式")
    add("storage", "数据目录", all((data / name).is_dir() for name in ("logs", "company_docs")), "运行 install.py 初始化目录")

    rows, profile_error = [], ""
    if "openpyxl" not in missing:
        try:
            rows = workbook_rows(data / "enterprises.xlsx")
        except Exception as exc:
            profile_error = f"企业档案无法读取（{type(exc).__name__}）；关闭占用文件或修复格式"
    companies = [r for r in rows if str(r.get("企业名称") or "").strip()]
    incomplete = [{"enterprise": r["企业名称"], "missing": [f for f in ("注册地区", "行业") if not str(r.get(f) or "").strip()]}
                  for r in companies]
    incomplete = [r for r in incomplete if r["missing"]]
    names = [str(r["企业名称"]).strip() for r in companies]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    profile_ok = bool(companies) and not incomplete and not duplicates and not profile_error
    add("enterprise", "企业初筛档案", profile_ok, "补充企业名称、注册地区、主营行业；核对重复企业，财务与资质按政策逐步补充",
        detail=profile_error or f"{len(companies)} 家企业；{len(incomplete)} 家缺少基础信息；{len(duplicates)} 个重名")
    try:
        source_report = json.loads((data / "collection_report.json").read_text(encoding="utf-8"))
        source_ok = source_report.get("success") is True
    except (OSError, ValueError, AttributeError):
        source_ok = False
    collection_ok = environment_ok and source_ok and (data / "subsidy_records.xlsx").is_file() and state.verified("collection", saved)
    add("collection", "政策采集验证", collection_ok, "运行 run_daily.py --local-only，检查各源状态及报告")
    matching_ok = profile_ok and collection_ok and (data / "match_results.xlsx").is_file() and state.verified("matching", saved)
    add("matching", "企业匹配验证", matching_ok, "完成档案后运行 run_daily.py --local-only 并核对匹配结果")

    channel_configured, detail = True, "本地模式无需平台连接"
    if mode == "feishu":
        channel_configured = all(configured(cfg.get(k)) for k in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_BASE_URL"))
        detail = "凭证与表格位置需通过实际读写验证"
    elif mode == "dingtalk":
        try:
            config = json.loads((data / "dingtalk_config.json").read_text(encoding="utf-8"))
            channel_configured = configured(config.get("base_id")) and all(
                configured(config.get("tables", {}).get(k)) for k in ("policy", "enterprise", "match"))
        except (OSError, ValueError, AttributeError):
            channel_configured = False
        detail = "由千问办公核验连接器、三表结构和受控写入；本机不推断宿主能力"
    tables_ok = mode == "local" or (channel_configured and state.verified("tables", saved))
    add("tables", "协作表格验证", tables_ok, "绑定表格并完成实际读写验证，记录 tables 回执", detail=detail)

    notify_enabled = saved["preferences"].get("notifications") is True
    route_ok = False
    if mode == "feishu":
        route_ok = configured(cfg.get("FEISHU_WEBHOOK"))
    elif mode == "dingtalk":
        try:
            users = json.loads((data / "dingtalk_notify_users.json").read_text(encoding="utf-8"))
            route_ok = bool(companies) and all(
                configured(users.get(str(r.get("通知人") or "").strip(), {}).get("userId"))
                if isinstance(users.get(str(r.get("通知人") or "").strip()), dict)
                else configured(users.get(str(r.get("通知人") or "").strip())) for r in companies)
        except (OSError, ValueError, AttributeError):
            route_ok = False
    notify_ok = profile_ok and tables_ok and route_ok and state.verified("notification", saved)
    add("notification", "通知验证", notify_ok, "确认通知范围、收件人并测试发送，记录 notification 回执",
        optional=not notify_enabled, detail="未启用" if not notify_enabled else "飞书为群级播报；钉钉按企业负责人映射")
    scheduled = saved["preferences"].get("schedule") is True
    schedule_ok = state.verified("schedule", saved)
    add("schedule", "定时验证", schedule_ok, "核验任务存在、时间与最近执行结果，记录 schedule 回执", optional=not scheduled)
    pending = [c for c in checks if c["status"] == "pending"]
    return {"schema_version": 1, "mode": mode, "data_dir": str(data), "complete": not pending,
            "capabilities": {"query": collection_ok, "match": matching_ok,
                             "notify": notify_enabled and notify_ok, "scheduled": scheduled and schedule_ok},
            "checks": checks, "profile_gaps": incomplete, "duplicate_enterprises": duplicates,
            "next_action": pending[0] if pending else None,
            "contexts": {step: state.context(step) for step in state.STAGES}}


def print_report(value):
    for check in value["checks"]:
        label = {"ready": "已验证", "pending": "待完成", "optional": "未启用"}[check["status"]]
        print(f"[{label}] {check['label']}" + (f"：{check['detail']}" if check['detail'] else ""))
    if value["next_action"]:
        print("下一步：" + value["next_action"]["next_action"])
    else:
        print("所选功能的接入验证已完成。")
