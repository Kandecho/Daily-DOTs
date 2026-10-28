"""One-command reuse of Claude newsfmt; only the standalone flip HTML is delivered.

python tools/daily.py editions/2026-10-27/原稿_2026-10-27.md
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tempfile

import core
import newsfmt

ROOT = Path(__file__).resolve().parents[1]


def layout_toml(day):
    """Adapt only locator maps; text emphasis/layout stay with Claude's renderer."""
    quote = lambda v: json.dumps(v, ensure_ascii=False)
    meta = day["meta"]
    ids = meta["layout"]["order"]
    lookup = {sid: core.item_key(it) for sid, it in zip(ids, day["items"])}
    mains = [it["number"] for it in day["items"] if it["kind"] == "main"]
    lines = [f'date = {quote(day["date"])}', f"lead = {mains[0]}", f"features = {mains[1:3]}"]
    for story in meta["layout"]["stories"]:
        if any(c.get("type") != "locator_map" for c in story.get("components", [])):
            raise ValueError("不支持的排版组件；当前只接受 locator_map 国家高亮定位图")
        maps = [c for c in story.get("components", []) if c["type"] == "locator_map"]
        if len(maps) > 1:
            raise ValueError("Claude 每条只接受一张定位图")
        for mp in maps:
            if mp.get("points"):
                raise ValueError("此适配只接受国家高亮定位图，不接受点位或传播路径")
            codes = [h["country_id"] for h in mp["highlights"]]
            lines += [f'\n[story.{lookup[story["story_id"]]}.map]',
                      f'countries = {quote(codes)}', f'view = {quote(mp["viewport"])}',
                      "points = []", f'caption = {quote(mp["caption"])}']
    return "\n".join(lines) + "\n"


