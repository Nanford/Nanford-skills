"""Text-level gates of qingtian-bid on one item draft: B5 (text), B7, B8, B13, W2, W3, W4, W7, W10.

INPUT: one Markdown draft under output/实施方案/ and the other items' drafts (W4); the rule card and fact
       card (B7 compares names against them; W10 reads its site limits through site_limits);
       analysis/identity-terms.json, the identity list the user
       provides per project (B5, 决策 4a-3A); build_response_docx.detect_markdown_leaks (B8: the renderer
       decides what leaks; imported at module level, since python-docx is already needed from stage 0).
OUTPUT: hit lists [{gate, match, message, fixed?}] per gate; text helpers (visible_lines, body_lines,
        number_tokens, fact_used) shared with consistency_gates; load_identity_terms().
        Table-caption markers expose their visible caption to gates; width markers are layout only.
POS: pattern layer of the step-4 gates (design v1 §9 第 4a 步). Every pattern is a heuristic 【推断】: a hit
     points at text for the user to judge, nothing is scored. B8 cannot be dismissed, so it only matches
     what never belongs in a finished 施组 (tender chapter or clause numbers, writing-process words,
     Markdown the renderer doesn't digest); text that can be legitimate goes to a dismissable B (B5, B7)
     or a W (决策 4a-1A). B13 flags price words and money amounts, tables included; an amount unrelated to
     the bid price is dismissed with the user's reason. Personnel files are never read (决策 3b-1A): B5
     finds names only by the 岗位＋姓名 shape. W10 (第 6b 步) flags a sentence that plans a facility the
     confirmed site limits forbid (材料堆场、办公区……) without saying 不设 or how it is solved off site.
     Everything runs offline (R26), so W4 cannot see web text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from build_response_docx import detect_markdown_leaks
from site_limits import fact_refs, forbidden_objects, unresolved

IDENTITY_FILE = "analysis/identity-terms.json"
IDENTITY_SCHEMA = "qingtian-identity-terms/1"
IDENTITY_KINDS = ("公司全称", "简称", "商标", "网址")

# 与 build_response_docx 的 MARKER_PATTERN、HEADING_PATTERN、IMAGE_PATTERN 一致：渲染器怎么认，这里就怎么认
LAYOUT_MARKER = re.compile(r"^<!--\s*(?:[a-z-]+|table-widths:\s*[\d.,\s]+|table-caption:\s*.+?)\s*-->$")
TABLE_CAPTION = re.compile(r"^<!--\s*table-caption:\s*(.+?)\s*-->$")
HEADING = re.compile(r"^#{1,6}\s+")
IMAGE = re.compile(r"^!\[([^\]]*)\]\((.+)\)$")
BULLET = re.compile(r"^[-*+]\s+")
TABLE_RULE = re.compile(r"^[|:\-\s]+$")

# 数字＋单位。单位按长度排在前面，mm 不会被拆成 m；前面紧挨字母或数字的不算（QTZ80、C30、HRB400 是型号）
UNITS = ("日历天", "平方米", "立方米", "千米", "公里", "毫米", "厘米", "小时", "分钟", "千克", "公斤",
         "MPa", "kPa", "kN", "kg", "km", "mm", "cm", "min", "m³", "m²", "m3", "m2", "㎡", "dB", "°C",
         "℃", "%", "％", "‰", "米", "吨", "m", "t", "h", "天", "日", "周", "月", "年", "层", "个", "处",
         "组", "道", "台", "套", "辆", "部", "人", "名", "次", "遍", "根", "块", "榀", "班", "级", "倍",
         "项", "批", "段", "座")
NUMBER_UNIT = re.compile(r"(?<![\d.A-Za-z])(\d+(?:\.\d+)?)\s*(" + "|".join(map(re.escape, UNITS)) + r")(?![A-Za-z²³])")
SAME_UNIT = {"m2": "平方米", "m²": "平方米", "㎡": "平方米", "m3": "立方米", "m³": "立方米", "t": "吨",
             "％": "%", "kg": "千克", "公斤": "千克", "km": "千米", "公里": "千米", "°C": "℃", "m": "米"}
DATE_UNITS = {"年", "月", "日"}  # 日期不算可考核的量化指标（W2）

# B5：岗位后面紧跟姓名【推断】。只认常见单姓，姓名后须是标点或"负责""担任"之类，减少把普通词当人名
ROLES = ("项目经理", "项目负责人", "技术负责人", "项目总工", "总工程师", "施工员", "质量员", "安全员", "材料员",
         "资料员", "机械员", "劳务员", "标准员", "预算员", "造价员", "测量员", "试验员", "施工队长", "班组长")
SURNAMES = ("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘蒋蔡余杜叶程苏魏吕丁"
            "任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵钱覃武戴莫孔汤")
PERSON = re.compile(r"(?:" + "|".join(ROLES) + r")(?:由|为|是|[：:])?\s*([" + SURNAMES + r"][一-龥]{1,2})"
                    r"(?=[，,。、；;：:\s（(）)]|担任|负责|全面|主持|同志|先生|女士|$)")
LONG_DIGITS = re.compile(r"(?<!\d)\d{8,}(?!\d)")  # 证书编号、电话、身份证号
LANDLINE = re.compile(r"(?<!\d)0\d{2,3}-\d{7,8}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+", re.ASCII)  # \w 默认含汉字，会把"邮箱abc@…"的汉字一起吞进去

# B7：地名只认省、市、县、镇、乡（"区"在施组里多是办公区、生活区）；前两个字加尾字，再排除常见泛称
PLACE = re.compile(r"([一-龥]{2})([省市县镇乡])(?![政场区级民容内外面])")
GENERIC_PLACES = {"全市", "本市", "该市", "城市", "超市", "各市", "外市", "省市", "市县", "全省", "本省", "该省",
                  "外省", "各省", "全县", "本县", "该县", "各县", "城镇", "乡镇", "村镇", "集镇", "小镇", "全镇",
                  "本镇", "该镇", "城乡", "本乡", "各乡"}
FUNCTION_CHARS = set("的在于和与及至到从向对为是将把被由按往级所")
NAME_RUN = re.compile(r"[一-龥A-Za-z0-9（）()·]+")
PROJECT_END = re.compile(r"项目|工程")
COMPANY = re.compile(r"[一-龥（）()]{4,30}?(?:有限责任公司|股份有限公司|有限公司|集团)")

# B8：采购文件的章节号、条款号（R17）。紧跟在规范编号后面的"第 x.x.x 条"是依据，不算
NORM_CODE = re.compile(r"(?:GB|JGJ|JG|CJJ|DBJ|DB|JTG|CECS|SL|DL|HG|T/[A-Z]+)\s*/?\s*T?\s*\d{2,5}")
CLAUSE_PATTERNS = (
    re.compile(r"第\s*[一二三四五六七八九十百零〇\d]+\s*章"),
    re.compile(r"(?:须知|前附表|评标办法|招标文件|采购文件|招标公告|合同条款)[^。；;，,\n]{0,8}?第\s*"
               r"[\d一二三四五六七八九十]+(?:\.\d+)*\s*[章节条款项]"),
    re.compile(r"(?:投标人须知|须知前附表|评标办法)(?:前附表)?\s*\d+(?:\.\d+)+"),
    re.compile(r"第\s*\d+(?:\.\d+)+\s*[项款]"),
)
# 写作过程用语和面向评审的话（R18），以及不该进成品的来源标签
PROCESS_WORDS = ("本节将", "本章将", "本项将", "本文将", "本方案将", "下文将", "以下将", "下面将", "下面介绍",
                 "根据招标文件要求", "按照招标文件要求", "按招标文件要求", "依据招标文件要求", "根据评审内容",
                 "评分标准", "评审要点", "评审内容要求", "得分点", "评委", "评审专家", "评标专家",
                 "【推断】", "【一手】", "【二手】", "此处省略")
# 只认真实标签名：施组里"强度<C35，温度>5℃"这样的比较符不能被当成标签（B8 不能放行）
HTML_TAG = re.compile(r"</?(?:br|p|div|span|sup|sub|b|i|u|font|table|tr|td|th|img|a|strong|em|center)\b[^<>]*>",
                      re.IGNORECASE)

# B13：形式评审"未出现投标报价"（真实招标文件原文：商务及技术文件中未出现有关投标报价的内容）【推断】。
# 报价用语按长的先配；金额要数字或大写数字紧跟"元"，"3单元""元件"不算
PRICE_TERMS = ("最高投标限价", "招标控制价", "投标总报价", "投标报价", "投标总价", "总报价", "报价", "投标价", "中标价",
               "合同价", "综合单价", "下浮率", "让利", "费率")
PRICE_TERM = re.compile("|".join(map(re.escape, PRICE_TERMS)))
MONEY = re.compile(r"(?<![\d.])\d+(?:[,，]\d{3})*(?:\.\d+)?\s*[万亿]?元(?![件素旦])|[¥￥]\s*\d[\d,，.]*"
                   r"|[零壹贰叁肆伍陆柒捌玖拾佰仟万亿]{2,}[元圆]|人民币\s*\d[\d,，.]*")

# W3：套话【推断】，每千字 3 处以上报警
STOCK_PHRASES = ("确保万无一失", "高标准、严要求", "高标准严要求", "高度重视", "全力以赴", "精心组织", "精心施工",
                 "严格把关", "切实加强", "科学管理", "优质高效", "狠抓落实", "常抓不懈", "万无一失", "认真贯彻",
                 "积极配合", "密切配合", "全面落实", "层层落实", "扎实推进", "务求实效", "精益求精", "一丝不苟",
                 "尽职尽责", "齐抓共管", "统筹兼顾", "行之有效", "切实可行", "有条不紊", "井然有序", "强有力",
                 "全方位", "多层次")
STOCK = re.compile("|".join(map(re.escape, STOCK_PHRASES)))
STOCK_PER_THOUSAND = 3
# W4：规范条文的写法【推断】；一段里引 3 个以上条文号，多半是逐条转述
NORM_PHRASES = ("应符合下列规定", "应符合以下规定", "应符合下列要求", "应符合下列条件", "应按下列规定",
                "本规范", "本标准", "本规程", "条文说明")
NORM_CLAUSE = re.compile(r"第\s*\d+(?:\.\d+){1,3}\s*条")
REPEAT_CHARS = 40
# W7：从标题里去掉这些泛词，剩下的两字片段才算"本项的关键词"
TITLE_STOPWORDS = ("技术组织措施", "组织措施", "拟投入的", "拟投入", "主要", "确保", "措施", "计划", "安排", "施工",
                   "工程", "管理", "体系", "的", "与", "和", "及")


def hit(gate: str, match: str, message: str, fixed: bool = False) -> dict:
    """fixed：不能说明理由放行的命中（门禁本身的前提缺失），只能改。"""
    return {"gate": gate, "match": match, "message": message, **({"fixed": True} if fixed else {})}


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def visible_lines(text: str) -> list[str]:
    """成品里看得见的文字：去掉版式标记，标题去掉 #，图片只留图题，表格去掉竖线和分隔行。"""
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        caption = TABLE_CAPTION.fullmatch(line)
        if caption:
            lines.append(caption.group(1))
            continue
        if not line or LAYOUT_MARKER.match(line) or (line.startswith("|") and TABLE_RULE.match(line)):
            continue
        image = IMAGE.match(line)
        if image:
            line = image.group(1)
        elif line.startswith("|"):
            line = " ".join(cell.strip() for cell in line.strip("|").split("|"))
        else:
            line = BULLET.sub("", HEADING.sub("", line))
        if line.strip():
            lines.append(line.strip())
    return lines


