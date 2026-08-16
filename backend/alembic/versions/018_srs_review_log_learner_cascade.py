"""Add ON DELETE CASCADE to srs_review_log.learner_id."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "srs_review_log_new",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("srs_card_id", sa.Integer(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("quality", sa.Integer(), nullable=False),
        sa.Column("ease_factor_before", sa.Float(), nullable=True),
        sa.Column("ease_factor_after", sa.Float(), nullable=True),
        sa.Column("interval_before", sa.Integer(), nullable=True),
        sa.Column("interval_after", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["srs_card_id"], ["srs_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO srs_review_log_new (
            id, srs_card_id, learner_id, quality,
            ease_factor_before, ease_factor_after,
            interval_before, interval_after, reviewed_at
        )
        SELECT
            id, srs_card_id, learner_id, quality,
            ease_factor_before, ease_factor_after,
            interval_before, interval_after, reviewed_at
        FROM srs_review_log
        """
    )
    op.drop_table("srs_review_log")
    op.rename_table("srs_review_log_new", "srs_review_log")
    op.create_index("ix_srs_review_log_learner_id", "srs_review_log", ["learner_id"])
    op.create_index("ix_srs_review_log_srs_card_id", "srs_review_log", ["srs_card_id"])


def downgrade() -> None:
    op.create_table(
        "srs_review_log_old",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("srs_card_id", sa.Integer(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("quality", sa.Integer(), nullable=False),
        sa.Column("ease_factor_before", sa.Float(), nullable=True),
        sa.Column("ease_factor_after", sa.Float(), nullable=True),
        sa.Column("interval_before", sa.Integer(), nullable=True),
        sa.Column("interval_after", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"]),
        sa.ForeignKeyConstraint(["srs_card_id"], ["srs_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO srs_review_log_old (
            id, srs_card_id, learner_id, quality,
            ease_factor_before, ease_factor_after,
            interval_before, interval_after, reviewed_at
        )
        SELECT
            id, srs_card_id, learner_id, quality,
            ease_factor_before, ease_factor_after,
            interval_before, interval_after, reviewed_at
        FROM srs_review_log
        """
    )
    op.drop_table("srs_review_log")
    op.rename_table("srs_review_log_old", "srs_review_log")
    op.create_index("ix_srs_review_log_learner_id", "srs_review_log", ["learner_id"])
    op.create_index("ix_srs_review_log_srs_card_id", "srs_review_log", ["srs_card_id"])