class Audit(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links, self.ids, self.resource_urls, self.article_text = [], [], [], {}
        self.article = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag in ("link", "script", "img", "iframe", "source", "audio", "video", "object", "embed", "image", "use"):
            self.resource_urls += [attrs[k] for k in ("src", "href", "xlink:href", "data", "poster")
                                   if attrs.get(k) and not attrs[k].startswith(("data:", "#"))]
        if tag == "article":
            self.article = attrs["id"]
            self.article_text[self.article] = ""

    def handle_endtag(self, tag):
        if tag == "article":
            self.article = None

    def handle_data(self, text):
        if self.article:
            self.article_text[self.article] += text


def audit_html(raw, rendered, day):
    parsed = Audit(rendered)
    want_links = Counter(url for _, url in core.RE_LINK.findall(raw))
    have_links = Counter(link for link in parsed.links if link.startswith(("https://", "http://")))
    if want_links != have_links:
        raise ValueError("来源链接地址或数量变化")
    styles = "\n".join(re.findall(r'<style\b[^>]*>(.*?)</style>', rendered, re.S | re.I))
    css_urls = [u.strip().strip('\"\'') for u in re.findall(r'url\(\s*([^)]*)\)', styles, re.I)]
    if parsed.resource_urls or re.search(r"@import\b", styles, re.I) or any(
            not u.startswith(("data:", "#")) for u in css_urls):
        raise ValueError("单文件成品不允许外链资源")
    if len(parsed.ids) != len(set(parsed.ids)):
        raise ValueError("HTML ID 重复")
    if any(link.startswith("#") and link[1:] not in parsed.ids for link in parsed.links):
        raise ValueError("目录链接指向不存在的页")
    if any(link and not link.startswith(("#", "http://", "https://")) for link in parsed.links):
        raise ValueError("单文件存在依赖其他文件的链接")
    # Independently compare every marked source paragraph/heading, so the bridge
    # cannot lose a block and still pass the renderer's own round-trip check.
    chunks = re.findall(r'<!-- story .*?-->\n(.*?)<!-- endstory -->', raw, re.S)
    for chunk, item in zip(chunks, day["items"]):
        visible = core.plain(parsed.article_text[f's-{core.item_key(item)}'])
        blocks = re.findall(r'<!-- block \S+ (heading|paragraph) -->\s*(.*?)(?=<!--)', chunk, re.S)
        for kind, block in blocks:
            if kind == "heading":
                texts = [re.sub(r'^### ', "", block.strip())]
            else:
                report = core.Report("原稿块")
                parsed_blocks = core.parse_blocks(list(enumerate(block.strip().splitlines(), 1)), report)
                texts = list(core.block_texts(parsed_blocks))
                if report.errors:
                    raise ValueError("原稿块解析失败")
            if any(core.plain(text) not in visible for text in texts):
                raise ValueError(f'原稿文字遗漏：{item["title"]} / {block[:30]}')
    # 制作说明不进入阅读成品；新闻的数据/来源边界放在对应正文，受上面的全文回读保护。
    cover = re.search(r'<section class="pg pg-cover".*?</section>', rendered, re.S)[0]
    if any(f'class="{name}"' in cover for name in ("edition-note", "ov-note", "ov-src", "ov-hint")):
        raise ValueError("目录中混入制作说明或导语")
    if not re.search(r'<a\b[^>]*id="to-toc"[^>]*href="#p0"', rendered):
        raise ValueError("缺少原生回目录锚点")
    return {"source_links": sum(want_links.values()), "story_pages": len(day["items"]),
            "source_blocks": "pass", "source_urls": "pass", "local_resources": "pass",
            "navigation_targets": "pass", "clean_cover": "pass", "native_return_anchor": "pass",
            "browser_visual_interaction": "not_run"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("draft", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--build-dir", type=Path)
    ap.add_argument("--date", help="可选：断言原稿日期为 YYYY-MM-DD，不会替换原稿日期")
    ap.add_argument("--font-dir", type=Path, help="可选：两份 Noto CJK TTC 所在目录")
    ap.add_argument("--overwrite", action="store_true", help="显式允许替换同一期已有且内容不同的 HTML")
    args = ap.parse_args(argv)
    try:
        return build(args)
    except (OSError, ValueError, ImportError) as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1


def build(args):
    doc, rep, raw = core.parse_file(args.draft)
    if rep.errors or len(doc["days"]) != 1 or not doc["days"][0].get("meta"):
        print("\n".join(rep.lines()) or "需要单期原稿＋JSON元数据", file=sys.stderr)
        return 1
    day = doc["days"][0]
    if args.date and dt.date.fromisoformat(args.date).isoformat() != day["date"]:
        raise ValueError("--date 与原稿 issue_date 不一致；不会替换原稿日期")
    target = args.out or args.draft.with_name(f'全球晚间新闻_{day["date"]}_翻页.html')
    if target.resolve() == args.draft.resolve() or target.suffix.lower() != ".html":
        raise ValueError("输出必须是独立 .html 文件，不能覆盖原稿")
    for path in (args.draft, target):
        dates = re.findall(r'\d{4}-\d{2}-\d{2}', path.name)
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', path.parent.name):
            dates.append(path.parent.name)
        if any(date != day["date"] for date in dates):
            raise ValueError(f"文件名或期目录日期与 issue_date 不一致：{path}")
    if target.exists():
        old = target.read_text(encoding="utf-8")
        old_title = re.search(r'<title>(.*?)</title>', old, re.S)
        old_date = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', old_title[1]) if old_title else None
        if old_date and dt.date(*map(int, old_date.groups())).isoformat() != day["date"]:
            raise ValueError("输出目标属于另一日期，拒绝覆盖旧期")
    from font_subset import embed, font_directory
    fonts_dir = font_directory(args.font_dir)
    work = args.build_dir or ROOT / "_build" / day["date"]
    if target.resolve().is_relative_to((work / "dist").resolve()):
        raise ValueError("输出不能位于内部 dist 目录；请将最终 HTML 放在原稿旁或独立路径")
    sheets = work / "版面"
    sheets.mkdir(parents=True, exist_ok=True)
    (sheets / f'{day["date"]}.toml').write_text(layout_toml(day), encoding="utf-8")
    rc = newsfmt.main(["build", str(args.draft), "--sheets", str(sheets), "-o", str(work / "dist"), "--strict"])
    if rc:
        return rc
    rendered = (work / "dist/flip" / f'{day["date"]}.html').read_text(encoding="utf-8")
    rendered, fonts = embed(rendered, fonts_dir)
    try:
        audit = audit_html(raw, rendered, day)
    except ValueError as exc:
        print(f"成品检查失败：{exc}", file=sys.stderr)
        return 2
    if target.exists() and target.read_text(encoding="utf-8") != rendered and not args.overwrite:
        raise ValueError(f"已有不同内容的成品，未覆盖；确认同一期修订后加 --overwrite：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                     dir=target.parent, suffix=".tmp", delete=False) as tmp:
        tmp.write(rendered)
        staged = Path(tmp.name)
    staged.replace(target)
    audit.update(html_sha256=hashlib.sha256(rendered.encode()).hexdigest(), output=str(target),
                 input_sha256=hashlib.sha256(raw.encode()).hexdigest(), fonts=fonts,
                 output_bytes=len(rendered.encode("utf-8")))
    (work / "verification.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"交付：{target}；{audit['story_pages']} 条全文，{audit['source_links']} 个来源链接保留。")
    print("本次程序检查不包含浏览器视觉/触控验证。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
