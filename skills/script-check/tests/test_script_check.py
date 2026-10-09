"""
INPUT: scripts/sclib/rules.py、terms.py、ocr.py 与 scripts/script_check.py；config/platform-terms.json；手写的最小文稿、事实与字幕样例
OUTPUT: 字宽与时长预估、开头规则、版面长度、事实与数字可追溯、结构、配音后开头闸门、平台敏感词（整词匹配、平台级别、
        发布文案章节、OCR 缓存与未检查降级）、命令退出码的测试。Windows OCR 本身不在单元测试里调用，以替身函数代替
POS: script-check 技能的回归测试（不联网、不计费、不读写真实项目）：
     python -m unittest discover -s .claude/skills/script-check/tests
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import script_check  # noqa: E402
from sclib import ocr  # noqa: E402
from sclib.rules import estimate_seconds, hook_gate, lint_variant, text_units  # noqa: E402
from sclib.terms import TextItem, load_terms, normalize, public_publish_sections, scan_texts  # noqa: E402

CLAIMS = {
    "claim_count": {"claim_id": "claim_count", "status": "verified_source", "statement": "官方招聘页共 23 个岗位", "source_ids": ["source_jobs"]},
    "claim_pay": {"claim_id": "claim_pay", "status": "verified_source", "statement": "年薪 18.5 万～30 万美元", "source_ids": ["source_jobs"]},
    "claim_guess": {"claim_id": "claim_guess", "status": "unverified", "statement": "岗位增长 300%", "source_ids": []},
}
SOURCES = {"source_jobs": {"source_id": "source_jobs", "title": "招聘页", "version_or_scope": "年薪 $185K – $300K", "checked_at": "2026-09-29", "published_at": None}}
BRIEF = {"hook": {"type": "benefit"}, "target_duration_seconds": {"douyin": {"min": 1, "max": 120}}}
COVER = {"kicker": "在招", "title": "23 个\nFDE 岗位", "sub": "年薪最高 $300K"}


def speech(first_text: str, first_claims: list[str] | None = None, candidates: int = 3) -> dict:
    return {
        "segments": [
            {"segment_id": "s01", "display_text": first_text, "claim_ids": first_claims if first_claims is not None else ["claim_count"]},
            {"segment_id": "s02", "display_text": "年薪 18.5 万到 30 万美元。", "claim_ids": ["claim_pay"]},
        ],
        "hook_candidates": [{"type": "benefit", "text": first_text}] * candidates,
    }


def shots(first_scene: str = "EvidenceCard", first_params: dict | None = None, segments: tuple[str, ...] = ("s01", "s02")) -> dict:
    return {"shots": [
        {"shot_id": "shot_01", "segment_ids": [segments[0]], "claim_ids": [], "scene_type": first_scene, "params": first_params or {"big": "23", "unit": "个岗位"}},
        {"shot_id": "shot_02", "segment_ids": list(segments[1:]), "claim_ids": ["claim_pay"], "scene_type": "EvidenceCard", "params": {"big": "$185K–$300K", "note": "a16z 说最热门"}},
    ]}


def rules_of(report: dict, level: str | None = None) -> set[str]:
    return {finding["rule"] for finding in report["findings"] if level is None or finding["level"] == level}


class UnitTest(unittest.TestCase):
    def test_text_units_matches_renderer(self) -> None:
        self.assertAlmostEqual(text_units("写代码 · 推上线"), 6 + 1 + 0.5)
        self.assertAlmostEqual(text_units("FDE"), 1.8)
        # 强调标记的花括号不显示、不计宽，与 remotion-render 的 textUnits 一致
        self.assertAlmostEqual(text_units("满屏{色块}"), 4)

    def test_estimate_calibrated_on_real_hook(self) -> None:
        # 2026-09-29 温润男声实测第一句 3.2 秒
        self.assertAlmostEqual(estimate_seconds("OpenAI 正在招 23 个 FDE 相关岗位。"), 3.3, delta=0.3)


class LintTest(unittest.TestCase):
    def lint(self, speech_data: dict, shots_data: dict, brief: dict = BRIEF, cover: dict | None = COVER) -> dict:
        return lint_variant("douyin", speech_data, shots_data, brief, CLAIMS, SOURCES, cover)

    def test_clean_number_hook_passes(self) -> None:
        report = self.lint(speech("OpenAI 正在招 23 个岗位。"), shots())
        self.assertEqual(report["errors"], 0, report["findings"])
        self.assertNotIn("hook.number_late", rules_of(report))

    def test_filler_opening_is_error_and_long_sentence_warned(self) -> None:
        report = self.lint(speech("做 AI 项目最怕的一种情况，演示的时候效果惊艳，一进客户现场就卡住。"), shots())
        self.assertIn("hook.filler", rules_of(report, "error"))
        self.assertIn("hook.first_sentence_long", rules_of(report, "warning"))

    def test_benefit_hook_needs_verified_claim(self) -> None:
        report = self.lint(speech("OpenAI 正在招 23 个岗位。", ["claim_guess"]), shots())
        self.assertIn("hook.benefit_unverified", rules_of(report, "error"))
        self.assertIn("claims.unverified", rules_of(report, "error"))

    def test_late_number_and_text_first_scene_warned(self) -> None:
        long_intro = "这是一段没有数字的铺陈。" * 3
        report = self.lint(speech(long_intro), shots(first_scene="StepFlow", first_params={"title": "说明", "items": ["甲", "乙"]}))
        self.assertIn("hook.number_late", rules_of(report))
        self.assertIn("hook.visual", rules_of(report))

    def test_layout_limits(self) -> None:
        params = {"title": "这是一个明显超过屏幕宽度的开头标题文字"}
        report = self.lint(speech("OpenAI 正在招 23 个岗位。"), shots(first_scene="ResultHook", first_params=params))
        self.assertIn("layout.too_long", rules_of(report, "error"))

    def test_numbers_traced_names_ignored(self) -> None:
        report = self.lint(speech("OpenAI 正在招 23 个岗位。"), shots())
        # $185K、$300K 在来源里有原文；a16z 里的 16 属于名称，不报
        self.assertNotIn("claims.number_untraced", rules_of(report))
        untraced = self.lint(speech("OpenAI 正在招 24 个岗位。"), shots(first_params={"big": "24"}))
        self.assertIn("claims.number_untraced", rules_of(untraced))

    def test_layout_params_not_traced_and_screenshot_compare_is_visual_hook(self) -> None:
        # 取景坐标、图片路径里的数字不上屏，不做出处核对；截图对比的标签照常核对
        params = {"images": [{"image": "assets/original/asset_image_003.png", "tag": "没写规则", "focus": {"x": 0.37, "y": 0.12, "w": 0.48, "h": 0.4}}, {"image": "b.png", "tag": "写了规则"}], "beats": [{"index": 0, "at": 0.36}, {"index": 1, "at": 0.66}]}
        report = self.lint(speech("官方招聘页共 23 个岗位。"), shots(first_scene="BeforeAfter", first_params=params))
        self.assertNotIn("claims.number_untraced", rules_of(report))
        self.assertNotIn("hook.visual", rules_of(report))
        params["images"][0]["tag"] = "规范前 99 处色块"
        self.assertIn("claims.number_untraced", rules_of(self.lint(speech("官方招聘页共 23 个岗位。"), shots(first_scene="BeforeAfter", first_params=params))))

    def test_number_traced_by_claim_statement(self) -> None:
        # 23 只出现在 claim 的 statement 里（来源标题、范围、日期里都没有）；字段名按数据合同为 statement
        report = self.lint(speech("官方招聘页共 23 个岗位。"), shots(first_params={"big": "23", "unit": "个岗位"}))
        self.assertNotIn("claims.number_untraced", rules_of(report))
        renamed = {key: {**claim, "text": claim["statement"], "statement": ""} for key, claim in CLAIMS.items()}
        legacy = lint_variant("douyin", speech("官方招聘页共 23 个岗位。"), shots(first_params={"big": "23"}), BRIEF, renamed, SOURCES, COVER)
        self.assertIn("claims.number_untraced", rules_of(legacy))

    def test_structure_and_missing_candidates_and_cover(self) -> None:
        report = self.lint(speech("OpenAI 正在招 23 个岗位。", candidates=1), shots(segments=("s02", "s01")), cover=None)
        self.assertIn("structure.segments", rules_of(report, "error"))
        self.assertIn("hook.candidates", rules_of(report, "warning"))
        self.assertIn("cover.missing", rules_of(report, "warning"))


class BackdropTest(unittest.TestCase):
    def lint(self, brief: dict, shots_data: dict) -> dict:
        return lint_variant("douyin", speech("OpenAI 正在招 23 个岗位。"), shots_data, brief, CLAIMS, SOURCES, COVER)

    def test_missing_theme_warned_only_when_wallpaper_scenes_exist(self) -> None:
        self.assertIn("backdrop.theme_missing", rules_of(self.lint(BRIEF, shots())))
        no_wallpaper = {"shots": [{"shot_id": "shot_01", "segment_ids": ["s01", "s02"], "claim_ids": [], "scene_type": "ResultHook", "params": {"title": "23 个岗位"}}]}
        self.assertNotIn("backdrop.theme_missing", rules_of(self.lint(BRIEF, no_wallpaper)))

    def test_theme_set_passes_and_fixed_wallpaper_warned(self) -> None:
        themed = {**BRIEF, "visual": {"backdrop_theme": ["blueprint"]}}
        self.assertFalse({"backdrop.theme_missing", "backdrop.fixed_wallpaper"} & rules_of(self.lint(themed, shots())))
        fixed = shots(first_params={"big": "23", "wallpaper": "glacier"})
        report = self.lint(themed, fixed)
        self.assertIn("backdrop.fixed_wallpaper", rules_of(report, "warning"))


class ToneTest(unittest.TestCase):
    def lint(self, shot_list: list[dict]) -> dict:
        return lint_variant("douyin", speech("OpenAI 正在招 23 个岗位。"), {"shots": shot_list}, BRIEF, CLAIMS, SOURCES, COVER)

    @staticmethod
    def shot(scene: str, params: dict) -> dict:
        return {"shot_id": "shot_01", "segment_ids": ["s01", "s02"], "claim_ids": [], "scene_type": scene, "params": params}

    def test_tone_marks_not_counted_in_width(self) -> None:
        self.assertAlmostEqual(text_units("每次{熬夜|痛点}"), text_units("每次熬夜"))

    def test_unknown_tone_is_error(self) -> None:
        report = self.lint([self.shot("ResultHook", {"title": "每次都{熬夜|高兴}"})])
        self.assertIn("tone.unknown", rules_of(report, "error"))

    def test_two_semantic_tones_pass_three_fail(self) -> None:
        ok = self.shot("ResultHook", {"title": "每次{熬夜|痛点}\n现在{半天|解法}{出稿}"})
        self.assertNotIn("tone.too_many", rules_of(self.lint([ok])))
        # 划掉的旧说法默认痛点色、换上的说法默认解法色，再加一个数字（默认数据色）就是三种
        busy = self.shot("KineticText", {"beats": [{"text": "通宵", "effect": "strike", "replace": "{半天}"}, {"text": "{12} 章", "effect": "count"}]})
        self.assertIn("tone.too_many", rules_of(self.lint([busy]), "error"))

    def test_kinetic_beats_are_display_text_and_layout_checked(self) -> None:
        long_line = self.shot("KineticText", {"beats": [{"text": "这一行文字特别特别特别特别特别长", "effect": "pop"}]})
        self.assertIn("layout.too_long", rules_of(self.lint([long_line])))


class HookGateTest(unittest.TestCase):
    def test_measures_first_sentence_end_and_first_number(self) -> None:
        data = {"segments": [{"segment_id": "s01", "display_text": "OpenAI 正在招 23 个岗位。旧金山年薪最高 30 万美元。"}]}
        captions = [
            {"segment_id": "s01", "start_ms": 100, "end_ms": 3200, "text": "OpenAI 正在招 23 个岗位"},
            {"segment_id": "s01", "start_ms": 3200, "end_ms": 6000, "text": "旧金山年薪最高 30 万美元"},
        ]
        result = hook_gate(data, captions)
        self.assertEqual((result["first_sentence_end_ms"], result["first_number_ms"], result["passed"]), (3200, 100, True))
        slow = [dict(captions[0], end_ms=5200), captions[1]]
        self.assertFalse(hook_gate(data, slow)["passed"])


def found(items: list[tuple[str, str]], platform: str = "douyin") -> set[tuple[str, str]]:
    findings = scan_texts([TextItem(where, text) for where, text in items], load_terms(platform))
    return {(finding.rule, finding.level) for finding in findings}


class TermsTest(unittest.TestCase):
    def test_english_terms_match_whole_words_only(self) -> None:
        # CLAUDE.md、GPT-4o 命中；Clawdbotx 后接小写字母不命中，Slack 不在词表里
        self.assertIn(("terms.overseas_ai", "error"), found([("s", "新建一个 CLAUDE.md")]))
        self.assertIn(("terms.overseas_ai", "error"), found([("s", "换成 GPT-4o 试试")]))
        # 驼峰话题：Claude 后面紧跟大写的 Code 也要命中
        self.assertIn(("terms.overseas_ai", "error"), found([("publish.md#话题", "#AI办公 #ClaudeCode")]))
        self.assertEqual(scan_texts([TextItem("s", "Clauded 与 ChatGPTs")], load_terms("douyin")), [])
        self.assertEqual(scan_texts([TextItem("s", "Clawdbotx 与 Slack")], load_terms("douyin")), [])

    def test_ocr_spacing_between_hanzi_is_removed(self) -> None:
        self.assertEqual(normalize("中 国 大 陆 用 户 macOS 、 Linux"), "中国大陆用户macOS、Linux")
        self.assertIn(("terms.circumvention", "error"), found([("截图", "网 络 要 求 中 国 大 陆 用 户")]))

    def test_platform_levels(self) -> None:
        # 视频号属于微信生态，站外引流词不检查；抖音报 error
        self.assertIn(("terms.off_platform", "error"), found([("s", "公众号回复「标书」领取")], "douyin"))
        self.assertEqual(found([("s", "公众号回复「标书」领取")], "channels"), set())
        self.assertIn(("terms.absolute_claims", "warning"), found([("s", "全网最强的办法")], "channels"))

    def test_publish_md_only_public_sections(self) -> None:
        markdown = ("# 发布包\n\n| 成片 | a.mp4 |\n\n## 标题\n标题文字\n\n## 说明\n说明文字\n\n## 话题\n#AI办公\n\n"
                    "## AI 生成内容声明\n- 配音 MiniMax\n\n## 来源（可用于置顶评论）\n- 链接\n\n## 发布前核对（不对外）\n- [ ] Telegram\n")
        wheres = [item.where for item in public_publish_sections(markdown)]
        self.assertEqual(wheres, ["publish.md#标题", "publish.md#说明", "publish.md#话题", "publish.md#来源（可用于置顶评论）"])


class OcrCacheTest(unittest.TestCase):
    def test_cache_keyed_by_image_hash(self) -> None:
        calls: list[list[str]] = []

        def fake_ocr(paths: list[Path]) -> dict[str, list[str]]:
            calls.append([path.name for path in paths])
            return {str(path): [f"文字 {path.name}"] for path in paths}

        original = ocr._run_windows_ocr
        ocr._run_windows_ocr = fake_ocr
        try:
            with TemporaryDirectory() as tmp:
                image, cache = Path(tmp) / "a.png", Path(tmp) / "ocr-cache.json"
                image.write_bytes(b"one")
                self.assertEqual(ocr.recognize([image], cache)[image], ["文字 a.png"])
                ocr.recognize([image], cache)
                self.assertEqual(len(calls), 1)
                # 换图（内容变了）就重新识别
                image.write_bytes(b"two")
                ocr.recognize([image], cache)
                self.assertEqual(len(calls), 2)
        finally:
            ocr._run_windows_ocr = original


def write_project(tmp: str) -> tuple[Path, Path]:
    project = Path(tmp) / "projects" / "p"
    variant = project / "variants" / "douyin"
    (project / "research").mkdir(parents=True)
    variant.mkdir(parents=True)
    (project / "research" / "claims.json").write_text(json.dumps({"claims": list(CLAIMS.values())}, ensure_ascii=False), encoding="utf-8")
    (project / "research" / "sources.json").write_text(json.dumps({"sources": list(SOURCES.values())}, ensure_ascii=False), encoding="utf-8")
    (project / "brief.json").write_text(json.dumps(BRIEF), encoding="utf-8")
    return project, variant


class CommandTest(unittest.TestCase):
    def test_terms_command_screenshots_and_exit_codes(self) -> None:
        with TemporaryDirectory() as tmp:
            project, variant = write_project(tmp)
            (project / "assets").mkdir()
            (project / "assets" / "shot.png").write_bytes(b"png")
            shot_data = shots(first_scene="ScreenFocus", first_params={"image": "assets/shot.png", "title": "看结果"})
            (variant / "shots.json").write_text(json.dumps(shot_data, ensure_ascii=False), encoding="utf-8")
            (variant / "speech.json").write_text(json.dumps(speech("OpenAI 正在招 23 个岗位。"), ensure_ascii=False), encoding="utf-8")
            # 口播里的 OpenAI 是境外 AI 产品名：error；--no-ocr 时截图记为未检查、只给 warning
            self.assertEqual(script_check.main(["terms", "--variant-dir", str(variant), "--no-ocr"]), 1)
            report = json.loads((variant / "terms-check.json").read_text(encoding="utf-8"))
            self.assertEqual(report["screenshots"][0]["status"], "not_checked")
            self.assertIn(("terms.ocr_not_checked", "warning"), {(item["rule"], item["level"]) for item in report["findings"]})
            (variant / "speech.json").write_text(json.dumps(speech("官方招聘页共 23 个岗位。"), ensure_ascii=False), encoding="utf-8")
            original = script_check.recognize

            def unavailable(paths: list[Path], cache: Path) -> dict:
                raise ocr.OcrUnavailable("测试：本机没有 OCR")

            try:
                script_check.recognize = lambda paths, cache: {path: ["通 过 Telegram 交 互"] for path in paths}
                self.assertEqual(script_check.main(["terms", "--variant-dir", str(variant)]), 1)
                script_check.recognize = lambda paths, cache: {path: ["正 文 宋 体"] for path in paths}
                self.assertEqual(script_check.main(["terms", "--variant-dir", str(variant)]), 0)
                # 截图没识别成，不能当作没有敏感词：不加 --no-ocr 时报 error
                script_check.recognize = unavailable
                self.assertEqual(script_check.main(["terms", "--variant-dir", str(variant)]), 1)
            finally:
                script_check.recognize = original

    def test_lint_exit_codes_and_report_file(self) -> None:
        with TemporaryDirectory() as tmp:
            project, variant = write_project(tmp)
            (variant / "shots.json").write_text(json.dumps(shots(), ensure_ascii=False), encoding="utf-8")
            (variant / "speech.json").write_text(json.dumps(speech("OpenAI 正在招 23 个岗位。"), ensure_ascii=False), encoding="utf-8")
            self.assertEqual(script_check.main(["lint", "--variant-dir", str(variant)]), 0)
            self.assertTrue((variant / "script-check.json").is_file())
            (variant / "speech.json").write_text(json.dumps(speech("大家好，今天聊聊 23 个岗位。"), ensure_ascii=False), encoding="utf-8")
            self.assertEqual(script_check.main(["lint", "--variant-dir", str(variant)]), 1)


if __name__ == "__main__":
    unittest.main()
