# -*- coding: utf-8 -*-
"""
INPUT: draft.md + skeleton.md（extract_doc --skeleton 或人工补全的标题树）
OUTPUT: 结构一致性报告；缺章/乱序为错误（退出码 1），仅顺序轻微差异可警告
POS: bid-document-builder 成稿前结构门禁——保证草稿标题树覆盖参考骨架

用法:
    python structure_check.py draft.md --skeleton skeleton.md
"""
from __future__ import annotations

import argparse
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HEADING = re.compile(r"^(#{1,4})\s+(.*)")
RED_MARK = re.compile(r"\{\{RED:(.*?)\}\}", re.S)
COVER_BLOCK = re.compile(r"\{\{COVER\}\}(.*?)\{\{/COVER\}\}", re.S)
# 一级章：第X章 / 一、二、… —— 顺序与覆盖按此类强制校验
PRIMARY = re.compile(
    r"^(第[一二三四五六七八九十百零〇0-9]+[章节部分篇]"
    r"|[一二三四五六七八九十百]+[、．.])"
)
MODULE_HINT = re.compile(r"前附表|附件|声明|开标记录|采购内容|项目概况内容")


def norm_title(s: str) -> str:
    s = RED_MARK.sub(lambda m: m.group(1), s)
    s = re.sub(r"\*\*|`", "", s)  # 行内 markdown 符不参与标题比对，避免加粗标题误报缺章
    s = re.sub(r"\s+", "", s)
    s = s.replace("（", "(").replace("）", ")")
    return s.strip()


def extract_draft_headings(text: str) -> list[str]:
    # 去掉 cover 块内内容，避免封面行干扰
    text = COVER_BLOCK.sub("", text)
    titles = []
    for line in text.splitlines():
        m = HEADING.match(line.strip())
        if m:
            t = m.group(2).strip()
            if t:
                titles.append(t)
    return titles


def extract_skeleton_headings(text: str) -> list[str]:
    """skeleton.md：仅读取「## 标题树」分区内的 # / ## 标题"""
    titles = []
    in_tree = False
    has_tree_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## 标题树"):
            in_tree = True
            has_tree_section = True
            continue
        if in_tree and (
            stripped.startswith("## 必检")
            or stripped.startswith("## 人工")
            or stripped.startswith("---")
        ):
            # 仅在明确的下一分区结束标题树（模块标题也用 ## 书写，不能一见 ## 就断）
            break
        if not in_tree:
            continue
        if stripped.startswith("- [") or stripped.startswith("* ["):
            continue  # 勾选列表
        m = HEADING.match(stripped)
        if m:
            t = m.group(2).strip()
            if t and t not in ("参考文件结构骨架",):
                titles.append(t)
            continue
        m3 = re.match(r"^[-*]\s+(.+)$", stripped)
        if m3:
            t = m3.group(1).strip()
            if t and not t.startswith("封面") and "必检" not in t:
                titles.append(t)
    # 若未写「标题树」分区，退化为全文 markdown 标题（跳过文档总题）
    if not has_tree_section and not titles:
        titles = [t for t in extract_draft_headings(text) if t != "参考文件结构骨架"]
    return titles


def check_modules(draft: str) -> list[str]:
    """六大必检模块启发式"""
    missing = []
    has_cover = bool(COVER_BLOCK.search(draft)) or ("招标文件" in draft[:800] and re.search(r"招标人|采购人", draft[:1200]))
    if not has_cover:
        missing.append("封面（建议使用 {{COVER}}…{{/COVER}}）")
    if "{{TOC}}" not in draft and "目录" not in draft[:2000]:
        missing.append("目录（建议使用 {{TOC}}）")
    # 招标信息
    if not re.search(r"招标公告|投标邀请|项目须知|须知前附表|采购内容及分包", draft):
        missing.append("招标信息（公告/须知/前附表/采购内容）")
    if not re.search(r"采购需求|发包人要求|招标内容|技术标准与要求|技术要求", draft):
        missing.append("采购需求/发包人要求/技术标准")
    if not re.search(r"评标|评分|定标", draft):
        missing.append("评标办法及标准")
    if not re.search(r"合同|投标文件格式|响应文件|其他附件", draft):
        missing.append("合同或投标/响应格式/附件")
    return missing


