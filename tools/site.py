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

from core import NAME, SUBTITLE, cn_date, edition_html_name, weekday
from flip import masthead
from font_subset import embed

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
        found.append({"date": date, "html": html.relative_to(root).as_posix()})
    if not found:
        raise ValueError("editions/ 中没有可发布的完整期次")
    return found


HOME_CSS = """
/* 首页：和目录页同一个报头，下面按日期列出各期 */
.home-in {
  max-width: 620px; margin: 0 auto; padding-block: 14px 48px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
}
.home .nameplate { margin-top: 18px; text-align: center; font-size: clamp(38px, 11vw, 56px); letter-spacing: .02em; padding-left: 0; }
.home .dateline { justify-content: space-between; margin-top: 8px; padding: 5px 2px; font-size: 13px; }
.home .issues { display: flex; flex-direction: column; margin-top: 6px; }
.home .issue {
  display: flex; align-items: baseline; gap: 12px; min-height: 54px; padding: 13px 2px;
  border-bottom: 1px solid var(--rule); text-decoration: none;
}
.issue .d { font: 700 18px/1.4 var(--serif); font-variant-numeric: tabular-nums; }
.issue .w { font-size: 13px; color: var(--muted); }
.issue .tag {
  margin-left: auto; padding: 4px 8px; border-radius: 3px;
  background: var(--accent); color: var(--paper); font: 700 12px/1 var(--sans); letter-spacing: .08em;
}
.issue:hover .d { text-decoration: underline; text-underline-offset: 4px; }
.issue:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
"""


def render(issues):
    """Use relative URLs so the same entry works locally and under a project URL."""
    def url(path):
        return escape(quote(path, safe="/"), quote=True)

    tools = Path(__file__).parent
    css = "\n".join((tools / name).read_text(encoding="utf-8") for name in ("style.css", "masthead.css")) + HOME_CSS
    def row(issue, latest):
        mark = ' id="latest-issue"' if latest else ""
        tag = '<span class="tag">最新</span>' if latest else ""
        return (f'<a class="issue"{mark} href="{url(issue["html"])}">'
                f'<time class="d" datetime="{issue["date"]}">{cn_date(issue["date"], False)}</time>'
                f'<span class="w">{weekday(issue["date"])}</span>{tag}</a>')

    rows = "\n".join(row(issue, i == 0) for i, issue in enumerate(issues))
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{NAME} · {SUBTITLE}</title>
<link rel="icon" href="data:,">
<style>
{css}
</style>
<script>
{(tools / "theme.js").read_text(encoding="utf-8")}
</script>
</head>
<body class="home">
<main class="home-in">
{masthead(SUBTITLE, f"共 {len(issues)} 期")}
<nav class="issues" aria-label="各期日报">
{rows}
</nav>
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
        text, _ = embed(render(issues))
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
