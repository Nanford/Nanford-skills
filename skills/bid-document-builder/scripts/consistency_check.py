# -*- coding: utf-8 -*-
"""
INPUT: 中间稿 draft.md；可选 project_data.json（确认值）与 old_values.json（参考文件旧值）
OUTPUT: stdout 一致性审查报告；发现"错误级"问题时退出码为 1
        （残留旧值/关键值冲突/分值不等于100/无法识别或未闭合的 {{}} 标记）
POS: bid-document-builder skill 的成稿前自检器——把 LLM 自查升级为可复跑的机械化交叉比对

用法:
    python consistency_check.py draft.md [--data project_data.json] [--old old_values.json]

project_data.json 格式（键名任意，值为应在全文交叉出现的确认值）:
    {"项目名称": "XX项目", "招标编号": "GW2026-001", "投标保证金": "50000", ...}
old_values.json 格式（参考文件中的旧项目值，出现在新稿中即报错）:
    ["旧项目名称", "旧编号", "旧账号", ...]
"""
import io
import json
import re
import sys
import argparse

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

RED_MARK = re.compile(r"\{\{RED:(.*?)\}\}", re.S)
PENDING = re.compile(r"【待填写[^】]*】")
DATE = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")
AMOUNT = re.compile(r"(?:人民币|￥)?\s*([\d,，]+(?:\.\d+)?)\s*(万?元)")

