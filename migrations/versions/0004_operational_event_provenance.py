"""Link operational events to their analysis and source.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None
UUID = sa.Uuid()


def upgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.add_column(sa.Column("analysis_run_id", UUID, nullable=True))
        batch.add_column(sa.Column("source_id", UUID, nullable=True))
        batch.add_column(sa.Column("source_record_id", sa.String(200), nullable=True))
        batch.create_foreign_key(
            "fk_events_analysis_run", "analysis_runs", ["analysis_run_id"], ["id"]
        )
        batch.create_foreign_key("fk_events_source", "sources", ["source_id"], ["id"])
    op.create_index("ix_events_source_record", "events", ["source_id", "source_record_id"])


def downgrade() -> None:
    op.drop_index("ix_events_source_record", table_name="events")
    with op.batch_alter_table("events") as batch:
        batch.drop_constraint("fk_events_source", type_="foreignkey")
        batch.drop_constraint("fk_events_analysis_run", type_="foreignkey")
        batch.drop_column("source_record_id")
        batch.drop_column("source_id")
        batch.drop_column("analysis_run_id")
