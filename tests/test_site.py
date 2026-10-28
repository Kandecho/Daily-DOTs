"""TEST edition fixtures only; exercise the static Pages entry CLI offline."""
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
# Child CLIs print Chinese; force UTF-8 pipes so tests also run on Windows.
UTF8_ENV = {**os.environ, "PYTHONUTF8": "1"}


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs))


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="TEST_pages_")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def edition(self, date):
        folder = self.root / "editions" / date
        folder.mkdir(parents=True, exist_ok=True)
        meta = json.dumps({"issue_date": date, "title": "TEST"})
        (folder / f"原稿_{date}.md").write_text(f"---\n{meta}\n---\n\n# TEST\n", encoding="utf-8")
        name = f"全球晚间新闻_{date}_翻页.html"
        year, month, day = map(int, date.split("-"))
        html = folder / name
        html.write_text(f"<!doctype html><title>TEST {year}年{month}月{day}日</title><p>TEST</p>", encoding="utf-8")
        return html

    def run_site(self):
        return subprocess.run([sys.executable, str(ROOT / "tools/site.py"), "--root", str(self.root)],
                              cwd=tempfile.gettempdir(), capture_output=True, text=True,
                              encoding="utf-8", env=UTF8_ENV)

    def test_latest_is_real_date_and_all_links_stay_under_project_prefix(self):
        self.edition("2098-12-31")
        newest = self.edition("2099-01-01")
        result = self.run_site()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = (self.root / "index.html").read_text(encoding="utf-8")
        links = Links(text).links
        latest = next(a for a in links if a.get("id") == "latest-issue")
        self.assertEqual(unquote(latest["href"]), newest.relative_to(self.root).as_posix())
        self.assertIn("2099-01-01", text)
        self.assertIn("2098-12-31", text)
        self.assertNotIn("今日", text)
        self.assertIn('<div class="mast"><h1 class="nameplate">Daily DOTs</h1>', text)
        self.assertIn('<button class="runner" id="theme"', text)
        self.assertEqual(len(links), 2, "只链接两期日报，不链接原稿")
        for link in links:
            url = urlsplit(urljoin("https://example.invalid/Daily-DOTs/", link["href"]))
            self.assertEqual(url.netloc, "example.invalid")
            self.assertTrue(url.path.startswith("/Daily-DOTs/"), url.path)
            target = self.root / unquote(url.path.removeprefix("/Daily-DOTs/"))
            self.assertTrue(target.is_file(), str(target))

    def test_single_edition_is_preserved_and_rerun_is_deterministic(self):
        issue = self.edition("2098-12-31")
        before = issue.read_bytes()
        result = self.run_site()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        homepage = (self.root / "index.html").read_bytes()
        self.assertEqual(self.run_site().returncode, 0)
        self.assertEqual((self.root / "index.html").read_bytes(), homepage)
        self.assertEqual(issue.read_bytes(), before)

    def test_incomplete_edition_preserves_existing_homepage(self):
        issue = self.edition("2098-12-31")
        issue.unlink()
        (self.root / "index.html").write_text("TEST previous homepage", encoding="utf-8")
        result = self.run_site()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual((self.root / "index.html").read_text(encoding="utf-8"), "TEST previous homepage")

    def test_metadata_date_mismatch_is_rejected(self):
        self.edition("2098-12-31")
        draft = self.root / "editions/2098-12-31/原稿_2098-12-31.md"
        draft.write_text(draft.read_text(encoding="utf-8").replace("2098-12-31", "2099-01-01"), encoding="utf-8")
        result = self.run_site()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.root / "index.html").exists())

    def test_extra_html_in_edition_is_rejected_not_guessed(self):
        issue = self.edition("2098-12-31")
        issue.with_name("全球晚间新闻_2098-12-31_翻页试读.html").write_bytes(issue.read_bytes())
        result = self.run_site()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.root / "index.html").exists())

    def test_html_date_mismatch_is_rejected(self):
        issue = self.edition("2098-12-31")
        issue.write_text(issue.read_text(encoding="utf-8").replace("2098年12月31日", "2099年1月1日"), encoding="utf-8")
        result = self.run_site()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.root / "index.html").exists())

    def test_empty_editions_fail_without_creating_homepage(self):
        result = self.run_site()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.root / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
