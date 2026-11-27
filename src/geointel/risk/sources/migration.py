"""Forced displacement (UNHCR Refugee Data Finder API) and EU asylum (Eurostat JSON-stat)."""

from collections import defaultdict
from collections.abc import Iterable, Mapping

from geointel.risk.countries import universe_codes

UNHCR_SOURCE = "UNHCR Refugee Population Statistics (api.unhcr.org)"
UNHCR_URL = "https://api.unhcr.org/population/v1/population/"
EUROSTAT_SOURCE = "Eurostat migr_asyappctzm (first-time asylum applicants, monthly)"
EUROSTAT_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/migr_asyappctzm"
IRREGULAR_SOURCE = "Eurostat migr_eipre (third-country nationals found illegally present)"
IRREGULAR_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/migr_eipre"
# Countries with published estimates of the number of irregular residents. Estimates differ
# by method, so the range spans the sources; the year is the reference year of the estimates.
IRREGULAR_ESTIMATES: dict[str, dict] = {
    "USA": {
        "low": 14_000_000,
        "high": 15_800_000,
        "years": "2023–2024",
        "sources": [
            [
                "Pew Research Center, 2023: 14.0M",
                "https://www.pewresearch.org/race-and-ethnicity/2025/08/21/u-s-unauthorized-immigrant-population-reached-a-record-14-million-in-2023/",
            ],
            [
                "Center for Migration Studies, 2024: 14.6M",
                "https://cmsny.org/research-and-policy/data/",
            ],
            ["Migration Policy Institute, 2024: 15.8M", "https://www.migrationpolicy.org/"],
        ],
        "note_ru": "После 2024 года число могло снизиться из-за отъездов и депортаций; "
        "свежих полных оценок нет, источники расходятся.",
        "note_en": "The number may have fallen after 2024 because of departures and "
        "deportations; no complete newer estimates, and sources disagree.",
    },
}
# Eurostat uses EL for Greece and UK for the United Kingdom.
EUROSTAT_GEO = {"EL": "GRC", "UK": "GBR"}


def unhcr_params(year: int, page: int) -> dict[str, str]:
    return {
        "limit": "10000",
        "page": str(page),
        "year": str(year),
        "coo_all": "true",
        "coa_all": "true",
        "cf_type": "ISO",
    }


def eurostat_params(since: str) -> dict[str, str]:
    return {
        "format": "JSON",
        "lang": "EN",
        "citizen": "TOTAL",
        "sex": "T",
        "age": "TOTAL",
        "applicant": "FRST",
        "unit": "PER",
        "sinceTimePeriod": since,
    }


def _num(value: object) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def displacement(rows: Iterable[Mapping], year: int) -> dict:
    """Bilateral refugees + asylum seekers + others in need of protection, and IDPs."""
    universe = universe_codes()
    pairs: dict[tuple[str, str], int] = defaultdict(int)
    idps: dict[str, int] = {}
    for row in rows:
        origin = str(row.get("coo_iso") or "").upper()
        host = str(row.get("coa_iso") or "").upper()
        if host not in universe:
            continue
        if origin == host:
            if _num(row.get("idps")):
                idps[origin] = _num(row.get("idps"))
            continue
        total = sum(_num(row.get(k)) for k in ("refugees", "asylum_seekers", "oip"))
        if total:
            pairs[(origin if origin in universe else "OTHER", host)] += total
    hosted: dict[str, dict] = defaultdict(lambda: {"total": 0, "origins": {}})
    abroad: dict[str, dict] = defaultdict(lambda: {"total": 0, "hosts": {}})
    for (origin, host), n in pairs.items():
        hosted[host]["total"] += n
        hosted[host]["origins"][origin] = n
        if origin != "OTHER":
            abroad[origin]["total"] += n
            abroad[origin]["hosts"][host] = n

    def top(counts: Mapping[str, int], k: int = 8) -> list[dict]:
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        return [{"iso3": c, "n": n} for c, n in ranked[:k] if c != "OTHER"]

    result: dict[str, dict] = {}
    for code in universe:
        entry: dict = {}
        if code in hosted:
            entry["hosted"] = hosted[code]["total"]
            entry["hosted_from"] = top(hosted[code]["origins"])
        if code in abroad:
            entry["abroad"] = abroad[code]["total"]
            entry["abroad_in"] = top(abroad[code]["hosts"])
        if code in idps:
            entry["idps"] = idps[code]
        if entry:
            entry["year"] = year
            result[code] = entry
    return result


