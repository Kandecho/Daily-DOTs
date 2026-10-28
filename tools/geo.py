"""定位地图：Natural Earth 1:110m 国界（公有领域）→ SVG。投影为等距圆柱，经度按视野中心纬度压缩。"""

import json
import math
from pathlib import Path

DATA = Path(__file__).with_name("data") / "ne_110m_countries.geojson"
W, H = 640, 400
INSET_W, INSET_H = 170, 85
# 地图上的国名与底稿用词一致
NAME_OVERRIDES = {"CHN": "中国", "COD": "刚果（金）", "ARE": "阿联酋", "TWN": "台湾", "USA": "美国", "GBR": "英国"}


class Geo:
    def __init__(self, path=DATA):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.countries = {}
        for f in raw["features"]:
            p = f["properties"]
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            self.countries[p["ADM0_A3"]] = {
                "name": NAME_OVERRIDES.get(p["ADM0_A3"]) or p.get("NAME_ZH") or p["NAME"],
                "label": (p.get("LABEL_X"), p.get("LABEL_Y")),
                "polys": polys,
                "bboxes": [ring_bbox(poly[0]) for poly in polys],
            }

    def main_bbox(self, code):
        """国家主体范围：只计入离最大块不远的部分（排除法属圭亚那这类海外领土）。"""
        c = self.countries[code]
        areas = [abs(ring_area(poly[0])) for poly in c["polys"]]
        big = c["bboxes"][areas.index(max(areas))]
        cx, cy = (big[0] + big[2]) / 2, (big[1] + big[3]) / 2
        keep = [b for b in c["bboxes"] if abs((b[0] + b[2]) / 2 - cx) < 25 and abs((b[1] + b[3]) / 2 - cy) < 20]
        return union(keep)

    def near(self, code, lon, lat, tol=0.8):
        """点在国界内，或离国界顶点不超过 tol 度（1:110m 海岸线很粗，沿海城市可能落在线外）。"""
        c = self.countries[code]
        for poly, bb in zip(c["polys"], c["bboxes"]):
            if not (bb[0] - tol <= lon <= bb[2] + tol and bb[1] - tol <= lat <= bb[3] + tol):
                continue
            if point_in_ring(lon, lat, poly[0]):
                return True
            if any(math.hypot(x - lon, y - lat) <= tol for x, y in poly[0]):
                return True
        return False


def ring_bbox(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def ring_area(ring):
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2


def union(bbs):
    return (min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs))


def point_in_ring(x, y, ring):
    inside = False
    for i in range(len(ring) - 1):
        (x1, y1), (x2, y2) = ring[i][:2], ring[i + 1][:2]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def fit_view(bb, w=W, h=H, pad=0.32, min_span=6.0):
    """把经纬度范围加边距、补到最小跨度，再按画布比例扩展。"""
    x0, y0, x1, y1 = bb
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    sx = max(x1 - x0, min_span) * (1 + 2 * pad)
    sy = max(y1 - y0, min_span * 0.6) * (1 + 2 * pad)
    k = math.cos(math.radians(cy))
    if sx * k / sy < w / h:
        sx = sy * (w / h) / k
    else:
        sy = sx * k / (w / h)
    sy = min(sy, 170)
    return (cx - sx / 2, max(cy - sy / 2, -85), cx + sx / 2, min(cy + sy / 2, 85))


class Proj:
    def __init__(self, view, w, h):
        self.x0, self.y0, self.x1, self.y1 = view
        self.k = math.cos(math.radians((self.y0 + self.y1) / 2))
        self.s = min(w / ((self.x1 - self.x0) * self.k), h / (self.y1 - self.y0))
        self.w, self.h = w, h

    def __call__(self, lon, lat):
        return ((lon - self.x0) * self.k * self.s, (self.y1 - lat) * self.s)


def ring_path(ring, pj, digits=1, min_step=0.6):
    out = []
    last = None
    for lon, lat in (p[:2] for p in ring):
        x, y = pj(lon, lat)
        if last and abs(x - last[0]) < min_step and abs(y - last[1]) < min_step:
            continue
        last = (x, y)
        out.append(f"{x:.{digits}f} {y:.{digits}f}")
    if len(out) < 3:
        return ""
    return "M" + "L".join(out) + "Z"


