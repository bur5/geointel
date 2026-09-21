"""Initial GEOINTEL domain schema.

Revision ID: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
UUID = sa.Uuid()


def upgrade():
    op.create_table(
        "locations",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("iso_code", sa.String(3)),
        sa.Column("geometry_wkt", sa.Text()),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "sources",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("base_url", sa.Text()),
        sa.Column("reliability", sa.String(20), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "analysis_runs",
        sa.Column("location_id", UUID, sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("pipeline_version", sa.String(30), nullable=False),
        sa.Column("provider_config", sa.JSON(), nullable=False),
        sa.Column("analyst_output", sa.JSON()),
        sa.Column("red_team_output", sa.JSON()),
        sa.Column("synthesis_output", sa.JSON()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "events",
        sa.Column("location_id", UUID, sa.ForeignKey("locations.id")),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "indicators",
        sa.Column("location_id", UUID, sa.ForeignKey("locations.id")),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("value", sa.Float()),
        sa.Column("unit", sa.String(40)),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "evidence",
        sa.Column("analysis_run_id", UUID, sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("source_id", UUID, sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("location_id", UUID, sa.ForeignKey("locations.id")),
        sa.Column("source_record_id", sa.String(200)),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("url", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("event_date", sa.DateTime(timezone=True)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reliability", sa.String(20), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "scenarios",
        sa.Column("analysis_run_id", UUID, sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "forecasts",
        sa.Column("analysis_run_id", UUID, sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("conflict_type", sa.String(50), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("probability_low", sa.Float()),
        sa.Column("probability_high", sa.Float()),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_for", sa.JSON(), nullable=False),
        sa.Column("evidence_against", sa.JSON(), nullable=False),
        sa.Column("unknowns", sa.JSON(), nullable=False),
        sa.Column("resolution_criteria", sa.JSON(), nullable=False),
        sa.Column("change_conditions", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("analysis_run_id", "conflict_type", "version"),
    )


def downgrade():
    for table in (
        "forecasts",
        "scenarios",
        "evidence",
        "indicators",
        "events",
        "analysis_runs",
        "sources",
        "locations",
    ):
        op.drop_table(table)
