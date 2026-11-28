"""UCDP Conflict Termination dataset: how each episode of armed conflict ended.

Fable round 4, #5: a country whose last internal conflict ended in a victory or an agreement
is less likely to see it resume than one where fighting just fell below the threshold.
Outcome codes (codebook v4): 1 peace agreement, 2 ceasefire, 3 victory for the government
side, 4 victory for the opposition side, 5 low activity, 6 actor ceases to exist.

Used as a feature of a trained correction on top of the base onset rate, tested on the time
machine before any live use. Licence: UCDP data are free to use with citation (Kreutz 2010).
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Mapping

from geointel.risk.countries import resolve_country_name

DOWNLOADS = "https://ucdp.uu.se/downloads/"
SOURCE = "UCDP Conflict Termination dataset (Kreutz 2010)"
DECISIVE = {1, 3, 4, 6}  # agreement, victory, actor gone
SOFT = {2, 5}  # ceasefire, low activity
INTERNAL_TYPES = {"3", "4"}


def pick_url(html: str) -> str | None:
    found = re.findall(
        r'href="([^"]*UCDPConflictTerminationDataset_v(\d+)_(\d+)_Conflict\.csv)"', html
    )
    if not found:
        return None
    return max(found, key=lambda m: (int(m[2]), int(m[1])))[0]


def _split(value: str) -> list[str]:
    return [p.strip() for p in re.split(r",\s*", value or "") if p.strip()]


def episodes(text: str) -> dict[str, list[tuple[int, int]]]:
    """ISO3 -> [(last year of fighting, outcome code)] for ended internal-conflict episodes."""
    out: dict[str, set[tuple[int, int]]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if str(row.get("type_of_conflict") or "").strip() not in INTERNAL_TYPES:
            continue
        if str(row.get("c_epterm") or "").strip() != "1":
            continue
        try:
            end = int(float(row.get("c_ep_endyear") or ""))
            outcome = int(float(row.get("c_outcome") or ""))
        except ValueError:
            continue
        for label in _split(row.get("location", "")):
            code = resolve_country_name(label)
            if code:
                out.setdefault(code, set()).add((end, outcome))
    return {k: sorted(v) for k, v in out.items()}


def features(
    ended: Mapping[str, list[tuple[int, int]]], iso3: str, known_until: int
) -> list[float]:
    """[1, last episode decisive, last episode soft, log(1 + years since it ended)], using only
    episodes that ended by ``known_until``. No ended episode: zeros and 50 years."""
    past = [(y, o) for y, o in ended.get(iso3, []) if y <= known_until]
    if not past:
        return [1.0, 0.0, 0.0, math.log1p(50)]
    year, outcome = max(past)
    return [
        1.0,
        float(outcome in DECISIVE),
        float(outcome in SOFT),
        math.log1p(min(known_until - year, 50)),
    ]