def country_paths(geo, view, pj, codes_hl, digits=1, min_step=0.6, margin=2):
    x0, y0, x1, y1 = view
    base, hl = [], []
    for code, c in geo.countries.items():
        for poly, bb in zip(c["polys"], c["bboxes"]):
            if bb[2] < x0 - margin or bb[0] > x1 + margin or bb[3] < y0 - margin or bb[1] > y1 + margin:
                continue
            d = "".join(ring_path(r, pj, digits, min_step) for r in poly)
            if d:
                (hl if code in codes_hl else base).append(d)
    return "".join(base), "".join(hl)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def map_svg(geo, spec):
    """spec: {countries: [ADM0_A3], view?: [lon0, lat0, lon1, lat1], points?: [{name, lon, lat}]}"""
    codes = spec.get("countries", [])
    pts = spec.get("points", [])
    if spec.get("view"):
        view = fit_view(tuple(spec["view"]), pad=0)
    else:
        bbs = [geo.main_bbox(c) for c in codes] + [(p["lon"], p["lat"], p["lon"], p["lat"]) for p in pts]
        view = fit_view(union(bbs))
    pj = Proj(view, W, H)
    base, hl = country_paths(geo, view, pj, set(codes))
    parts = [f'<svg class="map" viewBox="0 0 {W} {H}" role="img" aria-label="定位图：'
             f'{esc("、".join(geo.countries[c]["name"] for c in codes) or "、".join(p["name"] for p in pts))}">',
             f'<rect class="sea" width="{W}" height="{H}"/>',
             f'<path class="land" d="{base}"/>', f'<path class="land-hl" d="{hl}"/>']
    placed = []  # 已放标签的 (x0, y0, x1, y1)，按字数估宽；国名和地名共用，互不重叠
    hit = lambda box: any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed)
    # 国名：标在 Natural Earth 给出的标注点上，落在画面外就不标；和前面的国名撞上就上下错开，错不开就不标
    for c in codes:
        lx, ly = geo.countries[c]["label"]
        if lx is None:
            continue
        x, y = pj(lx, ly)
        if not (30 < x < W - 30 and 20 < y < H - 20) or any(math.hypot(*(a - b for a, b in zip(pj(p["lon"], p["lat"]), (x, y)))) < 70 for p in pts):
            continue
        name = geo.countries[c]["name"]
        w = 25 * len(name)  # 22px 字号加 .12em 字距
        for dy in (0, 30, -30, 60, -60):
            box = (x - w / 2, y + dy - 22, x + w / 2, y + dy + 6)
            if box[1] > 0 and box[3] < H and not hit(box):
                placed.append(box)
                parts.append(f'<text class="cname" x="{x:.0f}" y="{y + dy:.0f}" text-anchor="middle">{esc(name)}</text>')
                break
    for p in pts:
        x, y = pj(p["lon"], p["lat"])
        w = 23 * len(p["name"])
        sides = [("end", -13), ("start", 13)] if x > W * 0.7 else [("start", 13), ("end", -13)]
        for anchor, dx in sides + [sides[0]]:
            x0 = x + dx if anchor == "start" else x + dx - w
            box = (x0, y - 14, x0 + w, y + 14)
            if not hit(box):
                break
        placed.append(box)
        parts.append(f'<circle class="pt" cx="{x:.1f}" cy="{y:.1f}" r="7"/>'
                     f'<text class="pname" x="{x + dx:.1f}" y="{y + 8:.1f}" text-anchor="{anchor}">{esc(p["name"])}</text>')
    # 视野不到半个地球时加一个世界小图，标出位置
    if view[2] - view[0] < 90:
        parts.append(inset(geo, view))
    parts.append("</svg>")
    return "".join(parts)


def inset(geo, view):
    wv = (-170, -58, 190, 84)
    pj = Proj(wv, INSET_W, INSET_H)
    base, _ = country_paths(geo, wv, pj, set(), digits=0, min_step=1.5)
    x0, y0 = pj(view[0], view[3])
    x1, y1 = pj(view[2], view[1])
    bw, bh = max(x1 - x0, 4), max(y1 - y0, 4)
    ox, oy = 10, H - INSET_H - 10
    return (f'<g class="inset" transform="translate({ox} {oy})"><rect class="inset-bg" width="{INSET_W}" height="{INSET_H}"/>'
            f'<path class="land" d="{base}"/>'
            f'<rect class="inset-box" x="{x0:.0f}" y="{y0:.0f}" width="{bw:.0f}" height="{bh:.0f}"/></g>')
