from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Learner(Base, TimestampMixin):
    __tablename__ = "learners"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(128))
    age: Mapped[int] = mapped_column(Integer)
    english_level: Mapped[str] = mapped_column(String(8))
    ui_mode: Mapped[str] = mapped_column(String(8))
    emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    daily_review_goal: Mapped[int] = mapped_column(Integer, default=20)
    daily_new_word_goal: Mapped[int] = mapped_column(Integer, default=5)
    daily_learning_retention_mix: Mapped[int] = mapped_column(Integer, default=1)
    daily_mastered_retention_mix: Mapped[int] = mapped_column(Integer, default=1)

    user: Mapped["User"] = relationship(back_populates="learner_profile")


from app.models.user import User  # noqa: E402
