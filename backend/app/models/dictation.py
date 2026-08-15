from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import utcnow


class DictationSession(Base):
    __tablename__ = "dictation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    word_list_id: Mapped[int | None] = mapped_column(ForeignKey("word_lists.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="word_list")
    mode: Mapped[str] = mapped_column(String(16))
    ui_mode_snapshot: Mapped[str] = mapped_column(String(8))
    total_words: Mapped[int] = mapped_column(Integer)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class DictationAttempt(Base):
    __tablename__ = "dictation_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("dictation_sessions.id", ondelete="CASCADE"), index=True
    )
    dictionary_entry_id: Mapped[int] = mapped_column(ForeignKey("dictionary_entries.id"))
    prompt_audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expected_word: Mapped[str] = mapped_column(String(128))
    submitted_answer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    hint_used: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
