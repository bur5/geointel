import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from geointel.domain.models import (
    HistoricalCase,
    KnowledgeSection,
    KnowledgeWork,
    StrategicClaim,
    StrategicConcept,
)

MAX_FILE_BYTES = 1_000_000


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def reject_nul(cls, value):
        if isinstance(value, str) and "\x00" in value:
            raise ValueError("NUL characters are not allowed")
        if isinstance(value, dict) and len(json.dumps(value, sort_keys=True, default=str)) > 20_000:
            raise ValueError("metadata/provenance exceeds size limit")
        return value


class WorkInput(StrictRecord):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    title: str = Field(min_length=1, max_length=500)
    author: str = Field(min_length=1, max_length=300)
    publication_year: int | None = Field(default=None, ge=1000, le=3000)
    edition: str | None = Field(default=None, max_length=200)
    publisher: str | None = Field(default=None, max_length=300)
    language: str = Field(default="en", min_length=2, max_length=20)
    source_type: str = Field(min_length=1, max_length=50)
    source_provenance: dict
    copyright_status: str = Field(default="unknown", max_length=50)
    metadata: dict = Field(default_factory=dict)

    @field_validator("source_provenance")
    @classmethod
    def provenance_required(cls, value: dict) -> dict:
        if not value:
            raise ValueError("source provenance is required")
        return value


class SectionInput(StrictRecord):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    title: str = Field(min_length=1, max_length=500)
    ordering: int = Field(ge=0, le=100000)
    locator: str | None = Field(default=None, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    provenance: dict

    @field_validator("provenance")
    @classmethod
    def provenance_required(cls, value: dict) -> dict:
        if not value:
            raise ValueError("section provenance is required")
        return value


class ConceptInput(StrictRecord):
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    provenance: dict

    @field_validator("provenance")
    @classmethod
    def provenance_required(cls, value: dict) -> dict:
        if not value:
            raise ValueError("concept provenance is required")
        return value


class CaseInput(StrictRecord):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    name: str = Field(min_length=1, max_length=300)
    start_date: datetime | None = None
    end_date: datetime | None = None
    actors: list[str] = Field(default_factory=list, max_length=100)
    geography: list[str] = Field(default_factory=list, max_length=100)
    factual_summary: str = Field(min_length=1, max_length=4000)
    outcome: str | None = Field(default=None, max_length=2000)
    interpretation_notes: list[str] = Field(default_factory=list, max_length=50)
    source_provenance: dict
    concept_slugs: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("actors", "geography", "interpretation_notes")
    @classmethod
    def bounded_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 500 for item in value):
            raise ValueError("list items must be nonblank and at most 500 characters")
        return value

    @field_validator("source_provenance")
    @classmethod
    def provenance_required(cls, value: dict) -> dict:
        if not value:
            raise ValueError("case provenance is required")
        return value


class ClaimInput(StrictRecord):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")
    section_id: str = Field(min_length=1, max_length=120)
    attributed_author: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=2000)
    locator: str | None = Field(default=None, max_length=200)
    claim_type: str = Field(min_length=1, max_length=50)
    extraction_confidence: str = Field(pattern=r"^(low|medium|high)$")
    concept_slugs: list[str] = Field(default_factory=list, max_length=50)
    case_ids: list[str] = Field(default_factory=list, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=50)
    counterexamples: list[str] = Field(default_factory=list, max_length=50)
    provenance: dict
    ingestion_metadata: dict = Field(default_factory=dict)

    @field_validator("limitations", "counterexamples")
    @classmethod
    def bounded_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 500 for item in value):
            raise ValueError("list items must be nonblank and at most 500 characters")
        return value

    @field_validator("provenance")
    @classmethod
    def provenance_required(cls, value: dict) -> dict:
        if not value:
            raise ValueError("claim provenance is required")
        return value


