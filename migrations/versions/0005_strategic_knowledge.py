"""Add separate strategic knowledge and lens audit records.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None
UUID = sa.Uuid()


def upgrade() -> None:
    op.create_table(
        "knowledge_works",
        sa.Column("external_id", sa.String(120), nullable=False, unique=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(300), nullable=False),
        sa.Column("publication_year", sa.Integer()),
        sa.Column("edition", sa.String(200)),
        sa.Column("publisher", sa.String(300)),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_provenance", sa.JSON(), nullable=False),
        sa.Column("copyright_status", sa.String(50), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("work_metadata", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "strategic_concepts",
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "historical_cases",
        sa.Column("external_id", sa.String(120), nullable=False, unique=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True)),
        sa.Column("end_date", sa.DateTime(timezone=True)),
        sa.Column("actors", sa.JSON(), nullable=False),
        sa.Column("geography", sa.JSON(), nullable=False),
        sa.Column("factual_summary", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text()),
        sa.Column("interpretation_notes", sa.JSON(), nullable=False),
        sa.Column("source_provenance", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "knowledge_sections",
        sa.Column("work_id", UUID, sa.ForeignKey("knowledge_works.id"), nullable=False),
        sa.Column("section_identifier", sa.String(120), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("ordering", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(200)),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("work_id", "section_identifier"),
    )
    op.create_table(
        "strategic_claims",
        sa.Column("external_id", sa.String(120), nullable=False, unique=True),
        sa.Column("work_id", UUID, sa.ForeignKey("knowledge_works.id"), nullable=False),
        sa.Column("section_id", UUID, sa.ForeignKey("knowledge_sections.id"), nullable=False),
        sa.Column("attributed_author", sa.String(300), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("locator", sa.String(200)),
        sa.Column("claim_type", sa.String(50), nullable=False),
        sa.Column("extraction_confidence", sa.String(20), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("counterexamples", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("ingestion_metadata", sa.JSON(), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table, left, right, left_table, right_table in (
        (
            "strategic_claim_concepts",
            "claim_id",
            "concept_id",
            "strategic_claims",
            "strategic_concepts",
        ),
        ("strategic_claim_cases", "claim_id", "case_id", "strategic_claims", "historical_cases"),
        (
            "historical_case_concepts",
            "case_id",
            "concept_id",
            "historical_cases",
            "strategic_concepts",
        ),
    ):
        op.create_table(
            table,
            sa.Column(left, UUID, sa.ForeignKey(f"{left_table}.id"), primary_key=True),
            sa.Column(right, UUID, sa.ForeignKey(f"{right_table}.id"), primary_key=True),
        )
    op.create_table(
        "strategic_analyses",
        sa.Column("analysis_run_id", UUID, sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("lens_name", sa.String(120), nullable=False),
        sa.Column("lens_version", sa.String(50), nullable=False),
        sa.Column("retrieved_claim_ids", sa.JSON(), nullable=False),
        sa.Column("retrieved_case_ids", sa.JSON(), nullable=False),
        sa.Column("retrieval_provenance", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategic_analyses_run", "strategic_analyses", ["analysis_run_id"])


def downgrade() -> None:
    op.drop_index("ix_strategic_analyses_run", table_name="strategic_analyses")
    for table in (
        "strategic_analyses",
        "historical_case_concepts",
        "strategic_claim_cases",
        "strategic_claim_concepts",
        "strategic_claims",
        "knowledge_sections",
        "historical_cases",
        "strategic_concepts",
        "knowledge_works",
    ):
        op.drop_table(table)
