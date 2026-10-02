"""Deterministic, explainable news-discovery relevance heuristics.

Article fields are untrusted, inert data.  These rules perform no retrieval and assess
discovery relevance only; they do not establish that an event happened.
"""

from __future__ import annotations

import re
from collections import Counter
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from geointel.domain.schemas import AnalysisRequest, NormalizedNewsReport
from geointel.geography import matched_subnational_entities, resolve_country

RELEVANCE_METHOD_VERSION = "organized-political-violence-v2"
AUDIT_TITLE_LIMIT = 300
AUDIT_DESCRIPTION_LIMIT = 500
AUDIT_FIELD_LIMIT = 600
_WORDS = re.compile(r"[^\W_]+(?:['’-][^\W_]+)?", re.UNICODE)


class RelevanceState(StrEnum):
    RELEVANT = "RELEVANT"
    POSSIBLY_RELEVANT = "POSSIBLY_RELEVANT"
    NOT_RELEVANT = "NOT_RELEVANT"
    UNKNOWN = "UNKNOWN"


class NewsRelevanceAssessment(BaseModel):
    subject_id: str
    subject_type: str
    geographic_relevance: RelevanceState
    topic_relevance: RelevanceState
    conflict_relevance: RelevanceState
    temporal_relevance: RelevanceState
    overall_relevance: RelevanceState
    reason_codes: list[str]
    matched_terms: list[str] = Field(default_factory=list)
    matched_signal_families: list[str] = Field(default_factory=list)
    matched_entities: list[str] = Field(default_factory=list)
    uncertainty: str
    method_version: str = RELEVANCE_METHOD_VERSION
    member_relevance: list[dict] = Field(default_factory=list)
    boundary: str = "discovery_relevance_not_truth_not_event_confirmation"


class ReviewPriority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class NewsReviewItem(BaseModel):
    report_id: str
    audit_snapshot: dict
    unresolved_dimensions: list[str]
    reason_codes: list[str]
    review_priority: ReviewPriority
    semantics: str = "review priority only; not event probability or geopolitical risk"


_STRONG = {
    "armed conflict",
    "political violence",
    "terrorist attack",
    "terrorism",
    "insurgency",
    "separatist violence",
    "violent protest",
    "violent protests",
    "attempted coup",
    "coup attempt",
    "political assassination",
    "armed group",
    "militia attack",
    "military confrontation",
    "border clash",
    "border clashes",
    "state repression",
    "security forces opened fire",
    "politically motivated bombing",
    "car bomb",
    "suicide bombing",
    "armed separatist attack",
    "military border incident",
    "violent riot",
}
_VIOLENCE = {
    "bombing",
    "bombed",
    "explosion",
    "gunfire",
    "shooting",
    "killed",
    "riot",
    "riots",
    "clashes",
    "armed",
    "militia",
    "assassination",
    "terrorism",
    "insurgency",
    "attacked",
    "attack",
    "mutiny",
}
_POLITICAL = {
    "political",
    "government",
    "state",
    "military",
    "security",
    "separatist",
    "protest",
    "protesters",
    "coup",
    "election",
    "minister",
    "political leader",
    "party leader",
    "candidate",
    "parliamentarian",
    "campaign",
    "parliament",
    "border",
}
_PEACEFUL = {
    "peaceful protest",
    "peaceful demonstration",
    "peacefully protested",
    "nonviolent protest",
}
_NEGATIVE = {
    "sports": {
        "football",
        "soccer",
        "league",
        "fixture",
        "match",
        "tournament",
        "goal",
        "coach",
        "athlete",
    },
    "photography": {"photography", "photographer", "photo award", "camera", "portrait prize"},
    "consumer_technology": {
        "smartphone",
        "laptop",
        "gadget",
        "product review",
        "headphones",
        "camera review",
        "data centre",
        "data center",
    },
    "entertainment": {
        "celebrity",
        "film",
        "movie",
        "television",
        "concert",
        "album",
        "actor",
        "actress",
    },
    "routine_business": {
        "earnings",
        "quarterly results",
        "stock price",
        "product launch",
        "market share",
    },
    "travel": {"travel", "holiday", "hotel", "tourism", "destination", "beach"},
}


def _text(report: NormalizedNewsReport) -> str:
    # Deliberately never dereference canonical_url.
    return " ".join((report.title, str(report.provenance.get("description", "")))).casefold()


def _contains(text: str, terms: set[str]) -> set[str]:
    words = set(_WORDS.findall(text))
    return {term for term in terms if (" " in term and term in text) or term in words}


