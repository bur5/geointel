"""Create the advisory history and checkpoints.

Revision ID: 0009_early_warning
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_early_warning"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "early_warning_checkpoints",
        sa.Column("namespace", sa.String(128), primary_key=True),
        sa.Column("stream_id", sa.String(64), primary_key=True),
        sa.Column("state", sa.JSON()),
    )
    op.create_table(
        "early_warning_history",
        sa.Column("namespace", sa.String(128), primary_key=True),
        sa.Column("stream_id", sa.String(64), primary_key=True),
        sa.Column("period_end", sa.Date(), primary_key=True),
        sa.Column("as_of", sa.Date(), primary_key=True),
        sa.Column("revision_cutoff", sa.Date(), primary_key=True),
        sa.Column("event_id", sa.String(64), unique=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["namespace", "stream_id"],
            ["early_warning_checkpoints.namespace", "early_warning_checkpoints.stream_id"],
        ),
    )


def downgrade() -> None:
    op.drop_table("early_warning_history")
    op.drop_table("early_warning_checkpoints")
