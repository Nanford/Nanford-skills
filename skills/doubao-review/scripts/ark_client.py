"""
INPUT: 火山方舟 Chat API（POST {apiBase}/chat/completions，按输入与输出 token 计费）；config.json（模型、分档单价、每月预算）；
       API Key 依次取自环境变量 ARK_API_KEY、技能目录 .env、工作区根目录 .env（均已被 .gitignore 排除）
OUTPUT: ArkClient.chat() 带缓存与预算闸门的一次对话请求；Pricing（分档计价与上界）；UsageLog 本月用量账本（logs/doubao-review/usage.jsonl）；
        load_api_key()、request_hash()、max_input_tokens()；ArkError / BudgetExceeded
POS: 火山方舟接口的唯一封装层。doubao_review.py 只调用这里，接口或计费规则变动时只改本文件。
     接口依据：方舟 Chat API 文档（Bearer 鉴权、thinking、response_format），2026-09-30 经搜索结果核对，首次真实调用后复核。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from workspace import find_workspace, require_workspace

SKILL_ROOT = Path(__file__).resolve().parent.parent
# 工作区根目录（.env、.cache/、logs/ 用量账本所在）；技能可能装在工作区外，找不到时为 None，见 workspace.py
REPO_ROOT = find_workspace()
KEY_NAME = "ARK_API_KEY"
REQUEST_TIMEOUT_SEC = 120
# AGENTS.md 第 13 节：瞬时错误最多自动重试 2 次并退避
MAX_ATTEMPTS = 3
RETRYABLE_HTTP = {429, 500, 502, 503, 504}
# 401/403/404 是配置问题，重试也不会成功（AGENTS.md 第 13 节：配置错误不盲重试）
HTTP_HINTS = {
    400: "请求被拒绝（字段不合法；若提示 response_format 不支持，把 config.json 的 responseFormat 改为 json_object）",
    401: "密钥缺失或无效，请检查 .env 中的 ARK_API_KEY 是否为方舟控制台「API Key 管理」生成的密钥",
    403: "无权限：账号欠费、未实名，或该模型未在方舟控制台开通",
    404: "模型不存在：检查 config.json 的 model，并在方舟控制台「开通管理」开通该模型",
    429: "超过速率或 token 限额",
}
# 本项目工作时区（与 DATA_CONTRACTS 默认观察时区同为 UTC+8），预算按这个时区的自然月累计
LOCAL_TZ = timezone(timedelta(hours=8))


class ArkError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(f"{message}（HTTP {status_code}）" if status_code is not None else message)
        self.status_code = status_code


class BudgetExceeded(ArkError):
    pass


def _read_dotenv_key(env_path: Path, name: str) -> str:
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        key, sep, value = raw_line.partition("=")
        if sep and key.strip() == name:
            return value.strip().strip("\"'")
    return ""


def find_api_key() -> str:
    """优先环境变量，其次技能目录 .env，最后工作区根目录 .env；找不到返回空串。密钥不写进代码、日志和 Git。"""
    key = os.environ.get(KEY_NAME, "").strip()
    for env_path in (SKILL_ROOT / ".env", *([REPO_ROOT / ".env"] if REPO_ROOT else [])):
        if key:
            break
        key = _read_dotenv_key(env_path, KEY_NAME)
    return key


def load_api_key() -> str:
    key = find_api_key()
    if not key:
        raise ArkError(f"未找到 {KEY_NAME}：请在工作区根目录 .env 中写入 {KEY_NAME}=你的密钥（方舟控制台「API Key 管理」生成）")
    return key


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(payload: dict[str, Any]) -> str:
    """缓存键 = 完整请求体（模型 ID、提示词、文稿、输出格式、参数）。任何一项变化都会重新请求。"""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def max_input_tokens(payload: dict[str, Any], overhead: int) -> int:
    """
    预算闸门用的输入 token 上界。BPE 分词每个 token 至少覆盖 1 个字节，所以请求正文的 UTF-8 字节数是正文 token 数的上界
    （中文一个字 3 字节、通常不到 1 个 token，上界偏宽但不会少算）；消息模板开销用 config.json 的 tokenBoundOverhead 兜住。
    """
    return len(canonical_json(payload["messages"]).encode("utf-8")) + overhead


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


@dataclass(frozen=True)
class Pricing:
    tiers: list[dict[str, float]]
    monthly_budget_cny: float
    overhead: int

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Pricing:
        tiers = sorted(config["priceTiersCnyPerMillion"], key=lambda tier: tier["maxInputTokens"])
        return cls(tiers, float(config["monthlyBudgetCny"]), int(config["tokenBoundOverhead"]))

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        # 方舟按单次请求的输入长度落入的档位计价：输入与输出都用该档单价；超出最高档按最高档算
        tier = next((tier for tier in self.tiers if input_tokens <= tier["maxInputTokens"]), self.tiers[-1])
        return (input_tokens * tier["input"] + output_tokens * tier["output"]) / 1_000_000

    def bound(self, payload: dict[str, Any]) -> tuple[int, int, float]:
        input_bound, output_bound = max_input_tokens(payload, self.overhead), int(payload["max_tokens"])
        return input_bound, output_bound, self.cost(input_bound, output_bound)


class UsageLog:
    """
    本月用量账本，一行一次可能计费的请求。status：settled 为接口返回了真实 usage；unknown 为请求已发出但结果不明（读超时、连接中断），
    按上界占用预算、不记 0（AGENTS.md 第 13 节）。删除该文件会清零本月统计，所以放在 logs/ 而不是缓存目录。
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def month_spent_cny(self, month: str) -> float:
        return sum(entry["cost_cny"] for entry in self.entries() if entry["month"] == month)

    def append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


