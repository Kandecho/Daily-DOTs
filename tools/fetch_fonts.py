"""Download the two official Noto TTCs, or verify an existing/cache copy."""
import argparse
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.request import urlopen

FONT_DIR = Path(__file__).with_name("fonts")
# Versions, official URLs and SHA-256 are documented in THIRD_PARTY_NOTICES.md.
FONTS = {
    "NotoSerifCJK-Bold.ttc": (
        "https://github.com/notofonts/noto-cjk/raw/Serif2.003/Serif/OTC/NotoSerifCJK-Bold.ttc",
        "1505ee3b9c0890fae6302ee0e9c6fd74d690f4a55a6ace1d9944f3f6352d622d"),
    "NotoSansCJK-Regular.ttc": (
        "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/OTC/NotoSansCJK-Regular.ttc",
        "b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a"),
}


def verify(path, expected):
    if not path.is_file():
        raise ValueError(f"缺少字体：{path}")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"字体 SHA-256 不匹配：{path}；期望 {expected}，实际 {actual}")


def verify_fonts(directory):
    for name, (_, expected) in FONTS.items():
        verify(directory / name, expected)


def provision(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in FONTS.items():
        target = directory / name
        if target.exists():
            verify(target, expected)  # Cache hits must pass exactly the same check.
            continue
        staged = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as tmp:
                staged = Path(tmp.name)
                with urlopen(url, timeout=120) as response:
                    shutil.copyfileobj(response, tmp)
            verify(staged, expected)
            staged.replace(target)
        finally:
            if staged is not None and staged.exists():
                staged.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, default=FONT_DIR)
    parser.add_argument("--check-only", action="store_true", help="只校验本地字体，不联网")
    args = parser.parse_args(argv)
    try:
        (verify_fonts if args.check_only else provision)(args.font_dir)
        print("两份字体 SHA-256 校验通过。")
        return 0
    except (OSError, ValueError) as exc:
        print(f"字体准备失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
