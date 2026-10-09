"""
INPUT: 命令行参数；sfxlib 的音色配方
OUTPUT: build 生成音效库与 manifest.json；verify 校验库与当前配方一致；preview 写试听 WAV 并打印每个声音的起始时刻；list 列出动作类型与音效
POS: sfx-kit 的命令入口。只做本地计算，不联网、不计费、不读写项目清单。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sfxlib.library import build_library, build_preview, verify_library  # noqa: E402
from sfxlib.presets import KIND_TO_SOUNDS, PRESETS  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY = SKILL_ROOT / "library"


def _format_time(seconds: float) -> str:
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes):02d}:{rest:06.3f}"


def command_build(args: argparse.Namespace) -> int:
    manifest = build_library(Path(args.out_dir))
    for entry in manifest["sounds"]:
        print(f"{entry['id']:<11} {entry['kind']:<15} {entry['duration_ms']:>5} ms  峰值 {entry['peak_dbfs']:>6} dBFS")
    print(f"共 {len(manifest['sounds'])} 个音效 → {Path(args.out_dir).resolve()}")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    problems = verify_library(Path(args.out_dir))
    for problem in problems:
        print(f"[问题] {problem}")
    print("音效库与当前配方一致" if not problems else f"{len(problems)} 个问题")
    return 1 if problems else 0


def command_preview(args: argparse.Namespace) -> int:
    default_name = "preview-demo.wav" if args.demo else "preview-all.wav"
    dest = Path(args.out) if args.out else DEFAULT_LIBRARY / default_name
    sequence = build_preview(dest, demo=args.demo)
    for start, sound_id in sequence:
        print(f"{_format_time(start)}  {sound_id:<11} {PRESETS[sound_id].description}")
    print(f"试听文件：{dest.resolve()}")
    return 0


def command_list(_: argparse.Namespace) -> int:
    for kind, sound_ids in KIND_TO_SOUNDS.items():
        descriptions = "；".join(PRESETS[sound_id].description for sound_id in sound_ids[:1])
        print(f"{kind:<15} {', '.join(sound_ids):<24} {descriptions}")
    return 0


def main() -> int:
    # Windows 控制台默认 GBK，被智能体管道读取时中文会乱码；与其他技能一样统一输出 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="VideoCut 系列音效库（本地合成）")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--out-dir", default=str(DEFAULT_LIBRARY), help="音效库目录，默认技能目录下 library/")
    preview = sub.add_parser("preview")
    preview.add_argument("--demo", action="store_true", help="按示范动作序列排列（模拟一个文字动效镜头）")
    preview.add_argument("--out", help="试听 WAV 路径，默认写到 library/ 下")
    sub.add_parser("list")
    args = parser.parse_args()
    handlers = {"build": command_build, "verify": command_verify, "preview": command_preview, "list": command_list}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
