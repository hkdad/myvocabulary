"""Add definition_fill_jobs for parent word-bank backfill."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "definition_fill_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("bank_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("filled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bank_id"], ["word_lists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_definition_fill_jobs_bank_id"),
        "definition_fill_jobs",
        ["bank_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_definition_fill_jobs_parent_id"),
        "definition_fill_jobs",
        ["parent_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_definition_fill_jobs_parent_id"), table_name="definition_fill_jobs")
    op.drop_index(op.f("ix_definition_fill_jobs_bank_id"), table_name="definition_fill_jobs")
    op.drop_table("definition_fill_jobs")
