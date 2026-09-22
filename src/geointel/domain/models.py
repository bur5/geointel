import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


claim_concepts = Table(
    "strategic_claim_concepts",
    Base.metadata,
    Column("claim_id", ForeignKey("strategic_claims.id"), primary_key=True),
    Column("concept_id", ForeignKey("strategic_concepts.id"), primary_key=True),
)

claim_cases = Table(
    "strategic_claim_cases",
    Base.metadata,
    Column("claim_id", ForeignKey("strategic_claims.id"), primary_key=True),
    Column("case_id", ForeignKey("historical_cases.id"), primary_key=True),
)

case_concepts = Table(
    "historical_case_concepts",
    Base.metadata,
    Column("case_id", ForeignKey("historical_cases.id"), primary_key=True),
    Column("concept_id", ForeignKey("strategic_concepts.id"), primary_key=True),
)


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Location(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "locations"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    iso_code: Mapped[str | None] = mapped_column(String(3))
    geometry_wkt: Mapped[str | None] = mapped_column(
        Text, comment="Portable precursor to PostGIS geometry"
    )


class Source(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sources"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    source_type: Mapped[str] = mapped_column(String(40))
    base_url: Mapped[str | None] = mapped_column(Text)
    reliability: Mapped[str] = mapped_column(String(20), default="unknown")


class AnalysisRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "analysis_runs"
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"))
    question: Mapped[str] = mapped_column(Text)
    horizon_months: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="running")
    pipeline_version: Mapped[str] = mapped_column(String(30))
    provider_config: Mapped[dict] = mapped_column(JSON)
    collection_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    analyst_output: Mapped[dict | None] = mapped_column(JSON)
    red_team_output: Mapped[dict | None] = mapped_column(JSON)
    synthesis_output: Mapped[dict | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[Location] = relationship()
    forecasts: Mapped[list["Forecast"]] = relationship(back_populates="analysis_run")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="analysis_run")
    forecast_signals: Mapped[list["ForecastSignal"]] = relationship(back_populates="analysis_run")
    events: Mapped[list["Event"]] = relationship(back_populates="analysis_run")
    strategic_analyses: Mapped[list["StrategicAnalysis"]] = relationship(
        back_populates="analysis_run"
    )
    validation_runs: Mapped[list["ValidationRun"]] = relationship(back_populates="analysis_run")


class Watchlist(Base, UUIDMixin, TimestampMixin):
    """Named monitoring configuration; its text and metadata are untrusted data."""

    __tablename__ = "watchlists"
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    watchlist_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    targets: Mapped[list["WatchlistTarget"]] = relationship(back_populates="watchlist")


class WatchlistTarget(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "watchlist_targets"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "target_type", "geography_id"),
        Index("ix_watchlist_targets_enabled_due", "enabled", "next_due_at"),
    )
    watchlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("watchlists.id"))
    target_type: Mapped[str] = mapped_column(String(30), default="country")
    geography_id: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cadence: Mapped[str] = mapped_column(String(30))
    horizon_months: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_successful_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    watchlist: Mapped[Watchlist] = relationship(back_populates="targets")
    monitoring_runs: Mapped[list["MonitoringRun"]] = relationship(back_populates="target")


class MonitoringRun(Base, UUIDMixin):
    __tablename__ = "monitoring_runs"
    __table_args__ = (Index("ix_monitoring_runs_target_started", "target_id", "started_at"),)
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("watchlist_targets.id"))
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_runs.id"))
    previous_monitoring_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitoring_runs.id")
    )
    previous_analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    trigger_type: Mapped[str] = mapped_column(String(30))
    baseline_established: Mapped[bool] = mapped_column(Boolean, default=False)
    error_reason: Mapped[str | None] = mapped_column(Text)
    source_availability: Mapped[dict] = mapped_column(JSON, default=dict)
    run_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    target: Mapped[WatchlistTarget] = relationship(back_populates="monitoring_runs")
    analysis_run: Mapped[AnalysisRun | None] = relationship(foreign_keys=[analysis_run_id])
    changes: Mapped[list["DetectedChange"]] = relationship(back_populates="monitoring_run")


