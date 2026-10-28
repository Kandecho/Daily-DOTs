"""版面单：一天一张 TOML，记录编辑决策（主次、地图、导语、引语、接续）。

版面单里能写的每一项都要回查到底稿：导语和引语是正文原句，
地名在正文中出现且坐标落在所标国家附近。查不到就报错，不让模型凭空补内容。
"""

import re
import tomllib
from pathlib import Path

from core import Report, corpus, item_key, plain

ROLES = ("lead", "feature", "brief", "explore")
MAX_DEK = 90
MAX_QUOTE = 90
RE_FOLLOWS = re.compile(r"^(\d{4}-\d{2}-\d{2}):(\d+|x)$")


def default_sheet(day):
    mains = [i for i in day["items"] if i["kind"] == "main"]
    return {"date": day["date"], "lead": mains[0]["number"], "features": [i["number"] for i in mains[1:3]], "story": {}}


def load(path, day, geo, known_days):
    """返回 (排好的版面, Report)。known_days: {date: {key,...}}，用于检查接续目标。"""
    rep = Report(path or f"(默认版面 {day['date']})")
    if path is None:
        sheet = default_sheet(day)
        rep.warn("-", "没有版面单，使用默认版面：第 1 条做头条，第 2、3 条做次条，不配地图")
    else:
        try:
            sheet = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            rep.error("-", f"TOML 语法错误：{e}")
            return None, rep

    items = {item_key(i): i for i in day["items"]}
    mains = [i for i in day["items"] if i["kind"] == "main"]

    if sheet.get("date") != day["date"]:
        rep.error("date", f"版面单日期 {sheet.get('date')!r} 与底稿 {day['date']} 不一致")
    unknown = set(sheet) - {"date", "lead", "features", "story"}
    for k in sorted(unknown):
        rep.error(k, "未知字段")

    lead = sheet.get("lead")
    if not isinstance(lead, int) or str(lead) not in items:
        rep.error("lead", f"头条必须是某条主新闻的编号，实际为 {lead!r}")
        return None, rep
    features = sheet.get("features", [])
    if not isinstance(features, list) or len(features) > 2:
        rep.error("features", "次条最多 2 条，写成编号列表")
        features = []
    for n in features:
        if not isinstance(n, int) or str(n) not in items:
            rep.error("features", f"次条编号 {n!r} 不存在")
        elif n == lead:
            rep.error("features", f"第 {n} 条已经是头条")
    if len(set(features)) != len(features):
        rep.error("features", "次条编号重复")

    role = {}
    for it in mains:
        n = it["number"]
        role[str(n)] = "lead" if n == lead else "feature" if n in features else "brief"
    if "x" in items:
        role["x"] = "explore"

    stories = sheet.get("story", {})
    out = {}
    for key, it in items.items():
        spec = stories.get(key, {})
        out[key] = check_story(f"story.{key}", spec, it, role[key], geo, known_days, rep)
        out[key]["issue"] = day["date"]  # 简报日期：正文里的日期按它判断是不是“当天”
    for key in stories:
        if key not in items:
            rep.error(f"story.{key}", "底稿里没有这一条")

    layout = {
        "lead": str(lead),
        "features": [str(n) for n in features if str(n) in items and n != lead],
        "briefs": [str(i["number"]) for i in mains if role[str(i["number"])] == "brief"],
        "explore": "x" if "x" in items else None,
        "stories": out,
    }
    return layout, rep


def check_story(loc, spec, item, role, geo, known_days, rep):
    text = corpus(item)
    allowed = {"dek", "quote", "follows", "map"}
    for k in sorted(set(spec) - allowed):
        rep.error(f"{loc}.{k}", "未知字段")
    st = {"role": role}

    def verbatim(field, limit):
        v = spec.get(field)
        if v is None:
            return
        if not isinstance(v, str) or not v.strip():
            rep.error(f"{loc}.{field}", "必须是非空字符串")
            return
        if len(v) > limit:
            rep.error(f"{loc}.{field}", f"超过 {limit} 字")
        if plain(v) not in text:
            rep.error(f"{loc}.{field}", f"不是这一条正文里的原句：{v[:24]}")
            return
        st[field] = v

    verbatim("dek", MAX_DEK)
    verbatim("quote", MAX_QUOTE)
    if "quote" in st and role not in ("lead", "feature"):
        rep.warn(f"{loc}.quote", "只有头条和次条显示引语，这里会被忽略")

    if "follows" in spec:
        f = spec["follows"]
        m = RE_FOLLOWS.match(f) if isinstance(f, str) else None
        if not m:
            rep.error(f"{loc}.follows", "写成 \"2026-10-21:2\" 或 \"2026-10-21:x\"")
        elif m.group(1) not in known_days or m.group(2) not in known_days[m.group(1)]:
            rep.warn(f"{loc}.follows", f"找不到 {f}，接续链接不显示")
        else:
            st["follows"] = {"date": m.group(1), "key": m.group(2)}

    if "map" in spec:
        mp = check_map(f"{loc}.map", spec["map"], text, geo, rep)
        if mp:
            st["map"] = mp
    # 报纸版的简讯不显示地图，翻页版每条都显示；是否显示由版式决定，这里不丢弃
    return st


def check_map(loc, spec, text, geo, rep):
    ok = True
    codes = spec.get("countries", [])
    for c in codes:
        if c not in geo.countries:
            rep.error(f"{loc}.countries", f"未知国家代码 {c}（用 Natural Earth 的 ADM0_A3，如 UKR、CHN）")
            ok = False
    view = spec.get("view")
    if view is not None:
        if not (isinstance(view, list) and len(view) == 4 and -180 <= view[0] < view[2] <= 180
                and -85 <= view[1] < view[3] <= 85):
            rep.error(f"{loc}.view", "写成 [西经度, 南纬度, 东经度, 北纬度]")
            ok = False
    if not codes and view is None:
        rep.error(loc, "至少给出 countries 或 view")
        ok = False
    pts = spec.get("points", [])
    for i, p in enumerate(pts):
        pl = f"{loc}.points[{i}]"
        name, lon, lat = p.get("name"), p.get("lon"), p.get("lat")
        if not isinstance(name, str) or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            rep.error(pl, "需要 name、lon、lat")
            ok = False
            continue
        if plain(name) not in text:
            rep.error(pl, f"地名“{name}”没有出现在这一条正文里")
            ok = False
        if p.get("sea"):
            pass
        elif codes and ok and not any(geo.near(c, lon, lat) for c in codes):
            rep.error(pl, f"“{name}”({lon}, {lat}) 不在 {'/'.join(codes)} 境内或附近；海上地点加 sea = true")
            ok = False
        if view is not None and not (view[0] <= lon <= view[2] and view[1] <= lat <= view[3]):
            rep.error(pl, f"“{name}”不在 view 范围内")
            ok = False
    return {"countries": codes, "view": view, "points": pts, "caption": spec.get("caption")} if ok else None
