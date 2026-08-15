from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, utcnow


class WordList(Base, TimestampMixin):
    __tablename__ = "word_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    level_tag: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="custom")
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_learner_id: Mapped[int | None] = mapped_column(
        ForeignKey("learners.id", ondelete="SET NULL"), nullable=True, index=True
    )

    items: Mapped[list["WordListItem"]] = relationship(back_populates="word_list")


class WordListItem(Base):
    __tablename__ = "word_list_items"
    __table_args__ = (UniqueConstraint("word_list_id", "dictionary_entry_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    word_list_id: Mapped[int] = mapped_column(
        ForeignKey("word_lists.id", ondelete="CASCADE"), index=True
    )
    dictionary_entry_id: Mapped[int] = mapped_column(ForeignKey("dictionary_entries.id"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    word_list: Mapped[WordList] = relationship(back_populates="items")
    dictionary_entry: Mapped["DictionaryEntry"] = relationship()
    categories: Mapped[list["WordListItemCategory"]] = relationship(
        back_populates="word_list_item",
        cascade="all, delete-orphan",
        order_by="WordListItemCategory.id",
    )


class WordListItemCategory(Base):
    __tablename__ = "word_list_item_categories"
    __table_args__ = (UniqueConstraint("word_list_item_id", "category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    word_list_item_id: Mapped[int] = mapped_column(
        ForeignKey("word_list_items.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(64), index=True)

    word_list_item: Mapped[WordListItem] = relationship(back_populates="categories")


class WordListAssignment(Base):
    __tablename__ = "word_list_assignments"
    __table_args__ = (UniqueConstraint("word_list_id", "learner_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    word_list_id: Mapped[int] = mapped_column(
        ForeignKey("word_lists.id", ondelete="CASCADE"), index=True
    )
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(default=utcnow)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class MistakeLog(Base):
    __tablename__ = "mistake_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    dictionary_entry_id: Mapped[int] = mapped_column(ForeignKey("dictionary_entries.id"))
    context: Mapped[str] = mapped_column(String(32))
    wrong_answer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)


from app.models.dictionary import DictionaryEntry  # noqa: E402
