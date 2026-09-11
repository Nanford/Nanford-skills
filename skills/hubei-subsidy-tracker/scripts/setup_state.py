"""Persistent setup receipts. Configuration changes invalidate relevant checks."""
import datetime as dt
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGES = ("collection", "matching", "tables", "notification", "schedule")


def data_dir():
    return Path(os.environ.get("SUBSIDY_DATA_DIR") or ROOT / "data").resolve()


def config_path():
    return Path(os.environ.get("SUBSIDY_CONFIG_FILE") or ROOT / "config.env").resolve()


def read_config():
    cfg = {}
    if config_path().exists():
        for line in config_path().read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                cfg[key.strip()] = value.strip().strip("\"'")
    for key, value in os.environ.items():
        if key.startswith("FEISHU_") or key == "SKILL_MODE":
            cfg[key] = value
    return cfg


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_state():
    path = data_dir() / "setup_state.json"
    if not path.exists():
        return {"schema_version": 1, "preferences": {"notifications": False, "schedule": False}, "receipts": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("setup_state.json 格式不受支持，请保留原文件后修复")
    if not isinstance(state.get("preferences"), dict) or not isinstance(state.get("receipts"), dict):
        raise ValueError("setup_state.json 缺少 preferences 或 receipts")
    return state


def save_state(state):
    atomic_json(data_dir() / "setup_state.json", state)


def context(stage):
    # Store hashes, never credentials or financial data, in the setup receipts.
    parts = [str(data_dir()), stage]
    if stage == "schedule":
        parts.append(str(ROOT))
    if stage in ("tables", "notification", "schedule"):
        parts.append(json.dumps(read_config(), sort_keys=True, ensure_ascii=False))
    files = {
        "collection": ["subsidy_records.xlsx", "collection_report.json"],
        "matching": ["enterprises.xlsx", "subsidy_records.xlsx", "match_results.xlsx"],
        "tables": ["dingtalk_config.json"],
        "notification": ["dingtalk_config.json", "dingtalk_notify_users.json", "enterprises.xlsx"],
        "schedule": ["dingtalk_config.json", "schedule_registration.json"],
    }
    for name in files[stage]:
        path = data_dir() / name
        if path.exists() and ((stage == "notification" and name == "enterprises.xlsx") or name == "match_results.xlsx"):
            from onboarding import workbook_rows
            columns = ("企业名称", "通知人") if stage == "notification" else ("政策ID", "企业名称", "匹配结论", "命中条件", "缺口", "建议动作", "可通知")
            try:
                values = [tuple(str(row.get(col) or "").strip() for col in columns) for row in workbook_rows(path)]
                parts.append(json.dumps(sorted(values), ensure_ascii=False))
            except (OSError, ValueError, ImportError, zipfile.BadZipFile):
                parts.append("unreadable")
        else:
            parts.append(hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def record(stage, evidence):
    if stage not in STAGES:
        raise ValueError("未知验证步骤")
    if not isinstance(evidence, dict) or evidence.get("success") is not True:
        raise ValueError("只接受实际成功的验证回执")
    if evidence.get("context") != context(stage):
        raise ValueError("验证上下文已变化，请重新验证")
    if not isinstance(evidence.get("observed_at"), str):
        raise ValueError("回执缺少有效验证时间")
    stamp = dt.datetime.fromisoformat(evidence["observed_at"])
    if stamp.tzinfo is None:
        raise ValueError("回执时间必须包含时区")
    age = (dt.datetime.now(dt.timezone.utc) - stamp).total_seconds()
    if not 0 <= age <= 86400:
        raise ValueError("回执已过期或时间无效，请重新验证")
    reference = evidence.get("reference")
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("回执缺少本地验证报告或平台业务回执编号")
    state = load_state()
    state["receipts"][stage] = {key: evidence[key] for key in ("success", "context", "observed_at", "reference")}
    save_state(state)


def record_local(stage, reference):
    record(stage, {"success": True, "context": context(stage),
                   "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "reference": reference})


def verified(stage, state=None):
    receipt = (state or load_state())["receipts"].get(stage, {})
    return bool(isinstance(receipt, dict) and receipt.get("success") is True and receipt.get("context") == context(stage))


def invalidate(stage):
    state = load_state()
    state["receipts"].pop(stage, None)
    save_state(state)
