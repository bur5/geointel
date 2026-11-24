"""Deterministic briefing assembly and rendering."""

import json
import re
from collections import defaultdict
from datetime import UTC, date, datetime
from enum import StrEnum
from html import escape
from math import isfinite
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from geointel.domain.models import (
    AnalysisRun,
    Event,
    Evidence,
    ForecastSignal,
    Indicator,
    KnowledgeWork,
    Scenario,
    Source,
    StrategicAnalysis,
    StrategicClaim,
)
from geointel.pipeline.historical import HISTORICAL_ROLES


class BriefingType(StrEnum):
    COUNTRY = "country_intelligence"
    REGIONAL = "regional_security"
    CONFLICT = "conflict_situation"
    WEEKLY = "weekly_geopolitical"
    OUTLOOK = "strategic_outlook"


class BriefingRequest(BaseModel):
    briefing_type: BriefingType
    location_ids: frozenset[UUID] = Field(min_length=1)
    cutoff: date
    stale_after_days: int = Field(default=90, ge=0)
    conflict_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.conflict_id is not None and not self.conflict_id.strip():
            raise ValueError("conflict ID cannot be blank")
        if self.briefing_type == BriefingType.COUNTRY and len(self.location_ids) != 1:
            raise ValueError("country briefings require exactly one location")
        if (self.briefing_type == BriefingType.CONFLICT) != (self.conflict_id is not None):
            raise ValueError("conflict situation reports require an explicit conflict ID")
        return self


class Citation(BaseModel):
    id: str
    location_id: UUID
    source_name: str
    source_record_id: str | None = None
    url: str | None = None
    event_at: datetime | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    ingested_at: datetime
    provenance: dict = Field(default_factory=dict)


class Statement(BaseModel):
    kind: Literal["observation", "forecast", "interpretation", "hypothetical"]
    text: str
    citations: tuple[str, ...] = Field(min_length=1)
    stale: bool | None = None
    details: dict = Field(default_factory=dict)


SECTION_TITLES = (
    "Executive Summary",
    "Current Situation",
    "Key Developments",
    "Relevant Geopolitical Actors",
    "Conflict Risk Indicators",
    "Forecasts and Uncertainty",
    "Alternative Scenarios",
    "Information Gaps",
    "Sources and Evidence",
)


class Section(BaseModel):
    title: str
    status: Literal["available", "unavailable"]
    statements: tuple[Statement, ...] = ()
    notes: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()


def _plain(value: str) -> str:
    return re.sub(r"([\\`*_{}\[\]#!|~])", r"\\\1", escape(" ".join(value.split()), quote=False))


class Briefing(BaseModel):
    schema_version: Literal["1"] = "1"
    briefing_type: BriefingType
    cutoff: date
    stale_after_days: int
    location_ids: tuple[UUID, ...]
    conflict_id: str | None
    sections: tuple[Section, ...]
    sources: tuple[Citation, ...]

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, indent=2, allow_nan=False)

    def to_markdown(self) -> str:
        title = self.briefing_type.value.replace("_", " ").title()
        lines = [f"# {title}", "", f"Cutoff (UTC, inclusive) — {self.cutoff}"]
        lines.append(f"Location IDs — {', '.join(map(str, self.location_ids))}")
        if self.conflict_id:
            lines.append(f"Conflict ID — {_plain(self.conflict_id)}")
        labels = {source.id: f"S{index}" for index, source in enumerate(self.sources, 1)}
        for section in self.sections:
            lines.extend(("", f"## {section.title}", ""))
            if section.status == "unavailable":
                lines.append("Unavailable — insufficient eligible records.")
            for item in section.statements:
                refs = ", ".join(labels[ref] for ref in item.citations)
                stale = " (stale)" if item.stale else ""
                lines.append(
                    f"- **{item.kind.capitalize()}{stale}** — {_plain(item.text)} [{refs}]"
                )
            lines.extend(f"- {_plain(note)}" for note in section.notes)
            if section.title == SECTION_TITLES[-1]:
                for source in self.sources:
                    dates = ", ".join(
                        f"{label} {value.isoformat() if value else 'unknown'}"
                        for label, value in (
                            ("event", source.event_at),
                            ("published/issued", source.published_at),
                            ("retrieved", source.retrieved_at),
                            ("ingested", source.ingested_at),
                        )
                    )
                    identity = source.source_record_id or "no upstream record ID"
                    provenance = json.dumps(source.provenance, sort_keys=True, ensure_ascii=False)
                    url = f" · URL {_plain(source.url)}" if source.url else ""
                    lines.append(
                        f"- [{labels[source.id]}] {_plain(source.source_name)} / {_plain(identity)}"
                        f" — {dates}. Record — `{source.id}`. Provenance — {_plain(provenance)}"
                        f"{url}"
                    )
        return "\n".join(lines) + "\n"


