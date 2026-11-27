"""GeoNames cities with 15,000+ inhabitants (CC BY 4.0), used to estimate how the population
of a country is spread over its regions."""

import io
import zipfile

from geointel.risk.countries import universe

SOURCE = "GeoNames cities15000 (CC BY 4.0)"
URL = "https://download.geonames.org/export/dump/cities15000.zip"


def parse(payload: bytes) -> dict[str, list[tuple[float, float, int]]]:
    """ISO3 -> [(lat, lon, population)]."""
    if payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            name = next(n for n in archive.namelist() if n.endswith(".txt"))
            text = archive.read(name).decode("utf-8")
    else:
        text = payload.decode("utf-8")
    iso2_to_iso3 = {c.iso2: c.iso3 for c in universe()}
    result: dict[str, list[tuple[float, float, int]]] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 15:
            continue
        iso3 = iso2_to_iso3.get(parts[8].upper())
        try:
            lat, lon, pop = float(parts[4]), float(parts[5]), int(parts[14] or 0)
        except ValueError:
            continue
        if iso3 and pop > 0:
            result.setdefault(iso3, []).append((lat, lon, pop))
    return result
