"""Strategic rivalries (Thompson, Dreyer, Sakuwa and others, as packaged in the R package
``peacesciencer`` by Steven V. Miller): pairs of states that treat each other as competitors
and enemies. Used by the time machine (experiment C) only.

Caveats: rivalries are coded by historians with hindsight, so a rivalry that started shortly
before a war may be recorded knowing the war happened; the data end in 2020, and a rivalry
ongoing in 2020 is assumed to continue.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

DATA = "https://raw.githubusercontent.com/svmiller/peacesciencer/master/data/tss_rivalries.rda"
STATES = "https://raw.githubusercontent.com/svmiller/peacesciencer/master/data/cow_states.rda"
SOURCE = "Strategic rivalries (Thompson et al. 2021) via peacesciencer"
CARRY_TO = 2030


def active_years(
    rows: Iterable[Mapping], ccode_to_iso3: Mapping[int, str], data_end: int = 2020
) -> dict[str, set[int]]:
    """ISO3 -> years in which the country had an ongoing strategic rivalry."""
    out: dict[str, set[int]] = {}
    for row in rows:
        try:
            start = int(row.get("start") or row.get("styear"))
            end = int(row.get("end") or row.get("endyear") or data_end)
        except (TypeError, ValueError):
            continue
        if end >= data_end:
            end = CARRY_TO
        for key in ("ccode1", "ccode2"):
            try:
                code = ccode_to_iso3.get(int(row.get(key)))
            except (TypeError, ValueError):
                code = None
            if code:
                out.setdefault(code, set()).update(range(start, end + 1))
    return out


def load(rivalries_rda: str, states_rda: str) -> dict[str, set[int]]:
    import pyreadr

    from geointel.risk.countries import resolve_country_name

    states = next(iter(pyreadr.read_r(states_rda).values()))
    names: dict[int, str] = {}
    for row in states.to_dict("records"):
        code = resolve_country_name(str(row.get("statenme") or ""))
        if code:
            names[int(row["ccode"])] = code
    frame = next(iter(pyreadr.read_r(rivalries_rda).values()))
    print("[rivalries] columns:", list(frame.columns))
    return active_years(frame.to_dict("records"), names)
