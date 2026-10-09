"""
INPUT: 目标目录；规则文档与模板的来源——安装包里是 <本技能目录>/references/workspace/，在 VideoCut 仓库里直接用仓库根目录
OUTPUT: 命令 init_workspace.py <目标目录> [--article-library <目录>]：写 videocut.workspace.json 标记、建 projects/，
        复制 AGENTS.md、CLAUDE.md、WORKFLOW.md、README.md、docs/、templates/、.env.example、.gitignore；已有文件一律不覆盖
POS: 新工作区的唯一初始化入口。技能装在工作区外时靠标记文件找到工作区（见各技能的 workspace.py），所以先建工作区再用其他技能。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
MARKER = "videocut.workspace.json"
# 复制到新工作区的规则文档与模板（相对来源目录）；docs 与 templates 整个目录复制
WORKSPACE_FILES = ("AGENTS.md", "CLAUDE.md", "WORKFLOW.md", "README.md", ".env.example", ".gitignore")
WORKSPACE_DIRS = ("docs", "templates")


def source_root() -> Path:
    """安装包里用 references/workspace；在 VideoCut 仓库里（.claude/skills/video-workflow）直接用仓库根目录。"""
    packaged = SKILL_ROOT / "references" / "workspace"
    if (packaged / "AGENTS.md").is_file():
        return packaged
    repository = SKILL_ROOT.parents[2]
    if (repository / MARKER).is_file() and (repository / "AGENTS.md").is_file():
        return repository
    raise SystemExit(f"[失败] 找不到规则文档来源：{packaged} 不完整，且本技能不在 VideoCut 仓库里")


def _copy_new(source: Path, target: Path, created: list[str], skipped: list[str]) -> None:
    if target.exists():
        skipped.append(str(target))
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    created.append(str(target))


def init_workspace(target: Path, article_library: str | None) -> dict[str, list[str]]:
    source = source_root()
    target.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    skipped: list[str] = []
    for name in WORKSPACE_FILES:
        if (source / name).is_file():
            _copy_new(source / name, target / name, created, skipped)
    for folder in WORKSPACE_DIRS:
        for path in sorted((source / folder).rglob("*")):
            if path.is_file():
                _copy_new(path, target / path.relative_to(source), created, skipped)
    (target / "projects").mkdir(exist_ok=True)
    marker = target / MARKER
    if marker.exists():
        skipped.append(str(marker))
    else:
        config = {
            "schema_version": "1.0",
            "name": target.name,
            "description": "VideoCut 视频工作流的工作区标记：技能据此找到 .env、projects/、logs/（付费接口用量账本）与 .cache/。不要删除或移动。",
            # 公众号文章素材库（只读引用）；没有就留 null，改编文章时由用户直接给路径
            "article_library": article_library,
        }
        marker.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        created.append(str(marker))
    return {"created": created, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="初始化 VideoCut 工作区（已有文件不覆盖）")
    parser.add_argument("target", help="工作区目录，不存在会创建")
    parser.add_argument("--article-library", help="公众号文章素材库目录（只读引用），写入 videocut.workspace.json")
    args = parser.parse_args(argv)
    result = init_workspace(Path(args.target).resolve(), args.article_library)
    print(f"新建 {len(result['created'])} 个文件，跳过已有 {len(result['skipped'])} 个 -> {Path(args.target).resolve()}")
    print("下一步：复制 .env.example 为 .env 填密钥；在 remotion-render 技能目录 npm ci && npm run setup:fonts；运行 sfx_kit.py build；跑各计费技能的 check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
