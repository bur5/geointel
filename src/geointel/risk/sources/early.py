"""Early-warning sources that need no paid access.

* IODA - country-level internet outages (Georgia Tech), no key;
* NASA FIRMS - satellite fire detections (free MAP_KEY);
* airplanes.live - aircraft flagged as military (ADS-B), no key, 1 request/second;
* zakupki.gov.ru - Russian public procurement search counts for war-related medical goods;
* GDELT DOC timelines - Russian-language reporting volume on mobilisation and martial law;
* exchange rates - open.er-api.com daily rates (attribution: exchangerate-api.com);
* WFP food prices - Global Market Monitor (HDX).

Every fetched value is treated as data. Counts are compared with each country's own past.
"""

import csv
import io
import math
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from datetime import date, timedelta

IODA_URLS = (
    "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/summary",
    "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/events",
)
FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/world/1/{day}"
MIL_URL = "https://api.airplanes.live/v2/mil"
MIL_URLS = (MIL_URL, "https://api.adsb.lol/v2/mil")
ZAKUPKI_URL = "https://zakupki.gov.ru/epz/order/extendedsearch/results.html"
DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
FX_URL = "https://open.er-api.com/v6/latest/USD"
HDX_PACKAGE = "https://data.humdata.org/api/3/action/package_show?id=global-market-monitor"

# Russian procurement terms that rise before large-scale fighting (medical preparation).
ZAKUPKI_TERMS = {
    "blood": "компоненты крови",
    "field_hospital": "полевой госпиталь",
    "stretchers": "носилки",
    "tourniquet": "кровоостанавливающий жгут",
}

# Russian-language media volume on legal and manpower steps towards war.
# GDELT DOC searches the machine translation into English, so terms are English even for
# Russian-language sources.
DOC_QUERIES = {
    "mobilization": "(mobilization OR mobilisation OR reservists) sourcelang:russian",
    "martial_law": '("martial law" OR "counter-terrorist operation") sourcelang:russian',
}


# --------------------------------------------------------------------------------------
# Generic daily-series helpers


def merge_series(cache: Mapping[str, dict], new: Mapping[str, dict], keep_days: int, today: date):
    keep_from = (today - timedelta(days=keep_days)).isoformat()
    return dict(sorted((d, v) for d, v in {**cache, **new}.items() if d >= keep_from))


def ratio_to_baseline(
    series: Mapping[str, float], today: date, recent_days: int = 7, min_base: int = 21
) -> dict | None:
    """Mean of the last ``recent_days`` vs the mean and spread of earlier days."""
    start = (today - timedelta(days=recent_days)).isoformat()
    recent = [v for d, v in series.items() if d >= start]
    base = [v for d, v in series.items() if d < start]
    if not recent or len(base) < min_base:
        return None
    mean = sum(base) / len(base)
    sd = math.sqrt(sum((v - mean) ** 2 for v in base) / max(1, len(base) - 1))
    now = sum(recent) / len(recent)
    return {
        "recent": round(now, 3),
        "baseline": round(mean, 3),
        "ratio": round((now + 0.5) / (mean + 0.5), 2),
        "z": round((now - mean) / max(sd, 0.25 * mean, 0.5), 2),
    }


# --------------------------------------------------------------------------------------
# IODA internet outages


def ioda_params(today: date, days: int = 7) -> dict[str, str]:
    from datetime import UTC, datetime

    until = int(datetime(today.year, today.month, today.day, tzinfo=UTC).timestamp())
    return {"from": str(until - days * 86400), "until": str(until), "entityType": "country"}


def ioda_countries(payload: Mapping) -> dict[str, dict]:
    """Outage score and event count per country (ISO2 codes mapped to ISO3)."""
    from geointel.risk.countries import universe

    by_iso2 = {c.iso2: c.iso3 for c in universe()}
    result: dict[str, dict] = {}
    items = payload.get("data") or []
    if isinstance(items, dict):
        items = items.get("outages") or items.get("events") or list(items.values())
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        entity = item.get("entity") or {}
        code = str(entity.get("code") or item.get("entityCode") or item.get("location") or "")
        code = by_iso2.get(code.split("/")[-1].upper())
        if not code:
            continue
        scores = item.get("scores") or {}
        score = scores.get("overall") if isinstance(scores, dict) else None
        if score is None:
            score = item.get("score") or item.get("overall") or 0
        entry = result.setdefault(code, {"score": 0.0, "events": 0})
        entry["score"] = max(entry["score"], float(score or 0))
        entry["events"] += int(item.get("event_cnt") or item.get("eventCount") or 1)
    return result