def jsonstat_series(payload: Mapping) -> dict[str, list[tuple[str, float]]]:
    """Monthly series per country (ISO3) from a Eurostat JSON-stat 2.0 response."""
    ids: list[str] = list(payload.get("id") or [])
    sizes: list[int] = list(payload.get("size") or [])
    dims: Mapping = payload.get("dimension") or {}
    if "geo" not in ids or "time" not in ids or len(ids) != len(sizes):
        return {}
    index = {d: (dims[d]["category"]["index"]) for d in ids}
    order = {d: sorted(index[d], key=lambda k: index[d][k]) for d in ids}
    strides = [1] * len(ids)
    for i in range(len(ids) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    values: Mapping = payload.get("value") or {}
    from geointel.risk.countries import universe

    by_iso2 = {c.iso2: c.iso3 for c in universe()}
    series: dict[str, list[tuple[str, float]]] = {}
    geo_i, time_i = ids.index("geo"), ids.index("time")
    for flat_key, value in values.items():
        flat = int(flat_key)
        coords = [(flat // strides[i]) % sizes[i] for i in range(len(ids))]
        if any(coords[i] != 0 for i in range(len(ids)) if i not in (geo_i, time_i)):
            continue
        geo = order["geo"][coords[geo_i]]
        code = EUROSTAT_GEO.get(geo)
        if code is None:
            code = by_iso2.get(geo)
        if not code or value is None:
            continue
        series.setdefault(code, []).append((order["time"][coords[time_i]], float(value)))
    return {code: sorted(points) for code, points in series.items()}


def asylum_trend(series: Mapping[str, list[tuple[str, float]]]) -> dict[str, dict]:
    """Last 24 months, sum of last 12 vs previous 12, latest month."""
    result: dict[str, dict] = {}
    for code, points in series.items():
        points = points[-24:]
        if len(points) < 13:
            continue
        last12 = sum(v for _, v in points[-12:])
        prev = points[:-12]
        prev12 = sum(v for _, v in prev) * (12 / len(prev)) if prev else 0
        result[code] = {
            "months": [m for m, _ in points],
            "values": [int(v) for _, v in points],
            "last12": int(last12),
            "change": round(last12 / prev12 - 1, 3) if prev12 else None,
        }
    return result


def merge_pages(pages: Iterable[Mapping]) -> list[dict]:
    rows: list[dict] = []
    for page in pages:
        rows.extend(page.get("items") or [])
    return rows


def irregular_params(since: int) -> dict[str, str]:
    return {
        "format": "JSON",
        "lang": "EN",
        "reason": "TOTAL",
        "apprehen": "TOTAL",
        "citizen": "TOTAL",
        "sex": "T",
        "age": "TOTAL",
        "unit": "PER",
        "sinceTimePeriod": str(since),
    }


def irregular_found(series: Mapping[str, list[tuple[str, float]]]) -> dict[str, dict]:
    """Latest annual count of people found illegally present, per reporting country."""
    out: dict[str, dict] = {}
    for code, points in series.items():
        points = [(t, v) for t, v in points if v is not None]
        if not points:
            continue
        year, value = points[-1]
        out[code] = {"year": year, "found": int(value), "series": [[t, int(v)] for t, v in points]}
    return out


def irregular_label(code: str, found: Mapping[str, dict] | None) -> dict:
    """One of three honest labels; never a zero for a country without data."""
    estimate = IRREGULAR_ESTIMATES.get(code)
    if estimate:
        return {"kind": "estimate", **estimate}
    item = (found or {}).get(code)
    if item:
        return {"kind": "indirect", "source": IRREGULAR_SOURCE, "url": IRREGULAR_URL, **item}
    return {"kind": "none"}


POLICY_SIGNS = {"migration_tighten": 1, "migration_ease": -1}


def policy_journal(cache: Iterable[dict], news: Iterable[dict], keep_from: str) -> list[dict]:
    """News-classified immigration policy changes, kept for 400 days (deduplicated by URL)."""
    seen: set[tuple] = set()
    out = []
    for entry in [*news, *cache]:
        if entry.get("sign") not in POLICY_SIGNS or entry.get("date", "") < keep_from:
            continue
        key = (entry.get("url"), entry.get("country"), entry.get("sign"))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                k: entry.get(k)
                for k in ("date", "country", "sign", "summary_ru", "summary_en", "url", "domain")
            }
        )
    return sorted(out, key=lambda e: e["date"], reverse=True)


def policy_summary(journal: Iterable[dict], today) -> dict[str, dict]:
    """Direction of policy changes per country over 3 and 12 months: >0 tighter, <0 easier."""
    from datetime import date

    out: dict[str, dict] = {}
    for entry in journal:
        code = entry["country"]
        age = (today - date.fromisoformat(entry["date"])).days
        item = out.setdefault(code, {"d90": 0, "d365": 0, "entries": []})
        weight = POLICY_SIGNS[entry["sign"]]
        if age <= 90:
            item["d90"] += weight
        if age <= 365:
            item["d365"] += weight
        if len(item["entries"]) < 6:
            item["entries"].append(entry)
    return out