def assess_report_relevance(
    report: NormalizedNewsReport, request: AnalysisRequest
) -> NewsRelevanceAssessment:
    """Assess a report against location, question, and horizon without asserting truth."""
    text = _text(report)
    reasons: list[str] = []
    matched: set[str] = set()
    question = request.question.casefold()
    question_scope = _contains(
        question,
        {
            "organized political violence",
            "armed conflict",
            "political violence",
            "terrorism",
            "insurgency",
            "one-sided violence",
            "military confrontation",
        },
    )
    if question_scope:
        reasons.append("request_targets_organized_political_violence")
    else:
        reasons.append("request_topic_not_covered_by_violence_ontology")

    location = request.location.casefold().strip()
    geographic_entities: list[str] = []
    provider_geo = " ".join(str(x) for x in (report.provider_geography or {}).values()).casefold()
    source_geo = (report.source_country or "").casefold()
    try:
        identity = resolve_country(request.location)
        subnational = matched_subnational_entities(text, identity)
    except ValueError:
        subnational = []
    if location and (location in text or location == source_geo or location in provider_geo):
        geography = RelevanceState.RELEVANT
        reasons.append("requested_geography_supported_by_report_metadata")
        geographic_entities = [request.location]
    elif subnational:
        geography = RelevanceState.RELEVANT
        geographic_entities = subnational
        reasons.extend(
            f"explicit_subnational_mapping:{entity}:{request.location}" for entity in subnational
        )
    elif report.source_country or report.provider_geography:
        geography = RelevanceState.NOT_RELEVANT
        reasons.append("report_metadata_supports_different_geography")
    else:
        geography = RelevanceState.UNKNOWN
        geographic_entities = []
        reasons.append("query_geography_not_demonstrated_by_report_metadata")

    strong = _contains(text, _STRONG)
    violent = _contains(text, _VIOLENCE)
    political = _contains(text, _POLITICAL)
    peaceful = _contains(text, _PEACEFUL)
    matched.update(strong | violent | political | peaceful)
    negative = {category: _contains(text, terms) for category, terms in _NEGATIVE.items()}
    negative = {category: terms for category, terms in negative.items() if terms}
    for category, terms in negative.items():
        matched.update(terms)
        reasons.append(f"off_topic_signal:{category}")

    conflict_signal = bool(question_scope and (strong or (violent and political)))
    # Strongly off-topic contexts win over ambiguous sports metaphors such as attack,
    # defence and shot. Only an explicit multiword organized-violence phrase can override.
    explicit_strong = strong - {"armed group"}
    if negative and not explicit_strong:
        topic = conflict = RelevanceState.NOT_RELEVANT
        reasons.append("off_topic_without_conflict_signal")
    elif peaceful and not (strong or violent - {"protest"}):
        topic = conflict = RelevanceState.NOT_RELEVANT
        reasons.append("peaceful_protest_without_violence_signal")
    elif conflict_signal:
        conflict = RelevanceState.RELEVANT if strong else RelevanceState.POSSIBLY_RELEVANT
        topic = RelevanceState.RELEVANT if strong else RelevanceState.POSSIBLY_RELEVANT
        reasons.append("organized_political_violence_discovery_signal")
        if violent and political and geography == RelevanceState.RELEVANT:
            reasons.extend(
                [
                    "potential_political_violence_composition",
                    "violence_component_matched",
                    "political_actor_or_campaign_component_matched",
                    "motive_not_inferred",
                ]
            )
        if negative:
            topic = conflict = RelevanceState.POSSIBLY_RELEVANT
            reasons.append("conflict_signal_prevents_off_topic_override")
    elif political:
        topic = RelevanceState.POSSIBLY_RELEVANT
        conflict = RelevanceState.NOT_RELEVANT
        reasons.append("political_context_without_violence_signal")
    else:
        topic = conflict = RelevanceState.UNKNOWN
        reasons.append("organized_political_violence_relevance_not_established")

    stale = report.temporal_classification == "stale_or_republished"
    if stale or report.temporal_alignment not in {"within_requested_window", "aligned"}:
        temporal = RelevanceState.NOT_RELEVANT if stale else RelevanceState.UNKNOWN
        reasons.append(
            "stale_or_temporally_unaligned_report" if stale else "temporal_alignment_unknown"
        )
    else:
        temporal = RelevanceState.RELEVANT
        reasons.append("publication_time_within_discovery_window_not_event_time")
    reasons.append(f"requested_horizon_months:{request.horizon_months}")

    dimensions = (geography, topic, conflict, temporal)
    if RelevanceState.NOT_RELEVANT in dimensions:
        overall = RelevanceState.NOT_RELEVANT
    elif RelevanceState.UNKNOWN in dimensions:
        overall = RelevanceState.UNKNOWN
    elif RelevanceState.POSSIBLY_RELEVANT in dimensions:
        overall = RelevanceState.POSSIBLY_RELEVANT
    else:
        overall = RelevanceState.RELEVANT
    return NewsRelevanceAssessment(
        subject_id=f"{report.provider}:{report.source_record_id}",
        subject_type="NewsReport",
        geographic_relevance=geography,
        topic_relevance=topic,
        conflict_relevance=conflict,
        temporal_relevance=temporal,
        overall_relevance=overall,
        reason_codes=reasons,
        matched_terms=sorted(matched),
        matched_signal_families=sorted(
            (["explicit_organized_violence"] if strong else [])
            + (["violence_or_escalation"] if violent else [])
            + (["political_context"] if political else [])
        ),
        matched_entities=geographic_entities,
        uncertainty=(
            "Deterministic metadata heuristic for discovery triage only; article text is "
            "untrusted and relevance does not establish occurrence, motive, or truth."
        ),
    )


