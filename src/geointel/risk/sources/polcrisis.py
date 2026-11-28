"""History of political crises 2000–2025 (see docs/polcrisis-history.md)."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

WIKIDATA = "https://query.wikidata.org/sparql"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
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
# The country proper inside a realm (Netherlands in the Kingdom of the Netherlands): a part
# that is itself a country and has the same capital.
ALIASES_QUERY = """
SELECT DISTINCT ?c ?iso3 ?alias WHERE {
  VALUES ?iso3 { %s }
  ?k wdt:P298 ?iso3 ; wdt:P36 ?capital .
  FILTER NOT EXISTS { ?k wdt:P576 ?gone }
  { ?k wdt:P150 ?c } UNION { ?c wdt:P361 ?k }
  ?c wdt:P31 wd:Q6256 ; wdt:P36 ?capital .
  BIND(true AS ?alias)
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
SELECT ?office ?st ?p ?pLabel ?start ?end ?endPrecision ?cause ?causeLabel ?nature ?natureLabel
WHERE {
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
SELECT ?c ?e ?eLabel ?date ?precision ?type ?jur ?article WHERE {
  VALUES ?type { %s }
  ?e wdt:P31 ?type ; wdt:P17 ?c .
  OPTIONAL { ?e wdt:P1001 ?jur }
  OPTIONAL { ?article schema:about ?e ; schema:isPartOf <https://en.wikipedia.org/> }
  ?e p:P585/psv:P585 [ wikibase:timeValue ?date ; wikibase:timePrecision ?precision ] .
  FILTER(?date >= "1975-01-01T00:00:00Z"^^xsd:dateTime
         && ?date < "2026-07-01T00:00:00Z"^^xsd:dateTime)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
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
                timeout=120,
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


def _wikipedia_intros(client, titles: list[str]) -> dict[str, str]:
    """First paragraph (plain text) of English Wikipedia articles, keyed by article title."""
    for attempt in range(3):
        try:
            response = client.get(
                WIKIPEDIA_API,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "exintro": 1,
                    "explaintext": 1,
                    "exlimit": "max",
                    "redirects": 1,
                    "format": "json",
                    "titles": "|".join(titles),
                },
                headers={"User-Agent": USER_AGENT},
                timeout=60,
            )
            response.raise_for_status()
            query = response.json().get("query", {})
            renamed = {}
            for item in query.get("normalized", []) + query.get("redirects", []):
                renamed[item["to"]] = renamed.get(item["from"], item["from"])
            result = {}
            for page in query.get("pages", {}).values():
                title = page.get("title", "")
                original = renamed.get(title, title)
                result[original.replace(" ", "_")] = (page.get("extract") or "")[:3000]
            return result
        except Exception as exc:  # noqa: BLE001 - retry, then skip the batch
            print(f"[wikipedia] attempt {attempt + 1} failed: {type(exc).__name__}: {exc}")
            time.sleep(5 * (attempt + 1))
    return {}


SNAP_LIST_PAGES = ("Snap election",)
BACKGROUND_HEADINGS = (
    r"^==+\s*(background|context|prelude|history|electoral background|pre-election|"
    r"lead-up|events leading|political situation|dissolution)"
)


def background_section(text: str) -> str:
    """Background-type sections of a plain-text Wikipedia article (up to 4000 characters):
    every section whose heading matches BACKGROUND_HEADINGS, in article order."""
    lines = text.splitlines()
    parts: list[str] = []
    keep = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("=="):
            keep = re.match(BACKGROUND_HEADINGS, stripped, flags=re.IGNORECASE) is not None
            continue
        if keep and stripped:
            parts.append(stripped)
    return " ".join(parts)[:4000]


def _wiki_get(client, params: dict) -> dict:
    for attempt in range(3):
        try:
            response = client.get(
                WIKIPEDIA_API,
                params={**params, "format": "json", "formatversion": 2},
                headers={"User-Agent": USER_AGENT},
                timeout=90,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - retry, then give up on this call
            print(
                f"[wikipedia] attempt {attempt + 1} failed: {type(exc).__name__}: {str(exc)[:120]}"
            )
            time.sleep(10 * (attempt + 1))
    return {}


def wikitext_to_text(wikitext: str) -> str:
    """Rough plain text from wikitext: drop references, templates, tables and link markup."""
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", wikitext, flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    for _ in range(4):  # nested templates
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\{\|.*?\|\}", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\s*([^\]]*)\]", r"\1", text)
    text = re.sub(r"<[^>]+>|'{2,}", "", text)
    return text


def _wikipedia_backgrounds(client, titles: list[str]) -> dict[str, str]:
    """Background / Context sections of election articles (wikitext, many per request)."""
    data: dict = {}
    for _attempt in range(5):
        data = _wiki_get(
            client,
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "redirects": 1,
                "titles": "|".join(titles),
            },
        )
        if data:
            break
        time.sleep(60)  # rate limited: wait a minute
    query = data.get("query") or {}
    renamed = {}
    for item in query.get("normalized", []) + query.get("redirects", []):
        renamed[item["to"]] = renamed.get(item["from"], item["from"])
    result = {}
    for page in query.get("pages", []):
        revisions = page.get("revisions") or []
        if not revisions:
            continue
        content = (revisions[0].get("slots") or {}).get("main", {}).get("content", "")
        section = background_section(wikitext_to_text(content))
        if section:
            title = renamed.get(page["title"], page["title"])
            result[title.replace(" ", "_")] = section
    return result


def _wikipedia_snap_lists(client) -> dict[str, str]:
    """Election articles linked from Wikipedia's "Snap election" article and from the
    "List of snap elections in ..." pages: canonical title (underscores) -> list page."""
    pages = list(SNAP_LIST_PAGES)
    found = _wiki_get(
        client,
        {
            "action": "query",
            "list": "search",
            "srsearch": 'intitle:"snap elections"',
            "srlimit": 50,
        },
    )
    for hit in (found.get("query") or {}).get("search", []):
        if hit.get("title", "").startswith("List of snap elections"):
            pages.append(hit["title"])
    links: dict[str, str] = {}
    for page in pages:
        params = {
            "action": "query",
            "prop": "links",
            "titles": page,
            "plnamespace": 0,
            "pllimit": "max",
        }
        while True:
            data = _wiki_get(client, params)
            for item in (data.get("query") or {}).get("pages", []):
                for link in item.get("links", []):
                    title = link.get("title", "")
                    if re.search(r"\b(19|20)\d\d\b", title) and "election" in title.lower():
                        links.setdefault(title, page)
            if "continue" not in data:
                break
            params = {**params, **data["continue"]}
    resolved: dict[str, str] = {}
    titles = sorted(links)
    for batch in _batches(titles, 50):
        data = _wiki_get(client, {"action": "query", "titles": "|".join(batch), "redirects": 1})
        query = data.get("query") or {}
        target = {r["from"]: r["to"] for r in query.get("redirects", [])}
        for title in batch:
            canonical = target.get(title, title)
            resolved[canonical.replace(" ", "_")] = links[title]
    print(f"[wikipedia] snap lists: {pages}")
    return resolved


def fetch(work: Path) -> None:
    """Download every raw input into ``work`` (run in GitHub Actions)."""
    import httpx

    from geointel.risk.countries import universe_codes
    from geointel.risk.sources import coups

    work.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(follow_redirects=True)
    codes = sorted(universe_codes())
    values = " ".join(f'"{c}"' for c in codes)
    countries = _sparql(client, COUNTRIES_QUERY % values)
    try:
        countries += _sparql(client, ALIASES_QUERY % values)
    except RuntimeError as exc:
        print(f"[wikidata] aliases skipped: {exc}")
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
    for number, batch in enumerate(_batches(wanted, 40)):
        elections += _sparql(client, ELECTIONS_QUERY % " ".join(batch))
        print(f"[wikidata] elections batch {number}: {len(elections)} rows")
        time.sleep(1)
    (work / "wd_elections.json").write_text(json.dumps(elections))
    titles = sorted(
        {
            unquote(_value(b, "article").rsplit("/", 1)[-1])
            for b in elections
            if _value(b, "article") and "2000" <= _value(b, "date")[:4] <= "2025"
        }
    )
    intros: dict[str, str] = {}
    for number, batch in enumerate(_batches(titles, 20)):
        intros.update(_wikipedia_intros(client, batch))
        if number % 25 == 0:
            print(f"[wikipedia] batch {number}: {len(intros)} intros")
        time.sleep(0.5)
    (work / "wp_intros.json").write_text(json.dumps(intros))
    qid_to_iso3 = country_items(countries, frozenset(codes))
    national = national_elections(elections, types, qid_to_iso3)
    wanted_titles = sorted(
        {e["article"] for e in national if e["article"] and 2000 <= e["date"].year <= 2025}
    )
    background: dict[str, str] = {}
    for number, batch in enumerate(_batches(wanted_titles, 10)):
        background.update(_wikipedia_backgrounds(client, batch))
        time.sleep(1)
        if number % 40 == 0:
            print(f"[wikipedia] background batch {number}: {len(background)} texts")
    (work / "wp_background.json").write_text(json.dumps(background))
    print(f"[wikipedia] background sections: {len(background)} of {len(wanted_titles)}")
    listed = _wikipedia_snap_lists(client)
    (work / "wp_snap_listed.json").write_text(json.dumps(listed))
    print(f"[wikipedia] election articles linked from snap-election lists: {len(listed)}")
    print(f"[wikipedia] election intros: {len(intros)} of {len(titles)}")
    print(
        f"[wikidata] countries={len(countries)} offices={len(offices)} holders={len(holders)} "
        f"elections={len(elections)}"
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

FIRST_YEAR, LAST_YEAR = 2000, 2025
SEED = 20261205  # attempt 2 (attempt 1 used 20261128); see docs/polcrisis-history.md
SAMPLE_SIZE = 100
MAX_ERROR_RATE = 0.10  # written in docs/polcrisis-history.md before the first full run
MIN_RECALL = 0.70
COMPONENTS = ("leader_exit", "snap_election", "impeachment", "emergency", "coup")
SOURCES = {
    "wikidata": "Wikidata (CC0), https://www.wikidata.org/",
    "cline": "Cline Center Coup d'État Project v2.2.2 (CC BY 4.0), "
    "https://databank.illinois.edu/datasets/IDB-9651987",
    "manual": "Hand-made list with a source link in source_ref (data/polcrisis/*.csv)",
}
# Offices that change on a fixed rotation; their changes are scheduled unless Wikidata names
# an irregular reason (death, resignation, abdication...).
ROTATING_HEAD_OF_STATE = frozenset({"AND", "BIH", "CHE", "MYS", "SMR"})
# Offices whose holder changed on a fixed rotation in a period, whatever the role.
ROTATING_PERIODS = {
    "CHE": ("1848-01-01", "2100-01-01"),  # Federal Council and its yearly President
    "BTN": ("1998-07-20", "2008-04-09"),  # yearly chair of the Council of Ministers
}
SHORT_TERM_DAYS = 60  # shorter terms without a stated reason are caretakers
ACTING = ("acting", "interim", "caretaker", "provisional")
IRREGULAR_CAUSES = (
    "resign",
    "death",
    "died",
    "assassin",
    "confidence",
    "dismiss",
    "depos",
    "remov",
    "impeach",
    "coup",
    "overthrow",
    "abdicat",
    "oust",
    "recall",
    "vacan",
    "revolution",
    "suspen",
    "incapacit",
    "affair",
    "scandal",
    "self-coup",
    "killed",
    "suicide",
)
REGULAR_CAUSES = ("end of term", "term limit", "re-elect", "election", "expiry", "end of the term")
ELECTION_BEFORE_DAYS = 250  # exit up to this long after a national election is scheduled
ELECTION_AFTER_DAYS = 45
CONTINUATION_DAYS = 45


def pick_countries(bindings: list[dict]) -> dict[str, dict]:
    """One Wikidata item per ISO3 code: prefer a current sovereign state / country."""
    best: dict[str, tuple[int, dict]] = {}
    for b in bindings:
        iso3 = _value(b, "iso3").upper()
        if _value(b, "alias"):
            continue
        score = (2 if _value(b, "type") else 0) + (0 if _value(b, "dissolved") else 1)
        if iso3 not in best or score > best[iso3][0]:
            best[iso3] = (score, b)
    return {iso3: b for iso3, (_score, b) in best.items()}


def election_type_kind(binding: dict) -> str | None:
    """'presidential' / 'parliamentary' / 'snap' for national election classes, else None."""
    from geointel.risk.sources.elections import kind

    label = _value(binding, "typeLabel")
    if _value(binding, "snap") in ("true", "1") and "local" not in label.lower():
        return "snap"
    result = kind(label, "")
    return None if result == "referendum" else result


def _date(text: str | None):
    from datetime import date

    if not text:
        return None
    raw = str(text).strip()[:10]
    try:
        year, month, day = int(raw[:4]), int(raw[5:7]), int(raw[8:10])
        return date(year, max(month, 1), max(day, 1))
    except (ValueError, IndexError):
        return None


def _precision(binding: dict, key: str, default: int = 11) -> int:
    try:
        return int(_value(binding, key) or default)
    except ValueError:
        return default


def _event(iso3, when, component, detail, source, source_ref) -> dict:
    return {
        "iso3": iso3,
        "date": when.isoformat(),
        "year": when.year,
        "component": component,
        "detail": detail,
        "source": source,
        "source_ref": source_ref,
        "checked": False,
    }


def country_items(countries: list[dict], universe: frozenset[str]) -> dict[str, str]:
    """Wikidata QID -> ISO3 for the countries in the GeoIntel universe."""
    result = {
        _qid(_value(b, "c")): _value(b, "iso3").upper()
        for b in countries
        if not _value(b, "dissolved") and _value(b, "iso3").upper() in universe
    }
    for iso3, b in pick_countries(countries).items():
        if iso3 in universe:
            result[_qid(_value(b, "c"))] = iso3
    return result


def office_roles(offices: list[dict], qid_to_iso3: dict[str, str]) -> dict[str, dict]:
    """office QID -> {"iso3": {...}, "roles": {...}, "label": str}."""
    result: dict[str, dict] = {}
    for b in offices:
        iso3 = qid_to_iso3.get(_qid(_value(b, "c")))
        if not iso3:
            continue
        item = result.setdefault(
            _qid(_value(b, "office")),
            {"iso3": set(), "roles": set(), "label": _value(b, "officeLabel")},
        )
        item["iso3"].add(iso3)
        item["roles"].add(_value(b, "role"))
    return result


def terms_from(holders: list[dict], offices: dict[str, dict]) -> list[dict]:
    """Office terms: one per (statement), with parsed dates."""
    seen: dict[str, dict] = {}
    for b in holders:
        office = _qid(_value(b, "office"))
        if office not in offices:
            continue
        statement = _value(b, "st")
        term = seen.get(statement)
        if term is None:
            term = seen[statement] = {
                "office": office,
                "person": _qid(_value(b, "p")),
                "name": _value(b, "pLabel"),
                "start": _date(_value(b, "start")),
                "end": _date(_value(b, "end")),
                "end_precision": _precision(b, "endPrecision"),
                "causes": set(),
                "nature": set(),
                "statement": statement.rsplit("/", 1)[-1],
            }
        if _value(b, "causeLabel"):
            term["causes"].add(_value(b, "causeLabel"))
        if _value(b, "natureLabel"):
            term["nature"].add(_value(b, "natureLabel").lower())
    return list(seen.values())


def _union_days(intervals, lo, hi) -> int:
    clipped = sorted((max(a, lo), min(b, hi)) for a, b in intervals if a <= hi and b >= lo)
    total, cur_a, cur_b = 0, None, None
    for a, b in clipped:
        if cur_b is None or a > cur_b:
            if cur_b is not None:
                total += (cur_b - cur_a).days + 1
            cur_a, cur_b = a, b
        else:
            cur_b = max(cur_b, b)
    if cur_b is not None:
        total += (cur_b - cur_a).days + 1
    return total


def coverage(terms, offices, first_years: dict[str, int], threshold: float = 0.9):
    """ISO3 -> share of the period with a known head of state / of government."""
    from datetime import date

    lo_default, hi = date(FIRST_YEAR, 1, 1), date(LAST_YEAR, 12, 31)
    by_role: dict[tuple[str, str], list] = {}
    for term in terms:
        if term["start"] is None:
            continue
        info = offices[term["office"]]
        interval = (term["start"], term["end"] or hi)
        for iso3 in info["iso3"]:
            for role in info["roles"]:
                by_role.setdefault((iso3, role), []).append(interval)
    result: dict[str, dict] = {}
    for iso3 in sorted({key[0] for key in by_role}):
        lo = max(lo_default, date(first_years.get(iso3, FIRST_YEAR), 1, 1))
        shares = {}
        for role in ("head_of_state", "head_of_government"):
            intervals = by_role.get((iso3, role))
            if not intervals:
                continue
            span_lo = lo if role == "head_of_state" else max(lo, min(a for a, _ in intervals))
            span_hi = hi if role == "head_of_state" else min(hi, max(b for _, b in intervals))
            days = (span_hi - span_lo).days + 1
            shares[role] = _union_days(intervals, span_lo, span_hi) / days if days > 0 else 0.0
        ok = shares.get("head_of_state", 0) >= threshold and all(
            v >= threshold for v in shares.values()
        )
        result[iso3] = {"shares": shares, "covered": ok}
    return result


def _national_kind(type_label: str, label: str) -> str | None:
    """``sources/elections.kind`` plus federal elections (Australia, Germany, Belgium...)."""
    from geointel.risk.sources.elections import kind as election_kind

    result = election_kind(type_label, label)
    if result is None and "federal election" in f"{type_label} {label}".lower():
        result = election_kind(type_label.replace("federal", "general"), "")
    return None if result == "referendum" else result


# Dependent territories, constituent units and breakaway regions whose elections carry the
# sovereign country in P17 but are not national elections of that country.
TERRITORY = (
    r"\b(greenland|faroe|aruba|cura[cç]ao|sint maarten|bermuda|gibraltar|puerto ric|guam|"
    r"somaliland|puntland|jubaland|republika srpska|federation of bosnia|northern cyprus|"
    r"transnistria|abkhaz|south osseti|artsakh|nagorno|kurdistan|zanzibar|bougainville|"
    r"[aå]land|isle of man|jersey|guernsey|new caledonia|french polynesia|tokelau|cook islands|"
    r"niue|hong kong|maca[ou]|montserrat|cayman|anguilla|turks and caicos|virgin islands|"
    r"falkland|saint helena|wallis|mayotte|r[ée]union|martinique|guadeloupe|scottish|welsh|"
    r"northern ireland|catalan|basque|galician|andalusian|flemish|walloon|brussels|quebec|"
    r"ontario|bavarian|azores|madeira|sicilian|sardinian|corsican|tibet|xinjiang|chechen|"
    r"tatarstan|bashkortostan|crimea|kosovo serb|gagauz|adjar|nakhchivan|karakalpak|"
    r"gilgit|azad|kashmir|bangsamoro|aceh|papua(?! new)|tamil nadu|kerala|punjab|state of|"
    r"provincial|territorial|faroese|greenlandic|aruban|bermudian|gibraltarian|manx|"
    r"cura[cç]aoan|caymanian|anguillan|montserratian|falkland islands|zanzibari|[aå]landic|"
    r"new caledonian|french polynesian|macanese|puerto rican|guamanian|northern mariana|"
    r"american samoan|tokelauan|niuean|transnistrian|abkhazian|south ossetian|"
    r"northern cypriot|turkish cypriot|br[cč]ko|northern irish|sahrawi|western sahara|"
    r"kurdistan region|iraqi kurdistan|autonomous region|autonomous republic|regional)\b"
)


def national_elections(elections, types, qid_to_iso3) -> list[dict]:
    """National elections (one record per Wikidata item and country).

    Sub-national votes are dropped: the item label or class must look national (same rule as
    ``sources/elections.py``) and the jurisdiction (P1001), when given, must be the country.
    """
    from geointel.risk.sources.elections import kind as election_kind

    labels = {_qid(_value(b, "type")): _value(b, "typeLabel") for b in types}
    kinds = {_qid(_value(b, "type")): election_type_kind(b) for b in types}
    result: dict[tuple[str, str], dict] = {}
    owners: dict[str, set[str]] = {}
    for b in elections:
        owners.setdefault(_qid(_value(b, "e")), set()).add(_qid(_value(b, "c")))
    foreign_jurisdiction: set[str] = set()
    for b in elections:
        iso3 = qid_to_iso3.get(_qid(_value(b, "c")))
        jur = _qid(_value(b, "jur")) if _value(b, "jur") else ""
        item = _qid(_value(b, "e"))
        if iso3 and jur and qid_to_iso3.get(jur) != iso3 and jur not in owners[item]:
            foreign_jurisdiction.add(item)
    for b in elections:
        iso3 = qid_to_iso3.get(_qid(_value(b, "c")))
        type_id = _qid(_value(b, "type"))
        kind = kinds.get(type_id)
        when = _date(_value(b, "date"))
        qid = _qid(_value(b, "e"))
        label = _value(b, "eLabel")
        if not iso3 or not kind or when is None or _precision(b, "precision") < 10:
            continue
        if qid in foreign_jurisdiction or re.search(TERRITORY, label, flags=re.IGNORECASE):
            continue
        label_year = re.match(r"\s*(?:\w+\s+)?((?:19|20)\d\d)\b", label)
        if label_year and abs(int(label_year.group(1)) - when.year) > 1:
            continue  # the date in Wikidata contradicts the item's own name
        if kind != "snap" and _national_kind(labels.get(type_id, ""), label) is None:
            continue
        if kind == "snap" and election_kind("", label.replace("snap", "general")) is None:
            continue
        article = unquote(_value(b, "article").rsplit("/", 1)[-1]) if _value(b, "article") else ""
        item = result.setdefault(
            (iso3, qid),
            {
                "iso3": iso3,
                "qid": qid,
                "label": label,
                "date": when,
                "types": set(),
                "kinds": set(),
                "snap": False,
                "article": article,
            },
        )
        item["types"].add(type_id)
        item["kinds"].add(_national_kind(labels.get(type_id, ""), label) or kind)
        if kind == "snap":
            item["snap"] = True
    return sorted(result.values(), key=lambda e: (e["iso3"], e["date"]))


SNAP_PATTERNS = (
    r"\b(snap|early|premature|anticipated|extraordinary)\s+(?:\w+\s+){0,3}"
    r"(elections?|polls?|vote)\b",
    r"\b(elections?|polls?|vote)\s+(?:\w+\s+){0,3}(brought forward|called early|held early)",
    r"\bahead of schedule\b",
    r"\bearlier than (scheduled|planned|required|originally)",
    r"\belections?\s+(?:was|were|had been)\s+called\s+(?:early|following|after)\b",
    r"\b(?:barely|only|just|less than)\s+(?:a|one|two|three|\d+)\s+(?:\w+\s+)?"
    r"(?:years?|months?)\s+after\s+the\s+previous\b",
    r"\b(?:following|after)\s+the\s+(?:collapse|fall)\s+of\b",
    r"\b(?:following|after)\s+the\s+(?:early\s+|premature\s+)?dissolution\s+of\b",
    r"\b(?:triggered|precipitated|necessitated|prompted)\s+by\s+the\s+(?:collapse|fall|"
    r"resignation|death|dissolution)\b",
    r"\b(?:following|followed|after)\s+the\s+(?:\w+\s+)?(?:death|assassination|resignation|"
    r"removal|impeachment|ouster|overthrow)\s+(?:\w+\s+){0,7}of\s+(?:the\s+)?"
    r"(?:incumbent\s+)?(?:\w+\s+){0,3}(?:president|prime minister|king|emir|head of state)\b",
    r"\b(?:called|calling|call)\s+(?:an?\s+)?(?:early|snap)\b",
    r"\bafter\s+(?:his|her)\s+(?:resignation|death|assassination|removal)\b",
    r"\b(?:dissolved|dissolution of)\s+(?:the\s+)?(?:\w+\s+){0,3}(?:parliament|assembly|"
    r"house|chamber|legislature|diet|knesset|sejm|duma|rada|bundestag|storting|riksdag|"
    r"folketing|cortes|congress)\s+(?:\w+\s+){0,4}(?:early|prematurely|before the end)\b",
    r"\b(?:originally|initially)\s+(?:been\s+)?(?:scheduled|expected|planned|due)\b",
)
# Words that turn "originally scheduled" into a postponement, not an early election.
LATE_WORDS = ("delay", "postpon", "deferred", "rescheduled for later", "pushed back")
# Sentences about other elections ("the previous election was a snap election") are skipped.
OTHER_ELECTION = (
    r"\b(previous|last|preceding|prior|next|subsequent|upcoming)\s+(?:\w+\s+){0,2}"
    r"(elections?|vote)\b(?!\.)"
)


def snap_in_intro(text: str, sentences: int = 6) -> str | None:
    """The phrase in a Wikipedia lead that says the election was early, else None."""
    import re

    for sentence in re.split(r"(?<=[.!?])\s+", text.strip())[:sentences]:
        for pattern in SNAP_PATTERNS:
            match = re.search(pattern, sentence, flags=re.IGNORECASE)
            if not match or "early voting" in match.group(0).lower():
                continue
            if "originally" in pattern and any(w in sentence.lower() for w in LATE_WORDS):
                continue
            if "after the previous" not in match.group(0).lower() and re.search(
                OTHER_ELECTION, sentence, flags=re.IGNORECASE
            ):
                continue
            return match.group(0)
    return None


MONARCH = (
    r"\b(monarch|king|queen|emir|sultan|emperor|grand duke|prince|sheikh|amir|"
    r"yang di-pertuan|druk gyalpo)\b"
)


def leader_exits(terms, offices, elections, covered=None) -> list[dict]:
    """Exits of heads of state/government outside the normal schedule (see the docs)."""
    from datetime import date, timedelta

    lo, hi = date(FIRST_YEAR, 1, 1), date(LAST_YEAR, 12, 31)
    any_dates: dict[str, list] = {}
    presidential_dates: dict[str, list] = {}
    for item in elections:
        any_dates.setdefault(item["iso3"], []).append(item["date"])
        if "presidential" in item["kinds"]:
            presidential_dates.setdefault(item["iso3"], []).append(item["date"])
    starts: dict[tuple[str, str], list] = {}
    for term in terms:
        for iso3 in offices[term["office"]]["iso3"]:
            for role in offices[term["office"]]["roles"]:
                if term["start"]:
                    starts.setdefault((iso3, term["person"]), []).append((role, term["start"]))
    events: dict[tuple[str, str, str], dict] = {}
    for term in terms:
        end = term["end"]
        if end is None or not lo <= end <= hi or term["end_precision"] < 10:
            continue
        if any(word in nature for nature in term["nature"] for word in ACTING):
            continue
        info = offices[term["office"]]
        if "governor" in info["label"].lower():
            continue  # governors-general represent the monarch; they are not the head of state
        hereditary = re.search(MONARCH, info["label"].lower()) is not None
        head_of_state_only = info["roles"] == {"head_of_state"}
        causes = " ".join(sorted(term["causes"])).lower()
        irregular = any(word in causes for word in IRREGULAR_CAUSES)
        regular = not irregular and any(word in causes for word in REGULAR_CAUSES)
        for iso3 in sorted(info["iso3"]):
            if covered is not None and iso3 not in covered:
                continue
            if regular:
                continue
            continued = any(
                role in info["roles"]
                and end - timedelta(days=1) <= start <= end + timedelta(days=CONTINUATION_DAYS)
                for role, start in starts.get((iso3, term["person"]), [])
            )
            if continued:
                continue
            period = ROTATING_PERIODS.get(iso3)
            if period and period[0] <= end.isoformat() <= period[1]:
                continue  # collegial or rotating executive: changes are routine
            if not irregular:
                if "head_of_state" in info["roles"] and iso3 in ROTATING_HEAD_OF_STATE:
                    continue
                if term["start"] and (end - term["start"]).days < SHORT_TERM_DAYS:
                    continue  # an acting or caretaker term Wikidata does not mark as such
                if full_term(term["start"], end):
                    continue
                dates = any_dates.get(iso3, [])
                if head_of_state_only and presidential_dates.get(iso3):
                    dates = presidential_dates[iso3]
                near_election = not hereditary and any(
                    end - timedelta(days=ELECTION_BEFORE_DAYS)
                    <= when
                    <= end + timedelta(days=ELECTION_AFTER_DAYS)
                    for when in dates
                )
                if near_election:
                    continue
            why = ", ".join(sorted(term["causes"])) or (
                "hereditary office" if hereditary else "no national election in the 250 days before"
            )
            detail = f"{term['name']} left office as {info['label']} ({why})"
            key = (iso3, term["person"], end.isoformat()[:7])
            events.setdefault(
                key, _event(iso3, end, "leader_exit", detail, "wikidata", term["statement"])
            )
    return sorted(events.values(), key=lambda e: (e["iso3"], e["date"]))


def full_term(start, end) -> bool:
    """A term that lasted a whole number of years (4–7, ±30 days) ended on schedule."""
    if start is None:
        return False
    years = (end - start).days / 365.25
    return round(years) in (4, 5, 6, 7) and abs(years - round(years)) * 365.25 <= 30


def snap_elections(
    elections,
    intros: dict[str, str] | None = None,
    listed: dict[str, str] | None = None,
    background: dict[str, str] | None = None,
) -> list[dict]:
    """Snap elections: typed as snap in Wikidata, linked from a Wikipedia list of snap
    elections, or called early according to the first sentences of the Wikipedia article."""
    from datetime import date

    intros, listed, background = intros or {}, listed or {}, background or {}
    lo, hi = date(FIRST_YEAR, 1, 1), date(LAST_YEAR, 12, 31)
    events: dict[str, dict] = {}
    for item in elections:
        if not lo <= item["date"] <= hi:
            continue
        article = item["article"]
        phrase = snap_in_intro(intros.get(article, "")) if article else None
        where = "lead"
        if not phrase and article and background.get(article):
            phrase, where = snap_in_intro(background[article], sentences=15), "Background"
        if item["snap"]:
            detail = f"{item['label']} (Wikidata: snap election)"
        elif article and article in listed:
            detail = f"{item['label']} (Wikipedia: listed in “{listed[article]}”)"
        elif phrase:
            detail = f"{item['label']} (Wikipedia {where}: “{phrase}”)"
        else:
            continue
        events[item["qid"]] = _event(
            item["iso3"], item["date"], "snap_election", detail, "wikidata", item["qid"]
        )
    return _dedupe(sorted(events.values(), key=lambda e: (e["iso3"], e["date"])), 90)


def _dedupe(events: list[dict], days: int) -> list[dict]:
    from datetime import date

    result: list[dict] = []
    for event in events:
        if result:
            last = result[-1]
            gap = date.fromisoformat(event["date"]) - date.fromisoformat(last["date"])
            same = last["iso3"] == event["iso3"] and last["component"] == event["component"]
            if same and gap.days <= days:
                continue
        result.append(event)
    return result


def cline_events(rows: list[dict], resolve) -> tuple[list[dict], int]:
    """Realised and attempted coups 2000–2025 (conspiracies excluded)."""
    from datetime import date

    events, unresolved = [], 0
    for row in rows:
        row = {str(k).strip().lower(): str(v or "").strip() for k, v in row.items()}
        kind = row.get("event_type", "").lower()
        if row.get("conspiracy") == "1" or kind.startswith("consp"):
            continue
        try:
            year = int(float(row.get("year", "")))
            month = int(float(row.get("month") or 0))
            day = int(float(row.get("day") or 0))
        except ValueError:
            continue
        if not FIRST_YEAR <= year <= LAST_YEAR:
            continue
        iso3 = resolve(row.get("country", ""))
        if not iso3:
            unresolved += 1
            continue
        when = date(year, month if 1 <= month <= 12 else 1, day if 1 <= day <= 28 else 1)
        if 1 <= month <= 12 and 29 <= day <= 31:
            try:
                when = date(year, month, day)
            except ValueError:
                pass
        outcome = "realised coup" if row.get("realized") == "1" else "attempted coup"
        events.append(
            _event(iso3, when, "coup", f"{outcome} (Cline Center)", "cline", row.get("coup_id", ""))
        )
    return events, unresolved


def manual_events(rows: list[dict], component: str, universe: frozenset[str]) -> list[dict]:
    """Events from a hand-made CSV; an impeachment row with ``removed_on`` also yields the
    removal from office as a ``leader_exit``."""
    events = []
    for row in rows:
        removed = _date(row.get("removed_on"))
        iso3 = (row.get("iso3") or "").strip().upper()
        if removed and iso3 in universe and row.get("source"):
            detail = f"{(row.get('person') or '').strip()} removed from office after impeachment"
            events.append(
                _event(iso3, removed, "leader_exit", detail, "manual", row["source"].strip())
            )
        when = _date(row.get("date"))
        iso3 = (row.get("iso3") or "").strip().upper()
        if when is None or iso3 not in universe or not row.get("source"):
            continue
        detail = row.get("detail", "").strip()
        if row.get("person"):
            detail = f"{row['person'].strip()}: {detail}"
        events.append(_event(iso3, when, component, detail, "manual", row["source"].strip()))
    return events


# ---------------------------------------------------------------- reference sets and quality


def cow_names(*tables: list[tuple[str, str]]) -> dict[int, str]:
    """COW country code -> country name from the reference files that carry both."""
    result: dict[int, str] = {}
    for table in tables:
        for code, name in table:
            try:
                result.setdefault(int(float(code)), name)
            except (TypeError, ValueError):
                continue
    return result


def archigos_reference(rows, cow_to_iso3: dict[int, str]) -> list[tuple[str, object]]:
    """Archigos 4.1 exits 2000–2015 that were not regular (see the docs)."""
    from datetime import date

    lo, hi = date(2000, 1, 1), date(2015, 12, 31)
    result = []
    for row in rows:
        exit_kind = str(row.get("exit", "")).strip()
        if exit_kind in ("Regular", "Still in Office", ""):
            continue
        when = _date(row.get("enddate"))
        try:
            iso3 = cow_to_iso3.get(int(float(row.get("ccode", ""))))
        except ValueError:
            iso3 = None
        if when and iso3 and lo <= when <= hi:
            result.append((iso3, when))
    return sorted(set(result))


COW_ALIASES = {"Republic of Korea": "South Korea", "Surinam": "Suriname"}
NELDA_EARLY = (
    "early",
    "dissol",
    "prematur",
    "snap",
    "ahead",
    "advance",
    "anticipat",
    "before",
)


def nelda_reference(rows, resolve, last_year: int = 2010) -> list[tuple[str, object]]:
    """NELDA elections 2000–last_year marked early or late (nelda6) whose note says early."""
    from datetime import date

    result: list[tuple[str, object]] = []
    for row in rows:
        if str(row.get("nelda6", "")).strip().lower() != "yes":
            continue
        note = str(row.get("nelda6notes", "") or "").lower()
        if not any(word in note for word in NELDA_EARLY):
            continue
        try:
            year = int(float(row.get("year", "")))
            mmdd = int(float(row.get("mmdd", "")))
            when = date(year, max(1, mmdd // 100), max(1, mmdd % 100))
        except ValueError:
            continue
        iso3 = resolve(str(row.get("nelda_country", "")))
        if iso3 and 2000 <= year <= last_year:
            result.append((iso3, when))
    result = sorted(set(result))
    merged: list[tuple[str, object]] = []
    for iso3, when in result:  # first and second rounds count once
        if merged and merged[-1][0] == iso3 and (when - merged[-1][1]).days <= 60:
            continue
        merged.append((iso3, when))
    return merged


def recall(reference, events, components, covered, days: int = 60) -> dict:
    from datetime import date

    ours: dict[str, list] = {}
    for event in events:
        if event["component"] in components:
            ours.setdefault(event["iso3"], []).append(date.fromisoformat(event["date"]))
    considered = [(iso3, when) for iso3, when in reference if iso3 in covered]
    found = [
        (iso3, when)
        for iso3, when in considered
        if any(abs((d - when).days) <= days for d in ours.get(iso3, []))
    ]
    missed = [
        f"{iso3} {when.isoformat()}" for iso3, when in considered if (iso3, when) not in found
    ]
    return {
        "reference": len(considered),
        "found": len(found),
        "recall": round(len(found) / len(considered), 3) if considered else None,
        "missed": missed,
    }


def _key(event: dict) -> tuple:
    return (event["iso3"], event["date"], event["component"], event["detail"])


def sample(events: list[dict], size: int = SAMPLE_SIZE, seed: int = SEED) -> list[dict]:
    import random

    ordered = sorted(events, key=_key)
    return random.Random(seed).sample(ordered, min(size, len(ordered)))


def apply_checks(events: list[dict], checks: list[dict]) -> dict:
    """Mark checked events and count errors from data/polcrisis/sample_check_2.csv."""
    verdicts = {
        (r["iso3"], r["date"], r["component"], r["detail"]): r for r in checks if r.get("verdict")
    }
    errors, checked, error_list = 0, 0, []
    for event in events:
        row = verdicts.get(_key(event))
        if row is None:
            continue
        event["checked"] = True
        checked += 1
        if row["verdict"].strip().lower() != "ok":
            errors += 1
            label = f"{event['iso3']} {event['date']} {event['component']}"
            error_list.append(f"{label}: {row.get('note', '')}")
    return {
        "sample_size": checked,
        "errors": errors,
        "error_rate": round(errors / checked, 3) if checked else None,
        "error_list": error_list,
        "seed": SEED,
    }


def build(raw: dict, universe: frozenset[str], first_years: dict[str, int], resolve, today):
    """Assemble the history file from parsed raw inputs (no network)."""
    qid_to_iso3 = country_items(raw["countries"], universe)
    offices = office_roles(raw["offices"], qid_to_iso3)
    terms = terms_from(raw["holders"], offices)
    cover = coverage(terms, offices, first_years)
    covered = sorted(iso3 for iso3, item in cover.items() if item["covered"])
    elections = national_elections(raw["elections"], raw["election_types"], qid_to_iso3)
    coup_events, coup_unresolved = cline_events(raw["cline"], resolve)
    events = (
        leader_exits(terms, offices, elections)
        + snap_elections(
            elections,
            raw.get("intros", {}),
            raw.get("snap_listed", {}),
            raw.get("background", {}),
        )
        + manual_events(raw["impeachments"], "impeachment", universe)
        + manual_events(raw["emergency_list"], "emergency", universe)
        + coup_events
    )
    events = _dedupe(sorted(events, key=_key), 3)
    quality = apply_checks(events, raw.get("checks", []))
    cow = cow_names(raw.get("cow_names", []))
    cow_iso3 = {code: resolve(COW_ALIASES.get(name, name)) for code, name in cow.items()}
    covered_set = frozenset(covered)
    quality["recall_vs_reference"] = {
        "leader_exit_vs_archigos_2000_2015": recall(
            archigos_reference(raw.get("archigos", []), cow_iso3),
            events,
            ("leader_exit", "coup"),
            covered_set,
        ),
        "snap_election_vs_nelda_2000_2010": recall(
            nelda_reference(raw.get("nelda", []), resolve), events, ("snap_election",), covered_set
        ),
    }
    recalls = [v["recall"] for v in quality["recall_vs_reference"].values()]
    quality["thresholds"] = {"max_error_rate": MAX_ERROR_RATE, "min_recall": MIN_RECALL}
    quality["passed"] = (
        quality["error_rate"] is not None
        and quality["error_rate"] <= MAX_ERROR_RATE
        and all(r is not None and r >= MIN_RECALL for r in recalls)
    )
    years: dict[str, list[int]] = {}
    for event in events:
        years.setdefault(event["iso3"], [])
        if event["year"] not in years[event["iso3"]]:
            years[event["iso3"]].append(event["year"])
    counts: dict[str, int] = {}
    for event in events:
        counts[event["component"]] = counts.get(event["component"], 0) + 1
    return {
        "version": 1,
        "built": today.isoformat(),
        "first_year": FIRST_YEAR,
        "last_year": LAST_YEAR,
        "covered": covered,
        "coverage_rule": "head of state (and of government, where separate) known for at least "
        "90% of days 2000–2025 in Wikidata; emergencies are a partial list and do not count "
        "towards coverage",
        "components_partial": ["emergency"],
        "sources": SOURCES,
        "counts": counts,
        "unresolved": {"cline_countries": coup_unresolved},
        "events": events,
        "years": {iso3: sorted(v) for iso3, v in sorted(years.items())},
        "quality": quality,
    }


def _csv(path: Path) -> list[dict]:
    import csv
    import io

    if not path.exists():
        print(f"[build] missing {path.name}")
        return []
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _json(path: Path) -> list[dict]:
    return json.loads(path.read_text()) if path.exists() else []


def load_raw(work: Path, data_dir: Path) -> dict:
    cline = _csv(work / "cline_coups.csv")
    nelda = _csv(work / "nelda.csv")
    names = [(r.get("cowcode"), r.get("country")) for r in cline] + [
        (r.get("nelda_ccode"), r.get("nelda_country")) for r in nelda
    ]
    return {
        "countries": _json(work / "wd_countries.json"),
        "offices": _json(work / "wd_offices.json"),
        "holders": _json(work / "wd_holders.json"),
        "elections": _json(work / "wd_elections.json"),
        "election_types": _json(work / "wd_election_types.json"),
        "intros": json.loads((work / "wp_intros.json").read_text())
        if (work / "wp_intros.json").exists()
        else {},
        "cline": cline,
        "archigos": _csv(work / "archigos.csv"),
        "nelda": nelda,
        "cow_names": names,
        "impeachments": _csv(data_dir / "impeachments.csv"),
        "emergency_list": _csv(data_dir / "emergencies.csv"),
        "checks": _csv(data_dir / "sample_check_2.csv"),
        "background": json.loads((work / "wp_background.json").read_text())
        if (work / "wp_background.json").exists()
        else {},
        "snap_listed": json.loads((work / "wp_snap_listed.json").read_text())
        if (work / "wp_snap_listed.json").exists()
        else {},
    }


def build_files(work: Path, data_dir: Path, output: Path) -> dict:
    from datetime import date

    from geointel.risk.countries import FIRST_YEAR as COUNTRY_FIRST_YEAR
    from geointel.risk.countries import resolve_country_name, universe_codes

    result = build(
        load_raw(work, data_dir),
        universe_codes(),
        COUNTRY_FIRST_YEAR,
        resolve_country_name,
        date.today(),
    )
    if len(result["covered"]) < 120 or len(result["events"]) < 500:
        raise SystemExit(
            f"[build] implausible result ({len(result['covered'])} countries covered, "
            f"{len(result['events'])} events): not written"
        )
    output.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    picked = sample(result["events"])
    with (output.parent / "polcrisis_sample.csv").open("w", newline="") as handle:
        import csv

        writer = csv.writer(handle)
        writer.writerow(["iso3", "date", "component", "detail", "source", "source_ref"])
        for event in picked:
            writer.writerow(
                [event[k] for k in ("iso3", "date", "component", "detail", "source", "source_ref")]
            )
    quality = {k: v for k, v in result["quality"].items()}
    print(
        f"[build] events={len(result['events'])} covered={len(result['covered'])} "
        f"counts={result['counts']} unresolved={result['unresolved']}"
    )
    print(f"[build] quality={json.dumps(quality, ensure_ascii=False)[:4000]}")
    return result


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "fetch":
        fetch(Path(argv[1]))
        return 0
    if len(argv) >= 3 and argv[0] == "build":
        build_files(Path(argv[1]), Path("data/polcrisis"), Path(argv[2]))
        return 0
    print("usage: python -m geointel.risk.sources.polcrisis fetch WORKDIR | build WORKDIR OUT")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
