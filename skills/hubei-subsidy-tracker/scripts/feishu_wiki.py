#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
湖北/武汉企业补贴 Skill · 飞书企业资料知识库（对应 SKILL.md §6）
=====================================================================
用法:
  python scripts/feishu_wiki.py --link <知识库页面URL>   # 登记资料库位置
  python scripts/feishu_wiki.py --init                  # 由应用创建知识库节点（best-effort）
  python scripts/feishu_wiki.py --sync                  # 按企业档案为每家企业建资料页(幂等)
  python scripts/feishu_wiki.py --status                # 显示登记状态

说明：本脚本复用 feishu_sync 的凭证/Token 加载逻辑。资料库 API 部分依赖真实
飞书凭证与「知识库」权限，未配置凭证时只会给出指引，不会报错中断。
"""
import os
import re
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.environ.get("SUBSIDY_DATA_DIR") or os.path.join(ROOT, "data")
CONFIG_ENV = os.environ.get("SUBSIDY_CONFIG_FILE") or os.path.join(ROOT, "config.env")

# 复用 feishu_sync 的凭证加载与 Token 获取
sys.path.insert(0, HERE)
from feishu_sync import load_config, get_token  # noqa: E402

BASE = "https://open.feishu.cn/open-apis"
WIKI_BASE = "https://open.feishu.cn/open-apis/wiki/v2"
TIMEOUT = 25


def set_config_key(key, value):
    """在 config.env 中设置/更新一个键值（不存在则创建文件）。"""
    lines = []
    if os.path.exists(CONFIG_ENV):
        lines = open(CONFIG_ENV, encoding="utf-8").read().splitlines()
    out, found = [], False
    for ln in lines:
        if ln.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"{key}={value}")
    with open(CONFIG_ENV, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def node_token_of(url):
    m = re.search(r'/wiki/([A-Za-z0-9]+)', url or "")
    return m.group(1) if m else ""


def link(url):
    if not url:
        print("[!] 请提供知识库页面 URL：--link <URL>")
        return
    tok = node_token_of(url)
    if not tok:
        print("[!] 无法从 URL 解析 wiki 节点，请确认是 https://*.feishu.cn/wiki/xxxx 形式")
        return
    set_config_key("FEISHU_WIKI_URL", url)
    print(f"[ok] 已登记知识库节点: {tok}（写入 config.env 的 FEISHU_WIKI_URL）")


def _hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _post(token, path, body):
    import requests
    r = requests.post(f"{WIKI_BASE}{path}", headers=_hdr(token),
                      json=body, timeout=TIMEOUT)
    return r.json()


def _get(token, path, params=None):
    import requests
    r = requests.get(f"{WIKI_BASE}{path}", headers=_hdr(token),
                     params=params, timeout=TIMEOUT)
    return r.json()


def resolve_space_and_parent(cfg, token):
    """从登记的 FEISHU_WIKI_URL 取得 space_id 与 parent_node_token。"""
    url = cfg.get("FEISHU_WIKI_URL", "")
    parent = node_token_of(url)
    # 通过节点详情拿 space_id
    d = _get(token, f"/nodes/{parent}")
    if d.get("code") != 0:
        raise RuntimeError(f"获取 wiki 节点失败: {d.get('msg')}")
    space_id = d.get("data", {}).get("node", {}).get("space_id", "")
    return space_id, parent


def init(cfg):
    """best-effort：校验凭证与节点，给出后续指引（真实建库需知识库写权限）。"""
    print("=== 知识库初始化（best-effort）===")
    if not (cfg.get("FEISHU_APP_ID") and cfg.get("FEISHU_APP_SECRET")):
        print("[!] 未配置飞书凭证，请先填 config.env（见 config.example.env）")
        return
    if not cfg.get("FEISHU_WIKI_URL"):
        print("[!] 尚未登记知识库：python scripts/feishu_wiki.py --link <URL>")
        return
    token = get_token(cfg)
    space_id, parent = resolve_space_and_parent(cfg, token)
    print(f"[ok] 凭证有效；知识库 space_id={space_id}，父节点={parent}")
    print("[提示] 资料页由 --sync 按企业档案批量创建（幂等）。")


def sync(cfg):
    """按企业档案为每家企业建一个资料页（幂等：已存在则跳过）。"""
    print("=== 按企业档案同步资料页 ===")
    if not (cfg.get("FEISHU_APP_ID") and cfg.get("FEISHU_APP_SECRET")):
        print("[!] 未配置飞书凭证，跳过")
        return
    if not cfg.get("FEISHU_WIKI_URL"):
        print("[!] 尚未登记知识库：--link <URL>")
        return

    import openpyxl
    ent_path = os.path.join(DATA_DIR, "enterprises.xlsx")
    if not os.path.exists(ent_path):
        print("[!] 未找到 enterprises.xlsx，跳过")
        return
    wb = openpyxl.load_workbook(ent_path)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h) for h in rows[0]]
    if "企业名称" not in hdr:
        print("[!] 企业档案缺少「企业名称」列")
        return
    ci = hdr.index("企业名称")
    companies = [str(r[ci]).strip() for r in rows[1:]
                 if r[ci] is not None and str(r[ci]).strip()]

    token = get_token(cfg)
    space_id, parent = resolve_space_and_parent(cfg, token)

    # 列出已存在子节点标题，做幂等判断
    existing = set()
    ch = _get(token, f"/nodes/{parent}/children", params={"page_size": 100})
    for it in ch.get("data", {}).get("items", []):
        existing.add(it.get("title", ""))

    created = skipped = 0
    for c in companies:
        if c in existing:
            skipped += 1
            continue
        d = _post(token, "/nodes",
                  {"space_id": space_id, "parent_node_token": parent,
                   "node_type": "doc", "title": c})
        if d.get("code") == 0:
            created += 1
            print(f"  [+] 已建资料页: {c}")
        else:
            print(f"  [!] 创建「{c}」失败: {d.get('msg')}")
    print(f"  资料页同步：新建 {created} / 已存在跳过 {skipped}")


def status(cfg):
    print("=== 知识库状态 ===")
    url = cfg.get("FEISHU_WIKI_URL", "")
    if url:
        print(f"  [ok] 已登记: {url}（节点 {node_token_of(url)}）")
    else:
        print("  [待办] 未登记知识库：--link <URL>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", help="登记知识库页面 URL")
    ap.add_argument("--init", action="store_true", help="初始化/校验知识库")
    ap.add_argument("--sync", action="store_true", help="按企业档案建资料页")
    ap.add_argument("--status", action="store_true", help="显示状态")
    args = ap.parse_args()
    cfg = load_config()

    if args.link:
        link(args.link)
    elif args.init:
        init(cfg)
    elif args.sync:
        sync(cfg)
    elif args.status:
        status(cfg)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
