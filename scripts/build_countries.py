"""Build src/watchstreet/data/countries.json (name + label point) from the vendored topojson.

Run:  python scripts/build_countries.py
"""

import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src/watchstreet/web/static/vendor/countries-110m.json"
DST = ROOT / "src/watchstreet/data/countries.json"


def decode_arcs(topo: dict) -> list[list[tuple[float, float]]]:
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            points.append((x * sx + tx, y * sy + ty))
        arcs.append(points)
    return arcs


def ring(arcs: list[list[tuple[float, float]]], ids: list[int]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i in ids:
        pts = arcs[i] if i >= 0 else arcs[~i][::-1]
        out += pts[1:] if out else pts
    return out


def centroid(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in itertools.pairwise(points):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if area == 0:
        xs, ys = zip(*points, strict=True)
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    return cx / (3 * area), cy / (3 * area), abs(area) / 2


# The antimeridian breaks the planar centroid for these; use hand-set label points.
OVERRIDES = {"Russia": (61.5, 99.0), "Fiji": (-17.8, 178.0)}


def main() -> None:
    topo = json.loads(SRC.read_text())
    arcs = decode_arcs(topo)
    out = []
    for geom in topo["objects"]["countries"]["geometries"]:
        polys = geom["arcs"] if geom["type"] == "MultiPolygon" else [geom["arcs"]]
        best = max((centroid(ring(arcs, p[0])) for p in polys), key=lambda c: c[2])
        name = geom["properties"]["name"]
        lat, lon = OVERRIDES.get(name, (best[1], best[0]))
        out.append({"name": name, "lon": round(lon, 2), "lat": round(lat, 2)})
    out.sort(key=lambda c: c["name"])
    DST.write_text(json.dumps(out, ensure_ascii=False, indent=0))
    print(len(out), "countries")


if __name__ == "__main__":
    main()
