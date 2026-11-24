from functools import lru_cache

import pycountry
from sqlalchemy import and_, func, or_

from geointel.api.dashboard_schemas import Geography
from geointel.domain.models import Location
from geointel.geography import COUNTRIES

# Dashboard subregions for the repository's reviewed country cohort.
REGIONS = {
    "eastern-asia": ("TWN",),
    "southern-europe": ("ESP", "SRB"),
    "western-africa": ("NGA",),
    "western-asia": ("GEO",),
}
COUNTRY_REGIONS = {code: region for region, codes in REGIONS.items() for code in codes}
REVIEWED_NAMES = {country.name: (country.name, *country.aliases) for country in COUNTRIES}


@lru_cache(maxsize=512)
def iso3(value: str) -> str | None:
    code = value.strip().upper()
    if len(code) == 2:
        country = pycountry.countries.get(alpha_2=code)
    elif len(code) == 3:
        country = pycountry.countries.get(alpha_3=code)
    else:
        return None
    return country.alpha_3 if country else None


def country_names(code: str) -> tuple[str, ...]:
    country = pycountry.countries.get(alpha_3=code)
    name = "Taiwan" if code == "TWN" else country.name
    return (
        *REVIEWED_NAMES.get(name, (name,)),
        country.name,
        getattr(country, "official_name", country.name),
        getattr(country, "common_name", country.name),
    )


def normalized(column):
    return func.lower(func.trim(column))


def source_country_matches(column, code: str):
    alpha2 = pycountry.countries.get(alpha_3=code).alpha_2
    return normalized(column).in_(
        sorted({code.lower(), alpha2.lower(), *(name.lower() for name in country_names(code))})
    )


def analysis_country_matches(code: str):
    alpha2 = pycountry.countries.get(alpha_3=code).alpha_2
    return or_(
        normalized(Location.iso_code).in_((alpha2.lower(), code.lower())),
        and_(
            or_(Location.iso_code.is_(None), func.trim(Location.iso_code) == ""),
            source_country_matches(Location.name, code),
        ),
    )


@lru_cache(maxsize=1)
def country_name_codes() -> dict[str, str | None]:
    names: dict[str, str | None] = {}
    for country in pycountry.countries:
        for name in country_names(country.alpha_3):
            key = name.lower()
            if key in names and names[key] != country.alpha_3:
                names[key] = None
            else:
                names[key] = country.alpha_3
    return names


def name_to_iso3(name: str) -> str | None:
    return iso3(name) or country_name_codes().get(name.strip().lower())


REVIEWED_GW_COUNTRIES = {country.gw_code: country.name for country in COUNTRIES}
REVIEWED_ISO_GW = {name_to_iso3(name): code for code, name in REVIEWED_GW_COUNTRIES.items()}


def geography(name: str | None, stored_code: str | None, unit: str | None) -> Geography:
    code = None
    if unit == "country" and name:
        code = iso3(stored_code) if stored_code and stored_code.strip() else name_to_iso3(name)
    return Geography(
        name=name,
        iso3=code,
        region=COUNTRY_REGIONS.get(code) if code else None,
        unit=unit if code or unit != "country" else None,
    )
