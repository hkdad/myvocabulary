"""Add Traditional Chinese definition gloss to dictionary entries."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("dictionary_entries") as batch_op:
        batch_op.add_column(sa.Column("definition_zh_hant", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("dictionary_entries") as batch_op:
        batch_op.drop_column("definition_zh_hant")
