"""widen word bank level column for custom labels

Revision ID: 006
Revises: 005
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("word_list_items") as batch_op:
        batch_op.alter_column(
            "level",
            existing_type=sa.String(length=8),
            type_=sa.String(length=32),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("word_list_items") as batch_op:
        batch_op.alter_column(
            "level",
            existing_type=sa.String(length=32),
            type_=sa.String(length=8),
            existing_nullable=True,
        )
