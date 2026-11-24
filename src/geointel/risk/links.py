"""Links between countries (trade, displacement, migration routes) and migration indicators.

Borders and bloc memberships are added on the site from the map topology and the bloc list;
this module publishes the data-driven links as ``links.json``.
"""

from collections.abc import Mapping
from datetime import UTC, datetime

SCHEMA = "geointel-links-v1"

# Main irregular migration routes as named by Frontex and the US border agencies. Routes are
# qualitative links (no flows): they say where people move if pressure rises.
ROUTES: tuple[dict, ...] = (
    {
        "key": "central_med",
        "ru": "Центральное Средиземноморье",
        "en": "Central Mediterranean",
        "from": ["LBY", "TUN"],
        "to": ["ITA", "MLT"],
    },
    {
        "key": "western_med",
        "ru": "Западное Средиземноморье и Атлантика",
        "en": "Western Mediterranean and Atlantic",
        "from": ["MAR", "DZA", "MRT", "SEN", "GMB"],
        "to": ["ESP"],
    },
    {
        "key": "eastern_med",
        "ru": "Восточное Средиземноморье",
        "en": "Eastern Mediterranean",
        "from": ["TUR", "LBY"],
        "to": ["GRC", "CYP", "BGR"],
    },
    {
        "key": "western_balkans",
        "ru": "Западные Балканы",
        "en": "Western Balkans",
        "from": ["SRB", "BIH", "MKD", "ALB", "MNE"],
        "to": ["HRV", "HUN", "SVN", "AUT", "DEU"],
    },
    {
        "key": "eastern_land",
        "ru": "Восточная сухопутная граница ЕС",
        "en": "EU eastern land border",
        "from": ["BLR", "RUS"],
        "to": ["POL", "LTU", "LVA", "FIN", "EST"],
    },
    {
        "key": "channel",
        "ru": "Ла-Манш",
        "en": "English Channel",
        "from": ["FRA", "BEL"],
        "to": ["GBR"],
    },
    {
        "key": "secondary_eu",
        "ru": "Вторичные перемещения внутри Шенгена",
        "en": "Secondary movements within Schengen",
        "from": ["ITA", "GRC", "ESP"],
        "to": ["FRA", "DEU", "AUT", "BEL", "NLD"],
    },
    {
        "key": "us_southwest",
        "ru": "Юго-западная граница США",
        "en": "US southwest border",
        "from": ["MEX", "GTM", "HND", "SLV"],
        "to": ["USA"],
    },
    {
        "key": "darien",
        "ru": "Дарьенский пролом",
        "en": "Darién Gap",
        "from": ["COL", "VEN", "ECU"],
        "to": ["PAN", "CRI"],
    },
    {
        "key": "horn_yemen",
        "ru": "Восточный маршрут (Африканский Рог — Йемен — Саудовская Аравия)",
        "en": "Eastern route (Horn of Africa — Yemen — Saudi Arabia)",
        "from": ["ETH", "SOM", "DJI"],
        "to": ["YEM", "SAU"],
    },
)


def build_links(
    *,
    trade: Mapping[str, dict] | None,
    trade_year: int | None,
    displacement: Mapping[str, dict] | None,
    asylum: Mapping[str, dict] | None,
    profiles: Mapping[str, dict] | None = None,
    sources: list[dict] | None = None,
    generated_at: datetime | None = None,
) -> dict:
    profiles = profiles or {}
    countries: dict[str, dict] = {}

    def entry(code: str) -> dict:
        return countries.setdefault(code, {})

    for code, links in (trade or {}).items():
        entry(code)["trade"] = {**links, "year": trade_year}
    for code, data in (displacement or {}).items():
        migration = dict(data)
        population = (profiles.get(code) or {}).get("population", {}).get("value")
        if population and data.get("hosted"):
            migration["hosted_per_1000"] = round(data["hosted"] / population * 1000, 2)
        if population and data.get("abroad"):
            migration["abroad_per_1000"] = round(data["abroad"] / population * 1000, 2)
        entry(code)["migration"] = migration
    for code, trend in (asylum or {}).items():
        entry(code).setdefault("migration", {})["asylum_eu"] = trend
    return {
        "schema": SCHEMA,
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        "routes": list(ROUTES),
        "sources": sources or [],
        "countries": countries,
    }
