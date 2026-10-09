"""
INPUT: media.py 的 ffprobe/ffmpeg 封装；loudness.py 的测量；timeline.json；成片 MP4
OUTPUT: picture_problems()（封装前检查无声画面）、moov_before_mdat()、source_aigc_labels()、run_automated_checks()、
        review_frame_numbers()、extract_frames()、contact_sheet()、MANUAL_CHECKS、manual_placeholders()、merge_report()、make_item()
POS: 成片自动检查的唯一实现。每项检查产出数据合同第 8 节 qa/report.json 的条目；自动检查只覆盖可测量的技术项，
     试听、完整观看、平台预览等人工项只登记为 not_checked，不能由程序判定通过。
"""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import Any

from .loudness import LoudnessTarget, measure_loudness
from .media import MediaError, ffprobe_json, local_now, run_tool, sha256_file

CHECKED_BY = "av-export check"
# 片长容差：AGENTS / ACCEPTANCE 约定原则上不超过 2 帧
FRAME_TOLERANCE = 2

# 人工或平台检查项：scope 为 delivery 的影响 delivery_ready，publish 的只影响 ready_to_publish
MANUAL_CHECKS: list[dict[str, Any]] = [
    {"check_id": "audio.full_listen", "scope": "delivery", "blocking": True, "method": "完整试听：无错读、缺字、断尾、爆音、刺耳拼接与限幅失真"},
    {"check_id": "captions.spot_listen", "scope": "delivery", "blocking": True, "method": "字幕关键位置抽听：段首、长句、专有名词与数字，偏差目标 ≤150 ms"},
    {"check_id": "picture.full_watch", "scope": "delivery", "blocking": True, "method": "手机尺寸完整观看：文字可读、无遮挡、无瞬时异常帧"},
    {"check_id": "picture.frame_review", "scope": "delivery", "blocking": True, "method": "成片抽帧审阅：首末帧、各镜头中段与切点前后"},
    {"check_id": "content.claims_match", "scope": "delivery", "blocking": True, "method": "画面文字与口播对照 claims.json：数字、来源、日期一致"},
    # 对应 ACCEPTANCE.md「画面增量」：只能看成片判断，程序无法测量，所以作为人工项阻断 delivery_ready
    {"check_id": "picture.value_add", "scope": "delivery", "blocking": True, "method": "画面增量：对照 shots.json 的 purpose 与场景文字看成片，每个镜头在口播之外提供证据、动作、对比或关系，屏幕文字不逐句复制口播"},
    {"check_id": "labels.aigc_explicit", "scope": "delivery", "blocking": True, "method": "显式标识与 brief.aigc 一致：explicit_overlay 为 none 时，画面与封面无角标，且发布包已把平台 AI 生成内容声明列为必做项；否则画面全程可见「AI 合成配音」角标"},
    # 以下两项对应 ACCEPTANCE.md 第 2 节的「权利」与「可复用」
    {"check_id": "rights.clearance", "scope": "delivery", "blocking": True, "method": "权利：字体、声音、音乐与素材的来源和使用范围清楚，核心授权不明即阻断"},
    {"check_id": "reuse.rerender", "scope": "delivery", "blocking": True, "method": "可复用：用锁定依赖与项目数据重渲染一次，结果与成片一致或差异有解释"},
    {"check_id": "platform.upload_preview", "scope": "publish", "blocking": True, "method": "平台上传预览：安全区、封面裁切与 AI 内容声明"},
]


def make_item(check_id: str, variant: str, artifact: Path, artifact_sha: str, *, result: str, method: str, blocking: bool,
              scope: str, detail: Any = None, evidence_path: str | None = None, checked_by: str = CHECKED_BY) -> dict[str, Any]:
    if result not in {"passed", "failed", "not_checked"}:
        raise MediaError(f"未知检查结果 {result}")
    return {
        "check_id": check_id, "variant": variant, "artifact_path": artifact.as_posix(), "artifact_sha256": artifact_sha,
        "method": method, "result": result, "blocking": blocking, "scope": scope, "detail": detail,
        "evidence_path": evidence_path, "checked_by": checked_by if result != "not_checked" else None,
        "checked_at": local_now() if result != "not_checked" else None,
    }


