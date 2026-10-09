"""
INPUT: MiniMax 开放平台 HTTP 接口（/v1/t2a_v2 同步语音合成、/v1/get_voice 查询音色）；
       API Key 依次取自环境变量 MINIMAX_API_KEY、技能目录 .env、工作区根目录 .env（workspace.py 查找）（均已被 .gitignore 排除）
OUTPUT: synthesize() 合成一段配音，返回音频字节、接口时长、计费字符数与可选字幕文件；
        list_voices() 返回账号可用音色；build_t2a_payload() 构造请求体（纯函数，可单测）；
        RoleVoice 描述一个配音角色；MiniMaxError 携带错误码与 trace_id
POS: MiniMax 接口的唯一封装层。cli.py 只调用这里，接口变动时只改本文件。
     来源：桌面「视频/remotion-project/scripts/minimax_tts.py」（2026-09-23 已实测），
     本版新增字幕时间戳、计费字符数与多位置密钥查找。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from workspace import find_workspace

SKILL_ROOT = Path(__file__).resolve().parent.parent
# 工作区根目录（.env、out/ 所在）；技能可能装在工作区外，找不到时为 None，见 workspace.py
REPO_ROOT = find_workspace()
DEFAULT_API_HOST = "https://api.minimax.cn"
DEFAULT_MODEL = "speech-2.8-hd"
REQUEST_TIMEOUT_SEC = 60
MAX_ATTEMPTS = 3

# 仅这些错误码值得重试：未知错误、超时、RPM 限流、TPM 限流。
# 鉴权失败(1004)、参数错误(2013)、非法字符过多(1042)、余额不足(1008)重试也不会成功，直接报错。
RETRYABLE_STATUS_CODES = {1000, 1001, 1002, 1039}
STATUS_HINTS = {
    1002: "触发限流，请稍后再试",
    1004: "鉴权失败，请检查 MINIMAX_API_KEY 是否正确、是否为 platform.minimax.cn 的密钥",
    1008: "账户余额不足",
    1039: "触发 TPM 限流，请稍后再试",
    1042: "文本中非法字符超过 10%",
    2013: "请求参数不合法（检查 voice_id、emotion 与模型是否匹配）",
}

# 官方文档（2026-09-29 核验）：字幕仅对以下模型有效
SUBTITLE_MODELS = {
    "speech-2.8-hd",
    "speech-2.8-turbo",
    "speech-2.6-hd",
    "speech-2.6-turbo",
    "speech-02-hd",
    "speech-02-turbo",
    "speech-01-hd",
    "speech-01-turbo",
}
SUBTITLE_TYPES = {"sentence", "word"}


class MiniMaxError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, trace_id: str | None = None) -> None:
        detail = f"{message}（status_code={status_code}, trace_id={trace_id}）" if status_code is not None else message
        super().__init__(detail)
        self.status_code = status_code
        self.trace_id = trace_id


@dataclass(frozen=True)
class RoleVoice:
    """一个配音角色 = 音色 + 语速/音量/语调/情绪。字段与接口 voice_setting 一一对应。"""

    voice_id: str
    speed: float = 1.0
    vol: float = 1.0
    pitch: int = 0
    # None 表示交给模型按文本自动判断情绪（官方建议一般不手动指定）
    emotion: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RoleVoice:
        if not raw.get("voice_id"):
            raise ValueError(f"角色配置缺少 voice_id: {raw}")
        return cls(
            voice_id=raw["voice_id"],
            speed=float(raw.get("speed", 1.0)),
            vol=float(raw.get("vol", 1.0)),
            pitch=int(raw.get("pitch", 0)),
            emotion=raw.get("emotion"),
        )


@dataclass(frozen=True)
class SynthesisOptions:
    model: str = DEFAULT_MODEL
    pronunciation: tuple[str, ...] = ()
    text_normalization: bool = False
    audio_format: str = "mp3"
    sample_rate: int = 32000
    bitrate: int = 128000
    subtitle_type: str | None = None  # None 表示不请求字幕


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    duration_ms: int
    usage_characters: int | None
    subtitle_url: str | None
    trace_id: str | None


def _read_dotenv_key(env_path: Path) -> str:
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        name, sep, value = raw_line.partition("=")
        if sep and name.strip() == "MINIMAX_API_KEY":
            return value.strip().strip("\"'")
    return ""


def load_api_key() -> str:
    """优先环境变量，其次技能目录 .env，最后工作区根目录 .env；密钥不写进代码、不进 Git。"""
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    for env_path in (SKILL_ROOT / ".env", *([REPO_ROOT / ".env"] if REPO_ROOT else [])):
        if key:
            break
        key = _read_dotenv_key(env_path)
    if not key:
        raise MiniMaxError("未找到 MINIMAX_API_KEY：请设置环境变量，或在工作区根目录 .env 中写入 MINIMAX_API_KEY=你的密钥")
    return key


def api_host() -> str:
    # 主地址不可用时可切到官方备用地址：MINIMAX_API_HOST=https://api-bj.minimaxi.com
    return os.environ.get("MINIMAX_API_HOST", DEFAULT_API_HOST).rstrip("/")


def _post_json(path: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    """发送请求并按 base_resp 判定成败；可重试的错误按 1s、2s 退避重试。"""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_error: MiniMaxError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(f"{api_host()}{path}", json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        except (requests.RequestException, ValueError) as error:  # 网络抖动 / 非 JSON 响应均视为可重试
            last_error = MiniMaxError(f"请求 {path} 失败: {error}")
        else:
            base_resp = body.get("base_resp") or {}
            status_code = int(base_resp.get("status_code", -1))
            if status_code == 0:
                return body
            message = STATUS_HINTS.get(status_code, base_resp.get("status_msg") or "未知错误")
            last_error = MiniMaxError(message, status_code, body.get("trace_id"))
            if status_code not in RETRYABLE_STATUS_CODES:
                raise last_error
        if attempt < MAX_ATTEMPTS:
            time.sleep(attempt)
    assert last_error is not None
    raise last_error


def validate_options(options: SynthesisOptions) -> None:
    """在发请求之前拦截必然失败的组合，避免白白消耗额度。"""
    if options.subtitle_type is None:
        return
    if options.subtitle_type not in SUBTITLE_TYPES:
        raise ValueError(f"subtitle_type 只支持 {sorted(SUBTITLE_TYPES)}，收到 {options.subtitle_type}")
    if options.model not in SUBTITLE_MODELS:
        raise ValueError(f"模型 {options.model} 不支持字幕时间戳，可选：{sorted(SUBTITLE_MODELS)}")


def build_t2a_payload(text: str, voice: RoleVoice, options: SynthesisOptions = SynthesisOptions()) -> dict[str, Any]:
    voice_setting: dict[str, Any] = {
        "voice_id": voice.voice_id,
        "speed": voice.speed,
        "vol": voice.vol,
        "pitch": voice.pitch,
        "text_normalization": options.text_normalization,
    }
    if voice.emotion:
        voice_setting["emotion"] = voice.emotion
    payload: dict[str, Any] = {
        "model": options.model,
        "text": text,
        "stream": False,
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": options.sample_rate,
            "bitrate": options.bitrate,
            "format": options.audio_format,
            "channel": 1,
        },
        # hex 直接内嵌在响应里；url 形式 24 小时过期还要二次下载，没有必要
        "output_format": "hex",
    }
    if options.pronunciation:
        payload["pronunciation_dict"] = {"tone": list(options.pronunciation)}
    if options.subtitle_type:
        payload["subtitle_enable"] = True
        payload["subtitle_type"] = options.subtitle_type
    return payload


def synthesize(text: str, voice: RoleVoice, api_key: str, options: SynthesisOptions = SynthesisOptions()) -> SynthesisResult:
    validate_options(options)
    body = _post_json("/v1/t2a_v2", build_t2a_payload(text, voice, options), api_key)
    data = body.get("data") or {}
    audio_hex = data.get("audio")
    if not audio_hex:
        raise MiniMaxError("接口返回成功但没有音频数据", 0, body.get("trace_id"))
    extra = body.get("extra_info") or {}
    usage = extra.get("usage_characters")
    return SynthesisResult(
        audio=bytes.fromhex(audio_hex),
        # audio_length 是接口给出的精确时长（毫秒），比按文件大小估算可靠
        duration_ms=int(extra.get("audio_length", 0)),
        usage_characters=int(usage) if usage is not None else None,
        subtitle_url=data.get("subtitle_file") or None,
        trace_id=body.get("trace_id"),
    )


def download_subtitles(url: str) -> Any:
    """字幕以临时链接返回，必须立即下载保存；链接过期后无法再取。"""
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT_SEC)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt < MAX_ATTEMPTS:
                time.sleep(attempt)
    raise MiniMaxError(f"字幕文件下载失败: {last_error}")


def list_voices(api_key: str, voice_type: str = "system") -> list[dict[str, Any]]:
    """voice_type: system / voice_cloning / voice_generation / all。返回扁平化列表并标注来源类别。"""
    body = _post_json("/v1/get_voice", {"voice_type": voice_type}, api_key)
    voices: list[dict[str, Any]] = []
    for category in ("system_voice", "voice_cloning", "voice_generation"):
        for item in body.get(category) or []:
            voices.append({**item, "category": category})
    return voices
