"""Draft the response matrix from the confirmed rule card and resource card (qingtian-bid stage 4).

INPUT: <project>/analysis/rule-card.json (review items, mandatory clauses whose 去处 is 施组, page limit,
       project_category), analysis/resource-card.json, analysis/fact-card.json (its site limits, through
       site_limits); project-state.json (stage 3 must be done); templates/response-matrix.json; the category
       knowledge cards the rule card selects (category_cards).
OUTPUT: analysis/response-matrix.json with one row per review item (title in the original wording, empty
        points and facts, prefilled resources, ★ landings, control points and page budget) and the
        analysis/response-matrix.md view. An existing matrix is never overwritten: the draft goes to
        analysis/response-matrix-候选-<时间>.json. JSON summary on stdout.
POS: stage-4 helper of qingtian-bid (design v1 §9, 第 3c 步). It only proposes: points, facts and the R13
     notes are written by hand, control points come prefilled with the category cards' 必备要点 (【推断】, 决策
     5-4A) and are edited for this project (deleted ones are not warned about by W9 later), then the user
     confirms the outline. A card point that plans a facility the confirmed site limits forbid (材料堆场、
     办公区……) is rewritten to "现场不设……，写明场外解决方式" with the card text kept after it (第 6b 步, 决策
     S6-A). Prefills are keyword guesses (物资/机械/劳动力 → that resource section; 工期/质量/安全 → the
     item named after it; 招标指定 clauses → the item whose title has 重点/难点) and must be checked. Page budgets follow the
     示范文本 defaults; a title outside them weighs DEFAULT_PAGES. When the tender lists no review items
     (T-合格), it stops: the chapters come from the user, not from a guess. Each row starts citing its own
     review item and the clauses landed on it (决策 D9); other rule rows it uses are added by hand.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

from category_cards import control_point_prefill, project_cards
from fact_resource_cards import card_template
from project_cards import (FACT_CARD_FILE, MATRIX_FILE, RESOURCE_CARD_FILE, RULE_CARD_FILE, TECH_SCOPE,
                           TENDER_SPECIFIED, load_json, load_project, scoped_clauses)
from response_matrix import check_matrix, expected_items
from rule_card_rows import REVIEW_PREFIX
from site_limits import forbidden_objects, rewrite_point


# 设计稿 §5.1 的默认页数【推断】：示范文本 10 项评审内容合计 47 页，加余量 3 页正好 50 页
DEMO_PAGES = {
    "工程概况": 3, "主要施工方法": 14, "拟投入的主要物资计划": 3, "拟投入的主要施工机械、设备计划": 3,
    "劳动力安排计划": 3, "确保工程质量的技术组织措施": 5, "确保安全生产的技术组织措施": 5,
    "确保工期的技术组织措施": 4, "确保文明施工的技术组织措施": 4, "施工总平面布置图": 3,
}
DEFAULT_PAGES = 3  # 没有篇幅上限、标题又不是示范文本那 10 项时，每项先给 3 页
# 标题关键词 → 预填的资源卡节
RESOURCE_KEYWORDS = (("物资", "materials"), ("机械", "machinery"), ("设备", "machinery"), ("劳动力", "labor"))
# 条款原文里的关键词 → 落在标题含同一关键词的那一项
LANDING_KEYWORDS = ("工期", "质量", "安全")
# 招标指定的内容 → 落在标题含这些字的那一项（真实招标文件把"重点、难点"列成一项评审内容）
FOCUS_WORDS = ("重点", "难点")
# R13：实施落在施工方法，进度落在工期措施，组织分布在劳动力、质量、安全措施（设计稿 R13 行）
COVERAGE_KEYWORDS = {"实施": ("施工方法",), "进度": ("工期",), "组织": ("劳动力", "质量", "安全")}
UNSPECIFIED_STOP = ("规则卡评审内容为“招标文件未规定”（T-合格）：脚手架不编章节，硬停。请用户给出章节清单和出处"
                    "（如招标文件第八章），按 stage-4-matrix.md 第五节手工写矩阵")


def prefill_resources(title: str, resource_card: dict) -> list[str]:
    sections = list(dict.fromkeys(section for word, section in RESOURCE_KEYWORDS if word in title))
    return [entry["id"] for section in sections for entry in resource_card.get(section) or []
            if isinstance(entry, dict) and entry.get("id")]


def prefill_landings(title: str, clauses: list) -> list[str]:
    """招标指定的内容不按关键词猜：重点难点原文常带"工期""安全"字样，却对应重难点那一项（land_tender_specified）。"""
    words = [word for word in LANDING_KEYWORDS if word in title]
    return [clause["id"] for clause in clauses if isinstance(clause, dict) and clause.get("id")
            and clause.get("type") != TENDER_SPECIFIED and any(word in str(clause.get("text") or "") for word in words)]


def land_tender_specified(items: list[dict], clauses: list) -> None:
    """招标指定的重点难点、危大清单还没落点的，落在标题含"重点"或"难点"的第一项（招标文件把它对应重难点评审）；
    没有这一项就留给人选，矩阵校验会报没有落点。"""
    focus = next((item for item in items if any(word in item["title"] for word in FOCUS_WORDS)), None)
    if focus is None:
        return
    landed = {ref for item in items for ref in item["mandatory"]}
    focus["mandatory"] += [clause["id"] for clause in clauses if isinstance(clause, dict) and clause.get("id")
                           and clause.get("type") == TENDER_SPECIFIED and clause["id"] not in landed]


def prefill_coverage(titles: list[str]) -> dict:
    """只预填落点，依据 note 留空：分布覆盖的理由要由人写，校验会要求补上。"""
    return {aspect: {"items": [no for no, title in enumerate(titles, 1) if any(word in title for word in words)],
                     "note": ""}
            for aspect, words in COVERAGE_KEYWORDS.items()}


def whole(value: float) -> float | int:
    return int(value) if float(value).is_integer() else value


def split_half_pages(weights: list[int], units: int) -> list[int]:
    """最大余数法按权重分 units 个半页，每项至少 1 个。零头逐个补给按比例最吃亏的项，不全堆在一项上，
    免得别的项被压到示范文本默认页数以下（Q5：不能偏科）。调用方保证 units 不少于项数。"""
    shares = [weight * units / sum(weights) for weight in weights]
    split = [max(1, math.floor(share)) for share in shares]
    while sum(split) != units:
        gap = [share - part for share, part in zip(shares, split)]
        if sum(split) < units:
            split[gap.index(max(gap))] += 1
        else:  # 保底的 1 个半页挤占了预算：从按比例多拿最多、又不止 1 个的项里扣
            split[min((index for index, part in enumerate(split) if part > 1), key=gap.__getitem__)] -= 1
    return split


def page_budget(titles: list[str], rule_card: dict, fixed: float) -> list[float | int]:
    """按示范文本默认页数的比例在上限内分配（不是那 10 项的标题按 DEFAULT_PAGES 计），以 0.5 页为单位。"""
    limit = (rule_card.get("page_limit") or {}).get("value")
    if not isinstance(limit, int) or isinstance(limit, bool):
        return [DEMO_PAGES.get(title, DEFAULT_PAGES) for title in titles]
    budget = limit - fixed
    if budget < 0.5 * len(titles):
        raise ValueError(f"篇幅上限 {limit} 页扣除封面目录和余量后不够每项 0.5 页：先和用户商定篇幅分配")
    # 示范文本以外的标题（如招标文件加的第 11 项"重点、难点"）按 DEFAULT_PAGES 计权，别的项仍按默认比例，
    # 不因多一项就全部平均分（2026-10-30 真实合肥招标文件）
    weights = [DEMO_PAGES.get(title, DEFAULT_PAGES) for title in titles]
    return [whole(units / 2) for units in split_half_pages(weights, math.floor(budget * 2))]


def build_matrix(rule_card: dict, resource_card: dict, fact_card: dict | None = None) -> dict:
    """矩阵骨架：一项评审内容一行，标题照抄规则卡原文；要点、事实留空等人写，控制点按类别知识卡预填，
    与事实卡现场限制矛盾的预填点改写成"现场不设……"。"""
    expected = expected_items(rule_card)
    if expected is None:
        raise ValueError(UNSPECIFIED_STOP)
    matrix = card_template("response-matrix.json")
    titles = [str(item.get("title") or "") for item in expected]
    pages = page_budget(titles, rule_card, matrix["front_pages"] + matrix["reserve_pages"])
    clauses = scoped_clauses(rule_card, TECH_SCOPE)  # 去处为提交前清单的不在施组里预填落点（决策 4c-4A）
    cards, _ = project_cards(rule_card)  # 选到但没交付的卡先跳过，rule-card.md 已写明
    # 补疑、答疑禁止设堆场、办公区的，卡片总平面要点照常要求标注，代理只能逐条删（第 6b 步真实项目，决策 S6-A）
    forbidden = forbidden_objects(list((fact_card or {}).get("facts") or []))
    matrix["items"] = [{"no": no, "title": title, "points": [], "facts": [], "facts_note": "",
                        "resources": prefill_resources(title, resource_card),
                        "mandatory": prefill_landings(title, clauses),
                        "control_points": [rewrite_point(point, forbidden)
                                           for point in control_point_prefill(cards, title)],
                        "pages": pages[no - 1]}
                       for no, title in enumerate(titles, 1)]
    land_tender_specified(matrix["items"], clauses)
    for item in matrix["items"]:  # 落点全部预填完才算得出引用
        item["cites"] = [f"{REVIEW_PREFIX}{item['no']}", *item["mandatory"]]
    matrix["coverage"] = prefill_coverage(titles)
    return matrix


def scaffold_matrix(project_dir: Path) -> dict:
    project_dir, state = load_project(project_dir)
    if state["stages"].get("3") != "done":
        raise ValueError("阶段 3 事实卡与资源卡未完成：大纲要引用确认过的事实和资源，先完成阶段 3")
    rule_card = load_json(project_dir / RULE_CARD_FILE, "规则卡")
    fact_card = load_json(project_dir / FACT_CARD_FILE, "事实卡")
    matrix = build_matrix(rule_card, load_json(project_dir / RESOURCE_CARD_FILE, "资源卡"), fact_card)
    cards, missing = project_cards(rule_card)
    target = project_dir / MATRIX_FILE
    if target.exists():
        # 已有矩阵里有写好的要点和引用，不覆盖；候选另存，由人对照合并
        target = target.with_name(f"response-matrix-候选-{datetime.now():%Y%m%d-%H%M%S}.json")
    target.write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    views = check_matrix(project_dir)["views"] if target.name == "response-matrix.json" else []
    return {"response_matrix": str(target), "views": views, "items": len(matrix["items"]),
            "category_cards": [card["name"] for card in cards], "undelivered_cards": missing,
            "site_limits": forbidden_objects(list(fact_card.get("facts") or [])),
            "note": "骨架：逐项写要点、引用事实（每项至少 2 条或写明原因），核对预填的资源、★落点和页数，写实施/进度/组织"
                    "的分布依据；控制点是类别知识卡的通用要点【推断】，不适用本项目的删掉，与现场限制（site_limits）矛盾的"
                    "已改写为现场不设、写明场外解决方式；校验通过后请用户确认大纲"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按确认过的规则卡出响应矩阵骨架（一项评审内容一行，预填资源、★落点和页数）。")
    parser.add_argument("project", type=Path, help="项目目录。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = scaffold_matrix(args.project)
    except (OSError, ValueError) as exc:
        print(f"响应矩阵骨架生成失败: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
