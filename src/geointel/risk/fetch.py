"""Download public datasets for the risk snapshot (run in CI, not in tests).

Every source is fetched independently; a failure is recorded in ``manifest.json`` and makes
only that source's event types unavailable.
"""

import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from geointel.risk import regions
from geointel.risk.sources import (
    advisories,
    elections,
    exposure,
    fcdo,
    fts,
    gdacs,
    ncei_tsunami,
    outlook,
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


def _elections(client: httpx.Client, _year: int) -> tuple[bytes, str, str]:
    response = client.get(
        elections.ENDPOINT,
        params={"query": elections.QUERY, "format": "json"},
        headers={"Accept": "application/sparql-results+json"},
        timeout=180,
    )
    response.raise_for_status()
    return response.content, elections.ENDPOINT, "SPARQL"


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


def fetch_all(raw_dir: Path, reference_year: int | None = None) -> dict:
    raw_dir.mkdir(parents=True, exist_ok=True)
    year = reference_year or datetime.now(UTC).year
    coups_urls = [u for u in (os.environ.get("GEOINTEL_COUPS_URL"),) if u] or list(COUPS_URLS)
    jobs: dict[str, tuple[str, Callable[[httpx.Client], tuple[bytes, str, str]]]] = {
        "ucdp_acd": ("ucdp_acd.bin", lambda c: _download_first(c, ucdp_acd_urls())),
        "coups": ("coups.txt", lambda c: _download_first(c, [(u, "live") for u in coups_urls])),
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
