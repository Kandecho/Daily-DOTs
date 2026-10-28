"""Use installed CJK fonts; subset only this issue's visible text, without network."""
import base64
from html import escape
from html.parser import HTMLParser
import io
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

FONT_DIR = Path(__file__).with_name("fonts")
SYSTEM_FONT_DIR = Path("/usr/share/fonts/opentype/noto")
FONT_FILES = ("NotoSerifCJK-Bold.ttc", "NotoSansCJK-Regular.ttc")
LICENSE = Path(__file__).with_name("fonts") / "OFL.txt"


def font_directory(requested=None):
    candidates = [Path(requested)] if requested is not None else [FONT_DIR, SYSTEM_FONT_DIR]
    for directory in candidates:
        if all((directory / name).is_file() for name in FONT_FILES):
            return directory
    raise ValueError("缺少字体 " + ", ".join(FONT_FILES) + "；检查 " +
                     ", ".join(map(str, candidates)) + "，或用 --font-dir 指向已有字体目录")


class VisibleText(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.in_body = False
        self.skip = False
        self.text = ""
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
        if tag in ("script", "style"):
            self.skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = False

    def handle_data(self, text):
        if self.in_body and not self.skip:
            self.text += text


def embed(html, font_dir=None):
    font_dir = font_directory(font_dir)
    text = VisibleText(html).text
    rules, info = [], []
    for file, family, weight, style in [
        ("NotoSerifCJK-Bold.ttc", "Daily Serif SC", 700, "Bold"),
        ("NotoSansCJK-Regular.ttc", "Daily Sans SC", 400, "Regular"),
    ]:
        font = TTFont(font_dir / file, fontNumber=2, recalcTimestamp=False)
        original = font["name"].getDebugName(1)
        if font["OS/2"].fsType != 0:
            raise ValueError(f"字体嵌入权限需复核：{file}")
        missing = sorted({ord(c) for c in text if not c.isspace()} - set(font.getBestCmap()))
        if missing:
            raise ValueError(f"字体缺字：{file} {missing}")
        opts = subset.Options()
        opts.recalc_timestamp = False
        opts.name_IDs = ["*"]
        opts.name_legacy = True
        sub = subset.Subsetter(options=opts)
        sub.populate(text=text)
        sub.subset(font)
        psname = family.replace(" ", "") + "-" + style
        names = {1: family, 2: style, 3: psname, 4: family + " " + style, 6: psname, 16: family, 17: style}
        for record in font["name"].names:
            if record.nameID in names:
                record.string = names[record.nameID].encode(record.getEncoding())
        if "CFF " in font:
            cff = font["CFF "].cff
            cff.fontNames[0] = psname
            cff.topDictIndex[0].FamilyName = family
            cff.topDictIndex[0].FullName = family + " " + style
        font.flavor = "woff"  # WOFF2's Brotli is absent; WOFF needs no installation.
        buf = io.BytesIO()
        font.save(buf)
        payload = buf.getvalue()
        # Re-open the actual emitted subset, not just the source font.
        emitted = TTFont(io.BytesIO(payload))
        if {ord(c) for c in text if not c.isspace()} - set(emitted.getBestCmap()):
            raise ValueError("子集字体遗漏正文用字")
        encoded = base64.b64encode(payload).decode("ascii")
        rules.append(f'@font-face{{font-family:"{family}";font-style:normal;font-weight:{weight};font-display:swap;src:url(data:font/woff;base64,{encoded}) format("woff")}}')
        info.append({"source": original, "weight": weight, "format": "woff", "bytes": len(payload),
                     "glyphs": len(emitted.getGlyphOrder()), "missing_visible_chars": 0, "license": "SIL OFL 1.1"})
    rules.append(':root{--serif:"Daily Serif SC","Noto Serif SC","Source Han Serif SC","Songti SC",serif;--sans:"Daily Sans SC","PingFang SC","Noto Sans SC","Microsoft YaHei",system-ui,sans-serif}')
    license_text = LICENSE.read_text(encoding="utf-8")
    return (html.replace("</style>", "\n" + "\n".join(rules) + "\n</style>", 1)
            .replace("</head>", '<template id="font-license"><pre>' + escape(license_text) + '</pre></template>\n</head>', 1)), info
