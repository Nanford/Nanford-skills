"""Stage-6 and stage-7 state of qingtian-bid: completion conditions and the 初步评审对照 (B12) confirmations.

INPUT: <project>/project-state.json; output/施工组织设计.docx and its .build-report.json; the confirmed drafts
       (writing_gate); required image jobs and build hashes; check_qingtian_final for stage-7 gates; analysis/rule-card.json.
OUTPUT: stage6_issues() and stage7_issues() for project_status --complete 6 / 7; confirm_b12() records
        final.b12.<row> in project-state.json; final_summary() for the progress summary.
POS: state layer of stages 6-7 (design v1 §9 第 4b-2 步), next to writing_gate (stage 5). Stage 6 is done when the
     finished file at the fixed path was built from exactly the confirmed drafts, in matrix order, with the locked
     format, and its layout check has no blockers. Whether it was saved in Word since is stage 7's business (B3 runs
     --final on the current file), so the build's docx sha256 is not compared. Stage 7 is done when
     check_qingtian_final finds no open blocking hit and no open hint on the current file (every W hit fixed or
     given a reason; gate-catalog: 警告项逐条处理，或书面说明不改的理由), which includes every B12 row confirmed, and
     review/gate-report.json records that passing run. A B12 confirmation locks the finished DOCX's sha256 and that
     row of the 初步评审表 (决策 D9); it is refused while B3, B4 or B9 still block, since those are its evidence (决策 4b-3A).

project-state.json keys owned here:
  final.b12.<row>   {docx_sha256, rule_row: digest, confirmed_at}
"""

from __future__ import annotations

from pathlib import Path

from check_qingtian_final import (
    B12_EVIDENCE,
    FINISHED_DOCX,
    REPORT_FILE,
    b12_rows,
    b12_status,
    final_run,
)
from docx_font_profiles import normalize_document_format
from format_state import save_state
from project_cards import RULE_CARD_FILE, file_sha256, load_json, load_project, now_text
from response_matrix import matrix_items, writing_inputs
from validate_docx_format import validate_docx_format
from writing_gate import item_records, stage5_issues
from visual_assets import visual_dependency_issues

BUILD_REPORT = "output/施工组织设计.build-report.json"
REBUILD = "按 stage-6-assembly.md 第三节写清单后重新出稿"


# ---------- 阶段 6 ----------

def format_issues(state: dict, report: dict) -> list[str]:
    try:
        locked = normalize_document_format(state.get("document_format") or {})
    except ValueError as exc:
        return [f"项目锁定的格式读不出来（{exc}）：回到阶段 0 或 stage-6-assembly.md 第二节"]
    if report.get("document_format") != locked:
        return [f"成品出稿时用的格式与项目现在锁定的格式不一致（出稿后格式又确认过？）：{REBUILD}"]
    return []


def item_sources(project_dir: Path, state: dict) -> dict[Path, tuple[int, str]]:
    """各项确认过的中间稿：路径 → (项号, 确认时的 sha256)。阶段 5 的条件保证每项都有记录且未失效。"""
    records = item_records(state)
    return {(project_dir / "output" / records[str(no)]["file"]).resolve(): (no, records[str(no)]["sha256"])
            for no in sorted(matrix_items(writing_inputs(project_dir))) if str(no) in records}


def front_issue(path: Path, sha: object, drafts_dir: Path) -> str | None:
    """不是中间稿的来源只许是 实施方案/00- 开头的封面、目录，且出稿后没改过。"""
    if path.parent != drafts_dir or not path.name.startswith("00-"):
        return f"成品收进了不是中间稿的文件 {path.name}：只收 实施方案/ 下 00 开头的封面、目录和各项中间稿"
    if not path.is_file() or file_sha256(path) != sha:
        return f"出稿后 {path.name} 改过或删了：{REBUILD}"
    return None