def body_lines(text: str) -> list[str]:
    """渲染器当正文段落的行（同 build_response_docx）：不含标题、表格、图片和版式标记，列表标记剥掉。"""
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not (LAYOUT_MARKER.match(line) or HEADING.match(line) or line.startswith("|")
                         or IMAGE.match(line)):
            lines.append(BULLET.sub("", line))
    return lines


def plain_number(number: str) -> str:
    return number.rstrip("0").rstrip(".") if "." in number else number


def number_tokens(text: str) -> list[tuple[str, str]]:
    """(数字, 统一后的单位)：4800㎡ 与 4800平方米 算同一个。"""
    return [(plain_number(m.group(1)), SAME_UNIT.get(m.group(2), m.group(2))) for m in NUMBER_UNIT.finditer(text)]


def fact_probes(fact: dict) -> tuple[set[tuple[str, str]], list[str]]:
    """一条事实在正文里的"指纹"：它的数字＋单位、工程量；没有数字时取冒号后的短语。"""
    text = str(fact.get("text") or "")
    numbers = set(number_tokens(text))
    quantity = fact.get("quantity") or {}
    if isinstance(quantity.get("amount"), (int, float)) and quantity.get("unit"):
        numbers |= set(number_tokens(f"{quantity['amount']}{quantity['unit']}"))
    if numbers:
        return numbers, []
    tail = text.split("：", 1)[-1].split(":", 1)[-1]
    return set(), [part for part in re.split(r"[，,。；;、（）()\s]+", tail) if 4 <= len(part) <= 16]


