"""Re-apply category capitalization after re-imports. Idempotent."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _format_category_name(category: str) -> str:
    cleaned = category.strip()
    if not cleaned:
        return cleaned
    return cleaned[0].upper() + cleaned[1:].lower()


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, word_list_item_id, category FROM word_list_item_categories")
    ).fetchall()

    for row_id, item_id, category in rows:
        formatted = _format_category_name(category)
        if formatted == category:
            continue

        existing = conn.execute(
            sa.text(
                "SELECT id FROM word_list_item_categories "
                "WHERE word_list_item_id = :item_id AND category = :category"
            ),
            {"item_id": item_id, "category": formatted},
        ).fetchone()
        if existing is not None:
            conn.execute(
                sa.text("DELETE FROM word_list_item_categories WHERE id = :row_id"),
                {"row_id": row_id},
            )
        else:
            conn.execute(
                sa.text(
                    "UPDATE word_list_item_categories SET category = :category WHERE id = :row_id"
                ),
                {"category": formatted, "row_id": row_id},
            )


def downgrade() -> None:
    pass
