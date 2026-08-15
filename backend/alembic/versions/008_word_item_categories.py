"""word bank item categories junction table

Revision ID: 008
Revises: 007
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "word_list_item_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_list_item_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["word_list_item_id"], ["word_list_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_list_item_id", "category"),
    )
    op.create_index(
        "ix_word_list_item_categories_word_list_item_id",
        "word_list_item_categories",
        ["word_list_item_id"],
    )
    op.create_index(
        "ix_word_list_item_categories_category",
        "word_list_item_categories",
        ["category"],
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, category FROM word_list_items WHERE category IS NOT NULL")
    ).fetchall()
    for item_id, stored in rows:
        if not stored or not str(stored).strip():
            categories = ["General"]
        else:
            categories = [
                part.strip()
                for part in __import__("re").split(
                    r"\s+and\s+", str(stored), flags=__import__("re").I
                )
                if part.strip()
            ] or ["General"]
        seen: set[str] = set()
        for category in categories:
            key = category.casefold()
            if key in seen:
                continue
            seen.add(key)
            conn.execute(
                sa.text(
                    "INSERT INTO word_list_item_categories (word_list_item_id, category) "
                    "VALUES (:item_id, :category)"
                ),
                {"item_id": item_id, "category": category},
            )

    with op.batch_alter_table("word_list_items") as batch_op:
        batch_op.drop_column("category")


def downgrade() -> None:
    with op.batch_alter_table("word_list_items") as batch_op:
        batch_op.add_column(
            sa.Column("category", sa.String(length=255), nullable=False, server_default="General")
        )

    conn = op.get_bind()
    items = conn.execute(sa.text("SELECT id FROM word_list_items")).fetchall()
    for (item_id,) in items:
        cats = conn.execute(
            sa.text(
                "SELECT category FROM word_list_item_categories "
                "WHERE word_list_item_id = :item_id ORDER BY id"
            ),
            {"item_id": item_id},
        ).fetchall()
        stored = " and ".join(c[0] for c in cats) if cats else "General"
        conn.execute(
            sa.text("UPDATE word_list_items SET category = :category WHERE id = :item_id"),
            {"category": stored, "item_id": item_id},
        )

    op.drop_index("ix_word_list_item_categories_category", table_name="word_list_item_categories")
    op.drop_index(
        "ix_word_list_item_categories_word_list_item_id", table_name="word_list_item_categories"
    )
    op.drop_table("word_list_item_categories")
