"""
INPUT: 平台版本目录下的 shots.json（镜头与所含语段）、speech.json（语段全局起止与母轨时长）、captions/captions.json
OUTPUT: build 子命令写出 timeline.json：统一的毫秒与帧边界、visual / voice / caption 轨道；
        纯函数 ms_to_frame()、shot_boundaries()、build_timeline() 供单测
POS: 画面、声音、字幕的唯一时间来源。渲染与混音都只读 timeline.json，不各自计算时长。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
DEFAULT_FPS = 30
WIDTH, HEIGHT = 1080, 1920


class TimelineError(ValueError):
    pass


def ms_to_frame(ms: float, fps: int) -> int:
    """绝对时间转帧：所有边界都从同一个毫秒值换算，避免逐段取整造成的累计漂移。"""
    return round(ms * fps / 1000)


def shot_boundaries(shots: list[dict[str, Any]], segments: dict[str, dict[str, Any]], total_ms: float) -> list[tuple[float, float]]:
    """
    每个镜头从「上一段口播结束与本段开始的中点」切入，让画面在停顿里换，而不是压在字上。
    第一个镜头从 0 开始，最后一个镜头延续到母轨结束（含片尾静音）。
    """
    starts: list[float] = []
    for index, shot in enumerate(shots):
        first = segments[shot["segment_ids"][0]]
        if index == 0:
            starts.append(0.0)
            continue
        previous_last = segments[shots[index - 1]["segment_ids"][-1]]
        starts.append((previous_last["global_end_ms"] + first["global_start_ms"]) / 2)
    ends = starts[1:] + [total_ms]
    return list(zip(starts, ends))


def validate_inputs(shots: list[dict[str, Any]], segments: dict[str, dict[str, Any]]) -> None:
    seen: list[str] = []
    for shot in shots:
        if not shot.get("segment_ids"):
            raise TimelineError(f"{shot['shot_id']} 没有对应语段")
        for segment_id in shot["segment_ids"]:
            segment = segments.get(segment_id)
            if segment is None:
                raise TimelineError(f"{shot['shot_id']} 引用了不存在的语段 {segment_id}")
            if segment.get("global_start_ms") is None:
                raise TimelineError(f"语段 {segment_id} 还没有全局时间，先运行 voice-captions assemble")
            seen.append(segment_id)
    order = list(segments)
    if seen != order:
        raise TimelineError("镜头引用的语段必须按口播顺序、不重复、不遗漏地覆盖全部语段")


def visual_clips(shots: list[dict[str, Any]], bounds: list[tuple[float, float]], fps: int) -> list[dict[str, Any]]:
    clips = []
    for shot, (start_ms, end_ms) in zip(shots, bounds):
        clips.append({
            "id": f"visual_{shot['shot_id']}",
            "shot_id": shot["shot_id"],
            "scene_type": shot["scene_type"],
            "params": shot.get("params", {}),
            "asset_ids": shot.get("asset_ids", []),
            "start_ms": round(start_ms),
            "end_ms": round(end_ms),
            "start_frame": ms_to_frame(start_ms, fps),
            "end_frame": ms_to_frame(end_ms, fps),
        })
    return clips


def caption_clips(entries: list[dict[str, Any]], fps: int) -> list[dict[str, Any]]:
    return [{**entry, "start_frame": ms_to_frame(entry["start_ms"], fps), "end_frame": ms_to_frame(entry["end_ms"], fps)} for entry in entries]


def build_timeline(shots_doc: dict[str, Any], speech: dict[str, Any], captions: dict[str, Any], fps: int = DEFAULT_FPS) -> dict[str, Any]:
    segments = {s["segment_id"]: s for s in speech["segments"]}
    shots = shots_doc["shots"]
    validate_inputs(shots, segments)
    master = speech["master_audio"]
    total_ms = float(master["duration_ms"])
    visuals = visual_clips(shots, shot_boundaries(shots, segments, total_ms), fps)
    # 片长向上取整补足最后一帧，保证声音不被截断
    duration_frames = math.ceil(total_ms * fps / 1000)
    visuals[-1]["end_frame"] = duration_frames
    return {
        "schema_version": SCHEMA_VERSION,
        "variant": speech.get("variant"),
        "revision": 1,
        "width": WIDTH,
        "height": HEIGHT,
        "fps": fps,
        "duration_ms": round(total_ms),
        "duration_frames": duration_frames,
        "voice_audio_sha256": master["sha256"],
        "captions_sha256": captions.get("audio_sha256"),
        "tracks": {
            "visual": visuals,
            "voice": [{"id": "voice_master", "path": master["path"], "start_ms": 0, "end_ms": round(total_ms), "start_frame": 0, "end_frame": duration_frames}],
            "caption": caption_clips(captions["entries"], fps),
        },
    }


def check_timeline(timeline: dict[str, Any]) -> list[str]:
    """主画面必须首尾相接覆盖全片；字幕不得越出片长。"""
    problems = []
    visuals = timeline["tracks"]["visual"]
    if visuals[0]["start_frame"] != 0:
        problems.append("第一个镜头不是从 0 帧开始")
    for earlier, later in zip(visuals, visuals[1:]):
        if earlier["end_frame"] != later["start_frame"]:
            problems.append(f"{earlier['shot_id']} 与 {later['shot_id']} 之间有空洞或重叠")
        if later["end_frame"] <= later["start_frame"]:
            problems.append(f"{later['shot_id']} 时长为 0")
    if visuals[-1]["end_frame"] != timeline["duration_frames"]:
        problems.append("最后一个镜头没有延续到片尾")
    for caption in timeline["tracks"]["caption"]:
        if caption["end_frame"] > timeline["duration_frames"]:
            problems.append(f"字幕 {caption['id']} 超出片长")
    return problems


def command_build(args: argparse.Namespace) -> int:
    variant_dir = Path(args.variant_dir).resolve()
    load = lambda name: json.loads((variant_dir / name).read_text(encoding="utf-8"))  # noqa: E731
    captions = load("captions/captions.json")
    speech = load("speech.json")
    if captions.get("audio_sha256") != speech["master_audio"]["sha256"]:
        raise TimelineError("字幕与当前配音母轨不对应，先重新运行 voice-captions assemble")
    timeline = build_timeline(load("shots.json"), speech, captions, args.fps)
    problems = check_timeline(timeline)
    body = json.dumps(timeline, ensure_ascii=False, indent=2)
    temporary = variant_dir / "timeline.json.tmp"
    temporary.write_text(body, encoding="utf-8")
    temporary.replace(variant_dir / "timeline.json")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
    print(f"时间轴 {timeline['duration_ms'] / 1000:.2f}s / {timeline['duration_frames']} 帧，镜头 {len(timeline['tracks']['visual'])} 个，字幕 {len(timeline['tracks']['caption'])} 条（{digest}）")
    for shot in timeline["tracks"]["visual"]:
        print(f"  {shot['shot_id']:<12} {shot['scene_type']:<12} {shot['start_frame']:>5} → {shot['end_frame']:>5}  ({(shot['end_frame'] - shot['start_frame']) / args.fps:.1f}s)")
    for problem in problems:
        print(f"[时间轴问题] {problem}", file=sys.stderr)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="生成统一时间轴")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--variant-dir", required=True)
    build.add_argument("--fps", type=int, default=DEFAULT_FPS)
    args = parser.parse_args(argv)
    try:
        return command_build(args)
    except (TimelineError, OSError, KeyError, ValueError) as error:
        print(f"[失败] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
