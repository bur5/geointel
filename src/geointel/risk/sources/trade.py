"""Bilateral merchandise trade (UN Comtrade public preview API, no key) and SIPRI military spending.

Comtrade is queried once per reporter for total exports by partner. Imports are derived from
partners' reported exports (mirror data), which is labelled as such on the site.
"""

import csv
import io
from collections import defaultdict
from collections.abc import Iterable, Mapping

from geointel.risk.countries import universe_codes

TRADE_SOURCE = "UN Comtrade (public preview API), total goods exports by partner"
REPORTERS_URL = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
PARTNERS_URL = "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json"
DATA_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"

MILEX_SOURCE = "SIPRI Military Expenditure Database (via Our World in Data)"
MILEX_SLUGS = ("military-expenditure-share-gdp", "military-spending-as-a-share-of-gdp-sipri")


def data_params(reporter_code: int, year: int) -> dict[str, str]:
    return {
        "reporterCode": str(reporter_code),
        "period": str(year),
        "cmdCode": "TOTAL",
        "flowCode": "X",
        "partner2Code": "0",
        "customsCode": "C00",
        "motCode": "0",
    }


def reference_codes(payload: Mapping) -> dict[int, str]:
    """Comtrade numeric area code -> ISO3 for countries in our universe."""
    universe = universe_codes()
    result: dict[int, str] = {}
    for row in payload.get("results") or []:
        iso3 = str(
            row.get("reporterCodeIsoAlpha3") or row.get("PartnerCodeIsoAlpha3") or ""
        ).upper()
        code = row.get("reporterCode", row.get("PartnerCode", row.get("id")))
        try:
            numeric = int(code)
        except (TypeError, ValueError):
            continue
        if iso3 in universe and not row.get("isGroup"):
            result.setdefault(numeric, iso3)
    return result


def exports_by_partner(
    responses: Iterable[Mapping], codes: Mapping[int, str]
) -> dict[str, dict[str, float]]:
    """reporter ISO3 -> partner ISO3 -> exports in USD (plus 'WLD' total when reported)."""
    universe = universe_codes()
    result: dict[str, dict[str, float]] = defaultdict(dict)
    for response in responses:
        for row in response.get("data") or []:
            reporter = str(row.get("reporterISO") or "").upper()
            if reporter not in universe:
                reporter = codes.get(_int(row.get("reporterCode")), "")
            partner_code = _int(row.get("partnerCode"))
            partner = "WLD" if partner_code == 0 else str(row.get("partnerISO") or "").upper()
            if partner != "WLD" and partner not in universe:
                partner = codes.get(partner_code, "")
            value = row.get("primaryValue")
            if not reporter or not partner or partner == reporter or value is None:
                continue
            try:
                result[reporter][partner] = result[reporter].get(partner, 0.0) + float(value)
            except (TypeError, ValueError):
                continue
    return dict(result)


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1


def trade_links(exports: Mapping[str, Mapping[str, float]], top: int = 10) -> dict[str, dict]:
    """Per country: main export destinations and (mirror) import suppliers with shares."""
    imports: dict[str, dict[str, float]] = defaultdict(dict)
    for reporter, partners in exports.items():
        for partner, value in partners.items():
            if partner != "WLD":
                imports[partner][reporter] = value
    result: dict[str, dict] = {}
    for code in set(exports) | set(imports):
        entry: dict = {}
        partners = {k: v for k, v in exports.get(code, {}).items() if k != "WLD"}
        total = exports.get(code, {}).get("WLD") or sum(partners.values())
        if partners and total:
            entry["exports_usd"] = round(total)
            entry["exports_to"] = [
                {"iso3": k, "share": round(v / total, 4)}
                for k, v in sorted(partners.items(), key=lambda kv: -kv[1])[:top]
            ]
        suppliers = imports.get(code, {})
        total_in = sum(suppliers.values())
        if suppliers and total_in:
            entry["imports_usd_mirror"] = round(total_in)
            entry["imports_from"] = [
                {"iso3": k, "share": round(v / total_in, 4)}
                for k, v in sorted(suppliers.items(), key=lambda kv: -kv[1])[:top]
            ]
        if entry:
            result[code] = entry
    return result


def owid_series(text: str, years: int = 12) -> dict[str, list[tuple[int, float]]]:
    """Last ``years`` values per country from an OWID grapher CSV."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = [h.strip().lower() for h in rows[0]]
    try:
        code_i, year_i = header.index("code"), header.index("year")
    except ValueError:
        return {}
    value_i = next(i for i in range(len(header) - 1, -1, -1) if i not in (0, code_i, year_i))
    series: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in rows[1:]:
        try:
            code, year, value = row[code_i].upper(), int(row[year_i]), float(row[value_i])
        except (IndexError, ValueError):
            continue
        code = "XKX" if code == "OWID_KOS" else code
        if code in universe_codes():
            series[code].append((year, value))
    return {code: sorted(points)[-years:] for code, points in series.items()}


def milex_summary(series: Mapping[str, list[tuple[int, float]]]) -> dict[str, dict]:
    """Military spending as % of GDP: latest, change over 5 years, short series."""
    result: dict[str, dict] = {}
    for code, points in series.items():
        if not points:
            continue
        year, value = points[-1]
        base = next((v for y, v in points if y == year - 5), None)
        result[code] = {
            "value": round(value, 2),
            "year": year,
            "change5": round(value - base, 2) if base is not None else None,
            "series": [[y, round(v, 2)] for y, v in points],
        }
    return result
