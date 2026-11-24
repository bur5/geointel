"""Download public bulk datasets for the risk snapshot (run in CI, not in tests)."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from geointel.risk.sources import usgs

UCDP_ACD_VERSIONS = ("26.1", "25.1", "24.1")
COUPS_URLS = (
    "https://www.uky.edu/~clthyn2/coup_data/powell_thyne_coups_final.txt",
    "http://www.uky.edu/~clthyn2/coup_data/powell_thyne_coups_final.txt",
)
USER_AGENT = "GeoIntel risk snapshot (https://github.com/bur5/geointel)"


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


def _download(client: httpx.Client, url: str) -> bytes:
    response = client.get(url)
    response.raise_for_status()
    if not response.content:
        raise ValueError("empty response")
    return response.content


def fetch_all(raw_dir: Path) -> dict:
    """Download each source independently; failures are recorded, never fatal."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    targets = {
        "ucdp_acd": ucdp_acd_urls(),
        "coups": [(u, "live") for u in (os.environ.get("GEOINTEL_COUPS_URL"),) if u]
        or [(u, "live") for u in COUPS_URLS],
        "usgs": [(usgs.query_url(), "live")],
    }
    filenames = {"ucdp_acd": "ucdp_acd.bin", "coups": "coups.txt", "usgs": "usgs.csv"}
    with httpx.Client(
        timeout=120,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "text/plain, text/csv, */*"},
    ) as client:
        for key, candidates in targets.items():
            errors = []
            for url, version in candidates:
                try:
                    payload = _download(client, url)
                except Exception as exc:  # noqa: BLE001 - recorded in the manifest
                    errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:200]}")
                    continue
                (raw_dir / filenames[key]).write_bytes(payload)
                manifest[key] = {
                    "status": "ok",
                    "url": url,
                    "version": version,
                    "bytes": len(payload),
                    "file": filenames[key],
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "errors": errors,
                }
                break
            else:
                manifest[key] = {"status": "failed", "errors": errors}
    (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
