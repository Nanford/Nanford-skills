#!/usr/bin/env python3
"""
Listing 合规与规格质检。

这里放的都是有确定答案的检查：字符数、条数、禁用词、图片像素、宽高比、
文件大小、格式。模型判断这些东西每次结果都可能不同，脚本不会。

用法：
    python validate.py --copy copy.json --site amazon-US
    python validate.py --images ./final/ --site amazon-US
    python validate.py --copy copy.json --images ./final/ --site amazon-US --json

退出码：0 表示无阻断级问题，1 表示存在阻断级问题。
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "..", "assets", "site_rules.json")

BLOCK = "block"
WARN = "warn"
INFO = "info"


def load_rules():
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def issue(level, where, message, fix=None):
    return {"level": level, "where": where, "message": message, "fix": fix}


# --------------------------------------------------------------------------
# 文案检查
# --------------------------------------------------------------------------

def check_copy(copy_data, site_cfg, rules):
    out = []
    platform = site_cfg["platform"]
    banned = list(rules.get("banned_terms_global", []))
    banned += rules.get("banned_terms_platform", {}).get(platform, [])

    title = copy_data.get("title", "") or ""
    if title:
        limit = site_cfg.get("title_max_chars", 0)
        if limit and len(title) > limit:
            out.append(issue(
                BLOCK, "title",
                "标题 %d 字符，超出 %s 上限 %d" % (len(title), site_cfg_name(site_cfg), limit),
                "砍掉长尾修饰，保留核心产品词和最重要的两三个属性"))
        if title.isupper():
            out.append(issue(WARN, "title", "标题全大写，多数平台判定为格式违规"))

    bullets = copy_data.get("bullets", []) or []
    want = site_cfg.get("bullet_count", 5)
    if bullets and len(bullets) != want:
        out.append(issue(WARN, "bullets", "五点描述有 %d 条，站点期望 %d 条" % (len(bullets), want)))

    b_limit = site_cfg.get("bullet_max_chars", 0)
    soft = int(b_limit * 0.8) if b_limit else 0
    for i, b in enumerate(bullets, 1):
        n = len(b)
        if b_limit and n > b_limit:
            out.append(issue(
                BLOCK, "bullet%d" % i,
                "第 %d 条 %d 字符，超出上限 %d" % (i, n, b_limit),
                "压缩支撑说明部分，抓手短语保留"))
        elif soft and n > soft:
            out.append(issue(
                INFO, "bullet%d" % i,
                "第 %d 条 %d 字符，接近上限 %d，移动端可能被折叠" % (i, n, b_limit)))
        if b.isupper() and not site_cfg.get("allow_all_caps_bullet", False):
            out.append(issue(BLOCK, "bullet%d" % i, "第 %d 条整条大写" % i,
                             "只保留开头抓手短语大写"))

    desc = copy_data.get("description", "") or ""
    d_limit = site_cfg.get("description_max_chars", 0)
    if d_limit and len(desc) > d_limit:
        out.append(issue(BLOCK, "description",
                         "长描述 %d 字符，超出上限 %d" % (len(desc), d_limit)))

    st = copy_data.get("search_terms", "") or ""
    st_limit = site_cfg.get("search_terms_max_bytes", 0)
    if st_limit:
        nbytes = len(st.encode("utf-8"))
        if nbytes > st_limit:
            out.append(issue(BLOCK, "search_terms",
                             "搜索词 %d 字节，超出上限 %d 字节（注意是字节不是字符）"
                             % (nbytes, st_limit)))

    # 禁用词扫描：整份文案一起扫，定位到具体字段
    fields = {"title": title, "description": desc, "search_terms": st}
    for i, b in enumerate(bullets, 1):
        fields["bullet%d" % i] = b
    for where, text in fields.items():
        if not text:
            continue
        low = text.lower()
        for term in banned:
            t = term.lower()
            pattern = r"\b%s\b" % re.escape(t) if re.match(r"^[a-z0-9 .#]+$", t) else re.escape(t)
            if re.search(pattern, low):
                out.append(issue(BLOCK, where, "命中禁用词：%s" % term,
                                 "改写为可验证的具体表述"))

    # 卖点维度覆盖度：五条都讲同一维度是最常见的失败模式
    dims = copy_data.get("bullet_dimensions", [])
    if dims and len(set(dims)) < 3:
        out.append(issue(WARN, "bullets",
                         "五点描述只覆盖 %d 个维度，建议覆盖核心功能、材质工艺、"
                         "使用场景、规格兼容、配件售后中的至少三类" % len(set(dims))))

    excluded = copy_data.get("excluded_points", [])
    if excluded:
        out.append(issue(INFO, "excluded_points",
                         "有 %d 条卖点因属性待确认被排除，补齐后可以拿回" % len(excluded)))
    return out


def site_cfg_name(site_cfg):
    return site_cfg.get("_name", "该站点")


def check_pending_claims(listing_data, copy_data, jobs_data):
    """Block unconfirmed product facts that leak into public copy or image text."""
    out = []
    public_parts = [json.dumps(copy_data or {}, ensure_ascii=False)]
    for job in (jobs_data or {}).get("jobs", []):
        public_parts.append(str(job.get("base_prompt", "")))
        public_parts.extend(str(layer.get("text", "")) for layer in job.get("text_layers", []))
    public_text = "\n".join(public_parts).casefold()

    candidates = []
    for item in (listing_data or {}).get("attributes", []):
        if item.get("needs_confirmation"):
            candidates.append(("attribute.%s" % item.get("key", "unknown"), item.get("value")))
    for item in (listing_data or {}).get("selling_points", []):
        if item.get("needs_confirmation"):
            candidates.append(("selling_point.%s.short" % item.get("id", "unknown"), item.get("short")))
            candidates.append(("selling_point.%s.full" % item.get("id", "unknown"), item.get("full")))

    for source, value in candidates:
        normalized = str(value or "").strip().casefold()
        if len(normalized) >= 2 and normalized in public_text:
            out.append(issue(
                BLOCK,
                source,
                "待确认事实出现在公开文案或出图工单中：%s" % value,
                "先由用户确认并更新 listing.json，或从下游内容删除该事实",
            ))
    return out


def check_jobs(jobs_data, image_dir=None):
    out = []
    jobs = (jobs_data or {}).get("jobs", [])
    if len(jobs) < 7:
        out.append(issue(BLOCK, "image_jobs", "套图仅 %d 张，低于 7 张交付门槛" % len(jobs)))

    ids = [str(job.get("id", "")) for job in jobs]
    duplicates = sorted({job_id for job_id in ids if ids.count(job_id) > 1})
    if duplicates:
        out.append(issue(BLOCK, "image_jobs", "任务 ID 重复：%s" % ", ".join(duplicates)))

    final_names = os.listdir(image_dir) if image_dir and os.path.isdir(image_dir) else []
    for job in jobs:
        job_id = str(job.get("id", ""))
        if not job_id:
            out.append(issue(BLOCK, "image_jobs", "存在缺少 id 的出图任务"))
            continue
        prompt = str(job.get("base_prompt", ""))
        if "no text" not in prompt.lower() and "无文字" not in prompt:
            out.append(issue(WARN, job_id, "底图提示词缺少无文字约束"))
        if job.get("type") == "main" and job.get("text_layers"):
            out.append(issue(BLOCK, job_id, "主图包含文字图层"))
        for index, layer in enumerate(job.get("text_layers", []), 1):
            box = layer.get("box")
            if box is not None and (
                not isinstance(box, list)
                or len(box) != 4
                or any(not isinstance(value, (int, float)) or value < 0 or value > 1 for value in box)
                or box[2] <= box[0]
                or box[3] <= box[1]
            ):
                out.append(issue(BLOCK, "%s.text_layer%d" % (job_id, index), "文字框 box 无效"))
        if final_names and not any(name.startswith(job_id) for name in final_names):
            out.append(issue(BLOCK, job_id, "成品图目录中找不到对应文件"))
    return out


# --------------------------------------------------------------------------
# 图片检查
# --------------------------------------------------------------------------

def check_images(image_dir, site_cfg):
    out = []
    img_cfg = site_cfg.get("image", {})
    try:
        from PIL import Image
    except ImportError:
        out.append(issue(WARN, "images",
                         "未安装 Pillow，跳过图片检查。安装：pip install Pillow"))
        return out

    files = sorted(
        f for f in os.listdir(image_dir)
        if os.path.splitext(f)[1].lower().lstrip(".") in
        ("jpg", "jpeg", "png", "tiff", "gif", "webp")
    )
    if not files:
        out.append(issue(BLOCK, "images", "目录中没有找到图片：%s" % image_dir))
        return out

    max_count = img_cfg.get("max_count", 0)
    if max_count and len(files) > max_count:
        out.append(issue(WARN, "images",
                         "共 %d 张图，超出站点上限 %d 张" % (len(files), max_count)))

    allowed_fmt = [x.lower() for x in img_cfg.get("formats", [])]
    ratios = img_cfg.get("aspect_ratios", [])

    for fn in files:
        path = os.path.join(image_dir, fn)
        ext = os.path.splitext(fn)[1].lower().lstrip(".")
        is_main = "main" in fn.lower() or fn.startswith("01")

        if allowed_fmt and ext not in allowed_fmt:
            out.append(issue(BLOCK, fn, "格式 %s 不在站点允许列表 %s 内"
                             % (ext, "/".join(allowed_fmt))))

        mb = os.path.getsize(path) / 1024.0 / 1024.0
        max_mb = img_cfg.get("max_file_mb", 0)
        if max_mb and mb > max_mb:
            out.append(issue(BLOCK, fn, "文件 %.1fMB，超出上限 %dMB" % (mb, max_mb),
                             "降低 JPEG 质量或缩小尺寸"))

        with Image.open(path) as im:
            w, h = im.size
            longest = max(w, h)
            if longest < img_cfg.get("min_longest_side", 0):
                out.append(issue(BLOCK, fn,
                                 "最长边 %dpx，低于站点下限 %dpx"
                                 % (longest, img_cfg["min_longest_side"]),
                                 "重新出图或用更高分辨率的原图"))
            elif longest < img_cfg.get("recommended_longest_side", 0):
                out.append(issue(INFO, fn,
                                 "最长边 %dpx，低于推荐值 %dpx，缩放体验会受影响"
                                 % (longest, img_cfg["recommended_longest_side"])))
            if img_cfg.get("max_longest_side") and longest > img_cfg["max_longest_side"]:
                out.append(issue(BLOCK, fn, "最长边 %dpx 超出上限" % longest))

            if ratios and not ratio_ok(w, h, ratios):
                out.append(issue(WARN, fn, "宽高比 %d:%d 不在站点建议比例 %s 内"
                                 % (w, h, "/".join(ratios))))

            if is_main and img_cfg.get("main_bg") == "white":
                if not corners_white(im):
                    out.append(issue(BLOCK, fn,
                                     "主图四角非纯白，不符合白底要求",
                                     "用抠图后的透明底图重新合成白底"))
    if not any(("main" in f.lower() or f.startswith("01")) for f in files):
        out.append(issue(WARN, "images",
                         "未识别到主图。建议主图文件名包含 main 或以 01 开头"))
    return out


def ratio_ok(w, h, ratios, tol=0.02):
    actual = w / float(h)
    for r in ratios:
        a, b = r.split(":")
        if abs(actual - float(a) / float(b)) <= tol:
            return True
    return False


def corners_white(im, tol=6, sample=12):
    im = im.convert("RGB")
    w, h = im.size
    boxes = [(0, 0), (w - sample, 0), (0, h - sample), (w - sample, h - sample)]
    for x, y in boxes:
        region = im.crop((x, y, x + sample, y + sample))
        for px_x in range(region.width):
            for px_y in range(region.height):
                if any(c < 255 - tol for c in region.getpixel((px_x, px_y))):
                    return False
    return True


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--copy", help="copy.json 路径")
    ap.add_argument("--listing", help="listing.json 路径，用于检查待确认事实泄漏")
    ap.add_argument("--jobs", help="image_jobs.json 路径，用于检查套图结构与文字层")
    ap.add_argument("--images", help="成品图目录")
    ap.add_argument("--site", required=True, help="站点标识，如 amazon-US")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--out", help="将 JSON 报告以 UTF-8 写入指定文件")
    args = ap.parse_args()

    rules = load_rules()
    site_cfg = rules["sites"].get(args.site)
    if not site_cfg:
        print("未知站点：%s\n可用站点：%s" % (args.site, ", ".join(rules["sites"])))
        return 2
    site_cfg = dict(site_cfg, _name=args.site)

    copy_data = {}
    listing_data = {}
    jobs_data = {}
    issues = []
    if args.copy:
        with open(args.copy, encoding="utf-8") as f:
            copy_data = json.load(f)
            issues += check_copy(copy_data, site_cfg, rules)
    if args.listing:
        with open(args.listing, encoding="utf-8") as f:
            listing_data = json.load(f)
    if args.jobs:
        with open(args.jobs, encoding="utf-8") as f:
            jobs_data = json.load(f)
        issues += check_jobs(jobs_data, args.images)
    if args.listing and (args.copy or args.jobs):
        issues += check_pending_claims(listing_data, copy_data, jobs_data)
    if args.images:
        issues += check_images(args.images, site_cfg)
    if not args.copy and not args.listing and not args.jobs and not args.images:
        print("至少指定 --copy、--listing、--jobs 或 --images 其中之一")
        return 2

    blockers = [i for i in issues if i["level"] == BLOCK]

    if args.json:
        payload = {"site": args.site, "issues": issues, "blocking": len(blockers)}
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(rendered + "\n")
            print("已写出质检报告：%s" % args.out)
        else:
            print(rendered)
    else:
        label = {BLOCK: "阻断", WARN: "警告", INFO: "提示"}
        if not issues:
            print("质检通过，未发现问题。站点：%s" % args.site)
        for lv in (BLOCK, WARN, INFO):
            group = [i for i in issues if i["level"] == lv]
            if not group:
                continue
            print("\n[%s] %d 项" % (label[lv], len(group)))
            for i in group:
                print("  %-16s %s" % (i["where"], i["message"]))
                if i.get("fix"):
                    print("  %-16s 修复建议：%s" % ("", i["fix"]))
        print("\n站点 %s：阻断级问题 %d 项" % (args.site, len(blockers)))

    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
