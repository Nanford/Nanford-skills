#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业补贴政策匹配引擎。

这个模块只做确定性的本地匹配，不负责发送消息。政策条件无法从现有
字段或企业档案确认时，会进入“信息不足/待人工”，不会被降级为“不匹配”。
"""
import argparse
import datetime
import os
import re
import sys

import openpyxl


# 资质关键词及其规范别名。匹配时按完整 token 判断，避免“高企”重复计算。
QUAL_MAP = {
    "高新技术企业": ["高新技术企业", "高企"],
    "专精特新": ["专精特新"],
    "单项冠军": ["单项冠军"],
    "瞪羚": ["瞪羚"],
    "科技型中小企业": ["科技型中小企业"],
    "创新型中小企业": ["创新型中小企业"],
    "规模以上": ["规模以上", "规上"],
}

DISTRICT_ALIASES = {
    "东湖高新": ["东湖高新", "东湖高新区", "东湖新技术开发区"],
    "江岸": ["江岸", "江岸区"],
    "洪山": ["洪山", "洪山区"],
    "武昌": ["武昌", "武昌区"],
    "青山": ["青山", "青山区"],
    "江汉": ["江汉", "江汉区"],
    "硚口": ["硚口", "硚口区"],
    "汉阳": ["汉阳", "汉阳区"],
    "东西湖": ["东西湖", "东西湖区"],
    "蔡甸": ["蔡甸", "蔡甸区"],
    "江夏": ["江夏", "江夏区"],
    "黄陂": ["黄陂", "黄陂区"],
    "新洲": ["新洲", "新洲区"],
    "汉南": ["汉南", "汉南区", "经开区", "武汉开发区", "武汉经济技术开发区"],
}
CITY_ALIASES = {
    "武汉": ["武汉", "武汉市"],
    "黄石": ["黄石", "黄石市"],
    "襄阳": ["襄阳", "襄阳市"],
    "宜昌": ["宜昌", "宜昌市"],
    "十堰": ["十堰", "十堰市"],
    "荆州": ["荆州", "荆州市"],
    "鄂州": ["鄂州", "鄂州市"],
    "孝感": ["孝感", "孝感市"],
    "黄冈": ["黄冈", "黄冈市"],
    "咸宁": ["咸宁", "咸宁市"],
    "随州": ["随州", "随州市"],
    "恩施": ["恩施", "恩施州", "恩施土家族苗族自治州"],
    "仙桃": ["仙桃", "仙桃市"],
    "潜江": ["潜江", "潜江市"],
    "天门": ["天门", "天门市"],
    "神农架": ["神农架", "神农架林区"],
}
OTHER_PROVINCES = ["北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
                   "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
                   "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州", "云南",
                   "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆", "香港", "澳门", "台湾"]
REGION_KW = ["湖北", *CITY_ALIASES.keys(), *DISTRICT_ALIASES.keys()]

INDUSTRY_ALIASES = {
    "智能制造": ["智能制造"],
    "软件": ["软件", "软件开发", "软件服务", "软件和信息技术服务业"],
    "电子信息": ["电子信息", "电子信息制造", "电子信息产业"],
    "新材料": ["新材料", "新材料产业"],
    "新能源": ["新能源", "新能源产业"],
    "生物医药": ["生物医药", "生物医药产业"],
    "装备制造": ["装备制造", "装备制造业"],
    "汽车": ["汽车", "汽车制造", "汽车产业"],
    "农业": ["农业", "农业产业"],
    "服务业": ["服务业"],
}

TALENT_ALIASES = {
    "博士": ["博士", "博士研究生"],
    "博士后": ["博士后"],
    "硕士": ["硕士", "硕士研究生"],
    "海归": ["海归", "留学归国", "留学人员"],
    "高工": ["高工", "高级工程师"],
    "技师": ["技师", "技能人才"],
    "研发人员": ["研发人员", "研发人才"],
}

UNKNOWN_MARKERS = ("未知", "不详", "不清楚", "待补", "待填", "未提供", "无数据")
HARD_FAIL = "不满足"
SATISFIED = "满足"
INFORMATION_MISSING = "信息不足"
MANUAL_REVIEW = "待人工"
NOT_APPLICABLE = "无需匹配"
# 企业负责人只接收已经满足当前自动规则的结果。部分匹配、信息不足和待人工
# 进入管理员复核队列，避免把尚未符合的政策包装成可申报机会。
NOTIFYABLE_CONCLUSIONS = {"匹配"}

MATCH_FIELDS = [
    "政策ID", "企业名称", "匹配结论", "命中条件", "缺口", "建议动作",
    "通知状态", "处理状态", "可通知",
]
KEY_RESULT_FIELDS = ("匹配结论", "命中条件", "缺口", "建议动作", "可通知")
SUCCESS_NOTIFICATION_STATES = {"已推送", "已发送"}
DEFAULT_LOOKBACK_DAYS = 370


def load_xlsx(path):
    """以字典行读取 xlsx；允许旧表缺少本轮新增列。"""
    if not os.path.exists(path):
        return [], []
    wb = openpyxl.load_workbook(path, data_only=False)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []
    hdr = ["" if h is None else str(h) for h in rows[0]]
    data = []
    for row in rows[1:]:
        data.append({hdr[i]: ("" if i >= len(row) or row[i] is None else row[i])
                     for i in range(len(hdr)) if hdr[i]})
    return hdr, data


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def _as_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    match = re.match(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})", _text(value))
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def policy_is_active(policy, today=None):
    """失效、已过截止日或过旧且无未来有效期证据的政策不进入匹配。"""
    today = today or datetime.date.today()
    state = _text(policy.get("政策状态", ""))
    if state in {"已过期", "已失效", "无效", "废止"}:
        return False
    deadline = _as_date(policy.get("申报截止", ""))
    if deadline:
        return deadline >= today
    published = _as_date(policy.get("发布日期", ""))
    if published and (today - published).days > DEFAULT_LOOKBACK_DAYS:
        return False
    return True


def _is_unknown(value):
    value = _text(value)
    return not value or any(marker in value for marker in UNKNOWN_MARKERS)


def _tokens(value):
    """将多选字段拆成 token，同时保留未拆分短语的精确匹配能力。"""
    value = _text(value)
    if _is_unknown(value):
        return set()
    return {x.strip() for x in re.split(r"[、，,;/；|\s]+", value) if x.strip()}


def extract_number(value):
    """抽取政策数值门槛，统一为“万”。没有明确数字时返回 None。"""
    text = _text(value)
    if not text:
        return None
    # 先抓带比较语义的数字，避免把年份或条款编号误当门槛。
    patterns = (
        r"(?:不少于|不低于|至少|大于等于|达到|超过|以上|≥|>=|大于)\s*"
        r"(\d+(?:\.\d+)?)\s*(亿|万|万元|亿元)?",
        r"(\d+(?:\.\d+)?)\s*(亿|万|万元|亿元)\s*(?:以上|及以上|起)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        number = float(match.group(1))
        unit = match.group(2) or ""
        if unit.startswith("亿"):
            number *= 10000
        return number
    return None


def _parse_enterprise_number(value):
    """解析企业数字，纯数字保持原单位（档案中的营收按万元约定）。"""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value)
    if _is_unknown(text):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    number = float(match.group(0))
    if "亿" in text:
        number *= 10000
    return number


def _required_qualifications(value):
    text = _text(value)
    if not text or _is_unknown(text):
        return []
    required = []
    for canonical, aliases in QUAL_MAP.items():
        for alias in aliases:
            start = text.find(alias)
            while start >= 0:
                prefix = text[max(0, start - 8):start]
                if not re.search(r"(?:无需|无须|不要求|不限|不作要求)$", prefix):
                    required.append(canonical)
                    break
                start = text.find(alias, start + len(alias))
            if canonical in required:
                break
    return list(dict.fromkeys(required))


def qualification_status(policy_qual, ent_qual):
    if not _text(policy_qual):
        return SATISFIED, ""
    required = _required_qualifications(policy_qual)
    if not required:
        return MANUAL_REVIEW, f"无法识别资质要求:{_text(policy_qual)[:40]}"
    if _is_unknown(ent_qual):
        return INFORMATION_MISSING, "企业未填写资质"
    ent_text = _text(ent_qual)
    # 对企业档案也使用规范别名，不把任意包含关系当作资格证据。
    ent_tokens = _tokens(ent_text)
    ent_canon = set()
    for canonical, aliases in QUAL_MAP.items():
        if any(alias in ent_tokens or alias == ent_text for alias in aliases):
            ent_canon.add(canonical)
    missing = [name for name in required if name not in ent_canon]
    if missing:
        return HARD_FAIL, "缺资质:" + "、".join(missing)
    return SATISFIED, ""


def check_qual(policy_qual, ent_qual):
    """兼容旧调用方的 (ok, missing) 接口；未知不会被报告为硬失败。"""
    status, note = qualification_status(policy_qual, ent_qual)
    if status == HARD_FAIL:
        return False, [note]
    return True, ([note] if note else [])


def _region_profile(value):
    text = _text(value)
    profile = {"province": "湖北" if "湖北" in text else "",
               "cities": set(), "districts": set(),
               "non_wuhan": bool("湖北" in text and "其他市" in text),
               "outside_hubei": bool(not "湖北" in text and any(p in text for p in OTHER_PROVINCES))}
    for city, aliases in CITY_ALIASES.items():
        if any(alias in text for alias in aliases):
            profile["cities"].add(city)
    for district, aliases in DISTRICT_ALIASES.items():
        if any(alias in text for alias in aliases):
            profile["districts"].add(district)
    # 区级地址天然属于武汉市，除非文本明确写的是湖北其他市。
    if profile["districts"] and not profile["non_wuhan"]:
        profile["cities"].add("武汉")
    return profile


def region_status(policy_region, ent_region):
    """按省→市→区的最具体层级判定地域。"""
    policy_text = _text(policy_region)
    if not policy_text:
        return SATISFIED, ""
    p = _region_profile(policy_text)
    if not (p["province"] or p["cities"] or p["districts"] or p["non_wuhan"]):
        return MANUAL_REVIEW, f"无法识别地域要求:{policy_text[:50]}"
    # 一个自动抽取字段同时出现多个城市/区县，通常混入了机构地址、引用法规或
    # 多个适用范围。此时禁止选取其中任意一个做硬性淘汰。
    if len(p["cities"]) > 1 or len(p["districts"]) > 1:
        return MANUAL_REVIEW, f"地域要求包含多个候选范围:{policy_text[:60]}"
    if p["districts"] and p["cities"] and p["cities"] != {"武汉"}:
        return MANUAL_REVIEW, f"地域层级存在冲突:{policy_text[:60]}"
    if _is_unknown(ent_region):
        return INFORMATION_MISSING, "企业未填写注册地区"
    e = _region_profile(ent_region)

    # 区级要求最具体：仅有武汉市而没有区，属于信息不足；其他区是明确不满足。
    if p["districts"]:
        if p["districts"] & e["districts"]:
            return SATISFIED, ""
        if e["outside_hubei"] or e["non_wuhan"] or (e["districts"] and not p["districts"] & e["districts"]):
            return HARD_FAIL, f"地域要求:{policy_text}"
        return INFORMATION_MISSING, f"缺少区县注册地证据（要求:{policy_text}）"

    # 武汉市要求不能由“湖北省其他市”满足；武汉各区则视为武汉。
    if "武汉" in p["cities"]:
        if "武汉" in e["cities"] and not e["non_wuhan"]:
            return SATISFIED, ""
        if e["outside_hubei"] or e["non_wuhan"] or (e["cities"] and "武汉" not in e["cities"]):
            return HARD_FAIL, f"地域要求:{policy_text}"
        return INFORMATION_MISSING, f"无法确认企业是否在武汉（要求:{policy_text}）"

    # 其他湖北城市的政策只接受同一城市；省级政策不走此分支。
    if p["cities"]:
        if p["cities"] & e["cities"]:
            return SATISFIED, ""
        if e["outside_hubei"] or e["cities"] or e["non_wuhan"]:
            return HARD_FAIL, f"地域要求:{policy_text}"
        return INFORMATION_MISSING, f"无法确认企业所在城市（要求:{policy_text}）"

    # “湖北省”只要求省域，湖北省内所有城市和区县都满足。
    if p["province"]:
        if e["outside_hubei"]:
            return HARD_FAIL, f"地域要求:{policy_text}"
        if e["province"] or e["cities"] or e["districts"] or e["non_wuhan"]:
            return SATISFIED, ""
        return INFORMATION_MISSING, "无法确认企业是否在湖北省"

    if p["non_wuhan"]:
        if e["outside_hubei"]:
            return HARD_FAIL, f"地域要求:{policy_text}"
        if e["non_wuhan"] or (e["cities"] and "武汉" not in e["cities"]):
            return SATISFIED, ""
        if "武汉" in e["cities"] or e["districts"]:
            return HARD_FAIL, f"地域要求:{policy_text}"
        return INFORMATION_MISSING, "无法确认企业是否位于湖北省其他市"
    return MANUAL_REVIEW, f"地域要求需人工确认:{policy_text[:50]}"


def check_region(policy_region, ent_region):
    """兼容旧调用方的 (ok, missing) 接口；未知状态按 ok 返回。"""
    status, note = region_status(policy_region, ent_region)
    if status == HARD_FAIL:
        return False, [note]
    return True, ([note] if note else [])


def numeric_status(policy_field, ent_value):
    if not _text(policy_field):
        return SATISFIED, ""
    need = extract_number(policy_field)
    if need is None:
        return MANUAL_REVIEW, f"无法解析数值:{_text(policy_field)[:40]}"
    if _is_unknown(ent_value):
        return INFORMATION_MISSING, "企业未填写数值"
    actual = _parse_enterprise_number(ent_value)
    if actual is None:
        return INFORMATION_MISSING, f"企业数值无法解析:{_text(ent_value)[:30]}"
    if actual >= need:
        return SATISFIED, ""
    return "缺口", f"企业{actual:g} < 要求{need:g}"


def _numeric_enterprise_value(policy_field, ent, default_field):
    """根据政策量纲选择企业字段，避免把人数与营收、研发与纳税交叉比较。"""
    text = _text(policy_field)
    if re.search(r"从业人员|职工人数|员工人数|人员数量|人数", text):
        return ent.get("规模-人数", "")
    if re.search(r"研发费用|研发投入|研究开发费用", text):
        return ent.get("研发费用", "")
    if re.search(r"营业收入|营收|销售额|产值|营业额", text):
        value = ent.get("近一年营收", "")
        return ent.get("规模-营收", "") if _is_unknown(value) else value
    return ent.get(default_field, "")


def _effective_region_requirement(policy):
    """优先使用地域要求；仅从明确地域化的申报对象中做保守回退。"""
    explicit = _text(policy.get("地域要求", ""))
    if explicit:
        return explicit
    target = _text(policy.get("申报对象", ""))
    if (re.search(r"(?:湖北省|武汉市|东湖高新)(?:内|辖区内|行政区域内)", target)
            or re.search(r"(?:在|注册地|登记地).{0,12}(?:湖北省|武汉市|东湖高新).{0,12}(?:注册|登记|经营)", target)):
        return target
    return ""


def check_numeric(policy_field, ent_value):
    """兼容旧名称；数值不足是软门槛缺口，不直接判不匹配。"""
    return numeric_status(policy_field, ent_value)


def _industry_tokens(value):
    text = _text(value)
    if _is_unknown(text):
        return set()
    result = set()
    chunks = [x.strip() for x in re.split(r"[、，,;/；|\s]+", text) if x.strip()]
    generic = re.compile(r"^(重点支持|支持|适用于|属于|行业|产业|领域|企业|等)+")
    for chunk in chunks:
        chunk = generic.sub("", chunk)
        chunk = re.sub(r"(行业|领域|产业)$", "", chunk)
        for canonical, aliases in INDUSTRY_ALIASES.items():
            if chunk in aliases or chunk == canonical:
                result.add(canonical)
                break
    return result


def industry_status(policy_industry, ent_industry):
    policy_text = _text(policy_industry)
    if not policy_text:
        return SATISFIED, ""
    required = _industry_tokens(policy_text)
    if not required:
        return MANUAL_REVIEW, f"无法识别行业要求:{policy_text[:50]}"
    if _is_unknown(ent_industry):
        return INFORMATION_MISSING, "企业未填写行业"
    actual = _industry_tokens(ent_industry)
    if not actual:
        return MANUAL_REVIEW, f"企业行业需人工核对:{_text(ent_industry)[:40]}"
    if required & actual:
        return SATISFIED, ""
    return HARD_FAIL, f"行业要求:{policy_text}"


def _talent_profile(value):
    text = _text(value)
    types = set()
    counts = {}
    for canonical, aliases in TALENT_ALIASES.items():
        if any(alias in text for alias in aliases):
            types.add(canonical)
            # 只从“类型附近”的显式人数字段取数量，不把人才类型字符串整体 float 化。
            for alias in aliases:
                for pattern in (
                    rf"{re.escape(alias)}\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:人|名)?",
                    rf"(\d+(?:\.\d+)?)\s*(?:人|名)?\s*{re.escape(alias)}",
                ):
                    match = re.search(pattern, text)
                    if match:
                        counts[canonical] = float(match.group(1))
                        break
                if canonical in counts:
                    break
    return types, counts


def talent_status(policy_talent, ent_talent):
    policy_text = _text(policy_talent)
    if not policy_text:
        return SATISFIED, ""
    required = set()
    for canonical, aliases in TALENT_ALIASES.items():
        if any(alias in policy_text for alias in aliases):
            required.add(canonical)
    # 比例、研发人员数量等需要企业档案新增字段，不能把人才类型当数字比较。
    ratio_or_count = bool(re.search(r"(?:占比|比例|人数|人次|名额|≥|>=|不少于|不低于|至少|超过)", policy_text))
    requirements = {}
    for canonical in required:
        aliases = TALENT_ALIASES[canonical]
        for alias in aliases:
            patterns = (
                rf"{re.escape(alias)}\s*(?:不少于|不低于|至少|≥|>=|大于等于|超过)?\s*(\d+(?:\.\d+)?)\s*(?:人|名)?",
                rf"(?:不少于|不低于|至少|≥|>=|大于等于|超过)\s*(\d+(?:\.\d+)?)\s*(?:人|名)?\s*{re.escape(alias)}",
            )
            for pattern in patterns:
                match = re.search(pattern, policy_text)
                if match:
                    requirements[canonical] = float(match.group(1))
                    break
            if canonical in requirements:
                break
    if not required:
        return INFORMATION_MISSING if ratio_or_count else MANUAL_REVIEW, \
            f"人才条件需人工确认:{policy_text[:50]}"
    if _is_unknown(ent_talent):
        return INFORMATION_MISSING, "企业未填写人才类型/人数"
    actual_types, actual_counts = _talent_profile(ent_talent)
    missing_types = required - actual_types
    if missing_types:
        return "缺口", "缺人才类型:" + "、".join(sorted(missing_types))
    for canonical, needed in requirements.items():
        actual_count = actual_counts.get(canonical)
        if actual_count is None:
            return INFORMATION_MISSING, f"缺少{canonical}人数证据"
        if actual_count < needed:
            return "缺口", f"{canonical}{actual_count:g}人 < 要求{needed:g}人"
    if ratio_or_count and not requirements:
        return INFORMATION_MISSING, "人才比例/人数需补充可核验字段"
    return SATISFIED, ""


def _policy_parse_state(policy):
    state = _text(policy.get("解析状态", ""))
    if state in ("已解析", "成功") and _text(policy.get("要素已解析", "是")) != "否":
        return "已解析"
    if state in (INFORMATION_MISSING, MANUAL_REVIEW):
        return state
    if _text(policy.get("要素已解析", "")) == "是":
        return "已解析"
    return MANUAL_REVIEW


def _has_policy_conditions(policy):
    return any(_text(policy.get(field, "")) for field in (
        "资质要求", "规模要求", "财务要求", "社保要求", "人才要求",
        "行业要求", "地域要求", "申报对象"))


def _policy_is_matchable(policy):
    """排除结果公示、兑付名单和普通新闻；这些记录留档但不做准入匹配。"""
    title = _text(policy.get("标题", ""))
    category = _text(policy.get("政策类别", ""))
    apply_words = ("申报", "征集", "报名", "指南", "预申报")
    result_words = ("公示", "公布", "名单", "通报", "结果", "验收", "入选", "兑付", "拨付")
    if category == "结果公示" or (any(word in title for word in result_words)
                                 and not any(word in title for word in apply_words)):
        return False, "结果公示/兑付类记录不进入企业申报匹配"
    high_signal = ("补贴", "补助", "奖励", "奖补", "申报", "征集", "专项", "资金",
                   "券", "扶持", "政策", "办法", "措施", "细则", "认定", "资助",
                   "贴息", "减税", "减免", "返还", "稳岗", "高企", "高新技术",
                   "专精特新", "单项冠军", "瞪羚", "研发", "项目", "惠企")
    if title and not any(word in title for word in high_signal):
        return False, "标题缺少申报或惠企政策高信号词，按普通资讯留档"
    return True, ""


def _evaluate_match(policy, ent):
    hits, hard_gaps, soft_gaps, needs = [], [], [], []
    matchable, reason = _policy_is_matchable(policy)
    if not matchable:
        return {"匹配结论": NOT_APPLICABLE, "命中条件": "", "缺口": reason,
                "建议动作": "仅保留政策记录，不向企业发送申报通知", "可通知": "否"}
    parse_state = _policy_parse_state(policy)
    if parse_state != "已解析":
        note = "政策解析状态为" + parse_state + "，需补充正文/附件或人工核验"
        return {"匹配结论": parse_state, "命中条件": "", "缺口": note,
                "建议动作": "先补充政策解析证据并人工复核", "可通知": "是"}
    if not _has_policy_conditions(policy):
        return {"匹配结论": MANUAL_REVIEW, "命中条件": "",
                "缺口": "未抽取到可核验申报门槛", "建议动作": "人工查看政策正文及附件",
                "可通知": "是"}

    status, note = qualification_status(policy.get("资质要求", ""), ent.get("资质", ""))
    if status == HARD_FAIL:
        hard_gaps.append(note)
    elif status == SATISFIED and _text(policy.get("资质要求", "")):
        hits.append("资质符合")
    elif note:
        needs.append(note)

    region_requirement = _effective_region_requirement(policy)
    status, note = region_status(region_requirement, ent.get("注册地区", ""))
    if status == HARD_FAIL:
        hard_gaps.append(note)
    elif status == SATISFIED and region_requirement:
        hits.append("地域符合")
    elif note:
        needs.append(note)

    status, note = industry_status(policy.get("行业要求", ""), ent.get("行业", ""))
    if status == HARD_FAIL:
        hard_gaps.append(note)
    elif status == SATISFIED and _text(policy.get("行业要求", "")):
        hits.append("行业符合")
    elif note:
        needs.append(note)

    for pfield, default_field, label in (
        ("规模要求", "近一年营收", "规模/营收"),
        ("财务要求", "纳税/利润", "财务"),
        ("社保要求", "社保人数", "社保"),
    ):
        evalue = _numeric_enterprise_value(policy.get(pfield, ""), ent, default_field)
        status, note = numeric_status(policy.get(pfield, ""), evalue)
        if status == SATISFIED and _text(policy.get(pfield, "")):
            hits.append(label + "满足")
        elif status == "缺口":
            soft_gaps.append(label + "不达标(" + note + ")")
        elif note:
            needs.append(label + ":" + note)

    status, note = talent_status(policy.get("人才要求", ""), ent.get("人才类型", ""))
    if status == SATISFIED and _text(policy.get("人才要求", "")):
        hits.append("人才满足")
    elif status == "缺口":
        soft_gaps.append("人才不达标(" + note + ")")
    elif note:
        needs.append("人才:" + note)

    if hard_gaps:
        conclusion = "不匹配"
        advice = "存在明确不满足的资质、地域或行业门槛，记录原因并结束本轮申报"
    elif soft_gaps:
        conclusion = "部分匹配"
        advice = "补充或改善软门槛证据后再申报"
    elif needs:
        has_info = any("未填写" in x or "信息" in x or "缺少" in x or "无法" in x for x in needs)
        conclusion = INFORMATION_MISSING if has_info else MANUAL_REVIEW
        advice = "补充企业字段、政策正文或附件证据后人工复核"
    elif hits:
        conclusion = "匹配"
        advice = "条件满足，建议核对截止日期并准备申报材料"
    else:
        conclusion = MANUAL_REVIEW
        advice = "没有形成可核验的命中证据，需人工查看政策原文"
    return {"匹配结论": conclusion, "命中条件": "；".join(hits),
            "缺口": "；".join(hard_gaps + soft_gaps + needs), "建议动作": advice,
            "可通知": "是" if conclusion in NOTIFYABLE_CONCLUSIONS else "否"}


def match_one(policy, ent):
    """保留旧接口，返回 (结论, 命中条件, 缺口, 建议动作)。"""
    result = _evaluate_match(policy, ent)
    return (result["匹配结论"], result["命中条件"], result["缺口"], result["建议动作"])


def _result_key(row):
    return f"{_text(row.get('政策ID', ''))}||{_text(row.get('企业名称', ''))}"


def _preserve_status(new_row, old_row):
    """已成功推送的复合键永久保留状态，避免内容刷新触发二次推送。"""
    if not old_row:
        new_row["通知状态"] = "未推送"
        new_row["处理状态"] = "待申报"
        return new_row
    changed = any(_text(new_row.get(field, "")) != _text(old_row.get(field, ""))
                  for field in KEY_RESULT_FIELDS)
    old_notify = _text(old_row.get("通知状态", "")) or "未推送"
    new_row["通知状态"] = (old_notify if old_notify in SUCCESS_NOTIFICATION_STATES
                            else ("未推送" if changed else old_notify))
    new_row["处理状态"] = _text(old_row.get("处理状态", "")) or "待申报"
    return new_row


def update_digest_report(policies, results, out_path):
    """只将今日新增且可通知的结果写入日报，避免打扰不匹配企业。"""
    data_dir = os.path.dirname(os.path.abspath(out_path))
    digest_path = os.path.join(data_dir, "digest_latest.md")
    if not os.path.exists(digest_path):
        return
    today = datetime.date.today().strftime("%Y-%m-%d")
    title_of = {_text(p.get("序号", "")): _text(p.get("标题", "")) for p in policies}
    new_ids = {_text(p.get("序号", "")) for p in policies
               if _text(p.get("采集时间", "")).startswith(today)}
    start, end = "<!-- MATCH_SECTION_START -->", "<!-- MATCH_SECTION_END -->"
    section = [start, "", "## 今日新增政策 · 可通知企业", ""]
    candidates = [r for r in results if _text(r.get("政策ID", "")) in new_ids
                  and _text(r.get("匹配结论", "")) in NOTIFYABLE_CONCLUSIONS
                  and _text(r.get("可通知", "是")) != "否"]
    if not candidates:
        section.append("今日无可通知的新增匹配结果。")
    else:
        by_policy = {}
        for row in candidates:
            by_policy.setdefault(_text(row.get("政策ID", "")), []).append(row)
        for pid in sorted(by_policy, key=lambda x: int(x) if x.isdigit() else 0):
            section.append(f"### 政策#{pid} {title_of.get(pid, '')}")
            for row in by_policy[pid]:
                note = row.get("命中条件") if row.get("匹配结论") == "匹配" else row.get("缺口")
                note = _text(note)
                if len(note) > 80:
                    note = note[:80] + "…"
                line = f"- {row.get('企业名称', '')}：**{row.get('匹配结论', '')}**"
                section.append(line + (f"（{note}）" if note else ""))
            section.append("")
    section.extend(["", end])
    block = "\n".join(section)
    with open(digest_path, encoding="utf-8") as handle:
        text = handle.read()
    if start in text and end in text:
        text = text[:text.index(start)] + block + text[text.index(end) + len(end):]
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    with open(digest_path, "w", encoding="utf-8") as handle:
        handle.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", default="subsidy_records.xlsx")
    parser.add_argument("--enterprises", default="enterprises.xlsx")
    parser.add_argument("--out", default="match_results.xlsx")
    args = parser.parse_args(argv)
    data_dir = os.environ.get("SUBSIDY_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    policy_path = args.policy if os.path.isabs(args.policy) else os.path.join(data_dir, args.policy)
    enterprise_path = args.enterprises if os.path.isabs(args.enterprises) else os.path.join(data_dir, args.enterprises)
    out_path = args.out if os.path.isabs(args.out) else os.path.join(data_dir, args.out)
    if not os.path.exists(policy_path):
        print(f"[!] 政策表不存在: {policy_path}")
        return 2
    if not os.path.exists(enterprise_path):
        print(f"[!] 企业档案表不存在: {enterprise_path}")
        return 2
    _, policies = load_xlsx(policy_path)
    active_policies = [policy for policy in policies if policy_is_active(policy)]
    _, enterprises = load_xlsx(enterprise_path)
    _, old_results = load_xlsx(out_path)
    old_by_key = {_result_key(row): row for row in old_results if _result_key(row) != "||"}
    print(f"  政策 {len(policies)} 条（当前有效 {len(active_policies)} 条）, 企业 {len(enterprises)} 家")

    results = []
    counts = {"匹配": 0, "部分匹配": 0, "信息不足": 0, "待人工": 0,
              "不匹配": 0, NOT_APPLICABLE: 0}
    for policy in active_policies:
        policy_id = policy.get("序号", "")
        for enterprise in enterprises:
            evaluated = _evaluate_match(policy, enterprise)
            row = {"政策ID": policy_id, "企业名称": enterprise.get("企业名称", "")}
            row.update(evaluated)
            _preserve_status(row, old_by_key.get(_result_key(row)))
            results.append(row)
            counts[row["匹配结论"]] = counts.get(row["匹配结论"], 0) + 1

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(MATCH_FIELDS)
    for row in results:
        worksheet.append([row.get(field, "") for field in MATCH_FIELDS])
    workbook.save(out_path)
    notifyable = sum(1 for row in results if row["匹配结论"] in NOTIFYABLE_CONCLUSIONS)
    print(f"  匹配结果 {len(results)} 行，可通知 {notifyable} 行，统计: {counts}")
    print(f"  输出: {out_path}")
    update_digest_report(active_policies, results, out_path)
    for row in results:
        if row["匹配结论"] == "匹配":
            print(f"   [匹配] 政策#{row['政策ID']} × {row['企业名称']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
