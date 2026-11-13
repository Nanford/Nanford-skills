"""Site limits of qingtian-bid: which site facilities the confirmed fact card forbids (no material yard, no
processing area, no office or living area, nothing stored outdoors), shared by the stage-4 control-point
prefill and the stage-5 W10 hint.

INPUT: fact-card facts [{id, text, ...}] confirmed in stage 3 (the candidates come from scaffold_facts'
       SITE_LIMIT sentences in 补遗、答疑). Standard library only, so scaffold_matrix and text_gates can both
       import it without pulling in each other.
OUTPUT: SITE_OBJECTS; forbidden_objects(facts) → {facility: [fact ids]}; unresolved(sentence, forbidden) →
        the forbidden facilities a sentence names without saying 不设 or how it is solved off site;
        rewrite_point(point, forbidden) for the matrix prefill (决策 6b-S6A).
POS: shared rule table of the 第 6b 步 fixes S5/S6. 2026-10-30、31 核对的两个真实合肥项目里，补疑、答疑禁止设
     材料堆场、加工区、办公区、生活区和室外堆放，而类别知识卡的总平面要点照常要求标注这些，草稿也照写。The
     facilities and their 叫法 are 【推断】 and only cover what those tenders forbade; when a new tender forbids
     something else, add a row. A fact counts only when a prohibition word comes before the facility in the
     same clause, so "办公区由发包人提供，严禁吸烟" forbids nothing. A sentence counts as solved when it
     carries any 不设/场外/租用 word; one sentence that both forbids one facility and plans another is missed,
     which is the price of a hint that stays quiet on normal wording.
"""

from __future__ import annotations

import re

# 现场限制禁止的设施：名称 → 叫法。名称用在改写后的控制点里（"现场不设……"），叫法用来认事实和正文。
# "加工厂"不算加工区：厂外加工正是场外解决方式；"办公室""宿舍"单说太宽（改造项目本身就有），只认施工临设的叫法
SITE_OBJECTS: dict[str, tuple[str, ...]] = {
    "材料堆场": ("材料堆场", "堆场", "堆料场", "堆放场", "堆放区"),
    "加工区": ("加工区", "加工场", "加工棚"),
    "办公区": ("办公区", "办公用房", "临时办公", "项目部办公"),
    "生活区": ("生活区", "生活用房", "工人宿舍", "职工宿舍", "临时宿舍"),
    "室外堆放点": ("室外堆放", "露天堆放", "室外存放", "露天存放"),
}
# 事实里的禁止词：同一分句里、设施叫法之前出现才算禁止（"现场不具备且不允许设置办公区、生活区"）
PROHIBIT = re.compile(r"严禁|禁止|不允许|不具备|不得|不准|不能|无法")
# 正文或控制点里说明了怎么处理的词：同一句里有这些词，提到设施也不算矛盾
RESOLVED = re.compile(r"不设|不另设|不搭设|不在|不堆放|不存放|严禁|禁止|不允许|不具备|不得|无法|场外|租用|租赁|外租")
CLAUSE_SPLIT = re.compile(r"[，,；;。！？!?\n]")


def facilities_in(text: str) -> list[str]:
    """一段文字提到了哪些设施（按 SITE_OBJECTS 的叫法认）。"""
    return [name for name, aliases in SITE_OBJECTS.items() if any(alias in text for alias in aliases)]


def forbidden_objects(facts: list[dict]) -> dict[str, list[str]]:
    """事实卡禁止的现场设施 → 出自哪几条事实。按 SITE_OBJECTS 的顺序排，同一条事实只记一次。"""
    found: dict[str, list[str]] = {}
    for fact in facts:
        identifier = str(fact.get("id") or "")
        for clause in CLAUSE_SPLIT.split(str(fact.get("text") or "")):
            prohibit = PROHIBIT.search(clause)
            if not prohibit:
                continue
            for name in facilities_in(clause[prohibit.start():]):
                ids = found.setdefault(name, [])
                if identifier not in ids:
                    ids.append(identifier)
    return {name: found[name] for name in SITE_OBJECTS if name in found}


def unresolved(sentence: str, forbidden: dict[str, list[str]]) -> list[str]:
    """这句提到了现场禁止的设施，却没写不设、场外、租用这类处理方式。"""
    if not forbidden or RESOLVED.search(sentence):
        return []
    return [name for name in facilities_in(sentence) if name in forbidden]


def fact_refs(names: list[str], forbidden: dict[str, list[str]]) -> str:
    return "、".join(dict.fromkeys(identifier for name in names for identifier in forbidden[name] if identifier))


def rewrite_point(point: str, forbidden: dict[str, list[str]]) -> str:
    """预填的控制点要求设现场禁止的设施时，改写成"现场不设……，写明场外解决方式"；卡片原文附在后面，
    其余要求（围挡、出入口、临时道路等）照样留着，W9 仍按原文的叫法比对。"""
    names = unresolved(point, forbidden)
    if not names:
        return point
    refs = fact_refs(names, forbidden)
    source = f"（现场限制 {refs}）" if refs else ""
    return f"现场不设{'、'.join(names)}{source}，写明场外解决方式；卡片原文：{point}"
