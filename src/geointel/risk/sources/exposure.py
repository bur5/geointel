"""World Bank WDI structural exposure indicators (latest available value per country)."""

from collections.abc import Mapping

from geointel.risk.countries import universe_codes

SOURCE = "World Bank World Development Indicators (structure of the economy)"
INDICATORS = {
    "gdp_usd": "NY.GDP.MKTP.CD",
    "population": "SP.POP.TOTL",
    "oil_rents_gdp": "NY.GDP.PETR.RT.ZS",
    "gas_rents_gdp": "NY.GDP.NGAS.RT.ZS",
    "fuel_exports_share": "TX.VAL.FUEL.ZS.UN",
    "food_exports_share": "TX.VAL.FOOD.ZS.UN",
    "fuel_imports_share": "TM.VAL.FUEL.ZS.UN",
    "food_imports_share": "TM.VAL.FOOD.ZS.UN",
    "trade_gdp": "NE.TRD.GNFS.ZS",
    "tourism_exports_share": "ST.INT.RCPT.XP.ZS",
    "remittances_gdp": "BX.TRF.PWKR.DT.GD.ZS",
}


def url(indicator: str, end_year: int) -> str:
    return (
        f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
        f"?format=json&per_page=20000&date={end_year - 8}:{end_year}"
    )


def latest(payloads: Mapping[str, object]) -> dict[str, dict]:
    """Latest non-null value per country and indicator, with its year."""
    profiles: dict[str, dict] = {}
    for name, code in INDICATORS.items():
        payload = payloads.get(code)
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        best: dict[str, tuple[int, float]] = {}
        for row in rows or []:
            iso3 = str(row.get("countryiso3code") or "").upper()
            if iso3 not in universe_codes() or row.get("value") is None:
                continue
            try:
                year, value = int(row["date"]), float(row["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if iso3 not in best or year > best[iso3][0]:
                best[iso3] = (year, value)
        for iso3, (year, value) in best.items():
            profiles.setdefault(iso3, {})[name] = {"value": round(value, 3), "year": year}
    world_gdp = sum(p["gdp_usd"]["value"] for p in profiles.values() if "gdp_usd" in p)
    for profile in profiles.values():
        if "gdp_usd" in profile and world_gdp:
            profile["world_gdp_share"] = {
                "value": round(profile["gdp_usd"]["value"] / world_gdp * 100, 3),
                "year": profile["gdp_usd"]["year"],
            }
    return profiles
