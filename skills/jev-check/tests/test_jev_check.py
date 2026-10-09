"""
INPUT: scripts/jev_client.py、scripts/jev_rules.py、scripts/jev_check.py；unittest.mock 伪造 HTTP 响应（不联网、不计费、不读真实 .env、不写真实用量账本）
OUTPUT: 缓存、预算闸门、重试与结果不明记账、密钥查找、判定阈值、请求拆分、review 端到端的单元测试
POS: 技能的回归测试。改动 scripts/ 下任一文件后运行：
     python -m unittest discover -s .claude/skills/jev-check/tests
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import jev_check  # noqa: E402
import jev_client  # noqa: E402
from jev_client import BudgetExceeded, JevClient, JevError, canonical_json, max_input_tokens  # noqa: E402
from jev_rules import Probe, build_probes, first_sentence, judge  # noqa: E402

CONFIG = {
    "model": "jev-latest", "calibratedModel": "jev-1.13.0", "apiBase": "https://api.example.test",
    "pricePerMillionInputTokensUsd": 0.042, "priceSource": "测试", "monthlyBudgetUsd": 1.0,
    "tokenBound": {"perQuestionOverhead": 100, "baseOverhead": 200},
}
PAYLOAD = {"model": "jev-latest", "state": "每次投标都要熬夜排版？", "questions": {"hook_concrete": {"type": "noul", "instructions": "具体吗？"}}}


def fake_response(status: int, body: dict[str, Any] | None = None) -> mock.Mock:
    response = mock.Mock()
    response.status_code = status
    response.json.return_value = body or {}
    response.text = json.dumps(body or {"detail": "err"})
    return response


def ok_body(tokens: int = 500, model: str = "jev-1.13.0") -> dict[str, Any]:
    return {"model": model, "answers": {"hook_concrete": {"type": "noul", "noul": 0.9}}, "usage": {"input_tokens": tokens, "output_tokens": 30}}


class ClientTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.post = mock.Mock(return_value=fake_response(200, ok_body()))
        self.sleep = mock.Mock()

    def client(self, config: dict[str, Any] = CONFIG) -> JevClient:
        return JevClient(config, api_key="test-key", cache_dir=self.root / "cache", usage_path=self.root / "usage.jsonl", post=self.post, sleep=self.sleep)

    def usage_entries(self) -> list[dict[str, Any]]:
        path = self.root / "usage.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


class ClientTest(ClientTestBase):
    def test_settled_call_records_tokens_and_cost_then_cache_hit_skips_post(self) -> None:
        client = self.client()
        first = client.ask(PAYLOAD)
        second = client.ask(PAYLOAD)
        self.assertEqual(self.post.call_count, 1)
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertEqual(second.body["answers"], first.body["answers"])
        [entry] = self.usage_entries()
        self.assertEqual((entry["status"], entry["input_tokens"], entry["model"]), ("settled", 500, "jev-1.13.0"))
        self.assertAlmostEqual(entry["cost_usd"], 500 * 0.042 / 1_000_000)

    def test_no_cache_requests_again(self) -> None:
        client = self.client()
        client.ask(PAYLOAD)
        client.ask(PAYLOAD, use_cache=False)
        self.assertEqual(self.post.call_count, 2)

    def test_budget_exceeded_stops_before_post(self) -> None:
        with self.assertRaises(BudgetExceeded):
            self.client({**CONFIG, "monthlyBudgetUsd": 1e-9}).ask(PAYLOAD)
        self.post.assert_not_called()

    def test_existing_month_spend_counts_toward_budget(self) -> None:
        month = jev_client.now_local().strftime("%Y-%m")
        (self.root / "usage.jsonl").write_text(json.dumps({"month": month, "cost_usd": 0.99999}) + "\n", encoding="utf-8")
        with self.assertRaises(BudgetExceeded):
            self.client().ask(PAYLOAD)
        self.post.assert_not_called()

    def test_auth_and_validation_errors_are_not_retried(self) -> None:
        for status in (401, 422):
            self.post.reset_mock()
            self.post.return_value = fake_response(status)
            with self.assertRaises(JevError) as caught:
                self.client().ask(PAYLOAD, use_cache=False)
            self.assertEqual(caught.exception.status_code, status)
            self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.usage_entries(), [])

    def test_rate_limit_is_retried_with_backoff(self) -> None:
        self.post.side_effect = [fake_response(429), fake_response(200, ok_body())]
        result = self.client().ask(PAYLOAD)
        self.assertEqual(self.post.call_count, 2)
        self.sleep.assert_called_once_with(1)
        self.assertEqual(result.input_tokens, 500)

    def test_overload_gives_up_after_two_retries(self) -> None:
        self.post.return_value = fake_response(529)
        with self.assertRaises(JevError):
            self.client().ask(PAYLOAD)
        self.assertEqual(self.post.call_count, 3)

    def test_read_timeout_reserves_upper_bound_instead_of_zero(self) -> None:
        self.post.side_effect = requests.ReadTimeout("slow")
        with self.assertRaises(JevError):
            self.client().ask(PAYLOAD)
        entries = self.usage_entries()
        bound = max_input_tokens(PAYLOAD, 100, 200)
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(entry["status"] == "unknown" and entry["input_tokens"] == bound and entry["cost_usd"] > 0 for entry in entries))

    def test_connect_timeout_records_nothing(self) -> None:
        self.post.side_effect = requests.ConnectTimeout("no route")
        with self.assertRaises(JevError):
            self.client().ask(PAYLOAD)
        self.assertEqual(self.usage_entries(), [])

    def test_token_bound_covers_body_bytes(self) -> None:
        body_bytes = len(canonical_json(PAYLOAD).encode("utf-8"))
        self.assertEqual(max_input_tokens(PAYLOAD, 100, 200), body_bytes + 100 + 200)


class ApiKeyTest(unittest.TestCase):
    def test_env_var_wins_and_missing_key_is_reported(self) -> None:
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "from-env"}):
            self.assertEqual(jev_client.load_api_key(), "from-env")
        with TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(jev_client, "SKILL_ROOT", Path(tmp)), mock.patch.object(jev_client, "REPO_ROOT", Path(tmp)):
            with self.assertRaises(JevError):
                jev_client.load_api_key()
            (Path(tmp) / ".env").write_text("OTHER=1\nTYPESAFE_API_KEY='from-file'\n", encoding="utf-8")
            self.assertEqual(jev_client.load_api_key(), "from-file")


SPEECH = {"segments": [
    {"segment_id": "s01", "display_text": "OpenAI 正在招 23 个 FDE 相关岗位。旧金山的年薪，最高 30 万美元。", "claim_ids": ["c_jobs", "c_salary"]},
    {"segment_id": "s02", "display_text": "AI 项目最难的一步在上线。", "claim_ids": ["o_why"]},
    {"segment_id": "s03", "display_text": "评论区聊聊。", "claim_ids": []},
    {"segment_id": "s04", "display_text": "Palantir 说这个岗位是它开创的。", "claim_ids": ["c_palantir", "c_missing"]},
]}
CLAIMS = {
    "c_jobs": {"statement": "岗位共 23 个", "status": "verified_source"},
    "c_salary": {"statement": "年薪最高 30 万美元", "status": "verified_test"},
    "o_why": {"statement": "落地卡在上线", "status": "opinion"},
    "c_palantir": {"statement": "Palantir 称该岗位由它开创", "status": "verified_source"},
}


class RulesTest(unittest.TestCase):
    def test_probes_split_opening_audience_and_segments(self) -> None:
        probes, skipped = build_probes(SPEECH, CLAIMS)
        by_key = {(probe.check, probe.where): probe for probe in probes}
        self.assertEqual(by_key[("hook_concrete", "s01")].state, "OpenAI 正在招 23 个 FDE 相关岗位。")
        self.assertEqual(by_key[("audience", "s01-s03")].state, "".join(s["display_text"] for s in SPEECH["segments"][:3]))
        self.assertEqual(by_key[("support", "s01")].state["evidence"], "岗位共 23 个；年薪最高 30 万美元")
        # 不存在的 claim 不进依据，由 script-check 的 claims.missing 负责报错
        self.assertEqual(by_key[("support", "s04")].state["evidence"], "Palantir 称该岗位由它开创")
        self.assertEqual(sorted(result.where for result in skipped), ["s02", "s03"])
        self.assertEqual(sum(1 for probe in probes if probe.check == "exaggeration"), 4)

    def test_noul_answers_without_confidence_use_probability_bands(self) -> None:
        hook = Probe("hook_concrete", "s01", "x")
        self.assertEqual(judge(hook, {"type": "noul", "noul": 0.9}, {}).verdict, "passed")
        self.assertEqual(judge(hook, {"type": "noul", "noul": 0.1}, {}).verdict, "flagged")
        self.assertEqual(judge(hook, {"type": "noul", "noul": 0.5}, {}).verdict, "not_checked")
        exaggeration = Probe("exaggeration", "s01", "x")
        self.assertEqual(judge(exaggeration, {"type": "noul", "noul": 0.9}, {}).verdict, "flagged")
        self.assertEqual(judge(exaggeration, {"type": "noul", "noul": 0.05}, {}).verdict, "passed")

    def test_audience_general_mismatch_and_low_confidence(self) -> None:
        probe, brief = Probe("audience", "s01-s03", "x"), {"audience_segment": "fde"}
        self.assertEqual(judge(probe, {"choice": "fde", "confidence": 0.95}, brief).verdict, "passed")
        self.assertEqual(judge(probe, {"choice": "general", "confidence": 0.99}, brief).verdict, "flagged")
        mismatch = judge(probe, {"choice": "ai_office", "confidence": 0.99}, brief)
        self.assertEqual(mismatch.verdict, "flagged")
        self.assertIn("ai_office", mismatch.message)
        self.assertEqual(judge(probe, {"choice": "ai_office", "confidence": 0.5}, brief).verdict, "not_checked")

    def test_support_verdicts(self) -> None:
        probe = Probe("support", "s01", {})
        self.assertEqual(judge(probe, {"choice": "supports", "confidence": 0.99}, {}).verdict, "passed")
        self.assertEqual(judge(probe, {"choice": "contradicts", "confidence": 0.9}, {}).verdict, "flagged")
        self.assertEqual(judge(probe, {"choice": "says_nothing", "confidence": 0.9}, {}).verdict, "flagged")
        self.assertEqual(judge(probe, {"choice": "supports", "confidence": 0.7}, {}).verdict, "not_checked")

    def test_first_sentence(self) -> None:
        self.assertEqual(first_sentence("每次投标都要熬夜排版？用这个 Skill。"), "每次投标都要熬夜排版？")
        self.assertEqual(first_sentence("没有句号"), "没有句号")


def answering_post(model: str = "jev-1.13.0") -> mock.Mock:
    """按问题类型回一个合理的答案，模拟 /v1/systemone。"""
    canned = {"hook_concrete": {"type": "noul", "noul": 0.9}, "exaggeration": {"type": "noul", "noul": 0.05},
              "audience": {"type": "choice", "choice": "fde", "confidence": 1.0, "probabilities": {"fde": 1.0}},
              "support": {"type": "choice", "choice": "contradicts", "confidence": 0.95, "probabilities": {"contradicts": 0.95}}}

    def post(url: str, json: dict[str, Any], headers: dict[str, str], timeout: int) -> mock.Mock:  # noqa: A002 - 与 requests.post 同名参数
        [name] = json["questions"]
        return fake_response(200, {"model": model, "answers": {name: canned[name]}, "usage": {"input_tokens": 400, "output_tokens": 20}})

    return mock.Mock(side_effect=post)


class ReviewCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        project = self.root / "20260101-demo"
        self.variant = project / "variants" / "channels"
        self.variant.mkdir(parents=True)
        (project / "research").mkdir()
        (self.variant / "speech.json").write_text(json.dumps(SPEECH, ensure_ascii=False), encoding="utf-8")
        (project / "brief.json").write_text(json.dumps({"audience_segment": "fde"}), encoding="utf-8")
        claims = [{"claim_id": cid, **claim} for cid, claim in CLAIMS.items()]
        (project / "research" / "claims.json").write_text(json.dumps({"claims": claims}, ensure_ascii=False), encoding="utf-8")

    def run_review(self, post: mock.Mock, *extra: str) -> int:
        def factory(config: dict[str, Any]) -> JevClient:
            return JevClient(config, api_key="test-key", cache_dir=self.root / "cache", usage_path=self.root / "usage.jsonl", post=post, sleep=lambda _: None)

        with mock.patch.object(jev_check, "JevClient", factory), mock.patch.object(jev_check, "load_config", return_value=CONFIG), \
                mock.patch("builtins.print"):
            return jev_check.main(["review", "--variant-dir", str(self.variant), *extra])

    def test_review_writes_report_with_inputs_usage_and_verdicts(self) -> None:
        post = answering_post()
        self.assertEqual(self.run_review(post), 0)
        report = json.loads((self.variant / "jev-check.json").read_text(encoding="utf-8"))
        # 1 开头 + 1 受众 + 4 夸大 + 2 依据（s01、s04）
        self.assertEqual(post.call_count, 8)
        self.assertEqual(report["summary"], {"passed": 6, "flagged": 2, "not_checked": 0, "skipped": 2})
        self.assertEqual(report["models"], ["jev-1.13.0"])
        self.assertIsNone(report["model_warning"])
        self.assertEqual(report["usage"]["input_tokens"], 8 * 400)
        self.assertEqual(len(report["inputs"]["speech_sha256"]), 64)
        # 第二次全部命中缓存
        self.assertEqual(self.run_review(post), 0)
        self.assertEqual(post.call_count, 8)

    def test_model_version_change_is_warned(self) -> None:
        self.run_review(answering_post(model="jev-2.0.0"))
        report = json.loads((self.variant / "jev-check.json").read_text(encoding="utf-8"))
        self.assertIn("calibrate", report["model_warning"])

    def test_dry_run_sends_nothing(self) -> None:
        post = answering_post()
        self.assertEqual(self.run_review(post, "--dry-run"), 0)
        post.assert_not_called()
        self.assertFalse((self.variant / "jev-check.json").exists())


class CalibrateCommandTest(unittest.TestCase):
    def run_calibrate(self, cases: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
        created: list[dict[str, Any]] = []
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases_path = root / "cases.json"
            cases_path.write_text(json.dumps({"cases": cases}, ensure_ascii=False), encoding="utf-8")

            def factory(config: dict[str, Any], **kwargs: Any) -> JevClient:
                created.append(kwargs)
                # 按命令传入的缓存目录名落到临时目录，确认 calibrate 与 review 不共用缓存
                cache_dir = root / Path(kwargs.get("cache_dir", root / "responses")).name
                return JevClient(config, api_key="test-key", cache_dir=cache_dir, usage_path=root / "usage.jsonl", post=answering_post(), sleep=lambda _: None)

            with mock.patch.object(jev_check, "JevClient", factory), mock.patch.object(jev_check, "load_config", return_value=CONFIG), \
                    mock.patch("builtins.print"):
                code = jev_check.main(["calibrate", "--cases", str(cases_path)])
        return code, created

    def test_calibrate_uses_own_cache_and_reports_unexpected_misses(self) -> None:
        good = [{"check": "hook_concrete", "state": "x", "expected": "passed"},
                {"check": "audience", "state": "y", "expected_choice": "fde"}]
        code, created = self.run_calibrate(good)
        self.assertEqual(code, 0)
        self.assertEqual(created[0]["cache_dir"], jev_check.calibration_cache())
        known_miss = [{"check": "hook_concrete", "state": "x", "expected": "flagged", "known_miss": "已知"}]
        self.assertEqual(self.run_calibrate(known_miss)[0], 0)
        unexpected = [{"check": "support", "state": {"sentence": "a", "evidence": "b"}, "expected_choice": "supports"}]
        self.assertEqual(self.run_calibrate(unexpected)[0], 1)


if __name__ == "__main__":
    unittest.main()
