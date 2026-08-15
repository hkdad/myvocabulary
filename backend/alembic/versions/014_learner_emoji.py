"""Add learner profile emoji."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("learners") as batch_op:
        batch_op.add_column(sa.Column("emoji", sa.String(length=16), nullable=True))

    op.execute(sa.text("UPDATE learners SET emoji = '🌟' WHERE emoji IS NULL"))


def downgrade() -> None:
    with op.batch_alter_table("learners") as batch_op:
        batch_op.drop_column("emoji")
