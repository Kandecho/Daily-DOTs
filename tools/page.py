"""版面渲染：底稿 + 版面单 → 一天一页的 HTML。组件固定，版面单只决定用哪些组件、放什么图。"""

import datetime as dt
import html
import re
from html.parser import HTMLParser
from pathlib import Path

from core import RE_LINK, body_plain, block_texts, cn_date, item_key, plain, weekday
from geo import map_svg

HERE = Path(__file__).parent
NAMEPLATE = "晚间简报"


# 正文里的数字（可带千位逗号、小数、万/亿）默认上色；紧挨字母、连字符或“第”的是编号或序号，不算。
RE_QTY = re.compile(r"(?<![\dA-Za-z.:,\-_第])(\d(?:[\d,]*\d)?(?:\.\d+)?(?:万|亿)?)")
NOT_QTY_AFTER = re.compile(r"[月日时秒号点:：]|分(?!钟)|世纪|年代|指数")
RE_YEAR = re.compile(r"(19|20)\d\d")


def quantity(m, text):
    """排除日期、时刻、年代、年份（含“2018—2020年”这类区间）和指数名；“27年”“400万年”这类时长保留。"""
    num, after = m.group(1), text[m.end():m.end() + 2]
    if NOT_QTY_AFTER.match(after):
        return m.group(0)
    if RE_YEAR.fullmatch(num) and after[:1] in ("年", "—", "–", "-", "至", "到"):
        return m.group(0)
    return f'<span class="q">{num}</span>'


RE_TAG = re.compile(r"(<[^>]+>)")


def mark_numbers(fragment):
    """给 HTML 片段里标签之外的数量包上 <span class="q">。"""
    parts = RE_TAG.split(fragment)
    for i in range(0, len(parts), 2):
        seg = parts[i]
        parts[i] = RE_QTY.sub(lambda m: quantity(m, seg), seg)
    return "".join(parts)


# 日期：先换算成一个日期区间，再和简报日期比较。包含简报日期的算“当天”，不标；整个在它之前的是过去，之后的是未来。
RE_DATE = re.compile(
    r"(?<![\d.])(?:"
    r"(?P<ya>(?:19|20)\d\d)[—–\-至](?P<yb>(?:19|20)\d\d)年"
    r"|(?P<dec>(?:19|20)\d\d)年代"
    r"|(?:(?P<y>(?:19|20)\d\d)年)?(?P<m>\d{1,2})月(?:(?P<d>\d{1,2})日)?"
    r"|(?P<yo>(?:19|20)\d\d)年"
    r"|本月(?P<dm>\d{1,2})日"
    r"|(?P<do>\d{1,2})日(?![后内])"  # “3日后”“3日内”是时长，不是日期
    r")")


def date_ctx(issue):
    """一条新闻的日期上下文：只写“N日”时沿用这一条里前面最近出现的年月，没有就用简报日期的年月。"""
    d = dt.date.fromisoformat(issue)
    return {"issue": d, "year": d.year, "month": d.month}


