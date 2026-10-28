"""翻页版：手机窄页，一条一页，按底稿顺序左右滑动翻页。第一页是当天 5+1 条的目录，不设头条，不折叠。

与报纸版共用解析、核对、地图和数字上色；版面单里只用到地图和接续。
"""

from core import HOME_HREF, NAME, SUBTITLE, cn_date, item_key, weekday
from page import esc, fill_template, inline, render_body, render_map, story_id


def page_id(n):
    return f"p{n}"


def render_flip_day(geo, day, layout, nav, source_name):
    items = day["items"]
    S = layout["stories"]

    # 第 0 页：目录
    rows = []
    for n, it in enumerate(items, start=1):
        x = it["kind"] == "explore"
        rows.append(
            f'<a class="ov-row{" ov-x" if x else ""}" href="#{page_id(n)}">'
            f'<span class="no">{"探索" if x else it["number"]}</span>'
            f'<span class="ov-t"><span class="domain">{esc(it["domain"])}</span> {inline(it["title"])}</span></a>')
    prev_a = f'<a href="{nav["prev"]}.html">‹ {cn_date(nav["prev"], False)}</a>' if nav.get("prev") else "<span></span>"
    next_a = f'<a href="{nav["next"]}.html">{cn_date(nav["next"], False)} ›</a>' if nav.get("next") else "<span></span>"
    n_main = sum(1 for i in items if i["kind"] == "main")
    count = f"{n_main}+1 条" if n_main < len(items) else f"{n_main} 条"
    home = HOME_HREF if nav.get("standalone") else "../index.html"
    # 单期成品没有前后日导航；旧的多日构建仍保留。
    mast_nav = "" if nav.get("standalone") else f'<nav class="mast-nav">{prev_a}<span class="mid"></span>{next_a}</nav>'
    dateline = f'{SUBTITLE} · {cn_date(day["date"])} {weekday(day["date"])}'
    cover = (
        f'<section class="pg pg-cover" id="{page_id(0)}"><div class="pg-in">'
        f'{mast_nav}{masthead(dateline, count)}'
        f'<nav class="ov" aria-label="目录">{"".join(rows)}</nav>'
        f'<p class="pg-foot"><a class="to-home" href="{home}">回到首页</a></p>'
        f'</div></section>')

    # 第 1…N 页：一条一页
    pages = [cover]
    for n, it in enumerate(items, start=1):
        key = item_key(it)
        st = S[key]
        x = it["kind"] == "explore"
        f = st.get("follows")
        fol = (f'<a class="follows" href="{f["date"]}.html#{page_id(follow_page(f, nav))}">续 {cn_date(f["date"], False)}</a>'
               if f else "")
        art = f'<div class="art ed">{render_map(geo, st["map"])}</div>' if "map" in st else ""
        pages.append(
            f'<section class="pg{" pg-x" if x else ""}" id="{page_id(n)}"><div class="pg-in">'
            f'<article class="story{" s-explore" if x else ""}" id="{story_id(key)}">'
            f'<p class="kicker"><span class="no">{"探索位" if x else it["number"]}</span>'
            f'<span class="domain">{esc(it["domain"])}</span>{fol}</p>'
            f'<h2 class="hl">{inline(it["title"])}</h2>{art}{render_body(it, issue=st["issue"])}</article>'
            f'<p class="pg-foot"><a class="to-toc" href="#{page_id(0)}">回到目录</a></p>'
            f'</div></section>')

    fill = {
        "{{TITLE}}": esc(f"{NAME}｜{cn_date(day['date'])}"),
        "{{PAGES}}": "\n".join(pages),
    }
    return fill_template("flip.html", fill, extra_css=["masthead.css", "flip.css"])


def masthead(left, right):
    """首页和目录页共用的报头：刊名、日期线，和坐在双线上的日月。样式在 masthead.css，切换在 theme.js。"""
    return (f'<div class="mast"><h1 class="nameplate">{NAME}</h1>'
            f'<div class="dateline"><span>{left}</span><span>{right}</span>{RUNNER}</div></div>')


# 一枚圆点：白天带一圈光芒；入夜时影子从右边移进来，把它遮成月牙。
RUNNER = ('<button class="runner" id="theme" type="button" aria-label="切换明暗"><svg viewBox="-13 -13 26 26" aria-hidden="true">'
          '<defs><mask id="dots-bite" maskUnits="userSpaceOnUse" x="-13" y="-13" width="26" height="26">'
          '<rect x="-13" y="-13" width="26" height="26" fill="#fff"/><circle class="bite" r="5.2" fill="#000"/></mask></defs>'
          '<circle class="rays" r="9.6" pathLength="48"/>'
          '<g class="body"><circle r="5.2" fill="currentColor" mask="url(#dots-bite)"/></g></svg></button>')


def follow_page(f, nav):
    """接续目标在那一天翻页版里的页码：主新闻编号就是页码，探索位是最后一页（页码 = 当天条数）。"""
    if f["key"] != "x":
        return int(f["key"])
    return nav.get("counts", {}).get(f["date"], 1)
