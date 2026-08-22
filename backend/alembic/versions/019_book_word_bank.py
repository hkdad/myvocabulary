"""Book metadata + per-lemma ranks for book-as-word-bank."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("word_list_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("coverage_target", sa.Float(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("unique_lemma_count", sa.Integer(), nullable=False),
        sa.Column("content_lemma_count", sa.Integer(), nullable=False),
        sa.Column("study_lemma_count", sa.Integer(), nullable=False),
        sa.Column("skipped_function_words", sa.Integer(), nullable=False),
        sa.Column("skipped_proper_nouns", sa.Integer(), nullable=False),
        sa.Column("coverage_curve_json", sa.Text(), nullable=False),
        sa.Column("analysis_engine", sa.String(length=16), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_list_id"], ["word_lists.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_list_id"),
    )
    op.create_index("ix_books_parent_id", "books", ["parent_id"])

    op.create_table(
        "book_lemmas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("lemma", sa.String(length=128), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("in_study_set", sa.Boolean(), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), nullable=False),
        sa.Column("dictionary_entry_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dictionary_entry_id"], ["dictionary_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "lemma"),
    )
    op.create_index("ix_book_lemmas_book_id", "book_lemmas", ["book_id"])
    op.create_index("ix_book_lemmas_lemma", "book_lemmas", ["lemma"])
    op.create_index("ix_book_lemmas_dictionary_entry_id", "book_lemmas", ["dictionary_entry_id"])


def downgrade() -> None:
    op.drop_index("ix_book_lemmas_dictionary_entry_id", table_name="book_lemmas")
    op.drop_index("ix_book_lemmas_lemma", table_name="book_lemmas")
    op.drop_index("ix_book_lemmas_book_id", table_name="book_lemmas")
    op.drop_table("book_lemmas")
    op.drop_index("ix_books_parent_id", table_name="books")
    op.drop_table("books")
