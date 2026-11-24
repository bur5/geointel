"""Deterministic historical features; no forecast probabilities or inferred zero years."""

from collections import defaultdict
from datetime import date
from statistics import median

from geointel.domain.schemas import (
    HistoricalBaseRateSummary,
    HistoricalConflictFeatures,
    HistoricalConflictProfile,
    HistoricalDatasetCoverage,
    HistoricalFatalityStatistics,
    HistoricalObservationStatistics,
    NormalizedConflictType,
    NormalizedEvidence,
)
from geointel.pipeline.taxonomy import normalize_historical_type

HISTORICAL_ROLES = {"annual_historical", "historical"}


def evidence_role(item: NormalizedEvidence) -> str:
    return item.provenance.get("temporal_role", "unclassified")


def is_historical(item: NormalizedEvidence) -> bool:
    return evidence_role(item) in HISTORICAL_ROLES


def is_current(item: NormalizedEvidence) -> bool:
    return evidence_role(item) in {"current_operational", "recent_operational"}


def _date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def summarize_history(records, geography: str, analysis_date: date) -> HistoricalBaseRateSummary:
    records = [item for item in records if is_historical(item)]
    dates = sorted(item.event_date.date() for item in records if item.event_date)
    years = {value.year for value in dates}
    groups = defaultdict(list)
    for item in records:
        key = _coverage_key(item)
        groups[key].append(item)
    coverage, windows = [], {}
    for index, (key, items) in enumerate(sorted(groups.items(), key=lambda pair: str(pair[0]))):
        provider, dataset, resource, version, role, geo_id, start, end, reference = key
        observed = sorted(item.event_date.date() for item in items if item.event_date)
        end, reference = _date(end), _date(reference)
        ref = reference or end or (observed[-1] if observed else None)
        coverage.append(
            HistoricalDatasetCoverage(
                provider=provider,
                dataset=dataset,
                resource=resource,
                dataset_version=version,
                temporal_role=role,
                requested_geography=geography,
                resolved_provider_geography_id=geo_id,
                earliest_observed_date=observed[0] if observed else None,
                latest_observed_date=observed[-1] if observed else None,
                coverage_start=_date(start),
                coverage_end=end,
                reference_date=ref,
                reference_basis="provider_reference"
                if reference
                else "dataset_coverage_end"
                if end
                else "latest_observation_not_dataset_coverage",
                coverage_semantics=items[0].provenance.get("coverage_semantics"),
                observation_count=len(items),
            )
        )
        if ref:
            windows[str(index)] = {}
            for span in (5, 10, 20):
                # Calendar windows (reference minus N years, reference], leap-safe.
                cutoff = (
                    ref.replace(year=ref.year - span, day=min(ref.day, 28))
                    if (ref.month == 2 and ref.day == 29)
                    else ref.replace(year=ref.year - span)
                )
                windows[str(index)][f"{span}y"] = sum(cutoff < d <= ref for d in observed)
    fatalities = {}
    values = {}
    for field in ("best", "low", "high"):
        values[field] = [(item.provenance.get("fatalities") or {}).get(field) for item in records]
        values[field] = [v for v in values[field] if type(v) is int and v >= 0]
        fatalities[f"{field}_total"] = sum(values[field]) if values[field] else None
        fatalities[f"{field}_available_count"] = len(values[field])
    categories, available = {}, {}
    for field in ("type_of_violence", "conflict_type", "category"):
        counts = defaultdict(int)
        for item in records:
            value = item.provenance.get(field)
            if value is not None and isinstance(value, (str, int)):
                counts[str(value)] += 1
        if counts:
            categories[field] = dict(sorted(counts.items()))
            available[field] = sum(counts.values())
    return HistoricalBaseRateSummary(
        status="available" if records else "unavailable",
        geography=geography,
        coverage=coverage,
        observation_statistics=HistoricalObservationStatistics(
            observation_count=len(records),
            dated_observation_count=len(dates),
            earliest_observation_date=dates[0] if dates else None,
            latest_observation_date=dates[-1] if dates else None,
            earliest_year=min(years) if years else None,
            latest_year=max(years) if years else None,
            observed_year_span=max(years) - min(years) + 1 if years else None,
            distinct_observed_year_count=len(years),
            years_since_latest_observation=max(0, analysis_date.year - max(years))
            if years
            else None,
        ),
        fatality_statistics=HistoricalFatalityStatistics(
            **fatalities,
            median_best_per_observation=median(values["best"]) if values["best"] else None,
            maximum_best_per_observation=max(values["best"]) if values["best"] else None,
        ),
        trailing_window_counts=windows,
        category_statistics=categories,
        category_available_counts=available,
        caveats=[
            "Historical observations are context/features, not forecast probabilities.",
            "Absence after dataset coverage end cannot establish absence of violence.",
            "Observed date span is not complete dataset coverage; unobserved years are not zeros.",
            "Fatality totals aggregate available values only; counts report field completeness.",
            "Sparse history cannot establish a trend; missing categories are not inferred.",
            "Trailing windows use each coverage entry's reference date, not the analysis date.",
        ],
    )


