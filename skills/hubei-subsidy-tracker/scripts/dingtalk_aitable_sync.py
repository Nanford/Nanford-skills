#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钉钉 AI 表格（多维表）同步与个人单聊通知 —— 计划生成器（hubei-subsidy-tracker 扩展）。

架构说明（重要）：
  本机 dws CLI 必须经由千问办公 host 端执行，独立进程/任务计划无法直接调用。
  因此本脚本不直接执行 dws，而是分三段工作，由千问办公 Agent 串起来：

    ① plan    读取本地 xlsx + Agent 预先导出的钉钉字段/记录快照，
               生成待执行命令清单 ops.json（含 record upsert 分片文件、单聊消息）。
    ② （Agent 执行 ops.json 中的 dws 命令，并记录通知发送结果 result.json）
    ③ mark    根据发送结果回写本地 xlsx 通知状态，并生成「通知状态=已推送」的 upsert 分片。

  日常自动化由千问办公定时任务驱动（Agent 每日执行同一序列）。

用法：
  python dingtalk_aitable_sync.py plan                 # 生成 data/dingtalk_ops/ops.json
  python dingtalk_aitable_sync.py plan --only sync     # 只生成同步命令；--only notify 只生成通知
  python dingtalk_aitable_sync.py pull-enterprises     # 钉钉企业档案快照 → 本地 enterprises.xlsx
  python dingtalk_aitable_sync.py mark --result result.json

Agent 需预先导出的快照（dws 命令输出原样保存）：
  data/dingtalk_dumps/policy_fields.json    = dws aitable table get --table-id <政策清单ID> --format json
  data/dingtalk_dumps/match_fields.json     = 同上（匹配结果表）
  data/dingtalk_dumps/enterprise_fields.json= 同上（企业档案表）
  data/dingtalk_dumps/policy_records.json   = dws aitable record query --table-id <政策清单ID> --all --format json
  data/dingtalk_dumps/match_records.json    = 同上（匹配结果表）
  data/dingtalk_dumps/enterprise_records.json = 同上（企业档案表，pull-enterprises 用）

操作人映射：企业档案“通知人”列表示每家企业的对应操作人；
data/dingtalk_notify_users.json 支持 {"张三": "userId123"} 文本模式，或
{"张三": {"userId": "...", "openDingTalkId": "..."}} 卡片模式，不支持固定或默认收件人。
安全默认：所有生成命令仅供 Agent 复核后执行；本脚本自身不做任何网络写入。
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path
from notification_ledger import Ledger

try:
    from openpyxl import load_workbook, Workbook
except ImportError:
    print("缺少依赖：请先 pip install openpyxl", file=sys.stderr)
    sys.exit(2)

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SUBSIDY_DATA_DIR") or (SKILL_DIR / "data"))
DUMPS_DIR = DATA_DIR / "dingtalk_dumps"
OPS_DIR = DATA_DIR / "dingtalk_ops"
CONFIG_PATH = DATA_DIR / "dingtalk_config.json"
NOTIFY_USERS_PATH = DATA_DIR / "dingtalk_notify_users.json"

KEEP_HUMAN_FIELDS = {"申报截止", "处理状态", "是否匹配", "备注", "通知状态"}
SUCCESS_NOTIFICATION_STATES = {"已推送", "已发送"}


# ---------------------------------------------------------------- 基础读取
def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def require_json(path, label):
    """Require a readable Agent-exported snapshot instead of guessing live state."""
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"缺少{label}快照：{p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label}快照不是有效 JSON：{p}") from exc


def load_config():
    cfg = load_json(CONFIG_PATH)
    tables = cfg.get("tables") if isinstance(cfg, dict) else None
    missing = [key for key in ("policy", "enterprise", "match")
               if not isinstance(tables, dict) or not tables.get(key)]
    if not isinstance(cfg, dict) or not cfg.get("base_id") or missing:
        raise RuntimeError(
            f"缺少配置 {CONFIG_PATH}（base_id + tables.policy/enterprise/match）"
        )
    return cfg


def sheet_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    out = []
    for r in rows[1:]:
        if all(c is None or str(c).strip() == "" for c in r):
            continue
        out.append({header[i]: r[i] for i in range(len(header)) if header[i]})
    return out


