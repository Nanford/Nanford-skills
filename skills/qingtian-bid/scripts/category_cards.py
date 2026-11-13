"""Category knowledge cards of qingtian-bid: the 13-card catalog, card validation, picking a project's cards
from its rule card, the outline's control-point prefill, the W9 check on drafts, BOQ main-item matching and
the Markdown views.

INPUT: references/category-cards/<名称>.json (JSON is the source of truth, 决策 5-1A); the project_category
       field of a confirmed rule card (主类别、涉及专业、场景, 决策 5-2A). Standard library only: project_cards
       imports the catalog for rule-card validation, so this module must not import it back.
OUTPUT: CATALOG; BOQ_CODE (清单编码单元格，阶段 2、3 读清单共用); check_category() (rule-card field check);
        selected_names() / no_card_names() (选到的类别里有卡、没卡的); card_path() / load_card() / project_cards();
        aspects_of(title);
        card_points(); control_point_prefill(); kept_points(); w9_hits() (at most one hint per item);
        boq_card(); render_card();
        a CLI that validates every card and rewrites the Markdown views next to them (--write).
POS: knowledge layer of stages 2～5 (design v1 §9 第 5 步). Every card is 【推断】 general construction
     knowledge, never a tender rule: it only prefills control points and warns (W9, 决策 5-4A); points the
     user deleted from the confirmed matrix are not warned about again (第 6b 步改). The tender's own 重点难点
     come first, so items whose title names 重点/难点 get no card points and no W9. Cards hold
     points, not paragraphs (Q10、W4); their machine and labour hints only point at gaps in the resource card
     and never go into the 施组 by themselves (R7).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
CARD_DIR = SKILL_DIR / "references" / "category-cards"
CARD_SCHEMA = "qingtian-category-card/1"
CATEGORY_FIELD = "project_category"
MAIN, MODULE, SCENARIO = "主类别", "专业", "场景"
# 导则 1.3.2 的 9 类（AI 类人评审支持的工程类型）；3 个专业和 1 个场景是 9 类以外常见的组合部分，
# 一个项目 = 主类别 + 涉及专业 + 场景（决策 5-3A）。名称就是卡片文件名。主类别和涉及专业不限名录（决策 D11），
# 名录外的没有知识卡，见 no_card_names
CATALOG = {
    "土建工程": (MAIN, "A080104"), "通风与空调工程": (MAIN, "A080108"), "装饰装修工程": (MAIN, "A080109"),
    "电梯工程": (MAIN, "A080112"), "道路工程": (MAIN, "A080201"), "给水工程": (MAIN, "A080204"),
    "排水工程": (MAIN, "A080205"), "园林工程": (MAIN, "A083001"), "绿化工程": (MAIN, "A083002"),
    "建筑电气与照明工程": (MODULE, ""), "建筑给排水与消防工程": (MODULE, ""), "建筑智能化工程": (MODULE, ""),
    "既有设施改造": (SCENARIO, ""),
}
# 示范文本 10 项评审内容 → 标题关键词。真实招标文件的标题可能换说法（"施工进度计划及保证措施"），按关键词认；
# 一个标题可以对上几个方面（"安全文明施工措施"）
ASPECTS = (
    ("工程概况", ("概况",)), ("施工方法", ("施工方法", "施工方案", "技术方案")), ("物资", ("物资", "材料")),
    ("机械", ("机械", "设备")), ("劳动力", ("劳动力",)), ("质量", ("质量",)), ("安全", ("安全",)),
    ("工期", ("工期", "进度")), ("文明施工", ("文明", "环境保护", "环保")), ("总平面", ("平面布置", "总平面")),
)
ASPECT_NAMES = tuple(name for name, _ in ASPECTS)
# 招标文件点名的重点难点优先：标题含这些字的一项不预填卡片要点、不查 W9，难点不替招标文件编（决策 5-4A）
FOCUS_WORDS = ("重点", "难点")
SIGNAL_KEYS = ("qualification", "scope", "bill")
CARD_KEYS = {"schema", "name", "kind", "code", "label", "applies_to", "signals", "boq", "aspects", "standards"}
VERIFIED_LABEL = re.compile(r"^二手·核于\d{4}-\d{2}-\d{2}$")
UNVERIFIED_LABEL = "待核验现行版本"
BOQ_PREFIX = re.compile(r"^\d{2,6}$")
# 清单编码：12 位数字；存成数字丢了前导零的 11 位；计价软件给补充项加的字母前缀（WB0402…、ZB04…）；
# 计量规范的补充项写法 01B001。比对前缀时只看数字部分
BOQ_LETTERS = re.compile(r"^[A-Z]{1,3}(?=\d)")
NATIONAL_SUPPLEMENT = re.compile(r"^(\d{2})B\d{3}$")
# 一个单元格是不是清单编码：上面三种写法都认（阶段 2 数清单行、阶段 3 取主要分项共用）
BOQ_CODE = re.compile(r"^(?:[A-Z]{1,3})?\d{9,12}$|^\d{2}B\d{3}$")


def is_text_list(value: object, allow_empty: bool = True) -> bool:
    return isinstance(value, list) and (allow_empty or bool(value)) and \
        all(isinstance(item, str) and item.strip() for item in value)


# ---------- 卡片校验 ----------

def check_identity(card: dict, stem: str) -> list[str]:
    issues = [f"未定义的键 {key}" for key in sorted(set(card) - CARD_KEYS)]
    if card.get("schema") != CARD_SCHEMA:
        issues.append(f"schema 应为 {CARD_SCHEMA}")
    name = card.get("name")
    if name not in CATALOG or name != stem:
        issues.append(f"name 须是名录里的名称且与文件名一致（当前: {name}）")
    elif (card.get("kind"), card.get("code") or "") != CATALOG[name]:
        issues.append(f"kind、code 应为 {CATALOG[name][0]}、{CATALOG[name][1] or '空'}")
    if card.get("label") != "推断":
        issues.append("label 只能是“推断”：卡片是通用施工知识，不是招标文件的规则")
    if not str(card.get("applies_to") or "").strip():
        issues.append("applies_to 写这张卡适用的工程范围")
    signals = card.get("signals")
    if not isinstance(signals, dict) or set(signals) != set(SIGNAL_KEYS) or \
            not all(is_text_list(signals[key]) for key in SIGNAL_KEYS):
        issues.append(f"signals 须含 {'、'.join(SIGNAL_KEYS)} 三个文字列表（资质、招标范围、清单单位工程名的关键词）")
    return issues


def check_boq(boq: object) -> list[str]:
    if not isinstance(boq, dict) or set(boq) - {"prefixes", "keywords", "note"}:
        return ["boq 只收 prefixes、keywords、note"]
    prefixes = boq.get("prefixes")
    if not isinstance(prefixes, list) or not prefixes or not all(isinstance(item, str) and BOQ_PREFIX.match(item)
                                                                 for item in prefixes):
        return ["boq.prefixes 写清单编码前缀（2～6 位数字），至少一个"]
    return [] if is_text_list(boq.get("keywords", [])) else ["boq.keywords 应为文字列表（空即该前缀下全收）"]


def check_point(point: object, where: str) -> list[str]:
    if not isinstance(point, dict) or set(point) != {"text", "keywords"}:
        return [f"{where}：必备要点须且只须含 text、keywords"]
    issues = [] if str(point["text"]).strip() else [f"{where}：text 不能为空"]
    if not is_text_list(point["keywords"], allow_empty=False):
        issues.append(f"{where}：keywords 列出正文写到这一点时会出现的叫法，至少一个（W9 按它比对）")
    return issues


def check_aspects(aspects: object) -> list[str]:
    if not isinstance(aspects, dict) or not aspects or set(aspects) - set(ASPECT_NAMES):
        return [f"aspects 的键只能是 {'、'.join(ASPECT_NAMES)}"]
    issues = []
    for aspect, entry in aspects.items():
        if not isinstance(entry, dict) or set(entry) != {"must", "hints"}:
            issues.append(f"aspects.{aspect} 须且只须含 must、hints")
            continue
        if not isinstance(entry["must"], list) or not is_text_list(entry["hints"]):
            issues.append(f"aspects.{aspect}：must 是要点列表，hints 是文字列表")
            continue
        for index, point in enumerate(entry["must"], 1):
            issues += check_point(point, f"aspects.{aspect}.must 第 {index} 条")
    return issues


def check_standards(standards: object) -> list[str]:
    """规范只列编号和名称；核到现行版本的标"二手·核于日期"并给来源，核不到的标"待核验现行版本"（决策 5-6A）。"""
    if not isinstance(standards, list) or not standards:
        return ["standards 至少列一条相关规范"]
    issues = []
    for index, item in enumerate(standards, 1):
        if not isinstance(item, dict) or set(item) - {"no", "name", "label", "source", "note"}:
            issues.append(f"standards 第 {index} 条只收 no、name、label、source、note")
            continue
        if not str(item.get("no") or "").strip() or not str(item.get("name") or "").strip():
            issues.append(f"standards 第 {index} 条须有编号 no 和名称 name")
        label = item.get("label")
        if label != UNVERIFIED_LABEL and not (isinstance(label, str) and VERIFIED_LABEL.match(label)):
            issues.append(f"standards 第 {index} 条 label 只能是“二手·核于YYYY-MM-DD”或“{UNVERIFIED_LABEL}”")
        elif label != UNVERIFIED_LABEL and not str(item.get("source") or "").startswith("http"):
            issues.append(f"standards 第 {index} 条核过版本，source 写核对时看的网址")
    return issues


def validate_card(card: dict, stem: str) -> list[str]:
    return check_identity(card, stem) + check_boq(card.get("boq")) + check_aspects(card.get("aspects")) + \
        check_standards(card.get("standards"))


def card_path(name: str, directory: Path = CARD_DIR) -> Path:
    return directory / f"{name}.json"


def load_card(name: str, directory: Path = CARD_DIR) -> dict | None:
    """名录里的卡；还没交付（文件不存在）返回 None。仓库里的卡写坏了是 Skill 的错，直接报错。"""
    path = card_path(name, directory)
    if not path.is_file():
        return None
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"类别知识卡读不出来: {path} ({exc})") from exc
    issues = validate_card(card, name) if isinstance(card, dict) else ["应为 JSON 对象"]
    if issues:
        raise ValueError(f"类别知识卡 {path.name} 有 {len(issues)} 个问题：{issues[0]}")
    return card


# ---------- 规则卡的工程类别 ----------

def category_value(rule_card: dict) -> dict:
    entry = rule_card.get(CATEGORY_FIELD)
    value = entry.get("value") if isinstance(entry, dict) else None
    return value if isinstance(value, dict) else {}


def check_category(value: object) -> list[str]:
    """规则卡 project_category 的取值。主类别是占比最大的工程类型（导则 1.3.3（1）），涉及专业是招标范围里的其他专业：
    招标文件启用青天就适用、不看行业（决策 D11），这两项不限名录，名录外的没有知识卡，只按招标文件和红线写。
    场景只有名录里的判断（在既有设施上施工），只能从名录选。占比由人按清单和招标范围判断，脚本不算。"""
    label = "工程类别"
    if not isinstance(value, dict) or set(value) != {"main", "modules", "scenarios"}:
        return [f"{label}：value 须且只须含 main、modules、scenarios"]
    scenes = [name for name, (kind, _) in CATALOG.items() if kind == SCENARIO]
    main, modules, scenarios = value["main"], value["modules"], value["scenarios"]
    issues = []
    if not (isinstance(main, str) and main.strip()) or main in scenes:
        issues.append(f"{label}：主类别 main 写占比最大的工程类型（导则 1.3.3（1）），不能空着，也不能写场景")
    checks = ((("modules", modules), is_text_list(modules) and not set(modules) & set(scenes),
               "只能从名录或招标范围写专业名称（文字列表），场景放 scenarios"),
              (("scenarios", scenarios), isinstance(scenarios, list) and all(name in scenes for name in scenarios),
               f"只能从 {'、'.join(scenes)} 里选"))
    for (key, names), valid, rule in checks:
        if not valid:
            issues.append(f"{label}：{key} {rule}")
        elif len(set(names)) != len(names) or main in names:
            issues.append(f"{label}：{key} 不能重复，也不能再写主类别")
    return issues


def picked_names(rule_card: dict) -> list[str]:
    """规则卡选的全部类别名：主类别、专业、场景的顺序，去重。"""
    value = category_value(rule_card)
    names = [value.get("main"), *(value.get("modules") or []), *(value.get("scenarios") or [])]
    return list(dict.fromkeys(name for name in names if isinstance(name, str) and name.strip()))


def selected_names(rule_card: dict) -> list[str]:
    return [name for name in picked_names(rule_card) if name in CATALOG]


def no_card_names(rule_card: dict) -> list[str]:
    """规则卡选了、名录里没有的类别：没有知识卡，不预填、不查 W9，只按招标文件和红线写，不编规则（决策 D11）。"""
    return [name for name in picked_names(rule_card) if name not in CATALOG]


def project_cards(rule_card: dict, directory: Path = CARD_DIR) -> tuple[list[dict], list[str]]:
    """规则卡判定的类别对应的卡（主类别、专业、场景的顺序），以及还没交付卡片的类别名。"""
    cards, missing = [], []
    for name in selected_names(rule_card):
        card = load_card(name, directory)
        if card is None:
            missing.append(name)
        else:
            cards.append(card)
    return cards, missing


# ---------- 大纲预填与 W9 ----------

def aspects_of(title: str) -> list[str]:
    if any(word in title for word in FOCUS_WORDS):
        return []
    return [aspect for aspect, words in ASPECTS if any(word in title for word in words)]


def card_points(cards: list[dict], title: str) -> list[tuple[str, dict]]:
    """这一项在各张卡上的必备要点：(卡名, 要点)，按卡、按方面的顺序。"""
    return [(card["name"], point) for card in cards for aspect in aspects_of(title)
            for point in (card["aspects"].get(aspect) or {}).get("must") or []]


def card_hints(cards: list[dict], title: str) -> list[tuple[str, str]]:
    return [(card["name"], hint) for card in cards for aspect in aspects_of(title)
            for hint in (card["aspects"].get(aspect) or {}).get("hints") or []]


def control_point_prefill(cards: list[dict], title: str) -> list[str]:
    """矩阵骨架的 control_points：卡上的必备要点原文，人按本项目删改；不适用的删掉，W9 写作时就不再提示它。"""
    return list(dict.fromkeys(point["text"] for _, point in card_points(cards, title)))


def kept_points(cards: list[dict], title: str, control_points: list[str]) -> list[tuple[str, dict]]:
    """确认过的矩阵这一项还留着的卡片要点：原文还在，或改写后还带它的某个叫法。阶段 4 按本项目删掉的要点用户已经
    确认过，写作时不再提示（第 6b 步真实项目：删掉的点每项都要再解释一遍，用户选 A，改决策 5-4A）。"""
    joined = "；".join(control_points)
    return [(name, point) for name, point in card_points(cards, title)
            if point["text"] in control_points or any(word in joined for word in point["keywords"])]


def w9_hits(text: str, title: str, cards: list[dict], control_points: list[str]) -> list[dict]:
    """W9：矩阵这一项还留着的必备要点，正文一个叫法都没出现的合成一条提示（每项最多一条）。只是关键词比对，
    可以说明理由不改。"""
    missing = [(name, point) for name, point in kept_points(cards, title, control_points)
               if not any(word in text for word in point["keywords"])]
    if not missing:
        return []
    listed = "；".join(f"{point['text']}（{name}）" for name, point in missing)
    return [{"gate": "W9", "match": "|".join(f"{name}:{point['text']}" for name, point in missing),
             "message": f"没写到类别知识卡的必备要点 {len(missing)} 条：{listed}。写进正文，或说明本项目为何不涉及（Q4 完整性）"}]


# ---------- 清单主要分项 ----------

def boq_digits(code: str) -> str:
    supplement = NATIONAL_SUPPLEMENT.match(code)
    if supplement:
        return supplement.group(1)
    digits = BOQ_LETTERS.sub("", code)
    return digits.zfill(12) if len(digits) == 11 and digits.isdigit() else digits


def boq_card(code: str, name: str, cards: list[dict]) -> str | None:
    """清单行归哪张卡：按传入顺序取第一张编码前缀对上、名称也含关键词（没写关键词即全收）的卡。"""
    digits = boq_digits(code)
    for card in cards:
        boq = card["boq"]
        if digits.startswith(tuple(boq["prefixes"])) and \
                (not boq.get("keywords") or any(word in name for word in boq["keywords"])):
            return card["name"]
    return None


# ---------- Markdown 视图 ----------

def aspect_lines(card: dict) -> list[str]:
    lines = []
    for aspect in ASPECT_NAMES:
        entry = card["aspects"].get(aspect)
        if not entry:
            continue
        lines += [f"### {aspect}", ""]
        lines += [f"- 必备：{point['text']}（正文叫法：{'、'.join(point['keywords'])}）" for point in entry["must"]]
        lines += [f"- 参考：{hint}" for hint in entry["hints"]]
        lines.append("")
    return lines


def standard_rows(card: dict) -> list[str]:
    rows = ["| 编号 | 名称 | 版本核验 | 说明 |", "|---|---|---|---|"]
    for item in card["standards"]:
        label = item["label"] if item["label"] == UNVERIFIED_LABEL else f"【{item['label']}】[来源]({item['source']})"
        rows.append(f"| {item['no']} | {item['name']} | {label} | {item.get('note') or '—'} |")
    return rows


def render_card(card: dict) -> str:
    kind = card["kind"] + (f"（导则 1.3.2 {card['code']}）" if card.get("code") else "")
    boq = card["boq"]
    lines = [f"# 类别知识卡：{card['name']}", "",
             f"> 由 `{card['name']}.json` 生成，改卡请改 JSON 后运行 `python scripts/category_cards.py --write`。"
             "全卡【推断】：通用施工知识，不是招标文件的规则；招标文件写了的以招标文件为准。只给要点、不给范文，"
             "要点要结合本项目事实写成自己的话（Q10、W4）；机械、劳动力、物资的参考只用来查资源卡缺什么，"
             "施组里写的资源只来自确认过的资源卡（R7）。", "",
             f"- 种类：{kind}", f"- 适用：{card['applies_to']}",
             f"- 判类别的线索：资质 {'、'.join(card['signals']['qualification']) or '—'}；招标范围 "
             f"{'、'.join(card['signals']['scope']) or '—'}；清单单位工程名 {'、'.join(card['signals']['bill']) or '—'}",
             f"- 清单主要分项：编码前缀 {'、'.join(boq['prefixes'])}；名称关键词 {'、'.join(boq.get('keywords') or []) or '不限'}"
             + (f"；{boq['note']}" if boq.get("note") else ""), "",
             "## 各项评审内容的要点", "",
             "必备要点进响应矩阵的控制点，写稿后按“正文叫法”比对（W9，只提示，可以说明理由不改）。", "",
             *aspect_lines(card), "## 相关规范（只引编号和名称，不抄条文，Q7）", "", *standard_rows(card), ""]
    return "\n".join(lines)


def card_files(directory: Path = CARD_DIR) -> list[Path]:
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def check_all(directory: Path = CARD_DIR, write: bool = False) -> list[str]:
    """逐张校验；write 时重出每张卡的 Markdown 视图。返回问题清单。"""
    issues = []
    for path in card_files(directory):
        if path.stem not in CATALOG:
            issues.append(f"{path.name}：文件名不在类别名录里（名录见 CATALOG，新增类别先改名录）")
            continue
        try:
            card = load_card(path.stem, directory)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        if write and card is not None:
            path.with_suffix(".md").write_text(render_card(card), encoding="utf-8")
    return issues


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验 qingtian-bid 的类别知识卡；--write 重出 Markdown 视图。")
    parser.add_argument("--write", action="store_true", help="校验通过的卡重出同名 .md 视图。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    issues = check_all(write=args.write)
    for issue in issues:
        print(f"- {issue}", file=sys.stderr)
    delivered = len(card_files())
    print(f"类别知识卡 {delivered}/{len(CATALOG)} 张已交付，{len(issues)} 个问题" + ("，视图已重出" if args.write else ""))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
