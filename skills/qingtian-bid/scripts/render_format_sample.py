"""Render a one-page format sample (DOCX + PDF) and its format confirmation card.

INPUT: a preset code from templates/format-presets.json and optional field assignments
       (字段=值, 磅值或中文字号名); in project mode also <project>/project-state.json and the
       stage-2 tender format file and, when it exists, analysis/rule-card.json (评审注释的扣分句);
       Word or WPS for PDF export (optional, via office_bridge), and optional --plain-sample.
OUTPUT: <output-dir>/<name>.docx, <name>.pdf (when Office is available), <name>-确认卡.md,
        the sample Markdown with a continuous frame by default and a stdlib-generated chart image; JSON summary on stdout.
        --list-presets prints the preset table, optionally filtered by field values.
        Project mode (--project) writes the sample under analysis/format/, records a pending
        format review in project-state.json, writes the three-column tender diff (with the
        tender's penalty sentence), and --confirm locks the reviewed format. A tender file that leaves
        out the penalty sentence the rule card's notes carry is refused.
POS: stage-0 kickoff tool and stage-2 format-override tool of qingtian-bid. It shows the user what
     the format really looks like before it is locked, and it renders through the final builder
     (format preview, bypassing the project format lock) so the sample cannot drift from the
     delivered DOCX.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from datetime import date, datetime
from pathlib import Path

from build_response_docx import build_response_docx
from docx_font_profiles import (
    FIELD_LABELS,
    apply_format_settings,
    describe_value,
    filter_presets,
    fonts_needing_install,
    format_card_rows,
    load_catalog,
    parse_assignment,
    preset_format,
)
from format_state import (
    add_deviations,
    check_tender_settings,
    compose_format,
    confirm_review,
    current_selection,
    current_tender,
    diff_markdown,
    load_state,
    load_tender_spec,
    make_review,
    penalty_issue,
    save_state,
    with_blind_mode_defaults,
)
from office_bridge import export_pdf_via_office
from project_cards import RULE_CARD_FILE, load_json


SAMPLE_IMAGE_NAME = "格式样张-示意图.png"
PROJECT_FORMAT_DIR = Path("analysis") / "format"
SAMPLE_HEADER = "示例项目施工组织设计"
# 样张文字只演示格式：含数字、西文和规范编号，便于看出西文字体；篇幅按 F4 一页排得下控制。
# 二级标题紧跟一级标题，开启标题分页的预设也能排在同一页。
SAMPLE_MARKDOWN = f"""<!-- chapter-center -->
# 一、主要施工方法

<!-- panel-grid-start -->
## （一）测量放线

本页为格式样张，文字只用于展示字体、字号、行距和页边距，不代表任何真实项目。示例工程为框架结构，地上 4 层，建筑面积 6850 m²，混凝土强度等级 C30，按 GB 50204-2015 验收。

### 1. 平面控制网

平面控制网按一级导线布设，轴线投测每层复核两次，标高偏差超过 3 mm 即返工。

<!-- table-caption: 表 1-1 测量仪器配置 -->
| 仪器名称 | 型号规格 | 数量（台） | 进场时间 |
|---|---|---|---|
| 经纬仪 | J2 | 1 | 开工前 3 天 |
| 水准仪 | DS3 | 2 | 开工前 3 天 |