def save_cell(path, match_cols, match_vals, col, value):
    path = Path(path)
    if not path.exists():
        return False
    wb = load_workbook(path)
    ws = wb.worksheets[0]
    header = {str(c.value).strip(): i + 1 for i, c in enumerate(ws[1]) if c.value}
    col_idx = header.get(col)
    if not col_idx:
        wb.close()
        return False
    changed = False
    for row in ws.iter_rows(min_row=2):
        vals = {k: row[header[k] - 1].value for k in match_cols if k in header}
        if all(str(vals.get(k, "")).strip() == str(match_vals[k]).strip() for k in match_vals):
            if row[col_idx - 1].value != value:
                row[col_idx - 1].value = value
                changed = True
            break
    if changed:
        wb.save(path)
    wb.close()
    return changed


# ---------------------------------------------------------------- 快照解析
def parse_fields(dump):
    """table get 快照 → [{fieldId, fieldName, type}]"""
    data = (dump or {}).get("data") or {}
    tables = data.get("tables") or []
    for t in tables:
        if t.get("fields"):
            return t["fields"]
    return []


def parse_records(dump):
    """record query 快照 → [ {recordId, cells:{fieldName: plain}} ]"""
    data = (dump or {}).get("data") or {}
    recs = data.get("records") or data.get("items") or []
    return recs


def to_cell(field, value):
    if value is None:
        return None
    v = str(value).strip()
    if v == "" or v.lower() == "nan":
        return None
    t = field.get("type")
    if t == "number":
        try:
            n = float(v.replace(",", "").replace("，", ""))
            return int(n) if n.is_integer() else n
        except ValueError:
            return None
    if t == "date":
        m = re.match(r"(\d{4}-\d{1,2}-\d{1,2})", v)
        return m.group(1) if m else None
    if t == "multipleSelect":
        parts = [p.strip() for p in re.split(r"[,，、;；\n]+", v) if p.strip()]
        return parts or None
    return v


def cell_plain(field, value):
    if value is None or value == "":
        return ""
    t = field.get("type")
    if t == "multipleSelect":
        if isinstance(value, list):
            return "、".join(o.get("name") if isinstance(o, dict) else str(o) for o in value)
        return str(value)
    if t == "url":
        if isinstance(value, dict):
            return value.get("link") or value.get("text") or ""
        return str(value)
    if t == "number":
        try:
            n = float(value)
            return int(n) if n.is_integer() else n
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def cells_equal(field, old_value, new_value):
    """Compare DingTalk snapshot values with local values after type normalization."""
    field_type = field.get("type")
    if field_type == "multipleSelect":
        def tags(value):
            if isinstance(value, list):
                return sorted(str(item).strip() for item in value if str(item).strip())
            return sorted(part.strip() for part in re.split(r"[,，、;；\n]+", str(value or "")) if part.strip())
        return tags(old_value) == tags(new_value)
    if field_type == "number":
        try:
            return float(old_value) == float(new_value)
        except (TypeError, ValueError):
            return str(old_value or "").strip() == str(new_value or "").strip()
    return str(old_value or "").strip() == str(new_value or "").strip()


# ---------------------------------------------------------------- 计划生成
def build_upserts(base_id, table_id, fields_dump, records_dump, rows, key_of, tag_fields):
    """→ (payload_list, multi_tags, new_tags)。payload 带 recordId 走更新。"""
    fields = parse_fields(require_json(fields_dump, "字段"))
    if not fields:
        raise RuntimeError(f"字段快照未包含字段定义：{fields_dump}")
    by_name = {f["fieldName"]: f for f in fields}
    by_id = {f["fieldId"]: f for f in fields}
    existing = []
    for rec in parse_records(require_json(records_dump, "记录")):
        cells = rec.get("fields") or rec.get("cells") or {}
        plain = {by_id[fid]["fieldName"]: cell_plain(by_id[fid], v) for fid, v in cells.items() if fid in by_id}
        existing.append((rec.get("recordId"), plain))
    index = {key_of(p): (rid, p) for rid, p in existing if key_of(p)}

    multi_tags = {}
    payload = []
    n_new = n_upd = n_same = 0
    for row in rows:
        cells = {}
        for col, val in row.items():
            f = by_name.get(col)
            if not f:
                continue
            cv = to_cell(f, val)
            if cv is None:
                continue
            cells[f["fieldId"]] = cv
            if f["type"] == "multipleSelect":
                multi_tags.setdefault(col, set()).update(cv)
        key = key_of(row)
        if not key:
            continue
        old = index.get(key)
        if old is None:
            payload.append({"cells": cells, "_key": key, "_title": str(row.get("标题") or row.get("企业名称") or key)})
            n_new += 1
        else:
            rid, old_plain = old
            patch = {}
            for fid, val in cells.items():
                fname = by_id[fid]["fieldName"]
                old_value = old_plain.get(fname)
                if fname in KEEP_HUMAN_FIELDS and old_value not in ("", None):
                    continue
                if not cells_equal(by_id[fid], old_value, val):
                    patch[fid] = val
            if patch:
                payload.append({"recordId": rid, "cells": patch, "_key": key})
                n_upd += 1
            else:
                n_same += 1
    return fields, payload, multi_tags, (n_new, n_upd, n_same)