class DetectedChange(Base, UUIDMixin):
    __tablename__ = "detected_changes"
    monitoring_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitoring_runs.id"))
    change_type: Mapped[str] = mapped_column(String(60))
    previous_state: Mapped[dict] = mapped_column(JSON)
    current_state: Mapped[dict] = mapped_column(JSON)
    affected_categories: Mapped[list] = mapped_column(JSON)
    source_references: Mapped[list] = mapped_column(JSON)
    severity: Mapped[str] = mapped_column(String(30))
    material: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict] = mapped_column(JSON)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    monitoring_run: Mapped[MonitoringRun] = relationship(back_populates="changes")


class Alert(Base, UUIDMixin):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("target_id", "deduplication_key"),
        Index("ix_alerts_target_status", "target_id", "status"),
    )
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("watchlist_targets.id"))
    monitoring_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitoring_runs.id"))
    deduplication_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="notable")
    what_changed: Mapped[list] = mapped_column(JSON)
    analytical_significance: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON)
    counterevidence: Mapped[list] = mapped_column(JSON)
    missing_or_disagreeing_sources: Mapped[list] = mapped_column(JSON)
    affected_categories: Mapped[list] = mapped_column(JSON)
    confirmation_or_reversal: Mapped[list] = mapped_column(JSON)
    guardrails: Mapped[list] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ValidationSuiteRecord(Base, UUIDMixin, TimestampMixin):
    """Identity of a version-controlled validation suite, never a risk product."""

    __tablename__ = "validation_suites"
    __table_args__ = (UniqueConstraint("suite_id", "version"),)
    suite_id: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(50))
    definition_digest: Mapped[str] = mapped_column(String(64))


class ValidationRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "validation_runs"
    suite_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("validation_suites.id"))
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"))
    case_id: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30))
    source_matrix: Mapped[dict] = mapped_column(JSON)
    implementation_version: Mapped[str] = mapped_column(String(30))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="validation_runs")
    results: Mapped[list["ValidationResult"]] = relationship(back_populates="validation_run")


class ValidationResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "validation_results"
    validation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("validation_runs.id"))
    assertion_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    explanation: Mapped[str] = mapped_column(Text)
    relevant_object_ids: Mapped[list] = mapped_column(JSON)
    implementation_version: Mapped[str] = mapped_column(String(30))
    validation_run: Mapped[ValidationRun] = relationship(back_populates="results")


class KnowledgeWork(Base, UUIDMixin, TimestampMixin):
    """Bibliographic container. Its contents are attributed context, not evidence."""

    __tablename__ = "knowledge_works"
    external_id: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(300))
    publication_year: Mapped[int | None] = mapped_column(Integer)
    edition: Mapped[str | None] = mapped_column(String(200))
    publisher: Mapped[str | None] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(String(20), default="en")
    source_type: Mapped[str] = mapped_column(String(50))
    source_provenance: Mapped[dict] = mapped_column(JSON)
    copyright_status: Mapped[str] = mapped_column(String(50), default="unknown")
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    work_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    sections: Mapped[list["KnowledgeSection"]] = relationship(back_populates="work")


class KnowledgeSection(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "knowledge_sections"
    __table_args__ = (UniqueConstraint("work_id", "section_identifier"),)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_works.id"))
    section_identifier: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(500))
    ordering: Mapped[int] = mapped_column(Integer)
    locator: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict] = mapped_column(JSON)
    work: Mapped[KnowledgeWork] = relationship(back_populates="sections")
    claims: Mapped[list["StrategicClaim"]] = relationship(back_populates="section")


class StrategicConcept(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "strategic_concepts"
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict] = mapped_column(JSON)


class HistoricalCase(Base, UUIDMixin, TimestampMixin):
    """Structured case; facts and interpretive notes deliberately occupy separate fields."""

    __tablename__ = "historical_cases"
    external_id: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actors: Mapped[list] = mapped_column(JSON)
    geography: Mapped[list] = mapped_column(JSON)
    factual_summary: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    interpretation_notes: Mapped[list] = mapped_column(JSON)
    source_provenance: Mapped[dict] = mapped_column(JSON)
    concepts: Mapped[list[StrategicConcept]] = relationship(secondary=case_concepts)


