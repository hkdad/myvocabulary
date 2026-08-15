from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, utcnow


class SrsCard(Base, TimestampMixin):
    __tablename__ = "srs_cards"
    __table_args__ = (UniqueConstraint("learner_id", "dictionary_entry_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    dictionary_entry_id: Mapped[int] = mapped_column(ForeignKey("dictionary_entries.id"))
    word_list_id: Mapped[int | None] = mapped_column(ForeignKey("word_lists.id"), nullable=True)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="new")
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dictionary_entry: Mapped["DictionaryEntry"] = relationship()


from app.models.dictionary import DictionaryEntry  # noqa: E402


class SrsReviewLog(Base):
    __tablename__ = "srs_review_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    srs_card_id: Mapped[int] = mapped_column(
        ForeignKey("srs_cards.id", ondelete="CASCADE"), index=True
    )
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id"), index=True)
    quality: Mapped[int] = mapped_column(Integer)
    ease_factor_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    ease_factor_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(default=utcnow)
