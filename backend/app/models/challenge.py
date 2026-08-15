from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import utcnow


class LevelChallenge(Base):
    __tablename__ = "level_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    challenge_type: Mapped[str] = mapped_column(String(32))
    target_level: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pass_threshold: Mapped[float] = mapped_column(Float, default=0.8)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    entry_ids_json: Mapped[str | None] = mapped_column(String(4096), nullable=True)


class LevelAssessment(Base):
    __tablename__ = "level_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    current_level: Mapped[str] = mapped_column(String(8))
    suggested_level: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    assessed_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LearnerBadge(Base):
    __tablename__ = "learner_badges"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    badge_type: Mapped[str] = mapped_column(String(32))
    earned_at: Mapped[datetime] = mapped_column(default=utcnow)
