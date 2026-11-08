"""Download the pinned official fonts, or verify an existing/cache copy."""
import argparse
import hashlib
import io
import tarfile
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
    "LXGWWenKai-Regular.ttf": (
        "https://raw.githubusercontent.com/lxgw/LxgwWenKai/4becfb4d5cf0c92cfdb60a6e9b504bda43315325/fonts/TTF/LXGWWenKai-Regular.ttf",
        "2d73eea94ad808999d90c0000c239a84a33b09d4bc6ab6c5b8bbf1eda8a7fc8b"),
    "LiberationSerif-Italic.ttf": (
        "https://github.com/liberationfonts/liberation-fonts/files/7261482/liberation-fonts-ttf-2.1.5.tar.gz",
        "0e3dea9f8d613e006ccfa62201f33e265d19167bd0907725c3e145368b04fc2e"),
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
                    if name == "LiberationSerif-Italic.ttf":
                        data = response.read()
                        if hashlib.sha256(data).hexdigest() != "7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0":
                            raise ValueError("Liberation 字体归档 SHA-256 不匹配")
                        # Read only the fixed font member; never extract paths or execute files.
                        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                            member = archive.getmember("liberation-fonts-ttf-2.1.5/LiberationSerif-Italic.ttf")
                            if not member.isfile():
                                raise ValueError("Liberation 字体归档成员不是文件")
                            with archive.extractfile(member) as source:
                                shutil.copyfileobj(source, tmp)
                    else:
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
        print("字体 SHA-256 校验通过。")
        return 0
    except (OSError, ValueError) as exc:
        print(f"字体准备失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