class NarrativeProvider(Protocol):
    """Future opt-in extension. Its result is an unverified interpretation."""

    def explain(self, briefing: Briefing) -> str: ...


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _timestamp(value) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, str):
        try:
            return _utc(datetime.fromisoformat(value))
        except ValueError:
            return None
    return None


def _strings(value) -> list[str]:
    return (
        sorted({item.strip() for item in value if isinstance(item, str) and item.strip()})
        if (isinstance(value, list))
        else []
    )


def _eligible(cutoff: date, *dates: datetime | None) -> bool:
    return all(value is None or _utc(value).date() <= cutoff for value in dates)


def _citation(row, location_id, name, **metadata) -> Citation:
    return Citation(
        id=f"{row.__tablename__}/{row.id}",
        location_id=location_id,
        source_name=name,
        ingested_at=_utc(row.created_at),
        **metadata,
    )


def _observations(session: Session, request: BriefingRequest):
    """Only explicit location associations and the provider's structured fields are used."""
    for model in (Evidence, Event, Indicator):
        query = select(model).where(model.location_id.in_(request.location_ids))
        if model in (Evidence, Event):
            query = query.join(Source, model.source_id == Source.id).add_columns(Source.name)
            rows = session.execute(query)
        else:
            rows = ((row, None) for row in session.scalars(query))
        for row, name in rows:
            provenance = row.provenance or {}
            nested = provenance.get("provenance")
            attributes = {**nested, **provenance} if isinstance(nested, dict) else provenance
            if request.conflict_id and attributes.get("conflict_id") != request.conflict_id:
                continue
            if isinstance(row, Evidence):
                event_at, published, retrieved = row.event_date, row.published_at, row.retrieved_at
                text = row.summary or row.title
                url = row.url
            elif isinstance(row, Event):
                event_at = row.occurred_at
                published = _timestamp(attributes.get("published_at"))
                retrieved = _timestamp(attributes.get("retrieved_at"))
                text = row.description
                url = attributes.get("source_url")
            else:
                name = attributes.get("source_name") or "GEOINTEL indicator record"
                event_at = row.observed_at
                published = _timestamp(attributes.get("published_at"))
                retrieved = _timestamp(attributes.get("retrieved_at"))
                url = attributes.get("source_url")
                if row.value is None or not isfinite(row.value):
                    continue
                text = f"{row.name} — {row.value:g} {row.unit or ''}".rstrip()
            extra_dates = [
                _timestamp(attributes[key])
                for key in ("published_at", "retrieved_at", "updated_at", "ingested_at")
                if attributes.get(key) is not None
            ]
            if (
                not text.strip()
                or None in extra_dates
                or not _eligible(
                    request.cutoff, row.created_at, event_at, published, retrieved, *extra_dates
                )
            ):
                continue
            if isinstance(row, Event) and attributes.get("alignment_status") == "mismatch":
                if event_at is None or attributes.get("temporal_classification") != "historical":
                    continue
                notes = _strings(attributes.get("alignment_notes"))
                if not notes or any(not note.startswith("stale event:") for note in notes):
                    continue
            if request.briefing_type == BriefingType.WEEKLY:
                activity = _utc(event_at or published)
                if not activity or (request.cutoff - activity.date()).days >= 7:
                    continue
            source = _citation(
                row,
                row.location_id,
                name,
                source_record_id=getattr(row, "source_record_id", None)
                or attributes.get("source_record_id"),
                event_at=_utc(event_at),
                published_at=_utc(published),
                retrieved_at=_utc(retrieved),
                url=url,
                provenance=provenance,
            )
            stale = (
                (request.cutoff - source.event_at.date()).days > request.stale_after_days
                if (source.event_at)
                else None
            )
            details = {}
            if isinstance(row, Indicator):
                details = {"name": row.name, "value": row.value, "unit": row.unit}
            yield (
                row,
                source,
                attributes,
                Statement(
                    kind="observation",
                    text=f"{name} reports: {text}",
                    citations=(source.id,),
                    stale=stale,
                    details=details,
                ),
            )


