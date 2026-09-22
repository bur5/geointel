"""Add watchlists, monitoring audit, changes, and alerts.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None
UUID = sa.Uuid()


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("watchlist_metadata", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "watchlist_targets",
        sa.Column("watchlist_id", UUID, sa.ForeignKey("watchlists.id"), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("geography_id", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("cadence", sa.String(30), nullable=False),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_successful_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_metadata", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("watchlist_id", "target_type", "geography_id"),
    )
    op.create_index(
        "ix_watchlist_targets_enabled_due", "watchlist_targets", ["enabled", "next_due_at"]
    )
    op.create_table(
        "monitoring_runs",
        sa.Column("target_id", UUID, sa.ForeignKey("watchlist_targets.id"), nullable=False),
        sa.Column("analysis_run_id", UUID, sa.ForeignKey("analysis_runs.id")),
        sa.Column("previous_monitoring_run_id", UUID, sa.ForeignKey("monitoring_runs.id")),
        sa.Column("previous_analysis_run_id", UUID, sa.ForeignKey("analysis_runs.id")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("trigger_type", sa.String(30), nullable=False),
        sa.Column("baseline_established", sa.Boolean(), nullable=False),
        sa.Column("error_reason", sa.Text()),
        sa.Column("source_availability", sa.JSON(), nullable=False),
        sa.Column("run_metadata", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
    )
    op.create_index(
        "ix_monitoring_runs_target_started", "monitoring_runs", ["target_id", "started_at"]
    )
    op.create_table(
        "detected_changes",
        sa.Column("monitoring_run_id", UUID, sa.ForeignKey("monitoring_runs.id"), nullable=False),
        sa.Column("change_type", sa.String(60), nullable=False),
        sa.Column("previous_state", sa.JSON(), nullable=False),
        sa.Column("current_state", sa.JSON(), nullable=False),
        sa.Column("affected_categories", sa.JSON(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("material", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", UUID, primary_key=True),
    )
    op.create_table(
        "alerts",
        sa.Column("target_id", UUID, sa.ForeignKey("watchlist_targets.id"), nullable=False),
        sa.Column("monitoring_run_id", UUID, sa.ForeignKey("monitoring_runs.id"), nullable=False),
        sa.Column("deduplication_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("what_changed", sa.JSON(), nullable=False),
        sa.Column("analytical_significance", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("counterevidence", sa.JSON(), nullable=False),
        sa.Column("missing_or_disagreeing_sources", sa.JSON(), nullable=False),
        sa.Column("affected_categories", sa.JSON(), nullable=False),
        sa.Column("confirmation_or_reversal", sa.JSON(), nullable=False),
        sa.Column("guardrails", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("id", UUID, primary_key=True),
        sa.UniqueConstraint("target_id", "deduplication_key"),
    )
    op.create_index("ix_alerts_target_status", "alerts", ["target_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_alerts_target_status", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("detected_changes")
    op.drop_index("ix_monitoring_runs_target_started", table_name="monitoring_runs")
    op.drop_table("monitoring_runs")
    op.drop_index("ix_watchlist_targets_enabled_due", table_name="watchlist_targets")
    op.drop_table("watchlist_targets")
    op.drop_table("watchlists")
