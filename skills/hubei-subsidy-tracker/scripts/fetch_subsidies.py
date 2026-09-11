#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
湖北/武汉企业补贴政策采集 + 内容获取 + 门槛解析  v2 (Skill 可移植版)
=================================================================
阶段1 采集：8 个官方通知公告列表页/JSON，按原文链接去重，写 subsidy_records.xlsx
阶段2a 内容：对新采集且未抓正文的记录，抓详情页正文 + 附件(PDF/Word/Excel)
阶段2b 门槛：从正文解析 资质/规模/营收/财务/社保/人才/行业/地域/材料/额度/截止

可移植：数据目录由环境变量 SUBSIDY_DATA_DIR 指定，默认 Skill 下的 data/。
用法:
  python fetch_subsidies.py --collect                 # 仅采集
  python fetch_subsidies.py --content                 # 仅抓正文+附件
  python fetch_subsidies.py --parse-thresholds        # 仅解析门槛
  python fetch_subsidies.py                           # 三阶段依次执行
  python fetch_subsidies.py --collect --dry           # 采集预览不写文件
依赖: requests beautifulsoup4 lxml openpyxl
"""
import os, re, sys, json, datetime, hashlib
import openpyxl
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote, urljoin, urlparse

# ---------- 数据目录(可移植) ----------
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("SUBSIDY_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DATA_DIR = os.path.abspath(DATA_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
XLSX_PATH = os.path.join(DATA_DIR, "subsidy_records.xlsx")
CONTENT_DIR = os.path.join(DATA_DIR, "content")
ATTACH_DIR = os.path.join(DATA_DIR, "attachments")
DIGEST_PATH = os.path.join(DATA_DIR, "digest_latest.md")
for d in (CONTENT_DIR, ATTACH_DIR):
    os.makedirs(d, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
TIMEOUT = 25
# 附件下载保持较小的资源边界；政府页面偶尔会返回错误的大文件或 HTML。
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_ATTACHMENTS_PER_POLICY = 10
ATT_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".png", ".jpg", ".jpeg")
ATT_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".doc": {"application/msword"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".xls": {"application/vnd.ms-excel"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".zip": {"application/zip", "application/x-zip-compressed"},
    ".rar": {"application/vnd.rar", "application/x-rar-compressed"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
}
ALLOWED_GENERIC_CONTENT_TYPES = {"", "application/octet-stream", "binary/octet-stream"}

# ---------- 数据源：8 个官方通知公告列表页/接口 ----------
SOURCES = [
    {"name": "湖北省经济和信息化厅", "level": "省", "dept": "经信",
     "url": "http://jxt.hubei.gov.cn/fbjd/zc/qtzdgkwj/gwfb/"},
    {"name": "武汉市经济和信息化局", "level": "市", "dept": "经信",
     "url": "https://jxj.wuhan.gov.cn/xwzx_9/tztg/"},
    {"name": "湖北省科学技术厅", "level": "省", "dept": "科技",
     "url": "https://kjt.hubei.gov.cn/kjdt/tzgg/"},
    {"name": "武汉市科技创新局", "level": "市", "dept": "科技",
     "url": "https://kjj.wuhan.gov.cn/wmfw/tzgg/tzgg_18371/"},
    {"name": "湖北省财政厅", "level": "省", "dept": "财政",
     "type": "json",
     "url": "https://czt.hubei.gov.cn/zfxxgk_GK2020/zc_GK2020/qtzdgkwj/qtzd.json",
     "seed_since": "2026-01-01"},
    {"name": "武汉市财政局", "level": "市", "dept": "财政",
     "url": "https://czj.wuhan.gov.cn/BMDT/TZGG/"},
    {"name": "湖北省人力资源和社会保障厅", "level": "省", "dept": "人社",
     "url": "http://rst.hubei.gov.cn/bmdt/dtyw/tzgg/"},
    {"name": "武汉市人力资源和社会保障局", "level": "市", "dept": "人社",
     "url": "https://rsj.wuhan.gov.cn/zwgk_17/zc/qtzdgkwj/zcfg/"},
]

# ---------- 相关性过滤 ----------
NEGATIVE = ["招标", "采购", "磋商", "询价", "中标", "比选", "拍卖", "出让",
            "会议", "培训", "讲座", "招聘", "简章", "后台", "隐私", "新媒体",
            "矩阵", "留言", "调查", "投票", "直播", "视频", "图解", "访谈",
            "工人日报", "媒体", "通讯", "报道", "新闻", "举行", "召开", "调研",
            "职能", "研究所", "中心）", "服务中心", "司局"]
POSITIVE = ["补贴", "补助", "奖励", "奖补", "申报", "征集", "专项", "资金",
            "券", "扶持", "兑现", "政策", "办法", "措施", "细则", "规定",
            "认定", "资助", "贴息", "创业", "就业", "人才", "社保", "高企",
            "高新技术", "专精特新", "单项冠军", "瞪羚", "研发", "项目", "惠企",
            "纾困", "减税降费", "减免", "返还", "稳岗", "技能", "见习", "博士后",
            "留学", "返乡", "孵化", "上云", "工业软件", "数字孪生", "智能",
            "通知", "公告", "方案", "计划", "指引", "意见"]

# 结果公告类：前期不采集（等后续有需求再放开）。标题含结果词且不含申报动作词 → 丢弃
RESULT_KWS = ["公示", "公布", "名单", "通报", "结果", "验收", "立项", "入选", "兑付", "拨付"]
APPLY_KWS = ["申报", "征集", "报名", "指南", "预申报"]
HIGH_SIGNAL_KWS = ["补贴", "补助", "奖励", "奖补", "申报", "征集", "专项", "资金",
                   "券", "扶持", "兑现", "政策", "办法", "措施", "细则", "认定",
                   "资助", "贴息", "减税", "减免", "返还", "稳岗", "高企", "高新技术",
                   "专精特新", "单项冠军", "瞪羚", "研发", "项目", "惠企"]

CATEGORY_RULES = [
    ("申报通知", ["申报", "征集", "预申报", "组织申报", "开展", "通知"]),
    ("结果公示", ["公示", "公告", "通报", "公布", "名单"]),
    ("资金补贴", ["补贴", "补助", "奖励", "奖补", "资金", "券", "贴息",
                "资助", "兑现", "减免", "返还", "减税降费"]),
    ("资质认定", ["认定", "入库", "复核", "遴选"]),
    ("政策文件", ["政策", "办法", "措施", "细则", "规定", "意见", "方案", "计划"]),
]

DATE8 = re.compile(r'20\d{6}')
DATESEP = re.compile(r'20\d{2}/\d{2}/\d{2}')
DATE_HUMAN = re.compile(r'(\d{4})\s*[-年./]\s*(\d{1,2})\s*[-月./]\s*(\d{1,2})')

# 列表页偶尔会把多年以前的归档混进搜索结果。每日采集只接纳近期发布的
# 政策；仍在有效期内的历史政策应通过首次人工导入保留，不依赖列表回捞。
DEFAULT_LOOKBACK_DAYS = 370
INVALID_POLICY_WORDS = ("已废止", "予以废止", "停止执行", "不再执行", "已经失效", "已失效")

# ---------- 政策表全字段(含阶段2b解析列) ----------
POLICY_FIELDS = ["序号", "标题", "发布部门", "部门级别", "政策类别", "发布日期",
                 "申报截止", "关键词标签", "原文链接", "正文已抓", "附件路径",
                 "要素已解析", "资质要求", "规模要求", "财务要求", "社保要求",
                 "人才要求", "行业要求", "地域要求", "申报材料", "支持额度",
                 "申报对象", "采集时间", "处理状态", "是否匹配", "备注",
                 "解析状态", "解析置信度", "解析备注", "附件下载失败",
                 "政策状态", "失效原因"]


def _as_date(value):
    """把 Excel 日期、日期时间和常见文本统一为 date。"""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value or "").strip()
    match = re.match(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})", text)
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def publication_is_fresh(value, today=None, lookback_days=None):
    """只接纳有可靠发布日期、未超出每日检索窗口的记录。"""
    published = _as_date(value)
    if not published:
        return False
    today = today or datetime.date.today()
    if lookback_days is None:
        try:
            lookback_days = max(1, int(os.environ.get("SUBSIDY_LOOKBACK_DAYS", DEFAULT_LOOKBACK_DAYS)))
        except ValueError:
            lookback_days = DEFAULT_LOOKBACK_DAYS
    age = (today - published).days
    return 0 <= age <= lookback_days


def canonical_url(value):
    """去掉锚点和常见追踪参数，避免同一原文换参数后重复入库。"""
    parsed = urlparse(str(value or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return str(value or "").strip()
    ignored = {"from", "source", "spm", "utm_source", "utm_medium", "utm_campaign"}
    pairs = []
    for item in parsed.query.split("&") if parsed.query else []:
        key = item.split("=", 1)[0].lower()
        if key and key not in ignored:
            pairs.append(item)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(),
                           path=path, query="&".join(pairs), fragment="").geturl()


def policy_identity(title, department, published):
    """URL 变化时用稳定的标题、部门和发布日期识别同一政策。"""
    normalized = re.sub(r"[\W_]+", "", str(title or "").lower(), flags=re.UNICODE)
    return normalized, str(department or "").strip(), str(published or "").strip()[:10]


def policy_status(row, text="", today=None, lookback_days=None):
    """返回 (状态, 原因)；过期、废止和无有效期证据的陈旧政策不再进入下游。"""
    today = today or datetime.date.today()
    recorded_state = str(row.get("政策状态") or "").strip()
    if recorded_state in {"已过期", "已失效", "无效", "废止"}:
        return recorded_state, str(row.get("失效原因") or "").strip()
    combined = " ".join((str(row.get("标题") or ""), str(text or "")))
    invalid_word = next((word for word in INVALID_POLICY_WORDS if word in combined), "")
    if invalid_word:
        return "已失效", f"原文出现“{invalid_word}”"
    deadline = _as_date(row.get("申报截止"))
    if deadline and deadline < today:
        return "已过期", f"申报截止日期为{deadline:%Y-%m-%d}"
    published = _as_date(row.get("发布日期"))
    if deadline and deadline >= today:
        return "有效", ""
    if published and publication_is_fresh(published, today=today, lookback_days=lookback_days):
        return "有效", ""
    return "已失效", "发布日期超出检索窗口，且未发现仍在有效期内的截止日期"


def policy_is_active(row, today=None):
    return policy_status(row, today=today)[0] == "有效"


# ===========================================================================
# 采集(阶段1)
# ===========================================================================
def fetch(url):
    try:
        # requests 的默认 TLS 校验必须保持开启，官方来源不得被降级为明文信任。
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=True)
    except Exception as e:
        return None, f"ERR {e}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    enc = (r.apparent_encoding or "utf-8").lower()
    txt = r.content.decode("gb18030" if ("gb" in enc or "2312" in enc) else "utf-8",
                           errors="ignore")
    return r, txt

def parse_date_from_url(u):
    m = DATE8.search(u)
    if m:
        s = m.group(0)
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    m = DATESEP.search(u)
    if m:
        p = re.split(r'/', m.group(0))
        return f"{p[0]}-{p[1]}-{p[2]}"
    return ""

def clean_title(raw):
    s = re.sub(r'\s+', ' ', raw or '').strip()
    s = re.sub(r'^\s*\d{1,3}\s*20\d{2}[-/]\d{2}\s*', '', s)
    s = re.sub(r'^\s*\d{2}[-/]\d{2}\s*20\d{2}\s*', '', s)
    s = re.sub(r'^\s*20\d{2}[-/]\d{2}([-/]\d{2})?\s*', '', s)
    s = re.sub(r'^\s*20\d{6}\s*', '', s)
    m = re.search(r'20\d{2}[-/]\d{2}([-/]\d{2})?|20\d{6}', s)
    if m:
        s = s[:m.start()]
    s = s.strip(' \t-|—·')
    return s.strip()

def is_relevant(title):
    for w in NEGATIVE:
        if w in title:
            return False, []
    # 结果公告类（公示/名单/通报/验收/立项等）前期不抓；含申报动作词的除外
    if any(w in title for w in RESULT_KWS) and not any(w in title for w in APPLY_KWS):
        return False, []
    # “通知、就业、人才、计划”等低信号词不能单独让普通新闻进入政策库。
    if not any(w in title for w in HIGH_SIGNAL_KWS):
        return False, []
    hits = [w for w in POSITIVE if w in title]
    return (len(hits) > 0), hits

def infer_category(title, hits):
    for cat, kws in CATEGORY_RULES:
        for k in kws:
            if k in title:
                return cat
    return "其他"

def extract_from_json(src):
    r, txt = fetch(src["url"])
    if not r:
        raise RuntimeError(f"{src['name']} 无法读取：{txt}")
    try:
        data = json.loads(txt)
    except Exception as e:
        raise RuntimeError(f"{src['name']} JSON解析失败") from e
    rows = data.get("data", []) if isinstance(data, dict) else data
    since = src.get("seed_since", "")
    items, seen = [], set()
    for it in rows:
        absu = (it.get("URL") or "").strip()
        if not absu or absu in seen:
            continue
        seen.add(absu)
        title = clean_title(it.get("FILENAME") or it.get("title") or "")
        if len(title) < 6:
            continue
        date = (it.get("PUBDATE") or it.get("DOCRELTIME") or parse_date_from_url(absu))
        if since and date and date < since:
            continue
        if not publication_is_fresh(date):
            continue
        ok, hits = is_relevant(title)
        if not ok:
            continue
        items.append(_mk_item(src, title, date, absu, hits))
    items.sort(key=lambda x: x["date"], reverse=True)
    return items

def _mk_item(src, title, date, absu, hits):
    return {"title": title, "dept_full": src["name"], "level": src["level"],
            "dept": src["dept"], "date": date, "url": absu,
            "category": infer_category(title, hits), "tags": "、".join(hits[:6])}

def extract_from_source(src):
    if src.get("type") == "json":
        return extract_from_json(src)
    r, txt = fetch(src["url"])
    if not r:
        raise RuntimeError(f"{src['name']} 无法读取：{txt}")
    dom = urlparse(r.url).netloc
    soup = BeautifulSoup(txt, "lxml")
    items, seen = [], set()
    for a in soup.find_all("a"):
        h = a.get("href") or ""
        if not h:
            continue
        absu = urljoin(r.url, h)
        if urlparse(absu).netloc != dom:
            continue
        if not (DATE8.search(absu) or DATESEP.search(absu)):
            continue
        if absu in seen:
            continue
        seen.add(absu)
        title = clean_title(a.get_text(" ", strip=True))
        if len(title) < 6:
            continue
        published = parse_date_from_url(absu)
        if not publication_is_fresh(published):
            continue
        ok, hits = is_relevant(title)
        if not ok:
            continue
        items.append(_mk_item(src, title, published, absu, hits))
    items.sort(key=lambda x: x["date"], reverse=True)
    return items

def load_existing():
    existing = {}
    if os.path.exists(XLSX_PATH):
        wb = openpyxl.load_workbook(XLSX_PATH)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if rows:
            hdr = list(rows[0])
            for r in rows[1:]:
                d = {hdr[i]: ("" if (i >= len(r) or r[i] is None) else r[i])
                     for i in range(len(hdr))}
                u = str(d.get("原文链接", "")).strip()
                if u:
                    existing[u] = d
    return existing

def collect(dry=False):
    from setup_state import atomic_json
    report = {"started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "sources": []}
    existing = load_existing()
    print(f"  已存档: {len(existing)} 条")
    existing_urls = {canonical_url(url) for url in existing}
    existing_identities = {
        policy_identity(row.get("标题"), row.get("发布部门"), row.get("发布日期"))
        for row in existing.values()
    }
    all_items = []
    for src in SOURCES:
        print(f"  抓取 {src['name']} ...")
        try:
            items = extract_from_source(src)
            report["sources"].append({"name": src["name"], "status": "ok", "count": len(items),
                                      "warning": "零命中，请核对源页面和解析规则" if not items else ""})
        except Exception as exc:
            items = []
            report["sources"].append({"name": src["name"], "status": "failed", "error_type": type(exc).__name__})
            print(f"    [失败] {src['name']}（{type(exc).__name__}），继续其余来源")
        print(f"    命中 {len(items)} 条")
        all_items.extend(items)
    new_items, seen_urls, seen_identities = [], set(), set()
    for it in all_items:
        normalized_url = canonical_url(it["url"])
        identity = policy_identity(it["title"], it["dept_full"], it["date"])
        if (normalized_url in existing_urls or normalized_url in seen_urls
                or identity in existing_identities or identity in seen_identities):
            continue
        seen_urls.add(normalized_url)
        seen_identities.add(identity)
        new_items.append(it)
    print(f"  本次新增: {len(new_items)} 条")
    if dry:
        for it in new_items:
            print(f"   + [{it['date']}][{it['dept_full']}] {it['title']}\n      {it['url']}")
        return new_items
    _upsert_rows(new_items, existing)
    report["success"] = bool(report["sources"]) and all(s["status"] == "ok" for s in report["sources"])
    atomic_json(os.path.join(DATA_DIR, "collection_report.json"), report)
    print(f"  主表: {XLSX_PATH}")
    return new_items

def _upsert_rows(new_items, existing):
    existing_rows = []
    if os.path.exists(XLSX_PATH):
        wb = openpyxl.load_workbook(XLSX_PATH)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if rows:
            hdr = list(rows[0])
            for r in rows[1:]:
                existing_rows.append(
                    {hdr[i]: ("" if (i >= len(r) or r[i] is None) else r[i])
                     for i in range(len(hdr))})
    start_idx = len(existing_rows) + 1
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(POLICY_FIELDS))
    for row in existing_rows:
        ws.append([row.get(f, "") for f in POLICY_FIELDS])
    for i, it in enumerate(new_items, start=start_idx):
        base = {f: "" for f in POLICY_FIELDS}
        base.update({"序号": i, "标题": it["title"], "发布部门": it["dept_full"],
                     "部门级别": it["level"], "政策类别": it["category"],
                     "发布日期": it["date"], "关键词标签": it["tags"],
                     "原文链接": it["url"], "正文已抓": "否", "附件路径": "",
                     "要素已解析": "否", "解析状态": "未解析", "解析置信度": 0.0,
                     "解析备注": "尚未获取正文", "采集时间": now, "处理状态": "未处理",
                     "政策状态": "有效", "失效原因": ""})
        ws.append([base[f] for f in POLICY_FIELDS])
    wb.save(XLSX_PATH)


# ===========================================================================
# 内容获取(阶段2a): 正文 + 附件
# ===========================================================================
CONTENT_SELECTORS = [
    ("div", {"class": re.compile(r'article|content|detail|TRS_Editor|news_txt|text', re.I)}),
    ("div", {"id": re.compile(r'article|content|detail|news|main|text', re.I)}),
    ("div", {"class": re.compile(r'con|body|view|info', re.I)}),
]

def extract_main_text(soup):
    best, best_len = "", 0
    for tag, attrs in CONTENT_SELECTORS:
        nodes = soup.find_all(tag, attrs)
        for n in nodes:
            t = n.get_text("\n", strip=True)
            if len(t) > best_len:
                best, best_len = t, len(t)
    if best_len > 200:
        return best
    # 兜底：去脚本样式，取 body 最大文本块
    for x in soup(["script", "style", "nav", "header", "footer"]):
        x.decompose()
    body = soup.body or soup
    text = body.get_text("\n", strip=True)
    # 按换行分段，取最长连续段落群
    paras = [p for p in text.split("\n") if len(p) > 10]
    return "\n".join(paras) if paras else text

def find_attachments(soup, base_url):
    atts = []
    for a in soup.find_all("a"):
        h = (a.get("href") or "").strip()
        if not h:
            continue
        low = urlparse(h).path.lower()
        if any(low.endswith(e) for e in ATT_EXT):
            atts.append(urljoin(base_url, h))
            continue
        txt = a.get_text(" ", strip=True)
        if ("附件" in txt or "下载" in txt) and not DATE8.search(h) and not DATESEP.search(h):
            atts.append(urljoin(base_url, h))
    # 去重保序
    seen, uniq = set(), []
    for u in atts:
        if u not in seen:
            seen.add(u); uniq.append(u)
    return uniq


def _header(headers, name):
    """兼容 requests 的大小写不敏感字典和测试替身。"""
    if not headers:
        return ""
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return str(value)
    return ""


def _content_disposition_filename(headers):
    disposition = _header(headers, "Content-Disposition")
    if not disposition:
        return ""
    # 同时支持 filename*=UTF-8''xxx 与常见 filename="xxx" 形式。
    m = re.search(r"filename\*\s*=\s*(?:UTF-8'')?([^;]+)", disposition, re.I)
    if not m:
        m = re.search(r"filename\s*=\s*\"([^\"]+)\"", disposition, re.I)
    if not m:
        m = re.search(r"filename\s*=\s*([^;]+)", disposition, re.I)
    return unquote(m.group(1).strip().strip('"')) if m else ""


def safe_filename(url, headers=None, fallback="attachment"):
    """生成不含路径穿越和 Windows 保留字符的附件名。"""
    candidate = _content_disposition_filename(headers) or os.path.basename(urlparse(url).path)
    candidate = unquote(candidate or fallback).strip().replace("\\", "_").replace("/", "_")
    candidate = re.sub(r"[\x00-\x1f\x7f]", "_", candidate)
    candidate = re.sub(r"[^0-9A-Za-z\u3400-\u9fff._()（）\- ]", "_", candidate)
    candidate = candidate.strip(" .")[:120] or fallback
    if candidate.lower() in {"con", "prn", "aux", "nul", "clock$"}:
        candidate = "_" + candidate
    return candidate


def _attachment_ext(url, headers):
    candidate = safe_filename(url, headers)
    ext = os.path.splitext(candidate)[1].lower()
    if ext in ATT_EXT:
        return ext
    ctype = _header(headers, "Content-Type").split(";", 1)[0].strip().lower()
    for known_ext, types in ATT_CONTENT_TYPES.items():
        if ctype in types:
            return known_ext
    return ""


def _read_attachment_body(response, max_bytes=MAX_ATTACHMENT_BYTES):
    """限制响应体大小；发现超限时抛出 ValueError 且不落盘。"""
    length = _header(getattr(response, "headers", {}), "Content-Length")
    try:
        if length and int(length) > max_bytes:
            raise ValueError(f"附件超过{max_bytes}字节上限")
    except ValueError as exc:
        if "上限" in str(exc):
            raise
    chunks = []
    total = 0
    iterator = getattr(response, "iter_content", None)
    if callable(iterator):
        for chunk in iterator(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"附件超过{max_bytes}字节上限")
            chunks.append(chunk)
        return b"".join(chunks)
    body = getattr(response, "content", b"") or b""
    if len(body) > max_bytes:
        raise ValueError(f"附件超过{max_bytes}字节上限")
    return body


def _attachment_failure(url, reason):
    # URL/原因写入表格时截断，避免错误页面或超长查询参数污染主表。
    return f"{url[:180]} ({str(reason)[:120]})"


def _safe_record_id(row):
    raw = str(row.get("序号") or "").strip()
    if raw:
        cleaned = re.sub(r"[^0-9A-Za-z_-]", "_", raw)[:64]
        if cleaned:
            return cleaned
    source = str(row.get("原文链接") or row.get("标题") or "policy")
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _unique_path(directory, filename):
    """同名附件不覆盖，稳定追加序号。"""
    candidate = os.path.join(directory, filename)
    if not os.path.exists(candidate):
        return candidate
    stem, ext = os.path.splitext(filename)
    index = 2
    while True:
        candidate = os.path.join(directory, f"{stem}_{index}{ext}")
        if not os.path.exists(candidate):
            return candidate
        index += 1

def fetch_content_for_row(row):
    rid = _safe_record_id(row)
    url = str(row.get("原文链接", "")).strip()
    if not url or urlparse(url).scheme.lower() not in ("http", "https"):
        return None
    r, txt = fetch(url)
    if not r:
        return {"ok": False, "err": txt}
    soup = BeautifulSoup(txt, "lxml")
    text = extract_main_text(soup)
    cpath = os.path.join(CONTENT_DIR, f"{rid}.txt")
    with open(cpath, "w", encoding="utf-8") as f:
        f.write(text)
    atts = find_attachments(soup, r.url)
    adir = os.path.join(ATTACH_DIR, rid)
    saved = []
    failures = []
    if len(atts) > MAX_ATTACHMENTS_PER_POLICY:
        failures.append(f"附件数量超过{MAX_ATTACHMENTS_PER_POLICY}个上限，已截断")
    if atts:
        os.makedirs(adir, exist_ok=True)
        for i, au in enumerate(atts[:MAX_ATTACHMENTS_PER_POLICY], 1):
            try:
                if urlparse(au).scheme.lower() not in ("http", "https"):
                    failures.append(_attachment_failure(au, "仅允许 HTTP/HTTPS 附件"))
                    continue
                ar = requests.get(au, headers=HEADERS, timeout=TIMEOUT,
                                  stream=True, verify=True)
                if ar.status_code != 200:
                    failures.append(_attachment_failure(au, f"HTTP {ar.status_code}"))
                    continue
                ext = _attachment_ext(au, getattr(ar, "headers", {}))
                if not ext:
                    failures.append(_attachment_failure(au, "文件类型不在允许列表"))
                    continue
                ctype = _header(getattr(ar, "headers", {}), "Content-Type").split(";", 1)[0].strip().lower()
                if ctype and ctype not in ALLOWED_GENERIC_CONTENT_TYPES and ctype not in ATT_CONTENT_TYPES.get(ext, set()):
                    failures.append(_attachment_failure(au, f"Content-Type与{ext}不匹配"))
                    continue
                body = _read_attachment_body(ar)
                if len(body) < 1:
                    failures.append(_attachment_failure(au, "空文件"))
                    continue
                fn = safe_filename(au, getattr(ar, "headers", {}), fallback=f"att{i}{ext}")
                if os.path.splitext(fn)[1].lower() not in ATT_EXT:
                    fn += ext
                fp = _unique_path(adir, fn)
                with open(fp, "wb") as handle:
                    handle.write(body)
                saved.append(fp)
            except Exception as exc:
                failures.append(_attachment_failure(au, exc))
    return {"ok": True, "content_path": cpath, "attach_dir": adir if saved else "",
            "n_attach": len(saved), "attachment_failures": failures[:10]}

def fetch_content():
    rows = _read_rows()
    todo = [r for r in rows if str(r.get("正文已抓", "")).strip() != "是"
            and policy_is_active(r)]
    print(f"  需抓正文: {len(todo)} 条 (总 {len(rows)} 条)")
    done, failed = 0, 0
    ok = {}  # 原文链接 -> 抓取结果(仅成功的)
    for r in todo:
        res = fetch_content_for_row(r)
        if res and res.get("ok"):
            done += 1
            ok[str(r.get("原文链接", "")).strip()] = res
        else:
            failed += 1
        if done % 10 == 0:
            print(f"    已抓 {done}/{len(todo)}")
    # 只给抓取成功的记录置"正文已抓=是"，失败的留待下次重试
    for r in rows:
        u = str(r.get("原文链接", "")).strip()
        if u in ok:
            r["正文已抓"] = "是"
            if ok[u].get("attach_dir"):
                r["附件路径"] = ok[u]["attach_dir"]
            failures = ok[u].get("attachment_failures") or []
            r["附件下载失败"] = "；".join(failures)[:1200]
    _write_rows(rows)
    print(f"  本轮抓取完成: 成功 {done} 条, 失败 {failed} 条(次日重试)")
    return done


# ===========================================================================
# 门槛解析(阶段2b)
# ===========================================================================
THRESHOLD_PATTERNS = {
    "资质要求": r'(?:高新技术企业|高企|专精特新|单项冠军|瞪羚|科技型中小企业|创新型中小企业|国家知识产权|规模以上|规上)[^。\n]{0,40}',
    "规模要求": r'(?:年营业收入|营业收入|年产值|产值|年销售额|从业人员|职工人数|员工人数|规模(?:以上|以下)|营收(?:不低于|超过|达到)|销售额(?:不低于|超过))[^。\n]{0,40}',
    "财务要求": r'(?:纳税|缴纳税收|利润总额|净利润|研发费用|研发投入|上规|升规)[^。\n]{0,40}',
    "社保要求": r'(?:社保|参保|缴纳社会保险|社会保险)[^。\n]{0,40}',
    "人才要求": r'(?:博士|硕士|海归|留学|高层次人才|高级工程师|高工|技能人才|技师|博士后|研发人员|本科以上)[^。\n]{0,40}',
    "行业要求": r'(?:行业|产业|领域)(?:为|限于|包括|涵盖|属)[^。\n]{0,40}',
    "地域要求": r'(?:注册(?:地|地址)|登记注册地|依法登记|在(?:湖北省|武汉市|东湖高新)[^。\n]{0,12}注册|(?:湖北省|武汉市|东湖高新)[^。\n]{0,12}(?:辖区内|行政区域内|范围内))[^。\n]{0,40}',
    "申报材料": r'(?:申报材料|材料清单|需(?:提交|提供)|提供以下材料|须提供)[^。\n]{0,80}',
    "支持额度": r'(?:支持额度|补助标准|奖励标准|补贴标准|最高(?:不|可)?(?:超过|补助|奖励|补贴)|不超过\s*\d+\s*(?:万|亿)|给予\s*\d+\s*(?:万|亿))[^。\n]{0,40}',
    "申报对象": r'(?:申报对象|支持对象|申报主体|适用对象|扶持对象)[^。\n]{0,60}',
}

def parse_thresholds(text):
    out = {}
    for field, pat in THRESHOLD_PATTERNS.items():
        ms = re.findall(pat, text)
        if ms:
            out[field] = "；".join(sorted(set(m.strip('；。，, ') for m in ms)))[:400]
    # 截止日期
    m = re.search(r'(截止日期|申报截止|受理截止|申报时间|截止时间|报名截止)[^。\n]{0,40}?'
                  r'(\d{4}\s*[-年./]\s*\d{1,2}\s*[-月./]\s*\d{1,2}|20\d{6})', text)
    if m:
        out["申报截止"] = _norm_date(m.group(2))
    return out

def _norm_date(s):
    s = s.replace(" ", "")
    m = re.match(r'(\d{4})[-年./](\d{1,2})[-月./](\d{1,2})', s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r'(\d{4})(\d{2})(\d{2})', s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return s

PARSED_ELEMENT_FIELDS = ("资质要求", "规模要求", "财务要求", "社保要求", "人才要求",
                         "行业要求", "地域要求", "申报材料", "支持额度", "申报对象", "申报截止")


def _parse_result_meta(text, extracted):
    """为旧的“要素已解析”字段提供不破坏兼容性的细化状态。"""
    if not text.strip():
        return "信息不足", 0.0, "正文为空，需重新获取正文或人工查看附件"
    if not extracted:
        return "待人工", 0.1, "自动抽取未命中申报要素，需人工核对正文及附件"
    gate_count = sum(1 for field in ("资质要求", "规模要求", "财务要求", "社保要求",
                                     "人才要求", "行业要求", "地域要求", "申报对象")
                     if extracted.get(field))
    # 抽取越多只代表线索更充分，不能等同于条款已完成法律意义上的确认。
    confidence = min(0.95, round(0.35 + 0.08 * len(extracted), 2))
    missing = [field for field in ("申报截止", "申报对象") if not extracted.get(field)]
    remark = "自动抽取完成，仍需人工核验原文"
    if not gate_count:
        return "待人工", min(confidence, 0.3), "仅抽取到非门槛信息，需人工确认适用主体"
    if missing:
        remark += "；未识别：" + "、".join(missing)
    return "已解析", confidence, remark


def parse_thresholds_stage(reparse=False):
    rows = _read_rows()
    todo = [r for r in rows if str(r.get("正文已抓", "")).strip() == "是"
            and (reparse or (str(r.get("要素已解析", "")).strip() != "是"
                             and str(r.get("解析状态", "")).strip() in ("", "未解析")))]
    print(f"  需解析门槛: {len(todo)} 条")
    done = 0
    for r in todo:
        rid = str(r.get("序号") or "").strip()
        cpath = os.path.join(CONTENT_DIR, f"{rid}.txt")
        if not os.path.exists(cpath):
            r["要素已解析"] = "否"
            r["解析状态"] = "信息不足"
            r["解析置信度"] = 0.0
            r["解析备注"] = "正文文件不存在，需重新获取正文或人工查看原文"
            continue
        with open(cpath, "r", encoding="utf-8") as f:
            text = f.read()
        th = parse_thresholds(text)
        if reparse:
            # 重新解析前清掉上次的自动值；人工备注和处理状态不在此列。
            for field in PARSED_ELEMENT_FIELDS:
                r[field] = ""
        for k, v in th.items():
            r[k] = v
        status, confidence, remark = _parse_result_meta(text, th)
        r["解析状态"] = status
        r["解析置信度"] = confidence
        r["解析备注"] = remark
        # 旧字段仅表达“自动解析完成”，细化状态以解析状态为准。
        r["要素已解析"] = "是" if status == "已解析" else "否"
        done += 1
    # 每日重算全部存量记录；昨天仍有效的政策可能今天刚好过截止日。
    for r in rows:
        rid = str(r.get("序号") or "").strip()
        text = ""
        cpath = os.path.join(CONTENT_DIR, f"{rid}.txt")
        if os.path.exists(cpath):
            with open(cpath, "r", encoding="utf-8") as handle:
                text = handle.read()
        state, reason = policy_status(r, text=text)
        r["政策状态"] = state
        r["失效原因"] = reason
    _write_rows(rows)
    print(f"  本轮解析完成: {done} 条")
    return done


# ===========================================================================
# xlsx 读写工具
# ===========================================================================
def _read_rows():
    if not os.path.exists(XLSX_PATH):
        return []
    wb = openpyxl.load_workbook(XLSX_PATH)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    hdr = list(rows[0])
    out = []
    for r in rows[1:]:
        out.append({hdr[i]: ("" if (i >= len(r) or r[i] is None) else r[i])
                     for i in range(len(hdr))})
    return out

def _write_rows(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(POLICY_FIELDS))
    for r in rows:
        ws.append([r.get(f, "") for f in POLICY_FIELDS])
    wb.save(XLSX_PATH)

def _apply_flag(all_rows, target_rows, flag_field, value):
    keys = {str(r.get("原文链接", "")).strip() for r in target_rows}
    for r in all_rows:
        if str(r.get("原文链接", "")).strip() in keys:
            r[flag_field] = value
    _write_rows(all_rows)


# ===========================================================================
# 每日报告
# ===========================================================================
def write_daily_digest():
    """每日报告：凡「采集时间=今天」的政策都算今日新增（约等于过去24小时），
    同一天重复运行不会把早间新增冲掉；报告附带申报要素（方向/对象/额度/截止）。"""
    rows = _read_rows()
    today = datetime.date.today().strftime("%Y-%m-%d")
    todays = [r for r in rows if str(r.get("采集时间", "")).startswith(today)
              and policy_is_active(r)]
    lines = [f"# 武汉/湖北企业补贴政策 · 每日报告（{today}）", ""]
    report_path = os.path.join(DATA_DIR, "collection_report.json")
    if os.path.exists(report_path):
        with open(report_path, encoding="utf-8") as handle:
            sources = json.load(handle)
        warnings = [s for s in sources.get("sources", []) if s.get("status") != "ok" or s.get("warning")]
        if warnings:
            lines += ["## 采集状态", ""]
            lines += [f"- {s['name']}：" + ("采集失败，本次结果不完整" if s.get("status") != "ok" else s["warning"]) for s in warnings]
            lines.append("")
    if not todays:
        lines += ["今日无新增政策（或均已入库）。", ""]
    else:
        lines += [f"今日新增 **{len(todays)}** 条，累计存档 {len(rows)} 条。",
                  "", "## 按部门分组", ""]
        by_dept = {}
        for r in todays:
            by_dept.setdefault(str(r.get("发布部门", "")), []).append(r)
        for dept, items in by_dept.items():
            lines += [f"### {dept}", ""]
            for r in items:
                lines.append(f"- **[{r.get('发布日期', '')}] {r.get('标题', '')}**  ")
                lines.append(f"  - 类别/方向: `{r.get('政策类别', '')}` / 标签: {r.get('关键词标签', '')}")
                for label in ("申报对象", "支持额度", "申报截止"):
                    v = str(r.get(label, "")).strip()
                    if v:
                        lines.append(f"  - {label}: {v}")
                lines.append(f"  - 原文: {r.get('原文链接', '')}")
                lines.append("")
        lines += ["## 下一步", "",
                  "1. 核对“申报截止/是否匹配/处理状态”三列。",
                  "2. 各企业符合与否见下方「企业匹配」一节（由匹配引擎生成）。", ""]
    with open(DIGEST_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ===========================================================================
def main():
    args = sys.argv[1:]
    do_collect = "--collect" in args
    do_content = "--content" in args
    do_parse = "--parse-thresholds" in args
    reparse = "--reparse" in args
    dry = "--dry" in args
    if reparse:
        do_parse = True
    if not (do_collect or do_content or do_parse):
        do_collect = do_content = do_parse = True
    print(f"== 企业补贴政策采集器 v2 == {datetime.date.today()} | data_dir={DATA_DIR}")
    if do_collect:
        print("[阶段1] 采集 ...")
        collect(dry=dry)
    if do_content:
        print("[阶段2a] 内容获取 ...")
        fetch_content()
    if do_parse:
        print("[阶段2b] 门槛解析 ...")
        parse_thresholds_stage(reparse=reparse)
    if do_collect and not dry:
        write_daily_digest()
        print(f"  摘要: {DIGEST_PATH}")
    print("完成。")

if __name__ == "__main__":
    main()
