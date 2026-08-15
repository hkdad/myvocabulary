"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_parent_id", "users", ["parent_id"])
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "learners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("english_level", sa.String(length=8), nullable=False),
        sa.Column("ui_mode", sa.String(length=8), nullable=False),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("daily_review_goal", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_learners_user_id", "learners", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("device_label", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "dictionary_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word", sa.String(length=128), nullable=False),
        sa.Column("phonetic", sa.String(length=128), nullable=True),
        sa.Column("part_of_speech", sa.String(length=64), nullable=True),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("example_sentence", sa.Text(), nullable=True),
        sa.Column("synonyms", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("audio_path", sa.String(length=512), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word"),
    )
    op.create_index("ix_dictionary_entries_word", "dictionary_entries", ["word"])

    op.create_table(
        "word_lists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("level_tag", sa.String(length=8), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_word_lists_parent_id", "word_lists", ["parent_id"])

    op.create_table(
        "word_list_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_list_id", sa.Integer(), nullable=False),
        sa.Column("dictionary_entry_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dictionary_entry_id"], ["dictionary_entries.id"]),
        sa.ForeignKeyConstraint(["word_list_id"], ["word_lists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_list_id", "dictionary_entry_id"),
    )
    op.create_index("ix_word_list_items_word_list_id", "word_list_items", ["word_list_id"])

    op.create_table(
        "word_list_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_list_id", sa.Integer(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_list_id"], ["word_lists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_list_id", "learner_id"),
    )
    op.create_index("ix_word_list_assignments_learner_id", "word_list_assignments", ["learner_id"])

    op.create_table(
        "srs_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("dictionary_entry_id", sa.Integer(), nullable=False),
        sa.Column("word_list_id", sa.Integer(), nullable=True),
        sa.Column("ease_factor", sa.Float(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_quality", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dictionary_entry_id"], ["dictionary_entries.id"]),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_list_id"], ["word_lists.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("learner_id", "dictionary_entry_id"),
    )
    op.create_index("ix_srs_cards_learner_id", "srs_cards", ["learner_id"])

    op.create_table(
        "srs_review_log",
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
    op.create_index("ix_srs_review_log_learner_id", "srs_review_log", ["learner_id"])
    op.create_index("ix_srs_review_log_srs_card_id", "srs_review_log", ["srs_card_id"])

    op.create_table(
        "dictation_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("word_list_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("ui_mode_snapshot", sa.String(length=8), nullable=False),
        sa.Column("total_words", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_list_id"], ["word_lists.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dictation_sessions_learner_id", "dictation_sessions", ["learner_id"])

    op.create_table(
        "dictation_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("dictionary_entry_id", sa.Integer(), nullable=False),
        sa.Column("prompt_audio_path", sa.String(length=512), nullable=True),
        sa.Column("expected_word", sa.String(length=128), nullable=False),
        sa.Column("submitted_answer", sa.String(length=255), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("hint_used", sa.Boolean(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dictionary_entry_id"], ["dictionary_entries.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["dictation_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dictation_attempts_session_id", "dictation_attempts", ["session_id"])

    op.create_table(
        "mistake_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("dictionary_entry_id", sa.Integer(), nullable=False),
        sa.Column("context", sa.String(length=32), nullable=False),
        sa.Column("wrong_answer", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dictionary_entry_id"], ["dictionary_entries.id"]),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mistake_log_learner_id", "mistake_log", ["learner_id"])

    op.create_table(
        "level_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("challenge_type", sa.String(length=32), nullable=False),
        sa.Column("target_level", sa.String(length=8), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("pass_threshold", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_level_challenges_learner_id", "level_challenges", ["learner_id"])

    op.create_table(
        "level_assessments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("current_level", sa.String(length=8), nullable=False),
        sa.Column("suggested_level", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=1024), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_level_assessments_learner_id", "level_assessments", ["learner_id"])

    op.create_table(
        "learner_badges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("badge_type", sa.String(length=32), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learner_badges_learner_id", "learner_badges", ["learner_id"])

    op.execute(
        """
        CREATE VIRTUAL TABLE dictionary_entries_fts USING fts5(
            word,
            definition,
            example_sentence,
            content='dictionary_entries',
            content_rowid='id',
            tokenize='porter unicode61'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER dictionary_entries_ai AFTER INSERT ON dictionary_entries BEGIN
          INSERT INTO dictionary_entries_fts(rowid, word, definition, example_sentence)
          VALUES (new.id, new.word, new.definition, new.example_sentence);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER dictionary_entries_ad AFTER DELETE ON dictionary_entries BEGIN
          INSERT INTO dictionary_entries_fts(dictionary_entries_fts, rowid, word, definition, example_sentence)
          VALUES ('delete', old.id, old.word, old.definition, old.example_sentence);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER dictionary_entries_au AFTER UPDATE ON dictionary_entries BEGIN
          INSERT INTO dictionary_entries_fts(dictionary_entries_fts, rowid, word, definition, example_sentence)
          VALUES ('delete', old.id, old.word, old.definition, old.example_sentence);
          INSERT INTO dictionary_entries_fts(rowid, word, definition, example_sentence)
          VALUES (new.id, new.word, new.definition, new.example_sentence);
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS dictionary_entries_au")
    op.execute("DROP TRIGGER IF EXISTS dictionary_entries_ad")
    op.execute("DROP TRIGGER IF EXISTS dictionary_entries_ai")
    op.execute("DROP TABLE IF EXISTS dictionary_entries_fts")

    op.drop_table("learner_badges")
    op.drop_table("level_assessments")
    op.drop_table("level_challenges")
    op.drop_table("mistake_log")
    op.drop_table("dictation_attempts")
    op.drop_table("dictation_sessions")
    op.drop_table("srs_review_log")
    op.drop_table("srs_cards")
    op.drop_table("word_list_assignments")
    op.drop_table("word_list_items")
    op.drop_table("word_lists")
    op.drop_table("dictionary_entries")
    op.drop_table("refresh_tokens")
    op.drop_table("learners")
    op.drop_table("users")