def norm_key_link(row):
    return str(row.get("原文链接") or "").strip() or None


def norm_key_pe(row):
    pid = str(row.get("政策ID") or "").strip()
    ent = str(row.get("企业名称") or "").strip()
    return f"{pid}|{ent}" if pid and ent else None


def norm_ent(row):
    ent = str(row.get("企业名称") or "").strip()
    return ent or None


def operator_name(enterprise_row):
    """Return the enterprise-specific operator; never fall back to a global recipient."""
    return str((enterprise_row or {}).get("操作人")
               or (enterprise_row or {}).get("通知人") or "").strip()


def _as_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    match = re.match(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})", str(value or "").strip())
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def policy_is_active(row, today=None):
    today = today or datetime.date.today()
    if str(row.get("政策状态") or "").strip() in {"已过期", "已失效", "无效", "废止"}:
        return False
    deadline = _as_date(row.get("申报截止"))
    return not deadline or deadline >= today


def notification_identity(value):
    """兼容旧字符串 userId 和卡片模式的双 ID 映射。"""
    if isinstance(value, dict):
        return (str(value.get("userId") or "").strip(),
                str(value.get("openDingTalkId") or "").strip())
    return str(value or "").strip(), ""


def remote_notified_keys():
    """以远端快照为第二道幂等锁，避免本地状态丢失后重复通知。"""
    fields_path = DUMPS_DIR / "match_fields.json"
    records_path = DUMPS_DIR / "match_records.json"
    if not fields_path.exists() or not records_path.exists():
        return set()
    fields = parse_fields(require_json(fields_path, "匹配表字段"))
    by_id = {f["fieldId"]: f for f in fields}
    keys = set()
    for rec in parse_records(require_json(records_path, "匹配表记录")):
        cells = rec.get("fields") or rec.get("cells") or {}
        plain = {by_id[fid]["fieldName"]: cell_plain(by_id[fid], value)
                 for fid, value in cells.items() if fid in by_id}
        if str(plain.get("通知状态") or "").strip() in SUCCESS_NOTIFICATION_STATES:
            key = norm_key_pe(plain)
            if key:
                keys.add(key)
    return keys


def match_table_link(cfg):
    base_id = cfg["base_id"]
    table_id = cfg["tables"]["match"]
    view_id = ""
    dump = load_json(DUMPS_DIR / "match_fields.json", {}) or {}
    for table in ((dump.get("data") or {}).get("tables") or []):
        views = table.get("views") or []
        if views:
            view_id = str(views[0].get("viewId") or "").strip()
            break
    link = f"https://alidocs.dingtalk.com/i/nodes/{base_id}?entrance=data&sheetId={table_id}"
    return link + (f"&viewId={view_id}" if view_id else "")


def card_content(enterprise, policy, match_row, table_link):
    title = str(policy.get("标题") or ("政策" + str(match_row.get("政策ID") or ""))).strip()
    source = str(policy.get("原文链接") or "").strip()
    conclusion = str(match_row.get("匹配结论") or "").strip()
    hits = str(match_row.get("命中条件") or "").strip()
    lines = ["### 惠企政策匹配通知", f"**企业名称**：{enterprise}"]
    lines.append(f"**匹配政策**：[{title}]({source})" if source else f"**匹配政策**：{title}")
    lines.append(f"**匹配度**：{conclusion}" + (f"（命中：{hits}）" if hits else ""))
    key_info = []
    amount = str(policy.get("支持额度") or "").strip()
    deadline = str(policy.get("申报截止") or "").strip()
    if amount:
        key_info.append(f"补贴金额：{amount}")
    if deadline:
        key_info.append(f"申报截止：{deadline}")
    if key_info:
        lines.append("**关键信息**：" + "；".join(key_info))
    links = []
    if source:
        links.append(f"[查看政策原文]({source})")
    links.append(f"[打开匹配结果表]({table_link})")
    lines.append("**快捷入口**：" + " ｜ ".join(links))
    lines.append("简介与材料为自动解析结果，最终申报请以政策原文人工核验为准。")
    return "\n\n".join(lines)


