"""Smithsonian Global Volcanism Program: Holocene volcanoes (names, location, last eruption).

Cite as: Global Volcanism Program, Smithsonian Institution, Volcanoes of the World database.
"""

from collections.abc import Mapping

from geointel.risk.countries import resolve_country_name

SOURCE = "Smithsonian Global Volcanism Program, Volcanoes of the World"
URL = (
    "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?service=WFS&version=2.0.0"
    "&request=GetFeature&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes"
    "&outputFormat=application/json"
)


def _year(value) -> int | None:
    text = str(value or "")
    digits = "".join(ch for ch in text if ch.isdigit() or ch == "-")
    try:
        return int(digits.split()[0]) if digits else None
    except ValueError:
        return None


def parse(payload: Mapping) -> list[dict]:
    """Volcanoes with a known eruption since 1900 or listed as such by GVP."""
    result = []
    for feature in payload.get("features") or []:
        props = {str(k).lower(): v for k, v in (feature.get("properties") or {}).items()}
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError, IndexError):
            continue
        country = resolve_country_name(str(props.get("country") or ""))
        last = _year(props.get("last_eruption_year"))
        result.append(
            {
                "name": str(props.get("volcano_name") or props.get("name") or ""),
                "country": country,
                "lat": lat,
                "lon": lon,
                "elevation": props.get("elevation"),
                "type": str(props.get("primary_volcano_type") or ""),
                "last_eruption": last,
            }
        )
    return result
