import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


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