def fact_used(fact: dict, text: str) -> bool:
    numbers, phrases = fact_probes(fact)
    return bool(numbers & set(number_tokens(text))) or any(phrase in compact(text) for phrase in phrases)


def load_identity_terms(project_dir: Path) -> list[dict] | None:
    """用户提供的身份词清单；没有文件返回 None。格式不对报错，不悄悄当成空清单。"""
    path = project_dir / IDENTITY_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{IDENTITY_FILE} 读不出来: {exc}") from exc
    terms = data.get("terms") if isinstance(data, dict) else None
    if not isinstance(terms, list) or data.get("schema") != IDENTITY_SCHEMA:
        raise ValueError(f"{IDENTITY_FILE} 须是 schema {IDENTITY_SCHEMA}，terms 为列表")
    for entry in terms:
        if not isinstance(entry, dict) or len(str(entry.get("term") or "").strip()) < 2 \
                or entry.get("kind") not in IDENTITY_KINDS:
            raise ValueError(f"{IDENTITY_FILE} 每条须写 term（至少 2 个字）和 kind（{'、'.join(IDENTITY_KINDS)}）")
    if not any(entry["kind"] == "公司全称" for entry in terms):
        raise ValueError(f"{IDENTITY_FILE} 至少要有一条公司全称")
    return terms


