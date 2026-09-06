# -*- coding: utf-8 -*-
"""
INPUT: 一个招标文件路径 (docx / pdf / doc)，依赖 python-docx、pymupdf、pywin32(仅.doc)
OUTPUT: stdout 输出纯文本（表格以 [TABLE]...[/TABLE] 线性化），并打印结构摘要；
        --skeleton 可导出可校验的章节标题树（供 structure_check / 成稿对照）
POS: bid-document-builder skill 的参考文件解析器——把任意格式招标文件转成可分析纯文本

用法:
    python extract_doc.py <文件路径> [--out 输出txt路径]
    python extract_doc.py <文件路径> --summary   # 只输出章节骨架与要素统计
    python extract_doc.py <文件路径> --skeleton skeleton.md  # 导出标题树
"""
import os
import re
import sys
import argparse
import tempfile

# stdout/stderr 都要设 UTF-8：扫描件报错走 stderr，GBK 控制台下否则乱码
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SCAN_PDF_THRESHOLD = 3000  # 提取字符数低于此值判定为扫描件


def extract_docx(path: str) -> str:
    """按文档顺序提取段落与表格，表格线性化为 'a | b | c' 行"""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.ns import qn

    doc = Document(path)
    lines = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            t = Paragraph(child, doc).text.strip()
            if t:
                lines.append(t)
        elif child.tag == qn("w:tbl"):
            tbl = Table(child, doc)
            lines.append("[TABLE]")
            for row in tbl.rows:
                lines.append(" | ".join(c.text.strip().replace("\n", " ") for c in row.cells))
            lines.append("[/TABLE]")
    return "\n".join(lines)


def extract_pdf(path: str) -> str:
    import fitz

    doc = fitz.open(path)
    parts = []
    for i, page in enumerate(doc):
        parts.append(f"=== PAGE {i + 1} ===")
        parts.append(page.get_text("text"))
    doc.close()
    text = "\n".join(parts)
    # 扫描件检测：图片型 PDF 提不出文字，直接报错让上层提示用户
    if len(text.replace("=== PAGE", "")) < SCAN_PDF_THRESHOLD:
        raise RuntimeError(
            f"提取字符数过少({len(text)})，该 PDF 疑似扫描件(图片型)，无法直接解析。"
            "请让用户提供 Word 版本，或先做 OCR。"
        )
    return text


def convert_doc_to_docx(path: str) -> str:
    """老式 .doc 经 Microsoft Word 或 WPS COM 只读转换为临时 .docx。"""
    from cover_template import convert_legacy_doc

    return convert_legacy_doc(path, tempfile.gettempdir())


# 第X章 / 附件 / 附录
CHAPTER = re.compile(
    r"^(第[一二三四五六七八九十百零〇0-9]+[章节部分篇]"
    r"|附件[一二三四五六七八九十0-9]*"
    r"|附录[一二三四五六七八九十0-9A-Za-z]*)"
)
# 粤政采等：一、二、三、…
CN_ORDINAL = re.compile(r"^[一二三四五六七八九十百]+[、．.]\s*\S+")
# 工程/烟草常见独立模块标题（无“第X章”前缀时仍识别）
MODULE_TITLES = re.compile(
    r"^(?:投标人须知前附表|评标办法前附表|招标公告|投标邀请"
    r"|采购内容及分包|项目采购内容|项目须知|商务要求及报价区间"
    r"|项目概况(?:内容)?|资格与符合性要求|技术标准与要求|评标方法及标准"
    r"|其他附件|发包人要求|发包人提供的资料|合同条款及格式"
    r"|投标文件格式|开标记录表)$"
)
# 须知正文一级节：1. 总则 / 2. 招标文件
NUM_SECTION = re.compile(r"^\d{1,2}[\.、．]\s*\S{1,30}$")