def _signals(session, request):
    query = select(ForecastSignal).where(ForecastSignal.location_id.in_(request.location_ids))
    for row in session.scalars(query):
        if request.conflict_id and row.provenance.get("conflict_id") != request.conflict_id:
            continue
        if not isfinite(row.prediction) or not _eligible(
            request.cutoff, row.created_at, row.retrieved_at, row.issue_date
        ):
            continue
        source = _citation(
            row,
            row.location_id,
            row.provider,
            source_record_id=row.source_record_id,
            url=row.source_url,
            published_at=_utc(row.issue_date),
            retrieved_at=_utc(row.retrieved_at),
            provenance=row.provenance,
        )
        details = {
            "model": row.model_name,
            "model_version": row.model_version,
            "target_variable": row.target_variable,
            "prediction": row.prediction,
            "unit": row.unit,
            "scale": row.scale,
            "target_start": _utc(row.target_start).isoformat(),
            "target_end": _utc(row.target_end).isoformat(),
            "alignment_status": row.alignment_status,
            "alignment_notes": row.alignment_notes,
        }
        yield (
            source,
            Statement(
                kind="forecast",
                citations=(source.id,),
                details=details,
                text=(
                    f"{row.provider} {row.model_name} predicts {row.prediction:g} "
                    f"{row.unit or 'units unspecified'} for {row.target_variable}, "
                    f"{details['target_start']} through {details['target_end']}. "
                    f"Source geography: {row.source_location}. Alignment: {row.alignment_status}. "
                    "The signal record supplies no uncertainty interval."
                ),
            ),
        )


def _run_products(session, request, references, sources, sections, gaps):
    query = select(AnalysisRun).where(
        AnalysisRun.location_id.in_(request.location_ids),
        AnalysisRun.status == "completed",
    )
    for run in session.scalars(query):
        if not run.completed_at or not _eligible(request.cutoff, run.created_at, run.completed_at):
            continue
        for forecast in run.forecasts:
            # Conflict category is not an incident identity.
            if request.conflict_id or not _eligible(request.cutoff, forecast.created_at):
                continue
            if forecast.probability_low is None or forecast.probability_high is None:
                gaps.add("At least one eligible analysis abstained from a numeric forecast.")
                continue
            if not 0 <= forecast.probability_low <= forecast.probability_high <= 1:
                gaps.add("A stored forecast was withheld because its interval was invalid.")
                continue
            supporting = _strings(forecast.evidence_for)
            opposing = _strings(forecast.evidence_against)
            resolved = {}
            for ref in set(supporting + opposing):
                matches = references.get((run.id, ref), set())
                if len(matches) == 1:
                    candidate = sources[next(iter(matches))]
                    if all(
                        value is None or value <= _utc(run.completed_at)
                        for value in (
                            candidate.ingested_at,
                            candidate.published_at,
                            candidate.retrieved_at,
                            candidate.event_at,
                        )
                    ):
                        resolved[ref] = candidate.id
            if (
                not supporting
                or len(resolved) != len(set(supporting + opposing))
                or len(supporting) != len(forecast.evidence_for)
                or len(opposing) != len(forecast.evidence_against)
            ):
                gaps.add(
                    "A stored forecast was withheld because its evidence could not be verified."
                )
                continue
            source = _citation(
                forecast,
                run.location_id,
                "GEOINTEL forecast",
                published_at=_utc(run.completed_at),
                provenance={
                    "analysis_run_id": str(run.id),
                    "pipeline_version": run.pipeline_version,
                },
            )
            sources[source.id] = source
            details = {
                "conflict_type": forecast.conflict_type,
                "horizon_months": forecast.horizon_months,
                "version": forecast.version,
                "probability_low": forecast.probability_low,
                "probability_high": forecast.probability_high,
                "confidence": forecast.confidence,
                "evidence_for": sorted({resolved[ref] for ref in supporting}),
                "evidence_against": sorted({resolved[ref] for ref in opposing}),
            }
            sections[5].append(
                Statement(
                    kind="forecast",
                    details=details,
                    citations=(source.id, *sorted(set(resolved.values()))),
                    text=(
                        f"GEOINTEL assessment for {forecast.conflict_type} over "
                        f"{forecast.horizon_months} months: {forecast.probability_low:.1%} to "
                        f"{forecast.probability_high:.1%} probability, "
                        f"{forecast.confidence} confidence."
                    ),
                )
            )
        if request.conflict_id:
            continue
        for scenario in session.scalars(select(Scenario).where(Scenario.analysis_run_id == run.id)):
            if not _eligible(request.cutoff, scenario.created_at):
                continue
            source = _citation(
                scenario,
                run.location_id,
                "GEOINTEL scenario",
                provenance={"analysis_run_id": str(run.id)},
            )
            sources[source.id] = source
            assumptions = _strings(scenario.assumptions)
            assumption_text = f" Assumptions — {' / '.join(assumptions)}" if assumptions else ""
            sections[6].append(
                Statement(
                    kind="hypothetical",
                    citations=(source.id,),
                    details={"assumptions": assumptions},
                    text=f"{scenario.name} — {scenario.description}" + assumption_text,
                )
            )

        _strategic_context(session, request, run, sources, sections)


