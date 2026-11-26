"""Download public datasets for the risk snapshot (run in CI, not in tests).

Every source is fetched independently; a failure is recorded in ``manifest.json`` and makes
only that source's event types unavailable.
"""

import csv
import io
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from geointel.risk import regions
from geointel.risk.sources import (
    advisories,
    early,
    elections,
    exposure,
    fcdo,
    fts,
    gdacs,
    gdelt,
    gpsjam,
    metaculus,
    migration,
    ncei_tsunami,
    newswire,
    outlook,
    polymarket,
    sentinel,
    trade,
    usgs,
    worldbank,
)

UCDP_ACD_VERSIONS = ("26.1", "25.1", "24.1")
COUPS_URLS = (
    "https://www.uky.edu/~clthyn2/coup_data/powell_thyne_coups_final.txt",
    "http://www.uky.edu/~clthyn2/coup_data/powell_thyne_coups_final.txt",
)
USER_AGENT = (
    "Mozilla/5.0 (compatible; GeoIntel-risk-snapshot/0.2; +https://github.com/bur5/geointel)"
)


def ucdp_acd_urls() -> list[tuple[str, str]]:
    override = os.environ.get("GEOINTEL_UCDP_ACD_URL")
    if override:
        return [(override, os.environ.get("GEOINTEL_UCDP_ACD_VERSION", "custom"))]
    return [
        (
            "https://ucdp.uu.se/downloads/ucdpprio/"
            f"ucdp-prio-acd-{version.replace('.', '')}-csv.zip",
            version,
        )
        for version in UCDP_ACD_VERSIONS
    ]


def _get(client: httpx.Client, url: str, retries: int = 2) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.get(url)
            if response.status_code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last = exc
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise last or RuntimeError("request failed")


def _download_first(
    client: httpx.Client, candidates: list[tuple[str, str]]
) -> tuple[bytes, str, str]:
    errors = []
    for url, version in candidates:
        try:
            response = _get(client, url, retries=0)
            if response.content:
                return response.content, url, version
            errors.append(f"{url}: empty response")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:160]}")
    raise RuntimeError("; ".join(errors))


def _event_id(feature: dict) -> str:
    return str((feature.get("properties") or {}).get("eventid"))


def _gdacs(client: httpx.Client, reference_year: int) -> tuple[bytes, str, str]:
    features: list[dict] = []
    failures = []
    for hazard in gdacs.HAZARDS:
        for year in range(gdacs.FIRST_YEAR[hazard], reference_year + 1):
            seen: set = set()
            for page in range(1, 20):
                try:
                    response = _get(client, gdacs.page_url(hazard, year, page))
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{hazard} {year}: {type(exc).__name__}")
                    break
                if response.status_code == 204 or not response.content.strip():
                    break
                batch = response.json().get("features") or []
                ids = {_event_id(f) for f in batch}
                features.extend(f for f in batch if _event_id(f) not in seen)
                if len(batch) < 100 or not (ids - seen):
                    break
                seen |= ids
    if failures and not features:
        raise RuntimeError("; ".join(failures[:5]))
    payload = {"features": features, "failures": failures}
    return json.dumps(payload).encode(), gdacs.API, f"{len(features)} features"


