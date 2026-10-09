"""
INPUT: TypeSafe HTTP 接口（POST /v1/systemone 按输入 token 计费、GET /v1/models 免费）；config.json（模型别名、单价、每月预算）；
       API Key 依次取自环境变量 TYPESAFE_API_KEY、技能目录 .env、工作区根目录 .env（均已被 .gitignore 排除）
OUTPUT: JevClient.ask() 带缓存与预算闸门的一次判断请求；list_models() 免费验证密钥；request_hash()、max_input_tokens() 纯函数；
        UsageLog 本月用量账本（logs/jev-check/usage.jsonl）；JevError / BudgetExceeded
POS: Jev 接口的唯一封装层。jev_check.py 只调用这里，接口或计费规则变动时只改本文件。
     来源：https://docs.typesafe.ai/api.md 与 /models.md（2026-09-29 核验）。
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
DEFAULT_API_BASE = "https://api.typesafe.ai"
REQUEST_TIMEOUT_SEC = 30
# AGENTS.md 第 13 节：瞬时错误最多自动重试 2 次并退避
MAX_ATTEMPTS = 3
# 官方文档：429 限流、529 过载需要退避重试；5xx 视同瞬时故障。401 密钥无效、422 请求体不合法重试也不会成功。
RETRYABLE_HTTP = {429, 500, 502, 503, 504, 529}
HTTP_HINTS = {
    401: "密钥缺失或无效，请检查 TYPESAFE_API_KEY 是否为 console.typesafe.ai/keys 生成的密钥",
    422: "请求体未通过校验（字段缺失或问题定义不合法）",
    429: "超过速率限制",
    529: "TypeSafe 服务暂时过载",
}
# 本项目工作时区（与 DATA_CONTRACTS 默认观察时区同为 UTC+8），预算按这个时区的自然月累计
LOCAL_TZ = timezone(timedelta(hours=8))


class JevError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(f"{message}（HTTP {status_code}）" if status_code is not None else message)
        self.status_code = status_code


class BudgetExceeded(JevError):
    pass


def _read_dotenv_key(env_path: Path, name: str) -> str:
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        key, sep, value = raw_line.partition("=")
        if sep and key.strip() == name:
            return value.strip().strip("\"'")
    return ""


def load_api_key() -> str:
    """优先环境变量，其次技能目录 .env，最后工作区根目录 .env；密钥不写进代码、日志和 Git。"""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    for env_path in (SKILL_ROOT / ".env", *([REPO_ROOT / ".env"] if REPO_ROOT else [])):
        if key:
            break
        key = _read_dotenv_key(env_path, "TYPESAFE_API_KEY")
    if not key:
        raise JevError("未找到 TYPESAFE_API_KEY：请设置环境变量，或在工作区根目录 .env 中写入 TYPESAFE_API_KEY=你的密钥")
    return key


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(payload: dict[str, Any]) -> str:
    """缓存键 = 模型别名 + state + 全部问题定义。别名背后的版本升级不会让缓存失效，所以缓存记录里另存返回的真实版本。"""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def max_input_tokens(payload: dict[str, Any], per_question_overhead: int, base_overhead: int) -> int:
    """
    预算闸门用的输入 token 上界。BPE 分词每个 token 至少覆盖 1 个字节，所以请求正文的 UTF-8 字节数是正文 token 数的上界；
    服务端给每个问题和整个请求套的模板开销不可见，用 config.json 里的两个常数兜住（数值来自 2026-09-29 试点实测，见 SKILL.md）。
    """
    body_bytes = len(canonical_json(payload).encode("utf-8"))
    return body_bytes + per_question_overhead * len(payload.get("questions", {})) + base_overhead


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


@dataclass(frozen=True)
class Pricing:
    usd_per_million_input: float
    monthly_budget_usd: float
    per_question_overhead: int
    base_overhead: int

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Pricing:
        return cls(float(config["pricePerMillionInputTokensUsd"]), float(config["monthlyBudgetUsd"]),
                   int(config["tokenBound"]["perQuestionOverhead"]), int(config["tokenBound"]["baseOverhead"]))

    def cost(self, tokens: int) -> float:
        return tokens * self.usd_per_million_input / 1_000_000


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

    def month_spent_usd(self, month: str) -> float:
        return sum(entry["cost_usd"] for entry in self.entries() if entry["month"] == month)

    def append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


@dataclass
class AskResult:
    body: dict[str, Any]
    request_hash: str
    cached: bool
    input_tokens: int
    cost_usd: float


class JevClient:
    def __init__(self, config: dict[str, Any], api_key: str | None = None, cache_dir: Path | None = None, usage_path: Path | None = None,
                 post: Callable[..., requests.Response] = requests.post, sleep: Callable[[float], None] = time.sleep) -> None:
        self.config = config
        self.pricing = Pricing.from_config(config)
        self.api_base = os.environ.get("TYPESAFE_API_BASE", config.get("apiBase", DEFAULT_API_BASE)).rstrip("/")
        self._api_key = api_key
        # 缓存与月度用量账本必须在工作区里：账本换位置会从 0 记起，月度上限就失效了
        if cache_dir is None or usage_path is None:
            root = require_workspace(REPO_ROOT, "Jev 检查的缓存与用量账本", JevError)
        self.cache_dir = cache_dir or root / ".cache" / "jev-check" / "responses"
        self.usage = UsageLog(usage_path or root / "logs" / "jev-check" / "usage.jsonl")
        self._post = post
        self._sleep = sleep

    @property
    def api_key(self) -> str:
        if self._api_key is None:
            self._api_key = load_api_key()
        return self._api_key

    def build_payload(self, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        return {"model": self.config["model"], "state": state, "questions": questions}

    def is_cached(self, payload: dict[str, Any]) -> bool:
        return (self.cache_dir / f"{request_hash(payload)}.json").exists()

    def ask(self, payload: dict[str, Any], use_cache: bool = True) -> AskResult:
        digest = request_hash(payload)
        cache_path = self.cache_dir / f"{digest}.json"
        if use_cache and cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return AskResult(cached["body"], digest, True, 0, 0.0)
        self._check_budget(payload)
        body = self._post_with_retries(payload, digest)
        tokens = int((body.get("usage") or {}).get("input_tokens") or 0)
        cost = self.pricing.cost(tokens)
        self._record(digest, "settled", tokens, cost, body.get("model"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps({"request_hash": digest, "saved_at": now_local().isoformat(timespec="seconds"), "body": body},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(cache_path)
        return AskResult(body, digest, False, tokens, cost)

    def _check_budget(self, payload: dict[str, Any]) -> None:
        # 已发生（含结果不明的占用）+ 下次请求上界 ≤ 本月上限；同步调用，没有其他在途请求
        month = now_local().strftime("%Y-%m")
        spent = self.usage.month_spent_usd(month)
        next_max = self.pricing.cost(max_input_tokens(payload, self.pricing.per_question_overhead, self.pricing.base_overhead))
        if spent + next_max > self.pricing.monthly_budget_usd:
            raise BudgetExceeded(f"本月 Jev 已用 {spent:.6f} 美元，下一次请求最多 {next_max:.6f} 美元，会超过每月上限 "
                                 f"{self.pricing.monthly_budget_usd} 美元；停止新增计费调用")

    def _record(self, digest: str, status: str, tokens: int, cost: float, model: str | None) -> None:
        now = now_local()
        self.usage.append({"recorded_at": now.isoformat(timespec="seconds"), "month": now.strftime("%Y-%m"), "request_hash": digest,
                           "status": status, "model": model, "input_tokens": tokens, "cost_usd": round(cost, 9)})

    def _post_with_retries(self, payload: dict[str, Any], digest: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error: JevError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._post(f"{self.api_base}/v1/systemone", json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
            except requests.ConnectTimeout as error:
                # 连接都没建立，请求没有发出，不会计费
                last_error = JevError(f"连接 TypeSafe 超时：{error}")
            except requests.RequestException as error:
                # 请求可能已送达并计费但结果没拿到：按上界占用预算，不记 0
                bound = max_input_tokens(payload, self.pricing.per_question_overhead, self.pricing.base_overhead)
                self._record(digest, "unknown", bound, self.pricing.cost(bound), None)
                last_error = JevError(f"请求 TypeSafe 失败，结果不明：{error}")
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as error:
                        raise JevError(f"TypeSafe 返回的不是 JSON：{error}", 200) from error
                last_error = JevError(HTTP_HINTS.get(response.status_code, response.text[:200]), response.status_code)
                if response.status_code not in RETRYABLE_HTTP:
                    raise last_error
            if attempt < MAX_ATTEMPTS:
                self._sleep(2 ** (attempt - 1))
        assert last_error is not None
        raise last_error


def list_models(api_base: str, api_key: str, get: Callable[..., requests.Response] = requests.get) -> list[dict[str, Any]]:
    """免费接口：列出账号可用的模型别名，用于验证密钥与连通性。"""
    try:
        response = get(f"{api_base.rstrip('/')}/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=REQUEST_TIMEOUT_SEC)
    except requests.RequestException as error:
        raise JevError(f"连接 TypeSafe 失败：{error}") from error
    if response.status_code != 200:
        raise JevError(HTTP_HINTS.get(response.status_code, response.text[:200]), response.status_code)
    return list(response.json().get("models", []))
