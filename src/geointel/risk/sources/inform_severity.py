"""INFORM Severity Index (European Commission JRC, via HDX): how severe each humanitarian
crisis is (1 very low … 5 very high), monthly, with its three dimensions."""

import re
from collections.abc import Mapping

from geointel.risk.countries import universe_codes
from geointel.risk.sources.xlsx import sheets

PACKAGE = (
    "https://data.humdata.org/api/3/action/package_show?id=inform-global-crisis-severity-index"
)
SOURCE = "INFORM Severity Index (EC JRC), via HDX"


def latest_resource(package: Mapping) -> str | None:
    resources = (package.get("result") or {}).get("resources") or []
    dated = []
    for r in resources:
        url = str(r.get("url") or "")
        m = re.search(r"/(\d{6})-inform-severity", url)
        if m and url.endswith(".xlsx"):
            dated.append((m.group(1), url))
    return max(dated)[1] if dated else None


SCORE_NAMES = ("inform severity index", "severity index")


def _find(header: list[str], *keys: str) -> int | None:
    return next((j for j, h in enumerate(header) if any(k in h for k in keys)), None)


def _pick(row: list[str], j: int | None) -> str:
    return row[j] if j is not None and j < len(row) else ""


def _num(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def parse(payload: bytes) -> dict[str, dict]:
    """ISO3 -> the most severe crisis: score, category, crisis name and dimensions."""
    codes = universe_codes()
    best: dict[str, dict] = {}
    for name, rows in sheets(payload).items():
        for i, row in enumerate(rows[:12]):
            header = [h.strip().lower() for h in row]
            if "iso3" not in header:
                continue
            iso_i = header.index("iso3")
            score_i = next(
                (
                    j
                    for j, h in enumerate(header)
                    if h in ("inform severity index", "severity index")
                ),
                None,
            )
            if score_i is None:
                continue
            crisis_i = _find(header, "crisis name", "crisis")
            cat_i = _find(header, "severity category", "category")
            impact_i, cond_i, comp_i = (
                _find(header, "impact"),
                _find(header, "conditions"),
                _find(header, "complexity"),
            )
            for r in rows[i + 1 :]:
                if len(r) <= max(iso_i, score_i):
                    continue
                iso3 = r[iso_i].strip().upper()[:3]
                score = _num(r[score_i])
                if iso3 not in codes or score is None:
                    continue
                item = {
                    "score": round(score, 1),
                    "category": _pick(r, cat_i),
                    "crisis": _pick(r, crisis_i),
                    "impact": _num(_pick(r, impact_i)),
                    "conditions": _num(_pick(r, cond_i)),
                    "complexity": _num(_pick(r, comp_i)),
                    "sheet": name,
                }
                if iso3 not in best or score > best[iso3]["score"]:
                    best[iso3] = item
            break
    return best
