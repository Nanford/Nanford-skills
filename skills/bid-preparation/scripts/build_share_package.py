"""Build desensitized share package under dist/.

INPUT: repo root (default: parent of bid-preparation/), current bid-preparation skill tree.
OUTPUT: dist/bid-preparation-skill/ (cleaned copy) + dist/bid-preparation-skill-vX.Y.zip
POS: Release helper — 分享包不含招标文件、公司资料、bid-projects 实例。
"""

from __future__ import annotations

import argparse
import re
import shutil
import zipfile
from pathlib import Path


SKIP_DIR_NAMES = {"__pycache__", ".git", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def detect_version(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    # 无显式版本时用默认；可在 SKILL  front matter 或注释中写 version: x.y
    match = re.search(r"version:\s*([0-9]+\.[0-9]+)", text, re.I)
    if match:
        return match.group(1)
    return "1.8"


def copy_skill_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            path = Path(directory) / name
            if name in SKIP_DIR_NAMES or path.suffix in SKIP_SUFFIXES:
                ignored.add(name)
        return ignored

    shutil.copytree(src, dst / "bid-preparation", ignore=ignore)


def write_skeleton_dirs(package_root: Path, repo_root: Path) -> None:
    """复制脱敏骨架：company-library README、招标文件/响应目录 README、bid-projects README。"""
    pairs = [
        ("company-library", "company-library"),
        ("招标文件", "招标文件"),
        ("响应投标文件", "响应投标文件"),
        ("bid-projects", "bid-projects"),
    ]
    for rel_src, rel_dst in pairs:
        src = repo_root / rel_src
        dst = package_root / rel_dst
        if not src.exists():
            dst.mkdir(parents=True, exist_ok=True)
            (dst / "README.md").write_text(f"# {rel_dst}\n\n（骨架目录）\n", encoding="utf-8")
            continue
        if dst.exists():
            shutil.rmtree(dst)
        # 只复制 md/txt 说明，不复制 pdf/docx 等大体量或敏感文件
        dst.mkdir(parents=True, exist_ok=True)

        def ignore(directory: str, names: list[str]) -> set[str]:
            ignored = set()
            for name in names:
                path = Path(directory) / name
                if name in SKIP_DIR_NAMES:
                    ignored.add(name)
                    continue
                if path.is_file():
                    lower = name.lower()
                    if not lower.endswith((".md", ".txt")):
                        ignored.add(name)
            return ignored

        # copytree into temp then move — simpler: walk
        for path in src.rglob("*"):
            rel = path.relative_to(src)
            if any(part in SKIP_DIR_NAMES for part in rel.parts):
                continue
            if path.is_dir():
                (dst / rel).mkdir(parents=True, exist_ok=True)
            elif path.suffix.lower() in {".md", ".txt"}:
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)


def write_package_readme(package_root: Path, version: str) -> None:
    content = f"""# bid-preparation - 标书响应文件制作 Skill（分享包 v{version}）

`bid-preparation` 是一个通用 Agent Skill：解析招标文件 → 匹配公司资料 → 按流程生成商务+技术响应文件 → 组装成品 DOCX → 合规审查。

适用于 Claude Code、Codex、Grok 等支持 Agent Skills 规范（SKILL.md + scripts/ + references/ + templates/）的工具。

## 包内容

```
bid-preparation-skill/
├── README.md                 ← 本文件
├── bid-preparation/          ← Skill 本体（复制到 Agent skills 目录）
├── company-library/          ← 公司资料库骨架（按 README 放入自己的扫描件）
├── 招标文件/                 ← 放待投招标文件
├── 响应投标文件/             ← 可选格式样本
└── bid-projects/             ← 项目工作目录（脚本自动创建）
```

**分享包不含任何实际公司资料、招标正文与投标报价。**

## 安装

1. 将 `bid-preparation/` 复制到 `~/.claude/skills/bid-preparation/`（或其他 Agent 的 skills 目录）
2. `pip install -r bid-preparation/requirements.txt`
3. 填写 `company-library/company-profile.md` 并按子目录 README 放入资料

## 核心能力（v{version}）

- 阶段 0–7 工作流 + 断点续作（`project_status.py`）
- 写作闸：大纲确认 → 逐章确认
- P0 门禁：提取硬停、硬参数、格式克隆、★三角、空库禁写
- P1 路由：项目类型（六类）、电子标清单、多现场/安全、机械得分策略
- P2 质量：章内深度与覆盖率（`check_content_quality.py`）
- **P3 采购路由**：
  - 采购体系 `gov`/`enterprise`——政府采购**价格扣除测算**（中小企业/监狱企业/残疾人福利性单位）、
    强制采购节能产品、政采信用三平台、资格三段式
  - 采购方式招标/**竞争性磋商**/谈判/询价——两阶段报价策略、术语一致性扫描
  - 定标方式 `standard`/**评定分离**——投标文件双分册（评标部分+定标部分）、定标因素、答辩预案
  - 工程总承包 `construction_epc` 写作骨架、人证绑定资格清单、联合体协议分工
- DOCX 成稿与格式校验；页码脚本兼容 **Word / WPS**

## 快速开始

```powershell
python -X utf8 bid-preparation/scripts/prepare_project.py `
  --root "<工作区>" --project-name "示例项目" `
  --tender "<工作区>/招标文件/xxx.pdf" `
  --materials "<工作区>/company-library" `
  --scope full `
  --procurement-system unset --procurement-mode unset --award-mode unset `
  --project-type unset --delivery-mode unset
```

对话中说明招标文件路径与「做标书/解标」即可触发 Skill。详见 Skill 内 `SKILL.md` 与各 `references/stage-*.md`。
"""
    (package_root / "README.md").write_text(content, encoding="utf-8")


def zip_package(package_root: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in package_root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(package_root.parent).as_posix())


def build_share_package(repo_root: Path, version: str | None = None) -> dict:
    repo_root = repo_root.expanduser().resolve()
    skill_src = repo_root / "bid-preparation"
    if not skill_src.is_dir():
        raise SystemExit(f"未找到 Skill 目录: {skill_src}")
    ver = version or detect_version(skill_src / "SKILL.md")
    dist_dir = repo_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    package_root = dist_dir / "bid-preparation-skill"
    copy_skill_tree(skill_src, package_root)
    write_skeleton_dirs(package_root, repo_root)
    write_package_readme(package_root, ver)
    zip_path = dist_dir / f"bid-preparation-skill-v{ver}.zip"
    zip_package(package_root, zip_path)
    return {
        "version": ver,
        "package_dir": str(package_root),
        "zip": str(zip_path),
        "skill_files": sum(1 for _ in (package_root / "bid-preparation").rglob("*") if _.is_file()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build desensitized bid-preparation share package.")
    parser.add_argument("--root", type=Path, default=None, help="Repo root (default: parent of scripts/../..)")
    parser.add_argument("--version", default=None, help="Package version label, e.g. 1.5")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.root is None:
        # scripts/ -> bid-preparation/ -> repo
        args.root = Path(__file__).resolve().parents[2]
    result = build_share_package(args.root, version=args.version)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
