"""Add title_source to books for name vs filename tracking."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "books",
        sa.Column("title_source", sa.String(length=16), nullable=False, server_default="filename"),
    )


def downgrade() -> None:
    op.drop_column("books", "title_source")