class KnowledgeDocument(StrictRecord):
    schema_version: str = Field(pattern=r"^geointel-knowledge-v1$")
    work: WorkInput
    sections: list[SectionInput] = Field(min_length=1, max_length=500)
    concepts: list[ConceptInput] = Field(default_factory=list, max_length=500)
    historical_cases: list[CaseInput] = Field(default_factory=list, max_length=500)
    claims: list[ClaimInput] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def references_and_duplicates(self):
        for values, label, key in (
            (self.sections, "section", lambda x: x.id),
            (self.concepts, "concept", lambda x: x.slug),
            (self.historical_cases, "case", lambda x: x.id),
            (self.claims, "claim", lambda x: x.id),
        ):
            identifiers = [key(item) for item in values]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"duplicate {label} identifier")
        sections = {item.id for item in self.sections}
        concepts = {item.slug for item in self.concepts}
        cases = {item.id for item in self.historical_cases}
        for claim in self.claims:
            if claim.section_id not in sections:
                raise ValueError(f"unknown section {claim.section_id}")
            if not set(claim.concept_slugs) <= concepts:
                raise ValueError("claim references unknown concept")
            if not set(claim.case_ids) <= cases:
                raise ValueError("claim references unknown historical case")
        if any(not set(case.concept_slugs) <= concepts for case in self.historical_cases):
            raise ValueError("historical case references unknown concept")
        return self


class KnowledgeIngestor:
    """Imports bounded operator-provided JSON. It performs no network access or execution."""

    def __init__(self, session: Session):
        self.session = session

    def load_json(self, path: Path, allowed_root: Path) -> KnowledgeWork:
        resolved, root = path.resolve(), allowed_root.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError("knowledge path must remain inside allowed root")
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("knowledge file exceeds size limit")
        return self.ingest(KnowledgeDocument.model_validate_json(resolved.read_text("utf-8")))

    def ingest(self, document: KnowledgeDocument | dict) -> KnowledgeWork:
        document = KnowledgeDocument.model_validate(document)
        duplicate_queries = (
            (KnowledgeWork, KnowledgeWork.external_id, document.work.id),
            *[(StrategicClaim, StrategicClaim.external_id, x.id) for x in document.claims],
            *[
                (HistoricalCase, HistoricalCase.external_id, x.id)
                for x in document.historical_cases
            ],
        )
        if any(
            self.session.scalar(select(model).where(column == value))
            for model, column, value in duplicate_queries
        ):
            raise ValueError("duplicate knowledge identifier already exists")
        work = KnowledgeWork(
            external_id=document.work.id,
            title=document.work.title,
            author=document.work.author,
            publication_year=document.work.publication_year,
            edition=document.work.edition,
            publisher=document.work.publisher,
            language=document.work.language,
            source_type=document.work.source_type,
            source_provenance=document.work.source_provenance,
            copyright_status=document.work.copyright_status,
            work_metadata=document.work.metadata,
        )
        self.session.add(work)
        self.session.flush()
        sections = {}
        for item in document.sections:
            section = KnowledgeSection(
                work_id=work.id,
                section_identifier=item.id,
                title=item.title,
                ordering=item.ordering,
                locator=item.locator,
                summary=item.summary,
                provenance=item.provenance,
            )
            self.session.add(section)
            self.session.flush()
            sections[item.id] = section
        concepts = {}
        for item in document.concepts:
            existing = self.session.scalar(
                select(StrategicConcept).where(StrategicConcept.slug == item.slug)
            )
            if existing:
                if existing.name != item.name:
                    raise ValueError("concept slug conflicts with existing concept")
                concepts[item.slug] = existing
                continue
            concept = StrategicConcept(
                slug=item.slug,
                name=item.name,
                description=item.description,
                provenance=item.provenance,
            )
            self.session.add(concept)
            self.session.flush()
            concepts[item.slug] = concept
        cases = {}
        for item in document.historical_cases:
            case = HistoricalCase(
                external_id=item.id,
                name=item.name,
                start_date=item.start_date,
                end_date=item.end_date,
                actors=item.actors,
                geography=item.geography,
                factual_summary=item.factual_summary,
                outcome=item.outcome,
                interpretation_notes=item.interpretation_notes,
                source_provenance=item.source_provenance,
                concepts=[concepts[x] for x in item.concept_slugs],
            )
            self.session.add(case)
            self.session.flush()
            cases[item.id] = case
        for item in document.claims:
            self.session.add(
                StrategicClaim(
                    external_id=item.id,
                    work_id=work.id,
                    section_id=sections[item.section_id].id,
                    attributed_author=item.attributed_author,
                    claim_text=item.text,
                    locator=item.locator,
                    claim_type=item.claim_type,
                    extraction_confidence=item.extraction_confidence,
                    limitations=item.limitations,
                    counterexamples=item.counterexamples,
                    provenance=item.provenance,
                    ingestion_metadata=item.ingestion_metadata,
                    concepts=[concepts[x] for x in item.concept_slugs],
                    historical_cases=[cases[x] for x in item.case_ids],
                )
            )
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ValueError("duplicate knowledge identifier") from exc
        return work
