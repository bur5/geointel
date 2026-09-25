"""Deterministic, bounded discovery query planning (never an evidence source)."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

QUERY_PLAN_VERSION = "organized-political-violence-v1"
_SAFE = re.compile(r"[^\w .,'()\-]", re.UNICODE)

# Deliberately compact packs: each request searches one coherent family rather than one
# location-only query or a single noisy mega-OR expression.
_FAMILIES: tuple[tuple[str, str], ...] = (
    ("armed_conflict", '"armed conflict" OR clashes OR fighting'),
    ("political_attack", '"political violence" OR bombing OR assassination'),
    ("militant_violence", "terrorism OR militant OR insurgency"),
    ("violent_unrest", '"violent unrest" OR riots OR mutiny OR coup'),
    ("armed_group_or_state_force", 'separatist OR "armed group" OR "security forces"'),
    ("military_escalation", '"military escalation" OR "border clash"'),
)


class NewsQuery(BaseModel):
    provider: str
    requested_geography: str
    analysis_intent: str
    query_text: str = Field(max_length=300)
    signal_family: str
    plan_version: str = QUERY_PLAN_VERSION
    request_ordinal: int


class NewsQueryPlan(BaseModel):
    provider: str
    requested_geography: str
    analysis_intent: str
    version: str = QUERY_PLAN_VERSION
    request_budget: int
    queries: list[NewsQuery]
    boundary: str = "discovery_instructions_not_article_content_or_evidence"


def plan_news_queries(
    geography: str,
    *,
    request_budget: int,
    provider: str = "NEWSAPI",
    analysis_intent: str = "organized_political_violence",
) -> NewsQueryPlan:
    """Return the same bounded plan for the same inputs."""
    location = " ".join(_SAFE.sub("", geography).split())[:120]
    if len(location) < 2:
        raise ValueError("location cannot form a safe news query")
    count = min(max(request_budget, 0), len(_FAMILIES))
    queries = [
        NewsQuery(
            provider=provider,
            requested_geography=location,
            analysis_intent=analysis_intent,
            query_text=f'"{location}" AND ({terms})',
            signal_family=family,
            request_ordinal=index,
        )
        for index, (family, terms) in enumerate(_FAMILIES[:count], 1)
    ]
    return NewsQueryPlan(
        provider=provider,
        requested_geography=location,
        analysis_intent=analysis_intent,
        request_budget=request_budget,
        queries=queries,
    )
