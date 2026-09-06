# -*- coding: utf-8 -*-
"""提取参考 Word 首页样式，或导出可复用的封面模板。"""
from __future__ import annotations

import argparse
import json
import sys

from cover_template import extract_cover_style, save_reference_cover_template

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", help="参考 .doc/.docx 文件")
    parser.add_argument("--out", help="封面样式报告 JSON")
    parser.add_argument("--template", help="另存仅含参考封面的 .docx 模板")
    args = parser.parse_args()

    report = extract_cover_style(args.reference, args.out)
    if args.template:
        report["template"] = save_reference_cover_template(args.reference, args.template)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
