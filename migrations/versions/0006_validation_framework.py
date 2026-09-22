"""Add validation suite, run, and assertion audit records.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None
UUID = sa.Uuid()


def upgrade() -> None:
    op.create_table(
        "validation_suites",
        sa.Column("suite_id", sa.String(120), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("definition_digest", sa.String(64), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("suite_id", "version"),
    )
    op.create_table(
        "validation_runs",
        sa.Column("suite_record_id", UUID, sa.ForeignKey("validation_suites.id"), nullable=False),
        sa.Column("analysis_run_id", UUID, sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("case_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("source_matrix", sa.JSON(), nullable=False),
        sa.Column("implementation_version", sa.String(30), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_validation_runs_analysis", "validation_runs", ["analysis_run_id"])
    op.create_table(
        "validation_results",
        sa.Column("validation_run_id", UUID, sa.ForeignKey("validation_runs.id"), nullable=False),
        sa.Column("assertion_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("relevant_object_ids", sa.JSON(), nullable=False),
        sa.Column("implementation_version", sa.String(30), nullable=False),
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_validation_results_run", "validation_results", ["validation_run_id"])


def downgrade() -> None:
    op.drop_index("ix_validation_results_run", table_name="validation_results")
    op.drop_table("validation_results")
    op.drop_index("ix_validation_runs_analysis", table_name="validation_runs")
    op.drop_table("validation_runs")
    op.drop_table("validation_suites")