KEYWORDS = {
    "★条款": re.compile(r"★"),
    "▲条款": re.compile(r"[▲△]"),
    "废标/否决": re.compile(r"废标|无效投标|投标无效|否决其?投标"),
    "评标/评分": re.compile(r"评标办法|评分标准|综合评[分估]|评标、定标"),
    "保证金": re.compile(r"保证金"),
    "收款账户": re.compile(r"开户[银行]|账号|户名"),
    "实质性要求": re.compile(r"实质性"),
    "槽位括号【】": re.compile(r"【[^】]{0,40}】"),
    "占位符[]": re.compile(r"\[[^\]\n]{1,40}\]"),
}


def strip_toc_pagenum(line: str) -> str:
    """去掉目录行尾部页码：'第一章 招标公告3' / '一、 采购内容及分包3' / 制表符页码"""
    s = re.sub(r"(?:\t+|\s*\.{2,}\s*)\d+\s*$", "", line).strip()
    # 标题末尾直接粘连页码（无空格）：仅当末尾数字较短且前部像标题时剥离
    m = re.match(r"^(.+?)(\d{1,3})$", s)
    if m and len(m.group(1)) >= 4 and not re.search(r"\d", m.group(1)[-3:]):
        head = m.group(1).rstrip()
        if CHAPTER.match(head) or CN_ORDINAL.match(head) or MODULE_TITLES.match(head):
            return head
    return s


def is_heading_candidate(line: str) -> bool:
    """判断一行是否为可进入骨架的标题（排除过长正文、表格行）"""
    if not line or len(line) > 60 or line.startswith("|") or line.startswith("["):
        return False
    if line.startswith("==="):  # PDF 页标记
        return False
    # 过长说明性句子（含“的，”等）不当标题
    if "，" in line and len(line) > 25:
        return False
    if CHAPTER.match(line):
        return True
    if CN_ORDINAL.match(line):
        return True
    if MODULE_TITLES.match(line):
        return True
    return False


def extract_headings(text: str, include_num_sections: bool = False) -> list[str]:
    """提取去重后的章节/模块标题列表（保持首次出现顺序）

    优先保留「第X章 / 一、二、三」一级结构；模块标题若已被章标题覆盖则跳过，
    避免目录+正文重复导致 skeleton 膨胀。
    """
    lines = [l.strip() for l in text.splitlines()]
    seen: set[str] = set()
    headings: list[str] = []
    chapter_blobs: list[str] = []  # 已收录章标题的归一化文本，用于去重子模块

    for raw in lines:
        clean = strip_toc_pagenum(raw)
        if not is_heading_candidate(clean):
            if include_num_sections and NUM_SECTION.match(clean) and len(clean) <= 40:
                pass
            else:
                continue

        key = re.sub(r"\s+", "", clean)
        if key in seen:
            continue
        if re.fullmatch(r"目\s*录", clean):
            continue

        is_primary = bool(CHAPTER.match(clean) or CN_ORDINAL.match(clean))
        if not is_primary and not include_num_sections:
            # 模块标题：若已有章标题包含该模块核心词，则跳过（如「招标公告」vs「第一章 招标公告」）
            core = re.sub(r"^[第]?[一二三四五六七八九十0-9]+[章节部分、．.\s]*", "", key)
            if core and any(core in blob or blob in core for blob in chapter_blobs):
                continue
            # 附件保留；纯重复的「合同条款及格式」等若章中已有则跳过
            if MODULE_TITLES.match(clean):
                if any(core in blob for blob in chapter_blobs if len(core) >= 4):
                    continue

        seen.add(key)
        headings.append(clean)
        if is_primary:
            chapter_blobs.append(key)
    return headings


def detect_school(headings: list[str], text: str) -> str:
    """粗判章节流派，供摘要展示（最终以用户参考文件为准）"""
    joined = "\n".join(headings)
    if "发包人要求" in joined or "评标、定标" in joined:
        return "G-工程总承包/施工系"
    if "采购内容及分包" in joined or "广东省政府采购" in text[:500] or "智慧云平台" in text[:2000]:
        return "H-粤政采云平台系"
    if "竞争性谈判" in text[:3000] or "响应文件" in joined:
        return "F-非招标/竞谈"
    if "公e采" in text or "投标人须知前附表" in joined and "招标内容及要求" in joined:
        return "B-电子平台系(或近似)"
    if re.search(r"第[一二三四五六]章", joined):
        return "A/C/D 通用章体系(以参考文件为准)"
    if CN_ORDINAL.search(joined):
        return "序号模块制(一、二、三…)"
    return "未判定(严格按参考文件标题树)"