def identity_term_hits(text: str, terms: list[dict] | None, list_error: str) -> list[dict]:
    if list_error:
        return [hit("B5", "identity-terms-invalid", f"身份词清单有问题：{list_error}", fixed=True)]
    if terms is None:
        return [hit("B5", "identity-terms-missing", f"没有身份词清单 {IDENTITY_FILE}：公司全称、简称、商标、网址都没查。"
                    "请用户提供，复制 templates/identity-terms.json 填写（决策 4a-3A）", fixed=True)]
    flat = compact(text).lower()
    return [hit("B5", entry["term"], f"出现身份词“{entry['term']}”（{entry['kind']}）")
            for entry in terms if compact(entry["term"]).lower() in flat]


def identity_pattern_hits(text: str) -> list[dict]:
    hits = [hit("B5", m.group(1), f"疑似人名“{m.group(1)}”（岗位后面跟着姓名）：只写岗位和持证类别")
            for m in PERSON.finditer(text)]
    for m in LONG_DIGITS.finditer(text):
        digits = m.group()
        label = "手机号" if re.fullmatch(r"1[3-9]\d{9}", digits) else \
            "身份证号" if len(digits) == 18 else "长串数字（证书编号、电话之类）"
        hits.append(hit("B5", digits, f"疑似{label}“{digits}”"))
    hits += [hit("B5", m.group(), f"疑似电话“{m.group()}”") for m in LANDLINE.finditer(text)]
    hits += [hit("B5", m.group(), f"疑似邮箱“{m.group()}”") for m in EMAIL.finditer(text)]
    return hits


def b5_hits(text: str, terms: list[dict] | None, list_error: str = "") -> list[dict]:
    """身份泄露（正文部分；文档属性和页眉图片随第 4b 步）。暗标阻断、其他轨道提示由编排脚本定（D3）。"""
    visible = "\n".join(visible_lines(text))
    return identity_term_hits(visible, terms, list_error) + identity_pattern_hits(visible)


def known_text(rule_card: dict, fact_card: dict | None) -> str:
    """B7 的"本项目"范围：规则卡全部内容和事实卡的原文、出处。"""
    facts = [f"{fact.get('text') or ''}{fact.get('source') or ''}" for fact in (fact_card or {}).get("facts") or []
             if isinstance(fact, dict)]
    return compact(json.dumps(rule_card, ensure_ascii=False) + "".join(facts))


def place_names(line: str) -> list[str]:
    return [m.group() for m in PLACE.finditer(line)
            if m.group()[1:] not in GENERIC_PLACES and m.group()[0] not in FUNCTION_CHARS
            and m.group()[1] not in FUNCTION_CHARS]


