"""
INPUT: 版本目录下 timeline.json、speech.json、audio/voice.wav、audio/segments/*.mp3、可选 actions.json 与 sfx-kit 音效库；remotion-render 输出的无声画面及其 .render.json；
       项目根目录 brief.json、costs/ledger.json；ffmpeg / ffprobe
OUTPUT: 子命令
  sfx     动作标记 actions.json + sfx-kit 音效库 → audio/sfx.wav（与母轨等长的音效轨）+ audio/sfx.json（可选步骤）
  mix     人声母轨（有 sfx.json 时加上音效轨）→ audio/mix.wav（目标响度、真峰值受控）+ audio/mix.json（处理参数、测量值、来源 AIGC 标识）
  mux     无声画面 + mix.wav → exports/final-<版本>.mp4（H.264 直接复制、AAC 48 kHz、faststart）+ .export.json
  check   对最终 MP4 做自动技术检查、从成片抽帧拼总览，结果并入 qa/report.json（人工项登记为 not_checked）
  record  登记人工 / 模型审阅项的结果，必须绑定当前成片校验值
  deliver 生成 delivery.json（文件清单、三个独立状态、待检查事项、授权、成本、AIGC 标识、重渲染说明）
POS: 混音、封装、质检与交付环节的命令入口。技能本身不写 project.json，阶段登记由 video-project 完成。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

from aelib.checks import MANUAL_CHECKS, contact_sheet, extract_frames, manual_placeholders, merge_report, picture_problems, review_frame_numbers, run_automated_checks, source_aigc_labels
from aelib.delivery import build_delivery
from aelib.loudness import LoudnessTarget, level_voice
from aelib.sfx import SFX_LEVEL_DB, build_sfx_track, current_sfx, default_library
from aelib.media import MediaError, ffprobe_json, inside, local_now, read_json, relative_to, replace_atomic, run_tool, sha256_file, temp_sibling, tool_version, write_json_atomic

AAC_BITRATE = "192k"
MUSIC_NOTE = "本版本只处理人声；配乐与人声避让（sidechaincompress）在第一条带授权配乐的项目接入时实现"


def _variant_dir(text: str) -> Path:
    path = Path(text).resolve()
    if not (path / "timeline.json").is_file():
        raise MediaError(f"{path} 下没有 timeline.json，请先运行 video-timeline")
    return path


def _project_dir(variant_dir: Path) -> Path:
    # 版本目录固定为 projects/<id>/variants/<平台>
    return variant_dir.parent.parent


def command_mix(args: argparse.Namespace) -> int:
    variant_dir = _variant_dir(args.variant_dir)
    brief = read_json(_project_dir(variant_dir) / "brief.json")
    if brief.get("music", {}).get("mode", "none") != "none":
        raise MediaError(f"brief.json 要求配乐（music.mode={brief['music']['mode']}），{MUSIC_NOTE}")
    timeline = read_json(variant_dir / "timeline.json")
    voice = variant_dir / "audio" / "voice.wav"
    voice_sha = sha256_file(voice)
    if voice_sha != timeline.get("voice_audio_sha256"):
        raise MediaError("audio/voice.wav 与 timeline.json 记录的母轨不一致：配音改过后请先重跑 voice-captions 与 video-timeline")
    target = LoudnessTarget(integrated_lufs=args.target_lufs)
    sfx = current_sfx(variant_dir, timeline)
    out = variant_dir / "audio" / "mix.wav"
    temporary = temp_sibling(out)
    processing = level_voice(voice, temporary, target, variant_dir / "audio" / "sfx.wav" if sfx else None)
    after = processing["after"]["integrated_lufs"]
    if not target.accept_min_lufs <= after <= target.accept_max_lufs:
        temporary.unlink(missing_ok=True)
        raise MediaError(f"处理后响度 {after} LUFS 不在 {target.accept_min_lufs}～{target.accept_max_lufs} 之内，未替换 mix.wav")
    replace_atomic(temporary, out)
    speech = read_json(variant_dir / "speech.json")
    record = {
        "schema_version": "1.0", "variant": variant_dir.name, "created_at": local_now(),
        "input": {"path": "audio/voice.wav", "sha256": voice_sha},
        "music": {"mode": "none", "waiver_ref": brief.get("music", {}).get("waiver_ref"), "note": MUSIC_NOTE},
        "sfx": ({"mode": "track", "path": "audio/sfx.wav", "sha256": sfx["output"]["sha256"], "record_sha256": sfx["_record_sha256"], "level_db": sfx["level_db"]}
                if sfx else {"mode": "none"}),
        "processing": {"chain": "4x 过采样 → 固定增益 → alimiter 前视限幅（关闭自动电平、补偿延迟）→ 48 kHz", "target": target.as_dict(), **processing},
        "output": {"path": "audio/mix.wav", "sha256": sha256_file(out), "sample_rate": 48000, "channels": 1, "codec": "pcm_s16le"},
        "source_aigc_labels": source_aigc_labels(variant_dir, speech),
        "tool_versions": {"ffmpeg": tool_version("ffmpeg")},
    }
    write_json_atomic(variant_dir / "audio" / "mix.json", record)
    source = "人声 + 音效轨" if sfx else "人声"
    print(f"{variant_dir.name}（{source}）: {processing['before']['integrated_lufs']} → {after} LUFS，真峰值 {processing['after']['true_peak_dbtp']} dBTP，增益 {processing['final_gain_db']} dB -> {out}")
    return 0


def _verify_mux_inputs(variant_dir: Path, picture: Path, timeline: dict[str, Any]) -> dict[str, Any]:
    problems = picture_problems(ffprobe_json(picture), timeline)
    render_record_path = picture.with_name(picture.name + ".render.json")
    timeline_sha = sha256_file(variant_dir / "timeline.json")
    if render_record_path.is_file():
        render_record = read_json(render_record_path)
        if render_record.get("input", {}).get("timeline_sha256") != timeline_sha:
            problems.append("画面是用旧版 timeline.json 渲染的，请重新渲染")
        if render_record.get("output", {}).get("sha256") != sha256_file(picture):
            problems.append("画面文件与其 .render.json 记录的校验值不一致")
    else:
        problems.append(f"缺少渲染记录 {render_record_path.name}，无法确认画面对应当前时间轴")
    mix = read_json(variant_dir / "audio" / "mix.json")
    if mix["input"]["sha256"] != timeline.get("voice_audio_sha256"):
        problems.append("mix.wav 来自旧的配音母轨，请重跑 mix")
    if mix["output"]["sha256"] != sha256_file(variant_dir / "audio" / "mix.wav"):
        problems.append("mix.wav 与 mix.json 记录不一致，请重跑 mix")
    sfx_path = variant_dir / "audio" / "sfx.wav"
    has_sfx = (variant_dir / "audio" / "sfx.json").is_file() and sfx_path.is_file()
    if mix.get("sfx", {}).get("sha256") != (sha256_file(sfx_path) if has_sfx else None):
        problems.append("音效轨在混音之后有变化（新增、重做或删除），请重跑 mix")
    if problems:
        raise MediaError("封装前检查未通过：\n  - " + "\n  - ".join(problems))
    return {"timeline_sha256": timeline_sha, "mix": mix}


def command_mux(args: argparse.Namespace) -> int:
    variant_dir = _variant_dir(args.variant_dir)
    timeline = read_json(variant_dir / "timeline.json")
    picture, out = inside(variant_dir, args.picture), inside(variant_dir, args.out)
    verified = _verify_mux_inputs(variant_dir, picture, timeline)
    mix_path = variant_dir / "audio" / "mix.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = temp_sibling(out)
    # 不加 -shortest：画面按帧向上取整，可能比音频长不到 1 帧，截短会丢掉最后一帧
    run_tool(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(picture), "-i", str(mix_path),
              "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", AAC_BITRATE, "-ar", "48000", "-ac", "1",
              "-map_metadata", "-1", "-movflags", "+faststart", str(temporary)])
    replace_atomic(temporary, out)
    record: dict[str, Any] = {
        "schema_version": "1.0", "variant": variant_dir.name, "created_at": local_now(),
        "inputs": {"picture": {"path": relative_to(variant_dir, picture), "sha256": sha256_file(picture)}, "timeline_sha256": verified["timeline_sha256"],
                   "mix": {"path": "audio/mix.wav", "sha256": verified["mix"]["output"]["sha256"]}},
        "settings": {"video": "copy（H.264 yuv420p 30fps，来自 remotion-render）", "audio": f"AAC {AAC_BITRATE} 48 kHz 单声道", "faststart": True},
        "output": {"path": relative_to(variant_dir, out), "sha256": sha256_file(out), "bytes": out.stat().st_size},
        "tool_versions": {"ffmpeg": tool_version("ffmpeg")},
    }
    if args.voice_only_out:
        record["voice_only"] = _write_voice_only(variant_dir, out, inside(variant_dir, args.voice_only_out), verified["mix"])
    write_json_atomic(out.with_name(out.name + ".export.json"), record)
    print(f"{variant_dir.name}: 成片 -> {out}（sha256 {record['output']['sha256']}）")
    return 0


def _write_voice_only(variant_dir: Path, final: Path, target: Path, mix: dict[str, Any]) -> dict[str, Any]:
    """无配乐时，无配乐母版与成片内容相同：复制一份并在记录里写明，而不是省略这个交付项。"""
    if mix.get("music", {}).get("mode") != "none":
        raise MediaError("带配乐的项目需要单独封装无配乐母版，当前版本未实现")
    temporary = temp_sibling(target)
    shutil.copyfile(final, temporary)
    replace_atomic(temporary, target)
    return {"path": relative_to(variant_dir, target), "sha256": sha256_file(target), "identical_to_final": True, "reason": "brief.music.mode=none，本片无配乐"}


def command_sfx(args: argparse.Namespace) -> int:
    variant_dir = _variant_dir(args.variant_dir)
    actions = inside(variant_dir, args.actions)
    library = Path(args.library).resolve() if args.library else default_library()
    record = build_sfx_track(variant_dir, actions, library, args.level_db)
    sounds = ", ".join(sorted({item["sound"] for item in record["placements"]})) or "无"
    print(f"{variant_dir.name}: 音效 {len(record['placements'])} 个（{sounds}），电平 {record['level_db']} dB，钳位 {record['clipped_samples']} 点 -> audio/sfx.wav")
    if record["clipped_samples"]:
        print("  [提示] 有音效重叠到溢出，已钳位；试听确认，必要时降低 --level-db 或拉开动作间隔")
    return 0


def command_check(args: argparse.Namespace) -> int:
    variant_dir = _variant_dir(args.variant_dir)
    project_dir, variant = _project_dir(variant_dir), variant_dir.name
    timeline = read_json(variant_dir / "timeline.json")
    video = inside(variant_dir, args.video)
    artifact = Path(relative_to(project_dir, video))
    items = run_automated_checks(video, artifact, variant, timeline, LoudnessTarget())
    sha = items[0]["artifact_sha256"]
    frame_dir = project_dir / "qa" / "frames" / f"{variant}-{sha[:8]}"
    images = extract_frames(video, review_frame_numbers(timeline), frame_dir)
    sheet = project_dir / "qa" / f"contact-sheet-{variant}-{sha[:8]}.png"
    contact_sheet(images, sheet)
    placeholders = manual_placeholders(variant, artifact, sha)
    for item in placeholders:
        if item["check_id"] == "picture.frame_review":
            item["evidence_path"] = relative_to(project_dir, sheet)
    report_path = project_dir / "qa" / "report.json"
    report = read_json(report_path) if report_path.is_file() else {}
    write_json_atomic(report_path, merge_report(report, items + placeholders))
    for item in items:
        print(f"  [{item['result']:>6}] {'阻断' if item['blocking'] else '提示'} {item['check_id']}: {item['detail']}")
    print(f"抽帧 {len(images)} 张 -> {frame_dir}；总览 -> {sheet}")
    failed = [item["check_id"] for item in items if item["blocking"] and item["result"] != "passed"]
    return 1 if failed else 0


def command_record(args: argparse.Namespace) -> int:
    variant_dir = _variant_dir(args.variant_dir)
    project_dir, variant = _project_dir(variant_dir), variant_dir.name
    if args.check_id not in {spec["check_id"] for spec in MANUAL_CHECKS}:
        raise MediaError(f"{args.check_id} 不是人工检查项；自动检查项只能由 check 命令重新测量")
    report_path = project_dir / "qa" / "report.json"
    report = read_json(report_path)
    item = next((entry for entry in report.get("items", []) if entry["variant"] == variant and entry["check_id"] == args.check_id), None)
    if item is None:
        raise MediaError(f"qa/report.json 中没有 {variant}/{args.check_id}，请先运行 check")
    current_sha = sha256_file(project_dir / item["artifact_path"])
    if current_sha != item["artifact_sha256"]:
        raise MediaError("成片已变化，旧的检查条目不能沿用：请先对新文件运行 check")
    if args.evidence:
        inside(project_dir, args.evidence)
    item.update({"result": args.result, "checked_by": args.by, "checked_at": local_now(), "detail": args.detail, "evidence_path": args.evidence})
    write_json_atomic(report_path, merge_report(report, []))
    print(f"{variant}/{args.check_id} -> {args.result}（{args.by}）")
    return 0


def command_deliver(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir).resolve()
    rerender = [
        "cd <remotion-render 技能目录> && npm ci && npm run setup:fonts",
        "node scripts/render.mjs video --timeline <版本目录>/timeline.json --out <版本目录>/exports/picture-<版本>.mp4",
        "node scripts/render.mjs cover --props <版本目录>/cover.props.json --out <版本目录>/exports/cover-<版本>.png",
        "node scripts/render.mjs actions --timeline <版本目录>/timeline.json --out <版本目录>/actions.json（有文字动效时）",
        "python <av-export 技能目录>/scripts/av_export.py sfx --variant-dir <版本目录>（有 actions.json 时）",
        "python <av-export 技能目录>/scripts/av_export.py mix --variant-dir <版本目录>",
        "python <av-export 技能目录>/scripts/av_export.py mux --variant-dir <版本目录> --picture exports/picture-<版本>.mp4 --out exports/final-<版本>.mp4 --voice-only-out exports/voice-only-<版本>.mp4",
        "python <av-export 技能目录>/scripts/av_export.py check --variant-dir <版本目录> --video exports/final-<版本>.mp4",
    ]
    delivery = build_delivery(project_dir, args.version, rerender)
    write_json_atomic(project_dir / "delivery.json", delivery)
    for variant, block in delivery["variants"].items():
        pending = ", ".join(f"{item['check_id']}={item['result']}" for item in block["pending_checks"]) or "无"
        print(f"{variant}: render_complete={block['render_complete']} delivery_ready={block['delivery_ready']} ready_to_publish={block['ready_to_publish']}；缺文件 {block['missing'] or '无'}；待检查 {pending}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VideoCut 混音、封装、质检与交付")
    sub = parser.add_subparsers(dest="command", required=True)
    mix = sub.add_parser("mix", help="人声母轨处理到目标响度")
    mix.add_argument("--variant-dir", required=True)
    mix.add_argument("--target-lufs", type=float, default=-16.0)
    sfx = sub.add_parser("sfx", help="按动作标记排出音效轨 audio/sfx.wav（可选；有它时 mix 自动混入）")
    sfx.add_argument("--variant-dir", required=True)
    sfx.add_argument("--actions", default="actions.json", help="相对版本目录，remotion-render 的 render.mjs actions 产物")
    sfx.add_argument("--library", help="sfx-kit 音效库目录；默认为同一技能目录下的 sfx-kit/library")
    sfx.add_argument("--level-db", type=float, default=SFX_LEVEL_DB, help="音效总线电平（暂定 -8，试听后再定）")
    mux = sub.add_parser("mux", help="无声画面 + 混音封装为成片")
    mux.add_argument("--variant-dir", required=True)
    mux.add_argument("--picture", required=True, help="相对版本目录，如 exports/picture-v001.mp4")
    mux.add_argument("--out", required=True, help="相对版本目录，如 exports/final-v001.mp4")
    mux.add_argument("--voice-only-out", help="无配乐母版输出路径（无配乐时与成片相同）")
    check = sub.add_parser("check", help="成片自动检查与抽帧")
    check.add_argument("--variant-dir", required=True)
    check.add_argument("--video", required=True, help="相对版本目录，如 exports/final-v001.mp4")
    record = sub.add_parser("record", help="登记人工或模型审阅结果")
    record.add_argument("--variant-dir", required=True)
    record.add_argument("--check-id", required=True)
    record.add_argument("--result", required=True, choices=["passed", "failed", "not_checked"])
    record.add_argument("--by", required=True, help="执行者，如「用户」或「Claude（抽帧审阅，未试听）」")
    record.add_argument("--detail")
    record.add_argument("--evidence", help="相对项目根目录的证据路径")
    deliver = sub.add_parser("deliver", help="生成 delivery.json")
    deliver.add_argument("--project-dir", required=True)
    deliver.add_argument("--version", default="v001")
    return parser


COMMANDS = {"mix": command_mix, "sfx": command_sfx, "mux": command_mux, "check": command_check, "record": command_record, "deliver": command_deliver}


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，被智能体管道读取时中文会乱码；与其他技能一样统一输出 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except MediaError as error:
        print(f"[失败] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
