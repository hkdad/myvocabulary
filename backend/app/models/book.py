from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, utcnow


class Book(Base, TimestampMixin):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    word_list_id: Mapped[int | None] = mapped_column(
        ForeignKey("word_lists.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    title: Mapped[str] = mapped_column(String(255))
    title_source: Mapped[str] = mapped_column(String(16), default="filename")
    original_filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="preview")
    coverage_target: Mapped[float] = mapped_column(Float, default=0.80)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_lemma_count: Mapped[int] = mapped_column(Integer, default=0)
    content_lemma_count: Mapped[int] = mapped_column(Integer, default=0)
    study_lemma_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_function_words: Mapped[int] = mapped_column(Integer, default=0)
    skipped_proper_nouns: Mapped[int] = mapped_column(Integer, default=0)
    coverage_curve_json: Mapped[str] = mapped_column(Text, default="{}")
    analysis_engine: Mapped[str] = mapped_column(String(16), default="fallback")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lemmas: Mapped[list["BookLemma"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="BookLemma.rank",
    )


class BookLemma(Base):
    __tablename__ = "book_lemmas"
    __table_args__ = (UniqueConstraint("book_id", "lemma"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    lemma: Mapped[str] = mapped_column(String(128), index=True)
    frequency: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    in_study_set: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    dictionary_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("dictionary_entries.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    book: Mapped[Book] = relationship(back_populates="lemmas")