def project_names(line: str, known: str) -> list[str]:
    """带已知地名的"……项目/工程"：从地名起到结尾不在卡片里，就是同一地方的别的项目（地名不认识的由地名报）。"""
    names = []
    for run in NAME_RUN.finditer(line):
        for end in PROJECT_END.finditer(run.group()):
            head = run.group()[:end.end()]
            places = [m for m in PLACE.finditer(head) if m.group() in known]
            if places and head[places[0].start():] not in known:
                names.append(head[places[0].start():])
    return names


def known_suffix(name: str, known: str, shortest: int = 6) -> bool:
    """名称前面常带着"由""与"之类的字：从后往前截，有一段 6 字以上在卡片里就算本项目的。"""
    return any(name[start:] in known for start in range(max(len(name) - shortest + 1, 1)))


def company_names(line: str, own: set[str]) -> list[str]:
    """先抹掉本公司的身份词（归 B5 报），剩下的"……有限公司/集团"才查。"""
    rest = compact(line)
    for term in sorted(own, key=len, reverse=True):
        rest = rest.replace(term, "＃")
    return [m.group() for m in COMPANY.finditer(rest)]


def b7_hits(text: str, rule_card: dict, fact_card: dict | None, terms: list[dict] | None) -> list[dict]:
    """残留：卡片里没有的地名、项目名、单位名（Q10）。本公司名称归 B5，不在这里重复报。"""
    known = known_text(rule_card, fact_card)
    own = {compact(entry["term"]) for entry in terms or []}
    hits = []
    for line in visible_lines(text):
        hits += [hit("B7", name, f"疑似非本项目的地名“{name}”：事实卡、规则卡里都没有")
                 for name in place_names(line) if name not in known]
        hits += [hit("B7", name, f"疑似别的项目“{name}”：事实卡、规则卡里没有这个名称")
                 for name in project_names(line, known)]
        hits += [hit("B7", name, f"疑似别的单位“{name}”：事实卡、规则卡里没有")
                 for name in company_names(line, own) if not known_suffix(name, known)]
    return hits


def near_norm_code(line: str, start: int) -> bool:
    return bool(NORM_CODE.search(line[max(0, start - 25):start]))


def clause_numbers(line: str) -> list[str]:
    """几条规则可能落在同一段文字上（"须知第3.7.5项"），同一处只报一次。"""
    spans: list[tuple[int, int]] = []
    for pattern in CLAUSE_PATTERNS:
        for m in pattern.finditer(line):
            if not near_norm_code(line, m.start()) and all(m.end() <= start or m.start() >= end for start, end in spans):
                spans.append(m.span())
    return [line[start:end] for start, end in sorted(spans)]


def b8_leak_hits(text: str) -> list[dict]:
    """只查渲染器当正文段落的行（同 build_response_docx 的调用处）：图片、表格、标题、版式标记不进来。"""
    hits = []
    for line in body_lines(text):
        hits += [hit("B8", f"{leak}|{line[:30]}", f"Markdown 痕迹（{leak}）：“{line[:30]}”")
                 for leak in detect_markdown_leaks(line)]
        if line.startswith("<!--") or "-->" in line:
            hits.append(hit("B8", line[:30], f"版式标记以外的 HTML 注释会印进成品：“{line[:30]}”"))
        elif HTML_TAG.search(line):
            hits.append(hit("B8", HTML_TAG.search(line).group(), f"HTML 标签“{HTML_TAG.search(line).group()}”"))
    return hits


def b8_hits(text: str) -> list[dict]:
    """采购文件章节号和条款号（R17）、写作过程用语（R18）、Markdown 泄漏（R19）。不能放行，误报就改规则。"""
    hits = []
    for line in visible_lines(text):
        hits += [hit("B8", found, f"正文写了采购文件的章节号或条款号“{found}”（R17）") for found in clause_numbers(line)]
        hits += [hit("B8", word, f"写作过程用语或来源标签“{word}”（R18）") for word in PROCESS_WORDS if word in line]
    return hits + b8_leak_hits(text)


def b13_hits(text: str) -> list[dict]:
    """施组出现报价用语或金额（Q0）。表格也查：单价、费用最容易随物资表带进来。所有轨道都阻断；招标文件给的
    投资额、应急资金额度这类与报价无关的，用户复核后说明理由放行。"""
    hits = []
    for line in visible_lines(text):
        hits += [hit("B13", compact(found), f"施组里出现报价用语或金额“{found}”：形式评审要求商务及技术文件不出现"
                     "有关投标报价的内容，删去或改写（Q0）") for found in PRICE_TERM.findall(line) + MONEY.findall(line)]
    return hits