def _streams(info: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [stream for stream in info.get("streams", []) if stream.get("codec_type") == kind]


def picture_problems(info: dict[str, Any], timeline: dict[str, Any]) -> list[str]:
    """封装前检查 Remotion 画面：规格与时间轴一致、没有音轨。"""
    problems: list[str] = []
    videos, audios = _streams(info, "video"), _streams(info, "audio")
    if len(videos) != 1:
        return [f"画面文件应只有 1 条视频流，实际 {len(videos)}"]
    if audios:
        problems.append("画面文件含音轨；应为 remotion-render 输出的无声画面")
    video = videos[0]
    expected_rate = f"{timeline['fps']}/1"
    checks = {
        "codec_name": ("h264", video.get("codec_name")),
        "width": (timeline["width"], video.get("width")),
        "height": (timeline["height"], video.get("height")),
        "pix_fmt": ("yuv420p", video.get("pix_fmt")),
        # 有限范围（tv）：全范围 yuvj420p 在按 TV 范围解码的播放器上会发灰或压黑
        "color_range": ("tv", video.get("color_range")),
        "r_frame_rate": (expected_rate, video.get("r_frame_rate")),
        "nb_frames": (str(timeline["duration_frames"]), video.get("nb_frames")),
    }
    for key, (expected, actual) in checks.items():
        if expected != actual:
            problems.append(f"{key} 应为 {expected}，实际 {actual}")
    return problems


def moov_before_mdat(path: Path) -> bool:
    """读取 MP4 顶层 box 顺序；moov 在 mdat 之前才能边下边播（-movflags +faststart 的效果）。"""
    with path.open("rb") as handle:
        while True:
            header = handle.read(8)
            if len(header) < 8:
                return False
            size, box_type = struct.unpack(">I4s", header)
            if box_type == b"moov":
                return True
            if box_type == b"mdat":
                return False
            if size == 1:
                size = struct.unpack(">Q", handle.read(8))[0] - 8
            elif size == 0:
                return False
            handle.seek(size - 8, 1)


def source_aigc_labels(variant_dir: Path, speech: dict[str, Any]) -> list[dict[str, Any]]:
    """
    读取各段配音原始 MP3 中服务商写入的 AIGC 隐式标识（ID3 TXXX:AIGC）。
    拼接为母轨后这些元数据不会随音频保留，这里完整记录来源与标识编号，原始 MP3 作为可核对的证据保留。
    """
    labels: list[dict[str, Any]] = []
    for segment in speech.get("segments", []):
        path = variant_dir / segment["audio_path"]
        tags = ffprobe_json(path).get("format", {}).get("tags", {})
        raw = next((value for key, value in tags.items() if key.upper() == "AIGC"), None)
        entry: dict[str, Any] = {"segment_id": segment["segment_id"], "file": segment["audio_path"], "sha256": sha256_file(path), "present": raw is not None}
        if raw is not None:
            try:
                parsed = json.loads(raw)
                entry.update({key: parsed.get(key) for key in ("Label", "ContentProducer", "ProduceID", "ContentPropagator", "PropagateID")})
                entry["signed"] = "SecurityData" in str(parsed.get("ReservedCode1", ""))
            except json.JSONDecodeError:
                entry["raw_unparsed"] = raw[:200]
        labels.append(entry)
    return labels


def _count_decoded_frames(path: Path) -> int:
    completed = run_tool(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "json", str(path)], timeout=1800)
    return int(json.loads(completed.stdout)["streams"][0]["nb_read_frames"])


def _full_decode(path: Path) -> tuple[bool, str]:
    completed = run_tool(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path), "-map", "0", "-f", "null", "-"], timeout=1800, check=False)
    stderr = completed.stderr.strip()
    return completed.returncode == 0 and not stderr, f"退出码 {completed.returncode}" + (f"；{stderr[-400:]}" if stderr else "；无错误输出")


