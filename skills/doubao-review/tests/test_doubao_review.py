"""
INPUT: scripts/ark_client.py、review_rules.py、doubao_review.py；手写的最小文稿、发布包与伪造的方舟 HTTP 响应
OUTPUT: 分档计价与上界、送审文本拼装、输出解析、原文核对与放行、缓存、预算闸门、结果不明计费、重试策略、review / waive 命令退出码的测试
POS: doubao-review 技能的回归测试（不联网、不计费、不读真实 .env、不写真实用量账本）：
     python -m unittest discover -s .claude/skills/doubao-review/tests
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import doubao_review  # noqa: E402
from ark_client import ArkClient, ArkError, BudgetExceeded, Pricing  # noqa: E402
from review_rules import Document, ReviewParseError, build_documents, make_items, parse_review, summarize  # noqa: E402

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text(encoding="utf-8"))
SPEECH = {"segments": [
    {"segment_id": "s01", "display_text": "新建一个 CLAUDE.md。", "spoken_text": "新建一个 Claude 点 M D。"},
    {"segment_id": "s02", "display_text": "评论区聊聊。", "spoken_text": "评论区聊聊。"},
]}
PUBLISH_MD = "# 发布包\n\n| 成片 | a.mp4 |\n\n## 标题\nAI 写标书\n\n## 话题\n#ClaudeCode\n\n## 发布前核对（不对外）\n- [ ] Telegram\n"


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}
        self.text = json.dumps(self._body, ensure_ascii=False)

    def json(self) -> dict[str, Any]:
        return self._body


def chat_body(items: list[dict[str, str]], summary: str = "整体风险", prompt_tokens: int = 1000, completion_tokens: int = 200) -> dict[str, Any]:
    content = json.dumps({"items": items, "summary": summary}, ensure_ascii=False)
    return {"model": "doubao-seed-2-0-lite-260428", "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens}}


def item(quote: str, risk: str = "high", category: str = "overseas_service", location: str = "speech.s01") -> dict[str, str]:
    return {"location": location, "quote": quote, "category": category, "risk": risk, "reason": "理由", "suggestion": "改成 AI Agent"}


class FakePost:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> FakeResponse:
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_client(tmp: str, responses: list[Any], budget: float | None = None) -> tuple[ArkClient, FakePost]:
    config = dict(CONFIG, monthlyBudgetCny=budget if budget is not None else CONFIG["monthlyBudgetCny"])
    post = FakePost(responses)
    client = ArkClient(config, api_key="test-key", cache_dir=Path(tmp) / "cache", usage_path=Path(tmp) / "usage.jsonl", post=post, sleep=lambda _: None)
    return client, post


class RulesTest(unittest.TestCase):
    def test_pricing_tiers(self) -> None:
        pricing = Pricing.from_config(CONFIG)
        self.assertAlmostEqual(pricing.cost(10_000, 1_000), (10_000 * 0.6 + 1_000 * 3.6) / 1_000_000)
        # 输入超过 32k 落入第二档，输入输出都按第二档计价；超出最高档按最高档
        self.assertAlmostEqual(pricing.cost(40_000, 1_000), (40_000 * 1.2 + 1_000 * 7.2) / 1_000_000)
        self.assertAlmostEqual(pricing.cost(1_000_000, 0), 1.8)

    def test_documents_split_scopes_and_skip_internal_sections(self) -> None:
        documents = build_documents(SPEECH, "脚本正文", {"title": "AI 出的文档\n总带底色？"}, PUBLISH_MD)
        self.assertEqual([document.scope for document in documents], ["script", "publish"])
        script, publish = documents[0].text, documents[1].text
        # 朗读文本与显示文本不同时两者都送审；相同时不重复
        self.assertIn("[speech.s01.朗读] 新建一个 Claude 点 M D。", script)
        self.assertNotIn("[speech.s02.朗读]", script)
        self.assertIn("[cover.title] AI 出的文档 总带底色？", script)
        self.assertIn("#ClaudeCode", publish)
        self.assertNotIn("Telegram", publish)
        self.assertEqual(len(build_documents(SPEECH, "脚本", None, None)), 1)

    def test_parse_review_strips_fence_and_rejects_bad_fields(self) -> None:
        parsed = parse_review("```json\n" + json.dumps({"items": [item("CLAUDE.md")], "summary": "s"}) + "\n```")
        self.assertEqual(parsed["items"][0]["quote"], "CLAUDE.md")
        with self.assertRaises(ReviewParseError):
            parse_review(json.dumps({"items": [dict(item("x"), risk="critical")], "summary": ""}))
        with self.assertRaises(ReviewParseError):
            parse_review("不是 JSON")

    def test_quote_check_and_waiver(self) -> None:
        document = Document("script", "[speech.s01] 新建一个 CLAUDE.md。")
        parsed = {"items": [item("新建一个 CLAUDE.md"), item("去 Telegram 找我", category="blocked_app")], "summary": ""}
        items = make_items("script", parsed, document, [])
        self.assertEqual([entry["quote_found"] for entry in items], [True, False])
        self.assertTrue(summarize(items)[1])
        waiver = {"scope": "script", "category": "overseas_service", "quote": "新建一个CLAUDE.md", "reason": "抖音能搜到 Claude"}
        waived = make_items("script", {"items": parsed["items"][:1], "summary": ""}, document, [waiver])
        counts, blocked = summarize(waived)
        self.assertEqual((counts["high"], counts["waived"], blocked), (0, 1, False))


class ClientTest(unittest.TestCase):
    def test_cache_hit_does_not_post_again(self) -> None:
        with TemporaryDirectory() as tmp:
            client, post = make_client(tmp, [FakeResponse(200, chat_body([]))])
            payload = client.build_payload([{"role": "user", "content": "审核"}], None)
            first = client.chat(payload)
            second = client.chat(payload)
            self.assertEqual((post.calls, first.cached, second.cached), (1, False, True))
            self.assertAlmostEqual(first.cost_cny, (1000 * 0.6 + 200 * 3.6) / 1_000_000)
            self.assertEqual(client.usage.entries()[0]["status"], "settled")

    def test_budget_gate_blocks_before_sending(self) -> None:
        with TemporaryDirectory() as tmp:
            client, post = make_client(tmp, [], budget=0.000001)
            with self.assertRaises(BudgetExceeded):
                client.chat(client.build_payload([{"role": "user", "content": "审核"}], None))
            self.assertEqual(post.calls, 0)

    def test_unknown_result_is_charged_at_bound_and_config_errors_not_retried(self) -> None:
        with TemporaryDirectory() as tmp:
            client, post = make_client(tmp, [requests.ReadTimeout("读超时"), FakeResponse(401, {"error": "bad key"})])
            payload = client.build_payload([{"role": "user", "content": "审核"}], None)
            with self.assertRaises(ArkError) as caught:
                client.chat(payload)
            self.assertEqual(caught.exception.status_code, 401)
            self.assertEqual(post.calls, 2)
            entry = client.usage.entries()[0]
            # 结果不明的请求按上界占用预算，不记 0
            self.assertEqual(entry["status"], "unknown")
            self.assertAlmostEqual(entry["cost_cny"], round(client.pricing.bound(payload)[2], 8))

    def test_rate_limit_retried(self) -> None:
        with TemporaryDirectory() as tmp:
            client, post = make_client(tmp, [FakeResponse(429), FakeResponse(200, chat_body([]))])
            client.chat(client.build_payload([{"role": "user", "content": "审核"}], None))
            self.assertEqual(post.calls, 2)


class CommandTest(unittest.TestCase):
    def test_review_blocks_on_high_then_waive_unblocks(self) -> None:
        with TemporaryDirectory() as tmp:
            variant = Path(tmp) / "projects" / "p" / "variants" / "douyin"
            variant.mkdir(parents=True)
            (variant / "speech.json").write_text(json.dumps(SPEECH, ensure_ascii=False), encoding="utf-8")
            (variant / "script.md").write_text("# 脚本\n新建一个 CLAUDE.md", encoding="utf-8")
            (variant / "publish.md").write_text(PUBLISH_MD, encoding="utf-8")
            responses = [FakeResponse(200, chat_body([item("新建一个 CLAUDE.md")])),
                         FakeResponse(200, chat_body([item("#ClaudeCode", risk="medium", location="publish.md#话题")]))]
            client, post = make_client(tmp, responses)
            original = doubao_review.ArkClient
            doubao_review.ArkClient = lambda config: client
            try:
                self.assertEqual(doubao_review.main(["review", "--variant-dir", str(variant)]), 1)
                report = json.loads((variant / "doubao-review.json").read_text(encoding="utf-8"))
                self.assertEqual((report["counts"]["high"], report["counts"]["medium"], report["blocked"]), (1, 1, True))
                self.assertEqual(report["usage"]["requests"], 2)
                self.assertEqual(doubao_review.main(["waive", "--variant-dir", str(variant), "--item", "script-01", "--reason", "抖音能搜到 Claude"]), 0)
                # 重跑命中缓存、不再计费，放行记录继续生效
                self.assertEqual(doubao_review.main(["review", "--variant-dir", str(variant)]), 0)
                self.assertEqual(post.calls, 2)
            finally:
                doubao_review.ArkClient = original


if __name__ == "__main__":
    unittest.main()
