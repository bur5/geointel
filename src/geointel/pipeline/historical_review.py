"""Deterministic historical misuse checks on structured claims and bounded narrative."""

import re

from geointel.domain.schemas import ConflictType, NormalizedConflictType
from geointel.pipeline.taxonomy import MAPPING_VERSION

FORECAST_HISTORY_TYPES = {
    ConflictType.INTERSTATE: NormalizedConflictType.INTERSTATE_ARMED_CONFLICT,
    ConflictType.INTERNAL: NormalizedConflictType.INTERNAL_ARMED_CONFLICT,
    ConflictType.ONE_SIDED: NormalizedConflictType.ONE_SIDED_VIOLENCE,
    ConflictType.POLITICAL: NormalizedConflictType.MAJOR_POLITICAL_VIOLENCE,
}


def historical_context(profile: dict, kind: ConflictType | None = None) -> str:
    if kind is not None:
        target = FORECAST_HISTORY_TYPES[kind].value
        count = profile["conflict_types"][target]["observation_statistics"]["observation_count"]
        return (
            f"Historical observations mapped to {target}: {count} retrieved observations. "
            "This is descriptive background, not current activity or a forecast probability; "
            "zero retrieved observations do not establish historical absence."
        )
    supported = [
        key
        for key, value in profile["conflict_types"].items()
        if value["historical_presence"] and key != "OTHER_OR_UNRESOLVED"
    ]
    return (
        "Historical base-rate context available: normalized types "
        + (", ".join(sorted(supported)) or "none safely mapped")
        + f"; {profile['unresolved_observation_count']} unresolved observations retained. "
        "Descriptive historical features are not current evidence, escalation evidence or "
        "forecast probabilities."
    )


def review_historical_claims(payload: dict) -> dict[str, list[str]]:
    profile = payload.get("historical_conflict_profile")
    if not profile or profile.get("status") != "available":
        return {}
    taxonomy, semantics, coverage = [], [], []
    audit = profile.get("normalization_audit", [])
    total = profile.get("overall", {}).get("observation_statistics", {}).get("observation_count", 0)
    if len(audit) != total or any(not x.get("mapping_method_version") for x in audit):
        taxonomy.append(
            "Historical taxonomy lacks an explicit versioned mapping for every observation."
        )
    for mapping in audit:
        direct = (
            mapping.get("provider") == "UCDP"
            and mapping.get("provider_dataset") == "GED"
            and mapping.get("provider_original_category") == "type_of_violence"
            and type(mapping.get("provider_original_value")) is int
            and mapping["provider_original_value"] == 3
        )
        expected_type = "ONE_SIDED_VIOLENCE" if direct else "OTHER_OR_UNRESOLVED"
        if (
            mapping.get("normalized_conflict_type") != expected_type
            or mapping.get("mapping_method_version") != MAPPING_VERSION
        ):
            taxonomy.append(
                "Provider category was normalized without the reviewed deterministic mapping."
            )
    unresolved = sum(x.get("normalized_conflict_type") == "OTHER_OR_UNRESOLVED" for x in audit)
    expected = profile.get("unresolved_observation_count", 0)
    grouped = sum(
        x.get("observation_statistics", {}).get("observation_count", 0)
        for x in profile.get("conflict_types", {}).values()
    )
    if unresolved != expected or grouped != total:
        taxonomy.append("Unresolved taxonomy mappings were hidden, discarded or miscounted.")
    analysis = payload.get("analysis", {})
    output_profile = analysis.get("historical_conflict_profile")
    if output_profile is not None and output_profile != profile:
        taxonomy.append("Analyst historical profile differs from the supplied auditable profile.")
    texts = []

    def walk(value):
        if isinstance(value, str):
            texts.append(value.lower())
        elif isinstance(value, dict):
            # Audit structures are data, not analytical assertions.
            for key, child in value.items():
                if key not in {"historical_conflict_profile", "historical_base_rate_summary"}:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(analysis)
    walk(payload.get("forecast", {}))
    # Match positive misuse assertions; disclaimers containing 'not'/'never'/'cannot' are excluded.
    patterns = [
        (
            r"\b\d+\s+(?:historical\s+)?(?:conflicts|episodes)\b|"
            r"observation(?:s|_count)? (?:are|is|equals|means) (?:the )?(?:conflict|episode)",
            "Historical observation counts were described as conflict or episode counts.",
        ),
        (
            r"fatalit(?:y|ies).*?(?:are|is|equals|means|measure) (?:the "
            r")?(?:event|observation) (?:count|frequency)",
            "Historical fatality totals were described as event frequency.",
        ),
        (
            r"historical "
            r"(?:frequency|presence|share).*?(?:implies|means|yields|is|increases).*?(?:probability|risk|likely|escalation|current|active)",
            "Historical frequency or presence was promoted to probability, "
            "current activity or escalation.",
        ),
    ]
    for text in texts:
        for clause in re.split(r"[.;\n]", text):
            if re.search(r"\b(?:not|never|cannot|without|no)\b", clause):
                continue
            for pattern, finding in patterns:
                if re.search(pattern, clause):
                    semantics.append(finding)
            if re.search(
                r"latest (?:historical "
                r")?observation.*?(?:is|equals|defines|establishes).*?coverage end",
                clause,
            ):
                coverage.append("Latest observation was treated as dataset coverage end.")
            if re.search(r"missing years.*?(?:are|mean|as|equals).*?(?:zero|no.conflict)", clause):
                coverage.append(
                    "Missing years were treated as zero-conflict years without validated coverage."
                )
            if re.search(
                r"(?:type_of_violence|provider "
                r"(?:code|category)).*?(?:means|is|equals).*?(?:internal|interstate|political)",
                clause,
            ):
                taxonomy.append(
                    "Provider category was treated as a normalized category without a "
                    "reviewed mapping."
                )
    for c in profile.get("coverage", []):
        if (
            c.get("reference_basis") == "latest_observation_not_dataset_coverage"
            and c.get("coverage_end") is not None
        ):
            coverage.append("Observation reference was silently promoted to dataset coverage end.")
    if profile.get("annualized_observation_rate") is not None:
        coverage.append("Annualized historical rate lacks a validated retrieval denominator.")
    if (
        payload.get("escalation_indicators")
        and not payload.get("recent_events")
        and not payload.get("observed_evidence")
    ):
        semantics.append("Historical-only inputs were used as escalation indicators.")
    return {
        "taxonomy_normalization_concerns": sorted(set(taxonomy)),
        "historical_semantic_concerns": sorted(set(semantics)),
        "base_rate_concerns": sorted(set(coverage)),
    }