def date_span(m, ctx):
    g = m.groupdict()
    try:
        if g["ya"]:
            lo, hi = dt.date(int(g["ya"]), 1, 1), dt.date(int(g["yb"]), 12, 31)
        elif g["dec"]:
            y = int(g["dec"])
            lo, hi = dt.date(y, 1, 1), dt.date(y + 9, 12, 31)
        elif g["m"]:
            mo = int(g["m"])
            # 没写年份时取简报那一年，不沿用前文年份；只在跨年边界修正：
            # 比简报晚 6 个月以上算上一年（1 月出刊写“12月30日”），早 11 个月以上算下一年（12 月底写“1月2日”）
            y = int(g["y"]) if g["y"] else ctx["issue"].year
            if not g["y"]:
                gap = (dt.date(y, mo, int(g["d"] or 15)) - ctx["issue"]).days
                y += -1 if gap > 183 else 1 if gap < -335 else 0
            ctx["year"], ctx["month"] = y, mo
            if g["d"]:
                lo = hi = dt.date(y, mo, int(g["d"]))
            else:
                lo = dt.date(y, mo, 1)
                hi = dt.date(y + mo // 12, mo % 12 + 1, 1) - dt.timedelta(days=1)
        elif g["yo"]:
            y = int(g["yo"])
            lo, hi = dt.date(y, 1, 1), dt.date(y, 12, 31)
        elif g["dm"]:
            ctx["year"], ctx["month"] = ctx["issue"].year, ctx["issue"].month
            lo = hi = dt.date(ctx["year"], ctx["month"], int(g["dm"]))
        else:
            lo = hi = dt.date(ctx["year"], ctx["month"], int(g["do"]))
    except ValueError:  # 不存在的日期（如 13月、2月30日）原样保留
        return m.group(0)
    if lo <= ctx["issue"] <= hi:
        return m.group(0)
    when = "past" if hi < ctx["issue"] else "fut"
    return f'<span class="dt {when}">{m.group(0)}</span>'


def mark_dates(fragment, ctx):
    parts = RE_TAG.split(fragment)
    for i in range(0, len(parts), 2):
        parts[i] = RE_DATE.sub(lambda m: date_span(m, ctx), parts[i])
    return "".join(parts)


def inline(text, numbers=False, ctx=None):
    """numbers=True 时给数量上色；再给出 ctx（简报日期上下文）时，标出不是当天的日期。"""
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    # The whole input was already escaped above; unescape once before escaping
    # the URL as an attribute, otherwise query separators become &amp;amp;.
    out = RE_LINK.sub(lambda m: f'<a href="{html.escape(html.unescape(m.group(2)))}">{m.group(1)}</a>', out)
    if numbers and ctx:
        out = mark_dates(out, ctx)
    return mark_numbers(out) if numbers else out


def esc(s):
    return html.escape(s, quote=True)


# ---------- 正文块 ----------

def render_blocks(blocks, ctx=None):
    out = []
    for b in blocks:
        t = b["type"]
        if t == "p":
            out.append(f"<p>{inline(b['text'], numbers=True, ctx=ctx)}</p>")
        elif t == "key":
            out.append(f'<p class="key">{inline(b["text"], numbers=True, ctx=ctx)}</p>')
        elif t in ("ul", "ol"):
            out.append(f"<{t}>" + "".join(f"<li>{inline(x, numbers=True, ctx=ctx)}</li>" for x in b["items"]) + f"</{t}>")
        elif t == "table":
            al = b["align"]
            a = lambda i: al[i] if i < len(al) else "left"  # noqa: E731
            th = "".join(f'<th class="a-{a(i)}">{inline(c)}</th>' for i, c in enumerate(b["head"]))
            trs = "".join("<tr>" + "".join(f'<td class="a-{a(i)}">{inline(c)}</td>' for i, c in enumerate(r)) + "</tr>"
                          for r in b["rows"])
            out.append(f'<div class="table"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')
    return "".join(out)


def render_body(item, quote=None, issue=None):
    ctx = date_ctx(issue) if issue else None
    parts = []
    for i, s in enumerate(item["sections"]):
        parts.append(f'<section class="sec sec-{s["key"]}"><h4>{s["label"]}</h4>{render_blocks(s["blocks"], ctx)}</section>')
        if quote and i == 0:
            parts.append(f'<blockquote class="pull ed">{inline(quote)}</blockquote>')
    return f'<div class="body">{"".join(parts)}</div>'


# ---------- 地图 ----------

def render_map(geo, mp):
    cap = mp.get("caption") or "定位：" + "、".join([geo.countries[c]["name"] for c in mp["countries"]] +
                                                [p["name"] for p in mp["points"]])
    return f'<figure class="fig fig-map">{map_svg(geo, mp)}<figcaption>{esc(cap)}</figcaption></figure>'


def render_art(geo, st):
    return f'<div class="art ed">{render_map(geo, st["map"])}</div>' if "map" in st else ""


# ---------- 条目 ----------

def story_id(key):
    return f"s-{key}"


def kicker(it, st):
    no = "探索位" if it["kind"] == "explore" else str(it["number"])
    f = st.get("follows")
    fol = (f'<a class="follows" href="{f["date"]}.html#{story_id(f["key"])}">续 {cn_date(f["date"], False)}</a>'
           if f else "")
    return f'<p class="kicker"><span class="no">{no}</span><span class="domain">{esc(it["domain"])}</span>{fol}</p>'


def render_story(geo, it, st, tag="h2"):
    role = st["role"]
    key = item_key(it)
    head = kicker(it, st) + f'<{tag} class="hl">{inline(it["title"])}</{tag}>'
    issue = st.get("issue")
    dctx = date_ctx(issue) if issue else None
    dek = f'<p class="dek ed">{inline(st["dek"], numbers=True, ctx=dctx)}</p>' if st.get("dek") else ""
    if role == "brief":
        teaser = dek or f'<p class="dek ed">{inline(first_paragraph(it), numbers=True, ctx=dctx)}</p>'
        return (f'<article class="story s-brief" id="{story_id(key)}">{head}{teaser}'
                f'<details class="more"><summary class="ed">展开全文</summary>{render_body(it, issue=issue)}</details></article>')
    quote = st.get("quote") if role in ("lead", "feature") else None
    if role == "explore":
        # 探索带：标题与导语在左，地图在右
        return (f'<article class="story s-explore" id="{story_id(key)}"><div class="x-head"><div>{head}{dek}</div>'
                f'{render_art(geo, st)}</div>{mobile_fold(render_body(it, issue=issue))}</article>')
    art = render_art(geo, st)
    body = render_body(it, quote, issue)
    if role == "feature":
        body = mobile_fold(body)
    return f'<article class="story s-{role}" id="{story_id(key)}">{head}{dek}{art}{body}</article>'


def mobile_fold(body):
    """窄屏上折叠的正文：默认展开（无脚本时内容完整），页面脚本在窄屏上收起；宽屏隐藏开关。"""
    return f'<details class="more m-fold" open><summary class="ed">展开全文</summary>{body}</details>'


def first_paragraph(it):
    for b in it["sections"][0]["blocks"]:
        if b["type"] in ("p", "key"):
            return b["text"]
    return next(block_texts(it["sections"][0]["blocks"]), "")


# ---------- 一天的版面 ----------

def cutoff(day):
    if day.get("meta", {}).get("cutoff"):
        return "原刊截稿 " + day["meta"]["cutoff"]
    intro = "".join(b.get("text", "") for b in day["intro"])
    m = re.search(r"截至北京时间约?(\d{1,2}:\d{2})", intro)
    return f"截至北京时间 {m.group(1)}" if m else ""


def render_day(geo, day, layout, nav, source_name):
    items = {item_key(i): i for i in day["items"]}
    S = layout["stories"]
    lead = render_story(geo, items[layout["lead"]], S[layout["lead"]], "h2")
    feats = layout["features"]
    rail = render_story(geo, items[feats[0]], S[feats[0]], "h3") if feats else ""
    front_cls = "front" + ("" if feats else " solo")
    front = f'<section class="{front_cls}">{lead}' + (f'<div class="rail">{rail}</div>' if rail else "") + "</section>"
    wide = "".join(f'<section class="second">{render_story(geo, items[k], S[k], "h3")}</section>' for k in feats[1:])
    briefs = ""
    if layout["briefs"]:
        cards = "".join(render_story(geo, items[k], S[k], "h3") for k in layout["briefs"])
        briefs = (f'<section class="briefs"><h3 class="band-title">简讯</h3>'
                  f'<div class="brief-grid n{len(layout["briefs"])}">{cards}</div></section>')
    explore = ""
    if layout["explore"]:
        explore = f'<section class="explore-band"><div class="wrap">{render_story(geo, items["x"], S["x"], "h3")}</div></section>'

    order = [layout["lead"]] + feats + layout["briefs"] + ([layout["explore"]] if layout["explore"] else [])
    toc = "".join(
        f'<a href="#{story_id(k)}" class="t-{S[k]["role"]}"><span class="no">{"探" if k == "x" else k}</span>'
        f'<span class="td">{esc(items[k]["domain"])}</span><span class="tt">{inline(items[k]["title"])}</span></a>'
        for k in order)
    n_main = sum(1 for i in day["items"] if i["kind"] == "main")
    count = f"{n_main} 条主新闻" + (" · 1 条探索" if layout["explore"] else "")
    prev_a = f'<a href="{nav["prev"]}.html">‹ {cn_date(nav["prev"], False)}</a>' if nav.get("prev") else "<span></span>"
    next_a = f'<a href="{nav["next"]}.html">{cn_date(nav["next"], False)} ›</a>' if nav.get("next") else "<span></span>"
    title = f"{NAMEPLATE}｜{cn_date(day['date'])}"
    fill = {
        "{{TITLE}}": esc(title),
        "{{NAMEPLATE}}": NAMEPLATE,
        "{{PREV}}": prev_a,
        "{{NEXT}}": next_a,
        "{{DATE}}": f"{cn_date(day['date'])} {weekday(day['date'])}",
        "{{CUTOFF}}": cutoff(day),
        "{{COUNT}}": count,
        "{{TOC}}": toc,
        "{{FRONT}}": front + wide,
        "{{BRIEFS}}": briefs,
        "{{EXPLORE}}": explore,
        "{{INTRO}}": render_blocks(day["intro"]),
        "{{SOURCE}}": esc(source_name),
    }
    return fill_template("day.html", fill)


def render_index(entries):
    rows = []
    for e in sorted(entries, key=lambda e: e["date"], reverse=True):
        rows.append(f'<div class="ix"><a class="ix-main" href="{e["date"]}.html"><span class="ix-d">{cn_date(e["date"], False)}'
                    f'<small>{weekday(e["date"])}</small></span><span class="ix-t"><span class="ix-dom">{esc(e["lead_domain"])}</span>'
                    f'{inline(e["lead_title"])}</span><span class="ix-n">{e["count"]}</span></a>'
                    f'<a class="ix-flip" href="flip/{e["date"]}.html">翻页版</a></div>')
    return fill_template("index.html", {"{{TITLE}}": NAMEPLATE, "{{NAMEPLATE}}": NAMEPLATE, "{{ROWS}}": "".join(rows)})


def strip_shell(doc):
    """去掉 doctype、html/head/body 标签和 charset/viewport meta，留下 title、style 与正文。"""
    doc = re.sub(r"(?is)^\s*<!doctype html>\s*<html[^>]*>\s*<head>\s*", "", doc)
    doc = re.sub(r'(?i)<meta charset="utf-8">\s*<meta name="viewport"[^>]*>\s*', "", doc)
    doc = re.sub(r"(?is)</head>\s*<body>\s*", "", doc)
    return re.sub(r"(?is)\s*</body>\s*</html>\s*$", "\n", doc)


def fill_template(name, fill, extra_css=None):
    css = (HERE / "style.css").read_text(encoding="utf-8")
    if extra_css:
        css += "\n" + (HERE / extra_css).read_text(encoding="utf-8")
    page = (HERE / name).read_text(encoding="utf-8").replace("{{STYLE}}", css)
    for k, v in fill.items():
        page = page.replace(k, v)
    return page


# ---------- 核对：从 HTML 反读每条正文，与底稿逐字比较 ----------

VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "source"}


