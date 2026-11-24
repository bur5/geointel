"""World Bank WDI: economic crisis years (GDP contraction or very high inflation)."""

from collections import defaultdict

from geointel.risk.countries import universe_codes
from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType

SOURCE = "World Bank World Development Indicators"
GDP_GROWTH = "NY.GDP.MKTP.KD.ZG"
INFLATION = "FP.CPI.TOTL.ZG"
START_YEAR = 1990
GDP_THRESHOLD = -3.0
INFLATION_THRESHOLD = 40.0


def url(indicator: str, end_year: int) -> str:
    return (
        f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
        f"?format=json&per_page=20000&date={START_YEAR}:{end_year}"
    )


def _rows(payload) -> list[dict]:
    if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list):
        return payload[1]
    return []


def values(payload) -> dict[tuple[str, int], float]:
    result = {}
    for row in _rows(payload):
        code = str(row.get("countryiso3code") or "").upper()
        if code == "XKX" or code in universe_codes():
            try:
                result[(code, int(row["date"]))] = float(row["value"])
            except (KeyError, TypeError, ValueError):
                continue
    return result


def history(gdp_payload, inflation_payload) -> TypeHistory:
    gdp = values(gdp_payload)
    inflation = values(inflation_payload)
    observed: dict[str, set[int]] = defaultdict(set)
    crises: dict[str, set[int]] = defaultdict(set)
    for (code, year), growth in gdp.items():
        observed[code].add(year)
        if growth < GDP_THRESHOLD:
            crises[code].add(year)
    for (code, year), rate in inflation.items():
        observed[code].add(year)
        if rate > INFLATION_THRESHOLD:
            crises[code].add(year)
    # Last year with broad coverage (data for at least 100 countries).
    per_year: dict[int, int] = defaultdict(int)
    for years in observed.values():
        for year in years:
            per_year[year] += 1
    covered = [year for year, count in per_year.items() if count >= 100]
    end_year = max(covered) if covered else START_YEAR
    return TypeHistory(
        event_type=EventType.ECONOMIC_CRISIS,
        source=SOURCE,
        start_year=START_YEAR,
        end_year=end_year,
        years_with_event={k: frozenset(v) for k, v in crises.items()},
        half_life_years=15.0,
        records=len(gdp) + len(inflation),
        observed_years={k: frozenset(y for y in v if y <= end_year) for k, v in observed.items()},
        metadata={"gdp_threshold": GDP_THRESHOLD, "inflation_threshold": INFLATION_THRESHOLD},
    )