def summarize(text: str) -> str:
    headings = extract_headings(text, include_num_sections=False)
    school = detect_school(headings, text)
    out = [
        f"## 流派粗判: {school}",
        "## 章节骨架（去重后）",
    ]
    if not headings:
        out.append("  （未识别到章节标题——请人工通读全文或检查是否扫描件）")
    for h in headings:
        out.append(f"  {h}")
    out.append("## 关键要素统计")
    for name, pat in KEYWORDS.items():
        n = len(pat.findall(text))
        if n:
            out.append(f"  {name}: {n} 处")
    # 封面线索
    cover_hints = []
    for pat, label in [
        (r"招标人[：:]\s*(\S.+)", "招标人"),
        (r"采购人[：:]\s*(\S.+)", "采购人"),
        (r"招标代理机构[：:]\s*(\S.+)", "代理机构"),
        (r"采购代理机构[：:]\s*(\S.+)", "代理机构"),
    ]:
        m = re.search(pat, text[:2500])
        if m:
            cover_hints.append(f"{label}={m.group(1).strip()[:40]}")
    if cover_hints:
        out.append("## 封面线索")
        for c in cover_hints:
            out.append(f"  {c}")
    return "\n".join(out)


def write_skeleton(text: str, path: str) -> None:
    """导出供 structure_check 使用的 skeleton.md"""
    headings = extract_headings(text, include_num_sections=False)
    school = detect_school(headings, text)
    lines = [
        "# 参考文件结构骨架",
        "",
        f"> 流派粗判: {school}",
        "> 成稿 draft.md 的一级/模块标题必须覆盖下列条目（顺序一致，允许变量替换措辞中的项目名）。",
        "",
        "## 标题树",
        "",
    ]
    for h in headings:
        # markdown 标题：第X章 / 一、 用 #；独立模块用 ##
        if CHAPTER.match(h) or CN_ORDINAL.match(h):
            lines.append(f"# {h}")
        else:
            lines.append(f"## {h}")
    lines.append("")
    lines.append("## 必检模块（人工勾选）")
    lines.append("")
    for item in [
        "封面（项目名称/招标人或采购人/代理机构/日期或编号）",
        "目录",
        "招标信息（公告或项目须知/前附表槽位）",
        "采购需求或发包人要求/技术标准",
        "评标办法及标准",
        "合同或附件格式",
    ]:
        lines.append(f"- [ ] {item}")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"OK 骨架已写入: {path}  (标题 {len(headings)} 条)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--out", help="纯文本输出路径")
    ap.add_argument("--summary", action="store_true", help="仅输出结构摘要")
    ap.add_argument("--skeleton", help="导出 skeleton.md 路径", default=None)
    args = ap.parse_args()

    ext = os.path.splitext(args.path)[1].lower()
    try:
        if ext == ".docx":
            text = extract_docx(args.path)
        elif ext == ".pdf":
            text = extract_pdf(args.path)
        elif ext == ".doc":
            text = extract_docx(convert_doc_to_docx(args.path))
        else:
            print(f"不支持的格式: {ext}", file=sys.stderr)
            sys.exit(2)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"OK 已提取 {len(text)} 字符 -> {args.out}")
        print(summarize(text))
    elif args.summary:
        print(summarize(text))
    elif not args.skeleton:
        # 无 --out/--summary/--skeleton 时才把全文打到 stdout
        print(text)

    if args.skeleton:
        write_skeleton(text, args.skeleton)
        if not args.out and not args.summary:
            print(summarize(text))


if __name__ == "__main__":
    main()