class StrategicClaim(Base, UUIDMixin, TimestampMixin):
    """An attributed proposition; never operational Evidence, Event, or ForecastSignal."""

    __tablename__ = "strategic_claims"
    external_id: Mapped[str] = mapped_column(String(120), unique=True)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_works.id"))
    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_sections.id"))
    attributed_author: Mapped[str] = mapped_column(String(300))
    claim_text: Mapped[str] = mapped_column(Text)
    locator: Mapped[str | None] = mapped_column(String(200))
    claim_type: Mapped[str] = mapped_column(String(50))
    extraction_confidence: Mapped[str] = mapped_column(String(20))
    limitations: Mapped[list] = mapped_column(JSON)
    counterexamples: Mapped[list] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    ingestion_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    work: Mapped[KnowledgeWork] = relationship()
    section: Mapped[KnowledgeSection] = relationship(back_populates="claims")
    concepts: Mapped[list[StrategicConcept]] = relationship(secondary=claim_concepts)
    historical_cases: Mapped[list[HistoricalCase]] = relationship(secondary=claim_cases)


class StrategicAnalysis(Base, UUIDMixin, TimestampMixin):
    """Immutable-by-convention audit record for one lens invocation."""

    __tablename__ = "strategic_analyses"
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"))
    lens_name: Mapped[str] = mapped_column(String(120))
    lens_version: Mapped[str] = mapped_column(String(50))
    retrieved_claim_ids: Mapped[list] = mapped_column(JSON)
    retrieved_case_ids: Mapped[list] = mapped_column(JSON)
    retrieval_provenance: Mapped[list] = mapped_column(JSON)
    output: Mapped[dict] = mapped_column(JSON)
    limitations: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30))
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="strategic_analyses")


class Evidence(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "evidence"
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    source_record_id: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reliability: Mapped[str] = mapped_column(String(20))
    provenance: Mapped[dict] = mapped_column(JSON)
    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="evidence")


class Event(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "events"
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_runs.id"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id"))
    source_record_id: Mapped[str | None] = mapped_column(String(200))
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    event_type: Mapped[str] = mapped_column(String(50))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20))
    provenance: Mapped[dict] = mapped_column(JSON)
    analysis_run: Mapped[AnalysisRun | None] = relationship(back_populates="events")


class Indicator(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "indicators"
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    name: Mapped[str] = mapped_column(String(150))
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(40))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[dict] = mapped_column(JSON)


class ForecastSignal(Base, UUIDMixin, TimestampMixin):
    """External predictive output, separate from observed evidence and GEOINTEL forecasts."""

    __tablename__ = "forecast_signals"
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    provider: Mapped[str] = mapped_column(String(120))
    source_record_id: Mapped[str] = mapped_column(String(200))
    model_name: Mapped[str] = mapped_column(String(150))
    model_version: Mapped[str | None] = mapped_column(String(100))
    geographic_unit: Mapped[str] = mapped_column(String(80))
    source_location: Mapped[str] = mapped_column(String(200))
    issue_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon_months: Mapped[int | None] = mapped_column(Integer)
    target_variable: Mapped[str] = mapped_column(String(200))
    prediction: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(80))
    scale: Mapped[str | None] = mapped_column(String(120))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str | None] = mapped_column(Text)
    alignment_status: Mapped[str] = mapped_column(String(30))
    alignment_notes: Mapped[list] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="forecast_signals")


class Scenario(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scenarios"
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    assumptions: Mapped[list] = mapped_column(JSON)


class Forecast(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "forecasts"
    __table_args__ = (UniqueConstraint("analysis_run_id", "conflict_type", "version"),)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"))
    conflict_type: Mapped[str] = mapped_column(String(50))
    question: Mapped[str] = mapped_column(Text)
    horizon_months: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    probability_low: Mapped[float | None] = mapped_column(Float)
    probability_high: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(20))
    rationale: Mapped[str] = mapped_column(Text)
    evidence_for: Mapped[list] = mapped_column(JSON)
    evidence_against: Mapped[list] = mapped_column(JSON)
    unknowns: Mapped[list] = mapped_column(JSON)
    resolution_criteria: Mapped[list] = mapped_column(JSON)
    change_conditions: Mapped[list] = mapped_column(JSON)
    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="forecasts")


@event.listens_for(Forecast, "before_update", propagate=True)
def prevent_forecast_update(mapper, connection, target):
    raise ValueError("Forecasts are immutable; create a new analysis run/version")


@event.listens_for(StrategicAnalysis, "before_update", propagate=True)
def prevent_strategic_analysis_update(mapper, connection, target):
    raise ValueError("Strategic analyses are immutable audit records; create a new analysis run")