def _strategic_context(session, request, run, sources, sections):
    analyses = session.scalars(
        select(StrategicAnalysis).where(
            StrategicAnalysis.analysis_run_id == run.id,
            StrategicAnalysis.status == "completed",
        )
    )
    claim_ids = {
        claim_id
        for analysis in analyses
        if _eligible(request.cutoff, analysis.created_at, analysis.analyzed_at)
        for claim_id in _strings(analysis.retrieved_claim_ids)
    }
    if not claim_ids:
        return
    query = (
        select(StrategicClaim, KnowledgeWork)
        .join(KnowledgeWork)
        .where(StrategicClaim.external_id.in_(claim_ids))
    )
    for claim, work in session.execute(query):
        if not _eligible(request.cutoff, claim.created_at, work.created_at, work.ingested_at):
            continue
        if work.publication_year and (work.publication_year, 12, 31) > (
            request.cutoff.year,
            request.cutoff.month,
            request.cutoff.day,
        ):
            continue
        source = _citation(
            claim,
            run.location_id,
            work.title,
            source_record_id=claim.external_id,
            provenance={
                "claim": claim.provenance,
                "work": work.source_provenance,
                "work_ingested_at": _utc(work.ingested_at).isoformat(),
                "publication_year": work.publication_year,
                "locator": claim.locator,
            },
        )
        # The same library claim can apply to several locations in one briefing.
        source = source.model_copy(update={"id": f"{source.id}/{run.location_id}"})
        sources[source.id] = source
        limits = _strings(claim.limitations)
        counterexamples = _strings(claim.counterexamples)
        qualifications = [
            "Applicability to the briefing scope remains unevaluated.",
            *[f"Limitation — {item.rstrip('.')}." for item in limits],
            *[f"Counterexample — {item.rstrip('.')}." for item in counterexamples],
        ]
        sections[1].append(
            Statement(
                kind="interpretation",
                citations=(source.id,),
                text=f"{claim.attributed_author} argues: {claim.claim_text} "
                + " ".join(qualifications),
                details={"limitations": limits, "counterexamples": counterexamples},
            )
        )


def generate_briefing(session: Session, request: BriefingRequest) -> Briefing:
    """Assemble a briefing from the caller's database snapshot without writing or fetching."""
    with session.no_autoflush:
        return _assemble(session, request)


