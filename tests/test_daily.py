"""Small contract checks for the verified-draft bridge; no browser/network."""
import os
import re
import sys
import subprocess
import tempfile
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Child CLIs print Chinese; force UTF-8 pipes so tests also run on Windows.
UTF8_ENV = {**os.environ, "PYTHONUTF8": "1"}
sys.path.insert(0, str(ROOT / "tools"))
import core
import flip
import page
import sheet
from geo import Geo

DRAFT = ROOT / "editions/2026-10-27/原稿_2026-10-27.md"


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class DailyTests(unittest.TestCase):
    def test_build_command_outputs_only_flip_beside_the_manuscript(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "_build") as tmp:
            result = subprocess.run([sys.executable, str(ROOT / "tools/daily.py"), str(DRAFT),
                                     "--out", str(Path(tmp) / "试读.html"), "--build-dir", str(Path(tmp) / "internal")],
                                    text=True, capture_output=True, encoding="utf-8", env=UTF8_ENV)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            html = (Path(tmp) / "试读.html").read_text(encoding="utf-8")
            self.assertIn("刚果（金）、肯尼亚、尼日利亚", html)
            self.assertIn("不表示传播方向", html)
            self.assertEqual(html.count("data:font/woff;base64,"), 2)
            self.assertIn("SIL OPEN FONT LICENSE Version 1.1", html)
            self.assertEqual(len(list(Path(tmp).glob("*.html"))), 1)

    def test_verified_draft_is_accepted_without_body_changes(self):
        doc, rep, raw = core.parse_file(DRAFT)
        self.assertEqual(rep.errors, [], list(rep.lines()))
        day = doc["days"][0]
        self.assertEqual(day["date"], "2026-10-27")
        self.assertEqual(len(day["items"]), 6)
        self.assertIn("2011至2020年的年均增量", core.body_plain(day["items"][3]))
        self.assertNotIn("近十年平均水平", core.body_plain(day["items"][3]))
        self.assertEqual(sum(len(core.RE_LINK.findall(t)) for it in day["items"]
                             for s in it["sections"] for t in core.block_texts(s["blocks"])), 12)

    def test_flip_is_standalone_and_keeps_links_and_full_text(self):
        doc, rep, raw = core.parse_file(DRAFT)
        self.assertEqual(rep.errors, [])
        day = doc["days"][0]
        geo = Geo()
        layout, rep = sheet.load(None, day, geo, {day["date"]: {"1", "2", "3", "4", "5", "x"}})
        html = flip.render_flip_day(geo, day, layout, {"standalone": True}, DRAFT.name)
        self.assertEqual(page.verify(day, html), [])
        tags = Tags(html).tags
        links = [a["href"] for tag, a in tags if tag == "a" and a.get("href", "").startswith("http")]
        self.assertEqual(Counter(links), Counter(url for _, url in core.RE_LINK.findall(raw)))
        self.assertEqual([a["id"] for tag, a in tags if tag == "section" and "pg" in a.get("class", "").split()],
                         [f"p{i}" for i in range(7)])
        self.assertFalse(any(tag == "details" for tag, _ in tags))
        self.assertFalse(any(tag in ("script", "link", "img") and
                             any(str(a.get(k, "")).startswith("http") for k in ("src", "href")) for tag, a in tags))
        self.assertNotIn('../index.html', html)
        self.assertNotIn("原期重制", html)
        wmo = re.search(r'<article class="story" id="s-4">(.*?)</article>', html, re.S)[1]
        self.assertIn("上线时刻无法独立核定", wmo)
        self.assertIn('class="q">44.9', html)
        self.assertIn('class="dt past">2025年', html)

    def test_cover_contains_only_the_issue_and_contents_not_production_notes(self):
        doc, rep, raw = core.parse_file(DRAFT)
        day = doc["days"][0]
        geo = Geo()
        layout, rep = sheet.load(None, day, geo, {day["date"]: {"1", "2", "3", "4", "5", "x"}})
        html = flip.render_flip_day(geo, day, layout, {"standalone": True}, DRAFT.name)
        cover = re.search(r'<section class="pg pg-cover".*?</section>', html, re.S)[0]
        self.assertIn("2026年10月27日", cover)
        self.assertIn("5+1 条", cover)
        self.assertEqual(cover.count('class="ov-row'), 6)
        for text in ("旧期", "试读", "制作", "底稿", "本期记录", "截稿", "上线时刻", "左右滑动", "正文中的"):
            with self.subTest(text=text):
                self.assertNotIn(text, cover)

    def test_return_link_is_always_visible_safe_area_aware_and_touch_sized(self):
        template = (ROOT / "tools/flip.html").read_text(encoding="utf-8")
        css = (ROOT / "tools/flip.css").read_text(encoding="utf-8")
        screen_css = css.split("@media print")[0]
        attrs = [a for tag, a in Tags(template).tags if a.get("id") == "to-toc"]
        self.assertEqual(len(attrs), 1)
        self.assertEqual(attrs[0].get("href"), "#p0")
        self.assertNotIn("hidden", attrs[0])
        self.assertNotRegex(screen_css, r"[^{}]*\.to-toc[^{}]*\{[^}]*display:\s*none")
        rule = re.search(r"\.to-toc\s*\{([^}]+)\}", screen_css)[1]
        for declaration in ("position: fixed", "display: inline-flex", "min-height: 44px", "min-width: 44px", "env(safe-area-inset-bottom, 0px)"):
            self.assertIn(declaration, rule)
        self.assertIn("viewport-fit=cover", template)
        self.assertRegex(screen_css, r"padding-bottom:\s*calc\(96px \+ env\(safe-area-inset-bottom, 0px\)\)")

    def test_return_link_preserves_native_anchor_navigation(self):
        result = subprocess.run(["node", str(ROOT / "tests/return_navigation.js")], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