def source_issues(project_dir: Path, state: dict, sources: list) -> list[str]:
    """成品的来源：各项中间稿一项不缺、按矩阵顺序、正是确认过的那版；封面、目录在最前。"""
    expected = item_sources(project_dir, state)
    drafts_dir = (project_dir / "output" / "实施方案").resolve()
    built = [(Path(str(entry.get("file"))).resolve(), entry.get("sha256")) for entry in sources if isinstance(entry, dict)]
    issues, seen_item = [], False
    for path, sha in built:
        if path in expected:
            seen_item = True
            no, confirmed = expected[path]
            if sha != confirmed:
                issues.append(f"第 {no} 项出稿用的不是确认过的那版中间稿（出稿后又改过、重新确认过）：{REBUILD}")
            continue
        issue = front_issue(path, sha, drafts_dir)
        if issue is None and seen_item:
            issue = f"{path.name} 排在评审内容中间：封面、目录放在最前"
        if issue:
            issues.append(issue)
    order = [path for path, _ in built if path in expected]
    if order != list(expected):
        missing = [str(no) for path, (no, _) in expected.items() if path not in order]
        detail = f"缺第 {'、'.join(missing)} 项" if missing else "顺序与评审内容不一致或有重复"
        issues.append(f"成品没按评审内容的顺序收齐各项中间稿（{detail}）：{REBUILD}")
    return issues


def build_issues(project_dir: Path, state: dict) -> list[str]:
    """构建报告：是正式出稿，出到固定路径，格式是锁定的格式，来源是确认过的中间稿。"""
    path = project_dir / BUILD_REPORT
    if not path.is_file():
        return [f"还没有构建报告 {BUILD_REPORT}：{REBUILD}"]
    try:
        report = load_json(path, "构建报告")
    except ValueError as exc:
        return [str(exc)]
    if report.get("format_preview"):
        return [f"{BUILD_REPORT} 是格式样张的构建记录，不是成品：{REBUILD}"]
    if Path(str(report.get("output"))).resolve() != (project_dir / FINISHED_DOCX).resolve():
        return [f"构建报告记的成品不是 {FINISHED_DOCX}：关掉 Word、WPS 后{REBUILD}"]
    if not isinstance(report.get("sources"), list):
        return [f"构建报告没有来源文件的 sha256（第 4b-2 步之前出的稿）：{REBUILD}"]
    plan = project_dir / "analysis" / "visual-assets.json"
    if plan.is_file():
        try:
            required = load_json(plan, "图片清单").get("required_jobs")
        except ValueError as exc:
            return [str(exc)]
        visual = report.get("visual_manifest")
        if required and (not isinstance(visual, dict) or visual.get("file") != str(plan.resolve())):
            return [f"构建未使用登记必需配图的项目清单：{REBUILD}"]
    return (format_issues(state, report) + source_issues(project_dir, state, report["sources"])
            + visual_dependency_issues(report, project_dir / FINISHED_DOCX))


def layout_issues(docx: Path) -> list[str]:
    result = validate_docx_format(docx, write_files=False)
    return [f"版式校验：{item.get('message')}（{item.get('target')}）" for item in result.get("issues") or []
            if item.get("level") == "blocker"]


def stage6_issues(project_dir: Path, state: dict) -> list[str]:
    """阶段 6 完成条件：阶段 5 仍成立；成品在固定路径，由确认过的中间稿按锁定格式出稿；版式校验没有阻断项。
    出稿后在 Word 里保存过不算问题（阶段 7 的 B3 在当前成品上跑 --final）。"""
    issues = stage5_issues(project_dir, state)
    if issues:
        return [f"阶段 5 的条件不再成立：{issue}" for issue in issues]
    docx = project_dir / FINISHED_DOCX
    if not docx.is_file():
        return [f"还没有成品 {FINISHED_DOCX}：{REBUILD}"]
    issues = build_issues(project_dir, state)
    return issues if issues else layout_issues(docx)


# ---------- 阶段 7 ----------

def report_issues(project_dir: Path, sha: str) -> list[str]:
    """门禁报告要记下这次放行的结果：成品再存过、或报告出在记录理由之前，都要重出。"""
    path = project_dir / REPORT_FILE
    rerun = "运行 check_qingtian_final.py <项目目录> 重出门禁报告"
    if not path.is_file():
        return [f"还没有门禁报告 {REPORT_FILE}：{rerun}"]
    try:
        report = load_json(path, "门禁报告")
    except ValueError as exc:
        return [str(exc)]
    if report.get("docx_sha256") != sha:
        return [f"门禁报告不是当前成品的（之后成品又存过）：{rerun}"]
    if report.get("ready") is not True:
        return [f"门禁报告出在问题处理完之前：{rerun}"]
    return []


