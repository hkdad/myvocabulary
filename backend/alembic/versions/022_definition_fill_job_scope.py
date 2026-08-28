"""Add scope to definition_fill_jobs; nullable bank_id for book-wide jobs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("definition_fill_jobs") as batch_op:
        batch_op.add_column(
            sa.Column("scope", sa.String(length=16), nullable=False, server_default="bank")
        )
        batch_op.alter_column("bank_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("definition_fill_jobs") as batch_op:
        batch_op.alter_column("bank_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("scope")
