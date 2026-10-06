"""Reviewed deterministic mappings; provider labels never establish current activity."""

from geointel.domain.schemas import (
    HistoricalTaxonomyMapping,
    NormalizedConflictType,
    NormalizedEvidence,
)

MAPPING_VERSION = "provider-conflict-taxonomy-v1"
UCDP_MAPPING_SOURCE = "https://ucdp.uu.se/downloads/ged/ged261.pdf"
UCDP_MEANINGS = {1: "state-based conflict", 2: "non-state conflict", 3: "one-sided violence"}


def normalize_historical_type(
    item: NormalizedEvidence, geography: str
) -> HistoricalTaxonomyMapping:
    p = item.provenance
    categories = {
        key: p[key] for key in ("type_of_violence", "conflict_type", "category") if key in p
    }
    category = next(iter(categories), None)
    value = categories.get(category)
    kind = NormalizedConflictType.OTHER_OR_UNRESOLVED
    meaning, source = None, None
    notes = ["No reviewed mapping exists for this provider/dataset/category/value."]
    if item.source_name == "UCDP" and p.get("dataset") == "GED":
        category, value = "type_of_violence", p.get("type_of_violence")
        source = UCDP_MAPPING_SOURCE
        # Booleans, strings and floats must not impersonate a reviewed integer code.
        meaning = UCDP_MEANINGS.get(value) if type(value) is int else None
        if type(value) is int and value == 3:
            kind = NormalizedConflictType.ONE_SIDED_VIOLENCE
            notes = ["Direct category mapping; UCDP inclusion criteria still apply."]
        elif meaning:
            notes = [
                "State-based conflict does not distinguish interstate, internal or "
                "internationalized internal armed conflict."
                if value == 1
                else "Non-state conflict is not automatically internal armed conflict or major "
                "political violence; a reviewed target definition and additional data are needed."
            ]
        else:
            notes = ["Missing or unknown UCDP type_of_violence; retained unresolved."]
    return HistoricalTaxonomyMapping(
        provider=item.source_name,
        provider_dataset=p.get("dataset"),
        provider_original_category=category,
        provider_original_value=value if type(value) in (str, int) else None,
        provider_original_categories=categories,
        provider_category_meaning=meaning,
        normalized_conflict_type=kind,
        mapping_confidence="verified_direct"
        if kind != NormalizedConflictType.OTHER_OR_UNRESOLVED
        else "unresolved",
        mapping_method_version=MAPPING_VERSION,
        mapping_notes=notes,
        mapping_source=source,
        source_record_id=item.source_record_id,
        dataset_version=p.get("dataset_version"),
        resource=p.get("endpoint"),
        requested_geography=geography,
        observation_geography=item.geographic_scope,
        resolved_provider_geography_id=p.get("resolved_ucdp_country_id") or p.get("country_id"),
        temporal_role=p.get("temporal_role", "unclassified"),
    )
