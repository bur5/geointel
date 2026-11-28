"""Regional (first-level administrative) view of natural hazards and, later, conflicts.

Why: a cyclone in Florida must not paint the whole United States orange. For every region we
estimate how often each hazard has struck it (shrunk towards the other regions of the same
country, empirical Bayes), name notable features (volcanoes, the highest recorded tsunami
wave), and give each region a current level from active alerts. A country's headline level is
the level at which most of its population lives (population-weighted median), shown next to
the most affected regions and the share of the population there.

Population per region comes from the GHSL population grid (1.12.0) when its cache is present,
otherwise from GeoNames cities of 15,000+ inhabitants (a proxy that misses rural people).
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping

from geointel.risk.model import Counts, fit_prior, posterior
from geointel.risk.popgrid import PopGrid
from geointel.risk.regions import RegionIndex, region_list

HAZARD_KEYS = {
    "EQ": "major_earthquake",
    "TS": "tsunami",
    "TC": "tropical_cyclone",
    "FL": "flood",
    "VO": "volcano",
    "DR": "drought",
    "WF": "wildfire",
}
# Severity class of each hazard for the frequency bands (see danger.py).
HAZARD_CLASS = {
    "major_earthquake": "A",
    "tsunami": "A",
    "tropical_cyclone": "B",
    "flood": "B",
    "volcano": "B",
    "drought": "C",
    "wildfire": "C",
}
BANDS = {"A": (0.02, 0.05, 0.20), "B": (0.03, 0.15, 0.5), "C": (0.15, 0.5, 2.0)}
ALERT_LEVEL = {"Red": 4, "Orange": 3}
MIN_EVENTS = 5  # fewer events in a region: show the country estimate instead


def _band(hazard: str, p: float) -> int:
    return 1 + sum(1 for x in BANDS[HAZARD_CLASS[hazard]] if p >= x)


def region_population(
    index: RegionIndex, iso3: str, cities: Iterable[tuple[float, float, int]]
) -> dict[str, int]:
    pop: dict[str, int] = defaultdict(int)
    for lat, lon, n in cities:
        found = index.locate(iso3, lat, lon)
        if found:
            pop[found[2]] += n
    return dict(pop)


def weighted_median(levels: list[tuple[int, float]]) -> int:
    total = sum(w for _, w in levels)
    if total <= 0:
        return max((lvl for lvl, _ in levels), default=1)
    acc = 0.0
    for level, weight in sorted(levels):
        acc += weight
        if acc >= total / 2:
            return level
    return levels[-1][0]


def _height(severity: str) -> float | None:
    for part in str(severity or "").split(","):
        part = part.strip()
        if part.endswith(" m"):
            try:
                return float(part[:-2])
            except ValueError:
                return None
    return None


def build_regional(
    index: RegionIndex,
    hazard_events: Iterable[Mapping],
    alerts: Mapping[str, list[dict]] | None,
    cities: Mapping[str, list[tuple[float, float, int]]] | None,
    volcanoes: Iterable[Mapping] | None,
    end_year: int,
    extra_levels: Mapping[str, Mapping[str, dict]] | None = None,
    popgrid: PopGrid | None = None,
) -> dict:
    """Per country: regions with population, hazard frequencies, notable features and level.

    ``extra_levels``: iso3 -> region code -> {"level", "reason_ru", "reason_en"} from other
    regional layers (conflicts), merged into the region level.
    """
    events_by = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))  # iso3/haz/code→years
    country_years = defaultdict(lambda: defaultdict(set))
    tsunami_max = defaultdict(dict)
    usable = [e for e in hazard_events if HAZARD_KEYS.get(e.get("hazard", "")) and e.get("year")]
    # One source per hazard, with the window from that source's own start (1.12.0): mixing
    # USGS (from 1900) with GDACS (from about 2000) under the earliest world-wide year
    # understated GDACS frequencies. The source with the longest record is used.
    starts: dict[tuple[str, str], int] = {}
    for e in usable:
        key = (HAZARD_KEYS[e["hazard"]], str(e.get("source") or ""))
        starts[key] = min(starts.get(key, e["year"]), e["year"])
    source_of: dict[str, str] = {}
    first_year: dict[str, int] = {}
    for (hazard, source), start in sorted(starts.items(), key=lambda kv: (kv[1], kv[0][1])):
        if hazard not in source_of:
            source_of[hazard], first_year[hazard] = source, start
    for e in usable:
        hazard = HAZARD_KEYS[e["hazard"]]
        if str(e.get("source") or "") != source_of[hazard]:
            continue
        codes = list(e.get("countries") or [])
        for code in codes:
            country_years[code][hazard].add(e["year"])
        # Events that hit several countries (cyclones, floods, tsunamis) are placed in the
        # nearest region of each country they hit (1.12.0); before, they were skipped.
        located: dict[str, str] = {}
        if e.get("region_code") and len(codes) == 1:
            located[codes[0]] = e["region_code"]
        elif len(codes) > 1 and e.get("lat") is not None and e.get("lon") is not None:
            for code in codes:
                found = index.locate(code, e["lat"], e["lon"])
                if found:
                    located[code] = found[2]
        for iso3, region in located.items():
            events_by[iso3][hazard][region].add(e["year"])
            if hazard == "tsunami":
                h = _height(e.get("severity", ""))
                if h is not None:
                    best = tsunami_max[iso3].get(region)
                    if best is None or h > best["height"]:
                        tsunami_max[iso3][region] = {
                            "height": h,
                            "year": e["year"],
                            "place": e.get("name", ""),
                        }
    volcano_by = defaultdict(lambda: defaultdict(list))
    for v in volcanoes or []:
        if not v.get("country") or v.get("last_eruption") is None or v["last_eruption"] < 1900:
            continue
        found = index.locate(v["country"], v["lat"], v["lon"])
        if found:
            volcano_by[v["country"]][found[2]].append(v)
    alert_by = defaultdict(lambda: defaultdict(list))
    for iso3, items in (alerts or {}).items():
        for a in items:
            if a.get("lat") is None or a.get("lon") is None:
                continue
            found = index.locate(iso3, a["lat"], a["lon"])
            if found:
                alert_by[iso3][found[2]].append(a)

    countries = {}
    for iso3 in index.by_country:
        regions = region_list(index, iso3)
        if not regions:
            continue
        grid_pop = popgrid.region_population(iso3) if popgrid else {}
        pop = grid_pop or region_population(index, iso3, (cities or {}).get(iso3, []))
        hazards_out = {}
        for hazard, start in first_year.items():
            n = max(end_year - start + 1, 1)
            by_region = events_by[iso3][hazard]
            counts = {
                r["code"]: Counts(float(len(by_region.get(r["code"], ()))), float(n))
                for r in regions
            }
            if not any(c.successes for c in counts.values()):
                continue
            prior = fit_prior(counts.values())
            rows = []
            for r in regions:
                c = counts[r["code"]]
                est = posterior(prior, c)
                rows.append(
                    {
                        "code": r["code"],
                        "years": int(c.successes),
                        "p_year": round(est.mean, 4),
                        "band": _band(hazard, est.mean),
                        "own_estimate": c.successes >= MIN_EVENTS,
                    }
                )
            rows.sort(key=lambda x: -x["p_year"])
            hazards_out[hazard] = {
                "window": [start, end_year],
                "country_years": len(country_years[iso3][hazard]),
                "regions": rows[:12],
            }
        region_rows = []
        for r in regions:
            code = r["code"]
            reasons, level = [], 1
            for a in alert_by[iso3].get(code, []):
                lvl = ALERT_LEVEL.get(a.get("alert"), 1)
                if lvl > level:
                    level = lvl
                reasons.append(
                    {
                        "kind": "alert",
                        "hazard": HAZARD_KEYS.get(a.get("hazard"), ""),
                        "name": a.get("name", ""),
                        "alert": a.get("alert"),
                        "date": a.get("date"),
                        "level": lvl,
                    }
                )
            base_level = level
            zone = None
            extra = ((extra_levels or {}).get(iso3) or {}).get(code)
            if extra:
                level = max(level, int(extra["level"]))
                hot = extra.get("hot_cells") or []
                if grid_pop and hot and level > base_level:
                    zone = popgrid.zone_population(iso3, code, [tuple(x) for x in hot])
                reasons.append(
                    {"kind": "extra", **{k: v for k, v in extra.items() if k != "hot_cells"}}
                )
            people = pop.get(code, 0)
            region_rows.append(
                {
                    **r,
                    "population": people,
                    "level": level,
                    "base_level": base_level,
                    "zone_population": min(zone, people) if zone is not None else None,
                    "reasons": reasons,
                    "volcanoes": sorted(
                        (
                            {
                                "name": v["name"],
                                "last_eruption": v["last_eruption"],
                                "elevation": v.get("elevation"),
                            }
                            for v in volcano_by[iso3].get(code, [])
                        ),
                        key=lambda v: -v["last_eruption"],
                    )[:5],
                    "tsunami_max": tsunami_max[iso3].get(code),
                }
            )
        total_pop = sum(r["population"] for r in region_rows)
        weights = []
        for r in region_rows:
            if not total_pop:
                weights.append((r["level"], 1.0))
            elif r["zone_population"] is not None:
                weights.append((r["level"], r["zone_population"]))
                weights.append((r["base_level"], r["population"] - r["zone_population"]))
            else:
                weights.append((r["level"], r["population"]))
        median = weighted_median(weights)
        top = max(r["level"] for r in region_rows)
        affected = [r for r in region_rows if r["level"] == top and top > median]

        def exposed(r: Mapping) -> int:
            return r["population"] if r["zone_population"] is None else r["zone_population"]

        share = sum(exposed(r) for r in affected) / total_pop if total_pop and affected else None
        countries[iso3] = {
            "level_median": median,
            "level_max": top,
            "max_regions": [{"code": r["code"], "en": r["en"], "ru": r["ru"]} for r in affected],
            "max_population_share": round(share, 3) if share is not None else None,
            "population_known": total_pop > 0,
            "population_source": "ghsl" if grid_pop else "cities" if total_pop else None,
            "regions": region_rows,
            "hazards": hazards_out,
        }
    return countries
