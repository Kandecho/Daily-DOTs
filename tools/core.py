"""底稿解析与校验：Markdown 底稿 → 结构化数据。只读内容，不涉及版面。"""

import datetime as dt
import re
from pathlib import Path

MAX_MAIN = 5
MAX_EXPLORE = 1
WEEKDAYS = "一二三四五六日"

RE_DAY = re.compile(r"^## (\d{4})年(\d{1,2})月(\d{1,2})日｜(.+)$")
RE_MAIN = re.compile(r"^### (\d+)\. (.+?)｜(.+)$")
RE_EXPLORE = re.compile(r"^### 探索位｜(.+?)[：:](.+)$")
RE_BOLD_LINE = re.compile(r"^\*\*([^*]+)\*\*$")
RE_TABLE_SEP = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+$")
RE_OL = re.compile(r"^(\d+)\. (.+)$")
RE_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

# 小节标签：底稿里的措辞会漂移（“今天留下”“今天结束时留下”“在今天结束时留下”），统一成规范名。
SECTIONS = {
    "what": ("今天发生了什么", re.compile(r"^今天发生了什么$")),
    "why": ("为什么值得今天留下", re.compile(r"^为什么值得.*留下$")),
    "pivot": ("支点在哪里，为什么可能值得以后回看", re.compile(r"^支点在哪里")),
    "uncertain": ("当前有哪些重要不确定性", re.compile(r"^当前有哪些重要不确定性")),
}
REQUIRED = {"main": ["what", "why"], "explore": ["what", "pivot", "uncertain"]}


class Report:
    """收集错误和警告。loc 是行号或键路径。"""

    def __init__(self, path):
        self.path = path
        self.errors = []
        self.warnings = []

    def error(self, loc, msg):
        self.errors.append({"at": loc, "message": msg})

    def warn(self, loc, msg):
        self.warnings.append({"at": loc, "message": msg})

    def lines(self):
        for kind, items in (("错误", self.errors), ("警告", self.warnings)):
            for d in items:
                yield f"{self.path}:{d['at']}: {kind}: {d['message']}"


# ---------- 文本工具 ----------