def _coverage_key(item: NormalizedEvidence) -> tuple:
    p = item.provenance
    return (
        item.source_name,
        p.get("dataset"),
        p.get("endpoint"),
        p.get("dataset_version"),
        evidence_role(item),
        p.get("resolved_ucdp_country_id") or p.get("country_id"),
        p.get("coverage_start"),
        p.get("coverage_end"),
        p.get("reference_date"),
    )


def build_conflict_profile(
    records, geography: str, analysis_date: date
) -> HistoricalConflictProfile:
    records = [item for item in records if is_historical(item)]
    summary = summarize_history(records, geography, analysis_date)
    keys = sorted({_coverage_key(item) for item in records}, key=str)
    audit = [normalize_historical_type(item, geography) for item in records]
    for item, mapping in zip(records, audit, strict=True):
        mapping.coverage_index = str(keys.index(_coverage_key(item)))

    def features(items, mappings):
        stats = summarize_history(items, geography, analysis_date)
        windows = {}
        # Every type uses the same dataset reference, including types with no retrieved rows.
        for index, coverage in enumerate(summary.coverage):
            ref = coverage.reference_date
            if ref is None:
                continue
            dates = [
                item.event_date.date()
                for item, mapping in zip(items, mappings, strict=True)
                if item.event_date and mapping.coverage_index == str(index)
            ]
            windows[str(index)] = {}
            for span in (5, 10, 20):
                cutoff = (
                    ref.replace(year=ref.year - span, day=28)
                    if (ref.month == 2 and ref.day == 29)
                    else ref.replace(year=ref.year - span)
                )
                windows[str(index)][f"{span}y"] = sum(cutoff < d <= ref for d in dates)
        return HistoricalConflictFeatures(
            observation_statistics=stats.observation_statistics,
            fatality_statistics=stats.fatality_statistics,
            historical_presence=bool(items),
            share_of_retrieved_historical_observations=len(items) / len(records)
            if records
            else None,
            trailing_window_counts=windows,
        )

    per_type = {}
    for kind in NormalizedConflictType:
        selected = [
            (item, mapping)
            for item, mapping in zip(records, audit, strict=True)
            if mapping.normalized_conflict_type == kind
        ]
        per_type[kind] = features([x[0] for x in selected], [x[1] for x in selected])
    unknown_coverage = not summary.coverage or any(
        c.coverage_start is None or c.coverage_end is None for c in summary.coverage
    )
    return HistoricalConflictProfile(
        status=summary.status,
        geography=geography,
        analysis_date=analysis_date,
        coverage=summary.coverage,
        overall=features(records, audit),
        conflict_types=per_type,
        unresolved_observation_count=per_type[
            NormalizedConflictType.OTHER_OR_UNRESOLVED
        ].observation_statistics.observation_count,
        normalization_audit=sorted(audit, key=lambda x: x.model_dump_json()),
        annualized_rate_status="UNAVAILABLE_UNKNOWN_COVERAGE"
        if unknown_coverage
        else "UNAVAILABLE_UNVALIDATED_DENOMINATOR",
        caveats=summary.caveats
        + [
            "Observation rows, distinct observed years, episodes and "
            "fatalities are different units.",
            "No episode counts are inferred; zero retrieved observations do not establish absence.",
            "Shares use retrieved historical observations, not a population "
            "or temporal denominator.",
            "Coverage boundaries alone do not validate complete retrieval or zero-conflict years.",
            "Unresolved mappings are retained; historical presence is not "
            "current activity or escalation.",
            "Per-type windows use the overall dataset reference, not per-type latest observations.",
            "Multiple datasets may overlap; totals count retrieved rows, not independent events.",
        ],
    )
