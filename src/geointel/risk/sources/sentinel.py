"""Sentinel-1 radar change detection at watched military sites (Copernicus Data Space).

Radar backscatter from metal (vehicles, equipment) is bright. For each site we track the 99th
percentile of VV backscatter in six-day intervals; a sharp rise over the site's own recent
level is a sign of a build-up. Experimental: buildings, harvest and snow also change radar
returns, so a change needs confirmation from reports. Sites are approximate areas around
garrison towns, not exact facility outlines.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

SOURCE = "Copernicus Sentinel-1 (Sentinel Hub Statistical API)"
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"


@dataclass(frozen=True)
class Site:
    key: str
    name_ru: str
    name_en: str
    lat: float
    lon: float
    actor: str
    countries: tuple[str, ...]  # countries whose risk a build-up here would raise


SITES: tuple[Site, ...] = (
    Site("pskov", "Псков", "Pskov", 57.82, 28.33, "RUS", ("EST", "LVA")),
    Site("luga", "Луга", "Luga", 58.74, 29.85, "RUS", ("EST",)),
    Site("petrozavodsk", "Петрозаводск", "Petrozavodsk", 61.79, 34.36, "RUS", ("FIN",)),
    Site("alakurtti", "Алакуртти", "Alakurtti", 66.96, 30.35, "RUS", ("FIN",)),
    Site("pechenga", "Печенга", "Pechenga", 69.55, 31.20, "RUS", ("NOR", "FIN")),
    Site("chernyakhovsk", "Черняховск", "Chernyakhovsk", 54.63, 21.81, "RUS", ("LTU", "POL")),
    Site("gusev", "Гусев", "Gusev", 54.59, 22.20, "RUS", ("LTU", "POL")),
    Site("grodno", "Гродно", "Grodno", 53.68, 23.83, "BLR", ("LTU", "POL")),
    Site("brest", "Брест", "Brest", 52.10, 23.70, "BLR", ("POL", "UKR")),
    Site("osipovichi", "Осиповичи", "Asipovichy", 53.30, 28.64, "BLR", ("POL", "LTU", "UKR")),
    Site("yelnya", "Ельня", "Yelnya", 54.58, 33.18, "RUS", ("UKR", "BLR")),
    Site("klintsy", "Клинцы", "Klintsy", 52.75, 32.24, "RUS", ("UKR",)),
    Site("belgorod", "Белгород", "Belgorod", 50.60, 36.60, "RUS", ("UKR",)),
)

EVALSCRIPT = """//VERSION=3
function setup() {
  return {input: [{bands: ["VV", "dataMask"]}],
          output: [{id: "vv", bands: 1, sampleType: "FLOAT32"}, {id: "dataMask", bands: 1}]};
}
function evaluatePixel(s) { return {vv: [s.VV], dataMask: [s.dataMask]}; }
"""


def request(site: Site, today: date, days: int = 420, half: float = 0.05) -> dict:
    return {
        "input": {
            "bounds": {
                "bbox": [
                    site.lon - half,
                    site.lat - half * 0.6,
                    site.lon + half,
                    site.lat + half * 0.6,
                ],
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [
                {
                    "type": "sentinel-1-grd",
                    "dataFilter": {"acquisitionMode": "IW", "polarization": "DV"},
                    "processing": {"orthorectify": True, "backCoeff": "SIGMA0_ELLIPSOID"},
                }
            ],
        },
        "aggregation": {
            "timeRange": {
                "from": f"{(today - timedelta(days=days)).isoformat()}T00:00:00Z",
                "to": f"{today.isoformat()}T00:00:00Z",
            },
            "aggregationInterval": {"of": "P6D"},
            "evalscript": EVALSCRIPT,
            "resx": 0.0002,
            "resy": 0.0002,
        },
        "calculations": {"default": {"statistics": {"default": {"percentiles": {"k": [99]}}}}},
    }


def series(response: Mapping) -> list[tuple[str, float]]:
    points = []
    for item in response.get("data") or []:
        stats = (
            ((item.get("outputs") or {}).get("vv") or {})
            .get("bands", {})
            .get("B0", {})
            .get("stats")
        ) or {}
        value = (stats.get("percentiles") or {}).get("99.0")
        if isinstance(value, int | float) and value > 0 and stats.get("sampleCount", 1):
            points.append((str((item.get("interval") or {}).get("from", ""))[:10], float(value)))
    return sorted(points)


def change(points: list[tuple[str, float]], seasonal_days: int = 365) -> dict | None:
    """Last two intervals vs the site's recent median and vs the same weeks a year earlier.

    A rise counts only when it beats both: the recent median (sudden change) and last year's
    level for the same season (snow, harvest and leaf cover change radar returns every year).
    """
    if len(points) < 8:
        return None
    recent = [v for _, v in points[-2:]]
    now = sum(recent) / len(recent)
    earlier = sorted(v for _, v in points[-17:-2])
    median = earlier[len(earlier) // 2]
    last_day = date.fromisoformat(points[-1][0])
    season = [
        v for d, v in points if abs((last_day - date.fromisoformat(d)).days - seasonal_days) <= 21
    ]
    ratio = now / median if median else None
    if ratio is None:
        return None
    seasonal = now / (sum(season) / len(season)) if season else None
    active = ratio >= 1.5 and (seasonal is None or seasonal >= 1.4)
    return {
        "ratio": round(ratio, 2),
        "seasonal_ratio": round(seasonal, 2) if seasonal else None,
        "active": active,
        "last": points[-1][0],
    }
