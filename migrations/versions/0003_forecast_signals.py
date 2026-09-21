"""Add external predictive forecast signals.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None
UUID = sa.Uuid()


def upgrade() -> None:
    op.create_table(
        "forecast_signals",
        sa.Column("analysis_run_id", UUID, sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("location_id", UUID, sa.ForeignKey("locations.id")),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("source_record_id", sa.String(200), nullable=False),
        sa.Column("model_name", sa.String(150), nullable=False),
        sa.Column("model_version", sa.String(100)),
        sa.Column("geographic_unit", sa.String(80), nullable=False),
        sa.Column("source_location", sa.String(200), nullable=False),
        sa.Column("issue_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_months", sa.Integer()),
        sa.Column("target_variable", sa.String(200), nullable=False),
        sa.Column("prediction", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(80)),
        sa.Column("scale", sa.String(120)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("alignment_status", sa.String(30), nullable=False),
        sa.Column("alignment_notes", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("forecast_signals")