# --------------------------------------------------------------------------------------
# NASA FIRMS fires


def firms_counts(text: str, locate: Callable[[float, float], str | None]) -> dict[str, int]:
    """Fire detections per country; locations are snapped to a 0.25° grid for speed."""
    counts: dict[str, int] = defaultdict(int)
    cells: dict[tuple[int, int], str | None] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, ValueError):
            continue
        if str(row.get("confidence", "")).lower() in ("l", "low"):
            continue
        cell = (round(lat * 4), round(lon * 4))
        if cell not in cells:
            cells[cell] = locate(cell[0] / 4, cell[1] / 4)
        if cells[cell]:
            counts[cells[cell]] += 1
    return dict(counts)


# --------------------------------------------------------------------------------------
# Military aircraft (ADS-B)

WATCH_BOXES = {
    "baltic": ("Балтика", "Baltic", (9.0, 53.0, 31.0, 61.0)),
    "black_sea": ("Чёрное море", "Black Sea", (27.0, 40.5, 42.0, 47.5)),
    "belarus_poland": ("Беларусь — Польша", "Belarus — Poland", (19.0, 50.0, 33.0, 56.5)),
    "barents": ("Баренцево море и Кола", "Barents Sea and Kola", (15.0, 66.0, 45.0, 75.0)),
    "gulf": ("Персидский залив", "Persian Gulf", (46.0, 23.0, 60.0, 31.0)),
    "east_med": ("Восточное Средиземноморье", "Eastern Mediterranean", (28.0, 30.0, 37.0, 37.5)),
    "taiwan": ("Тайваньский пролив", "Taiwan Strait", (115.0, 20.0, 126.0, 28.0)),
    "korea": ("Корейский полуостров", "Korean Peninsula", (124.0, 33.0, 131.5, 43.0)),
}


