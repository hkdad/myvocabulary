"""learner-owned word lists

Revision ID: 004
Revises: 003
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "word_lists",
        sa.Column("created_by_learner_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_word_lists_created_by_learner_id",
        "word_lists",
        ["created_by_learner_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_word_lists_created_by_learner_id", table_name="word_lists")
    op.drop_column("word_lists", "created_by_learner_id")
