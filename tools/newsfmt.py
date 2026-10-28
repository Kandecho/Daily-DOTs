"""每日新闻简报排版：底稿（内容）+ 版面单（编辑决策）→ 一天一页的报纸式 HTML。

模型负责两件事：按 排版约定.md 写底稿，按 版面单说明 写每天的版面单。
解析、回查、排版、地图、图表和成品核对全部由程序确定性完成；同样的输入总是得到同样的输出。

用法：
  python tools/newsfmt.py check <底稿.md>... [--sheets 版面]
  python tools/newsfmt.py build <底稿.md>... [--sheets 版面] [-o dist] [--strict]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import core
import flip
import page
import sheet
from geo import Geo

TOOL_VERSION = "2"


def sha(data):
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(description="每日新闻简报排版")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "build"):
        p = sub.add_parser(name)
        p.add_argument("drafts", nargs="+")
        p.add_argument("--sheets", default=None, help="版面单目录，默认：底稿所在目录下的 版面/")
        if name == "build":
            p.add_argument("-o", "--out-dir", default=None, help="默认：底稿所在目录下的 dist/")
            p.add_argument("--strict", action="store_true", help="有警告也视为失败")
    args = ap.parse_args(argv)

    base = Path(args.drafts[0]).parent
    sheets_dir = Path(args.sheets) if args.sheets else base / "版面"
    out = Path(getattr(args, "out_dir", None) or base / "dist")
    data_dir = out / "data"

    # 1. 底稿
    reports, days, sources = [], [], {}
    for d in args.drafts:
        doc, rep, text = core.parse_file(d)
        reports.append(rep)
        for day in doc["days"]:
            if day["date"] in sources:
                rep.error(day["line"], f"{day['date']} 已在 {sources[day['date']][0]} 中出现")
                continue
            sources[day["date"]] = (Path(d).name, text)
            days.append(day)
    days.sort(key=lambda d: d["date"])

    # 已有成品也算作可接续的日期
    known = {d["date"]: {core.item_key(i) for i in d["items"]} for d in days}
    existing = {}
    if data_dir.exists():
        for f in data_dir.glob("*.json"):
            e = json.loads(f.read_text(encoding="utf-8"))
            existing[e["date"]] = e
            known.setdefault(e["date"], set(e["keys"]))

    # 2. 版面单
    geo = Geo()
    layouts, sheet_texts = {}, {}
    if not any(r.errors for r in reports):
        for day in days:
            sp = sheets_dir / f"{day['date']}.toml"
            layout, rep = sheet.load(sp if sp.exists() else None, day, geo, known)
            reports.append(rep)
            layouts[day["date"]] = layout
            sheet_texts[day["date"]] = sp.read_text(encoding="utf-8") if sp.exists() else ""

    n_err = sum(len(r.errors) for r in reports)
    n_warn = sum(len(r.warnings) for r in reports)
    for r in reports:
        for line in r.lines():
            print(line, file=sys.stderr)
    if n_err or (getattr(args, "strict", False) and n_warn):
        print(f"失败：{n_err} 个错误，{n_warn} 个警告。修改底稿或版面单后重跑。", file=sys.stderr)
        return 1
    if args.cmd == "check":
        print(f"通过：{len(days)} 天，{n_warn} 个警告。")
        return 0

    # 3. 渲染与核对
    dates = sorted(set(known))
    counts = {d: len(k) for d, k in known.items()}
    pages, flips, problems = {}, {}, []
    for day in days:
        i = dates.index(day["date"])
        nav = {"prev": dates[i - 1] if i > 0 else None, "next": dates[i + 1] if i + 1 < len(dates) else None,
               "counts": counts, "standalone": bool(day.get("meta"))}
        if nav["standalone"]:
            nav.update(prev=None, next=None)
        html_page = page.render_day(geo, day, layouts[day["date"]], nav, sources[day["date"]][0])
        problems += page.verify(day, html_page)
        pages[day["date"]] = html_page
        flip_page = flip.render_flip_day(geo, day, layouts[day["date"]], nav, sources[day["date"]][0])
        problems += [f"翻页版 {m}" for m in page.verify(day, flip_page)]
        flips[day["date"]] = flip_page
    for msg in problems:
        print(f"核对失败：{msg}", file=sys.stderr)
    if problems:
        return 2

    # 4. 写出
    data_dir.mkdir(parents=True, exist_ok=True)
    (out / "flip").mkdir(exist_ok=True)
    receipt_days = []
    for day in days:
        date, lay = day["date"], layouts[day["date"]]
        items = {core.item_key(i): i for i in day["items"]}
        (out / f"{date}.html").write_text(pages[date], encoding="utf-8", newline="\n")
        (out / "flip" / f"{date}.html").write_text(flips[date], encoding="utf-8", newline="\n")
        n_main = sum(1 for i in day["items"] if i["kind"] == "main")
        entry = {
            "date": date,
            "keys": sorted(items),
            "lead_title": items[lay["lead"]]["title"],
            "lead_domain": items[lay["lead"]]["domain"],
            "count": f"{n_main}" + ("+1" if lay["explore"] else ""),
            "layout": {k: lay[k] for k in ("lead", "features", "briefs", "explore")},
            "day": day,
        }
        existing[date] = entry
        (data_dir / f"{date}.json").write_text(json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        receipt_days.append({
            "date": date,
            "draft": {"file": sources[date][0], "sha256": sha(sources[date][1])},
            "sheet": {"file": f"{date}.toml", "sha256": sha(sheet_texts[date])} if sheet_texts[date] else None,
            "html": {"file": f"{date}.html", "sha256": sha(pages[date])},
            "flip": {"file": f"flip/{date}.html", "sha256": sha(flips[date])},
            "layout": entry["layout"],
        })
    index_html = page.render_index(existing.values())
    (out / "index.html").write_text(index_html, encoding="utf-8", newline="\n")
    # 发布成 claude.ai artifact 时主页会被套上文档外壳，所以另存一份不带 doctype/head/body 的往期页
    (out / "artifact-index.html").write_text(page.strip_shell(index_html), encoding="utf-8", newline="\n")
    receipt = {
        "tool": f"newsfmt v{TOOL_VERSION}",
        "gates": {"draft": "pass", "sheet_trace": "pass", "render": "pass", "verify_text": "pass"},
        "days": receipt_days,
        "warnings": [w for r in reports for w in ({"file": r.path, **x} for x in r.warnings)],
    }
    (out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"通过：{len(days)} 天 → {out}（{n_warn} 个警告）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
