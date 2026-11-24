"""Upcoming national elections and referendums from Wikidata (CC0)."""

import re
from datetime import date

from geointel.risk.countries import universe_codes

SOURCE = "Wikidata — national elections and referendums"
ENDPOINT = "https://query.wikidata.org/sparql"
COUNTRY_QUERY = """
SELECT ?country ?iso3 WHERE { ?country wdt:P298 ?iso3 . ?country wdt:P31 wd:Q6256 . }
"""
BATCH_QUERY = """
SELECT ?e ?eLabelEn ?eLabelRu ?date ?precision ?iso3 ?typeLabel WHERE {
  VALUES (?country ?iso3) { %s }
  ?e wdt:P17 ?country .
  ?e p:P585/psv:P585 [ wikibase:timeValue ?date ; wikibase:timePrecision ?precision ] .
  FILTER(?date >= NOW() - "P45D"^^xsd:duration && ?date <= NOW() + "P400D"^^xsd:duration)
  ?e wdt:P31 ?type .
  ?type rdfs:label ?typeLabel FILTER(LANG(?typeLabel) = "en")
  FILTER(CONTAINS(LCASE(?typeLabel), "election") || CONTAINS(LCASE(?typeLabel), "referendum"))
  OPTIONAL { ?e rdfs:label ?eLabelEn FILTER(LANG(?eLabelEn) = "en") }
  OPTIONAL { ?e rdfs:label ?eLabelRu FILTER(LANG(?eLabelRu) = "ru") }
}
"""


def batch_values(pairs: list[tuple[str, str]]) -> str:
    return " ".join(f'(wd:{qid} "{iso3}")' for qid, iso3 in pairs)


QUERY = """
SELECT ?e ?eLabelEn ?eLabelRu ?date ?precision ?iso3 ?typeLabel WHERE {
  ?e wdt:P31 ?type .
  ?type wdt:P279* wd:Q40231 .
  ?e p:P585/psv:P585 [ wikibase:timeValue ?date ; wikibase:timePrecision ?precision ] .
  FILTER(?date >= NOW() - "P45D"^^xsd:duration && ?date <= NOW() + "P400D"^^xsd:duration)
  ?e wdt:P17 ?country .
  ?country wdt:P298 ?iso3 .
  OPTIONAL { ?e rdfs:label ?eLabelEn FILTER(LANG(?eLabelEn) = "en") }
  OPTIONAL { ?e rdfs:label ?eLabelRu FILTER(LANG(?eLabelRu) = "ru") }
  ?type rdfs:label ?typeLabel FILTER(LANG(?typeLabel) = "en")
}
LIMIT 5000
"""
_NATIONAL = re.compile(r"presidential|general|parliamentary|legislative|referendum|national")
_LOCAL = re.compile(
    r"local|municipal|mayor|regional|state |gubernatorial|provincial|primary|by-election|"
    r"county|city|council|district|party|leadership|caucus|senate|recall"
)


def kind(type_label: str, name: str) -> str | None:
    text = f"{type_label} {name}".lower()
    if _LOCAL.search(text) or not _NATIONAL.search(text):
        return None
    if "referendum" in text:
        return "referendum"
    if "presidential" in text:
        return "presidential"
    return "parliamentary"


def parse(payload: dict, today: date | None = None) -> dict[str, list[dict]]:
    today = today or date.today()
    result: dict[str, dict[str, dict]] = {}
    for b in (payload.get("results") or {}).get("bindings") or []:
        iso3 = b.get("iso3", {}).get("value", "").upper()
        if iso3 not in universe_codes():
            continue
        name_en = b.get("eLabelEn", {}).get("value", "")
        election_kind = kind(b.get("typeLabel", {}).get("value", ""), name_en)
        if not election_kind:
            continue
        raw = b.get("date", {}).get("value", "")[:10]
        precision = int(b.get("precision", {}).get("value", 11))
        entity = b.get("e", {}).get("value", "").rsplit("/", 1)[-1]
        result.setdefault(iso3, {})[entity] = {
            "date": raw,
            "precision": "day" if precision >= 11 else "month" if precision == 10 else "year",
            "kind": election_kind,
            "name_en": name_en,
            "name_ru": b.get("eLabelRu", {}).get("value") or None,
            "wikidata": entity,
        }
    return {
        iso3: sorted(items.values(), key=lambda item: item["date"])
        for iso3, items in result.items()
    }
