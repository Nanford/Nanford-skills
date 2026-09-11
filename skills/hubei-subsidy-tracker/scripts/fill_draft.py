#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
申报填报草稿生成器 (Skill 阶段5)
=================================================================
输入: 政策(序号或标题) + 企业名称 + 本地政策表/企业档案 + 已抓取的正文
输出: drafts/<政策>_<企业>.md (可再转 docx), 列出每字段的"政策要求 / 企业现状 / 待填"

边界: 仅生成草稿, 最终以人工审核为准(合规, 不自动提交)。
用法:
  python fill_draft.py --policy 12 --enterprise "武汉某某智能科技" --out drafts/
  python fill_draft.py --policy "工业软件券" --enterprise "武汉某某" --docx
依赖: openpyxl (python-docx 可选, 用于导出 docx)
"""
import os, re, sys, argparse
import openpyxl

DATA_DIR = os.environ.get("SUBSIDY_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CONTENT_DIR = os.path.join(DATA_DIR, "content")

THRESHOLD_LABELS = [
    ("资质要求", "资质条件"), ("规模要求", "规模/营收"), ("财务要求", "财务要求"),
    ("社保要求", "社保要求"), ("人才要求", "人才要求"), ("行业要求", "行业要求"),
    ("地域要求", "地域要求"), ("申报材料", "申报材料"), ("支持额度", "支持额度"),
    ("申报对象", "申报对象"),
]
ENT_FIELDS = ["企业名称", "统一信用代码", "行业", "规模-营收", "规模-人数", "资质",
              "近一年营收", "纳税/利润", "研发费用", "社保人数", "人才类型",
              "注册地区", "通知人"]


def load_xlsx(path):
    if not os.path.exists(path):
        return []
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    hdr = list(rows[0])
    return [{hdr[i]: ("" if (i >= len(r) or r[i] is None) else r[i])
             for i in range(len(hdr))} for r in rows[1:]]


def find_policy(policies, key):
    key = str(key)
    for p in policies:
        if str(p.get("序号", "")).strip() == key:
            return p
    for p in policies:
        if key in str(p.get("标题", "")):
            return p
    return None


def find_enterprise(ents, name):
    for e in ents:
        if name in str(e.get("企业名称", "")) or str(e.get("企业名称", "")) in name:
            return e
    return None


def build_draft(policy, ent):
    pid = str(policy.get("序号", ""))
    lines = []
    lines.append(f"# 申报填报草稿 · {policy.get('标题','')}")
    lines.append("")
    lines.append("> 本草稿由系统根据政策要求与企业档案自动生成，仅供人工核对，**最终以人工审核为准**。")
    lines.append("")
    lines.append("## 一、政策概要")
    lines.append(f"- 政策标题：{policy.get('标题','')}")
    lines.append(f"- 发布部门：{policy.get('发布部门','')}（{policy.get('部门级别','')}）")
    lines.append(f"- 政策类别：{policy.get('政策类别','')}")
    lines.append(f"- 申报截止：{policy.get('申报截止') or '【待从正文/附件确认】'}")
    lines.append(f"- 支持额度：{policy.get('支持额度') or '【待确认】'}")
    lines.append(f"- 原文链接：{policy.get('原文链接','')}")
    lines.append("")
    lines.append("## 二、企业基本信息（来自档案）")
    for f in ENT_FIELDS:
        v = ent.get(f, "")
        lines.append(f"- {f}：{v or '【待填】'}")
    lines.append("")
    lines.append("## 三、硬性条件对照")
    for pfield, label in THRESHOLD_LABELS:
        req = policy.get(pfield, "")
        if not req:
            continue
        # 在企业档案中找对应值
        ef = {"资质要求": "资质", "规模要求": "规模-营收", "财务要求": "纳税/利润",
              "社保要求": "社保人数", "人才要求": "人才类型", "行业要求": "行业",
              "地域要求": "注册地区", "申报材料": "", "支持额度": "", "申报对象": ""}.get(pfield, "")
        cur = ent.get(ef, "") if ef else "（见附件/材料）"
        lines.append(f"### {label}")
        lines.append(f"- 政策要求：{req}")
        lines.append(f"- 企业现状：{cur or '【待填/待核】'}")
        lines.append("")
    lines.append("## 四、申报材料清单（待准备/上传）")
    mats = policy.get("申报材料", "")
    if mats:
        for m in re.split(r'[；;]', mats):
            m = m.strip()
            if m:
                lines.append(f"- [ ] {m} → 【上传/准备】")
    else:
        lines.append("- 【待从政策正文/附件提取材料清单】")
    lines.append("")
    lines.append("## 五、待人工填写 / 待确认项")
    lines.append("- [ ] 申报截止日期（确认最新通知）")
    lines.append("- [ ] 附件中申请表各字段逐项填写")
    lines.append("- [ ] 资质/财务证明材料的真实性与时效性")
    lines.append("- [ ] 提交前由申报负责人复核")
    lines.append("")
    # 本地模式资料夹: data/company_docs/<企业名称>/ 下的原件清单
    docs_dir = os.path.join(DATA_DIR, "company_docs", str(ent.get("企业名称", "")).strip())
    lines.append("## 六、本地企业资料（company_docs）")
    if os.path.isdir(docs_dir):
        files = [f for f in sorted(os.listdir(docs_dir))
                 if os.path.isfile(os.path.join(docs_dir, f))]
        if files:
            for f in files:
                lines.append(f"- {f}")
        else:
            lines.append("- （文件夹为空，请放入营业执照/财报/资质证书等原件）")
    else:
        lines.append("- （无资料文件夹；本地模式建议建 data/company_docs/<企业名称>/ 放入原件）")
    lines.append("")
    lines.append("---")
    lines.append(f"_生成时间：{__import__('datetime').datetime.now():%Y-%m-%d %H:%M} · 政策ID={pid}_")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--enterprise", required=True)
    ap.add_argument("--policy-xlsx", default="subsidy_records.xlsx")
    ap.add_argument("--ent-xlsx", default="enterprises.xlsx")
    ap.add_argument("--out", default="drafts")
    ap.add_argument("--docx", action="store_true")
    args = ap.parse_args()

    ppath = args.policy_xlsx if os.path.isabs(args.policy_xlsx) else os.path.join(DATA_DIR, args.policy_xlsx)
    epath = args.ent_xlsx if os.path.isabs(args.ent_xlsx) else os.path.join(DATA_DIR, args.ent_xlsx)
    policies = load_xlsx(ppath)
    ents = load_xlsx(epath)
    policy = find_policy(policies, args.policy)
    if not policy:
        print(f"[!] 未找到政策: {args.policy}（可用序号或标题关键字）")
        return
    ent = find_enterprise(ents, args.enterprise)
    if not ent:
        print(f"[!] 未找到企业: {args.enterprise}（请先在 {epath} 录入）")
        return
    draft = build_draft(policy, ent)
    os.makedirs(args.out, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]', '_', f"{policy.get('序号','')}_{ent.get('企业名称','')}")
    md_path = os.path.join(args.out, f"{safe}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(draft)
    print(f"  草稿已生成: {md_path}")
    if args.docx:
        try:
            from docx import Document
            doc = Document()
            for line in draft.splitlines():
                doc.add_paragraph(line)
            dx = md_path[:-3] + ".docx"
            doc.save(dx)
            print(f"  已导出 docx: {dx}")
        except ImportError:
            print("  [提示] 未安装 python-docx，仅生成 md")


if __name__ == "__main__":
    main()