def _ncei(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    items: list[dict] = []
    page, total = 1, 1
    while page <= total and page <= 50:
        data = _get(client, ncei_tsunami.page_url(page)).json()
        items.extend(data.get("items") or [])
        total = int(data.get("totalPages") or 1)
        page += 1
    return json.dumps(items).encode(), ncei_tsunami.API, f"{len(items)} events"


def _worldbank(client: httpx.Client, reference_year: int) -> tuple[bytes, str, str]:
    payload = {
        indicator: _get(client, worldbank.url(indicator, reference_year)).json()
        for indicator in (worldbank.GDP_GROWTH, worldbank.INFLATION)
    }
    return json.dumps(payload).encode(), "https://api.worldbank.org/v2", "WDI"


def _fts(client: httpx.Client, reference_year: int) -> tuple[bytes, str, str]:
    payload = {
        year: _get(client, fts.url(year)).json()
        for year in range(fts.START_YEAR, reference_year + 1)
    }
    return json.dumps(payload).encode(), "https://api.hpc.tools/v1/public/plan/year", "FTS"


def _advisories(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    data = _get(client, advisories.URL).json()
    return json.dumps(data).encode(), advisories.URL, f"{len(data)} advisories"


def _exposure(client: httpx.Client, reference_year: int) -> tuple[bytes, str, str]:
    payload = {
        code: _get(client, exposure.url(code, reference_year)).json()
        for code in exposure.INDICATORS.values()
    }
    return json.dumps(payload).encode(), "https://api.worldbank.org/v2", "WDI structure"


def _imf(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    payload = {
        code: _get(client, outlook.imf_url(code)).json() for code in outlook.IMF_INDICATORS.values()
    }
    return json.dumps(payload).encode(), "https://www.imf.org/external/datamapper/api/v1", "WEO"


def _vdem(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    return _download_first(client, [(outlook.owid_url(slug), slug) for slug in outlook.VDEM_SLUGS])


def _gpr(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    return _get(client, outlook.GPR_URL).content, outlook.GPR_URL, "monthly"


def _sparql(client: httpx.Client, query: str) -> dict:
    for attempt in range(2):
        response = client.get(
            elections.ENDPOINT,
            params={"query": query, "format": "json"},
            headers={"Accept": "application/sparql-results+json"},
            timeout=45,
        )
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 1:
            time.sleep(5 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("SPARQL failed")


def _elections(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    from geointel.risk.countries import universe_codes

    rows = _sparql(client, elections.COUNTRY_QUERY)["results"]["bindings"]
    pairs = sorted(
        {
            (r["country"]["value"].rsplit("/", 1)[-1], r["iso3"]["value"].upper())
            for r in rows
            if r["iso3"]["value"].upper() in universe_codes()
        }
    )
    bindings, failures = [], 0
    deadline = time.monotonic() + 420  # never let elections hold up the daily run
    for start in range(0, len(pairs), 12):
        if time.monotonic() > deadline:
            failures += 1
            break
        query = elections.BATCH_QUERY % elections.batch_values(pairs[start : start + 12])
        try:
            bindings.extend(_sparql(client, query)["results"]["bindings"])
        except Exception:  # noqa: BLE001 - a failed batch only loses those countries
            failures += 1
        time.sleep(1)
    if not bindings:
        raise RuntimeError(f"no election data ({failures} failed batches)")
    payload = {"results": {"bindings": bindings}, "failed_batches": failures}
    return json.dumps(payload).encode(), elections.ENDPOINT, f"{len(pairs)} countries"


def _fcdo(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    pages = []
    for url in fcdo.child_urls(_get(client, fcdo.INDEX_URL).json()):
        try:
            pages.append(_get(client, url, retries=1).json())
        except Exception:  # noqa: BLE001 - a missing country page is not fatal
            continue
    if not pages:
        raise RuntimeError("no FCDO country pages")
    return json.dumps(pages).encode(), fcdo.INDEX_URL, f"{len(pages)} countries"


def _regions(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    return _get(client, regions.URL).content, regions.URL, "ne_10m_admin_1"


_BROWSER = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
}


def _coups(client: httpx.Client, fallback: list[str]) -> tuple[bytes, str, str]:
    """Cline Center Coup d'État Project (Illinois Data Bank), else Powell & Thyne."""
    from geointel.risk.sources import coups

    for link in coups.CLINE_FILES:
        try:
            payload = client.get(link, headers=_BROWSER, follow_redirects=True, timeout=90)
            payload.raise_for_status()
            if b"year" in payload.content[:2000].lower():
                print(f"[coups] Cline Center file {link}: {len(payload.content)} bytes")
                return payload.content, link, "Cline Center v2.2.2"
            print(f"[coups] {link}: not a CSV ({payload.content[:80]!r})")
        except Exception as exc:  # noqa: BLE001 - try the next link
            print(f"[coups] {link} failed: {type(exc).__name__}: {str(exc)[:160]}")
    for landing in coups.CLINE_LANDINGS:
        try:
            response = client.get(landing, headers=_BROWSER, follow_redirects=True, timeout=60)
            response.raise_for_status()
            links = coups.cline_csv_links(response.text)
            print(f"[coups] {landing}: {len(response.text)} chars, {len(links)} CSV links")
            if not links:
                import re

                hrefs = re.findall(
                    r"href=[\"']([^\"']*(?:datafile|download|\.csv)[^\"']*)", response.text
                )
                print(f"[coups] sample links: {hrefs[:8]}")
            for link in links:
                payload = client.get(link, headers=_BROWSER, follow_redirects=True, timeout=90)
                payload.raise_for_status()
                if b"year" in payload.content[:2000].lower():
                    return payload.content, link, "Cline Center"
        except Exception as exc:  # noqa: BLE001 - fall back to Powell & Thyne
            print(f"[coups] Cline Center {landing} failed: {type(exc).__name__}: {str(exc)[:160]}")
    errors = []
    for url in fallback:
        try:
            response = client.get(url, headers=_BROWSER, follow_redirects=True, timeout=60)
            response.raise_for_status()
            return response.content, url, "Powell & Thyne"
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            errors.append(f"{url}: {type(exc).__name__} {str(exc)[:120]}")
    raise RuntimeError("; ".join(errors))


def cache_dir() -> Path:
    """State carried between daily runs (published to the risk-data branch under cache/)."""
    return Path(os.environ.get("GEOINTEL_CACHE_DIR", "data/cache"))


def _read_cache(name: str) -> dict:
    path = cache_dir() / name
    try:
        return json.loads(path.read_text()) if path.is_file() else {}
    except ValueError:
        return {}


def _watch_dyads() -> set[tuple[str, str]]:
    from geointel.risk.scenarios import CATALOGUE

    pairs: set[tuple[str, str]] = set()
    for scenario in CATALOGUE:
        others = set(scenario.side_b) | {
            c for e in scenario.exposures if e.role in ("party", "frontline") for c in e.countries
        }
        for a in scenario.side_a:
            for b in others - {a}:
                pairs |= {(a, b), (b, a)}
    return pairs


def _gdelt(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    today = datetime.now(UTC).date()
    cached = _read_cache("gdelt.json").get("days", {})
    watch = _watch_dyads()
    days: dict[str, dict] = {}
    deadline = time.monotonic() + 540
    for day in gdelt.missing_days(cached, today, limit=200):
        if time.monotonic() > deadline:
            break
        texts: list[str] = []
        try:
            texts.append(
                gdelt.read_export(
                    _get(
                        client, gdelt.V1_DAILY.format(day=day.strftime("%Y%m%d")), retries=0
                    ).content
                )
            )
        except Exception:  # noqa: BLE001 - fall back to the 15-minute files
            for stamp in gdelt.v2_stamps(day):
                try:
                    texts.append(
                        gdelt.read_export(
                            _get(client, gdelt.V2_15MIN.format(stamp=stamp), retries=0).content
                        )
                    )
                except Exception:  # noqa: BLE001 - a missing slice is not fatal
                    continue
        if texts:
            days[day.isoformat()] = gdelt.aggregate(texts, watch)
    if not days and not cached:
        raise RuntimeError("no GDELT data")
    return (
        json.dumps({"days": days}).encode(),
        "http://data.gdeltproject.org/",
        f"{len(days)} new days",
    )


def _gpsjam(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    today = datetime.now(UTC).date()
    cached = _read_cache("gpsjam.json").get("days", {})
    wanted = [today - timedelta(days=i) for i in range(1, gpsjam.BASELINE_DAYS + 1)]
    files: dict[str, str] = {}
    errors = []
    for day in [d for d in wanted if d.isoformat() not in cached][:95]:
        for pattern in gpsjam.URLS:
            try:
                files[day.isoformat()] = _get(
                    client, pattern.format(day=day.isoformat()), retries=0
                ).text
                break
            except Exception as exc:  # noqa: BLE001 - try the next pattern
                errors.append(f"{day}: {type(exc).__name__}")
    if not files and not cached:
        raise RuntimeError("; ".join(errors[:4]) or "no GPSJam data")
    return json.dumps({"files": files}).encode(), "https://gpsjam.org/", f"{len(files)} new days"


def _metaculus(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    token = os.environ.get("METACULUS_API_TOKEN")
    if not token or os.environ.get("GEOINTEL_DISABLE_METACULUS"):
        raise RuntimeError("not configured (METACULUS_API_TOKEN secret missing)")
    from geointel.risk.scenarios import CATALOGUE

    payloads = []
    details = 0
    for query in sorted({q for s in CATALOGUE for q in (s.metaculus_queries or s.market_queries)}):
        response = client.get(
            metaculus.POSTS_URL,
            params=metaculus.search_params(query),
            headers={"Authorization": f"Token {token}"},
            timeout=45,
        )
        response.raise_for_status()
        body = response.json()
        results = body.get("results") or []
        sample = results[0] if results else {}
        question = sample.get("question") or {}
        print(
            f"[metaculus] query={query!r} results={len(results)} "
            f"type={question.get('type')} "
            f"aggregations={sorted(question.get('aggregations') or {})} "
            f"{metaculus.diagnose(body)}"
        )
        # The list endpoint leaves the community aggregate empty for this account; a few post
        # pages are fetched to keep checking whether access has changed (November 2026: it
        # had not — Metaculus hides aggregates from API tokens without data access).
        for post in results[:5]:
            if details >= 10 or metaculus.has_probability(post):
                continue
            try:
                detail = client.get(
                    f"{metaculus.POSTS_URL}{post['id']}/",
                    headers={"Authorization": f"Token {token}"},
                    timeout=45,
                )
                detail.raise_for_status()
                post.update(detail.json())
            except Exception as exc:  # noqa: BLE001 - keep the list entry
                print(f"[metaculus] detail {post.get('id')}: {type(exc).__name__}")
            details += 1
            time.sleep(1.0)
        print(f"[metaculus] after details: {metaculus.diagnose(body)}")
        payloads.append({"query": query, **body})
        time.sleep(1.5)
    found = metaculus.questions(payloads)
    for q in found[:30]:
        print(f"[metaculus] {q['p']:.3f} {q['end']} n={q['forecasters']} {q['question'][:100]}")
    return (
        json.dumps({"payloads": payloads}).encode(),
        metaculus.POSTS_URL,
        f"{len(found)} questions",
    )


def _sentinel(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    cid, secret = os.environ.get("CDSE_CLIENT_ID"), os.environ.get("CDSE_CLIENT_SECRET")
    if not cid or not secret:
        raise RuntimeError("not configured (CDSE_CLIENT_ID / CDSE_CLIENT_SECRET secrets missing)")
    token = client.post(
        sentinel.TOKEN_URL,
        data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret},
        timeout=30,
    )
    token.raise_for_status()
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    today = datetime.now(UTC).date()
    sites, errors = {}, []
    for site in sentinel.SITES:
        try:
            response = client.post(
                sentinel.STATS_URL, json=sentinel.request(site, today), headers=headers, timeout=90
            )
            response.raise_for_status()
            sites[site.key] = response.json()
        except Exception as exc:  # noqa: BLE001 - one site failing is not fatal
            errors.append(f"{site.key}: {type(exc).__name__}: {str(exc)[:120]}")
    if not sites:
        raise RuntimeError("; ".join(errors[:3]))
    return (
        json.dumps({"sites": sites, "errors": errors}).encode(),
        sentinel.STATS_URL,
        f"{len(sites)} sites",
    )


NEWSWIRE_BUDGET_SECONDS = 360  # headline fetching must not hold up the daily run


def _newswire(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("not configured (ANTHROPIC_API_KEY secret missing)")
    payloads, failed = [], []
    deadline = time.monotonic() + NEWSWIRE_BUDGET_SECONDS
    for name, query in newswire.QUERIES.items():
        if time.monotonic() > deadline:
            failed.append(f"{name}: time budget")
            continue
        outcome = "no answer"
        for _attempt in range(2):
            try:
                response = client.get(
                    newswire.DOC_URL, params=newswire.doc_params(query), timeout=30
                )
            except httpx.HTTPError as exc:
                outcome = type(exc).__name__
                time.sleep(5)
                continue
            if response.status_code == 429:
                outcome = "429"
                time.sleep(15)
                continue
            if response.status_code != 200:
                outcome = f"HTTP {response.status_code}"
                break
            try:
                payloads.append(response.json())
                outcome = "ok"
            except ValueError:
                outcome = f"not JSON: {response.text[:80]!r}"
            break
        print(f"[news] {name}: {outcome}")
        if outcome != "ok":
            failed.append(f"{name}: {outcome}")
        time.sleep(6)  # GDELT DOC asks for at most one request every five seconds
    print(f"[news] queries ok={len(payloads)} failed={len(failed)}")
    items = newswire.headlines(payloads)
    entries, tokens = [], 0
    for start in range(0, len(items), 60):
        batch = items[start : start + 60]
        response = client.post(
            newswire.MESSAGES_URL,
            json=newswire.request_body(batch),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=120,
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage") or {}
        tokens += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        text = "".join(
            c.get("text", "") for c in body.get("content") or [] if c.get("type") == "text"
        )
        entries.extend(newswire.parse_reply(text, batch))
    for e in entries[:40]:
        print(f"[news] {e['date']} {e['country']} {e['sign']} {e['summary_en'][:100]}")
    payload = {"entries": entries, "headlines": len(items), "tokens": tokens}
    return (
        json.dumps(payload).encode(),
        newswire.DOC_URL,
        f"{len(items)} headlines, {len(entries)} signs, {tokens} tokens",
    )


def _ioda(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    today = datetime.now(UTC).date()
    errors = []
    for url in early.IODA_URLS:
        try:
            response = client.get(url, params=early.ioda_params(today), timeout=90)
            response.raise_for_status()
            body = response.json()
            found = early.ioda_countries(body)
            sample = body.get("data")
            print(f"[ioda] {url} type={type(sample).__name__} countries={len(found)}")
            if isinstance(sample, list) and sample:
                print(f"[ioda] sample keys={sorted(sample[0])[:12]}")
            if found:
                return json.dumps({"countries": found}).encode(), url, f"{len(found)} countries"
        except Exception as exc:  # noqa: BLE001 - try the next route
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:160]}")
    raise RuntimeError("; ".join(errors) or "IODA returned no countries")


def _firms(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    key = os.environ.get("FIRMS_MAP_KEY")
    if not key:
        raise RuntimeError("not configured (FIRMS_MAP_KEY secret missing)")
    today = datetime.now(UTC).date()
    cached = _read_cache("firms.json").get("days", {})
    wanted = [today - timedelta(days=i) for i in range(1, 46)]
    days: dict[str, dict] = {}
    for day in [d for d in wanted if d.isoformat() not in cached][:12]:
        response = client.get(early.FIRMS_URL.format(key=key, day=day.isoformat()), timeout=180)
        response.raise_for_status()
        cells: dict[str, int] = {}
        for row in csv.DictReader(io.StringIO(response.text)):
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
            except (KeyError, ValueError):
                continue
            if str(row.get("confidence", "")).lower() in ("l", "low"):
                continue
            cell = f"{round(lat * 4) / 4},{round(lon * 4) / 4}"
            cells[cell] = cells.get(cell, 0) + 1
        days[day.isoformat()] = cells
        time.sleep(1)
    return (
        json.dumps({"days": days}).encode(),
        "https://firms.modaps.eosdis.nasa.gov/api/area/",
        f"{len(days)} new days",
    )


def _military(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    snapshots = []
    used = early.MIL_URL
    for i in range(3):
        for url in early.MIL_URLS:
            try:
                response = client.get(url, headers=_BROWSER, timeout=60)
                response.raise_for_status()
                snapshots.append(response.json())
                used = url
                break
            except Exception as exc:  # noqa: BLE001 - one failed snapshot is not fatal
                code = getattr(getattr(exc, "response", None), "status_code", "")
                print(f"[military] snapshot {i} {url}: {type(exc).__name__} {code}")
        if i < 2:
            time.sleep(60)
    if not snapshots:
        raise RuntimeError("no military aircraft snapshots (airplanes.live, adsb.lol)")
    counts = early.military_counts(snapshots)
    print(f"[military] {counts}")
    payload = {"counts": counts, "aircraft": sum(len(s.get("ac") or []) for s in snapshots)}
    return json.dumps(payload).encode(), used, f"{payload['aircraft']} positions"


def _zakupki(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    today = datetime.now(UTC).date()
    cached = _read_cache("zakupki.json").get("weeks", {})
    weeks = early.weekly_windows(today, 26)
    result: dict[str, dict[str, int]] = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
    }
    for start, end in weeks:
        key = start.isoformat()
        if key in cached and start < weeks[1][0]:
            continue
        counts: dict[str, int] = {}
        for name, term in early.ZAKUPKI_TERMS.items():
            try:
                response = client.get(
                    early.ZAKUPKI_URL,
                    params=early.zakupki_params(term, start, end),
                    headers=headers,
                    timeout=20,
                )
            except httpx.TimeoutException as exc:
                raise RuntimeError(
                    "zakupki.gov.ru did not answer; it is usually closed to servers outside "
                    "Russia, where GitHub runs"
                ) from exc
            response.raise_for_status()
            total = early.zakupki_total(response.text)
            if total is None:
                raise RuntimeError("could not read the result count (page layout changed?)")
            counts[name] = total
            time.sleep(1.5)
        result[key] = counts
    return json.dumps({"weeks": result}).encode(), early.ZAKUPKI_URL, f"{len(result)} weeks"


def _media(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    series = {}
    for key, query in early.DOC_QUERIES.items():
        for attempt in range(4):
            response = client.get(
                early.DOC_URL, params=early.doc_timeline_params(query), timeout=90
            )
            if response.status_code != 429:
                break
            print(f"[media] {key}: 429, waiting")
            time.sleep(20 * (attempt + 1))
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError:
            print(f"[media] {key}: not JSON: {response.text[:160]!r}")
            body = {}
        series[key] = early.doc_timeline(body)
        print(f"[media] {key}: {len(series[key])} days, {len(response.content)} bytes")
        time.sleep(6)
    return (
        json.dumps({"series": series}).encode(),
        early.DOC_URL,
        f"{sum(map(len, series.values()))} points",
    )


def _fx(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    rates = early.fx_rates(_get(client, early.FX_URL).json())
    if not rates:
        raise RuntimeError("no exchange rates")
    day = datetime.now(UTC).date().isoformat()
    return json.dumps({"days": {day: rates}}).encode(), early.FX_URL, f"{len(rates)} currencies"


def _food(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    url = early.hdx_csv_url(_get(client, early.HDX_PACKAGE).json())
    if not url:
        raise RuntimeError("no CSV in the HDX package")
    text = _get(client, url).text
    return text.encode(), url, f"{len(text)} bytes"


def _telegram(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    from geointel.risk.sources import telegram

    channels: dict[str, dict] = {}
    failures = []
    total = 0
    for channel in telegram.CHANNELS:
        try:
            url = telegram.URL.format(channel=channel)
            posts = telegram.parse_page(_get(client, url, retries=1).text)
            if not posts:
                failures.append(f"{channel}: no posts")
                continue
            # The preview shows ~20 posts per page; page back until yesterday is covered.
            yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
            for _ in range(6):
                before = telegram.oldest_id(posts)
                if not before or min(p["date"] for p in posts) < yesterday:
                    break
                time.sleep(1.5)
                more = telegram.parse_page(_get(client, f"{url}?before={before}", retries=1).text)
                if not more:
                    break
                posts.extend(more)
            channels[channel] = telegram.count(posts, channel)
            total += len(posts)
        except Exception as exc:  # noqa: BLE001 - a missing channel is not fatal
            failures.append(f"{channel}: {type(exc).__name__}")
        time.sleep(2)
    print(f"[telegram] posts={total} ok={sorted(channels)} failed={failures}")
    if not channels:
        raise RuntimeError("; ".join(failures[:5]))
    return (
        json.dumps({"channels": channels}).encode(),
        "https://t.me/s/",
        f"{len(channels)} channels",
    )


def _milex(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    return _download_first(client, [(outlook.owid_url(slug), slug) for slug in trade.MILEX_SLUGS])


def _markets(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    from geointel.risk.scenarios import CATALOGUE

    responses, failures = [], 0
    for query in sorted({q for s in CATALOGUE for q in s.market_queries}):
        try:
            response = client.get(
                polymarket.SEARCH_URL, params=polymarket.search_params(query), timeout=30
            )
            response.raise_for_status()
            responses.append({"query": query, **response.json()})
        except Exception:  # noqa: BLE001 - one failed query only loses its markets
            failures += 1
        time.sleep(0.5)
    if not responses:
        raise RuntimeError("no Polymarket responses")
    found = polymarket.markets(responses)
    for market in sorted(found, key=lambda m: -m["volume"])[:40]:
        print(
            f"[markets] {market['p']:.3f} {market['end']} ${market['volume']:.0f} "
            f"{market['question'][:110]}"
        )
    payload = {"responses": responses, "failed_queries": failures}
    return json.dumps(payload).encode(), polymarket.SEARCH_URL, f"{len(found)} markets"


def _unhcr(client: httpx.Client, reference_year: int) -> tuple[bytes, str, str]:
    last: Exception | None = None
    for year in (reference_year - 1, reference_year - 2):
        try:
            pages, page, max_pages = [], 1, 1
            while page <= max_pages and page <= 20:
                data = client.get(
                    migration.UNHCR_URL, params=migration.unhcr_params(year, page), timeout=90
                )
                data.raise_for_status()
                body = data.json()
                pages.append(body)
                max_pages = int(body.get("maxPages") or 1)
                page += 1
            if sum(len(p.get("items") or []) for p in pages) > 100:
                return (
                    json.dumps({"year": year, "pages": pages}).encode(),
                    migration.UNHCR_URL,
                    str(year),
                )
        except Exception as exc:  # noqa: BLE001 - try the previous year
            last = exc
    raise last or RuntimeError("no UNHCR data")


def _eurostat(client: httpx.Client, reference_year: int) -> tuple[bytes, str, str]:
    since = f"{reference_year - 3}-01"
    response = client.get(
        migration.EUROSTAT_URL, params=migration.eurostat_params(since), timeout=120
    )
    response.raise_for_status()
    return response.content, migration.EUROSTAT_URL, f"since {since}"


TRADE_FIELDS = ("reporterCode", "reporterISO", "partnerCode", "partnerISO", "primaryValue")


def _trade_cache() -> dict[int, dict]:
    """Previously fetched reporters (Comtrade is slow, so the cache fills over several days)."""
    path = os.environ.get("GEOINTEL_TRADE_CACHE") or str(cache_dir() / "trade.json")
    if not Path(path).is_file():
        return {}
    try:
        payload = json.loads(Path(path).read_text())
    except ValueError:
        return {}
    cached: dict[int, dict] = {}
    for response in payload.get("responses") or []:
        rows = response.get("data") or []
        if rows:
            cached[int(rows[0].get("reporterCode", -1))] = response
    return cached


def _trade(client: httpx.Client, reference_year: int) -> tuple[bytes, str, str]:
    key = os.environ.get("COMTRADE_API_KEY")
    if key:
        return _trade_keyed(client, reference_year, key)
    reporters = trade.reference_codes(_get(client, trade.REPORTERS_URL).json())
    partners = trade.reference_codes(_get(client, trade.PARTNERS_URL).json())
    codes = {**partners, **reporters}
    year = reference_year - 2
    cached = {
        code: r
        for code, r in _trade_cache().items()
        if code in reporters and r["period"] >= year - 1
    }
    fresh, failures = {}, 0
    deadline = time.monotonic() + 600  # never let trade hold up the daily run
    for code in sorted(c for c in reporters if c not in cached):
        if time.monotonic() > deadline:
            break
        for period in (year, year - 1):
            try:
                response = client.get(
                    trade.DATA_URL, params=trade.data_params(code, period), timeout=45
                )
                if response.status_code == 429:
                    time.sleep(10)
                    response = client.get(
                        trade.DATA_URL, params=trade.data_params(code, period), timeout=45
                    )
                response.raise_for_status()
                body = response.json()
            except Exception:  # noqa: BLE001 - a missing reporter is not fatal
                failures += 1
                break
            if body.get("data"):
                rows = [{k: row.get(k) for k in TRADE_FIELDS} for row in body["data"]]
                fresh[code] = {"period": period, "data": rows}
                break
        time.sleep(1.1)
    responses = [*cached.values(), *fresh.values()]
    if not responses:
        raise RuntimeError(f"no Comtrade data ({failures} failures)")
    payload = {"year": year, "codes": codes, "responses": responses, "failures": failures}
    version = f"{len(responses)}/{len(reporters)} reporters ({len(fresh)} new)"
    return json.dumps(payload).encode(), trade.DATA_URL, version


def _trade_keyed(client: httpx.Client, reference_year: int, key: str) -> tuple[bytes, str, str]:
    """With a free subscription key all reporters come in a few large requests."""
    reporters = trade.reference_codes(_get(client, trade.REPORTERS_URL).json())
    partners = trade.reference_codes(_get(client, trade.PARTNERS_URL).json())
    codes = {**partners, **reporters}
    year = reference_year - 2
    got: dict[int, dict] = {}
    for period in (year, year - 1):
        todo = sorted(c for c in reporters if c not in got)
        for start in range(0, len(todo), 40):
            chunk = todo[start : start + 40]
            params = {
                **trade.data_params(chunk[0], period),
                "reporterCode": ",".join(map(str, chunk)),
            }
            response = client.get(
                trade.KEYED_URL,
                params=params,
                headers={"Ocp-Apim-Subscription-Key": key},
                timeout=120,
            )
            response.raise_for_status()
            rows = response.json().get("data") or []
            by_reporter: dict[int, list] = {}
            for row in rows:
                by_reporter.setdefault(int(row.get("reporterCode", -1)), []).append(
                    {k: row.get(k) for k in TRADE_FIELDS}
                )
            for code, items in by_reporter.items():
                got.setdefault(code, {"period": period, "data": items})
            time.sleep(1)
    if not got:
        raise RuntimeError("no Comtrade data with key")
    payload = {"year": year, "codes": codes, "responses": list(got.values()), "failures": 0}
    return (
        json.dumps(payload).encode(),
        trade.KEYED_URL,
        f"{len(got)}/{len(reporters)} reporters (key)",
    )


def fetch_all(raw_dir: Path, reference_year: int | None = None) -> dict:
    raw_dir.mkdir(parents=True, exist_ok=True)
    year = reference_year or datetime.now(UTC).year
    coups_urls = [u for u in (os.environ.get("GEOINTEL_COUPS_URL"),) if u] or list(COUPS_URLS)
    jobs: dict[str, tuple[str, Callable[[httpx.Client], tuple[bytes, str, str]]]] = {
        "ucdp_acd": ("ucdp_acd.bin", lambda c: _download_first(c, ucdp_acd_urls())),
        "coups": ("coups.txt", lambda c: _coups(c, coups_urls)),
        "usgs": ("usgs.csv", lambda c: _download_first(c, [(usgs.query_url(), "live")])),
        "gdacs": ("gdacs.json", lambda c: _gdacs(c, year)),
        "tsunami": ("tsunami.json", lambda c: _ncei(c, year)),
        "worldbank": ("worldbank.json", lambda c: _worldbank(c, year)),
        "fts": ("fts.json", lambda c: _fts(c, year)),
        "advisories": ("advisories.json", lambda c: _advisories(c, year)),
        "exposure": ("exposure.json", lambda c: _exposure(c, year)),
        "imf": ("imf.json", lambda c: _imf(c, year)),
        "vdem": ("vdem.csv", lambda c: _vdem(c, year)),
        "gpr": ("gpr.xls", lambda c: _gpr(c, year)),
        "elections": ("elections.json", lambda c: _elections(c, year)),
        "fcdo": ("fcdo.json", lambda c: _fcdo(c, year)),
        "milex": ("milex.csv", lambda c: _milex(c, year)),
        "markets": ("markets.json", lambda c: _markets(c, year)),
        "unhcr": ("unhcr.json", lambda c: _unhcr(c, year)),
        "eurostat": ("eurostat.json", lambda c: _eurostat(c, year)),
        "trade": ("trade.json", lambda c: _trade(c, year)),
        "gdelt": ("gdelt.json", lambda c: _gdelt(c, year)),
        "gpsjam": ("gpsjam.json", lambda c: _gpsjam(c, year)),
        "metaculus": ("metaculus.json", lambda c: _metaculus(c, year)),
        "sentinel": ("sentinel.json", lambda c: _sentinel(c, year)),
        "newswire": ("newswire.json", lambda c: _newswire(c, year)),
        "ioda": ("ioda.json", lambda c: _ioda(c, year)),
        "firms": ("firms.json", lambda c: _firms(c, year)),
        "military": ("military.json", lambda c: _military(c, year)),
        "zakupki": ("zakupki.json", lambda c: _zakupki(c, year)),
        "media": ("media.json", lambda c: _media(c, year)),
        "fx": ("fx.json", lambda c: _fx(c, year)),
        "food": ("food.csv", lambda c: _food(c, year)),
        "telegram": ("telegram.json", lambda c: _telegram(c, year)),
        "regions": ("regions.geojson", lambda c: _regions(c, year)),
    }
    only = {k for k in os.environ.get("GEOINTEL_SOURCES", "").split(",") if k}
    manifest: dict[str, dict] = {}
    with httpx.Client(
        timeout=120,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/csv, */*"},
    ) as client:
        for key, (filename, job) in jobs.items():
            if only and key not in only:
                continue
            started = time.monotonic()
            try:
                payload, url, version = job(client)
            except Exception as exc:  # noqa: BLE001 - recorded in the manifest
                error = f"{type(exc).__name__}: {str(exc)[:600]}"
                manifest[key] = {"status": "failed", "errors": [error]}
                continue
            (raw_dir / filename).write_bytes(payload)
            manifest[key] = {
                "status": "ok",
                "url": url,
                "version": version,
                "bytes": len(payload),
                "file": filename,
                "seconds": round(time.monotonic() - started, 1),
                "retrieved_at": datetime.now(UTC).isoformat(),
                "errors": [],
            }
    (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
