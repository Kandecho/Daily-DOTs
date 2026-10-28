"""Refresh the static Pages entrance after accepting local edition files.

python tools/site.py
Only index.html is written. No network, Git commands, or edition changes.
"""
import argparse
import datetime as dt
from html import escape
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote

from core import NAME, SUBTITLE, edition_html_name

ROOT = Path(__file__).resolve().parents[1]


def editions(root):
    """Return complete, consistently dated original/HTML pairs, newest first."""
    found = []
    for folder in sorted((root / "editions").glob("*"), reverse=True):
        if not folder.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", folder.name):
            continue
        date = dt.date.fromisoformat(folder.name).isoformat()
        draft = folder / f"原稿_{date}.md"
        html = folder / edition_html_name(date)
        if not draft.is_file() or sorted(folder.glob("*.html")) != [html]:
            raise ValueError(f"{date} 需要一份同日期原稿和唯一的 {html.name}")
        if any(p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) for p in (folder, draft, html)):
            raise ValueError(f"{date} 不接受符号链接或项目以外的文件")
        raw = draft.read_text(encoding="utf-8")
        front = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", raw, re.S)
        if not front:
            raise ValueError(f"{date} 原稿缺少 JSON 元数据")
        meta = json.loads(front[1])
        if not isinstance(meta, dict) or meta.get("issue_date") != date:
            raise ValueError(f"{date} 原稿 issue_date 与期目录不一致")
        text = html.read_text(encoding="utf-8")
        title = re.search(r"<title\b[^>]*>(.*?)</title>", text, re.S | re.I)
        match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", title[1]) if title else None
        if not match or dt.date(*map(int, match.groups())).isoformat() != date:
            raise ValueError(f"{date} HTML 标题日期与期目录不一致")
        found.append({"date": date, "html": html.relative_to(root).as_posix(),
                      "draft": draft.relative_to(root).as_posix()})
    if not found:
        raise ValueError("editions/ 中没有可发布的完整期次")
    return found


def render(issues):
    """Use relative URLs so the same entry works locally and under a project URL."""
    def url(path):
        return escape(quote(path, safe="/"), quote=True)

    latest = issues[0]
    history = "\n".join(
        f'<li><a href="{url(issue["html"])}"><time datetime="{issue["date"]}">{issue["date"]}</time> · 阅读日报</a>'
        f'<a class="source" href="{url(issue["draft"])}">原稿</a></li>'
        for issue in issues[1:])
    history = f'<ul class="archive">{history}</ul>' if history else '<p class="muted">暂无更早期次。</p>'
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{NAME} · {SUBTITLE}</title>
<style>
:root {{ color-scheme: light dark; --paper: #faf8f4; --ink: #24211e; --muted: #6b645c; --line: #d9d2c7; --card: #fffdf9; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--paper); color: var(--ink); font-family: system-ui, "PingFang SC", sans-serif; line-height: 1.7; }}
main {{ max-width: 680px; margin: 0 auto; padding: 48px 24px 72px; }}
h1 {{ margin: 0; font-family: "Songti SC", "Noto Serif CJK SC", serif; font-size: clamp(1.7rem, 6vw, 2.2rem); }}
.sub {{ margin: 4px 0 36px; color: var(--muted); }}
h2 {{ font-size: 1.1rem; font-weight: 600; margin: 0 0 16px; }}
p {{ margin: 12px 0; }}
a {{ color: inherit; text-underline-offset: 4px; }}
a:focus-visible {{ outline: 3px solid currentColor; outline-offset: 5px; }}
.latest {{ padding: 24px; border: 1px solid var(--line); background: var(--card); border-radius: 4px; }}
.date {{ font-size: 1.8rem; font-variant-numeric: tabular-nums; margin: 0 0 22px; }}
.read {{ display: inline-flex; align-items: center; min-height: 48px; padding: 8px 18px; background: var(--ink); color: var(--paper); border-radius: 3px; text-decoration: none; }}
.source {{ display: inline-flex; align-items: center; min-height: 44px; margin-left: 18px; color: var(--muted); font-size: .95rem; }}
.history {{ margin-top: 38px; }}
.archive {{ padding: 0; margin: 0; list-style: none; }}
.archive li {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0 12px; padding: 10px 0; border-bottom: 1px solid var(--line); }}
.archive li > a:first-child {{ display: inline-flex; align-items: center; min-height: 44px; }}
.muted {{ color: var(--muted); }}
@media (prefers-color-scheme: dark) {{ :root {{ --paper: #1f1d1a; --ink: #f1e9df; --muted: #b9b0a5; --line: #514b43; --card: #27241f; }} }}
@media (max-width: 400px) {{ main {{ padding: 30px 16px 48px; }} .latest {{ padding: 20px; }} }}
</style>
</head>
<body>
<main>
<h1>{NAME}</h1>
<p class="sub">{SUBTITLE}</p>
<section class="latest" aria-labelledby="latest-heading">
<h2 id="latest-heading">最新一期</h2>
<p class="date"><time datetime="{latest["date"]}">{latest["date"]}</time></p>
<a class="read" id="latest-issue" href="{url(latest["html"])}" aria-label="阅读 {latest["date"]} 日报">阅读日报 →</a>
<a class="source" href="{url(latest["draft"])}">原稿</a>
</section>
<section class="history" aria-labelledby="history-heading">
<h2 id="history-heading">往期日报</h2>
{history}
</section>
</main>
</body>
</html>
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="项目根目录，默认脚本所在项目")
    args = parser.parse_args(argv)
    staged = None
    try:
        root = args.root.resolve()
        issues = editions(root)
        text = render(issues)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=root, suffix=".tmp", delete=False) as tmp:
            staged = Path(tmp.name)
            tmp.write(text)
        staged.replace(root / "index.html")
        print(f"首页已更新：{issues[0]['date']}；共 {len(issues)} 期。未执行 Git 或网站发布。")
        return 0
    except (OSError, ValueError) as exc:
        print(f"首页更新失败：{exc}", file=sys.stderr)
        return 1
    finally:
        if staged is not None and staged.exists():
            staged.unlink()


if __name__ == "__main__":
    sys.exit(main())
