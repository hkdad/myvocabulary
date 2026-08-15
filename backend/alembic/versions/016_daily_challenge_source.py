"""Store daily challenge mix source (random / category / list)."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("daily_challenge_logs") as batch_op:
        batch_op.add_column(sa.Column("source_kind", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("source_ref", sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("daily_challenge_logs") as batch_op:
        batch_op.drop_column("source_ref")
        batch_op.drop_column("source_kind")
