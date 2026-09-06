"""P0 hard gates for bid-preparation skill (stages 1–7, mid-pipeline friendly).

INPUT: bid-projects/<project> directory.
OUTPUT: analysis/p0-gate-report.md/json and process exit code.
Checks (blockers unless noted):
  1. Extraction: extraction-report must gate_ok (no failed/needs_ocr on tenders)
  2. Hard parameters: analysis/hard-parameters.md exists and no 待填/{{}}
  3. Format clone: analysis/format-clone-checklist.md exists; outline must not
     leave 官方有/大纲无 as unresolved when writing started
  4. ★ triangle: mandatory-checklist rows need 偏离表位置 + 正文位置 for 废标风险
  5. Material gate: if material-gate says outline_only, output body must not
     invent detailed evidence (warn/blocker when detailed output exists)
Also runs P1 routing checks and P3 procurement checks (采购体系/采购方式):
  P3a. gov 体系须有 gov-policy-checklist.md 且填完（价格扣除/强制节能/信用）
  P3b. 磋商谈判类须有 consultation-strategy.md（两阶段报价）
  P3c. 磋商谈判类 output 术语一致性（禁止残留「投标人/中标/评标委员会」）
POS: P0 compliance helper; also invoked by validate_bid_package.py at stage 7.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PLACEHOLDER_PATTERNS = (
    re.compile(r"\{\{"),
    re.compile(r"待填"),
    re.compile(r"【待"),
    re.compile(r"TBD", re.I),
    re.compile(r"^\s*\|\s*[^|]*\|\s*—\s*\|", re.M),  # value cell is em-dash only often ok
)

# 表格行中值列仍为占位
UNFILLED_CELL = re.compile(r"\|\s*(\{\{[^}]+\}\}|待填|待确认|TBD|—{0}|N/?A\s*待)\s*\|", re.I)

# P3 采购方式：磋商/谈判/询价类，术语须用「响应」体系而非「投标」体系
CONSULTATION_MODES = {"competitive_consultation", "competitive_negotiation", "inquiry_single"}

# 合法代码白名单：模板未填时留的 `________` 也符合 [a-z_]+，必须白名单校验才不会误判
VALID_PROCUREMENT_SYSTEMS = {"gov", "enterprise"}
VALID_PROCUREMENT_MODES = {
    "open_tender",
    "invited_tender",
    "competitive_consultation",
    "competitive_negotiation",
    "inquiry_single",
}
VALID_AWARD_MODES = {"standard", "evaluation_separated"}

# 评定分离：成品须是两本独立文件，命名须能区分评标部分/定标部分
EVAL_PART_KEYWORDS = ("评标部分", "评标文件")
AWARD_PART_KEYWORDS = ("定标部分", "定标文件")
# 工程总承包必须出现的人证/专章关键词（缺失多为套错骨架）
CONSTRUCTION_KEYWORDS = ("建造师", "安全生产许可证", "施工组织", "竣工验收", "文明施工")

# 磋商类文稿中不应出现的「招标体系」用词 → 建议替换词
# 官方格式标题（如"投标（响应）函"）属例外，故本项为 warning 而非 blocker。
TENDER_ONLY_TERMS = {
    "投标人": "供应商",
    "投标文件": "响应文件",
    "评标委员会": "磋商小组/谈判小组",
    "中标人": "成交供应商",
    "中标通知书": "成交通知书",
    "招标文件": "磋商文件/谈判文件",
    "投标有效期": "响应有效期",
}

# 判定政府采购体系的文本信号（project-profile / 提取文本中出现即倾向 gov）
GOV_SIGNALS = ("政府采购法", "中国政府采购网", "财库〔", "政采云", "中小企业声明函", "政府采购政策")


def add_issue(issues: list[dict], level: str, message: str, file_path: Path | None = None) -> None:
    issues.append({"level": level, "message": message, "file": str(file_path) if file_path else ""})


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def check_extraction_gate(project_dir: Path, issues: list[dict]) -> None:
    report_path = project_dir / "analysis" / "extraction-report.json"
    data = load_json(report_path)
    if data is None:
        # 兼容旧格式或尚未提取
        md_path = project_dir / "analysis" / "extraction-report.md"
        if not md_path.exists():
            add_issue(issues, "blocker", "缺少 extraction-report（阶段1未完成或报告丢失）", report_path)
            return
        text = md_path.read_text(encoding="utf-8", errors="replace")
        if "needs_ocr" in text or "failed" in text or "未通过" in text:
            add_issue(issues, "blocker", "提取报告显示存在失败/扫描件，禁止解标与写作", md_path)
        return

    if isinstance(data, list):
        # 旧版：纯 items 列表
        items = data
        bad = [i for i in items if i.get("status") not in {"ok", None}]
        if bad:
            add_issue(
                issues,
                "blocker",
                f"文本提取未全部成功（{len(bad)} 个 failed/needs_ocr），须 OCR 或文字版后重提",
                report_path,
            )
        return

    if not data.get("gate_ok", False):
        add_issue(
            issues,
            "blocker",
            data.get("message") or "文本提取门禁未通过（存在 failed/needs_ocr）",
            report_path,
        )


def check_hard_parameters(project_dir: Path, issues: list[dict]) -> None:
    path = project_dir / "analysis" / "hard-parameters.md"
    if not path.exists():
        add_issue(issues, "blocker", "缺少前附表硬参数表 analysis/hard-parameters.md（P0）", path)
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if "{{" in text or "待填" in text:
        add_issue(issues, "blocker", "hard-parameters.md 仍有待填/占位，须填完并与投标函/报价表一致", path)
    # 关键行：限价、保证金、有效期至少出现
    for keyword in ("最高限价", "投标保证金", "投标有效期"):
        if keyword not in text:
            add_issue(issues, "warning", f"hard-parameters.md 未检出关键词「{keyword}」，请核对是否漏项", path)
    if "一致性核对" not in text and "投标函" not in text:
        add_issue(issues, "warning", "hard-parameters.md 建议含「与响应文件一致性」核对区", path)


def check_format_clone(project_dir: Path, issues: list[dict]) -> None:
    path = project_dir / "analysis" / "format-clone-checklist.md"
    if not path.exists():
        add_issue(
            issues,
            "blocker",
            "缺少格式克隆清单 analysis/format-clone-checklist.md（须按招标文件响应格式章节逐条克隆）",
            path,
        )
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if "{{" in text or "待填" in text:
        add_issue(issues, "blocker", "format-clone-checklist.md 仍有待填占位", path)
    # 未关闭缺口：表格状态列使用「缺口」关键字
    if re.search(r"\|\s*缺口\s*\|", text) or "状态：缺口" in text:
        add_issue(
            issues,
            "blocker",
            "格式克隆清单仍有状态为「缺口」的行（官方格式未进大纲），须补进大纲并改为已覆盖",
            path,
        )
    # 若已有商务/技术输出，大纲应对齐
    has_output = any(
        (project_dir / "output" / name).exists()
        and any((project_dir / "output" / name).rglob("*.md"))
        for name in ("商务文件", "技术文件")
    )
    if has_output and "克隆完成" not in text and "已确认" not in text:
        add_issue(issues, "warning", "已有输出稿但格式克隆清单未标注克隆完成/已确认", path)


def _parse_markdown_tables(text: str) -> list[list[list[str]]]:
    """粗解析 Markdown 表格为三维：tables → rows → cells。"""
    tables: list[list[list[str]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].strip().startswith("|"):
            index += 1
            continue
        block: list[list[str]] = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
            # skip separator
            if not all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in row if cell):
                if not re.fullmatch(r"[\s|:\-]+", lines[index].strip()):
                    block.append(row)
            index += 1
        if block:
            tables.append(block)
    return tables


def check_star_triangle(project_dir: Path, issues: list[dict]) -> None:
    path = project_dir / "analysis" / "mandatory-checklist.md"
    if not path.exists():
        add_issue(issues, "blocker", "缺少 mandatory-checklist.md", path)
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    for status in ("需补材料", "需用户确认", "无法判断", "需确认"):
        if status in text:
            add_issue(issues, "blocker", f"强制条款清单仍有未闭环状态: {status}", path)

    # 三角字段：表头应含 偏离表 / 正文
    header_ok = ("偏离表" in text or "偏离" in text) and ("正文" in text or "方案位置" in text)
    if not header_ok:
        add_issue(
            issues,
            "blocker",
            "mandatory-checklist 须含「偏离表位置」与「正文/方案位置」列（★三角闭环）",
            path,
        )
        return

    tables = _parse_markdown_tables(text)
    if not tables:
        add_issue(issues, "warning", "mandatory-checklist 未解析到表格行", path)
        return

    # 找含 编号 的主表
    main = None
    for table in tables:
        if not table:
            continue
        header = "".join(table[0])
        if "编号" in header or "M-" in header or "条款" in header:
            main = table
            break
    if main is None:
        main = tables[0]

    header_cells = main[0]
    def col_index(*names: str) -> int | None:
        for i, cell in enumerate(header_cells):
            for name in names:
                if name in cell:
                    return i
        return None

    idx_risk = col_index("风险")
    idx_dev = col_index("偏离表")
    idx_body = col_index("正文", "方案位置", "响应位置")
    idx_status = col_index("状态")
    # 仅检查废标风险行的三角
    data_rows = main[1:]
    missing_triangle = 0
    for row in data_rows:
        if len(row) < 2:
            continue
        risk = row[idx_risk] if idx_risk is not None and idx_risk < len(row) else ""
        if idx_risk is not None and "废标" not in risk and "★" not in risk and "强制" not in risk:
            # 非废标行可跳过三角严格性，但仍建议填
            continue
        dev = row[idx_dev] if idx_dev is not None and idx_dev < len(row) else ""
        body = row[idx_body] if idx_body is not None and idx_body < len(row) else ""
        status = row[idx_status] if idx_status is not None and idx_status < len(row) else ""
        if status and any(s in status for s in ("不适用",)):
            continue
        def is_empty(value: str) -> bool:
            v = (value or "").strip()
            if not v or v in {"—", "-", "/", "无", "待填", "TBD"}:
                return True
            if "{{" in v or "待填" in v:
                return True
            return False

        if is_empty(dev) or is_empty(body):
            missing_triangle += 1

    if missing_triangle:
        add_issue(
            issues,
            "blocker",
            f"★三角闭环未完成：约 {missing_triangle} 条废标/强制条款缺少偏离表位置或正文位置",
            path,
        )

    # 若有输出偏离表，抽查关键词
    output_dir = project_dir / "output"
    if output_dir.exists():
        deviation_files = list(output_dir.rglob("*偏离表*.md"))
        if not deviation_files:
            # 有强制清单但无偏离表文件
            if any((output_dir / name).exists() for name in ("商务文件", "技术文件")):
                add_issue(issues, "warning", "output 下未找到偏离表文件，请确认命名含「偏离表」", output_dir)


def check_material_writing_gate(project_dir: Path, issues: list[dict]) -> None:
    gate_path = project_dir / "analysis" / "material-gate.json"
    gate = load_json(gate_path)
    if not isinstance(gate, dict):
        # 兼容：从 material-index 推断
        index = load_json(project_dir / "analysis" / "material-index.json")
        if isinstance(index, dict) and "materials" in index:
            count = len(index.get("materials") or [])
            gate = {
                "evidence_file_count": count,
                "writing_detail_allowed": count >= 3,
                "outline_only": count < 3,
            }
        else:
            add_issue(
                issues,
                "warning",
                "缺少 material-gate.json，请运行 index_materials.py 生成资料写作门禁",
                gate_path,
            )
            return

    if gate.get("writing_detail_allowed", True):
        return

    # outline_only：若 output 已有大量正文（非大纲），blocker
    output_dir = project_dir / "output"
    if not output_dir.exists():
        return
    body_chars = 0
    for path in output_dir.rglob("*.md"):
        body_chars += len(path.read_text(encoding="utf-8", errors="replace"))
    # 超过约 3000 字视为已写详细正文
    if body_chars > 3000:
        add_issue(
            issues,
            "blocker",
            gate.get("message")
            or "资料库证据不足（outline_only），但 output 已有详细正文——须补齐资料或删改为缺口清单",
            output_dir,
        )
    elif body_chars > 0:
        add_issue(
            issues,
            "warning",
            "资料库证据不足：当前仅允许大纲+缺口清单，请勿继续扩写事实性正文",
            output_dir,
        )


def _profile_flags(project_dir: Path) -> dict:
    """从 project-state / project-profile 读取 P1 路由标志。"""
    flags = {
        "project_type": "unset",
        "delivery_mode": "unset",
        "multi_site": False,
        "has_construction": False,
    }
    state = load_json(project_dir / "project-state.json")
    if isinstance(state, dict):
        flags["project_type"] = state.get("project_type", "unset") or "unset"
        flags["delivery_mode"] = state.get("delivery_mode", "unset") or "unset"
    profile = project_dir / "analysis" / "project-profile.md"
    if profile.exists():
        text = profile.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"主类型代码[^`\n]*`([a-z_]+)`", text)
        if m:
            flags["project_type"] = m.group(1)
        m2 = re.search(r"递交方式代码[^`\n]*`([a-z_]+)`", text)
        if m2:
            flags["delivery_mode"] = m2.group(1)
        for line in text.splitlines():
            compact = line.replace(" ", "")
            if "多现场" in line and "|是|" in compact:
                flags["multi_site"] = True
            if ("施工" in line or "安装" in line) and "|是|" in compact:
                flags["has_construction"] = True
        if flags["project_type"] == "hybrid_retrofit":
            flags["multi_site"] = True
            flags["has_construction"] = True
        if flags["project_type"] == "hardware_supply":
            flags["has_construction"] = True
    return flags


def check_p1_routing(project_dir: Path, issues: list[dict]) -> None:
    """P1：项目画像、电子递交、多现场、安全、机械得分策略（多为 warning）。"""
    analysis = project_dir / "analysis"
    profile_path = analysis / "project-profile.md"
    state = load_json(project_dir / "project-state.json")
    ptype = "unset"
    delivery = "unset"
    if isinstance(state, dict):
        ptype = state.get("project_type", "unset")
        delivery = state.get("delivery_mode", "unset")

    has_output = any(
        (project_dir / "output" / name).exists()
        and any((project_dir / "output" / name).rglob("*.md"))
        for name in ("商务文件", "技术文件")
    )

    if not profile_path.exists():
        level = "blocker" if has_output else "warning"
        add_issue(
            issues,
            level,
            "缺少 project-profile.md（P1 项目类型/递交方式路由）",
            profile_path,
        )
    else:
        text = profile_path.read_text(encoding="utf-8", errors="replace")
        if "待确认" in text and "已确认" not in text and has_output:
            add_issue(issues, "warning", "project-profile 尚未标注已确认，但已有输出稿", profile_path)
        if ptype == "unset" and "unset" in text and has_output:
            add_issue(issues, "warning", "项目类型仍为 unset，请判定后写入 project-state", profile_path)

    # 电子标清单
    if delivery in {"electronic", "hybrid"} or (
        profile_path.exists()
        and re.search(r"electronic|全电子|公e采|中招联合|中化商务", profile_path.read_text(encoding="utf-8", errors="replace"))
    ):
        ebid = analysis / "e-bid-delivery-checklist.md"
        if not ebid.exists():
            add_issue(
                issues,
                "warning" if not has_output else "blocker",
                "电子标/纸电并行须填写 e-bid-delivery-checklist.md（内容稿与平台递交分离）",
                ebid,
            )

    flags = _profile_flags(project_dir)
    if flags["project_type"] == "hybrid_retrofit" or flags["multi_site"]:
        multi = analysis / "multi-site-plan.md"
        if not multi.exists() and has_output:
            add_issue(
                issues,
                "warning",
                "软硬改造/多现场项目建议填写 multi-site-plan.md 并写入实施方案",
                multi,
            )

    if flags["has_construction"] or flags["project_type"] in {"hybrid_retrofit", "hardware_supply"}:
        # 技术正文是否出现安全关键词（有输出时）
        tech_dir = project_dir / "output" / "技术文件"
        if tech_dir.exists() and any(tech_dir.rglob("*.md")):
            combined = "\n".join(
                p.read_text(encoding="utf-8", errors="replace") for p in tech_dir.rglob("*.md")
            )
            if not any(k in combined for k in ("安全", "安全员", "环保", "文明施工", "LOTO")):
                add_issue(
                    issues,
                    "warning",
                    "含施工/安装/改造特征但技术文件未检出安全环保相关表述，请补专章（见 safety-env-plan.md）",
                    tech_dir,
                )

    strategy = analysis / "scoring-strategy.md"
    if not strategy.exists():
        if has_output and flags["project_type"] != "simplified":
            add_issue(
                issues,
                "warning",
                "缺少 scoring-strategy.md（P1 机械得分策略：延保/业绩份数/证书截图）",
                strategy,
            )
    else:
        st = strategy.read_text(encoding="utf-8", errors="replace")
        if "{{" in st or "待填" in st:
            add_issue(issues, "warning", "scoring-strategy.md 仍有待填，阶段3/4/5 可能丢分", strategy)


def _has_written_output(project_dir: Path) -> bool:
    """output 下已有商务/技术中间稿时，P3 提示升级为 blocker。"""
    return any(
        (project_dir / "output" / name).exists()
        and any((project_dir / "output" / name).rglob("*.md"))
        for name in ("商务文件", "技术文件")
    )


def _procurement_flags(project_dir: Path) -> dict:
    """读取 P3 采购体系/方式；state 未填时用 project-profile 与解标文本兜底推断。"""
    flags = {
        "procurement_system": "unset",
        "procurement_mode": "unset",
        "award_mode": "unset",
        "project_type": "unset",
        "inferred_gov": False,
    }
    state = load_json(project_dir / "project-state.json")
    if isinstance(state, dict):
        flags["procurement_system"] = state.get("procurement_system") or "unset"
        flags["procurement_mode"] = state.get("procurement_mode") or "unset"
        flags["award_mode"] = state.get("award_mode") or "unset"
        flags["project_type"] = state.get("project_type") or "unset"

    profile = project_dir / "analysis" / "project-profile.md"
    if profile.exists():
        text = profile.read_text(encoding="utf-8", errors="replace")
        match_system = re.search(r"采购体系代码[^`\n]*`([a-z_]+)`", text)
        if match_system and match_system.group(1) in VALID_PROCUREMENT_SYSTEMS:
            flags["procurement_system"] = match_system.group(1)
        match_mode = re.search(r"采购方式代码[^`\n]*`([a-z_]+)`", text)
        if match_mode and match_mode.group(1) in VALID_PROCUREMENT_MODES:
            flags["procurement_mode"] = match_mode.group(1)
        match_award = re.search(r"定标方式代码[^`\n]*`([a-z_]+)`", text)
        if match_award and match_award.group(1) in VALID_AWARD_MODES:
            flags["award_mode"] = match_award.group(1)
        match_type = re.search(r"主类型代码[^`\n]*`([a-z_]+)`", text)
        if match_type:
            flags["project_type"] = match_type.group(1)
    # state 里若存的是非法值（手改 JSON 出错），一律归为 unset，避免静默跳过检查
    if flags["procurement_system"] not in VALID_PROCUREMENT_SYSTEMS:
        flags["procurement_system"] = "unset"
    if flags["procurement_mode"] not in VALID_PROCUREMENT_MODES:
        flags["procurement_mode"] = "unset"

    # 兜底推断：解标产物里出现政采法条/平台信号，但体系仍为 unset/enterprise 时提醒复核
    if flags["procurement_system"] != "gov":
        analysis_dir = project_dir / "analysis"
        if analysis_dir.exists():
            for path in list(analysis_dir.glob("*.md"))[:20]:
                content = path.read_text(encoding="utf-8", errors="replace")
                if sum(signal in content for signal in GOV_SIGNALS) >= 2:
                    flags["inferred_gov"] = True
                    break
    return flags


def check_gov_policy(project_dir: Path, issues: list[dict], has_output: bool) -> None:
    """P3a：政府采购政策核对表（价格扣除是零成本得分，漏了等于自弃）。"""
    path = project_dir / "analysis" / "gov-policy-checklist.md"
    if not path.exists():
        add_issue(
            issues,
            "blocker" if has_output else "warning",
            "政府采购项目缺少 gov-policy-checklist.md（价格扣除/强制节能/信用查询/资格三段式），"
            "见 references/gov-procurement-policy.md",
            path,
        )
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if "{{" in text or "待填" in text:
        add_issue(
            issues,
            "blocker" if has_output else "warning",
            "gov-policy-checklist.md 仍有待填占位；价格扣除比例与企业属性未定则报价策略无依据",
            path,
        )
    if "专门面向中小企业" in text and "☑ 是" in text:
        add_issue(
            issues,
            "warning",
            "核对表标记本项目专门面向中小企业：须确认我方具备投标资格，否则应终止编制",
            path,
        )
    for keyword in ("价格扣除", "节能", "信用"):
        if keyword not in text:
            add_issue(
                issues, "warning", f"gov-policy-checklist.md 未检出「{keyword}」相关内容，请核对是否漏项", path
            )


def check_consultation_strategy(project_dir: Path, issues: list[dict], has_output: bool) -> None:
    """P3b：磋商/谈判类两阶段报价策略表。"""
    path = project_dir / "analysis" / "consultation-strategy.md"
    if not path.exists():
        add_issue(
            issues,
            "blocker" if has_output else "warning",
            "磋商/谈判类项目缺少 consultation-strategy.md（两阶段报价+术语切换+可变动条款），"
            "见 references/procurement-mode-routing.md",
            path,
        )
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if "{{" in text or "待填" in text:
        add_issue(issues, "warning", "consultation-strategy.md 仍有待填占位", path)
    if "最后报价" not in text:
        add_issue(
            issues,
            "warning",
            "consultation-strategy.md 未检出「最后报价」：须明确首次报价预留的下调空间",
            path,
        )


def check_terminology_consistency(project_dir: Path, issues: list[dict]) -> None:
    """P3c：磋商/谈判类文稿残留「投标」体系用词，属格式硬伤。"""
    output_dir = project_dir / "output"
    if not output_dir.exists():
        return
    hits: dict[str, int] = {}
    for path in output_dir.rglob("*.md"):
        content = path.read_text(encoding="utf-8", errors="replace")
        for term in TENDER_ONLY_TERMS:
            count = content.count(term)
            if count:
                hits[term] = hits.get(term, 0) + count
    if not hits:
        return
    detail = "；".join(
        f"{term}×{count}→改为「{TENDER_ONLY_TERMS[term]}」"
        for term, count in sorted(hits.items(), key=lambda kv: -kv[1])[:5]
    )
    add_issue(
        issues,
        "warning",
        f"磋商/谈判类文稿仍残留招标体系用词：{detail}"
        "（官方格式标题原文照抄的除外，自编文件必须切换）",
        output_dir,
    )


def check_award_separation(project_dir: Path, issues: list[dict], has_output: bool) -> None:
    """P3d：评定分离——投标文件须拆两本，且答辩人档期须锁定。

    这是会「静默做错」的一类：只组装一本、或传错文件夹，都不会报错，直接出局。
    """
    plan_path = project_dir / "analysis" / "award-separation-plan.md"
    if not plan_path.exists():
        add_issue(
            issues,
            "blocker" if has_output else "warning",
            "评定分离项目缺少 award-separation-plan.md（双分册结构+定标因素+答辩预案），"
            "见 references/award-separation-defense.md",
            plan_path,
        )
    else:
        text = plan_path.read_text(encoding="utf-8", errors="replace")
        if "{{" in text or "待填" in text:
            add_issue(issues, "warning", "award-separation-plan.md 仍有待填占位", plan_path)
        if "答辩" not in text:
            add_issue(
                issues,
                "warning",
                "award-separation-plan.md 未检出答辩预案：两位关键人缺席即视为放弃答辩资格",
                plan_path,
            )

    # 成品双分册核对：只看交付物位置。
    # source/ 放的是招标文件本身、analysis/ 可能有中间产物，都不是成品——
    # 否则新建项目一复制招标文件进来就会误报 blocker。
    docx_names = [
        path.name
        for path in project_dir.rglob("*.docx")
        if not path.name.startswith("~$")
        and "source" not in path.relative_to(project_dir).parts
        and "analysis" not in path.relative_to(project_dir).parts
    ]
    if not docx_names:
        return
    has_eval = any(any(k in name for k in EVAL_PART_KEYWORDS) for name in docx_names)
    has_award = any(any(k in name for k in AWARD_PART_KEYWORDS) for name in docx_names)
    if not (has_eval and has_award):
        add_issue(
            issues,
            "blocker",
            "评定分离要求投标文件分「评标部分」「定标部分」两本分别编制，"
            f"当前成品仅见：{'、'.join(docx_names[:5])}",
            project_dir,
        )


def check_construction_epc(project_dir: Path, issues: list[dict]) -> None:
    """P3e：工程总承包——技术稿缺工程要件多半是套错了 IT 骨架。"""
    tech_dir = project_dir / "output" / "技术文件"
    if not tech_dir.exists() or not any(tech_dir.rglob("*.md")):
        return
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in tech_dir.rglob("*.md")
    )
    missing = [word for word in CONSTRUCTION_KEYWORDS if word not in combined]
    if len(missing) >= 3:
        add_issue(
            issues,
            "warning",
            f"工程总承包项目技术稿未检出：{'、'.join(missing)}——"
            "疑似套用了IT/服务类骨架，见 references/sample-construction-epc.md",
            tech_dir,
        )


def check_p3_procurement(project_dir: Path, issues: list[dict]) -> None:
    """P3：采购体系与采购方式路由检查（政采政策包 + 磋商两阶段报价 + 术语一致性）。"""
    flags = _procurement_flags(project_dir)
    has_output = _has_written_output(project_dir)

    if flags["procurement_system"] == "unset" and has_output:
        add_issue(
            issues,
            "warning",
            "采购体系仍为 unset（gov/enterprise 未判定），政府采购专属得分项可能整体遗漏",
            project_dir / "analysis" / "project-profile.md",
        )
    if flags["inferred_gov"] and flags["procurement_system"] != "gov":
        add_issue(
            issues,
            "warning",
            "解标产物出现政府采购法条/平台信号，但采购体系未标为 gov —— 请复核，"
            "误判会漏掉价格扣除与强制采购节能产品",
            project_dir / "analysis" / "project-profile.md",
        )

    if flags["procurement_system"] == "gov" or flags["inferred_gov"]:
        check_gov_policy(project_dir, issues, has_output)

    if flags["procurement_mode"] in CONSULTATION_MODES:
        check_consultation_strategy(project_dir, issues, has_output)
        check_terminology_consistency(project_dir, issues)

    if flags["award_mode"] == "evaluation_separated":
        check_award_separation(project_dir, issues, has_output)

    if flags["project_type"] == "construction_epc":
        check_construction_epc(project_dir, issues)


def check_all_p0(project_dir: Path) -> dict:
    project_dir = project_dir.expanduser().resolve()
    issues: list[dict] = []
    if not project_dir.exists():
        add_issue(issues, "blocker", "项目目录不存在", project_dir)
    else:
        check_extraction_gate(project_dir, issues)
        check_hard_parameters(project_dir, issues)
        check_format_clone(project_dir, issues)
        check_star_triangle(project_dir, issues)
        check_material_writing_gate(project_dir, issues)
        check_p1_routing(project_dir, issues)
        check_p3_procurement(project_dir, issues)
    ok = not any(i["level"] == "blocker" for i in issues)
    return {
        "project_dir": str(project_dir),
        "ok": ok,
        "issues": issues,
        "gate": "p0+p1+p3",
    }


def write_report(project_dir: Path, result: dict) -> None:
    analysis = project_dir / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    lines = [
        "# P0/P1/P3 门禁报告",
        "",
        f"结论：{'通过' if result['ok'] else '未通过'}（blocker 决定是否通过；warning 须处理）",
        "",
        "| 级别 | 问题 | 文件 |",
        "|---|---|---|",
    ]
    if result["issues"]:
        for item in result["issues"]:
            lines.append(f"| {item['level']} | {item['message']} | `{item['file']}` |")
    else:
        lines.append("| ok | P0 硬门禁与 P1 路由检查均无问题 |  |")
    lines.extend([
        "",
        "## P0 五项对照",
        "1. 文本提取无 failed/needs_ocr",
        "2. hard-parameters.md 填完且无待填",
        "3. format-clone-checklist.md 官方格式与大纲 diff 关闭",
        "4. mandatory-checklist ★三角（偏离表位置+正文位置）闭环",
        "5. 资料库空壳时禁止详细正文（material-gate）",
        "",
        "## P1 路由对照",
        "1. project-profile.md 项目类型 + 递交方式",
        "2. electronic/hybrid → e-bid-delivery-checklist.md",
        "3. 多现场/改造 → multi-site-plan.md",
        "4. 施工安装 → 安全环保专章",
        "5. scoring-strategy.md 机械得分行动表",
        "",
        "## P3 采购体系与方式对照",
        "1. project-profile.md 采购体系（gov/enterprise）+ 采购方式（招标/磋商/谈判/询价）",
        "2. gov → gov-policy-checklist.md（价格扣除测算/强制节能/信用查询/资格三段式）",
        "3. 磋商谈判类 → consultation-strategy.md（首次报价须预留下调空间）",
        "4. 磋商谈判类 → 自编文稿术语切换为「响应文件/供应商/成交」",
        "5. 评定分离 → award-separation-plan.md + 成品分「评标部分」「定标部分」两本",
        "6. 工程总承包 → 建造师/安全许可/施工组织/竣工验收/文明施工要件齐备",
        "",
    ])
    (analysis / "p0-gate-report.md").write_text("\n".join(lines), encoding="utf-8")
    (analysis / "p0-gate-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check P0 hard gates for a bid project.")
    parser.add_argument("project_dir", type=Path, help="Project directory under bid-projects.")
    parser.add_argument("--no-report", action="store_true", help="Do not write p0-gate-report files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()
    result = check_all_p0(project_dir)
    if not args.no_report and project_dir.exists():
        write_report(project_dir, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
