"""challenge entry queue

Revision ID: 003
Revises: 002
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("level_challenges", sa.Column("entry_ids_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("level_challenges", "entry_ids_json")
