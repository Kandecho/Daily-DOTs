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
            self.assertIn("着色为报道涉及国家，不代表疫情分布范围。", html)
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
        self.assertEqual([a["href"] for tag, a in tags if tag == "a" and not a.get("href", "").startswith(("#", "http"))],
                         [core.HOME_HREF])
        self.assertIn('<h1 class="nameplate">Daily DOTs</h1>', html)
        self.assertIn("<title>Daily DOTs｜2026年10月27日</title>", html)
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
        self.assertIn("全球晚间新闻 · 2026年10月27日", cover)
        self.assertIn("5+1 条", cover)
        self.assertEqual(cover.count('class="ov-row'), 6)
        for text in ("旧期", "试读", "制作", "底稿", "本期记录", "截稿", "上线时刻", "左右滑动", "正文中的"):
            with self.subTest(text=text):
                self.assertNotIn(text, cover)

    def test_country_labels_do_not_overlap(self):
        from geo import map_svg
        svg = map_svg(Geo(), {"countries": ["COD", "KEN", "NGA"], "view": [-20, -36, 53, 38]})
        labels = [(float(x), float(y), name) for x, y, name in
                  re.findall(r'<text class="cname" x="([\d.-]+)" y="([\d.-]+)"[^>]*>([^<]+)</text>', svg)]
        self.assertEqual(sorted(n for _, _, n in labels), sorted(["刚果（金）", "肯尼亚", "尼日利亚"]))
        boxes = [(x - 12.5 * len(n), y - 22, x + 12.5 * len(n), y + 6) for x, y, n in labels]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertFalse(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3], (a, b))

    def render_sample(self):
        doc, rep, raw = core.parse_file(DRAFT)
        day = doc["days"][0]
        geo = Geo()
        layout, rep = sheet.load(None, day, geo, {day["date"]: {"1", "2", "3", "4", "5", "x"}})
        return flip.render_flip_day(geo, day, layout, {"standalone": True}, DRAFT.name), day

    def test_each_page_has_its_own_bottom_button(self):
        html, day = self.render_sample()
        # 条目里还嵌着小节 <section>，按每页开头切分，而不是找配对的结束标签
        pages = re.findall(r'<section class="pg[^"]*" id="p(\d+)">(.*?)(?=<section class="pg[ "]|</main>)', html, re.S)
        self.assertEqual(len(pages), len(day["items"]) + 1)
        for n, body in pages:
            foot = re.findall(r'<p class="pg-foot"><a class="(to-home|to-toc)" href="([^"]+)">', body)
            want = ("to-home", core.HOME_HREF) if n == "0" else ("to-toc", "#p0")
            self.assertEqual(foot, [want], f"p{n}")
        css = (ROOT / "tools/flip.css").read_text(encoding="utf-8").split("@media print")[0]
        foot_rule = re.search(r"\.pg-foot\s*\{([^}]+)\}", css)[1]
        for declaration in ("position: sticky", "bottom: 0", "margin: auto 0 0", "env(safe-area-inset-bottom, 0px)"):
            self.assertIn(declaration, foot_rule)
        button_rule = re.search(r"\.to-toc, \.to-home\s*\{([^}]+)\}", css)[1]
        for declaration in ("display: inline-flex", "min-height: 44px", "min-width: 44px"):
            self.assertIn(declaration, button_rule)
        self.assertIn("viewport-fit=cover", (ROOT / "tools/flip.html").read_text(encoding="utf-8"))

    def test_masthead_switch_is_shared_and_degrades(self):
        html, _ = self.render_sample()
        cover = re.search(r'<section class="pg pg-cover".*?</section>', html, re.S)[0]
        self.assertIn('<div class="mast"><h1 class="nameplate">Daily DOTs</h1><div class="dateline">', cover)
        self.assertEqual(html.count('<button class="runner" id="theme" type="button"'), 1)
        self.assertNotIn('class="mast-nav"', cover)
        css = (ROOT / "tools/masthead.css").read_text(encoding="utf-8")
        dark = re.findall(r':root\[data-theme="dark"\]\s*\{([^}]+)\}', css)[0]
        for token in ("--run-x", "--run-turn", "--rays-o", "--bite-x", "--body-x"):
            self.assertIn(token, css.split("@media")[0])
            self.assertIn(token, dark)
        js = (ROOT / "tools/theme.js").read_text(encoding="utf-8")
        for needed in ("startViewTransition", "prefers-reduced-motion", "theme-fade", "newsfmt-theme"):
            self.assertIn(needed, js)

    def test_return_link_preserves_native_anchor_navigation(self):
        result = subprocess.run(["node", str(ROOT / "tests/return_navigation.js")], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
