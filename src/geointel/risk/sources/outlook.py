"""Forward-looking and structural indicators: IMF WEO projections, V-Dem (via OWID), GPR."""

import csv
import io
from collections.abc import Iterable, Mapping

from geointel.risk.countries import resolve_country_name, universe_codes

IMF_SOURCE = "IMF World Economic Outlook (DataMapper)"
IMF_INDICATORS = {"growth": "NGDP_RPCH", "inflation": "PCPIPCH", "debt": "GGXWDG_NGDP"}
VDEM_SOURCE = "V-Dem electoral democracy index (via Our World in Data)"
VDEM_SLUGS = ("electoral-democracy-index", "liberal-democracy-index")
GPR_SOURCE = "Caldara & Iacoviello Geopolitical Risk Index (country-specific)"
GPR_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls"


def imf_url(indicator: str) -> str:
    return f"https://www.imf.org/external/datamapper/api/v1/{indicator}"


def owid_url(slug: str) -> str:
    return (
        f"https://ourworldindata.org/grapher/{slug}.csv?v=1&csvType=full&useColumnShortNames=true"
    )


def imf_outlook(payloads: Mapping[str, object], reference_year: int) -> dict[str, dict]:
    """IMF values for last year, this year and next year (projections flagged by year)."""
    result: dict[str, dict] = {}
    years = [reference_year - 1, reference_year, reference_year + 1]
    for name, code in IMF_INDICATORS.items():
        payload = payloads.get(code) or {}
        series = (payload.get("values") or {}).get(code) or {} if isinstance(payload, dict) else {}
        for iso3, values in series.items():
            if iso3 not in universe_codes() or not isinstance(values, dict):
                continue
            entry = {str(y): values.get(str(y)) for y in years if values.get(str(y)) is not None}
            if entry:
                result.setdefault(iso3, {})[name] = entry
    for entry in result.values():
        projected = [
            year
            for year in (str(reference_year), str(reference_year + 1))
            if (entry.get("growth", {}).get(year) is not None and entry["growth"][year] < -3)
            or (entry.get("inflation", {}).get(year) is not None and entry["inflation"][year] > 40)
        ]
        entry["projects_crisis"] = projected
    return result


def owid_latest(text: str) -> dict[str, dict]:
    """Latest value per country from an OWID grapher CSV (Entity, Code, Year, value)."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = [h.strip().lower() for h in rows[0]]
    try:
        code_i, year_i = header.index("code"), header.index("year")
    except ValueError:
        return {}
    value_i = next(i for i in range(len(header) - 1, -1, -1) if i not in (0, code_i, year_i))
    best: dict[str, tuple[int, float]] = {}
    for row in rows[1:]:
        try:
            code, year, value = row[code_i].upper(), int(row[year_i]), float(row[value_i])
        except (IndexError, ValueError):
            continue
        code = "XKX" if code == "OWID_KOS" else code
        if code in universe_codes() and (code not in best or year > best[code][0]):
            best[code] = (year, value)
    return {code: {"value": round(v, 3), "year": y} for code, (y, v) in best.items()}


def gpr_country_series(columns: Mapping[str, list], months: list[str]) -> dict[str, dict]:
    """Country GPR columns (GPRC_XXX) -> latest value, 5-year mean and last 24 months."""
    result: dict[str, dict] = {}
    for column, values in columns.items():
        if not column.upper().startswith("GPRC_"):
            continue
        code = column.upper()[5:]
        if code not in universe_codes():
            code = resolve_country_name(code) or code
        if code not in universe_codes():
            continue
        points = [
            (month, float(v))
            for month, v in zip(months, values, strict=False)
            if isinstance(v, int | float) and v == v
        ]
        if len(points) < 24:
            continue
        recent = points[-24:]
        baseline = [v for _, v in points[-72:-12]] or [v for _, v in points]
        mean = sum(baseline) / len(baseline)
        last12 = [v for _, v in points[-12:]]
        result[code] = {
            "latest_month": recent[-1][0],
            "latest": round(recent[-1][1], 3),
            "baseline_mean": round(mean, 3),
            "ratio_12m": round((sum(last12) / len(last12)) / mean, 3) if mean else None,
            "months": [m for m, _ in recent],
            "values": [round(v, 3) for _, v in recent],
        }
    return result


def read_gpr_xls(payload: bytes) -> tuple[dict[str, list], list[str]]:
    """Read the GPR Excel export (requires xlrd)."""
    import xlrd

    book = xlrd.open_workbook(file_contents=payload)
    sheet = book.sheet_by_index(0)
    header = [str(c.value).strip() for c in sheet.row(0)]
    month_i = next((i for i, h in enumerate(header) if h.lower() == "month"), None)
    if month_i is None:
        month_i = next(i for i, h in enumerate(header) if h.lower() in ("date", "yearmonth"))
    months: list[str] = []
    columns: dict[str, list] = {h: [] for h in header}
    for r in range(1, sheet.nrows):
        row = sheet.row(r)
        cell = row[month_i]
        try:
            y, m, *_ = xlrd.xldate_as_tuple(cell.value, book.datemode)
            months.append(f"{y:04d}-{m:02d}")
        except Exception:  # noqa: BLE001 - non-date or ambiguous cells
            months.append(str(cell.value)[:7])
        for i, h in enumerate(header):
            value = row[i].value if i < len(row) else None
            columns[h].append(value if isinstance(value, int | float) else None)
    return columns, months


def merge(*parts: Iterable[tuple[str, Mapping[str, object]]]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for group in parts:
        for key, data in group:
            for iso3, value in data.items():
                merged.setdefault(iso3, {})[key] = value
    return merged
