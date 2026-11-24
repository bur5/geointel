"""UN OCHA Financial Tracking Service: country humanitarian response plans by year."""

from collections import defaultdict
from collections.abc import Mapping

from geointel.risk.countries import universe_codes
from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType

SOURCE = "UN OCHA Financial Tracking Service (humanitarian response plans)"
START_YEAR = 2000


def url(year: int) -> str:
    return f"https://api.hpc.tools/v1/public/plan/year/{year}"


def country_plans(year_payloads: Mapping[int, object]) -> dict[str, set[int]]:
    """Years with a plan covering exactly one country (regional plans are excluded)."""
    result: dict[str, set[int]] = defaultdict(set)
    for year, payload in year_payloads.items():
        plans = payload.get("data", []) if isinstance(payload, dict) else []
        for plan in plans or []:
            locations = [
                loc
                for loc in plan.get("locations") or []
                if loc.get("adminLevel", 0) in (0, None) and loc.get("iso3")
            ]
            codes = {str(loc["iso3"]).upper() for loc in locations}
            if len(codes) != 1:
                continue
            code = codes.pop()
            if code in universe_codes():
                result[code].add(int(year))
    return result


def history(year_payloads: Mapping[int, object]) -> TypeHistory:
    years = sorted(year_payloads)
    data = country_plans(year_payloads)
    return TypeHistory(
        event_type=EventType.HUMANITARIAN_CRISIS,
        source=SOURCE,
        start_year=years[0] if years else START_YEAR,
        end_year=years[-1] if years else START_YEAR,
        years_with_event={k: frozenset(v) for k, v in data.items()},
        half_life_years=10.0,
        records=sum(len(v) for v in data.values()),
    )
