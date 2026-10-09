"""
INPUT: minimax_tts.py（接口封装）；技能目录 config.json（模型、角色音色、读音词典、字数上限）；
       命令行参数（文本或分段 JSON、输出位置）
OUTPUT: check / voices / say / batch / audition 五个子命令：
        合成的音频文件、同名 .meta.json（请求摘要、时长、计费字符数）、.subtitles.json（接口原始字幕）
POS: 技能的唯一命令入口，可被智能体或其他技能独立调用。
     不读写 project.json，只按参数读写文件，便于单独迭代和替换。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import minimax_tts
from minimax_tts import (
    SKILL_ROOT,
    MiniMaxError,
    RoleVoice,
    SynthesisOptions,
    api_host,
    download_subtitles,
    list_voices,
    load_api_key,
    synthesize,
)

DEFAULT_CONFIG_PATH = SKILL_ROOT / "config.json"
from workspace import require_workspace


def default_out_dir() -> Path:
    """音色缓存与试听输出放在工作区 out/minimax；找不到工作区时报错，不写到技能目录或主目录。"""
    return require_workspace(minimax_tts.REPO_ROOT, "音色缓存与试听文件", MiniMaxError) / "out" / "minimax"
DEFAULT_AUDITION_TEXT = "每次投标都要熬夜排版？同一份招标文件，我现在半天就能出标书初稿，第 3 步最关键。"


class SkillConfig:
    """config.json 的只读视图；命令行参数可覆盖其中的角色与字幕设置。"""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.default_role: str = raw["defaultRole"]
        self.roles = {name: RoleVoice.from_dict(item) for name, item in raw["roles"].items()}
        self.max_chars: int = int(raw.get("maxCharsPerRun", 3000))

    @classmethod
    def load(cls, path: Path) -> SkillConfig:
        try:
            return cls(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError) as error:
            raise ValueError(f"配置文件无法使用 {path}: {error}") from error

    def voice(self, role: str | None) -> RoleVoice:
        name = role or self.default_role
        if name not in self.roles:
            raise ValueError(f"config.json 的 roles 中没有角色 {name}，可选：{sorted(self.roles)}")
        return self.roles[name]

    def options(self, subtitles: str | None) -> SynthesisOptions:
        audio = self.raw.get("audio") or {}
        return SynthesisOptions(
            model=self.raw.get("model", "speech-2.8-hd"),
            pronunciation=tuple(self.raw.get("pronunciation") or ()),
            text_normalization=bool(self.raw.get("textNormalization", False)),
            audio_format=audio.get("format", "mp3"),
            sample_rate=int(audio.get("sampleRate", 32000)),
            bitrate=int(audio.get("bitrate", 128000)),
            subtitle_type=None if subtitles == "none" else subtitles,
        )


def request_hash(text: str, voice: RoleVoice, options: SynthesisOptions) -> str:
    """缓存键：文本、音色参数、模型、读音词典、音频格式、字幕类型任一变化都会重新合成。"""
    canonical = json.dumps(
        {"text": text, "voice": voice.__dict__, "options": options.__dict__, "host": api_host()},
        ensure_ascii=False,
        sort_keys=True,
        default=list,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_cjk(char: str) -> bool:
    code = ord(char)
    return 0x3400 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF or 0x20000 <= code <= 0x2FA1F


def billing_chars(text: str) -> int:
    """官方计费规则（2026-09-29 核验）：汉字计 2 个字符，字母、数字、标点、空格、换行各计 1 个。"""
    return sum(2 if is_cjk(char) else 1 for char in text)


def estimated_cost(units: int, config: "SkillConfig") -> float | None:
    price = config.raw.get("pricePer10kBillingChars")
    return None if price is None else round(units * float(price) / 10000, 4)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def meta_path_for(audio_path: Path) -> Path:
    return audio_path.with_suffix(".meta.json")


def cached_meta(audio_path: Path, expected_hash: str) -> dict[str, Any] | None:
    """音频与元数据都在、请求摘要一致、音频校验值一致时才算命中，防止复用被改动过的文件。"""
    meta_path = meta_path_for(audio_path)
    if not (audio_path.exists() and meta_path.exists()):
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if meta.get("request_hash") != expected_hash:
        return None
    if meta.get("audio_sha256") != sha256_bytes(audio_path.read_bytes()):
        return None
    # 请求了字幕却没拿到时不算完整命中；重跑会重新合成（计费）以取得时间戳
    if meta.get("subtitle_type") and not subtitle_saved(audio_path, meta):
        return None
    return meta


def subtitle_saved(audio_path: Path, meta: dict[str, Any]) -> bool:
    return meta.get("subtitle_status") == "saved" and (audio_path.parent / str(meta.get("subtitle_file"))).exists()


def write_atomic(path: Path, data: bytes, attempts: int = 5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_bytes(data)
    # Windows 上杀毒或索引服务会短暂占用刚写出的文件，替换时报「拒绝访问」（WinError 5）。
    # 这一步发生在已计费的合成之后，直接失败会让下次重跑再付一次钱，所以短暂退避重试
    for attempt in range(1, attempts + 1):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == attempts:
                raise
            time.sleep(0.2 * attempt)


def write_meta(audio_path: Path, meta: dict[str, Any]) -> None:
    write_atomic(meta_path_for(audio_path), json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"))


def save_subtitles(audio_path: Path, meta: dict[str, Any], subtitle_url: str | None) -> None:
    """字幕下载失败不抛错：音频已计费，必须保留音频与计费记录，只把字幕状态标为失败。"""
    if not meta["subtitle_type"]:
        meta["subtitle_status"] = "not_requested"
        return
    if not subtitle_url:
        meta["subtitle_status"] = "missing"
        return
    subtitle_path = audio_path.with_suffix(".subtitles.json")
    try:
        subtitles = download_subtitles(subtitle_url)
    except MiniMaxError as error:
        meta["subtitle_status"] = "failed"
        meta["subtitle_error"] = str(error)
        print(f"[警告] {audio_path.name} 字幕下载失败，音频已保存：{error}", file=sys.stderr)
        return
    write_atomic(subtitle_path, json.dumps(subtitles, ensure_ascii=False, indent=2).encode("utf-8"))
    meta["subtitle_status"] = "saved"
    meta["subtitle_file"] = subtitle_path.name


def synthesize_to_files(text: str, voice: RoleVoice, options: SynthesisOptions, api_key: str, audio_path: Path) -> dict[str, Any]:
    """
    合成一段并落盘。顺序很重要：接口一旦返回就已计费，先写音频与元数据（含 trace_id、计费字符数），
    再下载字幕；字幕环节出错也不会丢失计费记录。
    """
    result = synthesize(text, voice, api_key, options)
    write_atomic(audio_path, result.audio)
    meta = {
        "provider": "minimax",
        "api_host": api_host(),
        "model": options.model,
        "voice": voice.__dict__,
        "options": {**options.__dict__, "pronunciation": list(options.pronunciation)},
        "text": text,
        "text_chars": len(text),
        "request_hash": request_hash(text, voice, options),
        "audio_file": audio_path.name,
        "audio_sha256": sha256_bytes(result.audio),
        "audio_bytes": len(result.audio),
        "duration_ms": result.duration_ms,
        "usage_characters": result.usage_characters,
        "subtitle_type": options.subtitle_type,
        "subtitle_url": result.subtitle_url,
        "subtitle_file": None,
        "subtitle_status": "pending",
        "trace_id": result.trace_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_meta(audio_path, meta)
    save_subtitles(audio_path, meta, result.subtitle_url)
    write_meta(audio_path, meta)
    return meta


def load_segments(path: Path) -> list[dict[str, Any]]:
    """接受 {"segments": [...]} 或直接数组；每段需要 id 与 text，role 可选。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    segments = raw.get("segments") if isinstance(raw, dict) else raw
    if not isinstance(segments, list) or not segments:
        raise ValueError(f"{path} 中没有 segments")
    for segment in segments:
        if not segment.get("id") or not str(segment.get("text", "")).strip():
            raise ValueError(f"分段缺少 id 或 text: {segment}")
        if not re.fullmatch(r"[\w\-]+", str(segment["id"])):
            raise ValueError(f"分段 id 只能包含字母、数字、下划线和连字符: {segment['id']}")
    ids = [segment["id"] for segment in segments]
    if len(ids) != len(set(ids)):
        raise ValueError("分段 id 有重复")
    return segments


