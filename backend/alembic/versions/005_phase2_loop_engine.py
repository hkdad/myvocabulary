"""phase 2 loop engine

Revision ID: 005
Revises: 004
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("word_list_items", sa.Column("level", sa.String(length=8), nullable=True))
    op.add_column(
        "word_list_items",
        sa.Column("category", sa.String(length=64), nullable=False, server_default="General"),
    )

    op.add_column(
        "learners",
        sa.Column("daily_new_word_goal", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "learners",
        sa.Column("daily_retention_mix", sa.Integer(), nullable=False, server_default="2"),
    )

    op.add_column("srs_cards", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "daily_challenge_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "learner_id",
            sa.Integer(),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("challenge_date", sa.Date(), nullable=False),
        sa.Column("new_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retention_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("learner_id", "challenge_date", name="uq_daily_challenge_learner_date"),
    )
    op.create_index(
        "ix_daily_challenge_logs_learner_id",
        "daily_challenge_logs",
        ["learner_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_challenge_logs_learner_id", table_name="daily_challenge_logs")
    op.drop_table("daily_challenge_logs")
    op.drop_column("srs_cards", "released_at")
    op.drop_column("learners", "daily_retention_mix")
    op.drop_column("learners", "daily_new_word_goal")
    op.drop_column("word_list_items", "category")
    op.drop_column("word_list_items", "level")
