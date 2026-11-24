"""Isolated PostgreSQL persistence for advisory snapshots and evaluator state."""

from collections.abc import Iterable
from datetime import date

from sqlalchemy import (
    JSON,
    Column,
    Date,
    ForeignKeyConstraint,
    MetaData,
    String,
    Table,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from geointel.early_warning import (
    Observation,
    Scope,
    State,
    Thresholds,
    WarningRecord,
    evaluate,
    stream_id,
)

metadata = MetaData()
checkpoints = Table(
    "early_warning_checkpoints",
    metadata,
    Column("namespace", String(128), primary_key=True),
    Column("stream_id", String(64), primary_key=True),
    Column("state", JSON),
)
history = Table(
    "early_warning_history",
    metadata,
    Column("namespace", String(128), primary_key=True),
    Column("stream_id", String(64), primary_key=True),
    Column("period_end", Date, primary_key=True),
    Column("as_of", Date, primary_key=True),
    Column("revision_cutoff", Date, primary_key=True),
    Column("event_id", String(64), unique=True),
    Column("snapshot", JSON, nullable=False),
    ForeignKeyConstraint(
        ["namespace", "stream_id"],
        ["early_warning_checkpoints.namespace", "early_warning_checkpoints.stream_id"],
    ),
)


def persist_evaluation(
    connection: Connection,
    scope: Scope,
    observations: Iterable[Observation],
    *,
    thresholds: Thresholds,
    period_end: date,
    as_of: date,
    revision_cutoff: date,
    replay_id: str | None = None,
) -> WarningRecord:
    """Append a snapshot and advance its checkpoint in a READ COMMITTED transaction.

    Call within an explicit transaction and commit before using the returned record.
    A retry of an existing occurrence returns its original snapshot.
    """
    if (
        connection.dialect.name != "postgresql"
        or not connection.in_transaction()
        or connection.get_isolation_level() != "READ COMMITTED"
    ):
        raise ValueError("an active PostgreSQL READ COMMITTED transaction is required")
    if replay_id is not None and (not 1 <= len(replay_id) <= 121 or replay_id != replay_id.strip()):
        raise ValueError("replay ID must be nonempty, trimmed and at most 121 characters")
    with connection.begin_nested():
        return _persist(
            connection,
            scope,
            observations,
            thresholds=thresholds,
            period_end=period_end,
            as_of=as_of,
            revision_cutoff=revision_cutoff,
            replay_id=replay_id,
        )


def _persist(
    connection: Connection,
    scope: Scope,
    observations: Iterable[Observation],
    *,
    thresholds: Thresholds,
    period_end: date,
    as_of: date,
    revision_cutoff: date,
    replay_id: str | None,
) -> WarningRecord:
    namespace = "live" if replay_id is None else f"replay:{replay_id}"
    stream = stream_id(scope, thresholds)
    connection.execute(
        insert(checkpoints).values(namespace=namespace, stream_id=stream).on_conflict_do_nothing()
    )
    checkpoint = (checkpoints.c.namespace == namespace, checkpoints.c.stream_id == stream)
    state_data = connection.execute(
        select(checkpoints.c.state).where(*checkpoint).with_for_update()
    ).scalar_one()
    occurrence = (
        history.c.namespace == namespace,
        history.c.stream_id == stream,
        history.c.period_end == period_end,
        history.c.as_of == as_of,
        history.c.revision_cutoff == revision_cutoff,
    )
    stored = connection.scalar(select(history.c.snapshot).where(*occurrence))
    if stored is not None:
        return WarningRecord.model_validate(stored)
    snapshot, state = evaluate(
        scope,
        observations,
        period_end=period_end,
        as_of=as_of,
        revision_cutoff=revision_cutoff,
        thresholds=thresholds,
        previous=State.model_validate(state_data) if state_data is not None else None,
        mode="live" if replay_id is None else "replay",
    )
    if snapshot.event_id is not None and connection.scalar(
        select(history.c.event_id).where(history.c.event_id == snapshot.event_id)
    ):
        snapshot = snapshot.model_copy(update={"event_id": None})
    connection.execute(
        insert(history).values(
            namespace=namespace,
            stream_id=stream,
            period_end=period_end,
            as_of=as_of,
            revision_cutoff=revision_cutoff,
            event_id=snapshot.event_id,
            snapshot=snapshot.model_dump(mode="json"),
        )
    )
    connection.execute(
        update(checkpoints).where(*checkpoint).values(state=state.model_dump(mode="json"))
    )
    return snapshot
