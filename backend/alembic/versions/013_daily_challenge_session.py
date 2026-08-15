"""Daily challenge session progress fields and dictation source."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("daily_challenge_logs") as batch_op:
        batch_op.add_column(sa.Column("card_ids_json", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("srs_completed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("dictation_completed_at", sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table("dictation_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(length=32), nullable=False, server_default="word_list")
        )


def downgrade() -> None:
    with op.batch_alter_table("dictation_sessions") as batch_op:
        batch_op.drop_column("source")

    with op.batch_alter_table("daily_challenge_logs") as batch_op:
        batch_op.drop_column("dictation_completed_at")
        batch_op.drop_column("srs_completed_at")
        batch_op.drop_column("card_ids_json")
