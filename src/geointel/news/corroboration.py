"""Explainable story clustering and conservative reporting-chain assessment.

All article fields are treated as inert, untrusted strings.  This module performs no
network access and creates neither Events nor risk scores.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from geointel.domain.schemas import NormalizedNewsReport
from geointel.news.relevance import NewsRelevanceAssessment, RelevanceState

STORY_METHOD_VERSION = "story-similarity-v1"
ASSESSMENT_VERSION = "conservative-chains-v2"
_TOKEN = re.compile(r"[^\W_]+(?:['’-][^\W_]+)?", re.UNICODE)
_GENERIC = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "new",
    "of",
    "on",
    "or",
    "says",
    "the",
    "to",
    "with",
    "after",
    "amid",
    "over",
    "war",
    "attack",
    "attacks",
    "government",
    "protest",
    "protests",
    "violence",
    "conflict",
    "crisis",
    "official",
    "officials",
    "report",
    "reports",
    "breaking",
}
_WIRES = {
    "reuters": "REUTERS",
    "associated press": "AP",
    "ap news": "AP",
    "afp": "AFP",
    "agence france-presse": "AFP",
    "bloomberg": "BLOOMBERG",
}


class IndependenceStatus(StrEnum):
    INDEPENDENT = "INDEPENDENT"
    LIKELY_SHARED_UPSTREAM = "LIKELY_SHARED_UPSTREAM"
    UNKNOWN = "UNKNOWN"


class CorroborationStatus(StrEnum):
    SINGLE_REPORT = "SINGLE_REPORT"
    MULTIPLE_REPORTS_DEPENDENCE_UNKNOWN = "MULTIPLE_REPORTS_DEPENDENCE_UNKNOWN"
    MULTIPLE_REPORTS_INDEPENDENCE_UNKNOWN = "MULTIPLE_REPORTS_DEPENDENCE_UNKNOWN"  # compatibility
    LIKELY_SHARED_REPORTING_CHAIN = "LIKELY_SHARED_REPORTING_CHAIN"
    LIKELY_SYNDICATED = "LIKELY_SHARED_REPORTING_CHAIN"  # compatibility
    MULTIPLE_DISTINCT_PUBLISHERS_UNRESOLVED = "MULTIPLE_DISTINCT_PUBLISHERS_UNRESOLVED"
    MULTI_SOURCE_CORROBORATED_REPORTING = "MULTI_SOURCE_CORROBORATED_REPORTING"


class StoryMatch(BaseModel):
    left_report_id: str
    right_report_id: str
    method_version: str = STORY_METHOD_VERSION
    features: dict
    decision: str
    confidence: str


class StoryCluster(BaseModel):
    cluster_id: str
    member_report_ids: list[str]
    provider_set: list[str]
    publisher_domain_set: list[str]
    earliest_publication_timestamp: datetime | None
    latest_publication_timestamp: datetime | None
    method_version: str = STORY_METHOD_VERSION
    match_reasons: list[StoryMatch] = Field(default_factory=list)
    unresolved_matches: list[StoryMatch] = Field(default_factory=list)
    classification: str
    uncertainty: str
    first_seen: datetime
    last_seen: datetime


class CorroborationAssessment(BaseModel):
    cluster_id: str
    assessment_version: str = ASSESSMENT_VERSION
    status: CorroborationStatus
    member_count: int
    unique_domains: int
    independent_chain_count: int
    unknown_independence_count: int
    reporting_chains: list[dict]
    reason_codes: list[str]
    assessed_at: datetime
    candidate_indicator_eligible: bool
    candidate_indicator_blockers: list[str]
    news_report_provenance: list[str]
    boundary: str = "candidate_only_not_event_not_evidence_not_risk_score"


def _id(report: NormalizedNewsReport) -> str:
    return f"{report.provider}:{report.source_record_id}"


def _domain(report: NormalizedNewsReport) -> str:
    return (urlsplit(report.canonical_url).hostname or "unknown").removeprefix("www.").lower()


def _tokens(title: str) -> set[str]:
    return {token.casefold().replace("’", "'") for token in _TOKEN.findall(title)}


def _entities(title: str) -> set[str]:
    # Explainable heuristic only: title-cased non-generic words, not NLP-derived facts.
    return {
        token.casefold()
        for token in _TOKEN.findall(title)
        if token[:1].isupper() and token.casefold() not in _GENERIC and len(token) > 2
    }


def _hours(left: NormalizedNewsReport, right: NormalizedNewsReport) -> float | None:
    if left.publication_timestamp is None or right.publication_timestamp is None:
        return None
    return abs((left.publication_timestamp - right.publication_timestamp).total_seconds()) / 3600


def compare_reports(left: NormalizedNewsReport, right: NormalizedNewsReport) -> StoryMatch:
    """Return a deterministic explanation; only ``probable_same_story`` is mergeable."""
    if left.canonical_url == right.canonical_url:
        decision, confidence = "exact_duplicate_reporting_artifacts", "high"
        features = {
            "canonical_url_match": True,
            "title_similarity": 1.0,
            "distinctive_token_overlap": sorted(
                (_tokens(left.title) | _tokens(right.title)) - _GENERIC
            ),
            "entity_overlap": sorted(_entities(left.title) & _entities(right.title)),
            "location_overlap": left.requested_geography.casefold()
            == right.requested_geography.casefold(),
            "time_distance_hours": _hours(left, right),
            "time_semantics": "publication_proximity_only_not_event_time",
        }
        return StoryMatch(
            left_report_id=_id(left),
            right_report_id=_id(right),
            features=features,
            decision=decision,
            confidence=confidence,
        )

    lt, rt = _tokens(left.title), _tokens(right.title)
    union = lt | rt
    similarity = len(lt & rt) / len(union) if union else 0.0
    distinctive = sorted((lt & rt) - _GENERIC)
    entities = sorted(_entities(left.title) & _entities(right.title))
    location = left.requested_geography.casefold() == right.requested_geography.casefold()
    distance = _hours(left, right)
    compatible_time = distance is not None and distance <= 72
    # Multiple dimensions are mandatory. Generic vocabulary and geography alone never merge.
    strong_words = len(distinctive) >= 3 and similarity >= 0.42
    entity_route = len(entities) >= 2 and len(distinctive) >= 2 and similarity >= 0.30 and location
    if compatible_time and (strong_words or entity_route):
        decision, confidence = "probable_same_story", "medium"
    elif (len(distinctive) >= 2 and similarity >= 0.25) or (len(entities) >= 2 and location):
        decision, confidence = "possible_same_story_unresolved", "low"
    else:
        decision, confidence = "different_or_insufficient_evidence", "low"
    return StoryMatch(
        left_report_id=_id(left),
        right_report_id=_id(right),
        features={
            "canonical_url_match": False,
            "title_similarity": round(similarity, 3),
            "distinctive_token_overlap": distinctive,
            "entity_overlap": entities,
            "location_overlap": location,
            "time_distance_hours": distance,
            "time_window_hours": 72,
            "time_semantics": "publication_proximity_only_not_event_time",
        },
        decision=decision,
        confidence=confidence,
    )


def cluster_reports(reports: list[NormalizedNewsReport]) -> list[StoryCluster]:
    """Cluster exact identities first, then conservative complete-link semantic matches."""
    groups: list[list[NormalizedNewsReport]] = []
    for report in sorted(reports, key=lambda r: (r.canonical_url, _id(r))):
        exact = next(
            (group for group in groups if group[0].canonical_url == report.canonical_url), None
        )
        if exact is not None:
            exact.append(report)
        else:
            groups.append([report])

    # Complete-link placement prevents a weak transitive bridge from merging two stories.
    semantic: list[list[NormalizedNewsReport]] = []
    for group in groups:
        destination = next(
            (
                candidate
                for candidate in semantic
                if all(
                    compare_reports(item, peer).decision == "probable_same_story"
                    for item in group
                    for peer in candidate
                )
            ),
            None,
        )
        (destination if destination is not None else semantic.append(group))
        if destination is not None:
            destination.extend(group)

    result: list[StoryCluster] = []
    for members in semantic:
        matches = [
            compare_reports(a, b) for index, a in enumerate(members) for b in members[index + 1 :]
        ]
        exact_only = len({x.canonical_url for x in members}) == 1 and len(members) > 1
        probable = any(match.decision == "probable_same_story" for match in matches)
        classification = (
            "SINGLE_REPORT_CLUSTER"
            if len(members) == 1
            else "exact_duplicate_reporting_artifacts"
            if exact_only
            else "probable_same_story"
            if probable
            else "possible_same_story_unresolved"
        )
        published = [x.publication_timestamp for x in members if x.publication_timestamp]
        identity = "|".join(sorted(x.canonical_url for x in members))
        result.append(
            StoryCluster(
                cluster_id=hashlib.sha256(identity.encode()).hexdigest(),
                member_report_ids=[_id(x) for x in members],
                provider_set=sorted({x.provider for x in members}),
                publisher_domain_set=sorted({_domain(x) for x in members}),
                earliest_publication_timestamp=min(published) if published else None,
                latest_publication_timestamp=max(published) if published else None,
                match_reasons=[
                    x for x in matches if x.decision != "different_or_insufficient_evidence"
                ],
                classification=classification,
                uncertainty=(
                    "Candidate grouping does not confirm a common real-world event; "
                    "source dependence and factual truth are assessed separately."
                ),
                first_seen=min(x.retrieval_timestamp for x in members),
                last_seen=max(x.retrieval_timestamp for x in members),
            )
        )

    # Preserve plausible-but-unmerged relationships explicitly on both clusters.
    membership = {
        report_id: cluster for cluster in result for report_id in cluster.member_report_ids
    }
    for i, left in enumerate(reports):
        for right in reports[i + 1 :]:
            match = compare_reports(left, right)
            if (
                match.decision == "possible_same_story_unresolved"
                and membership[_id(left)] is not membership[_id(right)]
            ):
                membership[_id(left)].unresolved_matches.append(match)
                membership[_id(right)].unresolved_matches.append(match)
    return result


def _wire(report: NormalizedNewsReport) -> str | None:
    explicit = report.syndication_metadata.get("named_upstream") or report.provenance.get(
        "wire_service"
    )
    if explicit:
        value = str(explicit).strip().upper()
        return value or None
    haystack = " ".join(
        str(x)
        for x in (
            report.provenance.get("author", ""),
            report.provenance.get("description", ""),
        )
    ).casefold()
    return next((name for marker, name in _WIRES.items() if marker in haystack), None)


def assess_cluster(
    cluster: StoryCluster,
    reports: list[NormalizedNewsReport],
    *,
    assessed_at: datetime,
    relevance: NewsRelevanceAssessment | None = None,
) -> CorroborationAssessment:
    """Assess chains. Independence requires affirmative status *and* distinct chain IDs."""
    members = [r for r in reports if _id(r) in cluster.member_report_ids]
    domains = {_domain(r) for r in members}
    chain_rows, affirmative = [], set()
    wires = {_wire(r) for r in members if _wire(r)}
    shared = len({r.canonical_url for r in members}) < len(members)
    unknown = 0
    for report in members:
        state = str(report.syndication_metadata.get("independence_status", "UNKNOWN")).upper()
        chain_id = report.syndication_metadata.get("reporting_chain_id")
        wire = _wire(report)
        if state == IndependenceStatus.INDEPENDENT and chain_id:
            affirmative.add(str(chain_id))
        else:
            unknown += state == IndependenceStatus.UNKNOWN or not chain_id
        shared |= state == IndependenceStatus.LIKELY_SHARED_UPSTREAM or wire is not None
        chain_rows.append(
            {
                "report_id": _id(report),
                "provider": report.provider,
                "publisher_domain": _domain(report),
                "author": report.provenance.get("author"),
                "named_upstream": wire,
                "independence_status": state,
                "reporting_chain_id": chain_id,
            }
        )
    if len(members) == 1:
        status, reasons = CorroborationStatus.SINGLE_REPORT, ["single_reporting_artifact"]
    elif len(affirmative) >= 2 and not wires:
        status, reasons = (
            CorroborationStatus.MULTI_SOURCE_CORROBORATED_REPORTING,
            ["two_affirmatively_independent_distinct_reporting_chain_ids"],
        )
    elif shared:
        status, reasons = (
            CorroborationStatus.LIKELY_SHARED_REPORTING_CHAIN,
            ["exact_identity_or_explicit_shared_wire_or_upstream"],
        )
    elif len(domains) > 1:
        status, reasons = (
            CorroborationStatus.MULTIPLE_DISTINCT_PUBLISHERS_UNRESOLVED,
            ["different_publishers_do_not_establish_independence"],
        )
    else:
        status, reasons = (
            CorroborationStatus.MULTIPLE_REPORTS_DEPENDENCE_UNKNOWN,
            ["reporting_chain_dependence_unknown"],
        )

    blockers = []
    if status != CorroborationStatus.MULTI_SOURCE_CORROBORATED_REPORTING:
        blockers.append("insufficient_independent_reporting_chains")
    if cluster.classification != "probable_same_story":
        blockers.append("cluster_not_probable_same_story")
    if any(r.geographic_alignment_status != "aligned" for r in members):
        blockers.append("geographic_alignment_not_established")
    if any(r.temporal_alignment != "within_requested_window" for r in members):
        blockers.append("temporal_alignment_not_current_or_unknown")
    if any(r.temporal_classification == "stale_or_republished" for r in members):
        blockers.append("stale_or_republished_material")
    if relevance is None:
        blockers.append("relevance_assessment_not_available")
    else:
        for field, code in (
            ("topic_relevance", "topic_relevance_not_established"),
            ("conflict_relevance", "conflict_relevance_not_established"),
            ("geographic_relevance", "geographic_relevance_not_established"),
            ("temporal_relevance", "temporal_relevance_not_established"),
        ):
            if getattr(relevance, field) in {RelevanceState.NOT_RELEVANT, RelevanceState.UNKNOWN}:
                blockers.append(code)
    return CorroborationAssessment(
        cluster_id=cluster.cluster_id,
        status=status,
        member_count=len(members),
        unique_domains=len(domains),
        independent_chain_count=len(affirmative),
        unknown_independence_count=int(unknown),
        reporting_chains=chain_rows,
        reason_codes=reasons,
        assessed_at=assessed_at,
        candidate_indicator_eligible=not blockers,
        candidate_indicator_blockers=blockers,
        news_report_provenance=[_id(r) for r in members],
    )
