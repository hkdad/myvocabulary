from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import utcnow


class DailyChallengeLog(Base):
    __tablename__ = "daily_challenge_logs"
    __table_args__ = (UniqueConstraint("learner_id", "challenge_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    challenge_date: Mapped[date] = mapped_column(Date)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    retention_count: Mapped[int] = mapped_column(Integer, default=0)
    learning_retention_count: Mapped[int] = mapped_column(Integer, default=0)
    mastered_retention_count: Mapped[int] = mapped_column(Integer, default=0)
    card_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    srs_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dictation_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
