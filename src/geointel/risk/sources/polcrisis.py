"""History of political crises 2000–2025 (see docs/polcrisis-history.md)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

WIKIDATA = "https://query.wikidata.org/sparql"
USER_AGENT = "GeoIntel/1.0 (https://github.com/bur5/geointel; political crisis history)"
ARCHIGOS_URL = "https://www.rochester.edu/college/faculty/hgoemans/Archigos_4.1_stata14.dta"
NELDA_URL = "https://raw.githubusercontent.com/xmarquez/PoliticalDatasets/master/data/nelda.rda"
REIGN_LEADERS_URL = (
    "https://raw.githubusercontent.com/OEFdataScience/REIGN.github.io/gh-pages/"
    "data_sets/leader_list_8_21.csv"
)

COUNTRIES_QUERY = """
SELECT ?c ?iso3 ?type ?dissolved WHERE {
  VALUES ?iso3 { %s }
  ?c wdt:P298 ?iso3 .
  OPTIONAL { ?c wdt:P31 ?type . VALUES ?type { wd:Q3624078 wd:Q6256 } }
  OPTIONAL { ?c wdt:P576 ?dissolved }
}
"""
OFFICES_QUERY = """
SELECT ?c ?role ?office ?officeLabel WHERE {
  VALUES ?c { %s }
  { ?c wdt:P1906 ?office . BIND("head_of_state" AS ?role) }
  UNION { ?c wdt:P1313 ?office . BIND("head_of_government" AS ?role) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""
HOLDERS_QUERY = """
SELECT ?office ?st ?p ?pLabel ?start ?end ?endPrecision ?cause ?causeLabel ?nature ?natureLabel WHERE {
  VALUES ?office { %s }
  ?p p:P39 ?st . ?st ps:P39 ?office .
  ?st wikibase:rank ?rank . FILTER(?rank != wikibase:DeprecatedRank)
  OPTIONAL { ?st pq:P580 ?start }
  OPTIONAL { ?st pqv:P582 [ wikibase:timeValue ?end ; wikibase:timePrecision ?endPrecision ] }
  OPTIONAL { ?st pq:P1534 ?cause }
  OPTIONAL { ?st pq:P5102 ?nature }
  FILTER(!BOUND(?end) || ?end >= "1985-01-01T00:00:00Z"^^xsd:dateTime)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""
ELECTION_TYPES_QUERY = """
SELECT ?type ?typeLabel ?snap WHERE {
  ?type wdt:P279* wd:Q40231 .
  BIND(EXISTS { ?type wdt:P279* wd:Q1333366 } AS ?snap)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""
ELECTIONS_QUERY = """
SELECT ?c ?e ?eLabel ?date ?precision ?type WHERE {
  VALUES ?type { %s }
  ?e wdt:P31 ?type ; wdt:P17 ?c .
  ?e p:P585/psv:P585 [ wikibase:timeValue ?date ; wikibase:timePrecision ?precision ] .
  FILTER(?date >= "1975-01-01T00:00:00Z"^^xsd:dateTime
         && ?date < "2026-07-01T00:00:00Z"^^xsd:dateTime)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""
EMERGENCY_QUERY = """
SELECT ?e ?eLabel ?eDescription ?c ?start ?point ?cls ?clsLabel WHERE {
  VALUES ?cls { %s }
  ?e wdt:P31 ?cls .
  ?e wdt:P17 ?c .
  OPTIONAL { ?e wdt:P580 ?start }
  OPTIONAL { ?e wdt:P585 ?point }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""
EMERGENCY_CLASSES_QUERY = """
SELECT DISTINCT ?cls WHERE {
  VALUES ?label { "state of emergency"@en "martial law"@en "state of siege"@en
                  "state of exception"@en "national emergency"@en }
  ?root rdfs:label ?label .
  ?cls wdt:P279* ?root .
}
"""


# ---------------------------------------------------------------- network (CI only)


def _sparql(client, query: str, attempts: int = 4) -> list[dict]:
    for attempt in range(attempts):
        try:
            response = client.post(
                WIKIDATA,
                data={"query": query, "format": "json"},
                headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
                timeout=180,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise RuntimeError(f"status {response.status_code}")
            response.raise_for_status()
            return response.json()["results"]["bindings"]
        except Exception as exc:  # noqa: BLE001 - retry, then give up loudly
            print(f"[wikidata] attempt {attempt + 1} failed: {type(exc).__name__}: {exc}")
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("Wikidata query failed")


def _value(binding: dict, key: str) -> str:
    return (binding.get(key) or {}).get("value", "")


def _qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _batches(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch(work: Path) -> None:
    """Download every raw input into ``work`` (run in GitHub Actions)."""
    import httpx

    from geointel.risk.countries import universe_codes
    from geointel.risk.sources import coups

    work.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(follow_redirects=True)
    codes = sorted(universe_codes())
    countries = _sparql(client, COUNTRIES_QUERY % " ".join(f'"{c}"' for c in codes))
    (work / "wd_countries.json").write_text(json.dumps(countries))
    qids = sorted({"wd:" + _qid(_value(b, "c")) for b in pick_countries(countries).values()})
    offices: list[dict] = []
    for batch in _batches(qids, 60):
        offices += _sparql(client, OFFICES_QUERY % " ".join(batch))
    (work / "wd_offices.json").write_text(json.dumps(offices))
    office_ids = sorted({"wd:" + _qid(_value(b, "office")) for b in offices})
    holders: list[dict] = []
    for batch in _batches(office_ids, 25):
        holders += _sparql(client, HOLDERS_QUERY % " ".join(batch))
        time.sleep(1)
    (work / "wd_holders.json").write_text(json.dumps(holders))
    types = _sparql(client, ELECTION_TYPES_QUERY)
    (work / "wd_election_types.json").write_text(json.dumps(types))
    wanted = sorted(
        {"wd:" + _qid(_value(b, "type")) for b in types if election_type_kind(b) is not None}
    )
    print(f"[wikidata] election types: {len(types)}, national: {len(wanted)}")
    elections: list[dict] = []
    for batch in _batches(wanted, 150):
        elections += _sparql(client, ELECTIONS_QUERY % " ".join(batch))
        time.sleep(1)
    (work / "wd_elections.json").write_text(json.dumps(elections))
    emergencies: list[dict] = []
    try:
        classes = _sparql(client, EMERGENCY_CLASSES_QUERY)
        cls_ids = sorted({"wd:" + _qid(_value(b, "cls")) for b in classes})
        for batch in _batches(cls_ids, 40):
            emergencies += _sparql(client, EMERGENCY_QUERY % " ".join(batch))
    except RuntimeError as exc:
        print(f"[wikidata] emergencies skipped: {exc}")
    (work / "wd_emergencies.json").write_text(json.dumps(emergencies))
    print(
        f"[wikidata] countries={len(countries)} offices={len(offices)} holders={len(holders)} "
        f"elections={len(elections)} emergencies={len(emergencies)}"
    )
    browser = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) GeoIntel"}
    downloads = [(link, "cline_coups.csv") for link in coups.CLINE_FILES] + [
        (ARCHIGOS_URL, "archigos.dta"),
        (NELDA_URL, "nelda.rda"),
        (REIGN_LEADERS_URL, "reign_leaders.csv"),
    ]
    for url, name in downloads:
        if (work / name).exists():
            continue
        try:
            response = client.get(url, headers=browser, timeout=120)
            response.raise_for_status()
            (work / name).write_bytes(response.content)
            print(f"[download] {name}: {len(response.content)} bytes from {url}")
        except Exception as exc:  # noqa: BLE001 - reference sets are optional
            print(f"[download] {url} failed: {type(exc).__name__}: {str(exc)[:160]}")


# ---------------------------------------------------------------- pure parsing


def pick_countries(bindings: list[dict]) -> dict[str, dict]:
    """One Wikidata item per ISO3 code: prefer a current sovereign state / country."""
    best: dict[str, tuple[int, dict]] = {}
    for b in bindings:
        iso3 = _value(b, "iso3").upper()
        score = (2 if _value(b, "type") else 0) + (0 if _value(b, "dissolved") else 1)
        if iso3 not in best or score > best[iso3][0]:
            best[iso3] = (score, b)
    return {iso3: b for iso3, (_score, b) in best.items()}


def election_type_kind(binding: dict) -> str | None:
    """'presidential' / 'parliamentary' for national election classes, else None."""
    from geointel.risk.sources.elections import kind

    label = _value(binding, "typeLabel")
    if _value(binding, "snap") in ("true", "1") and "local" not in label.lower():
        return "snap"
    result = kind(label, "")
    return None if result == "referendum" else result


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "fetch":
        fetch(Path(argv[1]))
        return 0
    print("usage: python -m geointel.risk.sources.polcrisis fetch WORKDIR")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