def _assemble(session: Session, request: BriefingRequest) -> Briefing:
    sections: list[list[Statement]] = [[] for _ in SECTION_TITLES]
    sources: dict[str, Citation] = {}
    references = defaultdict(set)
    conflicts = defaultdict(list)
    gaps = set()
    observations = []
    current = []
    for row, source, attributes, item in _observations(session, request):
        sources[source.id] = source
        if isinstance(row, (Evidence, Event)):
            for ref in (str(row.id), source.id, source.source_record_id):
                if ref is not None:
                    references[row.analysis_run_id, ref].add(source.id)
        if isinstance(row, Indicator):
            sections[4].append(item)
            if source.event_at and row.unit:
                key = (row.location_id, row.name, source.event_at, row.unit)
                conflicts[key].append((source.id, row.value))
        else:
            observations.append((source, item))
            if (
                item.stale is False
                and attributes.get("temporal_role") not in HISTORICAL_ROLES
                and attributes.get("temporal_role") != "candidate_recent"
                and attributes.get("temporal_classification") != "historical"
            ):
                sections[1].append(item)
                current.append((source, item))
            sections[2].append(item)
            for actor in sorted(
                set(_strings(attributes.get("actors")))
                | set(_strings(attributes.get("associated_actors")))
            ):
                sections[3].append(
                    Statement(
                        kind="observation",
                        text=f"{source.source_name} identifies {actor} in its record.",
                        citations=(source.id,),
                        stale=item.stale,
                    )
                )
        group = attributes.get("conflict_group")
        value = attributes.get("conflict_value")
        if (
            isinstance(group, str)
            and group
            and isinstance(value, (str, int, float, bool))
            and (not isinstance(value, float) or isfinite(value))
        ):
            conflicts[row.location_id, group].append((source.id, value))
        if source.event_at is None:
            gaps.add("At least one observation lacks an event date, so its freshness is unknown.")
        if source.published_at is None:
            gaps.add("At least one observation lacks a publication date.")

    for values in conflicts.values():
        if len({value for _, value in values}) > 1:
            refs = tuple(sorted({ref for ref, _ in values}))
            readings = ", ".join(
                f"{sources[ref].source_name} reports {value}" for ref, value in sorted(values)
            )
            sections[7].append(
                Statement(
                    kind="interpretation",
                    text=f"Comparable records disagree. {readings}.",
                    citations=refs,
                    details={"reported_values": dict(sorted(values))},
                )
            )

    for source, item in _signals(session, request):
        sources[source.id] = source
        sections[5].append(item)
    _run_products(session, request, references, sources, sections, gaps)

    if not current:
        gaps.add("Current observations are unavailable in the selected scope.")
    if observations:
        _, latest = max(
            current or observations,
            key=lambda pair: (
                pair[0].event_at or datetime.min.replace(tzinfo=UTC),
                pair[0].id,
            ),
        )
        sections[0].append(latest)
    elif sections[4]:
        sections[0].append(min(sections[4], key=lambda item: item.citations))
    if sections[5]:
        sections[0].append(min(sections[5], key=lambda item: item.citations))
    if request.briefing_type == BriefingType.OUTLOOK:
        sections[0].extend(item for item in sections[1] if item.kind == "interpretation")

    gaps.update(
        f"{SECTION_TITLES[index]} is unavailable." for index in range(1, 7) if not sections[index]
    )
    report_sections = tuple(
        Section(
            title=title,
            status="available"
            if (sections[index] or (index == 7 and gaps) or (index == 8 and sources))
            else "unavailable",
            statements=tuple(
                sorted(sections[index], key=lambda item: (item.kind, item.citations, item.text))
            ),
            notes=tuple(sorted(gaps)) if index == 7 else (),
            citations=tuple(sorted(sources)) if index == 8 else (),
        )
        for index, title in enumerate(SECTION_TITLES)
    )
    return Briefing(
        briefing_type=request.briefing_type,
        cutoff=request.cutoff,
        stale_after_days=request.stale_after_days,
        location_ids=tuple(sorted(request.location_ids)),
        conflict_id=request.conflict_id,
        sections=report_sections,
        sources=tuple(sources[key] for key in sorted(sources)),
    )