def plan_batch(segments: list[dict[str, Any]], config: SkillConfig, options: SynthesisOptions, out_dir: Path, force: bool) -> list[dict[str, Any]]:
    """先算出哪些段需要真正调用接口，再统一做字数上限检查，避免合成到一半才超额。"""
    extension = options.audio_format
    plan = []
    for segment in segments:
        voice = config.voice(segment.get("role"))
        audio_path = out_dir / f"{segment['id']}.{extension}"
        expected = request_hash(segment["text"], voice, options)
        cached = None if force else cached_meta(audio_path, expected)
        plan.append({"segment": segment, "voice": voice, "audio_path": audio_path, "cached": cached})
    return plan


def command_batch(args: argparse.Namespace, config: SkillConfig) -> int:
    options = config.options(args.subtitles or config.raw.get("subtitles"))
    out_dir = Path(args.out_dir).resolve()
    plan = plan_batch(load_segments(Path(args.segments)), config, options, out_dir, args.force)
    billable = sum(len(item["segment"]["text"]) for item in plan if item["cached"] is None)
    units = sum(billing_chars(item["segment"]["text"]) for item in plan if item["cached"] is None)
    limit = args.max_chars or config.max_chars
    if billable > limit:
        print(f"[停止] 本次需合成 {billable} 字，超过上限 {limit}。确认后用 --max-chars 提高上限。", file=sys.stderr)
        return 2
    cost = estimated_cost(units, config)
    print(f"预计计费字符 {units}，预计费用 {'未知' if cost is None else f'¥{cost}'}（以账单为准）")
    api_key = load_api_key() if billable else ""
    results = []
    for item in plan:
        meta = item["cached"] or synthesize_to_files(item["segment"]["text"], item["voice"], options, api_key, item["audio_path"])
        status = "缓存" if item["cached"] else "合成"
        print(f"{status} {item['segment']['id']:<16} {meta['duration_ms'] / 1000:>6.2f}s  {item['segment']['text'][:30]}")
        results.append({"id": item["segment"]["id"], "cached": bool(item["cached"]), **meta})
    # 实际计费字符以接口返回的 usage_characters 为准，只统计本次真正调用的段
    actual_units = sum(r["usage_characters"] or 0 for r in results if not r["cached"])
    summary = {
        "segments": results,
        "synthesized_text_chars": billable,
        "estimated_billing_chars": units,
        "usage_characters": actual_units,
        "estimated_cost_cny": estimated_cost(actual_units, config),
        "price_source": config.raw.get("priceSource"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_atomic(out_dir / "batch-result.json", json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"))
    print(f"\n本次实际计费字符 {actual_units}，估算费用 ¥{summary['estimated_cost_cny']}；结果清单：{out_dir / 'batch-result.json'}")
    return 0


def command_say(args: argparse.Namespace, config: SkillConfig) -> int:
    text = args.text if args.text else Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("文本为空")
    options = config.options(args.subtitles or config.raw.get("subtitles"))
    voice = config.voice(args.role)
    audio_path = Path(args.out).resolve()
    cached = None if args.force else cached_meta(audio_path, request_hash(text, voice, options))
    if cached is None and len(text) > config.max_chars:
        print(f"[停止] 文本 {len(text)} 字，超过上限 {config.max_chars}", file=sys.stderr)
        return 2
    meta = cached or synthesize_to_files(text, voice, options, load_api_key(), audio_path)
    print(f"{'缓存命中' if cached else '已合成'}：{audio_path}（{meta['duration_ms'] / 1000:.2f}s，字幕：{meta['subtitle_file'] or '无'}）")
    return 0


def command_check(args: argparse.Namespace, config: SkillConfig) -> int:
    """只调用免费的音色查询接口：验证密钥、地址与已配置音色是否可用，不产生合成费用。"""
    voices = list_voices(load_api_key(), "all")
    available = {voice["voice_id"] for voice in voices}
    print(f"密钥可用，接口地址 {api_host()}，账号可用音色 {len(voices)} 个")
    missing = [f"{name}={voice.voice_id}" for name, voice in config.roles.items() if voice.voice_id not in available]
    for name, voice in config.roles.items():
        print(f"  角色 {name:<10} {voice.voice_id:<45} {'可用' if voice.voice_id in available else '不可用'}")
    return 1 if missing else 0


def describe_voice(voice: dict[str, Any]) -> str:
    description = voice.get("description") or []
    text = "；".join(description) if isinstance(description, list) else str(description)
    return f"{voice.get('voice_name') or '-'}｜{text}"


def matching_voices(voices: list[dict[str, Any]], keyword: str | None) -> list[dict[str, Any]]:
    if not keyword:
        return voices
    return [voice for voice in voices if keyword.lower() in f"{voice['voice_id']} {describe_voice(voice)}".lower()]


def command_voices(args: argparse.Namespace, config: SkillConfig) -> int:
    voices = list_voices(load_api_key(), args.type)
    cache_path = default_out_dir() / "voices.json"
    write_atomic(cache_path, json.dumps(voices, ensure_ascii=False, indent=2).encode("utf-8"))
    matched = matching_voices(voices, args.match)
    for voice in matched:
        print(f"{voice['voice_id']:<50} {describe_voice(voice)}")
    print(f"\n共 {len(matched)} / {len(voices)} 个音色；完整列表：{cache_path}")
    return 0


def safe_filename(voice_id: str) -> str:
    # voice_id 可能含空格、括号，如 "Chinese (Mandarin)_News_Anchor"，Windows 下转成安全文件名
    return re.sub(r"[^\w\-]+", "_", voice_id).strip("_")


def command_audition(args: argparse.Namespace, config: SkillConfig) -> int:
    api_key = load_api_key()
    voice_ids = list(args.voices or [])
    if not voice_ids:
        voice_ids = [voice["voice_id"] for voice in matching_voices(list_voices(api_key, "system"), args.match)[: args.limit]]
    if not voice_ids:
        print("没有匹配的音色，请换个 --match 关键词或直接用 --voices 指定", file=sys.stderr)
        return 1
    options = config.options("none")
    out_dir = default_out_dir() / "audition"
    failures = 0
    for voice_id in voice_ids:
        audio_path = out_dir / f"{safe_filename(voice_id)}.{options.audio_format}"
        try:
            meta = synthesize_to_files(args.text, RoleVoice(voice_id=voice_id), options, api_key, audio_path)
        except MiniMaxError as error:  # 单个音色失败不影响其余音色试听
            failures += 1
            print(f"[失败] {voice_id}: {error}", file=sys.stderr)
            continue
        print(f"{voice_id:<50} {meta['duration_ms'] / 1000:>5.2f}s  -> {audio_path}")
    return 1 if failures == len(voice_ids) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MiniMax 配音技能")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="配置文件，默认技能目录 config.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="验证密钥与已配置音色（免费）")
    voices = sub.add_parser("voices", help="列出可用音色（免费）")
    voices.add_argument("--type", default="system", choices=["system", "voice_cloning", "voice_generation", "all"])
    voices.add_argument("--match", help="按 ID/名称/描述关键词筛选")
    say = sub.add_parser("say", help="合成一段文本（计费）")
    text_source = say.add_mutually_exclusive_group(required=True)
    text_source.add_argument("--text")
    text_source.add_argument("--text-file")
    say.add_argument("--out", required=True, help="输出音频路径，如 out/minimax/test.mp3")
    say.add_argument("--role", help="config.json 中的角色名，默认 defaultRole")
    say.add_argument("--subtitles", choices=["word", "sentence", "none"])
    say.add_argument("--force", action="store_true", help="忽略缓存重新合成")
    batch = sub.add_parser("batch", help="按分段 JSON 批量合成（计费，命中缓存的段不再计费）")
    batch.add_argument("--segments", required=True)
    batch.add_argument("--out-dir", required=True)
    batch.add_argument("--subtitles", choices=["word", "sentence", "none"])
    batch.add_argument("--max-chars", type=int, help="覆盖 config.json 的 maxCharsPerRun")
    batch.add_argument("--force", action="store_true")
    audition = sub.add_parser("audition", help="为多个音色生成试听（计费）")
    audition.add_argument("--voices", nargs="+")
    audition.add_argument("--match")
    audition.add_argument("--limit", type=int, default=4, help="--match 时最多试听几个（默认 4，控制费用）")
    audition.add_argument("--text", default=DEFAULT_AUDITION_TEXT)
    return parser


COMMANDS = {
    "check": command_check,
    "voices": command_voices,
    "say": command_say,
    "batch": command_batch,
    "audition": command_audition,
}


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，被智能体管道读取时中文会乱码；统一输出 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        config = SkillConfig.load(Path(args.config))
        return COMMANDS[args.command](args, config)
    except (MiniMaxError, ValueError, OSError) as error:  # 配置、网络、鉴权错误给出一行明确提示
        print(f"[失败] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
