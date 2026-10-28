"""Bridge the already-verified Markdown + JSON metadata to Claude's data model.

No rewriting or fact review. The original core parser remains available.
"""
import datetime as dt
import json
import re

from core import SUBTITLE, Report, check_inline, parse_blocks, validate

STORY = re.compile(r'^<!-- story (\{[^\n]+\}) -->\n(.*?)^<!-- endstory -->', re.M | re.S)
BLOCK = re.compile(r'^<!-- block (\S+) (\S+) -->\s*$', re.M)
LABEL_KEYS = {"今天发生了什么": "what", "为什么今天值得留下": "why",
              "支点在哪里": "pivot", "当前的不确定性": "uncertain",
              "仍待确认": "uncertain", "仍待观察": "uncertain"}


def parse(text, path):
    rep = Report(path)
    doc = {"title": None, "note": [], "days": []}
    try:
        _, raw_meta, body = text.split("---\n", 2)
        meta = json.loads(raw_meta)
        date = dt.date.fromisoformat(meta["issue_date"]).isoformat()
        if meta.get("schema_version") != 1:
            raise ValueError("只支持原稿 schema_version=1")
        if meta["title"] != SUBTITLE:
            raise ValueError(f"title 必须是“{SUBTITLE}”")
        layout = meta["layout"]
        if layout.get("schema_version") != 1 or layout.get("template") != "claude-flip-v1":
            raise ValueError("layout 需要 schema_version=1、template=claude-flip-v1")
        order, stories = layout["order"], layout["stories"]
        if not isinstance(order, list) or not all(isinstance(sid, str) for sid in order):
            raise ValueError("layout.order 必须是条目 ID 列表")
        if not isinstance(stories, list) or [s["story_id"] for s in stories] != order:
            raise ValueError("layout.stories 必须完整对应 layout.order，不能缺失或重复")
        if layout.get("shared_map", "tools/data/ne_110m_countries.geojson") != "tools/data/ne_110m_countries.geojson":
            raise ValueError("shared_map 只支持随程序附带的 Natural Earth 底图")
        cutoff = meta.get("cutoff", "")
        if cutoff and (not isinstance(cutoff, str) or not cutoff.startswith(date)):
            raise ValueError("cutoff 必须以本期 issue_date 开头")
        for story in stories:
            if not isinstance(story.get("components", []), list):
                raise ValueError("components 必须是列表")
            for component in story.get("components", []):
                if not isinstance(component, dict) or component.get("type") != "locator_map":
                    raise ValueError("不支持的排版组件；当前只接受 locator_map 国家高亮定位图")
                highlights = component["highlights"]
                if not isinstance(highlights, list) or not highlights or not all(
                        isinstance(h, dict) and isinstance(h.get("country_id"), str) for h in highlights):
                    raise ValueError("highlights 必须是包含 country_id 的非空列表")
                view = component["viewport"]
                if not isinstance(view, list) or len(view) != 4 or not all(
                        isinstance(v, (int, float)) and not isinstance(v, bool) for v in view):
                    raise ValueError("viewport 必须是四个数字组成的列表")
                if not isinstance(component["caption"], str):
                    raise ValueError("caption 必须是字符串")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        rep.error(1, f"原稿元数据无效：{exc}")
        return doc, rep
    day = {"date": date, "subtitle": meta["title"], "line": 1, "items": [],
           "intro": [{"type": "p", "text": meta[k]} for k in ("intro", "reading_note", "colophon") if meta.get(k)],
           "meta": meta}
    doc.update(title=meta["title"], days=[day])
    matches = list(STORY.finditer(body))
    # All non-story prose must be the known title/intro/issue notes, not silently lost.
    residual = STORY.sub("", body)
    expected = f'# {meta["title"]} {date}\n{meta.get("intro", "")}'
    notes = "\n".join(meta[k] for k in ("reading_note", "colophon") if meta.get(k))
    if notes:
        expected += f"\n## 本期说明\n{notes}"
    squash = lambda s: re.sub(r"\s+", "", s)
    if squash(residual) != squash(expected):
        rep.error(1, "条目外文字与元数据不一致；拒绝忽略未知文字")
    ids = []
    for match in matches:
        no = text[:text.index(body) + match.start()].count("\n") + 1
        try:
            info = json.loads(match[1])
            sid, number, category = info["id"], int(info["number"]), info["category"]
            if not isinstance(sid, str) or not isinstance(category, str):
                raise ValueError("id 与 category 必须是字符串")
            title, content = match[2].strip().split("\n", 1)
        except (ValueError, KeyError, TypeError) as exc:
            rep.error(no, f"条目元数据无效：{exc}")
            continue
        if not title.startswith("## "):
            rep.error(no, "条目缺少 ## 标题")
            continue
        ids.append(sid)
        item = {"kind": "explore" if info.get("exploration") else "main", "line": no,
                "number": number, "domain": category, "title": title[3:], "sections": []}
        check_inline(item["title"], no, rep)
        content = re.sub(r'^\s*> 摘要：[^\n]*\n', "", content, count=1)
        if content.count("<!-- sources -->") != 1:
            rep.error(no, "每条必须有一个来源区")
            continue
        content, sources = content.split("<!-- sources -->")
        parts = BLOCK.split(content)
        if parts[0].strip():
            rep.error(no, "条目中出现未标记文字")
        current = None
        for block_id, kind, value in zip(parts[1::3], parts[2::3], parts[3::3]):
            value = value.strip()
            if kind == "heading":
                if not value.startswith("### ") or "\n" in value:
                    rep.error(no, f"{block_id}: 小节标题格式错误")
                    continue
                label = value[4:]
                check_inline(label, no, rep)
                current = {"key": LABEL_KEYS.get(label, "note"), "label": label, "raw_label": label,
                           "line": no, "blocks": []}
                item["sections"].append(current)
            elif kind == "paragraph" and current is not None:
                current["blocks"].extend(parse_blocks(list(enumerate(value.splitlines(), start=no)), rep))
            else:
                rep.error(no, f"{block_id}: 不支持的正文块或缺少小节标题：{kind}")
        item["sections"].append({"key": "sources", "label": "来源", "raw_label": "来源", "line": no,
                                 "blocks": parse_blocks(list(enumerate(sources.strip().splitlines(), start=no)), rep)})
        day["items"].append(item)
    order = meta.get("layout", {}).get("order")
    if len(ids) != len(set(ids)) or (order is not None and order != ids):
        rep.error(1, "条目 ID 重复或与排版顺序不一致")
    validate(doc, rep)
    return doc, rep
