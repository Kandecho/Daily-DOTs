"""TEST fixtures: build a complete site without changing source or publishing."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from test_pipeline import test_draft

ROOT = Path(__file__).resolve().parents[1]


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="TEST_publication_")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def draft(self, date="2098-12-31", **kwargs):
        return test_draft(self.root / "editions" / date / f"原稿_{date}.md", date=date, count=1, **kwargs)

    def build(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "tools/site.py"), "--build", "--root", str(self.root), *map(str, args)],
                              capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})

    def test_complete_site_has_only_pages_and_preserves_source_and_urls(self):
        draft = self.draft()
        before = draft.read_bytes()
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = self.root / "_site"
        files = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
        self.assertEqual(files, {"index.html", "editions/2098-12-31/全球晚间新闻_2098-12-31_翻页.html"})
        html = (out / "editions/2098-12-31/全球晚间新闻_2098-12-31_翻页.html").read_text(encoding="utf-8")
        self.assertIn('href="../../index.html"', html)
        self.assertIn("https://example.invalid/test/1", html)
        self.assertEqual(html.count("data:font/woff;base64,"), 2)
        self.assertEqual(draft.read_bytes(), before)
        self.assertEqual(list((self.root / "editions").rglob("*.html")), [])
        self.assertFalse((self.root / "index.html").exists())
        previous = {p.relative_to(out): p.read_bytes() for p in out.rglob("*.html")}
        self.assertEqual(self.build().returncode, 0)
        self.assertEqual({p.relative_to(out): p.read_bytes() for p in out.rglob("*.html")}, previous)
        self.draft("2099-01-01", mutate=lambda m: m["layout"]["stories"][0]["components"].append({"type": "unknown"}))
        self.assertEqual(self.build().returncode, 1)
        self.assertEqual({p.relative_to(out): p.read_bytes() for p in out.rglob("*.html")}, previous)

    def test_failed_edition_does_not_publish_partial_site(self):
        self.draft()
        # A complete first issue followed by an invalid second issue.
        self.draft("2099-01-01", mutate=lambda m: m["layout"]["stories"][0]["components"].append({"type": "unknown"}))
        result = self.build()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("不支持", result.stderr)
        self.assertFalse((self.root / "_site").exists())
        self.assertEqual(list(self.root.glob(".site-*")), [])

    def test_missing_fonts_leave_previous_site_unchanged(self):
        self.draft()
        out = self.root / "_site"
        out.mkdir()
        (out / "index.html").write_text("TEST previous site", encoding="utf-8")
        result = self.build("--font-dir", self.root / "missing")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("字体", result.stderr)
        self.assertEqual((out / "index.html").read_text(encoding="utf-8"), "TEST previous site")

    def test_bad_font_hash_prevents_any_site_output(self):
        self.draft()
        fonts = self.root / "fonts"
        fonts.mkdir()
        for name in ("NotoSerifCJK-Bold.ttc", "NotoSansCJK-Regular.ttc"):
            (fonts / name).write_bytes(b"TEST corrupt font")
        result = self.build("--font-dir", fonts)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("SHA-256", result.stderr)
        self.assertFalse((self.root / "_site").exists())

    def test_unexpected_local_output_file_is_not_deleted(self):
        self.draft()
        out = self.root / "_site"
        out.mkdir()
        local = out / "TEST-local-notes.md"
        local.write_text("TEST keep me", encoding="utf-8")
        result = self.build()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("拒绝替换", result.stderr)
        self.assertEqual(local.read_text(encoding="utf-8"), "TEST keep me")

    def test_empty_or_inconsistent_dates_do_not_create_site(self):
        for kind in ("empty", "metadata", "directory"):
            with self.subTest(kind=kind):
                if kind == "metadata":
                    self.draft(mutate=lambda m: m.update(issue_date="2099-01-01"))
                if kind == "directory":
                    folder = self.root / "editions/2098-12-31"
                    folder.rename(folder.with_name("2098-02-30"))
                result = self.build()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse((self.root / "_site").exists())

    def test_misnamed_edition_directory_is_not_silently_skipped(self):
        self.draft()
        misplaced = self.draft("2099-01-01")
        misplaced.parent.rename(misplaced.parent.with_name("2099-1-1"))
        result = self.build()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("期目录", result.stderr)
        self.assertFalse((self.root / "_site").exists())


if __name__ == "__main__":
    unittest.main()