class ArticleText(HTMLParser):
    """收集每个 <article id> 的标题（.hl）和正文（.body），跳过编辑层（.ed）、小节标签（h4）和图。"""

    def __init__(self):
        super().__init__()
        self.articles = {}
        self.stack = []  # (tag, mode, skip)
        self.cur = None

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        mode, skip = (self.stack[-1][1], self.stack[-1][2]) if self.stack else (None, False)
        if tag == "article" and a.get("id"):
            self.cur = a["id"]
            self.articles[self.cur] = {"title": "", "body": ""}
        if self.cur:
            if "hl" in cls:
                mode = "title"
            elif "body" in cls:
                mode = "body"
            if "ed" in cls or tag in ("h4", "svg", "figure"):
                skip = True
        self.stack.append((tag, mode, skip))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        while self.stack:
            t, _, _ = self.stack.pop()
            if t == tag:
                break
        if tag == "article":
            self.cur = None

    def handle_data(self, data):
        if self.cur and self.stack:
            _, mode, skip = self.stack[-1]
            if mode and not skip:
                self.articles[self.cur][mode] += data


def verify(day, page):
    p = ArticleText()
    p.feed(page)
    problems = []
    for it in day["items"]:
        aid = story_id(item_key(it))
        got = p.articles.get(aid)
        if got is None:
            problems.append(f"{day['date']} {aid}: HTML 中缺少这一条")
            continue
        if re.sub(r"\s+", "", got["title"]) != plain(it["title"]):
            problems.append(f"{day['date']} {aid}: 标题与底稿不一致")
        want, have = body_plain(it), re.sub(r"\s+", "", got["body"])
        if want != have:
            k = next((i for i, (a, b) in enumerate(zip(want, have)) if a != b), min(len(want), len(have)))
            problems.append(f"{day['date']} {aid}: 正文与底稿不一致，第 {k} 字附近：底稿“{want[k:k + 12]}” / HTML“{have[k:k + 12]}”")
    if len(p.articles) != len(day["items"]):
        problems.append(f"{day['date']}: HTML 有 {len(p.articles)} 条，底稿有 {len(day['items'])} 条")
    if "**" in page or "{{" in page:
        problems.append(f"{day['date']}: HTML 中残留未处理的标记")
    return problems
