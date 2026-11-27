"""Cloudflare Radar Outage Center: verified internet outages by country.

A second source for internet shutdowns next to IODA (which often refuses connections from
GitHub runners). Needs a read-only API token (``CLOUDFLARE_RADAR_TOKEN``, Radar Read).
Government-directed shutdowns and outages caused by military action count as a warning
sign; power cuts, cable cuts and weather are shown but do not light the sign.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date

SOURCE = "Cloudflare Radar Outage Center"
OUTAGES_URL = "https://api.cloudflare.com/client/v4/radar/annotations/outages"
POLITICAL_CAUSES = ("GOVERNMENT", "MILITARY", "CONFLICT", "WAR")


def outages(payload: Mapping) -> list[dict]:
    """Compact outage records from an API response."""
    result = payload.get("result") or {}
    items = result.get("annotations") if isinstance(result, Mapping) else None
    out = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        codes = [str(c).upper() for c in item.get("locations") or [] if c]
        if not codes:
            codes = [
                str(d.get("code") or "").upper()
                for d in item.get("locationsDetails") or []
                if isinstance(d, Mapping) and d.get("code")
            ]
        outage = item.get("outage") or {}
        out.append(
            {
                "countries": [c for c in codes if len(c) == 2],
                "start": str(item.get("startDate") or "")[:10],
                "end": str(item.get("endDate") or "")[:10] or None,
                "cause": str(outage.get("outageCause") or ""),
                "type": str(outage.get("outageType") or ""),
                "description": str(item.get("description") or "")[:240],
                "url": item.get("linkedUrl"),
            }
        )
    return out


def political(cause: str) -> bool:
    return any(word in cause.upper() for word in POLITICAL_CAUSES)


def by_country(
    records: Iterable[Mapping], iso2_to_iso3: Mapping[str, str], today: date, days: int = 7
) -> dict[str, list[dict]]:
    """Outages that started in the last ``days`` days or are still going, per ISO3."""
    out: dict[str, list[dict]] = {}
    for record in records:
        start = record.get("start") or ""
        end = record.get("end")
        try:
            started = date.fromisoformat(start)
        except ValueError:
            continue
        recent = (today - started).days <= days
        ongoing = not end or end >= today.isoformat()
        if not (recent or ongoing):
            continue
        for code in record.get("countries") or []:
            iso3 = iso2_to_iso3.get(code)
            if iso3:
                out.setdefault(iso3, []).append(dict(record))
    return out
