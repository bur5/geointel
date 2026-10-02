"""Bounded provider and news geography identities; never a sovereignty assertion."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CountryIdentity:
    name: str
    gw_code: int
    aliases: tuple[str, ...] = ()
    subnational_entities: tuple[str, ...] = ()


# Reviewed Gleditsch-Ward codes from the UCDP API country code list/codebook.
# Aliases express provider identity only, not political equivalence or sovereignty.
COUNTRIES = (
    CountryIdentity("Spain", 230, ("Kingdom of Spain",), ("Catalonia", "Tarragona")),
    CountryIdentity("Georgia", 372),
    CountryIdentity("Taiwan", 713),
    CountryIdentity("Serbia", 340, ("Republic of Serbia",)),
    CountryIdentity("Nigeria", 475, ("Federal Republic of Nigeria",)),
)


def resolve_country(value: str) -> CountryIdentity:
    normalized = " ".join(value.casefold().split())
    matches = [
        country
        for country in COUNTRIES
        if normalized in {country.name.casefold(), *(alias.casefold() for alias in country.aliases)}
    ]
    if len(matches) != 1:
        raise ValueError("geography is unknown or ambiguous in the reviewed country mapping")
    return matches[0]


def matched_subnational_entities(text: str, country: CountryIdentity) -> list[str]:
    folded = text.casefold()
    return sorted(entity for entity in country.subnational_entities if entity.casefold() in folded)