def w2_hits(text: str) -> list[dict]:
    """每项至少一组可考核的量化指标（R14）：数字＋单位，日期不算。第一行是标题，不算。"""
    tokens = [token for line in visible_lines(text)[1:] for token in number_tokens(line) if token[1] not in DATE_UNITS]
    return [] if tokens else [hit("W2", "no-indicator", "没有一处“数字＋单位”的量化指标（R14）")]


def w3_hits(text: str) -> list[dict]:
    body = compact("".join(body_lines(text)))
    found = STOCK.findall(body)
    if len(found) < 2 or len(found) * 1000 < STOCK_PER_THOUSAND * max(len(body), 1):
        return []
    top = "、".join(dict.fromkeys(found))
    return [hit("W3", "stock-density", f"套话 {len(found)} 处，约每千字 {len(found) * 1000 // max(len(body), 1)} 处"
                f"（{top}）：换成本项目的做法和数字（Q6）")]


def sentences(text: str) -> set[str]:
    return {part for part in re.split(r"[。！？；!?;]", compact("".join(body_lines(text)))) if len(part) >= REPEAT_CHARS}


def w4_hits(text: str, others: dict[int, str]) -> list[dict]:
    """疑似抄录：规范条文写法、一段多个条文号、与别的项整句相同。只在本机比对，查不到网络文本（R26）。"""
    hits = []
    for line in body_lines(text):
        hits += [hit("W4", phrase, f"规范条文写法“{phrase}”：规范只引编号，不抄条文（Q7）")
                 for phrase in NORM_PHRASES if phrase in line]
        cited = NORM_CLAUSE.findall(line)
        if len(cited) >= 3:
            hits.append(hit("W4", line[:30], f"一段里引了 {len(cited)} 个条文号，疑似逐条转述规范：“{line[:30]}”"))
    own = sentences(text)
    for other_no, other_text in sorted(others.items()):
        for sentence in sorted(own & sentences(other_text)):
            hits.append(hit("W4", sentence, f"与第 {other_no} 项有一整句相同（{len(sentence)} 字）：“{sentence[:24]}…”"))
    return hits


def title_keys(title: str) -> set[str]:
    rest = title
    for word in TITLE_STOPWORDS:
        rest = rest.replace(word, " ")
    parts = [part for part in re.split(r"[\s、，,（）()]+", rest) if len(part) >= 2] or [title]
    return {part[index:index + 2] for part in parts for index in range(len(part) - 1)}


def w7_hits(text: str, title: str, cited_facts: list[dict]) -> list[dict]:
    """第一段直接回答本项（Q2）：含标题里的关键词，并有数字或本项目事实【推断】。"""
    lines = body_lines(text)
    first = lines[0] if lines else ""
    has_key = any(key in first for key in title_keys(title))
    has_fact = bool(re.search(r"\d", first)) or any(fact_used(fact, first) for fact in cited_facts)
    if has_key and has_fact:
        return []
    missing = "、".join(label for label, ok in (("本项的关键词", has_key), ("数字或本项目事实", has_fact)) if not ok)
    return [hit("W7", "first-paragraph", f"第一段缺{missing}：开头直接回答本项怎么做、达到什么指标（Q2）")]


def w10_hits(text: str, fact_card: dict) -> list[dict]:
    """W10：正文要设现场限制禁止的设施（事实卡里补疑、答疑写了不允许设办公区、严禁室外堆放……），这句却没写不设
    或场外怎么解决。每种设施一条提示，同一项里多句合并计数。只是叫法比对，可以说明理由不改（第 6b 步，决策 S5-A）。"""
    forbidden = forbidden_objects(list(fact_card.get("facts") or []))
    hits = []
    for line in visible_lines(text)[1:]:  # 第一行是本项标题
        for sentence in re.split(r"[。！？；!?;]", line):
            hits += [hit("W10", name, f"现场限制（{fact_refs([name], forbidden)}）不能设{name}，这句却照写，没说不设或场外"
                         f"怎么解决：“{sentence.strip()[:30]}”。改成现场不设、写明场外解决方式，或说明理由（Q3、R15）")
                     for name in unresolved(sentence, forbidden)]
    return hits
