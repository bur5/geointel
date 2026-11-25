"""Powell & Thyne global instances of coups (attempted and successful).

The published text file has a header ``country ccode ccode_gw ccode_polity year month day
coup version`` but rows may omit the optional code columns, so rows are parsed by token
position: the quoted country first, then numbers, with year, month, day and coup being the
last four numeric tokens.
"""

import shlex
from collections import defaultdict

from geointel.risk.countries import resolve_country_name
from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType

SOURCE = "Powell & Thyne Global Instances of Coups"


def _parse_line(line: str) -> tuple[str, int, int] | None:
    try:
        tokens = shlex.split(line.replace("\t", " "))
    except ValueError:
        return None
    if len(tokens) < 5:
        return None
    numbers = []
    for token in tokens[1:]:
        try:
            numbers.append(int(float(token)))
        except ValueError:
            continue
    if len(numbers) < 4:
        return None
    year, _month, _day, outcome = numbers[-4:]
    return tokens[0], year, outcome


def parse(text: str, reference_year: int, start_year: int = 1990) -> TypeHistory:
    """Count coup years through ``reference_year - 1`` (the last complete year)."""
    data: dict[str, set[int]] = defaultdict(set)
    unresolved = rows = 0
    end_year = reference_year - 1
    version = None
    for line in text.splitlines()[1:]:
        parsed = _parse_line(line)
        if parsed is None:
            continue
        country, year, outcome = parsed
        if version is None and line.rstrip().endswith('"'):
            version = shlex.split(line)[-1]
        if year < start_year or year > end_year or outcome not in (1, 2):
            continue
        rows += 1
        code = resolve_country_name(country)
        if code:
            data[code].add(year)
        else:
            unresolved += 1
    return TypeHistory(
        event_type=EventType.COUP_ATTEMPT,
        source=SOURCE,
        start_year=start_year,
        end_year=end_year,
        years_with_event={k: frozenset(v) for k, v in data.items()},
        half_life_years=10.0,
        unresolved_labels=unresolved,
        records=rows,
        metadata={"dataset_version": version} if version else {},
    )


CLINE_SOURCE = "Cline Center Coup d'État Project"
CLINE_LANDING = "https://databank.illinois.edu/datasets/IDB-9651987"
CLINE_LANDINGS = (
    "https://aws-databank-alb.library.illinois.edu/datasets/IDB-7095878",
    CLINE_LANDING,
)
# Direct links to "Coup data 2.2.2.csv" (version 10, released 17 February 2026, licence CC BY).
# The main databank page builds its file list with JavaScript, so the links are kept here and
# the landing pages are only a fallback for newer versions.
CLINE_FILES = (
    "https://databank.illinois.edu/datafiles/yfjyv/download",
    "https://aws-databank-alb.library.illinois.edu/datafiles/yfjyv/download",
)
CLINE_LICENCE = "CC BY 4.0 — Cline Center for Advanced Social Research, University of Illinois"


def cline_csv_links(html: str) -> list[str]:
    """Download links of CSV files on the Illinois Data Bank landing page (newest first)."""
    import re

    links = []
    matches = list(
        re.finditer(
            r"href=[\"'](?:https?://databank\.illinois\.edu)?(/datafiles/[A-Za-z0-9_-]+/download)",
            html,
        )
    )
    for i, match in enumerate(matches):
        # the file name sits between this link and the next one (or just before it)
        before = html[matches[i - 1].end() if i else max(0, match.start() - 400) : match.start()]
        after = html[match.end() : matches[i + 1].start() if i + 1 < len(matches) else None][:400]
        name = (after.split("href=")[0] or before).lower()
        if ".csv" in name and "coup" in name:
            links.append("https://databank.illinois.edu" + match.group(1))
            links.append("https://aws-databank-alb.library.illinois.edu" + match.group(1))
    return list(dict.fromkeys(links))


def parse_cline(text: str, reference_year: int, start_year: int = 1990) -> TypeHistory:
    """Realised and attempted coups (conspiracies excluded) from the Cline Center CSV."""
    import csv
    import io

    data: dict[str, set[int]] = defaultdict(set)
    unresolved = rows = 0
    end_year = reference_year - 1
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        row = {str(k).strip().lower(): str(v or "").strip() for k, v in row.items()}
        try:
            year = int(float(row.get("year", "")))
        except ValueError:
            continue
        kind = row.get("event_type", "").lower()
        conspiracy = row.get("conspiracy") == "1" or kind.startswith("consp")
        if conspiracy or year < start_year or year > end_year:
            continue
        rows += 1
        code = resolve_country_name(row.get("country", ""))
        if code:
            data[code].add(year)
        else:
            unresolved += 1
    return TypeHistory(
        event_type=EventType.COUP_ATTEMPT,
        source=CLINE_SOURCE,
        start_year=start_year,
        end_year=end_year,
        years_with_event={k: frozenset(v) for k, v in data.items()},
        half_life_years=10.0,
        unresolved_labels=unresolved,
        records=rows,
        metadata={"dataset": "Cline Center v2.2"},
    )


def parse_any(text: str, reference_year: int) -> TypeHistory:
    head = text.lstrip("﻿")[:300].lower()
    if "coup_id" in head or ("year" in head and "," in head.splitlines()[0]):
        return parse_cline(text, reference_year)
    return parse(text, reference_year)
