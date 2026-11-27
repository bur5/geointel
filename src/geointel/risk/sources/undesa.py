"""UN DESA International Migrant Stock: people born in a country and living abroad.

The workbook's "Table 1" has one row per destination × origin with columns for 1990–2024
(both sexes first, then male and female). Rows whose destination is WORLD (M49 code 900)
give the total stock abroad by origin. Values are mid-year estimates; for many destinations
they are modelled, so GeoIntel shows them as estimates with the year.
"""

from __future__ import annotations

from collections.abc import Iterable

SOURCE = "UN DESA International Migrant Stock 2024"
URL = (
    "https://www.un.org/development/desa/pd/sites/www.un.org.development.desa.pd/files/"
    "undesa_pd_2024_ims_stock_by_sex_destination_and_origin.xlsx"
)
WORLD = "900"


def _numeric_map() -> dict[str, str]:
    from geointel.risk.countries import universe

    return {str(int(c.numeric)): c.iso3 for c in universe() if c.numeric}


def _num(text: str) -> float | None:
    text = str(text).strip().replace(" ", "")
    if not text or text in ("..", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _code(text: str) -> str | None:
    value = _num(text)
    return str(int(value)) if value is not None else None


def stock(rows: Iterable[list[str]], top: int = 8) -> dict[str, dict]:
    """{origin ISO3: {"year": 2024, "total": n, "series": {year: n}, "top": [[ISO3, n]]}}."""
    numeric = _numeric_map()
    header: list[str] | None = None
    dest_col = origin_col = None
    years: list[tuple[int, int]] = []
    totals: dict[str, dict[int, float]] = {}
    dests: dict[str, list[tuple[str, float]]] = {}
    series_by_dest: dict[str, dict[str, dict[str, int]]] = {}
    for row in rows:
        if header is None:
            lower = [str(c).strip().lower() for c in row]
            if any("location code of destination" in c for c in lower) and any(
                "location code of origin" in c for c in lower
            ):
                header = lower
                dest_col = next(i for i, c in enumerate(lower) if "code of destination" in c)
                origin_col = next(i for i, c in enumerate(lower) if "code of origin" in c)
                seen: set[int] = set()
                for i, c in enumerate(lower):
                    value = _num(c)
                    if value and 1950 <= value <= 2100 and int(value) not in seen:
                        seen.add(int(value))
                        years.append((i, int(value)))
            continue
        if len(row) <= max(dest_col or 0, origin_col or 0) or not years:
            continue
        origin = numeric.get(_code(row[origin_col]) or "")
        if not origin:
            continue
        dest_code = _code(row[dest_col])
        values = {y: _num(row[i]) for i, y in years if i < len(row)}
        if dest_code == WORLD:
            totals[origin] = {y: v for y, v in values.items() if v is not None}
            continue
        dest = numeric.get(dest_code or "")
        latest = values.get(years[-1][1])
        if dest and latest:
            dests.setdefault(origin, []).append((dest, latest))
            series_by_dest.setdefault(origin, {})[dest] = {
                str(y): int(v) for y, v in values.items() if v is not None and y >= 2010
            }
    out: dict[str, dict] = {}
    for origin, series in totals.items():
        if not series:
            continue
        year = max(series)
        out[origin] = {
            "year": year,
            "total": int(series[year]),
            "series": {str(y): int(v) for y, v in sorted(series.items())},
            "top": [
                [code, int(n)]
                for code, n in sorted(dests.get(origin, []), key=lambda x: -x[1])[:top]
            ],
            # Destination series since 2010 for the top destinations: shows where the growth
            # after 2014 and after 2022 went (net change between UN estimate years).
            "destinations": {
                code: series_by_dest.get(origin, {}).get(code, {})
                for code, _n in sorted(dests.get(origin, []), key=lambda x: -x[1])[:top]
            },
        }
    return out


def from_workbook(payload: bytes) -> dict[str, dict]:
    from geointel.risk.sources import xlsx

    books = xlsx.sheets(payload)
    name = next((n for n in books if n.strip().lower() == "table 1"), None) or next(iter(books))
    return stock(books[name])