def _spec_video(video: dict[str, Any], timeline: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    expected = {"codec_name": "h264", "width": timeline["width"], "height": timeline["height"], "pix_fmt": "yuv420p", "color_range": "tv",
                "r_frame_rate": f"{timeline['fps']}/1", "avg_frame_rate": f"{timeline['fps']}/1"}
    actual = {key: video.get(key) for key in expected}
    # r_frame_rate 与 avg_frame_rate 都等于 30/1 才视为恒定帧率
    return actual == expected, {"expected": expected, "actual": actual, "profile": video.get("profile")}


def _spec_audio(audios: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    if len(audios) != 1:
        return False, {"audio_streams": len(audios)}
    audio = audios[0]
    actual = {"codec_name": audio.get("codec_name"), "sample_rate": audio.get("sample_rate"), "channels": audio.get("channels"), "bit_rate": audio.get("bit_rate")}
    return actual["codec_name"] == "aac" and actual["sample_rate"] == "48000", actual


def _black_segments(path: Path) -> list[dict[str, float]]:
    # 画面底色很深（约 #0A0F1C），阈值取 0.03 只抓接近纯黑的帧；0.5 秒以上才报告
    completed = run_tool(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:v:0", "-vf", "blackdetect=d=0.5:pix_th=0.03:pic_th=0.98", "-an", "-f", "null", "-"], timeout=1800, check=False)
    pattern = re.compile(r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)")
    return [{"start_s": float(a), "end_s": float(b), "duration_s": float(c)} for a, b, c in pattern.findall(completed.stderr)]


def run_automated_checks(video_path: Path, relative_path: Path, variant: str, timeline: dict[str, Any], target: LoudnessTarget) -> list[dict[str, Any]]:
    """对最终编码文件做全部可自动测量的检查；每项独立给出结果与测量值。"""
    sha = sha256_file(video_path)
    info = ffprobe_json(video_path)
    videos, audios = _streams(info, "video"), _streams(info, "audio")
    if len(videos) != 1:
        raise MediaError(f"{video_path.name} 应有 1 条视频流，实际 {len(videos)}")
    items: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, method: str, detail: Any, blocking: bool = True) -> None:
        items.append(make_item(check_id, variant, relative_path, sha, result="passed" if passed else "failed", method=method, blocking=blocking, scope="render", detail=detail))

    decoded_ok, decode_detail = _full_decode(video_path)
    add("file.full_decode", decoded_ok, "ffmpeg -v error 完整解码全部流到 null", decode_detail)
    ok, detail = _spec_video(videos[0], timeline)
    add("spec.video", ok, "ffprobe：H.264、分辨率、yuv420p 有限范围、恒定 30fps", detail)
    ok, detail = _spec_audio(audios)
    add("spec.audio", ok, "ffprobe：AAC、48 kHz，记录真实声道与码率", detail)
    add("spec.faststart", moov_before_mdat(video_path), "读取顶层 box 顺序：moov 位于 mdat 之前", None)
    frames = _count_decoded_frames(video_path)
    add("timeline.frame_count", abs(frames - timeline["duration_frames"]) <= FRAME_TOLERANCE, f"ffprobe -count_frames 解码计数，与时间轴相差不超过 {FRAME_TOLERANCE} 帧",
        {"decoded_frames": frames, "timeline_frames": timeline["duration_frames"]})
    audio_ms = round(float(audios[0].get("duration", 0)) * 1000) if audios else None
    tolerance_ms = FRAME_TOLERANCE * 1000 / timeline["fps"]
    add("timeline.audio_duration", audio_ms is not None and abs(audio_ms - timeline["duration_ms"]) <= tolerance_ms,
        f"音轨时长与时间轴相差不超过 {tolerance_ms:.0f} ms（{FRAME_TOLERANCE} 帧）", {"audio_ms": audio_ms, "timeline_ms": timeline["duration_ms"]})
    measured = measure_loudness(video_path)
    loud_ok = target.accept_min_lufs <= measured.integrated_lufs <= target.accept_max_lufs and measured.true_peak_dbtp <= target.max_true_peak_dbtp
    add("audio.loudness", loud_ok, f"ebur128 测最终 AAC 音轨：{target.accept_min_lufs}～{target.accept_max_lufs} LUFS，真峰值 ≤ {target.max_true_peak_dbtp} dBTP",
        {"integrated_lufs": measured.integrated_lufs, "true_peak_dbtp": measured.true_peak_dbtp, "lra_lu": measured.lra_lu})
    black = _black_segments(video_path)
    add("picture.black_segments", not black, "blackdetect（d=0.5, pix_th=0.03）：无 0.5 秒以上接近纯黑的片段", black, blocking=False)
    tags = info.get("format", {}).get("tags", {})
    has_aigc = any(key.upper() == "AIGC" for key in tags)
    add("labels.aigc_implicit", has_aigc, "成片容器元数据是否带 AIGC 隐式标识", {"format_tags": sorted(tags)}, blocking=False)
    return items


def review_frame_numbers(timeline: dict[str, Any]) -> list[tuple[int, str]]:
    """审阅帧：首末帧、每个镜头中段、每个切点前后各一帧（切点前一帧应完整，切点后应开始新镜头）。"""
    frames: dict[int, str] = {0: "first", timeline["duration_frames"] - 1: "last"}
    for clip in timeline["tracks"]["visual"]:
        frames.setdefault((clip["start_frame"] + clip["end_frame"]) // 2, f"mid-{clip['shot_id']}")
        if clip["start_frame"] > 0:
            frames.setdefault(clip["start_frame"] - 1, f"cut-before-{clip['shot_id']}")
            frames.setdefault(clip["start_frame"], f"cut-at-{clip['shot_id']}")
    return sorted(frames.items())


def extract_frames(video_path: Path, frames: list[tuple[int, str]], out_dir: Path) -> list[Path]:
    """从编码后的成片按帧号解码取图（不是从 Remotion 合成截图），作为与该文件校验值绑定的证据。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()
    selector = "+".join(f"eq(n\\,{number})" for number, _ in frames)
    pattern = out_dir / "raw-%04d.png"
    run_tool(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(video_path), "-vf", f"select='{selector}'", "-fps_mode", "passthrough", str(pattern)], timeout=1800)
    raw = sorted(out_dir.glob("raw-*.png"))
    if len(raw) != len(frames):
        raise MediaError(f"抽帧数量不符：期望 {len(frames)}，实际 {len(raw)}")
    named: list[Path] = []
    for path, (number, label) in zip(raw, frames):
        target = out_dir / f"{number:05d}-{label}.png"
        path.replace(target)
        named.append(target)
    return named


def contact_sheet(images: list[Path], out: Path, columns: int = 8) -> None:
    """把抽帧拼成一张总览图（每张缩到 270×480），供快速审阅。"""
    rows = -(-len(images) // columns)
    padding = rows * columns - len(images)
    args = ["ffmpeg", "-hide_banner", "-v", "error", "-y"]
    for image in images:
        args += ["-i", str(image)]
    chains = [f"[{index}]scale=270:480[s{index}]" for index in range(len(images))]
    chains += [f"color=c=black:s=270x480:d=1[p{index}]" for index in range(padding)]
    labels = [f"[s{index}]" for index in range(len(images))] + [f"[p{index}]" for index in range(padding)]
    layout = "|".join(f"{(k % columns) * 270}_{(k // columns) * 480}" for k in range(len(labels)))
    graph = ";".join(chains) + ";" + "".join(labels) + f"xstack=inputs={len(labels)}:layout={layout}"
    out.parent.mkdir(parents=True, exist_ok=True)
    run_tool(args + ["-filter_complex", graph, "-frames:v", "1", str(out)], timeout=600)


def merge_report(report: dict[str, Any], new_items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    同一版本、同一检查项只保留最新一条。人工项占位只在「当前文件还没有这项记录」时加入，
    所以文件变了（校验值不同）之后，旧的人工通过结果会被 not_checked 替换，不会移用到新文件上。
    """
    items = report.setdefault("items", [])
    for new in new_items:
        key = (new["variant"], new["check_id"])
        existing = next((item for item in items if (item["variant"], item["check_id"]) == key), None)
        if new["result"] == "not_checked" and existing and existing["artifact_sha256"] == new["artifact_sha256"]:
            continue
        if existing:
            items.remove(existing)
        items.append(new)
    items.sort(key=lambda item: (item["variant"], item["scope"], item["check_id"]))
    report["schema_version"] = "1.0"
    report["updated_at"] = local_now()
    return report


def manual_placeholders(variant: str, artifact: Path, artifact_sha: str) -> list[dict[str, Any]]:
    return [make_item(spec["check_id"], variant, artifact, artifact_sha, result="not_checked", method=spec["method"], blocking=spec["blocking"], scope=spec["scope"]) for spec in MANUAL_CHECKS]
