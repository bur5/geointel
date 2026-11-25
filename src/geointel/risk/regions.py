"""Assign event coordinates to first-level administrative regions (Natural Earth, public domain)."""

import json
from collections import defaultdict
from math import hypot

from geointel.risk.countries import universe

SOURCE = "Natural Earth admin-1 states and provinces (1:10m)"
URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
    "ne_10m_admin_1_states_provinces.geojson"
)
MAX_DISTANCE_DEG = 3.0


def _rings(geometry: dict) -> list[list[list[float]]]:
    if geometry.get("type") == "Polygon":
        return [geometry["coordinates"][0]]
    if geometry.get("type") == "MultiPolygon":
        return [poly[0] for poly in geometry["coordinates"]]
    return []


def _inside(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _segment_distance(x: float, y: float, a: list[float], b: list[float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / length))
    return hypot(x - (a[0] + t * dx), y - (a[1] + t * dy))


class RegionIndex:
    def __init__(self, geojson: dict):
        iso2_to_iso3 = {c.iso2: c.iso3 for c in universe()}
        self.by_country: dict[str, list[tuple]] = defaultdict(list)
        for feature in geojson.get("features") or []:
            props = feature.get("properties") or {}
            iso3 = iso2_to_iso3.get(str(props.get("iso_a2") or "").upper())
            if not iso3:
                continue
            rings = _rings(feature.get("geometry") or {})
            if not rings:
                continue
            xs = [p[0] for r in rings for p in r]
            ys = [p[1] for r in rings for p in r]
            names = (
                props.get("name_en") or props.get("name") or "",
                props.get("name_ru") or props.get("name_en") or props.get("name") or "",
            )
            self.by_country[iso3].append(((min(xs), min(ys), max(xs), max(ys)), rings, names))

    def country_of(self, lat: float, lon: float) -> str | None:
        """Country (ISO3) whose admin-1 polygon contains the point, if any."""
        if not hasattr(self, "_bounds"):
            self._bounds = {
                code: (
                    min(f[0][0] for f in feats),
                    min(f[0][1] for f in feats),
                    max(f[0][2] for f in feats),
                    max(f[0][3] for f in feats),
                )
                for code, feats in self.by_country.items()
            }
        for code, (x0, y0, x1, y1) in self._bounds.items():
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            for (fx0, fy0, fx1, fy1), rings, _names in self.by_country[code]:
                if (
                    fx0 <= lon <= fx1
                    and fy0 <= lat <= fy1
                    and any(_inside(lon, lat, r) for r in rings)
                ):
                    return code
        return None

    @classmethod
    def from_bytes(cls, payload: bytes) -> "RegionIndex":
        return cls(json.loads(payload))

    def locate(self, iso3: str, lat: float, lon: float) -> tuple[str, str] | None:
        features = self.by_country.get(iso3) or []
        for (x0, y0, x1, y1), rings, names in features:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and any(_inside(lon, lat, r) for r in rings):
                return names
        best, best_d = None, MAX_DISTANCE_DEG
        for (x0, y0, x1, y1), rings, names in features:
            if lon < x0 - best_d or lon > x1 + best_d or lat < y0 - best_d or lat > y1 + best_d:
                continue
            for ring in rings:
                sampled = ring[:: max(1, len(ring) // 200)] + [ring[-1]]
                for a, b in zip(sampled, sampled[1:], strict=False):
                    d = _segment_distance(lon, lat, a, b)
                    if d < best_d:
                        best, best_d = names, d
        return best


def annotate(events: list[dict], index: RegionIndex) -> None:
    """Add region_en/region_ru for events with coordinates and exactly one country."""
    for event in events:
        if (
            event.get("lat") is None
            or event.get("lon") is None
            or len(event.get("countries") or []) != 1
        ):
            continue
        names = index.locate(event["countries"][0], event["lat"], event["lon"])
        if names:
            event["region_en"], event["region_ru"] = names
