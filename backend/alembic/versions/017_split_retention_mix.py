"""Split daily_retention_mix into learning and mastered retention goals."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("learners") as batch_op:
        batch_op.add_column(
            sa.Column(
                "daily_learning_retention_mix",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "daily_mastered_retention_mix",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )

    op.execute(
        """
        UPDATE learners
        SET daily_learning_retention_mix =
                (daily_retention_mix - daily_retention_mix % 2) / 2 + daily_retention_mix % 2,
            daily_mastered_retention_mix =
                (daily_retention_mix - daily_retention_mix % 2) / 2
        """
    )

    with op.batch_alter_table("learners") as batch_op:
        batch_op.drop_column("daily_retention_mix")

    with op.batch_alter_table("daily_challenge_logs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "learning_retention_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "mastered_retention_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("daily_challenge_logs") as batch_op:
        batch_op.drop_column("mastered_retention_count")
        batch_op.drop_column("learning_retention_count")

    with op.batch_alter_table("learners") as batch_op:
        batch_op.add_column(
            sa.Column(
                "daily_retention_mix",
                sa.Integer(),
                nullable=False,
                server_default="2",
            )
        )

    op.execute(
        """
        UPDATE learners
        SET daily_retention_mix = daily_learning_retention_mix + daily_mastered_retention_mix
        """
    )

    with op.batch_alter_table("learners") as batch_op:
        batch_op.drop_column("daily_mastered_retention_mix")
        batch_op.drop_column("daily_learning_retention_mix")
