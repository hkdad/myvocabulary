"""Store failed words JSON on definition fill jobs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "definition_fill_jobs",
        sa.Column("failed_words_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("definition_fill_jobs", "failed_words_json")
