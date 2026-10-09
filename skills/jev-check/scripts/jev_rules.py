"""
INPUT: speech.json（语段）、brief.json（audience_segment）、claims.json（事实与状态）；Jev 返回的 answers
OUTPUT: CHECKS 四项判断的问题定义；build_probes() 把一版文稿拆成若干次请求；judge() 把回答换算为 passed / flagged / not_checked；
        Result 单条结果
POS: 语义检查的规则层，纯函数、不联网。问题措辞、语言与阈值都来自 2026-09-29 试点（jev-1.13.0，44 条中文样例），
     改措辞或阈值后须重跑 calibrate；问题措辞一变，旧缓存自动不再命中。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

QUESTION_SET = "2026-09-29"
# Noul 只返回「是」的概率、没有置信度：落在中间带的回答不下结论，交给人看
NOUL_LOW, NOUL_HIGH = 0.35, 0.65
# Choice 的置信度低于该值不下结论；与官方 citation_check 示例的自动放行线一致
CHOICE_MIN_CONFIDENCE = 0.8
VERIFIED_STATUSES = {"verified_source", "verified_test"}
AUDIENCE_OPENING_SEGMENTS = 3

# 试点里中文提问的区分度最好（16 条对 15 条），英文 0.39 误判了一条自我介绍
HOOK_CONCRETE = {
    "type": "noul",
    "instructions": "这是一条面向职场人的中文实操短视频的第一句话。它是否一开口就给出具体内容：具体的痛点、具体的好处、一个数字，或者一个做成的结果？",
    "criteria": {"true": "点出观众在意的具体任务、具体问题、数字或结果", "false": "打招呼、自我介绍、泛泛谈 AI 或趋势、故弄玄虚的预告，或者没有具体内容的提问"},
}
# 受众用英文描述：试点 8 条全对且最低置信度 0.88；中文描述有一条只有 0.43
AUDIENCE = {
    "type": "choice",
    "instructions": "Which single audience is this Chinese short-video script aimed at?",
    "criteria": {
        "ai_office": "Office workers using AI to finish concrete deliverables faster: bids, slides, reports, weekly reports, communication",
        "ai_learning": "Learners who want a shortcut method for learning AI that they can use right away",
        "ai_transformation": "Team leads trying to actually change team workflows with AI, not just install more tools",
        "fde": "Engineers interested in the Forward Deployed Engineer role: deploying AI into real client workflows on site",
        "beginner": "Complete beginners getting their first result running, stuck on installation and setup",
        "smb_owner": "Small business owners wanting AI efficiency without hiring, focused on cost and payback",
        "general": "No single audience: addresses everyone at once or no identifiable group",
    },
}
# 中文提问多抓到一条制造焦虑的说法（英文 0.25 漏判）
EXAGGERATION = {
    "type": "noul",
    "instructions": "这句话是否夸大或打包票承诺收益，比如保证收入、保证升职、百分之百搞定、从此再也不用，而且没有说明限制？",
}
# 结构参照官方 citation_check 示例：依据与说法三分类；中文提问在改错数字的样例上置信度更高（0.86 对 0.75）
SUPPORT = {
    "type": "choice",
    "instructions": "依据与这句口播是什么关系？",
    "criteria": {"supports": "依据写明了这句话的说法，或能直接推出", "contradicts": "依据写的是相反的说法，或不同的数字、事实",
                 "says_nothing": "依据没有涉及这句话说的内容"},
}
CHECKS: dict[str, dict[str, Any]] = {"hook_concrete": HOOK_CONCRETE, "audience": AUDIENCE, "exaggeration": EXAGGERATION, "support": SUPPORT}
# Noul 检查里「是」代表好还是坏
NOUL_TRUE_IS_GOOD = {"hook_concrete": True, "exaggeration": False}


@dataclass(frozen=True)
class Probe:
    """一次请求：一个 state + 一个问题。每项检查单独请求，保持与试点相同的输入形状。"""

    check: str
    where: str
    state: Any


@dataclass
class Result:
    check: str
    where: str
    verdict: str  # passed / flagged / not_checked / skipped
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def first_sentence(text: str) -> str:
    match = re.search(r"[。？！?!]", text)
    return text[: match.end()] if match else text


def build_probes(speech: dict[str, Any], claims: dict[str, dict[str, Any]]) -> tuple[list[Probe], list[Result]]:
    """返回要发出的请求，以及无需请求就能确定的 skipped 结果（没有已核实事实的语段不做依据检查）。"""
    segments = speech["segments"]
    opening = "".join(segment["display_text"] for segment in segments[:AUDIENCE_OPENING_SEGMENTS])
    probes = [Probe("hook_concrete", segments[0]["segment_id"], first_sentence(segments[0]["display_text"])),
              Probe("audience", f"{segments[0]['segment_id']}-{segments[:AUDIENCE_OPENING_SEGMENTS][-1]['segment_id']}", opening)]
    skipped: list[Result] = []
    for segment in segments:
        segment_id, text = segment["segment_id"], segment["display_text"]
        probes.append(Probe("exaggeration", segment_id, text))
        statements = [claims[cid]["statement"] for cid in segment.get("claim_ids", []) if claims.get(cid, {}).get("status") in VERIFIED_STATUSES]
        if statements:
            probes.append(Probe("support", segment_id, {"sentence": text, "evidence": "；".join(statements)}))
        else:
            skipped.append(Result("support", segment_id, "skipped", "没有关联已核实事实（观点或收尾句），不做依据检查"))
    return probes, skipped


def _judge_noul(check: str, answer: dict[str, Any]) -> tuple[str, str]:
    probability = float(answer["noul"])
    if NOUL_LOW < probability < NOUL_HIGH:
        return "not_checked", f"模型拿不准（概率 {probability:.2f}），请人工判断"
    good = (probability >= NOUL_HIGH) == NOUL_TRUE_IS_GOOD[check]
    if good:
        return "passed", ""
    messages = {"hook_concrete": "第一句没有给出具体痛点、好处、数字或结果", "exaggeration": "疑似夸大或打包票承诺收益，补上限制条件或改成实测数字"}
    return "flagged", messages[check]


def _judge_choice(check: str, answer: dict[str, Any], brief: dict[str, Any]) -> tuple[str, str]:
    choice, confidence = answer["choice"], float(answer.get("confidence") or 0.0)
    if confidence < CHOICE_MIN_CONFIDENCE:
        return "not_checked", f"模型拿不准（最可能是 {choice}，置信度 {confidence:.2f}），请人工判断"
    if check == "audience":
        expected = brief.get("audience_segment")
        if choice == "general":
            return "flagged", "开头没有对准单一人群；按 AUDIENCE.md 点名一类人的痛点或优势"
        if expected and choice != expected:
            return "flagged", f"开头读起来对准的是 {choice}，brief 写的是 {expected}"
        return "passed", ""
    if choice == "supports":
        return "passed", ""
    if choice == "contradicts":
        return "flagged", "口播与所引事实矛盾（常见于数字或范围写错），对照 claims.json 修改"
    return "flagged", "所引事实没有覆盖这段口播的说法，补充 claim 或改写"


def judge(probe: Probe, answer: dict[str, Any], brief: dict[str, Any]) -> Result:
    if CHECKS[probe.check]["type"] == "noul":
        verdict, message = _judge_noul(probe.check, answer)
        detail = {"noul": answer["noul"]}
    else:
        verdict, message = _judge_choice(probe.check, answer, brief)
        detail = {"choice": answer["choice"], "confidence": answer.get("confidence"), "probabilities": answer.get("probabilities")}
    return Result(probe.check, probe.where, verdict, message, detail)