def text_fallback_content(enterprise, policy, match_row, table_link):
    content = card_content(enterprise, policy, match_row, table_link)
    materials = str(policy.get("申报材料") or "").strip()
    gaps = str(match_row.get("缺口") or "").strip()
    if materials:
        content += f"\n\n**申报材料**：{materials}"
    if gaps:
        content += f"\n\n**人工核对项**：{gaps}"
    return content


def cmd_plan(cfg, args):
    base_id = cfg["base_id"]
    tables = cfg["tables"]
    OPS_DIR.mkdir(parents=True, exist_ok=True)
    ops = {"base_id": base_id, "commands": [], "notify": []}
    only = args.only

    def add_chunk(table_id, payload, label):
        if not payload:
            return
        for i in range(0, len(payload), 30):
            chunk = payload[i:i + 30]
            for item in chunk:
                item.pop("_key", None)
                item.pop("_title", None)
            f = OPS_DIR / f"upsert_{label}_{i // 30:03d}.json"
            f.write_text(json.dumps(chunk, ensure_ascii=False), encoding="utf-8")
            ops["commands"].append({
                "desc": f"upsert {label} 第{i // 30 + 1}批（{len(chunk)} 条）",
                "argv": ["dws", "aitable", "record", "upsert", "--base-id", base_id,
                         "--table-id", table_id, "--records-file", str(f), "--format", "json"],
            })

    if only in ("sync", "all"):
        # 政策清单
        active_policy_rows = [row for row in sheet_rows(DATA_DIR / "subsidy_records.xlsx")
                              if policy_is_active(row)]
        fields, payload, tags, (a, b, c) = build_upserts(
            base_id, tables["policy"],
            DUMPS_DIR / "policy_fields.json", DUMPS_DIR / "policy_records.json",
            active_policy_rows, norm_key_link, ["关键词标签"])
        add_chunk(tables["policy"], payload, "policy")
        print(f"政策清单：新增 {a}，更新 {b}，无变化 {c}")
        if tags:
            ops["option_extensions"] = {t: sorted(v) for t, v in tags.items()}
        # 匹配结果
        fields_m, payload_m, tags_m, (a, b, c) = build_upserts(
            base_id, tables["match"],
            DUMPS_DIR / "match_fields.json", DUMPS_DIR / "match_records.json",
            sheet_rows(DATA_DIR / "match_results.xlsx"), norm_key_pe, [])
        add_chunk(tables["match"], payload_m, "match")
        print(f"匹配结果：新增 {a}，更新 {b}，无变化 {c}")
        # 企业档案（本地→钉钉，建档/补录用）
        if getattr(args, "push_enterprises", False):
            fields_e, payload_e, tags_e, (a, b, c) = build_upserts(
                base_id, tables["enterprise"],
                DUMPS_DIR / "enterprise_fields.json", DUMPS_DIR / "enterprise_records.json",
                sheet_rows(DATA_DIR / "enterprises.xlsx"), norm_ent, [])
            add_chunk(tables["enterprise"], payload_e, "ent")
            print(f"企业档案：新增 {a}，更新 {b}，无变化 {c}")

    if only in ("notify", "all"):
        policy_rows = sheet_rows(DATA_DIR / "subsidy_records.xlsx")
        ent_rows = sheet_rows(DATA_DIR / "enterprises.xlsx")
        match_rows = sheet_rows(DATA_DIR / "match_results.xlsx")
        users = load_json(NOTIFY_USERS_PATH, {}) or {}
        policy_by_id = {str(int(float(r["序号"]))): r for r in policy_rows if r.get("序号") not in (None, "")}
        ent_operators = {str(r.get("企业名称") or "").strip(): operator_name(r) for r in ent_rows}
        new_active_ids = {str(int(float(r["序号"]))) for r in policy_rows
                          if r.get("序号") not in (None, "")
                          and policy_is_active(r)}
        pushed_remote = remote_notified_keys()
        blocked = Ledger(DATA_DIR).blocked()
        table_link = match_table_link(cfg)
        pending = []
        for r in match_rows:
            pid = str(r.get("政策ID") or "").strip().split(".")[0]
            ent = str(r.get("企业名称") or "").strip()
            match_key = f"{pid}|{ent}"
            if (pid in new_active_ids
                    and str(r.get("匹配结论") or "").strip() == "匹配"
                    and str(r.get("可通知") or "").strip() == "是"
                    and str(r.get("通知状态") or "").strip() not in SUCCESS_NOTIFICATION_STATES
                    and match_key not in pushed_remote
                    and match_key not in blocked):
                pending.append((ent, pid, match_key, r))
        if not pending:
            print("匹配通知：当前无可自动发送的匹配记录；发送结果不明项请查看通知台账")
        for ent, pid, match_key, match_row in pending:
            operator = ent_operators.get(ent, "")
            if not operator:
                print(f"  [缺操作人] {ent}：企业档案“通知人”列为空")
                continue
            uid, open_id = notification_identity(users.get(operator))
            if not uid and not open_id:
                print(f"  [缺映射] {ent}：操作人「{operator}」不在 dingtalk_notify_users.json")
                continue
            policy = policy_by_id.get(pid, {})
            title = str(policy.get("标题") or ("政策" + pid)).strip()
            content = card_content(ent, policy, match_row, table_link)
            fallback = text_fallback_content(ent, policy, match_row, table_link)
            mode = "card" if open_id else "text"
            entry = {
                "mode": mode,
                "enterprise": ent,
                "policy_id": pid,
                "match_key": match_key,
                "reserve_argv": [sys.executable, str(SKILL_DIR / "scripts" / "notification_ledger.py"),
                                 "reserve", "--keys", match_key],
                "operator": operator,
                "notify_user": operator,
                "user_id": uid,
                "open_dingtalk_id": open_id,
                "title": f"惠企政策匹配提醒：{title}",
                "content": content,
                "argv": (["dws", "chat", "message", "send-card", "--receiver", open_id,
                          "--format", "json"] if open_id else
                         ["dws", "chat", "message", "send", "--user", uid,
                          "--title", f"惠企政策匹配提醒：{title}", "--content", fallback,
                          "--format", "json"]),
                "argv_update": (["dws", "chat", "message", "update-card", "--biz-id", "{{BIZ_ID}}",
                                 "--content", content, "--flow-status", "3", "--format", "json"]
                                if open_id else []),
                "argv_text": (["dws", "chat", "message", "send", "--user", uid,
                               "--title", f"惠企政策匹配提醒：{title}", "--content", fallback,
                               "--format", "json"] if uid else []),
                "runbook": ("先执行 reserve_argv，成功后才发送。执行 argv 后从 result.bizId 取值替换 argv_update 中的 {{BIZ_ID}}；"
                            "update-card 成功且 flow-status=3 后才把 match_key 写入 result.json。"
                            "每条成功后立即执行 mark。超时或业务结果不明时停止并核对；"
                            "仅明确未送达且 user_id 可用时执行 argv_text 兜底。"),
            }
            ops["notify"].append(entry)
            print(f"  通知 → 操作人 {operator}（{ent}）：{title} [{mode}]")

        ops["notify_hint"] = (
            "notify 每项对应一个有效政策与企业的待通知组合，包含隔天补档结果。先执行 reserve_argv；card 模式执行 argv，取 result.bizId 替换 argv_update 的"
            " {{BIZ_ID}}，再执行 argv_update；flow-status 必须为 3。只有最终发送成功的 match_key"
            " 才能写入 result.json 的 notified。text 模式执行 argv；禁止重发已成功项。"
        )

    out = OPS_DIR / "ops.json"
    out.write_text(json.dumps(ops, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已生成 {out}")
    print(f"待执行 dws 命令 {len(ops['commands'])} 条，待发单聊 {len(ops['notify'])} 条")
    print("下一步：由千问办公 Agent 逐条执行 ops.json 中的命令，"
          "通知成功后把 {\"notified\": [\"政策ID|企业名称\", ...]} 写入 result.json 并运行 mark。")


def cmd_mark(cfg, args):
    result = load_json(args.result, {}) or {}
    notified = set(result.get("notified") or [])
    if not notified:
        print("result.json 中无 notified 记录，无需回写")
        return
    # The delivery receipt survives an Excel lock or a later remote write failure.
    Ledger(DATA_DIR).finish(notified, str(Path(args.result).name))
    match_xlsx = DATA_DIR / "match_results.xlsx"
    fields = parse_fields(require_json(DUMPS_DIR / "match_fields.json", "匹配表字段"))
    by_name = {f["fieldName"]: f for f in fields}
    if "通知状态" not in by_name:
        raise RuntimeError("匹配表字段快照缺少“通知状态”字段")
    recs = parse_records(require_json(DUMPS_DIR / "match_records.json", "匹配表记录"))
    by_id = {f["fieldId"]: f for f in fields}
    payload = []
    for rec in recs:
        cells = rec.get("fields") or rec.get("cells") or {}
        plain = {by_id[fid]["fieldName"]: cell_plain(by_id[fid], v) for fid, v in cells.items() if fid in by_id}
        key = f"{plain.get('政策ID', '').strip()}|{str(plain.get('企业名称') or '').strip()}"
        if key in notified and str(plain.get("通知状态") or "").strip() != "已推送":
            payload.append({"recordId": rec.get("recordId"),
                            "cells": {by_name["通知状态"]["fieldId"]: "已推送"}})
    if payload:
        OPS_DIR.mkdir(parents=True, exist_ok=True)
        f = OPS_DIR / "upsert_notified.json"
        f.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"已生成 {f}（{len(payload)} 条）：")
        print(f"  dws aitable record upsert --base-id {cfg['base_id']} "
              f"--table-id {cfg['tables']['match']} --records-file \"{f}\" --format json")
    n_local = 0
    for key in notified:
        pid, _, ent = key.partition("|")
        if save_cell(match_xlsx, ["政策ID", "企业名称"],
                     {"政策ID": pid, "企业名称": ent}, "通知状态", "已推送"):
            n_local += 1
    print(f"本地 xlsx 通知状态已回写 {n_local} 条")


def cmd_pull(cfg, args):
    fields = parse_fields(require_json(DUMPS_DIR / "enterprise_fields.json", "企业表字段"))
    if not fields:
        raise RuntimeError("企业表字段快照未包含字段定义")
    names = [f["fieldName"] for f in fields]
    by_id = {f["fieldId"]: f for f in fields}
    rows = []
    records_dump = require_json(DUMPS_DIR / "enterprise_records.json", "企业表记录")
    for rec in parse_records(records_dump):
        cells = rec.get("fields") or rec.get("cells") or {}
        row = {}
        for fid, val in cells.items():
            f = by_id.get(fid)
            if f:
                row[f["fieldName"]] = cell_plain(f, val)
        rows.append(row)
    wb = Workbook()
    ws = wb.worksheets[0]
    ws.append(names)
    for r in rows:
        ws.append([r.get(n, "") for n in names])
    out = DATA_DIR / "enterprises.xlsx"
    wb.save(out)
    wb.close()
    print(f"企业档案已拉回：{len(rows)} 家 → {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="钉钉 AI 表格同步计划生成器")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("plan", help="生成 ops.json（upsert 分片 + 单聊通知命令）")
    p1.add_argument("--only", choices=["sync", "notify", "all"], default="all")
    p1.add_argument("--push-enterprises", action="store_true", help="同步把本地企业档案推送到钉钉（建档用）")
    p2 = sub.add_parser("mark", help="按发送结果回写通知状态")
    p2.add_argument("--result", required=True, help='结果 JSON：{"notified": ["政策ID|企业名称", ...]}')
    p3 = sub.add_parser("pull-enterprises", help="钉钉企业档案快照 → 本地 enterprises.xlsx")
    args = ap.parse_args(argv)
    try:
        cfg = load_config()
        if args.cmd == "plan":
            cmd_plan(cfg, args)
        elif args.cmd == "mark":
            cmd_mark(cfg, args)
        elif args.cmd == "pull-enterprises":
            cmd_pull(cfg, args)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
