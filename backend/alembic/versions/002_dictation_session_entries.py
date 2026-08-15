"""dictation session entry queue

Revision ID: 002
Revises: 001
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("dictation_sessions", sa.Column("entry_ids_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("dictation_sessions", "entry_ids_json")