![施工进度横道图（示意）]({SAMPLE_IMAGE_NAME})
<!-- panel-end -->
"""


def png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_sample_png(path: Path, width: int = 800, height: int = 200) -> None:
    """用标准库画一张灰度示意横道图，不为样张引入图像依赖。"""
    bars = [(40, 300), (200, 520), (380, 700), (560, 760)]
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)  # PNG 行过滤类型：无
        row = (y - 20) // 45
        in_bar_row = 0 <= row < len(bars) and 30 + row * 45 <= y < 50 + row * 45
        for x in range(width):
            value = 255
            if x in (0, width - 1) or y in (0, height - 1):
                value = 0
            elif x % 100 == 0:
                value = 200
            if in_bar_row and bars[row][0] <= x < bars[row][1]:
                value = 0
            pixels.append(value)
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) + png_chunk(b"IDAT", zlib.compress(bytes(pixels), 9))
    path.write_bytes(data + png_chunk(b"IEND", b""))


def user_source() -> str:
    return f"用户自定义（{date.today().isoformat()}）"


def custom_fields(record: dict) -> list[str]:
    base = preset_format(record["preset"])
    return [key for key in FIELD_LABELS if record[key] != base[key] or record["sources"][key] != base["sources"][key]]


def format_card_markdown(record: dict, docx_path: Path, pdf_path: Path | None, pdf_note: str,
                         notes: list[str] | None = None, *, plain_sample: bool = False) -> str:
    catalog = load_catalog()
    preset = catalog["presets"][record["preset"]]
    changed = custom_fields(record)
    install = fonts_needing_install(record, catalog)
    lines = [
        "# 格式确认卡",
        "",
        f"- 基础预设：{record['preset']} {preset['name']}",
        f"- 与预设不同的字段：{'、'.join(FIELD_LABELS[key] for key in changed) if changed else '无'}",
        f"- 样张 DOCX：{docx_path}",
        f"- 样张 PDF：{pdf_path if pdf_path else '无'}（{pdf_note}）",
        f"- 样张正文：{'无分块线框' if plain_sample else '黑色细线分块，表格、图题可编辑'}。",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "| 字段 | 取值 | 出处 |",
        "|---|---|---|",
        *(f"| {label} | {value} | {source} |" for label, value, source in format_card_rows(record)),
        "",
        "## 提醒",
        "",
        f"- 需另装的字体（W8）：{'、'.join(install) + '。评审端未安装时会替换字体，版式和页数随之变化' if install else '无'}。",
        "- 招标文件（含补遗）对格式另有规定时，阶段 2 解标后以招标文件为准，差异列成“所选 / 招标文件要求 / 最终采用”三列请你确认；招标文件写的是“建议”时也默认照做。",
        "- 用户看过样张并明确同意后，格式才写入 project-state.json 的 document_format 并锁定；"
        "确认前生成器和校验器拒绝按项目格式出稿。",
        *(f"- {note}" for note in notes or []),
        "",
    ]
    return "\n".join(lines)


def render_sample(record: dict, output_dir: Path, name: str, export_pdf: bool = True, office: str = "auto",
                  notes: list[str] | None = None, *, plain_sample: bool = False) -> dict:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_sample_png(output_dir / SAMPLE_IMAGE_NAME)
    markdown_path = output_dir / f"{name}.md"
    # Preview style is independent of typography and does not alter the project's format lock.
    markdown = (SAMPLE_MARKDOWN.replace("<!-- panel-grid-start -->\n", "").replace("<!-- panel-end -->\n", "")
                if plain_sample else SAMPLE_MARKDOWN)
    markdown_path.write_text(markdown, encoding="utf-8")
    header = "" if record["blind_mode"] else SAMPLE_HEADER
    build = build_response_docx([markdown_path], output_dir / f"{name}.docx", header, document_format=record,
                                format_preview=True)
    docx_path = Path(build["output"])  # Word 占用原文件时生成器会另存为更新版
    pdf_path, pdf_note = None, "已指定 --no-pdf"
    if export_pdf:
        candidate = docx_path.with_suffix(".pdf")
        app = export_pdf_via_office(docx_path, candidate, office)
        if app:
            pdf_path, pdf_note = candidate, f"已用 {app} 导出"
        else:
            pdf_note = "未找到可用的 Word/WPS 或导出失败，请直接打开 DOCX 查看"
    card_path = output_dir / f"{name}-确认卡.md"
    card_path.write_text(format_card_markdown(record, docx_path, pdf_path, pdf_note, notes, plain_sample=plain_sample),
                         encoding="utf-8")
    return {
        "preset": record["preset"],
        "docx": str(docx_path),
        "pdf": str(pdf_path) if pdf_path else None,
        "pdf_note": pdf_note,
        "card": str(card_path),
        "warnings": build["warnings"],
    }


def preset_table(codes: list[str]) -> str:
    catalog = load_catalog()
    lines = ["| 代号 | 名称 | 正文字体/字号 | 标题字体 | 标题字号（一/二/三级） | 行距 | 页边距（上/下/左/右） |",
             "|---|---|---|---|---|---|---|"]
    for code in codes:
        record = preset_format(code, catalog)
        fonts = "/".join(record[f"heading{level}_font"] for level in (1, 2, 3))
        sizes = " / ".join(describe_value(f"heading{level}_size_pt", record) for level in (1, 2, 3))
        spacing = f"{describe_value('line_spacing_rule', record)} {describe_value('line_spacing', record)}"
        margins = "/".join(f"{record[f'margin_{side}_cm']:g}" for side in ("top", "bottom", "left", "right"))
        lines.append(f"| {code} | {catalog['presets'][code]['name']} | {record['body_font']} "
                     f"{describe_value('body_size_pt', record)} | {fonts} | {sizes} | {spacing} | {margins} 厘米 |")
    return "\n".join(lines)


def propose_review(project_dir: Path, kind: str, selection: dict, tender: dict | None,
                   export_pdf: bool = True, office: str = "auto", *, plain_sample: bool = False) -> dict:
    """Render the candidate format and park it in project-state.json until the user confirms."""
    project_dir = project_dir.expanduser().resolve()
    load_state(project_dir)  # 先确认是 qingtian-bid 项目，再写任何文件
    candidate, rows = compose_format(selection, tender)
    format_dir = project_dir / PROJECT_FORMAT_DIR
    format_dir.mkdir(parents=True, exist_ok=True)
    diff_path = None
    notes = [f"确认命令（用户明确同意后才运行）：render_format_sample.py --project \"{project_dir}\" --confirm"]
    if tender is not None:
        diff_path = format_dir / "格式差异-招标文件.md"
        selected = compose_format(selection, None)[0]
        diff_path.write_text(diff_markdown(rows, selected, candidate, tender), encoding="utf-8")
        notes.insert(0, f"招标文件格式差异见 {diff_path}，逐行确认后再确认样张。")
    name = "格式样张-招标文件覆盖" if tender is not None else "格式样张"
    sample = render_sample(candidate, format_dir, name, export_pdf, office, notes, plain_sample=plain_sample)
    state = load_state(project_dir)
    state["format_review"] = make_review(kind, selection, tender, candidate, rows, sample, diff_path)
    save_state(project_dir, state)
    return {**sample, "kind": kind, "diff": str(diff_path) if diff_path else None,
            "diff_rows": rows, "status": "待用户确认"}


def project_selection_review(project_dir: Path, preset: str | None, settings: dict,
                             export_pdf: bool, office: str, *, plain_sample: bool = False) -> dict:
    """用户改自己的格式选择：开工确认前反复调整，或确认后改主意（招标文件规定仍然覆盖）。"""
    state = load_state(project_dir)
    tender = current_tender(state)
    check_tender_settings(settings, tender)
    base = current_selection(state)
    if preset or base is None:
        base = preset_format(preset)
    selection = apply_format_settings(base, settings, user_source()) if settings else base
    kind = "kickoff" if state["stages"].get("0") != "done" else "selection"
    return propose_review(project_dir, kind, selection, tender, export_pdf, office, plain_sample=plain_sample)


def project_tender_review(project_dir: Path, tender_file: Path, settings: dict, deviate: list[str],
                          deviation_note: str, export_pdf: bool, office: str, *, plain_sample: bool = False) -> dict:
    """阶段 2：招标文件（含补遗）的格式规定覆盖用户所选，出三列差异和新样张。"""
    state = load_state(project_dir)
    if state["stages"].get("0") != "done" or current_selection(state) is None:
        raise ValueError("开工格式尚未确认：先完成阶段 0 的格式样张确认，再按招标文件覆盖")
    tender = add_deviations(load_tender_spec(tender_file), deviate, deviation_note)
    card_path = project_dir / RULE_CARD_FILE
    if card_path.is_file():
        # 规则卡在阶段 2 先于格式覆盖起草；评审注释写了扣分而格式规定漏登的，偏离时用户看不到扣分原文
        issue = penalty_issue(load_json(card_path, "规则卡").get("review_notes", {}).get("value"), tender)
        if issue:
            raise ValueError(issue)
    check_tender_settings(settings, tender)
    selection = current_selection(state)
    if settings:
        selection = apply_format_settings(selection, settings, user_source())
    return propose_review(project_dir, "tender", selection, tender, export_pdf, office, plain_sample=plain_sample)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成格式样张与格式确认卡，或列出格式预设；--project 时管理项目格式。")
    parser.add_argument("--list-presets", action="store_true", help="列出格式预设；可配合 --filter 筛选。")
    parser.add_argument("--filter", action="append", default=[], metavar="字段=值",
                        help="按字段筛选预设，如 正文字体=仿宋、行距方式=固定值；可重复。")
    parser.add_argument("--output-dir", type=Path, help="样张输出目录（不在项目里出样时用）。")
    parser.add_argument("--project", type=Path, help="项目目录：样张写到 analysis/format/，并登记为待确认的格式变更。")
    parser.add_argument("--preset", help="基础预设代号，默认取预设库的 default_preset；--project 时默认沿用当前所选。")
    parser.add_argument("--set", dest="settings", action="append", default=[], metavar="字段=值",
                        help="在预设上改个别字段，如 正文字号=小四、latin_font=Times New Roman；可重复。")
    parser.add_argument("--all-presets", action="store_true", help="一次生成全部预设的样张（不能与 --set 同用）。")
    parser.add_argument("--name", help="输出文件名（不含扩展名），默认按预设代号命名。")
    parser.add_argument("--tender-format", type=Path, help="--project 时：阶段 2 写的招标文件格式规定（JSON）。")
    parser.add_argument("--deviate", action="append", default=[], metavar="字段",
                        help="--tender-format 时：保留所选、偏离招标文件“建议”的字段；可重复，须配 --deviation-note。")
    parser.add_argument("--deviation-note", default="", help="用户同意偏离的记录，如“用户 2026-10-28 明确同意”。")
    parser.add_argument("--confirm", action="store_true", help="--project 时：用户明确同意样张后，锁定待确认的格式。")
    parser.add_argument("--no-pdf", action="store_true", help="不调用 Word/WPS 导出 PDF。")
    parser.add_argument("--plain-sample", action="store_true", help="样张正文不使用分块线框，仍保留图表。")
    parser.add_argument("--office", choices=("auto", "word", "wps"), default="auto", help="导出 PDF 用哪个应用。")
    args = parser.parse_args()
    if args.project is not None:
        if args.list_presets or args.output_dir or args.all_presets or args.name:
            parser.error("--project 不能与 --list-presets、--output-dir、--all-presets、--name 同用")
        if args.confirm and (args.preset or args.settings or args.tender_format or args.deviate or args.plain_sample):
            parser.error("--confirm 只确认已出的样张，不能同时改格式")
        if args.tender_format and args.preset:
            parser.error("--tender-format 以当前所选为底，不能同时换预设")
        if (args.deviate or args.deviation_note) and not args.tender_format:
            parser.error("--deviate、--deviation-note 只用于 --tender-format")
        return args
    if args.confirm or args.tender_format or args.deviate:
        parser.error("--confirm、--tender-format、--deviate 须配 --project")
    if not args.list_presets and args.output_dir is None:
        parser.error("生成样张须指定 --output-dir 或 --project；只看预设请用 --list-presets")
    if args.all_presets and (args.settings or args.preset or args.name):
        parser.error("--all-presets 不能与 --set、--preset、--name 同用")
    return args


def run_project_mode(args: argparse.Namespace) -> object:
    if args.confirm:
        return confirm_review(args.project)
    settings = with_blind_mode_defaults(dict(parse_assignment(item) for item in args.settings))
    if args.tender_format:
        return project_tender_review(args.project, args.tender_format, settings, args.deviate,
                                     args.deviation_note, not args.no_pdf, args.office, plain_sample=args.plain_sample)
    return project_selection_review(args.project, args.preset, settings, not args.no_pdf, args.office,
                                    plain_sample=args.plain_sample)


def run_standalone(args: argparse.Namespace) -> object:
    if args.list_presets:
        criteria = dict(parse_assignment(item) for item in args.filter)
        codes = filter_presets(criteria)
        return preset_table(codes) if codes else "没有符合筛选条件的预设。"
    catalog = load_catalog()
    if args.all_presets:
        jobs = [(preset_format(code, catalog), f"{code}-格式样张") for code in catalog["presets"]]
    else:
        record = preset_format(args.preset, catalog)
        settings = with_blind_mode_defaults(dict(parse_assignment(item) for item in args.settings))
        if settings:
            record = apply_format_settings(record, settings, user_source(), catalog)
        default_name = f"{record['preset']}{'-自定义' if settings else ''}-格式样张"
        jobs = [(record, args.name or default_name)]
    return [render_sample(record, args.output_dir, name, not args.no_pdf, args.office, plain_sample=args.plain_sample)
            for record, name in jobs]


def main() -> int:
    args = parse_args()
    try:
        result = run_project_mode(args) if args.project is not None else run_standalone(args)
    except (OSError, ValueError) as exc:
        print(f"格式样张生成失败: {exc}", file=sys.stderr)
        return 2
    print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
