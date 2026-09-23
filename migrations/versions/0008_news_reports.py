"""Add epistemically separate current-news reports.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None
UUID = sa.Uuid()


def upgrade() -> None:
    op.create_table(
        "news_reports",
        sa.Column("analysis_run_id", UUID, sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("source_record_id", sa.String(200), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publisher", sa.String(500)),
        sa.Column("publication_timestamp", sa.DateTime(timezone=True)),
        sa.Column("retrieval_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("language", sa.String(100)),
        sa.Column("source_country", sa.String(120)),
        sa.Column("requested_geography", sa.String(120), nullable=False),
        sa.Column("provider_geography", sa.JSON()),
        sa.Column("geographic_alignment_status", sa.String(30), nullable=False),
        sa.Column("geographic_alignment_notes", sa.JSON(), nullable=False),
        sa.Column("temporal_classification", sa.String(50), nullable=False),
        sa.Column("temporal_alignment", sa.String(30), nullable=False),
        sa.Column("identity_metadata", sa.JSON(), nullable=False),
        sa.Column("syndication_metadata", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("epistemic_status", sa.String(50), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("analysis_run_id", "canonical_url"),
    )
    op.create_index(
        "ix_news_reports_provider_identity", "news_reports", ["provider", "source_record_id"]
    )
    op.create_index(
        "ix_news_reports_run_published",
        "news_reports",
        ["analysis_run_id", "publication_timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_news_reports_run_published", table_name="news_reports")
    op.drop_index("ix_news_reports_provider_identity", table_name="news_reports")
    op.drop_table("news_reports")
