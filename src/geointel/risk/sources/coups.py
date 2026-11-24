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
