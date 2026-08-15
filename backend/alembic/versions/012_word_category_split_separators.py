"""Split category values on comma / spaced hyphen. Idempotent."""

import re
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORY_SPLIT_RE = re.compile(
    r"\s+and\s+|\s*;\s*|\s*,\s*|\s+-\s+",
    re.IGNORECASE,
)
_LEADING_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)
_CATEGORY_ALIASES = {
    "communications": "Communication",
    "sport": "Sports",
}


def _format_category_name(category: str) -> str:
    cleaned = " ".join(category.strip().split())
    if not cleaned:
        return cleaned

    without_article = _LEADING_ARTICLE_RE.sub("", cleaned).strip()
    if without_article:
        cleaned = without_article

    formatted = cleaned[0].upper() + cleaned[1:].lower()
    return _CATEGORY_ALIASES.get(formatted.casefold(), formatted)


def _normalize_parts(category: str) -> list[str]:
    parts = [part.strip() for part in _CATEGORY_SPLIT_RE.split(category.strip()) if part.strip()]
    if not parts:
        return ["General"]

    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        formatted = _format_category_name(part)
        if not formatted:
            continue
        key = formatted.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(formatted)
    return deduped or ["General"]


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, word_list_item_id, category FROM word_list_item_categories")
    ).fetchall()

    for row_id, item_id, category in rows:
        parts = _normalize_parts(category)
        if parts == [category]:
            continue

        conn.execute(
            sa.text("DELETE FROM word_list_item_categories WHERE id = :row_id"),
            {"row_id": row_id},
        )
        for part in parts:
            existing = conn.execute(
                sa.text(
                    "SELECT id FROM word_list_item_categories "
                    "WHERE word_list_item_id = :item_id AND category = :category"
                ),
                {"item_id": item_id, "category": part},
            ).fetchone()
            if existing is None:
                conn.execute(
                    sa.text(
                        "INSERT INTO word_list_item_categories (word_list_item_id, category) "
                        "VALUES (:item_id, :category)"
                    ),
                    {"item_id": item_id, "category": part},
                )


def downgrade() -> None:
    pass