# 歧视性/排他性措辞警示词（V2 规则库雏形）：命中仅提示人工判断，不判错
DISCRIMINATION_PATTERNS = [
    (r"指定品牌|唯一供应商|独家代理", "疑似指定品牌/独家来源"),
    (r"驰名商标|名牌产品", "以商标荣誉设限，属明令禁止情形"),
    (r"本[省市县区]\s*(?:注册|企业|单位)", "疑似地域限制"),
    (r"注册资本(?:金)?不低于|注册资金不低于", "注册资本门槛（政府采购项目禁止）"),
    (r"成立\s*(?:满|不少于)?\s*\d+\s*年", "成立年限门槛，注意合规性"),
    (r"国产|进口产品除外", "产地限制，注意合规性"),
    (r"特定行政区域|特定行业的业绩", "业绩地域/行业限制（87号令禁止）"),
]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check(draft_path: str, data: dict, old_values: list) -> int:
    with open(draft_path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    errors, warnings, infos = [], [], []

    def locate(keyword: str) -> list:
        """返回含关键词的行号列表"""
        return [i + 1 for i, l in enumerate(lines) if keyword in l]

    # 1. 未填写项
    pendings = PENDING.findall(text)
    if pendings:
        warnings.append(f"存在 {len(pendings)} 处【待填写】占位：" + "、".join(sorted(set(pendings))))

    # 2. 红字标记统计（0 处红字通常意味着漏标）
    reds = RED_MARK.findall(text)
    if reds:
        infos.append(f"红字标记 {len(reds)} 处（将进入待确认清单）")
    else:
        warnings.append("全文没有任何 {{RED:}} 红字标记——关键变量可能未按规范标注")

    # 3. 确认值交叉引用检查：关键值应在全文多处出现
    plain = RED_MARK.sub(lambda m: m.group(1), text)  # 去标记后做出现次数统计
    for key, val in (data or {}).items():
        val = str(val).strip()
        if not val or len(val) < 2:
            continue
        n = plain.count(val)
        if n == 0:
            errors.append(f"确认值缺失：[{key}]={val} 在全文中一次都未出现")
        elif n == 1 and key in ("项目名称", "招标编号", "项目编号"):
            warnings.append(f"[{key}]={val} 全文仅出现 1 次——招标文件通常需在封面/公告/前附表/合同/格式文件多处引用")
        else:
            infos.append(f"[{key}]={val} 出现 {n} 次")

    # 4. 旧值残留检查（信息泄露/废标级错误）
    for old in old_values or []:
        old = str(old).strip()
        if len(old) < 4:  # 过短字符串误报率高
            continue
        if old in plain:
            errors.append(f"参考文件旧值残留：'{old}' 出现在第 {locate(old)[:5]} 行附近，必须替换")

    # 5. 保证金金额冲突：同类保证金在不同位置出现不同金额
    for kind in ("投标保证金", "履约保证金"):
        amounts = set()
        for l in lines:
            if kind in l:
                for m in AMOUNT.finditer(RED_MARK.sub(lambda x: x.group(1), l)):
                    amounts.add(m.group(1).replace(",", "").replace("，", "") + m.group(2))
        if len(amounts) > 1:
            errors.append(f"{kind}金额在全文出现多个不同值：{sorted(amounts)}，请核对统一")
        elif len(amounts) == 1:
            infos.append(f"{kind}金额全文一致：{next(iter(amounts))}")

    # 6. 投标截止/开标时间冲突（只取关键词后 30 字符内的日期，避免同行多个时间点误报）
    for kind in ("投标截止", "开标时间"):
        dates = set()
        for l in lines:
            pos = 0
            while (idx := l.find(kind, pos)) != -1:
                dates.update(DATE.findall(l[idx: idx + len(kind) + 30]))
                pos = idx + len(kind)
        if len(dates) > 1:
            errors.append(f"'{kind}'相关日期出现多个不同值：{sorted(dates)}，请核对统一")

    # 7. 评标分值构成合计 = 100
    # 只在"评标办法/评标方法"章内搜索，避免误抓正文他处的"价格X分"类字样；
    # 找不到该章标题时退回全文搜索（不因章名差异而漏检）
    plain_lines = plain.splitlines()
    ch_head = re.compile(r"^#{0,4}\s*第[一二三四五六七八九十]+[章部分]")
    start = next((i for i, l in enumerate(plain_lines)
                  if ch_head.match(l.strip()) and re.search(r"评标[办方]法", l)), None)
    if start is not None:
        end = next((i for i in range(start + 1, len(plain_lines))
                    if ch_head.match(plain_lines[i].strip())), len(plain_lines))
        score_scope = "\n".join(plain_lines[start:end])
    else:
        score_scope = plain
    m_price = re.search(r"价格[^0-9\n]{0,12}(\d+)\s*分", score_scope)
    m_biz = re.search(r"商务[^0-9\n]{0,12}(\d+)\s*分", score_scope)
    m_tech = re.search(r"技术[^0-9\n]{0,12}(\d+)\s*分", score_scope)
    if m_price and m_biz and m_tech:
        total = int(m_price.group(1)) + int(m_biz.group(1)) + int(m_tech.group(1))
        if total != 100:
            errors.append(
                f"分值构成合计 {total} ≠ 100（价格{m_price.group(1)}+商务{m_biz.group(1)}+技术{m_tech.group(1)}）"
            )
        else:
            infos.append(f"分值构成合计 100（价格{m_price.group(1)}/商务{m_biz.group(1)}/技术{m_tech.group(1)}）")

    # 8. 歧视性/排他性措辞提示（仅警示，由人判断）
    for pat, why in DISCRIMINATION_PATTERNS:
        hits = [i + 1 for i, l in enumerate(lines) if re.search(pat, l)]
        if hits:
            warnings.append(f"歧视性措辞警示（{why}）：第 {hits[:5]} 行，请人工确认是否保留")

    # 9. 标记/markdown 残留检查——成稿引擎无法渲染的原始字符不允许进入 Word
    #    仅支持 RED/COVER//COVER/TOC/PAGEBREAK 五种标记；拼错或未闭合即错误
    #    RED 内容限定单行匹配——若允许跨行，未闭合的 {{RED: 会吞掉下一个 }} 把错误洗白
    valid_mark = re.compile(r"\{\{(?:RED:[^\n]*?|COVER|/COVER|TOC|PAGEBREAK)\}\}")
    leftover = valid_mark.sub("", text)
    bad_lines = [i + 1 for i, l in enumerate(leftover.splitlines()) if "{{" in l or "}}" in l]
    if bad_lines:
        errors.append(
            f"无法识别/未闭合的 {{{{...}}}} 标记：第 {bad_lines[:5]} 行附近"
            "（仅支持 RED/COVER/TOC/PAGEBREAK，检查拼写与闭合）"
        )
    deep_heads = [i + 1 for i, l in enumerate(lines) if re.match(r"^\s*#{5,}\s", l)]
    if deep_heads:
        warnings.append(f"5 级以上标题（#####）：第 {deep_heads[:5]} 行，将降为四级标题渲染，建议改用正文编号文字")
    if "```" in text:
        warnings.append("draft 含代码围栏 ```，将按普通段落输出，请确认是否本意")
    html_hits = [i + 1 for i, l in enumerate(lines)
                 if re.search(r"</?(?:b|i|u|p|td|tr|table|span|div)\b", l, re.I)]
    if html_hits:
        warnings.append(f"疑似 HTML 标签残留：第 {html_hits[:5]} 行，成稿引擎不解析 HTML（单元格内换行 <br> 除外）")
    odd_bold = [i + 1 for i, l in enumerate(lines) if l.count("**") % 2 == 1]
    if odd_bold:
        warnings.append(f"未闭合的 ** 加粗标记：第 {odd_bold[:5]} 行，会以原始星号漏进成稿")

    # ---- 报告 ----
    print(f"# 一致性自检报告：{draft_path}")
    print(f"\n错误 {len(errors)} | 警告 {len(warnings)} | 信息 {len(infos)}\n")
    for e in errors:
        print(f"[错误] {e}")
    for w in warnings:
        print(f"[警告] {w}")
    for i in infos:
        print(f"[信息] {i}")
    if not errors and not warnings:
        print("全部检查通过。")
    return 1 if errors else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("--data", help="project_data.json 确认值")
    ap.add_argument("--old", help="old_values.json 参考文件旧值清单")
    args = ap.parse_args()
    data = load_json(args.data) if args.data else {}
    old = load_json(args.old) if args.old else []
    sys.exit(check(args.draft, data, old))


if __name__ == "__main__":
    main()