def stage7_issues(project_dir: Path, state: dict) -> list[str]:
    """阶段 7 完成条件：阶段 6 仍成立；当前成品没有未放行的阻断项和未处理的提示（含 B12 每行已确认）；
    门禁报告记的是这次的结果。不调 Word/WPS：还没计页的，按 B2 阻断报出来。"""
    issues = stage6_issues(project_dir, state)
    if issues:
        return [f"阶段 6 的条件不再成立：{issue}" for issue in issues]
    result = final_run(project_dir, counter=None)
    issues = [f"{entry['gate']} [{entry['id']}] {entry['message']}" for entry in result["blocking"] + result["warnings"]]
    return issues if issues else report_issues(project_dir, result["docx_sha256"])


def row_error(rule_card: dict, row: int) -> str:
    rows = (rule_card.get("preliminary_review") or {}).get("value") or []
    if 1 <= row <= len(rows):
        return f"初步评审第 {row} 行与施组无关（tech_related 为 false），不用确认"
    return f"初步评审表没有第 {row} 行（共 {len(rows)} 行）"


def confirm_b12(project_dir: Path, row: int) -> dict:
    """用户逐条核对、明确认可初步评审表第 row 行后才调用；锁定成品的 sha256 和这一行（决策 4b-3A、D9）。"""
    project_dir, state = load_project(project_dir)
    if state["stages"].get("6") != "done":
        raise ValueError("阶段 6 还没完成：出稿并完成阶段 6 后才核对初步评审对照")
    rule_card = load_json(project_dir / RULE_CARD_FILE, "规则卡")
    rows = {entry["row"]: entry for entry in b12_rows(rule_card)}
    if row not in rows:
        raise ValueError(row_error(rule_card, row))
    issues = stage6_issues(project_dir, state)
    if issues:
        raise ValueError(f"阶段 6 的条件不再成立，不能确认：{issues[0]}")
    result = final_run(project_dir, counter=None)
    evidence = [entry for entry in result["blocking"] if entry["gate"] in B12_EVIDENCE]
    if evidence:
        first = evidence[0]
        raise ValueError(f"{'、'.join(sorted({entry['gate'] for entry in evidence}))} 还有 {len(evidence)} 条阻断，"
                         f"初步评审对照的证据不成立，先处理：{first['gate']} [{first['id']}] {first['message']}")
    record = {"docx_sha256": result["docx_sha256"], "rule_row": rows[row]["digest"], "confirmed_at": now_text()}
    state.setdefault("final", {}).setdefault("b12", {})[str(row)] = record
    if state["stages"].get("7") == "pending":
        state["stages"]["7"] = "in-progress"
    save_state(project_dir, state)
    return {"project": str(project_dir), "row": row, **record}


def report_summary(project_dir: Path, sha: str) -> str:
    try:
        report = load_json(project_dir / REPORT_FILE, "门禁报告")
    except ValueError:
        return "还没出门禁报告"
    if report.get("docx_sha256") != sha:
        return "门禁报告不是当前成品的"
    summary = report.get("summary") or {}
    return f"门禁报告阻断 {summary.get('blocking')} 条、未处理提示 {summary.get('warnings')} 条（{report.get('checked_at')}）"


def final_summary(project_dir: Path, state: dict) -> str:
    docx = project_dir / FINISHED_DOCX
    if not docx.is_file():
        return "—"
    try:
        rule_card = load_json(project_dir / RULE_CARD_FILE, "规则卡")
    except ValueError as exc:
        return str(exc)
    sha = file_sha256(docx)
    rows = b12_status(state, rule_card, sha)
    done = sum(1 for entry in rows if entry["status"] == "confirmed")
    return f"{report_summary(project_dir, sha)}；初步评审对照已确认 {done}/{len(rows)} 行"
