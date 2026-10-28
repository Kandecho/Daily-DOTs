"""TEST bytes stand in for remote responses; never fetch fonts during tests."""
import hashlib
from contextlib import redirect_stderr
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]


class FontProvisionTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "tools/fetch_fonts.py"
        self.assertTrue(path.is_file(), "font provisioning command is missing")
        spec = importlib.util.spec_from_file_location("test_fetch_fonts", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.tmp = tempfile.TemporaryDirectory(prefix="TEST_fonts_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = b"TEST font fixture"
        self.specs = {"TEST.ttc": ("https://example.invalid/font", hashlib.sha256(self.data).hexdigest())}
        self.patcher = patch.object(self.module, "FONTS", self.specs)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_download_is_verified_before_install_and_cache_hit_is_offline(self):
        with patch.object(self.module, "urlopen", return_value=io.BytesIO(self.data)):
            self.module.provision(self.root)
        self.assertEqual((self.root / "TEST.ttc").read_bytes(), self.data)
        with patch.object(self.module, "urlopen", side_effect=AssertionError("cache must not download")):
            self.module.provision(self.root)
        self.assertEqual(list(self.root.iterdir()), [self.root / "TEST.ttc"])

    def test_bad_download_hash_never_installs_font(self):
        with patch.object(self.module, "urlopen", return_value=io.BytesIO(b"TEST corrupt")):
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                self.module.provision(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_bad_cache_hash_fails_without_replacing_local_data(self):
        font = self.root / "TEST.ttc"
        font.write_bytes(b"TEST corrupt cache")
        with patch.object(self.module, "urlopen", side_effect=AssertionError("bad cache must fail closed")):
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                self.module.provision(self.root)
        self.assertEqual(font.read_bytes(), b"TEST corrupt cache")

    def test_missing_font_check_is_offline_and_download_failure_is_clean(self):
        with self.assertRaisesRegex(ValueError, "缺少字体"):
            self.module.verify_fonts(self.root)
        with patch.object(self.module, "urlopen", side_effect=URLError("TEST offline")):
            errors = io.StringIO()
            with redirect_stderr(errors):
                self.assertEqual(self.module.main(["--font-dir", str(self.root)]), 1)
            self.assertIn("字体准备失败", errors.getvalue())
            self.assertIn("TEST offline", errors.getvalue())
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