@dataclass
class ChatResult:
    body: dict[str, Any]
    request_hash: str
    cached: bool
    input_tokens: int
    output_tokens: int
    cost_cny: float

    @property
    def content(self) -> str:
        choices = self.body.get("choices") or [{}]
        return str((choices[0].get("message") or {}).get("content") or "")


class ArkClient:
    def __init__(self, config: dict[str, Any], api_key: str | None = None, cache_dir: Path | None = None, usage_path: Path | None = None,
                 post: Callable[..., requests.Response] = requests.post, sleep: Callable[[float], None] = time.sleep) -> None:
        self.config = config
        self.pricing = Pricing.from_config(config)
        self.api_base = os.environ.get("ARK_API_BASE", config["apiBase"]).rstrip("/")
        self._api_key = api_key
        # 缓存与月度用量账本必须在工作区里：账本换位置会从 0 记起，月度上限就失效了
        if cache_dir is None or usage_path is None:
            root = require_workspace(REPO_ROOT, "豆包审核的缓存与用量账本", ArkError)
        self.cache_dir = cache_dir or root / ".cache" / "doubao-review" / "responses"
        self.usage = UsageLog(usage_path or root / "logs" / "doubao-review" / "usage.jsonl")
        self._post = post
        self._sleep = sleep

    @property
    def api_key(self) -> str:
        if self._api_key is None:
            self._api_key = load_api_key()
        return self._api_key

    def build_payload(self, messages: list[dict[str, str]], response_format: dict[str, Any] | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.config["model"], "messages": messages, "temperature": self.config["temperature"],
                                   "max_tokens": self.config["maxOutputTokens"], "thinking": {"type": self.config["thinking"]}}
        if response_format:
            payload["response_format"] = response_format
        return payload

    def is_cached(self, payload: dict[str, Any]) -> bool:
        return (self.cache_dir / f"{request_hash(payload)}.json").exists()

    def chat(self, payload: dict[str, Any], use_cache: bool = True) -> ChatResult:
        digest = request_hash(payload)
        cache_path = self.cache_dir / f"{digest}.json"
        if use_cache and cache_path.exists():
            return ChatResult(json.loads(cache_path.read_text(encoding="utf-8"))["body"], digest, True, 0, 0, 0.0)
        self.check_budget([payload])
        body = self._post_with_retries(payload, digest)
        usage = body.get("usage") or {}
        input_tokens, output_tokens = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        cost = self.pricing.cost(input_tokens, output_tokens)
        self._record(digest, "settled", input_tokens, output_tokens, cost, body.get("model"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps({"request_hash": digest, "saved_at": now_local().isoformat(timespec="seconds"), "body": body},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(cache_path)
        return ChatResult(body, digest, False, input_tokens, output_tokens, cost)

    def check_budget(self, payloads: list[dict[str, Any]]) -> None:
        """已发生（含结果不明的占用）+ 这批请求的上界 ≤ 本月上限；同步调用，没有其他在途请求。"""
        month = now_local().strftime("%Y-%m")
        spent = self.usage.month_spent_cny(month)
        next_max = sum(self.pricing.bound(payload)[2] for payload in payloads)
        if spent + next_max > self.pricing.monthly_budget_cny:
            raise BudgetExceeded(f"本月豆包审核已用 ¥{spent:.4f}，这次请求最多 ¥{next_max:.4f}，会超过每月上限 "
                                 f"¥{self.pricing.monthly_budget_cny}；停止新增计费调用")

    def _record(self, digest: str, status: str, input_tokens: int, output_tokens: int, cost: float, model: str | None) -> None:
        now = now_local()
        self.usage.append({"recorded_at": now.isoformat(timespec="seconds"), "month": now.strftime("%Y-%m"), "request_hash": digest,
                           "status": status, "model": model, "input_tokens": input_tokens, "output_tokens": output_tokens,
                           "cost_cny": round(cost, 8)})

    def _send_once(self, payload: dict[str, Any], digest: str, headers: dict[str, str]) -> tuple[dict[str, Any] | None, ArkError]:
        try:
            response = self._post(f"{self.api_base}/chat/completions", json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
        except requests.ConnectTimeout as error:
            # 连接都没建立，请求没有发出，不会计费
            return None, ArkError(f"连接火山方舟超时：{error}")
        except requests.RequestException as error:
            # 请求可能已送达并计费但结果没拿到：按上界占用预算，不记 0
            input_bound, output_bound, cost_bound = self.pricing.bound(payload)
            self._record(digest, "unknown", input_bound, output_bound, cost_bound, None)
            return None, ArkError(f"请求火山方舟失败，结果不明：{error}")
        if response.status_code == 200:
            try:
                return response.json(), ArkError("")
            except ValueError as error:
                raise ArkError(f"火山方舟返回的不是 JSON：{error}", 200) from error
        error = ArkError(f"{HTTP_HINTS.get(response.status_code, '')} {response.text[:300]}".strip(), response.status_code)
        if response.status_code not in RETRYABLE_HTTP:
            raise error
        return None, error

    def _post_with_retries(self, payload: dict[str, Any], digest: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error = ArkError("未发出请求")
        for attempt in range(1, MAX_ATTEMPTS + 1):
            body, last_error = self._send_once(payload, digest, headers)
            if body is not None:
                return body
            if attempt < MAX_ATTEMPTS:
                self._sleep(2 ** (attempt - 1))
        raise last_error
