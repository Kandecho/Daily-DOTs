"""Synthetic TEST issues only: no news claims, network, or browser needed."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Child CLIs print Chinese; force UTF-8 pipes so tests also run on Windows.
UTF8_ENV = {**os.environ, "PYTHONUTF8": "1"}
sys.path.insert(0, str(ROOT / "tools"))
import core
import daily
import page


def test_draft(path, date="2098-12-31", count=3, mutate=None):
    ids = [f"test-{n}" for n in range(1, count + 1)]
    meta = {"schema_version": 1, "issue_date": date, "title": "全球晚间新闻",
            "cutoff": date + " 22:55 北京时间",
            "layout": {"schema_version": 1, "template": "claude-flip-v1", "order": ids,
                       "shared_map": "tools/data/ne_110m_countries.geojson",
                       "stories": [{"story_id": sid, "components": []} for sid in ids]}}
    if mutate:
        mutate(meta)
    body = f"# 全球晚间新闻 {date}\n\n"
    for n, sid in enumerate(ids, 1):
        info = {"id": sid, "number": str(n), "category": f"TEST领域{n}", "exploration": False}
        body += (f'<!-- story {json.dumps(info, ensure_ascii=False)} -->\n'
                 f'## TEST 虚构条目{n}\n'
                 '<!-- block a heading -->\n### 今天发生了什么\n'
                 '<!-- block b paragraph -->\n'
                 'TEST：仅为程序测试，不是真实新闻。刚果（金）、肯尼亚、尼日利亚是测试地图标签。'
                 '2098年12月30日、2098年12月31日和2099年1月1日用于测试日期强调。\n'
                 '<!-- block c heading -->\n### 为什么今天值得留下\n'
                 '<!-- block d paragraph -->\nTEST：核对来源与全文保留。\n'
                 f'<!-- sources -->\n- [TEST 来源](https://example.invalid/test/{n})\n'
                 '<!-- endstory -->\n\n')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('---\n' + json.dumps(meta, ensure_ascii=False, indent=2) + '\n---\n\n' + body, encoding="utf-8")
    return path


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="TEST_pipeline_", dir=ROOT / "_build")
        self.work = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_daily(self, draft, *args):
        return subprocess.run([sys.executable, str(ROOT / "tools/daily.py"), str(draft),
                               "--build-dir", str(self.work / "internal"), *map(str, args)],
                              cwd=tempfile.gettempdir(), capture_output=True, text=True,
                              encoding="utf-8", env=UTF8_ENV)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_one_and_two_main_items_without_exploration_build(self):
        for count in (1, 2):
            with self.subTest(count=count):
                draft = test_draft(self.work / str(count) / "TEST.md", count=count)
                out = draft.with_suffix(".html")
                self.assert_success(self.run_daily(draft, "--out", out))
                self.assertEqual(out.read_text(encoding="utf-8").count('<article class="story"'), count)

    def test_shared_build_directory_cannot_add_unshipped_cross_day_links(self):
        for date in ("2098-12-31", "2099-01-01"):
            draft = test_draft(self.work / date / "TEST.md", date=date)
            out = draft.with_suffix(".html")
            self.assert_success(self.run_daily(draft, "--out", out))
            self.assertNotRegex(out.read_text(encoding="utf-8"), r'href="(?!\.\./\.\./index\.html")(?:\.\./|209[89]-)')

    def test_missing_metadata_title_reports_clean_error(self):
        draft = test_draft(self.work / "TEST.md", mutate=lambda m: m.pop("title"))
        result = self.run_daily(draft)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("title", result.stderr)

    def test_unknown_component_is_not_silently_dropped(self):
        draft = test_draft(self.work / "TEST.md", mutate=lambda m: m["layout"]["stories"][0]["components"].append({"type": "unknown"}))
        result = self.run_daily(draft)
        self.assertNotEqual(result.returncode, 0, "Unsupported component silently accepted")
        self.assertNotIn("Traceback", result.stderr)

    def test_draft_is_never_an_output_target(self):
        draft = test_draft(self.work / "TEST.md")
        before = draft.read_bytes()
        result = self.run_daily(draft, "--out", draft)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(draft.read_bytes(), before)

    def test_changed_existing_output_needs_explicit_overwrite(self):
        draft = test_draft(self.work / "TEST.md")
        out = self.work / "TEST.html"
        out.write_text("TEST prior output must survive", encoding="utf-8")
        result = self.run_daily(draft, "--out", out)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(out.read_text(encoding="utf-8"), "TEST prior output must survive")

    def test_output_cannot_target_a_different_dated_edition(self):
        draft = test_draft(self.work / "TEST.md")
        out = self.work / "2099-01-01" / "TEST.html"
        result = self.run_daily(draft, "--out", out)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(out.exists())

    def test_official_name_and_expected_date(self):
        draft = test_draft(self.work / "TEST.md")
        result = self.run_daily(draft, "--date", "2098-12-31")
        self.assert_success(result)
        self.assertTrue((self.work / "全球晚间新闻_2098-12-31_翻页.html").exists())
        self.assertFalse((self.work / "全球晚间新闻_2098-12-31_翻页试读.html").exists())
        result = self.run_daily(draft, "--date", "2099-01-01")
        self.assertNotEqual(result.returncode, 0)

    def test_offline_audit_rejects_css_and_relative_resources(self):
        html = '<section class="pg pg-cover" id="p0"></section>'
        for resource in ('<img src="missing.png">', '<style>.x{background:url(https://example.invalid/p.png)}</style>'):
            with self.subTest(resource=resource):
                with self.assertRaisesRegex(ValueError, "资源"):
                    daily.audit_html("", html + resource, {"items": []})

    def test_source_query_parameters_survive_rendering_exactly(self):
        url = "https://example.invalid/test?a=1&b=2"
        self.assertEqual(daily.Audit(page.inline(f"[TEST 来源]({url})")).links, [url])

    def test_explicit_font_directory_and_missing_font_diagnostic(self):
        draft = test_draft(self.work / "TEST.md")
        self.assert_success(self.run_daily(draft, "--font-dir", ROOT / "tools/fonts"))
        missing = self.work / "missing_fonts"
        result = self.run_daily(draft, "--font-dir", missing)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn(str(missing), result.stderr)
        self.assertIn("NotoSerifCJK-Bold.ttc", result.stderr)

    def test_malformed_map_reports_error_without_publishing(self):
        draft = test_draft(self.work / "TEST.md", mutate=lambda m: m["layout"]["stories"][0]["components"].append({"type": "locator_map"}))
        result = self.run_daily(draft)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("highlights", result.stderr)

    def test_repeated_build_is_stable_and_revision_requires_overwrite(self):
        draft = test_draft(self.work / "TEST.md")
        out = self.work / "TEST.html"
        self.assert_success(self.run_daily(draft, "--out", out))
        original = out.read_bytes()
        self.assert_success(self.run_daily(draft, "--out", out))
        self.assertEqual(out.read_bytes(), original)
        draft.write_text(draft.read_text(encoding="utf-8").replace("核对来源与全文保留", "修改后的虚构测试段落"), encoding="utf-8")
        denied = self.run_daily(draft, "--out", out)
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(out.read_bytes(), original)
        self.assert_success(self.run_daily(draft, "--out", out, "--overwrite"))
        self.assertNotEqual(out.read_bytes(), original)

    def test_cross_year_map_fonts_dates_and_query_sources_build(self):
        def add_map(meta):
            meta["layout"]["stories"][0]["components"] = [{"type": "locator_map",
                "highlights": [{"country_id": "COD"}, {"country_id": "KEN"}, {"country_id": "NGA"}],
                "viewport": [-20, -36, 53, 38], "points": [], "caption": "TEST 虚构国家定位，不表示传播方向。"}]
        draft = test_draft(self.work / "TEST.md", date="2099-01-01", count=1, mutate=add_map)
        draft.write_text(draft.read_text(encoding="utf-8").replace("https://example.invalid/test/1", "https://example.invalid/test/1?a=1&b=2"), encoding="utf-8")
        out = self.work / "TEST.html"
        self.assert_success(self.run_daily(draft, "--out", out))
        html = out.read_text(encoding="utf-8")
        self.assertIn("2099年1月1日 星期四", html)
        self.assertIn('<span class="dt past">2098年12月31日</span>', html)
        self.assertEqual(html.count('<figure class="fig fig-map">'), 1)
        self.assertIn('aria-label="定位图：刚果（金）、肯尼亚、尼日利亚"', html)
        self.assertNotIn('class="pt"', html)
        self.assertEqual(html.count("data:font/woff;base64,"), 2)
        receipt = json.loads((self.work / "internal/verification.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["source_links"], 1)
        self.assertEqual([f["missing_visible_chars"] for f in receipt["fonts"]], [0, 0])

    def test_output_cannot_overlap_internal_render_files(self):
        draft = test_draft(self.work / "TEST.md")
        out = self.work / "internal/dist/flip/2098-12-31.html"
        out.parent.mkdir(parents=True)
        out.write_text("TEST prior published file must survive", encoding="utf-8")
        result = self.run_daily(draft, "--out", out)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(out.read_text(encoding="utf-8"), "TEST prior published file must survive")

    def test_supported_lists_and_tables_preserve_visible_text(self):
        draft = test_draft(self.work / "TEST.md", count=1)
        raw = draft.read_text(encoding="utf-8").replace("TEST：核对来源与全文保留。", "- TEST 第一项\n- TEST 第二项\n\n1. TEST 顺序项\n\n| TEST 表头 |\n| --- |\n| TEST 单元格 |")
        draft.write_text(raw, encoding="utf-8")
        out = self.work / "TEST.html"
        self.assert_success(self.run_daily(draft, "--out", out))
        html = out.read_text(encoding="utf-8")
        for expected in ("TEST 第一项", "TEST 第二项", "TEST 顺序项", "TEST 单元格"):
            self.assertIn(expected, html)

    def test_empty_source_area_renders_no_sources_section(self):
        draft = test_draft(self.work / "TEST.md", count=2)
        raw = draft.read_text(encoding="utf-8").replace("- [TEST 来源](https://example.invalid/test/1)\n", "", 1)
        draft.write_text(raw, encoding="utf-8")
        out = self.work / "TEST.html"
        self.assert_success(self.run_daily(draft, "--out", out))
        html = out.read_text(encoding="utf-8")
        self.assertEqual(html.count('class="sec sec-sources"'), 1)
        self.assertIn("https://example.invalid/test/2", html)


if __name__ == "__main__":
    unittest.main()
