"""Deterministic reporting corroboration; this module never creates Events or risk scores."""

import hashlib
from collections import defaultdict
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from geointel.domain.schemas import NormalizedNewsReport


class IndependenceStatus(StrEnum):
    INDEPENDENT = "INDEPENDENT"
    LIKELY_SHARED_UPSTREAM = "LIKELY_SHARED_UPSTREAM"
    UNKNOWN = "UNKNOWN"


class CorroborationStatus(StrEnum):
    SINGLE_REPORT = "SINGLE_REPORT"
    MULTIPLE_REPORTS_INDEPENDENCE_UNKNOWN = "MULTIPLE_REPORTS_INDEPENDENCE_UNKNOWN"
    LIKELY_SYNDICATED = "LIKELY_SYNDICATED"
    MULTI_SOURCE_CORROBORATED_REPORTING = "MULTI_SOURCE_CORROBORATED_REPORTING"


class StoryCluster(BaseModel):
    cluster_id: str
    member_report_ids: list[str]
    method_version: str = "exact-canonical-url-v1"
    reasons: list[str] = Field(default_factory=lambda: ["exact_canonical_url"])
    classification: str = "exact_duplicate_reporting_artifacts"
    first_seen: datetime
    last_seen: datetime


class CorroborationAssessment(BaseModel):
    cluster_id: str
    assessment_version: str = "conservative-chains-v1"
    status: CorroborationStatus
    member_count: int
    unique_domains: int
    independent_chain_count: int
    unknown_independence_count: int
    reason_codes: list[str]
    assessed_at: datetime
    candidate_indicator_eligible: bool
    boundary: str = "analyst_review_only_not_event_not_risk_score"


def cluster_reports(reports: list[NormalizedNewsReport]) -> list[StoryCluster]:
    """Cluster exact canonical identities only; ambiguous similar titles remain separate."""
    groups = defaultdict(list)
    for report in reports:
        groups[report.canonical_url].append(report)
    result = []
    for url in sorted(groups):
        members = groups[url]
        seen = [item.retrieval_timestamp for item in members]
        result.append(
            StoryCluster(
                cluster_id=hashlib.sha256(url.encode()).hexdigest(),
                member_report_ids=[f"{x.provider}:{x.source_record_id}" for x in members],
                first_seen=min(seen),
                last_seen=max(seen),
            )
        )
    return result


def assess_cluster(
    cluster: StoryCluster, reports: list[NormalizedNewsReport], *, assessed_at: datetime
) -> CorroborationAssessment:
    members = [
        r for r in reports if f"{r.provider}:{r.source_record_id}" in cluster.member_report_ids
    ]
    domains = {urlsplit(r.canonical_url).hostname for r in members}
    states = [r.syndication_metadata.get("independence_status", "UNKNOWN").upper() for r in members]
    independent = sum(state == IndependenceStatus.INDEPENDENT for state in states)
    unknown = sum(state == IndependenceStatus.UNKNOWN for state in states)
    shared = any(state == IndependenceStatus.LIKELY_SHARED_UPSTREAM for state in states)
    if len(members) == 1:
        status, reasons = CorroborationStatus.SINGLE_REPORT, ["single_reporting_artifact"]
    elif independent >= 2:
        status, reasons = (
            CorroborationStatus.MULTI_SOURCE_CORROBORATED_REPORTING,
            ["two_affirmatively_independent_chains"],
        )
    elif shared or len(domains) == 1:
        status, reasons = (
            CorroborationStatus.LIKELY_SYNDICATED,
            ["shared_upstream_or_exact_identity"],
        )
    else:
        status, reasons = (
            CorroborationStatus.MULTIPLE_REPORTS_INDEPENDENCE_UNKNOWN,
            ["different_domains_do_not_establish_independence"],
        )
    return CorroborationAssessment(
        cluster_id=cluster.cluster_id,
        status=status,
        member_count=len(members),
        unique_domains=len(domains),
        independent_chain_count=independent,
        unknown_independence_count=unknown,
        reason_codes=reasons,
        assessed_at=assessed_at,
        candidate_indicator_eligible=(
            status == CorroborationStatus.MULTI_SOURCE_CORROBORATED_REPORTING
        ),
    )