def longest_common_subsequence(a: list[str], b: list[str]) -> int:
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[n][m]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft", help="中间稿 draft.md")
    ap.add_argument("--skeleton", required=True, help="skeleton.md")
    args = ap.parse_args()

    with open(args.draft, encoding="utf-8") as f:
        draft = f.read()
    with open(args.skeleton, encoding="utf-8") as f:
        skeleton = f.read()

    sk_all = extract_skeleton_headings(skeleton)
    dr = extract_draft_headings(draft)
    # 强制校验只用一级章；前附表/附件等为附属（缺失仅警告）
    sk_primary_raw = [t for t in sk_all if PRIMARY.match(t.strip())]
    sk_modules = [t for t in sk_all if t not in sk_primary_raw]

    def primary_key(title: str) -> str:
        """同一章的「第六章」与「第六章（如有）」合并为同一校验键"""
        n = norm_title(title)
        m = re.match(
            r"^(第[一二三四五六七八九十百零〇0-9]+[章节部分篇]"
            r"|[一二三四五六七八九十百]+[、．.])",
            n,
        )
        return m.group(1) if m else n

    # 一级章按章号去重（保留首次，丢掉 TOC/正文重复与「如有」变体）
    seen_pk: set[str] = set()
    sk_primary: list[str] = []
    for t in sk_primary_raw:
        if "如有" in t:
            continue
        pk = primary_key(t)
        if pk in seen_pk:
            continue
        seen_pk.add(pk)
        sk_primary.append(t)
    sk = sk_primary if sk_primary else sk_all

    sk_n = [norm_title(x) for x in sk]
    dr_n = [norm_title(x) for x in dr]

    errors: list[str] = []
    warnings: list[str] = []

    if not sk_n:
        errors.append("skeleton 未解析到任何标题，请检查 skeleton.md 格式")
    if not dr_n:
        errors.append("draft 未解析到任何 # 标题，请用 Markdown 标题标记章节")

    sk_set = set(sk_n)
    dr_set = set(dr_n)

    def fuzzy_hit(title: str) -> bool:
        nt = norm_title(title)
        return any(k in nt or nt in k for k in dr_n)

    missing = [sk[i] for i, k in enumerate(sk_n) if k not in dr_set]
    for t in missing:
        if fuzzy_hit(t):
            warnings.append(f"一级章未精确命中（可能已改写）: {t}")
            continue
        if "如有" in t:
            warnings.append(f"可选骨架未命中: {t}")
            continue
        errors.append(f"草稿缺少一级章: {t}")

    for t in sk_modules:
        if norm_title(t) in dr_set or fuzzy_hit(t):
            continue
        if MODULE_HINT.search(t) or re.search(r"附件|声明", t):
            warnings.append(f"附属模块未单列: {t}")
        else:
            warnings.append(f"骨架模块未命中: {t}")

    if sk_n and dr_n:
        # 顺序：仅比一级章在 draft 中的相对序（模糊匹配到的也计入）
        ok_order = True
        last = -1
        matched_dr = []
        for t, k in zip(sk, sk_n):
            pos = None
            if k in dr_set:
                pos = dr_n.index(k)
            else:
                for j, dk in enumerate(dr_n):
                    if k in dk or dk in k:
                        pos = j
                        break
            if pos is None:
                continue
            if pos < last:
                ok_order = False
            last = pos
            matched_dr.append(dr_n[pos])
        if not ok_order:
            errors.append("草稿中一级章相对顺序与 skeleton 不一致")
        # 覆盖率：一级章模糊命中比例
        hit = sum(1 for t in sk if norm_title(t) in dr_set or fuzzy_hit(t))
        cover = hit / len(sk) if sk else 0
        if cover < 0.7:
            errors.append(f"一级章覆盖率过低: {cover:.0%}（{hit}/{len(sk)}）")
        elif cover < 0.95:
            warnings.append(f"一级章覆盖率: {cover:.0%}（{hit}/{len(sk)}）")

    for m in check_modules(draft):
        warnings.append(f"必检模块提示: {m}")

    print("## 结构校验报告")
    print(f"  skeleton 标题数: {len(sk)}")
    print(f"  draft 标题数: {len(dr)}")
    if errors:
        print("## 错误")
        for e in errors:
            print(f"  [ERR] {e}")
    if warnings:
        print("## 警告")
        for w in warnings:
            print(f"  [WARN] {w}")
    if not errors:
        print("## 结果: PASS")
        sys.exit(0)
    print("## 结果: FAIL")
    sys.exit(1)


if __name__ == "__main__":
    main()