def _bounded(value: object, limit: int) -> str:
    """Normalize untrusted provider strings for bounded inert JSON storage."""
    return " ".join(str(value or "").replace("\x00", "").split())[:limit]


def relevance_audit_snapshot(
    report: NormalizedNewsReport,
    request: AnalysisRequest,
    assessment: NewsRelevanceAssessment,
) -> dict:
    """Create a strict allowlist snapshot; raw payloads and credentials are excluded."""
    description = report.provenance.get("description", "")
    domain = urlsplit(str(report.canonical_url)).hostname or ""
    return {
        "report_id": assessment.subject_id,
        "provider": _bounded(report.provider, 40),
        "publisher": _bounded(report.publisher, 200),
        "publisher_domain": _bounded(domain, 253),
        "title": _bounded(report.title, AUDIT_TITLE_LIMIT),
        "publication_timestamp": (
            report.publication_timestamp.isoformat() if report.publication_timestamp else None
        ),
        "requested_geography": _bounded(request.location, 120),
        "geographic_relevance": assessment.geographic_relevance.value,
        "topic_relevance": assessment.topic_relevance.value,
        "conflict_relevance": assessment.conflict_relevance.value,
        "temporal_relevance": assessment.temporal_relevance.value,
        "overall_relevance": assessment.overall_relevance.value,
        "matched_terms": [_bounded(x, 80) for x in assessment.matched_terms[:30]],
        "matched_signal_families": assessment.matched_signal_families[:20],
        "reason_codes": [_bounded(x, 120) for x in assessment.reason_codes[:30]],
        "uncertainty": _bounded(assessment.uncertainty, AUDIT_FIELD_LIMIT),
        "canonical_url": _bounded(report.canonical_url, 1000),
        "description_excerpt": _bounded(description, AUDIT_DESCRIPTION_LIMIT),
        "content_treatment": "untrusted_inert_data_not_instructions",
    }


def build_review_item(assessment: NewsRelevanceAssessment, snapshot: dict) -> NewsReviewItem:
    unresolved = [
        name
        for name in ("geographic", "topic", "conflict", "temporal")
        if getattr(assessment, f"{name}_relevance") == RelevanceState.UNKNOWN
    ]
    reasons = [f"{name}_unresolved" for name in unresolved]
    has_geo = assessment.geographic_relevance == RelevanceState.RELEVANT
    has_signal = bool(assessment.matched_terms)
    priority = (
        ReviewPriority.HIGH
        if has_geo and has_signal
        else ReviewPriority.MEDIUM
        if has_geo or has_signal
        else ReviewPriority.LOW
    )
    return NewsReviewItem(
        report_id=assessment.subject_id,
        audit_snapshot=snapshot,
        unresolved_dimensions=unresolved,
        reason_codes=sorted(set(reasons + assessment.reason_codes)),
        review_priority=priority,
    )


def assess_cluster_relevance(cluster, assessments: list[NewsRelevanceAssessment]):
    members = [a for a in assessments if a.subject_id in cluster.member_report_ids]
    reasons = sorted({reason for item in members for reason in item.reason_codes})

    def combine(field: str) -> RelevanceState:
        states = [getattr(item, field) for item in members]
        if states and all(x == RelevanceState.RELEVANT for x in states):
            return RelevanceState.RELEVANT
        if states and all(x == RelevanceState.NOT_RELEVANT for x in states):
            return RelevanceState.NOT_RELEVANT
        if states and all(
            x in {RelevanceState.RELEVANT, RelevanceState.POSSIBLY_RELEVANT} for x in states
        ):
            return RelevanceState.POSSIBLY_RELEVANT
        return RelevanceState.UNKNOWN

    geographic, topic = combine("geographic_relevance"), combine("topic_relevance")
    conflict, temporal = combine("conflict_relevance"), combine("temporal_relevance")
    overall = combine("overall_relevance")
    counts = Counter(item.overall_relevance.value for item in members)
    reasons.append("cluster_requires_consistent_member_relevance")
    return NewsRelevanceAssessment(
        subject_id=cluster.cluster_id,
        subject_type="StoryCluster",
        geographic_relevance=geographic,
        topic_relevance=topic,
        conflict_relevance=conflict,
        temporal_relevance=temporal,
        overall_relevance=overall,
        reason_codes=reasons,
        matched_terms=sorted({term for item in members for term in item.matched_terms}),
        matched_signal_families=sorted(
            {family for item in members for family in item.matched_signal_families}
        ),
        matched_entities=sorted({term for item in members for term in item.matched_entities}),
        uncertainty=(
            f"Conservative aggregation of {len(members)} member assessments: {dict(counts)}."
        ),
        member_relevance=[
            {
                "report_id": x.subject_id,
                "overall_relevance": x.overall_relevance.value,
                "reason_codes": x.reason_codes,
            }
            for x in members
        ],
    )
