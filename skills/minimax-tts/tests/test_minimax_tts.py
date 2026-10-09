"""
INPUT: scripts/minimax_tts.py、scripts/cli.py；unittest.mock 伪造 HTTP 响应（不联网、不消耗额度）
OUTPUT: 接口封装、字幕参数、密钥查找、缓存命中与字数上限的单元测试
POS: 技能的回归测试。改动 scripts/ 下任一文件后运行：
     python -m unittest discover -s .claude/skills/minimax-tts/tests
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cli  # noqa: E402

# 用例直接调用 command_batch（绕过 main 里的输出编码设置）；Windows 控制台为 GBK 时打印 ¥ 会抛错，这里与 main 一致改为 UTF-8
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")
import minimax_tts  # noqa: E402
from minimax_tts import MiniMaxError, RoleVoice, SynthesisOptions, build_t2a_payload, list_voices, synthesize  # noqa: E402

FAKE_AUDIO = b"ID3fake-mp3"


def fake_response(body: dict) -> mock.Mock:
    response = mock.Mock()
    response.json.return_value = body
    response.raise_for_status.return_value = None
    return response


def success_body(subtitle_url: str | None = None) -> dict:
    data = {"audio": FAKE_AUDIO.hex(), "status": 2}
    if subtitle_url:
        data["subtitle_file"] = subtitle_url
    return {
        "data": data,
        "extra_info": {"audio_length": 2345, "usage_characters": 12},
        "trace_id": "trace-ok",
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }


def error_body(status_code: int) -> dict:
    return {"trace_id": "trace-err", "base_resp": {"status_code": status_code, "status_msg": "err"}}


@mock.patch.object(minimax_tts.time, "sleep", lambda _: None)
class SynthesizeTest(unittest.TestCase):
    def test_payload_maps_role_pronunciation_and_subtitles(self) -> None:
        options = SynthesisOptions(model="speech-2.8-turbo", pronunciation=("码包/(ma3)(bao1)",), text_normalization=True, subtitle_type="word")
        payload = build_t2a_payload("你好", RoleVoice("v1", speed=1.2, emotion="calm"), options)
        self.assertEqual(payload["model"], "speech-2.8-turbo")
        self.assertEqual(payload["voice_setting"]["emotion"], "calm")
        self.assertTrue(payload["voice_setting"]["text_normalization"])
        self.assertEqual(payload["pronunciation_dict"], {"tone": ["码包/(ma3)(bao1)"]})
        self.assertTrue(payload["subtitle_enable"])
        self.assertEqual(payload["subtitle_type"], "word")

    def test_payload_omits_optional_fields_when_unset(self) -> None:
        payload = build_t2a_payload("你好", RoleVoice("v1"))
        self.assertNotIn("emotion", payload["voice_setting"])
        self.assertNotIn("pronunciation_dict", payload)
        self.assertNotIn("subtitle_enable", payload)

    def test_unsupported_subtitle_model_rejected_before_request(self) -> None:
        with mock.patch.object(minimax_tts.requests, "post") as post:
            with self.assertRaises(ValueError):
                synthesize("你好", RoleVoice("v1"), "key", SynthesisOptions(model="speech-old", subtitle_type="word"))
        post.assert_not_called()

    def test_synthesize_returns_audio_duration_usage_and_subtitle_url(self) -> None:
        body = success_body("https://example.com/sub.json")
        with mock.patch.object(minimax_tts.requests, "post", return_value=fake_response(body)) as post:
            result = synthesize("你好", RoleVoice("v1"), "key-123", SynthesisOptions(subtitle_type="word"))
        self.assertEqual(result.audio, FAKE_AUDIO)
        self.assertEqual(result.duration_ms, 2345)
        self.assertEqual(result.usage_characters, 12)
        self.assertEqual(result.subtitle_url, "https://example.com/sub.json")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer key-123")

    def test_rate_limit_is_retried(self) -> None:
        responses = [fake_response(error_body(1002)), fake_response(success_body())]
        with mock.patch.object(minimax_tts.requests, "post", side_effect=responses) as post:
            synthesize("你好", RoleVoice("v1"), "key")
        self.assertEqual(post.call_count, 2)

    def test_auth_failure_is_not_retried(self) -> None:
        with mock.patch.object(minimax_tts.requests, "post", return_value=fake_response(error_body(1004))) as post:
            with self.assertRaises(MiniMaxError) as caught:
                synthesize("你好", RoleVoice("v1"), "bad-key")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(caught.exception.status_code, 1004)

    def test_network_error_gives_up_after_max_attempts(self) -> None:
        error = minimax_tts.requests.ConnectionError("offline")
        with mock.patch.object(minimax_tts.requests, "post", side_effect=error) as post:
            with self.assertRaises(MiniMaxError):
                synthesize("你好", RoleVoice("v1"), "key")
        self.assertEqual(post.call_count, minimax_tts.MAX_ATTEMPTS)

    def test_list_voices_flattens_categories(self) -> None:
        body = {
            "system_voice": [{"voice_id": "sys-1"}],
            "voice_cloning": [{"voice_id": "clone-1"}],
            "voice_generation": None,
            "base_resp": {"status_code": 0},
        }
        with mock.patch.object(minimax_tts.requests, "post", return_value=fake_response(body)):
            voices = list_voices("key", "all")
        self.assertEqual([(v["voice_id"], v["category"]) for v in voices], [("sys-1", "system_voice"), ("clone-1", "voice_cloning")])


class ApiKeyTest(unittest.TestCase):
    def run_with_roots(self, skill_env: str | None, repo_env: str | None) -> str:
        with TemporaryDirectory() as skill, TemporaryDirectory() as repo, mock.patch.dict("os.environ", {}, clear=True):
            if skill_env is not None:
                Path(skill, ".env").write_text(skill_env, encoding="utf-8")
            if repo_env is not None:
                Path(repo, ".env").write_text(repo_env, encoding="utf-8")
            with mock.patch.object(minimax_tts, "SKILL_ROOT", Path(skill)), mock.patch.object(minimax_tts, "REPO_ROOT", Path(repo)):
                return minimax_tts.load_api_key()

    def test_skill_env_takes_priority_over_repo_env(self) -> None:
        self.assertEqual(self.run_with_roots('MINIMAX_API_KEY="skill"\n', "MINIMAX_API_KEY=repo\n"), "skill")

    def test_falls_back_to_repo_env(self) -> None:
        self.assertEqual(self.run_with_roots(None, "OTHER=1\nMINIMAX_API_KEY=repo\n"), "repo")

    def test_missing_key_raises_clear_error(self) -> None:
        with self.assertRaises(MiniMaxError):
            self.run_with_roots(None, None)


def make_config(max_chars: int = 3000) -> cli.SkillConfig:
    return cli.SkillConfig(
        {
            "model": "speech-2.8-hd",
            "subtitles": "word",
            "maxCharsPerRun": max_chars,
            "defaultRole": "narrator",
            "roles": {"narrator": {"voice_id": "v-narrator"}, "host": {"voice_id": "v-host"}},
        }
    )


def fake_synthesis(*_args: object, **_kwargs: object) -> minimax_tts.SynthesisResult:
    return minimax_tts.SynthesisResult(FAKE_AUDIO, 1500, 5, "https://example.com/sub.json", "t")


FAKE_SUBTITLES = [{"text": "你好", "time_begin": 0, "time_end": 1500}]


@mock.patch.object(cli, "download_subtitles", lambda _url: FAKE_SUBTITLES)
class BatchTest(unittest.TestCase):
    def write_segments(self, folder: Path, segments: list[dict]) -> Path:
        path = folder / "segments.json"
        path.write_text(json.dumps({"segments": segments}, ensure_ascii=False), encoding="utf-8")
        return path

    def run_batch(self, folder: Path, segments_path: Path, config: cli.SkillConfig, extra: list[str] | None = None) -> int:
        argv = ["batch", "--segments", str(segments_path), "--out-dir", str(folder / "out"), *(extra or [])]
        args = cli.build_parser().parse_args(argv)
        return cli.command_batch(args, config)

    def test_second_run_hits_cache_without_calling_api(self) -> None:
        with TemporaryDirectory() as tmp, mock.patch.object(cli, "load_api_key", return_value="key"):
            folder = Path(tmp)
            segments = self.write_segments(folder, [{"id": "seg-1", "text": "你好"}, {"id": "seg-2", "text": "再见", "role": "host"}])
            with mock.patch.object(cli, "synthesize", side_effect=fake_synthesis) as call:
                self.assertEqual(self.run_batch(folder, segments, make_config()), 0)
                self.assertEqual(call.call_count, 2)
                self.assertEqual(call.call_args_list[1].args[1].voice_id, "v-host")
            with mock.patch.object(cli, "synthesize", side_effect=fake_synthesis) as call:
                self.assertEqual(self.run_batch(folder, segments, make_config()), 0)
                call.assert_not_called()
            result = json.loads((folder / "out" / "batch-result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["synthesized_text_chars"], 0)
            self.assertEqual(result["usage_characters"], 0)

    def test_changed_text_invalidates_only_that_segment(self) -> None:
        with TemporaryDirectory() as tmp, mock.patch.object(cli, "load_api_key", return_value="key"):
            folder = Path(tmp)
            with mock.patch.object(cli, "synthesize", side_effect=fake_synthesis):
                self.run_batch(folder, self.write_segments(folder, [{"id": "a", "text": "一"}, {"id": "b", "text": "二"}]), make_config())
            changed = self.write_segments(folder, [{"id": "a", "text": "一"}, {"id": "b", "text": "二改"}])
            with mock.patch.object(cli, "synthesize", side_effect=fake_synthesis) as call:
                self.run_batch(folder, changed, make_config())
            self.assertEqual([c.args[0] for c in call.call_args_list], ["二改"])

    def test_tampered_audio_is_not_reused(self) -> None:
        with TemporaryDirectory() as tmp, mock.patch.object(cli, "load_api_key", return_value="key"):
            folder = Path(tmp)
            segments = self.write_segments(folder, [{"id": "a", "text": "一"}])
            with mock.patch.object(cli, "synthesize", side_effect=fake_synthesis):
                self.run_batch(folder, segments, make_config())
            (folder / "out" / "a.mp3").write_bytes(b"edited")
            with mock.patch.object(cli, "synthesize", side_effect=fake_synthesis) as call:
                self.run_batch(folder, segments, make_config())
            self.assertEqual(call.call_count, 1)

    def test_char_limit_stops_before_any_call(self) -> None:
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            segments = self.write_segments(folder, [{"id": "a", "text": "一二三四五"}])
            with mock.patch.object(cli, "synthesize") as call:
                self.assertEqual(self.run_batch(folder, segments, make_config(max_chars=3)), 2)
            call.assert_not_called()

    def test_invalid_segments_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for bad in ([{"id": "a"}], [{"id": "../x", "text": "t"}], [{"id": "a", "text": "1"}, {"id": "a", "text": "2"}]):
                with self.assertRaises(ValueError):
                    cli.load_segments(self.write_segments(folder, bad))


class SubtitleFailureTest(unittest.TestCase):
    def test_paid_audio_and_meta_kept_when_subtitle_download_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "a.mp3"
            failing = mock.Mock(side_effect=MiniMaxError("expired"))
            with mock.patch.object(cli, "synthesize", side_effect=fake_synthesis), mock.patch.object(cli, "download_subtitles", failing):
                meta = cli.synthesize_to_files("你好", RoleVoice("v1"), SynthesisOptions(subtitle_type="word"), "key", audio_path)
            saved = json.loads(cli.meta_path_for(audio_path).read_text(encoding="utf-8"))
            self.assertEqual(audio_path.read_bytes(), FAKE_AUDIO)
            self.assertEqual(saved["subtitle_status"], "failed")
            self.assertEqual(saved["trace_id"], "t")
            self.assertEqual(saved["usage_characters"], 5)
            self.assertEqual(saved["subtitle_url"], "https://example.com/sub.json")
            # 字幕缺失的结果不能当作完整缓存
            self.assertIsNone(cli.cached_meta(audio_path, meta["request_hash"]))

    def test_subtitles_saved_next_to_audio(self) -> None:
        with TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "a.mp3"
            with mock.patch.object(cli, "synthesize", side_effect=fake_synthesis), mock.patch.object(cli, "download_subtitles", lambda _u: FAKE_SUBTITLES):
                meta = cli.synthesize_to_files("你好", RoleVoice("v1"), SynthesisOptions(subtitle_type="word"), "key", audio_path)
            self.assertEqual(meta["subtitle_status"], "saved")
            self.assertEqual(json.loads((Path(tmp) / "a.subtitles.json").read_text(encoding="utf-8")), FAKE_SUBTITLES)
            self.assertIsNotNone(cli.cached_meta(audio_path, meta["request_hash"]))


class BillingTest(unittest.TestCase):
    def test_official_counting_rule(self) -> None:
        # 汉字 2，英文字母、数字、标点、空格各 1：与 2026-09-29 真实调用返回的 usage_characters 对得上
        self.assertEqual(cli.billing_chars("我今天查了 OpenAI 的官方招聘页，职位名称带 Forward Deployed 的，一共 23 个，从旧金山、纽约，一直开到东京、新加坡和首尔。"), 113)
        self.assertEqual(cli.billing_chars("AI"), 2)

    def test_cost_estimate_uses_config_price(self) -> None:
        config = make_config()
        self.assertIsNone(cli.estimated_cost(1000, config))
        config.raw["pricePer10kBillingChars"] = 3.5
        self.assertAlmostEqual(cli.estimated_cost(693, config), 0.2426, places=3)


class ConfigTest(unittest.TestCase):
    def test_unknown_role_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_config().voice("typo")

    def test_subtitles_none_disables_request(self) -> None:
        self.assertIsNone(make_config().options("none").subtitle_type)
        self.assertEqual(make_config().options("word").subtitle_type, "word")

    def test_shipped_config_is_valid(self) -> None:
        config = cli.SkillConfig.load(cli.DEFAULT_CONFIG_PATH)
        self.assertEqual(config.voice(None).voice_id, "Chinese (Mandarin)_Gentleman")
        minimax_tts.validate_options(config.options(config.raw.get("subtitles")))


if __name__ == "__main__":
    unittest.main()