def military_counts(payloads: Iterable[Mapping]) -> dict[str, int]:
    """Distinct military aircraft per watched box across one or more snapshots."""
    seen: dict[str, set[str]] = defaultdict(set)
    for payload in payloads:
        for ac in payload.get("ac") or []:
            try:
                lat, lon = float(ac["lat"]), float(ac["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            for key, (_ru, _en, (x0, y0, x1, y1)) in WATCH_BOXES.items():
                if x0 <= lon <= x1 and y0 <= lat <= y1:
                    seen[key].add(str(ac.get("hex") or ac.get("flight") or f"{lat},{lon}"))
    return {key: len(seen.get(key, set())) for key in WATCH_BOXES}


BOX_COUNTRIES = {
    "baltic": ("EST", "LVA", "LTU", "POL", "FIN", "SWE", "DNK", "DEU"),
    "black_sea": ("ROU", "BGR", "TUR", "UKR", "GEO"),
    "belarus_poland": ("POL", "LTU", "LVA", "UKR"),
    "barents": ("NOR", "FIN"),
    "gulf": ("IRN", "ARE", "QAT", "BHR", "KWT", "SAU", "OMN"),
    "east_med": ("ISR", "LBN", "SYR", "CYP"),
    "taiwan": ("TWN", "CHN", "PHL", "JPN"),
    "korea": ("KOR", "PRK", "JPN"),
}


# --------------------------------------------------------------------------------------
# Russian procurement


def zakupki_params(term: str, start: date, end: date) -> dict[str, str]:
    return {
        "searchString": term,
        "morphology": "on",
        "fz44": "on",
        "fz223": "on",
        "publishDateFrom": start.strftime("%d.%m.%Y"),
        "publishDateTo": end.strftime("%d.%m.%Y"),
        "recordsPerPage": "_10",
    }


def zakupki_total(html: str) -> int | None:
    match = re.search(r"search-results__total[^>]*>\s*([^<]+)<", html)
    if not match:
        return None
    digits = re.sub(r"[^\d]", "", match.group(1))
    return int(digits) if digits else None


def weekly_windows(today: date, weeks: int) -> list[tuple[date, date]]:
    end = today - timedelta(days=today.weekday() + 1)  # last complete Mon–Sun week
    return [(end - timedelta(days=7 * i + 6), end - timedelta(days=7 * i)) for i in range(weeks)]


# --------------------------------------------------------------------------------------
# GDELT DOC timelines


def doc_timeline_params(query: str) -> dict[str, str]:
    return {"query": query, "mode": "timelinevolraw", "format": "json", "timespan": "90d"}


def doc_timeline(payload: Mapping) -> dict[str, float]:
    """Daily article counts from a GDELT DOC timeline (volume of matching articles)."""
    series: dict[str, float] = {}
    for line in payload.get("timeline") or []:
        for point in line.get("data") or []:
            stamp = str(point.get("date") or "")
            if len(stamp) >= 8:
                day = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
                series[day] = series.get(day, 0.0) + float(point.get("value") or 0)
        break  # the first line is the matching volume
    return series


# --------------------------------------------------------------------------------------
# Exchange rates


def fx_rates(payload: Mapping) -> dict[str, float]:
    if payload.get("result") != "success":
        return {}
    return {k: float(v) for k, v in (payload.get("rates") or {}).items() if v}


def currency_of(iso3: str) -> str | None:
    return _CURRENCIES.get(iso3) or None


def fx_change(history: Mapping[str, Mapping[str, float]], code: str, today: date) -> dict | None:
    """Change in the local-currency value of one US dollar over ~30 days."""
    points = sorted((d, r.get(code)) for d, r in history.items() if r.get(code))
    if len(points) < 2:
        return None
    last_day, last = points[-1]
    target = (today - timedelta(days=30)).isoformat()
    older = [p for p in points if p[0] <= target]
    if not older:
        return None
    _, base = older[-1]
    depreciation = last / base - 1  # >0: local currency lost value
    return {"change30": round(depreciation, 4), "since": older[-1][0], "last": last_day}


# --------------------------------------------------------------------------------------
# WFP food prices


def hdx_csv_url(package: Mapping) -> str | None:
    for res in (package.get("result") or {}).get("resources") or []:
        name = str(res.get("name") or res.get("url") or "").lower()
        if name.endswith(".csv") and "subnational" not in name:
            return res.get("url")
    return None


def food_prices(text: str) -> dict[str, dict]:
    """Latest food-basket change per country from the WFP Global Market Monitor CSV."""
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if rows and str(next(iter(rows[0].values()), "")).startswith("#"):
        rows = rows[1:]  # HXL tag row
    from geointel.risk.countries import universe_codes

    result: dict[str, dict] = {}
    for row in rows:
        row = {str(k).strip().lower(): str(v or "").strip() for k, v in row.items()}
        code = (row.get("countryiso3") or row.get("iso3") or row.get("adm0_iso3") or "").upper()
        if code not in universe_codes():
            continue
        day = row.get("date") or row.get("survey_date") or ""
        change = None
        for key in (
            "price_basket_change_1m",
            "basket_change_1m",
            "food_basket_change_1m",
            "change_1m",
            "price_change_1m",
        ):
            try:
                change = float(row[key])
                break
            except (KeyError, ValueError):
                continue
        level = row.get("impact") or row.get("alert") or row.get("price_alert") or ""
        if day and (code not in result or day > result[code]["date"]):
            result[code] = {"date": day[:10], "change_1m": change, "alert": level}
    return result


# ISO3 -> ISO 4217 for currencies with a national exchange rate (euro area and dollarised
# economies are left out on purpose: their rate says nothing about a national crisis).
_CURRENCIES = {
    "AFG": "AFN",
    "ALB": "ALL",
    "DZA": "DZD",
    "AGO": "AOA",
    "ARG": "ARS",
    "ARM": "AMD",
    "AUS": "AUD",
    "AZE": "AZN",
    "BHS": "BSD",
    "BHR": "BHD",
    "BGD": "BDT",
    "BRB": "BBD",
    "BLR": "BYN",
    "BLZ": "BZD",
    "BTN": "BTN",
    "BOL": "BOB",
    "BIH": "BAM",
    "BWA": "BWP",
    "BRA": "BRL",
    "BRN": "BND",
    "BGR": "BGN",
    "BDI": "BIF",
    "KHM": "KHR",
    "CMR": "XAF",
    "CAN": "CAD",
    "CPV": "CVE",
    "CHL": "CLP",
    "CHN": "CNY",
    "COL": "COP",
    "COM": "KMF",
    "COD": "CDF",
    "CRI": "CRC",
    "CUB": "CUP",
    "CZE": "CZK",
    "DNK": "DKK",
    "DJI": "DJF",
    "DOM": "DOP",
    "EGY": "EGP",
    "ERI": "ERN",
    "SWZ": "SZL",
    "ETH": "ETB",
    "FJI": "FJD",
    "GMB": "GMD",
    "GEO": "GEL",
    "GHA": "GHS",
    "GTM": "GTQ",
    "GIN": "GNF",
    "GUY": "GYD",
    "HTI": "HTG",
    "HND": "HNL",
    "HUN": "HUF",
    "ISL": "ISK",
    "IND": "INR",
    "IDN": "IDR",
    "IRN": "IRR",
    "IRQ": "IQD",
    "ISR": "ILS",
    "JAM": "JMD",
    "JPN": "JPY",
    "JOR": "JOD",
    "KAZ": "KZT",
    "KEN": "KES",
    "KOR": "KRW",
    "KWT": "KWD",
    "KGZ": "KGS",
    "LAO": "LAK",
    "LBN": "LBP",
    "LSO": "LSL",
    "LBR": "LRD",
    "LBY": "LYD",
    "MDG": "MGA",
    "MWI": "MWK",
    "MYS": "MYR",
    "MDV": "MVR",
    "MRT": "MRU",
    "MUS": "MUR",
    "MEX": "MXN",
    "MDA": "MDL",
    "MNG": "MNT",
    "MAR": "MAD",
    "MOZ": "MZN",
    "MMR": "MMK",
    "NAM": "NAD",
    "NPL": "NPR",
    "NZL": "NZD",
    "NIC": "NIO",
    "NGA": "NGN",
    "MKD": "MKD",
    "NOR": "NOK",
    "OMN": "OMR",
    "PAK": "PKR",
    "PAN": "PAB",
    "PNG": "PGK",
    "PRY": "PYG",
    "PER": "PEN",
    "PHL": "PHP",
    "POL": "PLN",
    "QAT": "QAR",
    "ROU": "RON",
    "RUS": "RUB",
    "RWA": "RWF",
    "SAU": "SAR",
    "SRB": "RSD",
    "SYC": "SCR",
    "SLE": "SLE",
    "SGP": "SGD",
    "SLB": "SBD",
    "SOM": "SOS",
    "ZAF": "ZAR",
    "SSD": "SSP",
    "LKA": "LKR",
    "SDN": "SDG",
    "SUR": "SRD",
    "SWE": "SEK",
    "CHE": "CHF",
    "SYR": "SYP",
    "TWN": "TWD",
    "TJK": "TJS",
    "TZA": "TZS",
    "THA": "THB",
    "TTO": "TTD",
    "TUN": "TND",
    "TUR": "TRY",
    "TKM": "TMT",
    "UGA": "UGX",
    "UKR": "UAH",
    "ARE": "AED",
    "GBR": "GBP",
    "URY": "UYU",
    "UZB": "UZS",
    "VUT": "VUV",
    "VEN": "VES",
    "VNM": "VND",
    "YEM": "YER",
    "ZMB": "ZMW",
    "ZWE": "ZWG",
    "BEN": "XOF",
    "BFA": "XOF",
    "CIV": "XOF",
    "MLI": "XOF",
    "NER": "XOF",
    "SEN": "XOF",
    "TGO": "XOF",
    "GNB": "XOF",
    "TCD": "XAF",
    "CAF": "XAF",
    "COG": "XAF",
    "GAB": "XAF",
    "GNQ": "XAF",
}
