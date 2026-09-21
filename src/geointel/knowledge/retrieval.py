import re
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from geointel.domain.models import StrategicClaim
from geointel.domain.schemas import RetrievedStrategicClaim

_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]+")
_STOP = {
    "about",
    "after",
    "against",
    "analysis",
    "and",
    "are",
    "for",
    "from",
    "into",
    "over",
    "risk",
    "that",
    "the",
    "this",
    "what",
    "where",
    "which",
    "with",
}


@dataclass(frozen=True)
class KnowledgeQuery:
    concepts: tuple[str, ...] = ()
    geography: tuple[str, ...] = ()
    actors: tuple[str, ...] = ()
    conflict_category: str | None = None
    strategic_question: str = ""
    historical_analog: str | None = None
    author: str | None = None
    lens: str | None = None
    limit: int = field(default=10)


class KnowledgeRetriever(Protocol):
    def retrieve(self, query: KnowledgeQuery) -> list[RetrievedStrategicClaim]: ...


class LexicalKnowledgeRetriever:
    """Deterministic structured/lexical retrieval; this is explicitly not vector search."""

    def __init__(self, session: Session):
        self.session = session

    def retrieve(self, query: KnowledgeQuery) -> list[RetrievedStrategicClaim]:
        if query.limit < 1 or query.limit > 100:
            raise ValueError("retrieval limit must be between 1 and 100")
        claims = (
            self.session.scalars(
                select(StrategicClaim).options(
                    selectinload(StrategicClaim.work),
                    selectinload(StrategicClaim.concepts),
                    selectinload(StrategicClaim.historical_cases),
                )
            )
            .unique()
            .all()
        )
        wanted_concepts = {x.casefold() for x in query.concepts}
        wanted_author = (query.author or self._author_for_lens(query.lens)).casefold()
        query_tokens = self._tokens(
            " ".join(
                (
                    query.strategic_question,
                    *query.geography,
                    *query.actors,
                    query.conflict_category or "",
                    query.historical_analog or "",
                )
            )
        )
        ranked = []
        for claim in claims:
            concepts = {x.slug.casefold() for x in claim.concepts} | {
                x.name.casefold() for x in claim.concepts
            }
            matched_concepts = sorted(wanted_concepts & concepts)
            if wanted_concepts and not matched_concepts:
                continue
            if (
                wanted_author
                and wanted_author not in claim.attributed_author.casefold()
                and wanted_author not in claim.work.author.casefold()
            ):
                continue
            case_terms = [
                term for case in claim.historical_cases for term in case.actors + case.geography
            ]
            searchable = " ".join(
                (
                    claim.claim_text,
                    claim.work.title,
                    *(x.name for x in claim.concepts),
                    *(x.name for x in claim.historical_cases),
                    *case_terms,
                )
            )
            lexical = sorted(query_tokens & self._tokens(searchable))
            structured = bool(
                matched_concepts
                or (query.author and wanted_author)
                or (
                    query.historical_analog
                    and query.historical_analog.casefold() in searchable.casefold()
                )
            )
            if not structured and not lexical:
                continue
            reasons = [
                *(f"matched concept: {x}" for x in matched_concepts),
                *(f"lexical match: {x}" for x in lexical),
            ]
            if wanted_author:
                reasons.append(f"matched attributed author/lens: {wanted_author}")
            score = len(matched_concepts) * 10 + len(lexical) + (5 if wanted_author else 0)
            ranked.append(
                (
                    -score,
                    claim.external_id,
                    RetrievedStrategicClaim(
                        claim_id=claim.external_id,
                        text=claim.claim_text,
                        author=claim.attributed_author,
                        work_id=claim.work.external_id,
                        work_title=claim.work.title,
                        locator=claim.locator,
                        provenance={
                            "work": claim.work.source_provenance,
                            "claim": claim.provenance,
                        },
                        matched_concepts=matched_concepts,
                        historical_case_ids=[x.external_id for x in claim.historical_cases],
                        retrieval_reasons=reasons,
                        limitations=claim.limitations,
                        counterexamples=claim.counterexamples,
                    ),
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in ranked[: query.limit]]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {x for x in _TOKEN.findall(text.casefold()) if len(x) > 2 and x not in _STOP}

    @staticmethod
    def _author_for_lens(lens: str | None) -> str:
        return "kissinger" if lens and lens.casefold() == "kissinger" else ""
