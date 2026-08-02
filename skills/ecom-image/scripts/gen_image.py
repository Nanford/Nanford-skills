#!/usr/bin/env python3
"""Generate ecommerce base images through supported external providers.

The Codex App image tool is intentionally not called from Python. When that tool
is available, the ecom-image skill calls it directly. This script is
the network-enabled fallback for local CLI environments.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR.parent / "assets" / "providers.json"
NO_TEXT_GUARD = (
    "no text, no letters, no words, no logo, no watermark, no typography, "
    "clean commercial composition"
)
GEMINI_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")


class ProviderError(RuntimeError):
    """Raised for actionable provider or response errors."""


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def provider_value(config: dict[str, Any], field: str) -> str:
    env_name = config.get(f"{field}_env")
    return os.getenv(env_name, config.get(field, "")) if env_name else config.get(field, "")


def post_json(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: int,
    retries: int = 2,
) -> dict[str, Any]:
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            # Retry only transient throttling and upstream failures. Bad requests
            # should fail immediately so the user sees the real provider message.
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == retries:
                raise ProviderError(f"HTTP {exc.code}: {detail[:1000]}") from exc
        except urllib.error.URLError as exc:
            if attempt == retries:
                raise ProviderError(f"网络请求失败：{exc.reason}") from exc
        time.sleep(2**attempt)
    raise ProviderError("请求失败")


def download(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "ecom-skill/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def local_image_block(path: Path) -> tuple[str, str]:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return mime, base64.b64encode(path.read_bytes()).decode("ascii")


def resolve_references(job: dict[str, Any], jobs_dir: Path) -> list[tuple[str, str, str]]:
    resolved = []
    for value in job.get("reference_images", []):
        if value.startswith(("http://", "https://", "data:")):
            resolved.append(("remote", value, ""))
            continue
        path = (jobs_dir / value).resolve()
        if not path.is_file():
            raise ProviderError(f"参考图不存在：{path}")
        mime, data = local_image_block(path)
        resolved.append(("local", data, mime))
    return resolved


def guarded_prompt(job: dict[str, Any]) -> str:
    prompt = str(job.get("base_prompt", "")).strip()
    if not prompt:
        raise ProviderError(f"任务 {job.get('id')} 缺少 base_prompt")
    if "no text" not in prompt.lower():
        prompt = f"{prompt}, {NO_TEXT_GUARD}"
    return prompt


def dimensions(job: dict[str, Any]) -> tuple[int, int]:
    value = job.get("size", [2048, 2048])
    if not isinstance(value, list) or len(value) != 2:
        raise ProviderError(f"任务 {job.get('id')} 的 size 必须是 [width, height]")
    return int(value[0]), int(value[1])


def closest_ratio(width: int, height: int) -> str:
    target = width / height
    return min(GEMINI_RATIOS, key=lambda item: abs(target - _ratio_value(item)))


def _ratio_value(value: str) -> float:
    left, right = value.split(":", 1)
    return int(left) / int(right)


def image_size_label(width: int, height: int) -> str:
    longest = max(width, height)
    if longest >= 3072:
        return "4K"
    if longest >= 1536:
        return "2K"
    return "1K"


def qwen_render(
    config: dict[str, Any], job: dict[str, Any], refs: list[tuple[str, str, str]], timeout: int
) -> tuple[bytes, str | None]:
    api_key = require_key(config)
    content: list[dict[str, str]] = []
    for kind, value, mime in refs[:3]:
        image_value = value if kind == "remote" else f"data:{mime};base64,{value}"
        content.append({"image": image_value})
    content.append({"text": guarded_prompt(job)})
    width, height = dimensions(job)
    options = job.get("provider_options", {})
    body = {
        "model": provider_value(config, "model"),
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {
            "prompt_extend": options.get("prompt_extend", True),
            "n": 1,
            "size": f"{width}*{height}",
            "watermark": options.get("watermark", False),
        },
    }
    if options.get("negative_prompt"):
        body["parameters"]["negative_prompt"] = options["negative_prompt"]
    payload = post_json(
        provider_value(config, "endpoint"),
        {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        body,
        timeout,
    )
    try:
        url = payload["output"]["choices"][0]["message"]["content"][0]["image"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(provider_message(payload)) from exc
    return download(url, timeout), payload.get("request_id")


def gemini_render(
    config: dict[str, Any], job: dict[str, Any], refs: list[tuple[str, str, str]], timeout: int
) -> tuple[bytes, str | None]:
    api_key = require_key(config)
    input_blocks: list[dict[str, str]] = [{"type": "text", "text": guarded_prompt(job)}]
    for kind, value, mime in refs:
        if kind == "remote":
            raw = download(value, timeout)
            mime = mimetypes.guess_type(value.split("?", 1)[0])[0] or "image/png"
            value = base64.b64encode(raw).decode("ascii")
        input_blocks.append({"type": "image", "mime_type": mime, "data": value})
    width, height = dimensions(job)
    body = {
        "model": provider_value(config, "model"),
        "input": input_blocks,
        "response_format": {
            "type": "image",
            "mime_type": "image/png",
            "aspect_ratio": job.get("aspect_ratio") or closest_ratio(width, height),
            "image_size": job.get("provider_options", {}).get("image_size", image_size_label(width, height)),
        },
    }
    payload = post_json(
        provider_value(config, "endpoint"),
        {"Content-Type": "application/json", "x-goog-api-key": api_key},
        body,
        timeout,
    )
    image_data = find_image_data(payload)
    if not image_data:
        raise ProviderError(provider_message(payload))
    return base64.b64decode(image_data), payload.get("id")


def volcengine_render(
    config: dict[str, Any], job: dict[str, Any], refs: list[tuple[str, str, str]], timeout: int
) -> tuple[bytes, str | None]:
    api_key = require_key(config)
    width, height = dimensions(job)
    options = job.get("provider_options", {})
    images = []
    for kind, value, mime in refs:
        images.append(value if kind == "remote" else f"data:{mime};base64,{value}")
    body: dict[str, Any] = {
        "model": provider_value(config, "model"),
        "prompt": guarded_prompt(job),
        "size": options.get("size", image_size_label(width, height)),
        "response_format": "b64_json",
        "watermark": options.get("watermark", False),
        "stream": False,
    }
    if images:
        body["image"] = images
    payload = post_json(
        provider_value(config, "endpoint"),
        {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        body,
        timeout,
    )
    try:
        item = payload["data"][0]
        if item.get("b64_json"):
            blob = base64.b64decode(item["b64_json"])
        else:
            blob = download(item["url"], timeout)
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(provider_message(payload)) from exc
    return blob, payload.get("id") or payload.get("request_id")


def require_key(config: dict[str, Any]) -> str:
    name = config["api_key_env"]
    value = os.getenv(name, "")
    if not value:
        raise ProviderError(f"未设置环境变量 {name}")
    return value


def find_image_data(payload: Any) -> str | None:
    """Find Gemini image blocks without coupling to one response envelope version."""
    if isinstance(payload, dict):
        if payload.get("type") == "image" and isinstance(payload.get("data"), str):
            return payload["data"]
        inline = payload.get("inlineData") or payload.get("inline_data")
        if isinstance(inline, dict) and isinstance(inline.get("data"), str):
            return inline["data"]
        output = payload.get("output_image")
        if isinstance(output, dict) and isinstance(output.get("data"), str):
            return output["data"]
        for value in payload.values():
            found = find_image_data(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = find_image_data(value)
            if found:
                return found
    return None


def provider_message(payload: dict[str, Any]) -> str:
    return str(payload.get("message") or payload.get("error") or payload)[:1000]


def extension_for(blob: bytes) -> str:
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if blob.startswith(b"RIFF") and blob[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def prompt_digest(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def codex_handoff(jobs: list[dict[str, Any]], jobs_dir: Path, out_dir: Path) -> int:
    calls = []
    for job in jobs:
        local_refs = []
        for ref in job.get("reference_images", []):
            if ref.startswith(("http://", "https://", "data:")):
                raise ProviderError("Codex ImageGen 路由要求参考图具有本地文件路径")
            local_refs.append(str((jobs_dir / ref).resolve()))
        args: dict[str, Any] = {"prompt": guarded_prompt(job)}
        if local_refs:
            args["referenced_image_paths"] = local_refs
        calls.append({"job_id": job["id"], "tool": "image_gen__imagegen", "arguments": args})
    write_json(out_dir / "codex_imagegen_calls.json", {"calls": calls})
    write_json(out_dir / "render_manifest.json", {
        "schema_version": "1.0",
        "provider": "codex-imagegen",
        "status": "handoff_required",
        "items": [{"job_id": item["job_id"], "status": "pending"} for item in calls],
    })
    print(f"已生成 Codex ImageGen 调用清单：{out_dir / 'codex_imagegen_calls.json'}")
    return 3


def main() -> int:
    parser = argparse.ArgumentParser(description="通过外部 API 生成无文字电商底图")
    parser.add_argument("--jobs", required=True, help="image_jobs.json 路径")
    parser.add_argument("--out", required=True, help="底图输出目录")
    parser.add_argument("--provider", default="auto")
    parser.add_argument("--only", action="append", help="仅运行指定 job id，可重复")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    jobs_path = Path(args.jobs).resolve()
    jobs_doc = load_json(jobs_path)
    jobs = [job for job in jobs_doc.get("jobs", []) if not args.only or job.get("id") in args.only]
    if not jobs:
        raise ProviderError("没有可执行的出图任务")

    config_doc = load_json(CONFIG_PATH)
    provider_name = args.provider
    if provider_name == "auto":
        provider_name = os.getenv("ECOM_IMAGE_PROVIDER", config_doc["default_external"])
    provider = config_doc["providers"].get(provider_name)
    if not provider:
        raise ProviderError(f"未知 provider：{provider_name}")

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if provider["kind"] == "codex_tool":
        return codex_handoff(jobs, jobs_path.parent, out_dir)

    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "provider": provider_name,
        "model": provider_value(provider, "model"),
        "status": "dry_run" if args.dry_run else "running",
        "items": [],
    }
    renderers = {"qwen": qwen_render, "gemini": gemini_render, "volcengine": volcengine_render}
    renderer = renderers[provider["kind"]]

    failures = 0
    for job in jobs:
        prompt = guarded_prompt(job)
        item = {"job_id": job.get("id"), "prompt_sha256": prompt_digest(prompt)}
        if args.dry_run:
            width, height = dimensions(job)
            item.update({"status": "planned", "size": [width, height], "references": len(job.get("reference_images", []))})
            manifest["items"].append(item)
            continue
        try:
            refs = resolve_references(job, jobs_path.parent)
            blob, request_id = renderer(provider, job, refs, args.timeout)
            output = out_dir / f"{job['id']}{extension_for(blob)}"
            output.write_bytes(blob)
            item.update({"status": "success", "output": str(output), "request_id": request_id})
            print(f"完成：{output}")
        except Exception as exc:  # Keep successful siblings available for resumable reruns.
            failures += 1
            item.update({"status": "failed", "error": str(exc)})
            print(f"失败：{job.get('id')} — {exc}")
        manifest["items"].append(item)

    manifest["status"] = "failed" if failures else ("dry_run" if args.dry_run else "complete")
    write_json(out_dir / "render_manifest.json", manifest)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProviderError as exc:
        print(f"错误：{exc}")
        raise SystemExit(2)
