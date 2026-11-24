"""Country universe and dataset-name resolution for the global risk snapshot.

The universe is the 193 UN member states plus Kosovo, Palestine and Taiwan. Names are
identifiers for data matching only; they make no sovereignty claim.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

import pycountry

UN_MEMBERS = (
    "AFG ALB DZA AND AGO ATG ARG ARM AUS AUT AZE BHS BHR BGD BRB BLR BEL BLZ BEN BTN BOL BIH "
    "BWA BRA BRN BGR BFA BDI CPV KHM CMR CAN CAF TCD CHL CHN COL COM COG CRI CIV HRV CUB CYP "
    "CZE PRK COD DNK DJI DMA DOM ECU EGY SLV GNQ ERI EST SWZ ETH FJI FIN FRA GAB GMB GEO DEU "
    "GHA GRC GRD GTM GIN GNB GUY HTI HND HUN ISL IND IDN IRN IRQ IRL ISR ITA JAM JPN JOR KAZ "
    "KEN KIR KWT KGZ LAO LVA LBN LSO LBR LBY LIE LTU LUX MDG MWI MYS MDV MLI MLT MHL MRT MUS "
    "MEX FSM MCO MNG MNE MAR MOZ MMR NAM NRU NPL NLD NZL NIC NER NGA MKD NOR OMN PAK PLW PAN "
    "PNG PRY PER PHL POL PRT QAT KOR MDA ROU RUS RWA KNA LCA VCT WSM SMR STP SAU SEN SRB SYC "
    "SLE SGP SVK SVN SLB SOM ZAF SSD ESP LKA SDN SUR SWE CHE SYR TJK THA TLS TGO TON TTO TUN "
    "TUR TKM TUV UGA UKR ARE GBR TZA USA URY UZB VUT VEN VNM YEM ZMB ZWE"
).split()
OBSERVERS_AND_OTHERS = ("PSE", "TWN", "XKX")

# First full calendar year of independent statehood for states created after 1989.
# Earlier years are not counted as exposure for these countries.
FIRST_YEAR = {
    "NAM": 1990,
    **dict.fromkeys(
        "ARM AZE BLR EST GEO KAZ KGZ LVA LTU MDA TJK TKM UKR UZB SVN HRV".split(), 1992
    ),
    "MKD": 1992,
    "BIH": 1992,
    "ERI": 1993,
    "CZE": 1993,
    "SVK": 1993,
    "PLW": 1995,
    "TLS": 2002,
    "MNE": 2006,
    "XKX": 2008,
    "SSD": 2011,
}

_SPECIAL_NAMES = {"XKX": ("XK", "Kosovo"), "TWN": ("TW", "Taiwan"), "PSE": ("PS", "Palestine")}

_ALIASES = {
    "russia": "RUS",
    "soviet union": "RUS",
    "ussr": "RUS",
    "dr congo": "COD",
    "democratic republic of congo": "COD",
    "democratic republic of the congo": "COD",
    "congo, democratic republic of the": "COD",
    "congo, dem. rep.": "COD",
    "congo-kinshasa": "COD",
    "zaire": "COD",
    "congo": "COG",
    "republic of congo": "COG",
    "republic of the congo": "COG",
    "congo-brazzaville": "COG",
    "congo, rep.": "COG",
    "ivory coast": "CIV",
    "cote d'ivoire": "CIV",
    "cote divoire": "CIV",
    "bosnia-herzegovina": "BIH",
    "bosnia": "BIH",
    "yugoslavia": "SRB",
    "serbia and montenegro": "SRB",
    "macedonia": "MKD",
    "fyr macedonia": "MKD",
    "burma": "MMR",
    "kampuchea": "KHM",
    "laos": "LAO",
    "vietnam": "VNM",
    "north vietnam": "VNM",
    "south vietnam": "VNM",
    "north korea": "PRK",
    "korea, north": "PRK",
    "south korea": "KOR",
    "korea, south": "KOR",
    "korea": "KOR",
    "iran": "IRN",
    "syria": "SYR",
    "bolivia": "BOL",
    "venezuela": "VEN",
    "tanzania": "TZA",
    "zanzibar": "TZA",
    "moldova": "MDA",
    "united states": "USA",
    "united states of america": "USA",
    "usa": "USA",
    "united kingdom": "GBR",
    "uk": "GBR",
    "great britain": "GBR",
    "turkey": "TUR",
    "turkiye": "TUR",
    "czech republic": "CZE",
    "czechia": "CZE",
    "czechoslovakia": "CZE",
    "east timor": "TLS",
    "timor leste": "TLS",
    "swaziland": "SWZ",
    "cape verde": "CPV",
    "gambia": "GMB",
    "the gambia": "GMB",
    "north yemen": "YEM",
    "south yemen": "YEM",
    "rhodesia": "ZWE",
    "malagasy": "MDG",
    "upper volta": "BFA",
    "dahomey": "BEN",
    "brunei": "BRN",
    "micronesia": "FSM",
    "palestine": "PSE",
    "palestinian territories": "PSE",
    "west bank": "PSE",
    "gaza": "PSE",
    "taiwan": "TWN",
    "kosovo": "XKX",
    "west germany": "DEU",
    "german federal republic": "DEU",
    "germany": "DEU",
    "st. kitts and nevis": "KNA",
    "st. lucia": "LCA",
    "st. vincent and the grenadines": "VCT",
    "sao tome and principe": "STP",
    "guinea bissau": "GNB",
    "trinidad": "TTO",
    "uae": "ARE",
    "netherlands": "NLD",
    "the netherlands": "NLD",
}

_US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia (us)", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
    "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire",
    "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia",
    "wisconsin", "wyoming", "ca", "ak", "hi", "nv", "wa", "or", "mt", "id", "wy", "ut", "az",
    "nm",
}  # fmt: skip


@dataclass(frozen=True)
class Country:
    iso3: str
    iso2: str
    name: str
    first_year: int | None


@lru_cache(maxsize=1)
def universe() -> tuple[Country, ...]:
    result = []
    for iso3 in (*UN_MEMBERS, *OBSERVERS_AND_OTHERS):
        if iso3 in _SPECIAL_NAMES:
            iso2, name = _SPECIAL_NAMES[iso3]
        else:
            record = pycountry.countries.get(alpha_3=iso3)
            if record is None:
                raise ValueError(f"unknown ISO alpha-3 code in universe: {iso3}")
            iso2 = record.alpha_2
            name = getattr(record, "common_name", None) or record.name
        result.append(Country(iso3, iso2, name, FIRST_YEAR.get(iso3)))
    return tuple(sorted(result, key=lambda country: country.iso3))


@lru_cache(maxsize=1)
def universe_codes() -> frozenset[str]:
    return frozenset(country.iso3 for country in universe())


def _normalize(name: str) -> str:
    text = name.strip().casefold()
    text = re.sub(r"\(.*?\)", " ", text)
    text = re.sub(r"^government of\s+", "", text.strip())
    text = text.replace("’", "'").replace("ô", "o").replace("ü", "u").replace("é", "e")
    text = re.sub(r"\s+", " ", text).strip(" .,")
    return text


@lru_cache(maxsize=4096)
def resolve_country_name(name: str) -> str | None:
    """Map a dataset country label to an ISO alpha-3 code in the universe, else None."""
    text = _normalize(name)
    if not text:
        return None
    code = _ALIASES.get(text)
    if code is None:
        try:
            code = pycountry.countries.lookup(text).alpha_3
        except LookupError:
            code = None
    return code if code in universe_codes() else None


def resolve_usgs_place(place: str) -> str | None:
    """Resolve the country named in a USGS place label such as '10 km SW of X, Japan'."""
    if not place:
        return None
    tail = place.rsplit(",", 1)[-1] if "," in place else place
    tail = re.sub(r"\bregion\b", "", tail, flags=re.IGNORECASE).strip()
    folded = tail.casefold()
    if folded in _US_STATES:
        return "USA"
    code = resolve_country_name(tail)
    if code is None and "," not in place:
        code = _contained_country(place)
    return code


@lru_cache(maxsize=1)
def _name_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    names = {country.name.casefold(): country.iso3 for country in universe()}
    names.update({alias: code for alias, code in _ALIASES.items() if len(alias) > 3})
    ordered = sorted(names.items(), key=lambda item: -len(item[0]))
    return tuple((re.compile(rf"\b{re.escape(name)}\b"), code) for name, code in ordered)


def _contained_country(text: str) -> str | None:
    """Flinn-Engdahl style labels such as 'near the coast of Ecuador'."""
    folded = text.casefold()
    for pattern, code in _name_patterns():
        if pattern.search(folded):
            return code
    return None