def plain(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = RE_LINK.sub(r"\1", s)
    return re.sub(r"\s+", "", s)


def block_texts(blocks):
    for b in blocks:
        if b["type"] in ("p", "key"):
            yield b["text"]
        elif b["type"] in ("ul", "ol"):
            yield from b["items"]
        elif b["type"] == "table":
            yield from b["head"]
            for r in b["rows"]:
                yield from r


def body_plain(item):
    """一条新闻的正文（不含标题和小节标签），去掉标记与空白。"""
    return "".join(plain(t) for s in item["sections"] for t in block_texts(s["blocks"]))


def corpus(item):
    """用于回查版面单的文本：标题 + 正文。"""
    return plain(item["title"]) + body_plain(item)


def cn_date(iso, with_year=True):
    d = dt.date.fromisoformat(iso)
    s = f"{d.month}月{d.day}日"
    return (f"{d.year}年" + s) if with_year else s


def weekday(iso):
    return "星期" + WEEKDAYS[dt.date.fromisoformat(iso).weekday()]


def item_key(it):
    return "x" if it["kind"] == "explore" else str(it["number"])


# ---------- 解析 ----------

def check_inline(text, loc, rep):
    if text.count("**") % 2:
        rep.error(loc, "粗体标记 ** 不成对")
    if "`" in text or re.search(r"<[a-zA-Z/!]", text):
        rep.error(loc, "正文不支持行内代码或 HTML 标签")


def parse_blocks(lines, rep):
    """lines: [(行号, 文本)]。只接受段落、要点句、无序/有序列表、表格。"""
    blocks = []
    i = 0
    while i < len(lines):
        no, text = lines[i]
        if not text.strip():
            i += 1
            continue
        if text.startswith((" ", "\t")):
            rep.error(no, "不支持缩进行（嵌套列表或代码块）")
            i += 1
            continue
        if text.strip() == "---":
            rep.warn(no, "条目内部的分隔线 --- 已忽略")
            i += 1
            continue
        if text.startswith((">", "```", "#")):
            rep.error(no, f"条目正文中不支持这种写法：{text[:12]}")
            i += 1
            continue
        if text.startswith("|"):
            rows = []
            while i < len(lines) and lines[i][1].startswith("|"):
                rows.append(lines[i])
                i += 1
            blocks.append(parse_table(rows, rep))
            continue
        if text.startswith("- "):
            items = []
            while i < len(lines) and lines[i][1].startswith("- "):
                check_inline(lines[i][1][2:], lines[i][0], rep)
                items.append(lines[i][1][2:].strip())
                i += 1
            blocks.append({"type": "ul", "items": items})
            continue
        if RE_OL.match(text):
            items = []
            while i < len(lines) and RE_OL.match(lines[i][1]):
                check_inline(lines[i][1], lines[i][0], rep)
                items.append(RE_OL.match(lines[i][1]).group(2).strip())
                i += 1
            blocks.append({"type": "ol", "items": items})
            continue
        # 段落：连续非空行合并（中文不加空格）
        para = []
        while i < len(lines) and lines[i][1].strip() and not lines[i][1].startswith(("|", "- ", " ", "\t")) \
                and not RE_OL.match(lines[i][1]):
            para.append(lines[i][1].strip())
            i += 1
        joined = "".join(para)
        check_inline(joined, no, rep)
        m = RE_BOLD_LINE.match(joined)
        blocks.append({"type": "key" if m else "p", "text": m.group(1) if m else joined})
    return blocks


def parse_table(rows, rep):
    no = rows[0][0]
    if len(rows) < 2 or not RE_TABLE_SEP.match(rows[1][1].replace(" ", "")):
        rep.error(no, "表格第二行必须是分隔行，例如 | --- | ---: |")
        return {"type": "table", "head": [], "align": [], "rows": []}

    def cells(t):
        return [c.strip() for c in t.strip().strip("|").split("|")]

    head = cells(rows[0][1])
    align = ["right" if c.endswith(":") and not c.startswith(":") else
             "center" if c.startswith(":") and c.endswith(":") else "left"
             for c in cells(rows[1][1])]
    body = []
    for rno, rtext in rows[2:]:
        row = cells(rtext)
        if len(row) != len(head):
            rep.error(rno, f"表格这一行有 {len(row)} 格，表头有 {len(head)} 格")
        for c in row:
            check_inline(c, rno, rep)
        body.append(row)
    return {"type": "table", "head": head, "align": align, "rows": body}


def parse_item(kind, header, body, rep):
    no, head = header
    if kind == "main":
        m = RE_MAIN.match(head)
        item = {"kind": kind, "line": no, "number": int(m.group(1)), "domain": m.group(2).strip(),
                "title": m.group(3).strip(), "sections": []}
    else:
        m = RE_EXPLORE.match(head)
        item = {"kind": kind, "line": no, "domain": m.group(1).strip(), "title": m.group(2).strip(), "sections": []}
    check_inline(item["title"], no, rep)

    current = None
    buf = []

    def flush():
        if current is not None:
            current["blocks"] = parse_blocks(buf, rep)
            if not current["blocks"]:
                rep.error(current["line"], f"小节“{current['label']}”没有内容")

    for ln in body:
        m = RE_BOLD_LINE.match(ln[1].strip())
        key = next((k for k, (_, rx) in SECTIONS.items() if rx.match(m.group(1))), None) if m else None
        if key:
            flush()
            current = {"key": key, "label": SECTIONS[key][0], "raw_label": m.group(1), "line": ln[0]}
            item["sections"].append(current)
            buf = []
        elif current is None:
            if ln[1].strip():
                rep.error(ln[0], "条目标题之后必须先出现小节标签，例如 **今天发生了什么**")
        else:
            buf.append(ln)
    flush()

    keys = [s["key"] for s in item["sections"]]
    if keys != REQUIRED[kind]:
        want = " → ".join(SECTIONS[k][0] for k in REQUIRED[kind])
        got = " → ".join(SECTIONS[k][0] for k in keys) or "无"
        rep.error(no, f"小节顺序应为：{want}；实际为：{got}")
    return item


def parse(text, path="<input>"):
    rep = Report(path)
    lines = list(enumerate(text.splitlines(), start=1))
    doc = {"title": None, "note": [], "days": []}
    day = None
    header, body, kind = None, [], None
    intro = []

    def close_item():
        nonlocal header, body
        if header:
            day["items"].append(parse_item(kind, header, body, rep))
        header, body = None, []

    def close_day():
        nonlocal intro
        if day is not None:
            day["intro"] = parse_blocks(intro, rep)
        intro = []

    for no, t in lines:
        if t.startswith("# ") and not doc["days"] and day is None:
            doc["title"] = t[2:].strip()
            continue
        if t.startswith("## "):
            close_item()
            close_day()
            m = RE_DAY.match(t)
            day = None
            if not m:
                rep.error(no, "日期标题应为：## 2026年10月19日｜全球晚间新闻简报")
                continue
            y, mo, d, sub = m.groups()
            try:
                date = dt.date(int(y), int(mo), int(d))
            except ValueError:
                rep.error(no, "日期不存在")
                continue
            day = {"date": date.isoformat(), "subtitle": sub.strip(), "line": no, "intro": [], "items": []}
            doc["days"].append(day)
            continue
        if t.startswith("### "):
            close_item()
            if day is None:
                rep.error(no, "条目必须位于某个日期标题之下")
                continue
            if RE_MAIN.match(t):
                kind, header = "main", (no, t)
            elif RE_EXPLORE.match(t):
                kind, header = "explore", (no, t)
            else:
                rep.error(no, "条目标题应为：### 1. 领域｜标题  或  ### 探索位｜领域：标题")
            continue
        if header:
            # 日与日之间的 --- 是分隔线，不属于上一条的正文
            if t.strip() == "---" and next((x for _, x in lines[no:] if x.strip()), "## ").startswith("## "):
                continue
            body.append((no, t))
            continue
        if day is None:
            if t.startswith(">"):
                doc["note"].append(t.lstrip("> ").strip())
            elif t.strip() and t.strip() != "---":
                rep.error(no, "第一个日期标题之前只允许 # 标题 和 > 说明")
        elif t.strip() and t.strip() != "---":
            intro.append((no, t))
    close_item()
    close_day()
    validate(doc, rep)
    return doc, rep


def parse_file(path):
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---\n{"):
        from draft_input import parse as parse_verified_draft
        doc, rep = parse_verified_draft(text, str(path))
    else:
        doc, rep = parse(text, str(path))
    return doc, rep, text


# ---------- 校验（对应 每日新闻定时任务.md 的规则） ----------

def validate(doc, rep):
    if not doc["days"]:
        rep.error(1, "没有找到任何日期标题")
    seen = set()
    prev = None
    for day in doc["days"]:
        no = day["line"]
        if day["date"] in seen:
            rep.error(no, f"日期 {day['date']} 重复")
        seen.add(day["date"])
        if prev and day["date"] < prev:
            rep.warn(no, "日期没有按先后排序")
        prev = day["date"]

        mains = [i for i in day["items"] if i["kind"] == "main"]
        explores = [i for i in day["items"] if i["kind"] == "explore"]
        if len(mains) > MAX_MAIN:
            rep.error(no, f"主新闻 {len(mains)} 条，超过上限 {MAX_MAIN}")
        if len(explores) > MAX_EXPLORE:
            rep.error(no, f"探索位 {len(explores)} 条，超过上限 {MAX_EXPLORE}")
        if not mains:
            rep.error(no, "这一天没有主新闻")
        for want, it in enumerate(mains, start=1):
            if it["number"] != want:
                rep.error(it["line"], f"编号应为 {want}，实际为 {it['number']}")
        if explores and day["items"][-1]["kind"] != "explore":
            rep.warn(explores[0]["line"], "探索位应放在主新闻之后")
        domains = {}
        for it in mains:
            if it["domain"] in domains:
                rep.error(it["line"], f"领域“{it['domain']}”与第 {domains[it['domain']]} 条重复")
            domains.setdefault(it["domain"], it["number"])

        # 导语里写的条数要与实际一致
        intro = "".join(b.get("text", "") for b in day["intro"])
        m = re.search(r"保留(\d+)条主新闻", intro)
        if m and int(m.group(1)) != len(mains):
            rep.error(no, f"导语说保留 {m.group(1)} 条主新闻，实际 {len(mains)} 条")
        m = re.search(r"(\d+)条探索", intro)
        if m and int(m.group(1)) != len(explores):
            rep.error(no, f"导语说 {m.group(1)} 条探索新闻，实际 {len(explores)} 条")
        if "不设置探索位" in intro and explores:
            rep.error(no, "导语说不设置探索位，但正文有探索位")
